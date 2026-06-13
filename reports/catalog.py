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
    "leadlag_edge_summary.csv",
    "imbalance_edge_summary.csv",
    "imbalance_edge_sweep_summary.csv",
    "imbalance_edge_selection_summary.csv",
    "imbalance_edge_walkforward_summary.csv",
    "imbalance_replay_walkforward_summary.csv",
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
    "scaleup_summary.csv",
    "market_profile_summary.csv",
    "market_portability_summary.csv",
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
    "broker_dispatch_ack_summary.csv",
    "halt_response_summary.csv",
    "halt_response_export_summary.csv",
    "halt_execution_summary.csv",
    "halt_incident_summary.csv",
    "resume_summary.csv",
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
    return ExperimentCatalog(catalog=catalog, summary=summary)


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
    write_experiment_manifest(
        out,
        run_type="experiment_catalog",
        parameters={"roots": [str(Path(root)) for root in roots]},
        inputs={"roots": [Path(root) for root in roots]},
    )
    return ExperimentCatalog(report.catalog, report.summary, out)


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
    row = {
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "run_type": manifest.get("run_type", ""),
        "generated_at_utc": manifest.get("generated_at_utc", ""),
        "git_branch": _nested(manifest, "git", "branch"),
        "git_commit": _nested(manifest, "git", "commit"),
        "git_dirty": _nested(manifest, "git", "dirty"),
        "artifact_count": len(manifest.get("artifacts", []) or []),
        "input_count": len(manifest.get("inputs", {}) or {}),
        "summary_file": summary_file,
        "summary_status_column": status_column,
        "summary_status": status,
        "parameters_json": json.dumps(manifest.get("parameters", {}), sort_keys=True),
        "inputs_json": json.dumps(manifest.get("inputs", {}), sort_keys=True),
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
            }
        ]
    )


def _nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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


def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan
