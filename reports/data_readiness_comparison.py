from __future__ import annotations

import json
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
    min_unique_source_files: int | None = None
    min_source_file_fingerprint_coverage: float | None = None
    min_mapping_coverage: float | None = None


@dataclass(frozen=True)
class DataReadinessComparisonReport:
    dataset_runs: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

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
    _coalesce_column(runs, "source_file_sha256", "vendor_intake_source_file_sha256", default="")
    _coalesce_column(runs, "source_header_sha256", "vendor_intake_source_header_sha256", default="")
    _coalesce_column(runs, "mapping_draft_sha256", "vendor_intake_mapping_draft_sha256", default="")
    _coalesce_column(runs, "mapping_coverage", "vendor_intake_mapping_coverage", default=np.nan)
    for column in ("source_file_sha256", "source_header_sha256", "mapping_draft_sha256"):
        if column not in runs.columns:
            runs[column] = ""
        runs[column] = runs[column].fillna("").astype(str).str.strip()
    if "mapping_coverage" not in runs.columns:
        runs["mapping_coverage"] = np.nan
    runs["mapping_coverage"] = pd.to_numeric(runs["mapping_coverage"], errors="coerce")
    summary = _summary(runs)
    checks = _checks(summary.iloc[0], thresholds)
    action_queue = _action_queue(checks)
    accepted = bool(checks["passed"].all()) if not checks.empty else False
    summary["accepted"] = accepted
    summary["recommendation"] = "feed_walkforward_research" if accepted else "collect_or_fix_data"
    summary["ready_action_count"] = 0
    summary["blocked_action_count"] = int(len(action_queue))
    summary["next_gate"] = _primary_next_gate(action_queue)
    summary["next_gate_help_command"] = summary["next_gate"].map(_next_gate_help_command)
    return DataReadinessComparisonReport(
        dataset_runs=runs,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
    )


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
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "data_readiness_comparison_action_queue.csv", index=False)
    (out / "data_readiness_comparison_config.json").write_text(
        json.dumps(
            _config(report.summary.iloc[0], report.dataset_runs, report.checks, action_queue, thresholds),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "data_readiness_comparison_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.dataset_runs, report.checks, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="data_readiness_comparison",
        parameters={"labels": labels, "thresholds": asdict(thresholds)},
        inputs={"readiness": readiness_dirs},
    )
    return DataReadinessComparisonReport(report.dataset_runs, report.checks, report.summary, out, action_queue)


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
                "source_file_sha256": _text(
                    row,
                    "vendor_intake_source_file_sha256",
                    fallback=_text(row, "source_file_sha256"),
                ),
                "source_header_sha256": _text(
                    row,
                    "vendor_intake_source_header_sha256",
                    fallback=_text(row, "source_header_sha256"),
                ),
                "mapping_draft_sha256": _text(
                    row,
                    "vendor_intake_mapping_draft_sha256",
                    fallback=_text(row, "mapping_draft_sha256"),
                ),
                "mapping_coverage": _number(
                    row,
                    "vendor_intake_mapping_coverage",
                    fallback=_number(row, "mapping_coverage"),
                ),
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
                "unique_source_files": _unique_text_count(runs, "source_file_sha256"),
                "source_file_fingerprint_coverage": _text_coverage(runs, "source_file_sha256"),
                "unique_header_fingerprints": _unique_text_count(runs, "source_header_sha256"),
                "unique_mapping_drafts": _unique_text_count(runs, "mapping_draft_sha256"),
                "min_mapping_coverage": _min_number(runs, "mapping_coverage"),
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
    checks = [
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
    if thresholds.min_unique_source_files is not None:
        checks.append(
            _threshold_check(
                "unique_source_files",
                row["unique_source_files"],
                ">=",
                thresholds.min_unique_source_files,
            )
        )
    if thresholds.min_source_file_fingerprint_coverage is not None:
        checks.append(
            _threshold_check(
                "source_file_fingerprint_coverage",
                row["source_file_fingerprint_coverage"],
                ">=",
                thresholds.min_source_file_fingerprint_coverage,
            )
        )
    if thresholds.min_mapping_coverage is not None:
        checks.append(
            _threshold_check(
                "min_mapping_coverage",
                row["min_mapping_coverage"],
                ">=",
                thresholds.min_mapping_coverage,
            )
        )
    return pd.DataFrame(checks)


def _config(
    summary_row: pd.Series,
    dataset_runs: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    thresholds: DataReadinessComparisonThresholds,
) -> dict[str, object]:
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    failed_checks = (
        checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
        if not checks.empty and "passed" in checks.columns
        else []
    )
    return {
        "schema_version": 1,
        "accepted": _to_bool(summary_row.get("accepted", False)),
        "recommendation": _value_text(summary_row.get("recommendation")),
        "thresholds": asdict(thresholds),
        "summary": _jsonable_record(summary_row.to_dict()),
        "dataset_count": int(_value_number(summary_row.get("dataset_count"))),
        "ready_datasets": int(_value_number(summary_row.get("ready_datasets"))),
        "failed_datasets": int(_value_number(summary_row.get("failed_datasets"))),
        "failed_checks": failed_checks,
        "datasets": _records(dataset_runs),
        "ready_action_count": int(len(ready_actions)),
        "blocked_action_count": int(len(blocked_actions)),
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _value_text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _records(action_queue),
        "ready_actions": _records(ready_actions),
        "blocked_actions": _records(blocked_actions),
    }


def _first_action_record(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return _jsonable_record(frame.iloc[0].to_dict())


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [_jsonable_record(row) for row in frame.to_dict(orient="records")]


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Path):
            record[str(key)] = str(value)
            continue
        try:
            if pd.isna(value):
                record[str(key)] = None
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(value, np.generic):
            record[str(key)] = value.item()
            continue
        record[str(key)] = value
    return record


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _value_text(action_queue.iloc[0].get(column))


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not checks.empty and "passed" in checks.columns:
        failed = checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)
        for priority, row in enumerate(failed.to_dict(orient="records"), start=1):
            check_name = _value_text(row.get("check"))
            next_gate = _next_gate_for_check(check_name)
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "blocked",
                    "check": check_name,
                    "next_gate": next_gate,
                    "next_gate_help_command": _next_gate_help_command(next_gate),
                    "actual": _value_text(row.get("value")),
                    "operator": _value_text(row.get("operator")),
                    "expected": _value_text(row.get("threshold")),
                    "reason": _value_text(row.get("reason")),
                    "recommendation": _action_recommendation(check_name),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "check",
            "next_gate",
            "next_gate_help_command",
            "actual",
            "operator",
            "expected",
            "reason",
            "recommendation",
        ],
    )


def _next_gate_for_check(check_name: str) -> str:
    if check_name in {
        "dataset_count",
        "unique_source_files",
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
    }:
        return "pipeline-vendor-market-data-batch"
    if check_name in {"ready_datasets", "ready_rate", "total_failed_checks"}:
        return "review-data-readiness"
    return "compare-data-readiness"


def _next_gate_help_command(next_gate: str) -> str:
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _primary_next_gate(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return ""
    return _value_text(action_queue.iloc[0].get("next_gate"))


def _action_recommendation(check_name: str) -> str:
    if check_name == "dataset_count":
        return "collect_additional_vendor_data_days"
    if check_name in {"ready_datasets", "ready_rate", "total_failed_checks"}:
        return "fix_failed_data_readiness_runs"
    if check_name == "unique_source_files":
        return "rerun_batch_with_distinct_raw_source_files"
    if check_name == "source_file_fingerprint_coverage":
        return "rerun_batch_with_source_file_fingerprints"
    if check_name == "min_mapping_coverage":
        return "improve_vendor_mapping_coverage"
    return "review_data_readiness_comparison_gap"


def _runbook_markdown(
    summary_row: pd.Series,
    dataset_runs: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    accepted_label = "yes" if _to_bool(summary_row.get("accepted", False)) else "no"
    lines = [
        "# Data Readiness Comparison Runbook",
        "",
        f"- Accepted: {accepted_label}",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Dataset count: {int(_value_number(summary_row.get('dataset_count')))}",
        f"- Ready datasets: {int(_value_number(summary_row.get('ready_datasets')))}",
        f"- Failed datasets: {int(_value_number(summary_row.get('failed_datasets')))}",
        f"- Blocked actions: {int(_value_number(summary_row.get('blocked_action_count')))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
        "## Datasets",
        "",
        _dataset_table(dataset_runs),
        "",
        "## Failed Checks",
        "",
        _failed_checks_table(checks),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Check", "Next gate", "Help", "Recommendation"],
        [
            [
                str(int(_value_number(row.get("priority")))),
                _value_text(row.get("check")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _value_text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _dataset_table(dataset_runs: pd.DataFrame) -> str:
    if dataset_runs.empty:
        return "_None_"
    return _markdown_table(
        ["Dataset", "Ready", "Failed checks", "Source hash", "Mapping coverage", "Recommendation"],
        [
            [
                _value_text(row.get("dataset")),
                "yes" if _to_bool(row.get("ready")) else "no",
                str(int(_value_number(row.get("failed_checks")))),
                _value_text(row.get("source_file_sha256")),
                _format_number(row.get("mapping_coverage")),
                _value_text(row.get("recommendation")),
            ]
            for row in dataset_runs.to_dict(orient="records")
        ],
    )


def _failed_checks_table(checks: pd.DataFrame) -> str:
    if checks.empty or "passed" not in checks.columns:
        return "_None_"
    failed = checks.loc[~checks["passed"].astype(bool)]
    if failed.empty:
        return "_None_"
    return _markdown_table(
        ["Check", "Actual", "Op", "Expected", "Reason"],
        [
            [
                _value_text(row.get("check")),
                _value_text(row.get("value")),
                _value_text(row.get("operator")),
                _value_text(row.get("threshold")),
                _value_text(row.get("reason")),
            ]
            for row in failed.to_dict(orient="records")
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _code(value: object) -> str:
    text = _value_text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: object) -> str:
    return _value_text(value).replace("|", "\\|").replace("\n", " ")


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
    if thresholds.min_unique_source_files is not None and thresholds.min_unique_source_files <= 0:
        raise ValueError("min_unique_source_files must be positive")
    if (
        thresholds.min_source_file_fingerprint_coverage is not None
        and not 0 <= thresholds.min_source_file_fingerprint_coverage <= 1
    ):
        raise ValueError("min_source_file_fingerprint_coverage must be between 0 and 1")
    if thresholds.min_mapping_coverage is not None and not 0 <= thresholds.min_mapping_coverage <= 1:
        raise ValueError("min_mapping_coverage must be between 0 and 1")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _coalesce_column(frame: pd.DataFrame, column: str, fallback_column: str, *, default: object) -> None:
    if column not in frame.columns:
        frame[column] = frame[fallback_column] if fallback_column in frame.columns else default
        return
    if fallback_column not in frame.columns:
        return
    current = frame[column]
    if pd.api.types.is_numeric_dtype(current):
        missing = current.isna()
    else:
        missing = current.isna() | (current.astype(str).str.strip() == "")
    frame.loc[missing, column] = frame.loc[missing, fallback_column]


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _text(row: pd.Series, column: str, fallback: str = "") -> str:
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return str(value).strip()


def _value_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _value_number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    try:
        if pd.isna(number):
            return 0.0
    except (TypeError, ValueError):
        pass
    return number


def _format_number(value: object) -> str:
    text = _value_text(value)
    if not text:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return text
    if pd.isna(number):
        return ""
    return f"{number:.6g}"


def _unique_text_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return int(values.nunique())


def _text_coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = frame[column].fillna("").astype(str).str.strip()
    return float((values != "").sum() / len(values)) if len(values) else 0.0


def _min_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.min(skipna=True)) if values.notna().any() else np.nan


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
