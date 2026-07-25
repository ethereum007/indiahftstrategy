from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    ManifestIntegrity,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from scanners.run_parity_box import (
    PARITY_SCAN_REQUIRED_ARTIFACTS,
    PARITY_SCAN_RUN_TYPE,
)


PARITY_EDGE_RUN_TYPE = "parity_edge_audit"
PARITY_EDGE_REQUIRED_ARTIFACTS = (
    "parity_edge_metrics.csv",
    "parity_edge_checks.csv",
    "parity_edge_summary.csv",
)


@dataclass(frozen=True)
class ParityEdgeThresholds:
    min_total_opportunities: int = 1
    min_parity_opportunities: int = 0
    min_box_opportunities: int = 0
    min_total_net_edge: float = 0.0
    min_median_net_edge: float = 0.0
    min_best_net_edge: float = 0.0
    min_median_persistence_ticks: float = 0.0
    min_direction_count: int = 1
    max_future_staleness_ns: int | None = None


@dataclass(frozen=True)
class ParityEdgeAudit:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def evaluate_parity_edge(
    parity_opportunities: pd.DataFrame,
    box_opportunities: pd.DataFrame,
    *,
    thresholds: ParityEdgeThresholds | None = None,
) -> ParityEdgeAudit:
    thresholds = thresholds or ParityEdgeThresholds()
    _validate_thresholds(thresholds)
    parity = _normalize_opportunities(parity_opportunities, scanner="parity")
    boxes = _normalize_opportunities(box_opportunities, scanner="box")
    combined = pd.concat([parity, boxes], ignore_index=True, sort=False)
    metrics = pd.DataFrame([_metrics(parity, boxes, combined)])
    checks = _checks(metrics.iloc[0], thresholds)
    summary = _summary(metrics, checks)
    return ParityEdgeAudit(metrics=metrics, checks=checks, summary=summary)


def write_parity_edge_audit(
    scan_dir: str | Path,
    *,
    output_dir: str | Path,
    thresholds: ParityEdgeThresholds | None = None,
) -> ParityEdgeAudit:
    source = Path(scan_dir).resolve()
    scan_manifest = source / "manifest.json"
    scan_integrity = verify_experiment_manifest(
        scan_manifest,
        expected_run_type=PARITY_SCAN_RUN_TYPE,
        required_artifacts=PARITY_SCAN_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    parity = _read_required(source / "parity_opportunities.csv")
    boxes = _read_required(source / "box_opportunities.csv")
    thresholds = thresholds or ParityEdgeThresholds()
    base_audit = evaluate_parity_edge(
        parity,
        boxes,
        thresholds=thresholds,
    )
    checks = pd.concat(
        [
            _scan_manifest_check(scan_integrity),
            base_audit.checks,
        ],
        ignore_index=True,
    )
    summary = _summary(base_audit.metrics, checks)
    summary["scan_manifest_current"] = bool(
        scan_integrity.passed
    )
    summary["scan_manifest_error"] = str(scan_integrity.error)
    audit = ParityEdgeAudit(
        base_audit.metrics,
        checks,
        summary,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit.metrics.to_csv(out / "parity_edge_metrics.csv", index=False)
    audit.checks.to_csv(out / "parity_edge_checks.csv", index=False)
    audit.summary.to_csv(out / "parity_edge_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type=PARITY_EDGE_RUN_TYPE,
        parameters={"thresholds": asdict(thresholds)},
        inputs={
            "scan": source,
            "scan_manifest": scan_manifest,
            "scan_dependencies": manifest_dependency_paths(
                scan_manifest
            ),
        },
        extra={
            "scan_manifest_current": bool(
                scan_integrity.passed
            ),
        },
    )
    return ParityEdgeAudit(audit.metrics, audit.checks, audit.summary, out)


def _scan_manifest_check(
    integrity: ManifestIntegrity,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "check": "scan_manifest_current",
                "value": float(bool(integrity.passed)),
                "operator": "is",
                "threshold": 1.0,
                "passed": bool(integrity.passed),
                "reason": (
                    ""
                    if integrity.passed
                    else "parity scan manifest failed: "
                    f"{integrity.error or 'verification_failed'}"
                ),
            }
        ]
    )


def _normalize_opportunities(frame: pd.DataFrame, *, scanner: str) -> pd.DataFrame:
    out = frame.copy()
    if "scanner" not in out.columns:
        out["scanner"] = scanner
    for column in ["net_edge", "edge_per_unit", "persistence_ticks", "qty"]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _metrics(parity: pd.DataFrame, boxes: pd.DataFrame, combined: pd.DataFrame) -> dict[str, Any]:
    net_edge = _numeric(combined, "net_edge")
    edge_per_unit = _numeric(combined, "edge_per_unit")
    persistence = _numeric(combined, "persistence_ticks")
    return {
        "total_opportunities": int(len(combined)),
        "parity_opportunities": int(len(parity)),
        "box_opportunities": int(len(boxes)),
        "total_net_edge": float(net_edge.sum(skipna=True)) if not net_edge.empty else 0.0,
        "median_net_edge": float(net_edge.median(skipna=True)) if not net_edge.empty else np.nan,
        "best_net_edge": float(net_edge.max(skipna=True)) if not net_edge.empty else np.nan,
        "median_edge_per_unit": float(edge_per_unit.median(skipna=True)) if not edge_per_unit.empty else np.nan,
        "best_edge_per_unit": float(edge_per_unit.max(skipna=True)) if not edge_per_unit.empty else np.nan,
        "median_persistence_ticks": float(persistence.median(skipna=True)) if not persistence.empty else np.nan,
        "max_persistence_ticks": float(persistence.max(skipna=True)) if not persistence.empty else np.nan,
        "direction_count": _nunique(combined, "direction"),
        "regime_count": _nunique(combined, "regime"),
        "expiry_count": _nunique(combined, "expiry"),
        "max_future_staleness_ns": _max_future_staleness(parity),
        "median_future_staleness_ns": _median_future_staleness(parity),
    }


def _checks(row: pd.Series, thresholds: ParityEdgeThresholds) -> pd.DataFrame:
    checks = [
        _threshold_check(row, "total_opportunities", ">=", thresholds.min_total_opportunities),
        _threshold_check(row, "parity_opportunities", ">=", thresholds.min_parity_opportunities),
        _threshold_check(row, "box_opportunities", ">=", thresholds.min_box_opportunities),
        _threshold_check(row, "total_net_edge", ">=", thresholds.min_total_net_edge),
        _threshold_check(row, "median_net_edge", ">=", thresholds.min_median_net_edge),
        _threshold_check(row, "best_net_edge", ">=", thresholds.min_best_net_edge),
        _threshold_check(row, "median_persistence_ticks", ">=", thresholds.min_median_persistence_ticks),
        _threshold_check(row, "direction_count", ">=", thresholds.min_direction_count),
    ]
    if thresholds.max_future_staleness_ns is not None and int(row.get("parity_opportunities", 0)) > 0:
        checks.append(_threshold_check(row, "max_future_staleness_ns", "<=", thresholds.max_future_staleness_ns))
    return pd.DataFrame(checks)


def _summary(metrics: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    row = metrics.iloc[0]
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "replay_or_sweep_candidate" if passed else "keep_scanning",
                "total_opportunities": int(row["total_opportunities"]),
                "parity_opportunities": int(row["parity_opportunities"]),
                "box_opportunities": int(row["box_opportunities"]),
                "total_net_edge": float(row["total_net_edge"]),
                "median_net_edge": row["median_net_edge"],
                "best_net_edge": row["best_net_edge"],
                "median_persistence_ticks": row["median_persistence_ticks"],
                "max_future_staleness_ns": row["max_future_staleness_ns"],
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


def _validate_thresholds(thresholds: ParityEdgeThresholds) -> None:
    if thresholds.min_total_opportunities < 0:
        raise ValueError("min_total_opportunities must be non-negative")
    if thresholds.min_parity_opportunities < 0:
        raise ValueError("min_parity_opportunities must be non-negative")
    if thresholds.min_box_opportunities < 0:
        raise ValueError("min_box_opportunities must be non-negative")
    if thresholds.min_direction_count < 0:
        raise ValueError("min_direction_count must be non-negative")
    if thresholds.max_future_staleness_ns is not None and thresholds.max_future_staleness_ns < 0:
        raise ValueError("max_future_staleness_ns must be non-negative")


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required parity scan artifact missing: {path}")
    return pd.read_csv(path)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _nunique(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].dropna().nunique())


def _max_future_staleness(parity: pd.DataFrame) -> float:
    staleness = _future_staleness(parity)
    return float(staleness.max(skipna=True)) if not staleness.empty else np.nan


def _median_future_staleness(parity: pd.DataFrame) -> float:
    staleness = _future_staleness(parity)
    return float(staleness.median(skipna=True)) if not staleness.empty else np.nan


def _future_staleness(parity: pd.DataFrame) -> pd.Series:
    if parity.empty or "ts" not in parity.columns or "future_ts" not in parity.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(parity["ts"], errors="coerce") - pd.to_numeric(parity["future_ts"], errors="coerce")


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan
