from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import MANIFEST_NAME, write_experiment_manifest


SUMMARY_FILES = [
    "parity_edge_summary.csv",
    "parity_order_summary.csv",
    "parity_launch_pipeline_summary.csv",
    "leadlag_edge_summary.csv",
    "leadlag_replay_walkforward_summary.csv",
    "leadlag_order_summary.csv",
    "leadlag_launch_pipeline_summary.csv",
    "imbalance_edge_summary.csv",
    "imbalance_edge_sweep_summary.csv",
    "imbalance_edge_selection_summary.csv",
    "imbalance_edge_walkforward_summary.csv",
    "imbalance_replay_walkforward_summary.csv",
    "imbalance_order_summary.csv",
    "imbalance_launch_pipeline_summary.csv",
    "imbalance_pipeline_summary.csv",
    "surface_mm_pipeline_summary.csv",
    "surface_mm_launch_pipeline_summary.csv",
    "settlement_convergence_walkforward_summary.csv",
    "settlement_launch_pipeline_summary.csv",
    "settlement_convergence_summary.csv",
    "settlement_order_summary.csv",
    "proof_summary.csv",
    "proof_refresh_summary.csv",
    "strategy_evidence_summary.csv",
    "strategy_scorecard_summary.csv",
    "scaleup_summary.csv",
    "market_profile_summary.csv",
    "market_portability_summary.csv",
    "route_readiness_summary.csv",
    "instrument_metadata_summary.csv",
    "vendor_market_data_batch_summary.csv",
    "vendor_market_data_pipeline_summary.csv",
    "data_readiness_summary.csv",
    "data_readiness_comparison_summary.csv",
    "diagnostic_summary.csv",
    "mapped_data_summary.csv",
    "stress_summary.csv",
    "selection_summary.csv",
    "promotion_summary.csv",
    "launch_summary.csv",
    "broker_order_summary.csv",
    "broker_upload_summary.csv",
    "broker_readiness_summary.csv",
    "broker_vendor_data_readiness_summary.csv",
    "mapped_order_summary.csv",
    "order_mapping_draft_summary.csv",
    "reconciliation_summary.csv",
    "shadow_session_summary.csv",
    "shadow_session_comparison_summary.csv",
    "runtime_telemetry_summary.csv",
    "runtime_guard_summary.csv",
    "runtime_session_summary.csv",
    "cutover_summary.csv",
    "route_enable_summary.csv",
    "broker_dispatch_summary.csv",
    "broker_dispatch_send_summary.csv",
    "broker_dispatch_ack_summary.csv",
    "broker_dispatch_roundtrip_summary.csv",
    "halt_response_summary.csv",
    "halt_response_export_summary.csv",
    "halt_execution_summary.csv",
    "halt_incident_summary.csv",
    "resume_summary.csv",
    "surface_quality_summary.csv",
    "quote_risk_summary.csv",
    "quote_lifecycle_summary.csv",
    "order_exposure_summary.csv",
    "staged_order_summary.csv",
    "fill_model_summary.csv",
    "fill_model_drift_summary.csv",
    "calibrated_replay_summary.csv",
    "adapter_schema_summary.csv",
    "vendor_intake_summary.csv",
    "surface_quote_summary.csv",
    "sweep_summary.csv",
    "summary.csv",
    "calibration_summary.csv",
]

STATUS_COLUMNS = [
    "passed",
    "all_passed",
    "ready",
    "accepted",
    "all_scenarios_passed",
    "has_selection",
    "selection_passed",
    "all_required_present",
]


@dataclass(frozen=True)
class ExperimentCatalog:
    catalog: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def run_count(self) -> int:
        return int(len(self.catalog))


def catalog_experiment_runs(roots: list[str | Path]) -> ExperimentCatalog:
    if not roots:
        raise ValueError("at least one experiment root is required")
    manifests = _manifest_paths(roots)
    rows = [_catalog_row(path) for path in manifests]
    catalog = pd.DataFrame(rows)
    summary = _catalog_summary(catalog)
    action_queue = _catalog_action_queue(catalog)
    return ExperimentCatalog(catalog=catalog, summary=summary, action_queue=action_queue)


def write_experiment_catalog(
    roots: list[str | Path],
    *,
    output_dir: str | Path,
) -> ExperimentCatalog:
    report = catalog_experiment_runs(roots)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.catalog.to_csv(out / "experiment_catalog.csv", index=False)
    report.summary.to_csv(out / "experiment_catalog_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _catalog_action_queue(report.catalog)
    action_queue.to_csv(out / "experiment_catalog_action_queue.csv", index=False)
    (out / "experiment_catalog_runbook.md").write_text(
        _catalog_runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="experiment_catalog",
        parameters={"roots": [str(Path(root)) for root in roots]},
        inputs={"roots": [Path(root) for root in roots]},
    )
    return ExperimentCatalog(report.catalog, report.summary, out, action_queue)


def _manifest_paths(roots: list[str | Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        path = Path(root)
        if path.is_file():
            candidates = [path] if path.name == MANIFEST_NAME else []
        elif path.exists():
            candidates = sorted(path.rglob(MANIFEST_NAME))
        else:
            raise FileNotFoundError(f"experiment root not found: {path}")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return sorted(paths)


def _catalog_row(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_dir = manifest_path.parent
    summary_file, summary_row = _summary_row(run_dir)
    status_column, status = _summary_status(summary_row)
    inputs = manifest.get("inputs", {}) or {}
    input_stats = _input_stats(inputs)
    row = {
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "run_type": manifest.get("run_type", ""),
        "generated_at_utc": manifest.get("generated_at_utc", ""),
        "git_branch": _nested(manifest, "git", "branch"),
        "git_commit": _nested(manifest, "git", "commit"),
        "git_dirty": _nested(manifest, "git", "dirty"),
        "artifact_count": len(manifest.get("artifacts", []) or []),
        "input_count": len(inputs),
        **input_stats,
        "summary_file": summary_file,
        "summary_status_column": status_column,
        "summary_status": status,
        "parameters_json": json.dumps(manifest.get("parameters", {}), sort_keys=True),
        "inputs_json": json.dumps(inputs, sort_keys=True),
    }
    for column, value in summary_row.items():
        row[f"summary_{column}"] = value
    return row


def _summary_row(run_dir: Path) -> tuple[str, dict[str, Any]]:
    for name in SUMMARY_FILES:
        path = run_dir / name
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return name, {}
        if frame.empty:
            return name, {}
        return name, _jsonable_row(frame.iloc[0].to_dict())
    return "", {}


def _summary_status(row: dict[str, Any]) -> tuple[str, bool | None]:
    for column in STATUS_COLUMNS:
        if column in row:
            return column, _to_bool(row[column])
    if "failed_checks" in row:
        return "failed_checks", _numeric(row["failed_checks"]) == 0
    if "failed_runs" in row:
        return "failed_runs", _numeric(row["failed_runs"]) == 0
    if "failed_rows" in row:
        return "failed_rows", _numeric(row["failed_rows"]) == 0
    return "", None


def _catalog_summary(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty:
        return pd.DataFrame(
            [
                {
                    "run_count": 0,
                    "run_type_count": 0,
                    "status_true_runs": 0,
                    "status_false_runs": 0,
                    "missing_summary_runs": 0,
                    "dirty_runs": 0,
                    "git_commit_count": 0,
                    "input_file_count": 0,
                    "input_directory_count": 0,
                    "input_other_count": 0,
                    "input_hashed_count": 0,
                    "input_unfingerprinted_count": 0,
                    "runs_with_directory_inputs": 0,
                    "runs_with_unfingerprinted_inputs": 0,
                }
            ]
        )
    status = catalog["summary_status"]
    return pd.DataFrame(
        [
            {
                "run_count": int(len(catalog)),
                "run_type_count": int(catalog["run_type"].nunique()),
                "status_true_runs": int(status.map(lambda value: value is True).sum()),
                "status_false_runs": int(status.map(lambda value: value is False).sum()),
                "missing_summary_runs": int((catalog["summary_file"].astype(str) == "").sum()),
                "dirty_runs": int(catalog["git_dirty"].map(_to_bool).sum()),
                "git_commit_count": int(catalog["git_commit"].dropna().nunique()),
                "input_file_count": int(catalog["input_file_count"].sum()),
                "input_directory_count": int(catalog["input_directory_count"].sum()),
                "input_other_count": int(catalog["input_other_count"].sum()),
                "input_hashed_count": int(catalog["input_hashed_count"].sum()),
                "input_unfingerprinted_count": int(catalog["input_unfingerprinted_count"].sum()),
                "runs_with_directory_inputs": int((catalog["input_directory_count"] > 0).sum()),
                "runs_with_unfingerprinted_inputs": int((catalog["input_unfingerprinted_count"] > 0).sum()),
            }
        ]
    )


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "run_type",
    "run_dir",
    "strategy",
    "market",
    "profile",
    "summary_status",
    "next_gate",
    "next_gate_help_command",
    "recommendation",
    "generated_at_utc",
]

EXCLUDED_SIDECAR_ACTION_QUEUES = {"experiment_catalog_action_queue.csv"}


def _catalog_action_queue(catalog: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not catalog.empty:
        for _, row in catalog.iterrows():
            item = row.to_dict()
            sidecar_rows = _sidecar_action_rows(item)
            if sidecar_rows:
                rows.extend(sidecar_rows)
                continue
            next_gate = _first_text(item, "summary_next_gate", "summary_best_next_gate")
            help_command = _first_text(
                item,
                "summary_next_gate_help_command",
                "summary_best_next_gate_help_command",
            )
            if not next_gate and not help_command:
                continue
            rows.append(
                {
                    "queue_status": _queue_status(item.get("summary_status")),
                    "run_type": _text(item.get("run_type")),
                    "run_dir": _text(item.get("run_dir")),
                    "strategy": _first_text(
                        item,
                        "summary_strategy",
                        "summary_best_strategy",
                        "summary_runtime_strategy",
                    ),
                    "market": _first_text(
                        item,
                        "summary_market",
                        "summary_best_market",
                        "summary_runtime_market",
                    ),
                    "profile": _first_text(
                        item,
                        "summary_evidence_profile",
                        "summary_profile",
                        "summary_best_profile",
                    ),
                    "summary_status": item.get("summary_status"),
                    "next_gate": next_gate,
                    "next_gate_help_command": help_command,
                    "recommendation": _text(item.get("summary_recommendation")),
                    "generated_at_utc": _text(item.get("generated_at_utc")),
                    "_source_priority": 0,
                }
            )
    if rows:
        ordered = sorted(
            rows,
            key=lambda row: (
                _queue_rank(row["queue_status"]),
                row["run_type"],
                row["run_dir"],
                _int_metric(row.get("_source_priority")),
                row["next_gate"],
            ),
        )
        for priority, row in enumerate(ordered, start=1):
            row["priority"] = priority
            row.pop("_source_priority", None)
        rows = ordered
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _sidecar_action_rows(catalog_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _sidecar_action_queue_paths(catalog_row.get("run_dir")):
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if frame.empty:
            continue
        for _, action in frame.iterrows():
            item = action.to_dict()
            next_gate = _text(item.get("next_gate"))
            help_command = _text(item.get("next_gate_help_command"))
            if not next_gate and not help_command:
                continue
            rows.append(
                {
                    "queue_status": _first_text(item, "queue_status")
                    or _queue_status(catalog_row.get("summary_status")),
                    "run_type": _text(catalog_row.get("run_type")),
                    "run_dir": _text(catalog_row.get("run_dir")),
                    "strategy": _first_text_from_sources(
                        item,
                        catalog_row,
                        "strategy",
                        "summary_strategy",
                        "summary_best_strategy",
                        "summary_runtime_strategy",
                    ),
                    "market": _first_text_from_sources(
                        item,
                        catalog_row,
                        "market",
                        "summary_market",
                        "summary_best_market",
                        "summary_runtime_market",
                    ),
                    "profile": _first_text_from_sources(
                        item,
                        catalog_row,
                        "profile",
                        "summary_evidence_profile",
                        "summary_profile",
                        "summary_best_profile",
                    ),
                    "summary_status": catalog_row.get("summary_status"),
                    "next_gate": next_gate,
                    "next_gate_help_command": help_command,
                    "recommendation": _action_recommendation(item, path),
                    "generated_at_utc": _text(catalog_row.get("generated_at_utc")),
                    "_source_priority": _int_metric(item.get("priority")),
                }
            )
    return rows


def _sidecar_action_queue_paths(run_dir: Any) -> list[Path]:
    run_dir_text = _text(run_dir)
    if not run_dir_text:
        return []
    path = Path(run_dir_text)
    if not path.exists() or not path.is_dir():
        return []
    return sorted(
        candidate
        for candidate in path.glob("*_action_queue.csv")
        if candidate.name not in EXCLUDED_SIDECAR_ACTION_QUEUES
    )


def _first_text_from_sources(primary: dict[str, Any], fallback: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = _text(primary.get(column))
        if value:
            return value
        value = _text(fallback.get(column))
        if value:
            return value
    return ""


def _action_recommendation(action: dict[str, Any], path: Path) -> str:
    recommendation = _first_text(action, "recommendation", "reason")
    if recommendation:
        return recommendation
    check = _text(action.get("check"))
    component = _text(action.get("component"))
    if check and component:
        return f"{path.name}:{component}:{check}"
    if check:
        return f"{path.name}:{check}"
    if component:
        return f"{path.name}:{component}"
    return path.name


def _queue_status(value: Any) -> str:
    if value is True:
        return "ready"
    if value is False:
        return "blocked"
    return "unknown"


def _queue_rank(status: str) -> int:
    return {"ready": 0, "blocked": 1, "unknown": 2}.get(status, 3)


def _catalog_runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready = (
        _int_metric(summary_row.get("status_false_runs")) == 0
        and _int_metric(summary_row.get("missing_summary_runs")) == 0
    )
    lines = [
        "# Experiment Catalog Runbook",
        "",
        "## Readiness",
        "",
        f"- Ready: {'yes' if ready else 'no'}",
        f"- Runs: {_int_metric(summary_row.get('run_count'))}",
        f"- Run types: {_int_metric(summary_row.get('run_type_count'))}",
        f"- Status true runs: {_int_metric(summary_row.get('status_true_runs'))}",
        f"- Status false runs: {_int_metric(summary_row.get('status_false_runs'))}",
        f"- Missing summary runs: {_int_metric(summary_row.get('missing_summary_runs'))}",
        f"- Dirty runs: {_int_metric(summary_row.get('dirty_runs'))}",
        "",
        "## Input Provenance",
        "",
        f"- Input files: {_int_metric(summary_row.get('input_file_count'))}",
        f"- Input directories: {_int_metric(summary_row.get('input_directory_count'))}",
        f"- Input hashes: {_int_metric(summary_row.get('input_hashed_count'))}",
        f"- Unfingerprinted inputs: {_int_metric(summary_row.get('input_unfingerprinted_count'))}",
        f"- Runs with directory inputs: {_int_metric(summary_row.get('runs_with_directory_inputs'))}",
        f"- Runs with unfingerprinted inputs: {_int_metric(summary_row.get('runs_with_unfingerprinted_inputs'))}",
        "",
        "## Action Queue",
        "",
        f"- Queue rows: {len(action_queue)}",
        "",
        _action_queue_markdown_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_markdown_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    columns = [
        "priority",
        "queue_status",
        "run_type",
        "strategy",
        "market",
        "profile",
        "next_gate",
        "next_gate_help_command",
        "recommendation",
    ]
    headers = [
        "Priority",
        "Status",
        "Run Type",
        "Strategy",
        "Market",
        "Profile",
        "Next Gate",
        "Help Command",
        "Recommendation",
    ]
    rows = [
        [_format_markdown_cell(row.get(column)) for column in columns]
        for _, row in action_queue.iterrows()
    ]
    return _markdown_table(headers, rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(_escape_markdown_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape_markdown_cell(value) for value in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def _format_markdown_cell(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if text.startswith("python -m ") or "--" in text:
        return f"`{text}`"
    return text


def _escape_markdown_cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


def _int_metric(value: Any) -> int:
    numeric = _numeric(value)
    if pd.isna(numeric):
        return 0
    return int(numeric)


def _first_text(row: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = _text(row.get(column))
        if value:
            return value
    return ""


def _nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _input_stats(inputs: Any) -> dict[str, int]:
    stats = {
        "input_file_count": 0,
        "input_directory_count": 0,
        "input_other_count": 0,
        "input_hashed_count": 0,
        "input_unfingerprinted_count": 0,
    }
    _accumulate_input_stats(inputs, stats)
    return stats


def _accumulate_input_stats(value: Any, stats: dict[str, int]) -> None:
    if isinstance(value, dict):
        kind = value.get("kind")
        if isinstance(kind, str) and "path" in value:
            normalized = kind.strip().lower()
            if normalized == "file":
                stats["input_file_count"] += 1
            elif normalized == "directory":
                stats["input_directory_count"] += 1
            else:
                stats["input_other_count"] += 1
            if value.get("sha256") or value.get("tree_sha256"):
                stats["input_hashed_count"] += 1
            return
        for item in value.values():
            _accumulate_input_stats(item, stats)
        return
    if isinstance(value, list):
        for item in value:
            _accumulate_input_stats(item, stats)
        return
    if value is not None:
        stats["input_unfingerprinted_count"] += 1


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan
