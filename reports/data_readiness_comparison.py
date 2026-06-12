from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class DataReadinessComparisonThresholds:
    min_datasets: int = 1
    min_ready_datasets: int | None = None
    min_ready_rate: float = 1.0
    max_total_failed_checks: int = 0


@dataclass(frozen=True)
class DataReadinessComparisonReport:
    dataset_runs: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def accepted(self) -> bool:
        return bool(self.summary.iloc[0]["accepted"]) if not self.summary.empty else False


def compare_data_readiness(
    datasets: pd.DataFrame,
    *,
    thresholds: DataReadinessComparisonThresholds | None = None,
) -> DataReadinessComparisonReport:
    thresholds = thresholds or DataReadinessComparisonThresholds()
    _validate_thresholds(thresholds)
    _require(datasets, ["dataset", "ready", "failed_checks"], "data_readiness_runs")
    runs = datasets.copy().reset_index(drop=True)
    runs["ready"] = runs["ready"].map(_to_bool)
    for column in ("components", "required_components", "provided_components", "ready_components", "failed_checks"):
        if column not in runs.columns:
            runs[column] = 0.0
        runs[column] = pd.to_numeric(runs[column], errors="coerce")
    summary = _summary(runs)
    checks = _checks(summary.iloc[0], thresholds)
    accepted = bool(checks["passed"].all()) if not checks.empty else False
    summary["accepted"] = accepted
    summary["recommendation"] = "feed_walkforward_research" if accepted else "collect_or_fix_data"
    return DataReadinessComparisonReport(dataset_runs=runs, checks=checks, summary=summary)


def write_data_readiness_comparison(
    readiness_dirs: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    thresholds: DataReadinessComparisonThresholds | None = None,
) -> DataReadinessComparisonReport:
    if not readiness_dirs:
        raise ValueError("at least one data readiness directory is required")
    if labels is not None and len(labels) != len(readiness_dirs):
        raise ValueError("labels must match readiness directories")
    thresholds = thresholds or DataReadinessComparisonThresholds()
    runs = _read_readiness_runs(readiness_dirs, labels=labels)
    report = compare_data_readiness(runs, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.dataset_runs.to_csv(out / "data_readiness_runs.csv", index=False)
    report.checks.to_csv(out / "data_readiness_comparison_checks.csv", index=False)
    report.summary.to_csv(out / "data_readiness_comparison_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="data_readiness_comparison",
        parameters={"labels": labels, "thresholds": asdict(thresholds)},
        inputs={"readiness": readiness_dirs},
    )
    return DataReadinessComparisonReport(report.dataset_runs, report.checks, report.summary, out)


def _read_readiness_runs(readiness_dirs: list[str | Path], *, labels: list[str] | None) -> pd.DataFrame:
    rows = []
    for idx, raw_path in enumerate(readiness_dirs):
        path = Path(raw_path)
        summary_path = path / "data_readiness_summary.csv" if path.is_dir() else path
        if not summary_path.exists():
            raise FileNotFoundError(f"data_readiness_summary.csv not found for {path}")
        summary = pd.read_csv(summary_path)
        if summary.empty:
            raise ValueError(f"data readiness summary is empty: {summary_path}")
        row = summary.iloc[0]
        label = labels[idx] if labels is not None else path.stem
        rows.append(
            {
                "dataset": label,
                "dataset_path": str(path),
                "ready": _to_bool(row.get("ready", False)),
                "components": _number(row, "components", fallback=0.0),
                "required_components": _number(row, "required_components", fallback=0.0),
                "provided_components": _number(row, "provided_components", fallback=0.0),
                "ready_components": _number(row, "ready_components", fallback=0.0),
                "failed_checks": _number(row, "failed_checks", fallback=0.0),
                "recommendation": str(row.get("recommendation", "")),
            }
        )
    return pd.DataFrame(rows)


def _summary(runs: pd.DataFrame) -> pd.DataFrame:
    dataset_count = int(len(runs))
    ready_datasets = int(runs["ready"].sum()) if dataset_count else 0
    failed_datasets = dataset_count - ready_datasets
    return pd.DataFrame(
        [
            {
                "dataset_count": dataset_count,
                "ready_datasets": ready_datasets,
                "failed_datasets": failed_datasets,
                "ready_rate": ready_datasets / dataset_count if dataset_count else 0.0,
                "total_failed_checks": int(pd.to_numeric(runs["failed_checks"], errors="coerce").sum(skipna=True)),
                "median_ready_components": float(pd.to_numeric(runs["ready_components"], errors="coerce").median(skipna=True))
                if dataset_count
                else np.nan,
                "min_ready_components": float(pd.to_numeric(runs["ready_components"], errors="coerce").min(skipna=True))
                if dataset_count
                else np.nan,
                "recommendation": "",
            }
        ]
    )


def _checks(row: pd.Series, thresholds: DataReadinessComparisonThresholds) -> pd.DataFrame:
    min_ready = thresholds.min_ready_datasets if thresholds.min_ready_datasets is not None else thresholds.min_datasets
    return pd.DataFrame(
        [
            _threshold_check("dataset_count", row["dataset_count"], ">=", thresholds.min_datasets),
            _threshold_check("ready_datasets", row["ready_datasets"], ">=", min_ready),
            _threshold_check("ready_rate", row["ready_rate"], ">=", thresholds.min_ready_rate),
            _threshold_check(
                "total_failed_checks",
                row["total_failed_checks"],
                "<=",
                thresholds.max_total_failed_checks,
            ),
        ]
    )


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


def _validate_thresholds(thresholds: DataReadinessComparisonThresholds) -> None:
    if thresholds.min_datasets <= 0:
        raise ValueError("min_datasets must be positive")
    if thresholds.min_ready_datasets is not None and thresholds.min_ready_datasets <= 0:
        raise ValueError("min_ready_datasets must be positive")
    if not 0 <= thresholds.min_ready_rate <= 1:
        raise ValueError("min_ready_rate must be between 0 and 1")
    if thresholds.max_total_failed_checks < 0:
        raise ValueError("max_total_failed_checks must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed", "accepted"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)
