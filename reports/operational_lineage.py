from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
)
from reports.runtime_guard import RUNTIME_LINEAGE_COLUMNS, SCALEUP_PROVENANCE_COLUMNS


LINEAGE_COLUMNS = (*SCALEUP_PROVENANCE_COLUMNS, *RUNTIME_LINEAGE_COLUMNS)
RUNTIME_SESSION_REQUIRED_ARTIFACTS = (
    "runtime_session_steps.csv",
    "runtime_session_summary.csv",
    "runtime_session_action_queue.csv",
    "runtime_session_config.json",
    "runtime_session_runbook.md",
)
CUTOVER_REQUIRED_ARTIFACTS = (
    "cutover_authorization.csv",
    "cutover_checks.csv",
    "cutover_summary.csv",
    "cutover_action_queue.csv",
    "cutover_config.json",
    "cutover_runbook.md",
)


def empty_runtime_session_lineage(*, required: bool = False) -> dict[str, Any]:
    state: dict[str, Any] = {
        "required": required,
        "provided": False,
        "manifest_current": not required,
        "manifest_run_type": "",
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_error": "manifest_missing" if required else "",
        "contract_consistent": not required,
        "contract_error": "",
        "non_authorizing": not required,
        "scaleup_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update({column: _field_default(column) for column in LINEAGE_COLUMNS})
    return state


def load_runtime_session_lineage(
    runtime_session_summary_path: str | Path,
    scaleup_config_path: str | Path,
) -> dict[str, Any]:
    summary_path = Path(runtime_session_summary_path).resolve()
    root = summary_path.parent
    config_path = root / "runtime_session_config.json"
    manifest_path = root / "manifest.json"
    state = empty_runtime_session_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in RUNTIME_SESSION_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in LINEAGE_COLUMNS
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="runtime_session_monitor",
            required_artifacts=RUNTIME_SESSION_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        dependencies = manifest_dependency_paths(manifest_path)
        state.update(
            {
                "manifest_current": bool(integrity.passed),
                "manifest_run_type": integrity.run_type,
                "manifest_sha256": file_sha256(manifest_path),
                "manifest_error": integrity.error,
                "dependency_paths": [str(path) for path in dependencies],
                "dependency_count": len(dependencies),
            }
        )

    errors = _runtime_session_contract_errors(
        summary=summary,
        config=config,
        manifest=manifest,
        lineage=state,
    )
    scaleup_manifest_path = _source_manifest_path(scaleup_config_path)
    current_scaleup_sha256 = (
        file_sha256(scaleup_manifest_path) if scaleup_manifest_path.is_file() else ""
    )
    scaleup_matches_current = bool(
        current_scaleup_sha256
        and state["scaleup_manifest_sha256"] == current_scaleup_sha256
        and state["runtime_telemetry_scaleup_manifest_sha256"] == current_scaleup_sha256
    )
    extra = _mapping(manifest.get("extra"))
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
        and _bool(state["scaleup_non_authorizing"])
    )
    lineage_current = bool(
        state["scaleup_provenance_gate_passed"]
        and state["runtime_telemetry_scaleup_provenance_carried"]
        and state["runtime_telemetry_scaleup_provenance_gate_passed"]
        and state["runtime_telemetry_scaleup_manifest_matches_current"]
        and state["runtime_telemetry_lineage_matches_current"]
    )
    if state["scaleup_research_family_bound"]:
        lineage_current = bool(
            lineage_current
            and state["scaleup_research_family_provenance_current"]
            and state["runtime_telemetry_research_family_bound"]
            and state["runtime_telemetry_research_family_provenance_current"]
            and state["runtime_telemetry_research_family_matches_current"]
            and state["scaleup_research_family_id"]
            and state["scaleup_research_family_registration_id"]
            and state["scaleup_research_family_manifest_sha256"]
        )

    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["scaleup_matches_current"] = scaleup_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and scaleup_matches_current
        and lineage_current
    )
    return state


def runtime_session_lineage_fields(lineage: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "runtime_lineage_required": _bool(lineage.get("required", False)),
        "runtime_lineage_provided": _bool(lineage.get("provided", False)),
        "runtime_session_manifest_current": _bool(lineage.get("manifest_current", False)),
        "runtime_session_manifest_run_type": _text(lineage.get("manifest_run_type", "")),
        "runtime_session_manifest_path": _text(lineage.get("manifest_path", "")),
        "runtime_session_manifest_sha256": _text(lineage.get("manifest_sha256", "")),
        "runtime_session_manifest_error": _text(lineage.get("manifest_error", "")),
        "runtime_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "runtime_lineage_contract_error": _text(lineage.get("contract_error", "")),
        "runtime_lineage_non_authorizing": _bool(lineage.get("non_authorizing", False)),
        "runtime_lineage_scaleup_matches_current": _bool(
            lineage.get("scaleup_matches_current", False)
        ),
        "runtime_lineage_gate_passed": _bool(lineage.get("gate_passed", False)),
        "runtime_lineage_dependency_count": int(lineage.get("dependency_count", 0)),
    }
    fields.update(
        {
            (column if column.startswith("runtime_") else f"runtime_{column}"): _normalize(
                lineage.get(column), column
            )
            for column in LINEAGE_COLUMNS
        }
    )
    return fields


def runtime_session_lineage_manifest_inputs(lineage: Mapping[str, Any]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["runtime_session_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["runtime_session_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["runtime_session_dependencies"] = dependencies
    return inputs


def empty_cutover_lineage(*, required: bool = False) -> dict[str, Any]:
    state: dict[str, Any] = {
        "required": required,
        "provided": False,
        "manifest_current": not required,
        "manifest_run_type": "",
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_error": "manifest_missing" if required else "",
        "contract_consistent": not required,
        "contract_error": "",
        "non_authorizing": not required,
        "runtime_lineage_gate_passed": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in runtime_session_lineage_fields(
                empty_runtime_session_lineage()
            )
        }
    )
    return state


def load_cutover_lineage(cutover_config_path: str | Path) -> dict[str, Any]:
    config_path = Path(cutover_config_path).resolve()
    root = config_path.parent
    summary_path = root / "cutover_summary.csv"
    manifest_path = root / "manifest.json"
    state = empty_cutover_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in CUTOVER_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    runtime_fields = runtime_session_lineage_fields(empty_runtime_session_lineage())
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in runtime_fields
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="cutover_gate",
            required_artifacts=CUTOVER_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        dependencies = manifest_dependency_paths(manifest_path)
        state.update(
            {
                "manifest_current": bool(integrity.passed),
                "manifest_run_type": integrity.run_type,
                "manifest_sha256": file_sha256(manifest_path),
                "manifest_error": integrity.error,
                "dependency_paths": [str(path) for path in dependencies],
                "dependency_count": len(dependencies),
            }
        )

    errors = _cutover_contract_errors(
        summary=summary,
        config=config,
        manifest=manifest,
        lineage=state,
        runtime_fields=tuple(runtime_fields),
    )
    extra = _mapping(manifest.get("extra"))
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )
    runtime_gate = _bool(state.get("runtime_lineage_gate_passed", False))
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["runtime_lineage_gate_passed"] = runtime_gate
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and runtime_gate
    )
    return state


def cutover_lineage_fields(lineage: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "cutover_lineage_required": _bool(lineage.get("required", False)),
        "cutover_lineage_provided": _bool(lineage.get("provided", False)),
        "cutover_manifest_current": _bool(lineage.get("manifest_current", False)),
        "cutover_manifest_run_type": _text(lineage.get("manifest_run_type", "")),
        "cutover_manifest_path": _text(lineage.get("manifest_path", "")),
        "cutover_manifest_sha256": _text(lineage.get("manifest_sha256", "")),
        "cutover_manifest_error": _text(lineage.get("manifest_error", "")),
        "cutover_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "cutover_lineage_contract_error": _text(lineage.get("contract_error", "")),
        "cutover_non_authorizing": _bool(lineage.get("non_authorizing", False)),
        "cutover_runtime_lineage_gate_passed": _bool(
            lineage.get("runtime_lineage_gate_passed", False)
        ),
        "cutover_lineage_gate_passed": _bool(lineage.get("gate_passed", False)),
        "cutover_lineage_dependency_count": int(lineage.get("dependency_count", 0)),
    }
    runtime_fields = runtime_session_lineage_fields(empty_runtime_session_lineage())
    fields.update(
        {
            f"cutover_{column}": _normalize(lineage.get(column), column)
            for column in runtime_fields
        }
    )
    return fields


def cutover_lineage_manifest_inputs(lineage: Mapping[str, Any]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["cutover_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["cutover_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["cutover_dependencies"] = dependencies
    return inputs


def _runtime_session_contract_errors(
    *,
    summary: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    lineage: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("runtime_session_summary_missing_or_empty")
    if not config:
        errors.append("runtime_session_config_missing_or_invalid")
    if not manifest:
        errors.append("runtime_session_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    scaleup_config = _mapping(config.get("scaleup_provenance"))
    telemetry_config = _mapping(config.get("runtime_telemetry_lineage"))
    for column in LINEAGE_COLUMNS:
        config_value = (
            scaleup_config.get(column)
            if column in SCALEUP_PROVENANCE_COLUMNS
            else telemetry_config.get(column)
        )
        expected = lineage[column]
        if not _same(config_value, expected, column):
            errors.append(f"runtime_session_config_{column}_mismatch")
        if not _same(extra.get(column), expected, column):
            errors.append(f"runtime_session_manifest_{column}_mismatch")
    for field in ("ready", "guard_action"):
        if not _same(config.get(field), row.get(field), field):
            errors.append(f"runtime_session_config_{field}_mismatch")
        if not _same(extra.get(field), row.get(field), field):
            errors.append(f"runtime_session_manifest_{field}_mismatch")
    return errors


def _cutover_contract_errors(
    *,
    summary: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    lineage: Mapping[str, Any],
    runtime_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("cutover_summary_missing_or_empty")
    if not config:
        errors.append("cutover_config_missing_or_invalid")
    if not manifest:
        errors.append("cutover_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_lineage = _mapping(config.get("runtime_lineage"))
    for column in runtime_fields:
        expected = lineage[column]
        if not _same(config_lineage.get(column), expected, column):
            errors.append(f"cutover_config_{column}_mismatch")
        if not _same(extra.get(column), expected, column):
            errors.append(f"cutover_manifest_{column}_mismatch")
    if not _same(config.get("ready"), row.get("ready"), "ready"):
        errors.append("cutover_config_ready_mismatch")
    if not _same(extra.get("ready"), row.get("ready"), "ready"):
        errors.append("cutover_manifest_ready_mismatch")
    return errors


def _source_manifest_path(config_path: str | Path) -> Path:
    candidate = Path(config_path).resolve()
    return candidate.parent / "manifest.json"


def _field_default(column: str) -> Any:
    if column.endswith("_count"):
        return 0
    if column == "guard_action" or column.endswith(
        ("_path", "_sha256", "_error", "_run_type", "_id")
    ):
        return ""
    return False


def _normalize(value: Any, column: str) -> Any:
    default = _field_default(column)
    if _missing(value):
        return default
    if isinstance(default, bool):
        return _bool(value)
    if isinstance(default, int):
        return _integer(value)
    return _text(value)


def _same(left: Any, right: Any, column: str) -> bool:
    return _normalize(left, column) == _normalize(right, column)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _existing_path(value: Any) -> Path | None:
    text = _text(value)
    if not text:
        return None
    path = Path(text)
    return path if path.exists() else None


def _existing_paths(value: Any) -> list[Path]:
    if not isinstance(value, (list, tuple)):
        return []
    return [path for item in value if (path := _existing_path(item)) is not None]


def _text(value: Any) -> str:
    if _missing(value):
        return ""
    return str(value).strip()


def _bool(value: Any) -> bool:
    if _missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready", "continue"}
    return bool(value)


def _integer(value: Any, *, fallback: int = 0) -> int:
    if _missing(value):
        return fallback
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
