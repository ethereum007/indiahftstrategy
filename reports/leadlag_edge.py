from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import (
    ManifestIntegrity,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from research.leadlag import MEASUREMENT_REQUIRED_ARTIFACTS, MEASUREMENT_RUN_TYPE


LEAD_LAG_STRATEGY = "lead_lag_taker"
RUN_TYPE = "leadlag_edge_audit"


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
    min_best_latency_fill_rate: float | None = None
    min_best_latency_avg_net_edge: float | None = None
    max_best_latency_cost_drag_ratio: float | None = None


@dataclass(frozen=True)
class LeadLagEdgeAudit:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    provenance: pd.DataFrame = field(default_factory=pd.DataFrame)

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
    strategy: str = LEAD_LAG_STRATEGY,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
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
    summary = _summary(metrics, checks, strategy=strategy, market=market)
    return LeadLagEdgeAudit(metrics=metrics, checks=checks, summary=summary)


def write_leadlag_edge_audit(
    measure_dir: str | Path,
    *,
    output_dir: str | Path,
    thresholds: LeadLagEdgeThresholds | None = None,
    strategy: str = LEAD_LAG_STRATEGY,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> LeadLagEdgeAudit:
    source = Path(measure_dir).resolve()
    measurement_manifest = source / "manifest.json"
    integrity = verify_experiment_manifest(
        measurement_manifest,
        expected_run_type=MEASUREMENT_RUN_TYPE,
        required_artifacts=MEASUREMENT_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    cross_correlation = _read_required(source / "cross_correlation.csv")
    lag_profile = _read_required(source / "lag_profile.csv")
    latency_curve = _read_required(source / "latency_curve.csv")
    thresholds = thresholds or LeadLagEdgeThresholds()
    audit = evaluate_leadlag_edge(
        cross_correlation,
        lag_profile,
        latency_curve,
        thresholds=thresholds,
        strategy=strategy,
        market=market,
    )
    provenance = _measurement_provenance(source, integrity)
    checks = pd.concat(
        [_measurement_manifest_check(integrity), audit.checks],
        ignore_index=True,
    )
    summary = _summary(audit.metrics, checks, strategy=strategy, market=market)
    provenance_row = provenance.iloc[0]
    summary["measurement_manifest_current"] = bool(integrity.passed)
    summary["measurement_manifest_error"] = str(integrity.error)
    summary["measurement_manifest_sha256"] = str(
        provenance_row["manifest_sha256"]
    )
    summary["measurement_input_fingerprint_count"] = int(
        integrity.input_fingerprint_count
    )
    summary["measurement_input_fingerprint_matches"] = int(
        integrity.input_fingerprint_match_count
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit.metrics.to_csv(out / "leadlag_edge_metrics.csv", index=False)
    checks.to_csv(out / "leadlag_edge_checks.csv", index=False)
    summary.to_csv(out / "leadlag_edge_summary.csv", index=False)
    provenance.to_csv(out / "leadlag_edge_measurement_provenance.csv", index=False)
    dependencies = manifest_dependency_paths(measurement_manifest)
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"strategy": strategy, "market": market, "thresholds": asdict(thresholds)},
        inputs={
            "leadlag_measurement": source,
            "leadlag_measurement_manifest": measurement_manifest,
            "leadlag_measurement_dependencies": dependencies,
        },
        extra={
            "passed": bool(summary.iloc[0]["passed"]),
            "measurement_manifest_current": bool(integrity.passed),
            "measurement_manifest_sha256": str(
                provenance_row["manifest_sha256"]
            ),
            "authorizes_submission": False,
        },
    )
    return LeadLagEdgeAudit(
        metrics=audit.metrics,
        checks=checks,
        summary=summary,
        output_dir=out,
        provenance=provenance,
    )


def _measurement_provenance(
    source: Path,
    integrity: ManifestIntegrity,
) -> pd.DataFrame:
    manifest_path = integrity.manifest_path
    return pd.DataFrame(
        [
            {
                "measurement_path": str(source),
                "manifest_path": str(manifest_path),
                "manifest_exists": bool(integrity.exists),
                "manifest_readable": bool(integrity.readable),
                "manifest_sha256": (
                    file_sha256(manifest_path) if manifest_path.is_file() else ""
                ),
                "run_type": integrity.run_type,
                "expected_run_type": integrity.expected_run_type,
                "run_type_matches": bool(integrity.run_type_matches),
                "artifact_count": int(integrity.artifact_count),
                "artifact_matches": int(integrity.artifact_match_count),
                "required_artifact_count": int(
                    integrity.required_artifact_count
                ),
                "required_artifact_matches": int(
                    integrity.required_artifact_match_count
                ),
                "input_fingerprint_count": int(
                    integrity.input_fingerprint_count
                ),
                "input_fingerprint_matches": int(
                    integrity.input_fingerprint_match_count
                ),
                "passed": bool(integrity.passed),
                "error": integrity.error,
                "recommendation": (
                    "audit_current_measurement"
                    if integrity.passed
                    else "rerun_measure_leadlag_from_current_source_files"
                ),
            }
        ]
    )


def _measurement_manifest_check(integrity: ManifestIntegrity) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "check": "measurement_manifest_current",
                "value": float(bool(integrity.passed)),
                "operator": "==",
                "threshold": 1.0,
                "passed": bool(integrity.passed),
                "reason": (
                    ""
                    if integrity.passed
                    else "lead-lag measurement manifest failed: "
                    f"{integrity.error or 'verification_failed'}"
                ),
            }
        ]
    )


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
    fill_rate_source = (
        work["fill_rate"]
        if "fill_rate" in work
        else work.get("win_rate", pd.Series(np.nan, index=work.index))
    )
    work["fill_rate"] = pd.to_numeric(fill_rate_source, errors="coerce")
    derived_avg_net_edge = work["net_pnl"].div(work["fills"].replace(0, np.nan))
    if "avg_net_edge" in work:
        work["avg_net_edge"] = pd.to_numeric(
            work["avg_net_edge"], errors="coerce"
        ).fillna(derived_avg_net_edge)
    else:
        work["avg_net_edge"] = derived_avg_net_edge
    if "cost_drag_ratio" in work:
        work["cost_drag_ratio"] = pd.to_numeric(
            work["cost_drag_ratio"], errors="coerce"
        )
    else:
        work["cost_drag_ratio"] = np.nan
    if work["net_pnl"].notna().any():
        best = work.sort_values(["net_pnl", "fills"], ascending=[False, False]).iloc[0]
        best_latency_ns = int(best["latency_ns"])
        best_net_pnl = float(best["net_pnl"])
        best_fills = int(best["fills"])
        best_win_rate = _float(best, "win_rate")
        best_fill_rate = _float(best, "fill_rate")
        if np.isnan(best_fill_rate):
            best_fill_rate = best_win_rate
        best_avg_edge = _float(best, "avg_edge")
        best_gross_pnl = _float(best, "gross_pnl")
        best_round_trip_cost = _float(best, "round_trip_cost")
        best_avg_net_edge = _float(best, "avg_net_edge")
        if np.isnan(best_avg_net_edge) and best_fills > 0:
            best_avg_net_edge = best_net_pnl / best_fills
        best_cost_drag_ratio = _float(best, "cost_drag_ratio")
        if np.isnan(best_cost_drag_ratio) and best_gross_pnl > 0:
            best_cost_drag_ratio = best_round_trip_cost / best_gross_pnl
        best_net_edge_bps = _float(best, "net_edge_bps")
    else:
        best_latency_ns = np.nan
        best_net_pnl = np.nan
        best_fills = 0
        best_win_rate = np.nan
        best_fill_rate = np.nan
        best_avg_edge = np.nan
        best_gross_pnl = np.nan
        best_round_trip_cost = np.nan
        best_avg_net_edge = np.nan
        best_cost_drag_ratio = np.nan
        best_net_edge_bps = np.nan

    viable_mask = (
        (work["net_pnl"] >= thresholds.min_best_latency_net_pnl)
        & (work["fills"] >= thresholds.min_best_latency_fills)
    )
    if thresholds.min_best_latency_fill_rate is not None:
        viable_mask &= (
            work["fill_rate"] >= thresholds.min_best_latency_fill_rate
        )
    if thresholds.min_best_latency_avg_net_edge is not None:
        viable_mask &= (
            work["avg_net_edge"] >= thresholds.min_best_latency_avg_net_edge
        )
    if thresholds.max_best_latency_cost_drag_ratio is not None:
        viable_mask &= (
            work["cost_drag_ratio"]
            <= thresholds.max_best_latency_cost_drag_ratio
        )
    viable = work.loc[viable_mask]
    max_profitable_latency_ns = int(viable["latency_ns"].max()) if not viable.empty else np.nan
    return {
        "latency_rows": int(len(work)),
        "best_latency_ns": best_latency_ns,
        "best_latency_net_pnl": best_net_pnl,
        "best_latency_fills": best_fills,
        "best_latency_fill_rate": best_fill_rate,
        "best_latency_win_rate": best_win_rate,
        "best_latency_avg_edge": best_avg_edge,
        "best_latency_gross_pnl": best_gross_pnl,
        "best_latency_round_trip_cost": best_round_trip_cost,
        "best_latency_avg_net_edge": best_avg_net_edge,
        "best_latency_cost_drag_ratio": best_cost_drag_ratio,
        "best_latency_net_edge_bps": best_net_edge_bps,
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
    if thresholds.min_best_latency_fill_rate is not None:
        checks.append(
            _threshold_check(
                row,
                "best_latency_fill_rate",
                ">=",
                thresholds.min_best_latency_fill_rate,
            )
        )
    if thresholds.min_best_latency_avg_net_edge is not None:
        checks.append(
            _threshold_check(
                row,
                "best_latency_avg_net_edge",
                ">=",
                thresholds.min_best_latency_avg_net_edge,
            )
        )
    if thresholds.max_best_latency_cost_drag_ratio is not None:
        checks.append(
            _threshold_check(
                row,
                "best_latency_cost_drag_ratio",
                "<=",
                thresholds.max_best_latency_cost_drag_ratio,
            )
        )
    return pd.DataFrame(checks)


def _summary(metrics: pd.DataFrame, checks: pd.DataFrame, *, strategy: str, market: str) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    metric = metrics.iloc[0]
    return pd.DataFrame(
        [
            {
                "strategy": strategy,
                "market": market,
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "replay_or_sweep_candidate" if passed else "keep_researching",
                "event_count": int(metric["event_count"]),
                "best_lag_ns": metric["best_lag_ns"],
                "best_abs_correlation": metric["best_abs_correlation"],
                "update_rate": metric["update_rate"],
                "best_latency_ns": metric["best_latency_ns"],
                "best_latency_net_pnl": metric["best_latency_net_pnl"],
                "best_latency_fill_rate": metric["best_latency_fill_rate"],
                "best_latency_win_rate": metric["best_latency_win_rate"],
                "best_latency_gross_pnl": metric["best_latency_gross_pnl"],
                "best_latency_round_trip_cost": metric[
                    "best_latency_round_trip_cost"
                ],
                "best_latency_avg_net_edge": metric[
                    "best_latency_avg_net_edge"
                ],
                "best_latency_cost_drag_ratio": metric[
                    "best_latency_cost_drag_ratio"
                ],
                "best_latency_net_edge_bps": metric[
                    "best_latency_net_edge_bps"
                ],
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
    if (
        thresholds.min_best_latency_fill_rate is not None
        and not 0 <= thresholds.min_best_latency_fill_rate <= 1
    ):
        raise ValueError("min_best_latency_fill_rate must be between 0 and 1")
    if (
        thresholds.max_best_latency_cost_drag_ratio is not None
        and thresholds.max_best_latency_cost_drag_ratio < 0
    ):
        raise ValueError(
            "max_best_latency_cost_drag_ratio must be non-negative"
        )
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
