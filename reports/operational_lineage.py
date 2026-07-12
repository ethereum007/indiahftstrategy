from __future__ import annotations

import hashlib
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
ROUTE_ENABLE_REQUIRED_ARTIFACTS = (
    "route_enable_packet.csv",
    "route_enable_checks.csv",
    "route_enable_summary.csv",
    "route_enable_action_queue.csv",
    "route_enable_config.json",
    "route_enable_runbook.md",
)
BROKER_DISPATCH_REQUIRED_ARTIFACTS = (
    "broker_dispatch_orders.csv",
    "broker_dispatch_checks.csv",
    "broker_dispatch_summary.csv",
    "broker_dispatch_action_queue.csv",
    "broker_dispatch_config.json",
    "broker_dispatch_runbook.md",
)
BROKER_DISPATCH_SEND_REQUIRED_ARTIFACTS = (
    "broker_dispatch_send_requests.csv",
    "broker_dispatch_expected_acks.csv",
    "broker_dispatch_send_checks.csv",
    "broker_dispatch_send_summary.csv",
    "broker_dispatch_send_action_queue.csv",
    "broker_dispatch_send_config.json",
    "broker_dispatch_send_runbook.md",
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


def empty_route_enable_lineage(*, required: bool = False) -> dict[str, Any]:
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
        "cutover_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in cutover_lineage_fields(empty_cutover_lineage())
        }
    )
    return state


def load_route_enable_lineage(route_enable_config_path: str | Path) -> dict[str, Any]:
    config_path = Path(route_enable_config_path).resolve()
    root = config_path.parent
    summary_path = root / "route_enable_summary.csv"
    packet_path = root / "route_enable_packet.csv"
    manifest_path = root / "manifest.json"
    state = empty_route_enable_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in ROUTE_ENABLE_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    packet = _read_csv(packet_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    route_fields = cutover_lineage_fields(empty_cutover_lineage())
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in route_fields
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="route_enable_packet",
            required_artifacts=ROUTE_ENABLE_REQUIRED_ARTIFACTS,
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

    errors = _route_enable_contract_errors(
        summary=summary,
        packet=packet,
        config=config,
        manifest=manifest,
        lineage=state,
        route_fields=tuple(route_fields),
    )
    packet_row = packet.iloc[0] if not packet.empty else pd.Series(dtype=object)
    extra = _mapping(manifest.get("extra"))
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and "authorizes_submission" in packet_row.index
        and not _bool(packet_row.get("authorizes_submission"))
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )
    cutover_gate = _bool(state.get("cutover_lineage_gate_passed", False))
    cutover_matches_current = _route_cutover_matches_current(
        route_manifest=manifest,
        route_manifest_path=manifest_path,
        lineage=state,
        route_fields=tuple(route_fields),
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["cutover_matches_current"] = cutover_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and cutover_gate
        and cutover_matches_current
    )
    return state


def route_enable_lineage_fields(lineage: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "route_enable_lineage_required": _bool(lineage.get("required", False)),
        "route_enable_lineage_provided": _bool(lineage.get("provided", False)),
        "route_enable_manifest_current": _bool(lineage.get("manifest_current", False)),
        "route_enable_manifest_run_type": _text(lineage.get("manifest_run_type", "")),
        "route_enable_manifest_path": _text(lineage.get("manifest_path", "")),
        "route_enable_manifest_sha256": _text(lineage.get("manifest_sha256", "")),
        "route_enable_manifest_error": _text(lineage.get("manifest_error", "")),
        "route_enable_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "route_enable_lineage_contract_error": _text(
            lineage.get("contract_error", "")
        ),
        "route_enable_non_authorizing": _bool(
            lineage.get("non_authorizing", False)
        ),
        "route_enable_cutover_lineage_gate_passed": _bool(
            lineage.get("cutover_lineage_gate_passed", False)
        ),
        "route_enable_cutover_matches_current": _bool(
            lineage.get("cutover_matches_current", False)
        ),
        "route_enable_lineage_gate_passed": _bool(lineage.get("gate_passed", False)),
        "route_enable_lineage_dependency_count": int(
            lineage.get("dependency_count", 0)
        ),
    }
    route_fields = cutover_lineage_fields(empty_cutover_lineage())
    fields.update(
        {
            f"route_enable_{column}": _normalize(lineage.get(column), column)
            for column in route_fields
        }
    )
    return fields


def route_enable_lineage_manifest_inputs(lineage: Mapping[str, Any]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["route_enable_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["route_enable_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["route_enable_dependencies"] = dependencies
    return inputs


def empty_broker_dispatch_lineage(*, required: bool = False) -> dict[str, Any]:
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
        "route_enable_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in route_enable_lineage_fields(empty_route_enable_lineage())
        }
    )
    return state


def load_broker_dispatch_lineage(
    broker_dispatch_config_path: str | Path,
) -> dict[str, Any]:
    config_path = Path(broker_dispatch_config_path).resolve()
    root = config_path.parent
    summary_path = root / "broker_dispatch_summary.csv"
    orders_path = root / "broker_dispatch_orders.csv"
    manifest_path = root / "manifest.json"
    state = empty_broker_dispatch_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in BROKER_DISPATCH_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    orders = _read_csv(orders_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    route_fields = route_enable_lineage_fields(empty_route_enable_lineage())
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in route_fields
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="broker_dispatch_plan",
            required_artifacts=BROKER_DISPATCH_REQUIRED_ARTIFACTS,
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

    errors = _broker_dispatch_contract_errors(
        summary=summary,
        orders=orders,
        config=config,
        manifest=manifest,
        lineage=state,
        route_fields=tuple(route_fields),
    )
    extra = _mapping(manifest.get("extra"))
    orders_non_authorizing = bool(
        not orders.empty
        and "authorizes_submission" in orders.columns
        and not orders["authorizes_submission"].map(_bool).any()
        and "dry_run_only" in orders.columns
        and orders["dry_run_only"].map(_bool).all()
    )
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and _bool(config.get("dry_run_only"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and _bool(row.get("dry_run_only"))
        and orders_non_authorizing
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )
    route_gate = _bool(state.get("route_enable_lineage_gate_passed", False))
    route_enable_matches_current = _dispatch_route_enable_matches_current(
        dispatch_manifest=manifest,
        dispatch_manifest_path=manifest_path,
        lineage=state,
        route_fields=tuple(route_fields),
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["route_enable_matches_current"] = route_enable_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and route_gate
        and route_enable_matches_current
    )
    return state


def broker_dispatch_lineage_fields(lineage: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "broker_dispatch_lineage_required": _bool(lineage.get("required", False)),
        "broker_dispatch_lineage_provided": _bool(lineage.get("provided", False)),
        "broker_dispatch_manifest_current": _bool(lineage.get("manifest_current", False)),
        "broker_dispatch_manifest_run_type": _text(lineage.get("manifest_run_type", "")),
        "broker_dispatch_manifest_path": _text(lineage.get("manifest_path", "")),
        "broker_dispatch_manifest_sha256": _text(lineage.get("manifest_sha256", "")),
        "broker_dispatch_manifest_error": _text(lineage.get("manifest_error", "")),
        "broker_dispatch_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "broker_dispatch_lineage_contract_error": _text(
            lineage.get("contract_error", "")
        ),
        "broker_dispatch_non_authorizing": _bool(
            lineage.get("non_authorizing", False)
        ),
        "broker_dispatch_route_enable_lineage_gate_passed": _bool(
            lineage.get("route_enable_lineage_gate_passed", False)
        ),
        "broker_dispatch_route_enable_matches_current": _bool(
            lineage.get("route_enable_matches_current", False)
        ),
        "broker_dispatch_lineage_gate_passed": _bool(
            lineage.get("gate_passed", False)
        ),
        "broker_dispatch_lineage_dependency_count": int(
            lineage.get("dependency_count", 0)
        ),
    }
    route_fields = route_enable_lineage_fields(empty_route_enable_lineage())
    fields.update(
        {
            f"broker_dispatch_{column}": _normalize(lineage.get(column), column)
            for column in route_fields
        }
    )
    return fields


def broker_dispatch_lineage_manifest_inputs(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["broker_dispatch_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["broker_dispatch_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["broker_dispatch_dependencies"] = dependencies
    return inputs


def empty_broker_dispatch_send_lineage(*, required: bool = False) -> dict[str, Any]:
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
        "broker_dispatch_matches_current": not required,
        "expected_dispatch_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in broker_dispatch_lineage_fields(
                empty_broker_dispatch_lineage()
            )
        }
    )
    return state


def load_broker_dispatch_send_lineage(
    broker_dispatch_send_config_path: str | Path,
    expected_broker_dispatch_config_path: str | Path | None = None,
) -> dict[str, Any]:
    config_path = Path(broker_dispatch_send_config_path).resolve()
    root = config_path.parent
    summary_path = root / "broker_dispatch_send_summary.csv"
    requests_path = root / "broker_dispatch_send_requests.csv"
    expected_acks_path = root / "broker_dispatch_expected_acks.csv"
    manifest_path = root / "manifest.json"
    state = empty_broker_dispatch_send_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in BROKER_DISPATCH_SEND_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    requests = _read_csv(requests_path)
    expected_acks = _read_csv(expected_acks_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    dispatch_fields = broker_dispatch_lineage_fields(
        empty_broker_dispatch_lineage()
    )
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in dispatch_fields
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="broker_dispatch_send_packet",
            required_artifacts=BROKER_DISPATCH_SEND_REQUIRED_ARTIFACTS,
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

    errors = _broker_dispatch_send_contract_errors(
        summary=summary,
        requests=requests,
        expected_acks=expected_acks,
        config=config,
        manifest=manifest,
        lineage=state,
        dispatch_fields=tuple(dispatch_fields),
    )
    extra = _mapping(manifest.get("extra"))
    requests_non_authorizing = bool(
        not requests.empty
        and "authorizes_submission" in requests.columns
        and not requests["authorizes_submission"].map(_bool).any()
        and "submission_enabled" in requests.columns
        and not requests["submission_enabled"].map(_bool).any()
        and "dry_run_only" in requests.columns
        and requests["dry_run_only"].map(_bool).all()
        and _request_payload_boolean_matches(
            requests, "authorizes_submission", False
        )
        and _request_payload_boolean_matches(requests, "submission_enabled", False)
        and _request_payload_boolean_matches(requests, "dry_run_only", True)
    )
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and "submission_enabled" in config
        and not _bool(config.get("submission_enabled"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and "submission_enabled" in row.index
        and not _bool(row.get("submission_enabled"))
        and _bool(row.get("dry_run_only"))
        and requests_non_authorizing
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
        and "submission_enabled" in extra
        and not _bool(extra.get("submission_enabled"))
    )
    dispatch_gate = _bool(state.get("broker_dispatch_lineage_gate_passed", False))
    broker_dispatch_matches_current = _send_dispatch_matches_current(
        send_manifest=manifest,
        send_manifest_path=manifest_path,
        lineage=state,
        dispatch_fields=tuple(dispatch_fields),
    )
    expected_dispatch_matches_current = _send_matches_expected_dispatch(
        lineage=state,
        expected_broker_dispatch_config_path=expected_broker_dispatch_config_path,
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["broker_dispatch_matches_current"] = broker_dispatch_matches_current
    state["expected_dispatch_matches_current"] = expected_dispatch_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and dispatch_gate
        and broker_dispatch_matches_current
        and expected_dispatch_matches_current
    )
    return state


def broker_dispatch_send_lineage_fields(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "broker_dispatch_send_lineage_required": _bool(
            lineage.get("required", False)
        ),
        "broker_dispatch_send_lineage_provided": _bool(
            lineage.get("provided", False)
        ),
        "broker_dispatch_send_manifest_current": _bool(
            lineage.get("manifest_current", False)
        ),
        "broker_dispatch_send_manifest_run_type": _text(
            lineage.get("manifest_run_type", "")
        ),
        "broker_dispatch_send_manifest_path": _text(
            lineage.get("manifest_path", "")
        ),
        "broker_dispatch_send_manifest_sha256": _text(
            lineage.get("manifest_sha256", "")
        ),
        "broker_dispatch_send_manifest_error": _text(
            lineage.get("manifest_error", "")
        ),
        "broker_dispatch_send_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "broker_dispatch_send_lineage_contract_error": _text(
            lineage.get("contract_error", "")
        ),
        "broker_dispatch_send_non_authorizing": _bool(
            lineage.get("non_authorizing", False)
        ),
        "broker_dispatch_send_broker_dispatch_lineage_gate_passed": _bool(
            lineage.get("broker_dispatch_lineage_gate_passed", False)
        ),
        "broker_dispatch_send_broker_dispatch_matches_current": _bool(
            lineage.get("broker_dispatch_matches_current", False)
        ),
        "broker_dispatch_send_expected_dispatch_matches_current": _bool(
            lineage.get("expected_dispatch_matches_current", False)
        ),
        "broker_dispatch_send_lineage_gate_passed": _bool(
            lineage.get("gate_passed", False)
        ),
        "broker_dispatch_send_lineage_dependency_count": int(
            lineage.get("dependency_count", 0)
        ),
    }
    dispatch_fields = broker_dispatch_lineage_fields(
        empty_broker_dispatch_lineage()
    )
    fields.update(
        {
            f"broker_dispatch_send_{column}": _normalize(
                lineage.get(column), column
            )
            for column in dispatch_fields
        }
    )
    return fields


def broker_dispatch_send_lineage_manifest_inputs(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["broker_dispatch_send_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["broker_dispatch_send_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["broker_dispatch_send_dependencies"] = dependencies
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


def _route_enable_contract_errors(
    *,
    summary: pd.DataFrame,
    packet: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    lineage: Mapping[str, Any],
    route_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("route_enable_summary_missing_or_empty")
    if packet.empty:
        errors.append("route_enable_packet_missing_or_empty")
    if not config:
        errors.append("route_enable_config_missing_or_invalid")
    if not manifest:
        errors.append("route_enable_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    packet_row = packet.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_lineage = _mapping(config.get("cutover_lineage"))
    for column in route_fields:
        expected = lineage[column]
        if not _same(packet_row.get(column), expected, column):
            errors.append(f"route_enable_packet_{column}_mismatch")
        if not _same(config_lineage.get(column), expected, column):
            errors.append(f"route_enable_config_{column}_mismatch")
        if not _same(extra.get(column), expected, column):
            errors.append(f"route_enable_manifest_{column}_mismatch")
    if not _same(config.get("route_enabled"), row.get("ready"), "ready"):
        errors.append("route_enable_config_ready_mismatch")
    if not _same(packet_row.get("route_enabled"), row.get("ready"), "ready"):
        errors.append("route_enable_packet_ready_mismatch")
    if not _same(extra.get("ready"), row.get("ready"), "ready"):
        errors.append("route_enable_manifest_ready_mismatch")
    return errors


def _broker_dispatch_contract_errors(
    *,
    summary: pd.DataFrame,
    orders: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    lineage: Mapping[str, Any],
    route_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("broker_dispatch_summary_missing_or_empty")
    if orders.empty:
        errors.append("broker_dispatch_orders_missing_or_empty")
    if not config:
        errors.append("broker_dispatch_config_missing_or_invalid")
    if not manifest:
        errors.append("broker_dispatch_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_lineage = _mapping(config.get("route_enable_lineage"))
    for column in route_fields:
        expected = lineage[column]
        if not _frame_column_matches(orders, column, expected):
            errors.append(f"broker_dispatch_orders_{column}_mismatch")
        if not _same(config_lineage.get(column), expected, column):
            errors.append(f"broker_dispatch_config_{column}_mismatch")
        if not _same(extra.get(column), expected, column):
            errors.append(f"broker_dispatch_manifest_{column}_mismatch")

    for column in (
        "dispatch_batch_id",
        "target_mode",
        "strategy",
        "market",
        "scenario_key",
        "adapter",
    ):
        expected = row.get(column)
        if not _frame_text_column_matches(orders, column, expected):
            errors.append(f"broker_dispatch_orders_{column}_mismatch")
        if not _same_text(config.get(column), expected):
            errors.append(f"broker_dispatch_config_{column}_mismatch")
    if not _same(config.get("ready"), row.get("ready"), "ready"):
        errors.append("broker_dispatch_config_ready_mismatch")
    if not _same_text(config.get("dispatch_state"), row.get("dispatch_state")):
        errors.append("broker_dispatch_config_dispatch_state_mismatch")
    if not _same(extra.get("ready"), row.get("ready"), "ready"):
        errors.append("broker_dispatch_manifest_ready_mismatch")
    if not _frame_column_matches(orders, "dispatch_action", "dry_run_submit"):
        errors.append("broker_dispatch_orders_dispatch_action_mismatch")
    return errors


def _broker_dispatch_send_contract_errors(
    *,
    summary: pd.DataFrame,
    requests: pd.DataFrame,
    expected_acks: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    lineage: Mapping[str, Any],
    dispatch_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("broker_dispatch_send_summary_missing_or_empty")
    if requests.empty:
        errors.append("broker_dispatch_send_requests_missing_or_empty")
    if expected_acks.empty:
        errors.append("broker_dispatch_send_expected_acks_missing_or_empty")
    if not config:
        errors.append("broker_dispatch_send_config_missing_or_invalid")
    if not manifest:
        errors.append("broker_dispatch_send_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_lineage = _mapping(config.get("broker_dispatch_lineage"))
    for column in dispatch_fields:
        expected = lineage[column]
        if not _frame_column_matches(requests, column, expected):
            errors.append(f"broker_dispatch_send_requests_{column}_mismatch")
        if not _request_payload_field_matches(requests, column, expected):
            errors.append(f"broker_dispatch_send_payload_{column}_mismatch")
        if not _same(config_lineage.get(column), expected, column):
            errors.append(f"broker_dispatch_send_config_{column}_mismatch")
        if not _same(extra.get(column), expected, column):
            errors.append(f"broker_dispatch_send_manifest_{column}_mismatch")

    for column in (
        "dispatch_batch_id",
        "target_mode",
        "strategy",
        "market",
        "scenario_key",
        "adapter",
    ):
        expected = row.get(column)
        if not _frame_text_column_matches(requests, column, expected):
            errors.append(f"broker_dispatch_send_requests_{column}_mismatch")
        if not _same_text(config.get(column), expected):
            errors.append(f"broker_dispatch_send_config_{column}_mismatch")
    if not _same(config.get("ready"), row.get("ready"), "ready"):
        errors.append("broker_dispatch_send_config_ready_mismatch")
    if not _same_text(config.get("request_state"), row.get("request_state")):
        errors.append("broker_dispatch_send_config_request_state_mismatch")
    if not _same(extra.get("ready"), row.get("ready"), "ready"):
        errors.append("broker_dispatch_send_manifest_ready_mismatch")
    if _integer(row.get("requests")) != len(requests):
        errors.append("broker_dispatch_send_summary_request_count_mismatch")
    if not _send_request_hashes_valid(requests):
        errors.append("broker_dispatch_send_request_hash_contract_mismatch")
    if not _expected_ack_template_matches_requests(expected_acks, requests):
        errors.append("broker_dispatch_send_expected_ack_template_mismatch")
    return errors


def _send_dispatch_matches_current(
    *,
    send_manifest: Mapping[str, Any],
    send_manifest_path: Path,
    lineage: Mapping[str, Any],
    dispatch_fields: tuple[str, ...],
) -> bool:
    dispatch_manifest_path = _manifest_input_path(
        send_manifest,
        send_manifest_path,
        "broker_dispatch_manifest",
    ) or _manifest_input_path(
        send_manifest,
        send_manifest_path,
        "dispatch_manifest",
    )
    if dispatch_manifest_path is None or not dispatch_manifest_path.is_file():
        return False
    dispatch_config_path = dispatch_manifest_path.with_name(
        "broker_dispatch_config.json"
    )
    if not dispatch_config_path.is_file():
        return False
    current = load_broker_dispatch_lineage(dispatch_config_path)
    current_fields = broker_dispatch_lineage_fields(current)
    return bool(
        current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in dispatch_fields
        )
    )


def _send_matches_expected_dispatch(
    *,
    lineage: Mapping[str, Any],
    expected_broker_dispatch_config_path: str | Path | None,
) -> bool:
    if expected_broker_dispatch_config_path is None:
        return True
    expected_config_path = Path(expected_broker_dispatch_config_path).resolve()
    expected_manifest_path = expected_config_path.with_name("manifest.json")
    if not expected_config_path.is_file() or not expected_manifest_path.is_file():
        return False
    return bool(
        _same_text(
            lineage.get("broker_dispatch_manifest_path"),
            str(expected_manifest_path),
        )
        and _same_text(
            lineage.get("broker_dispatch_manifest_sha256"),
            file_sha256(expected_manifest_path),
        )
    )


def _dispatch_route_enable_matches_current(
    *,
    dispatch_manifest: Mapping[str, Any],
    dispatch_manifest_path: Path,
    lineage: Mapping[str, Any],
    route_fields: tuple[str, ...],
) -> bool:
    route_manifest_path = _manifest_input_path(
        dispatch_manifest,
        dispatch_manifest_path,
        "route_enable_manifest",
    )
    if route_manifest_path is None or not route_manifest_path.is_file():
        return False
    route_enable_config_path = route_manifest_path.with_name("route_enable_config.json")
    if not route_enable_config_path.is_file():
        return False
    current = load_route_enable_lineage(route_enable_config_path)
    current_fields = route_enable_lineage_fields(current)
    return bool(
        current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in route_fields
        )
    )


def _route_cutover_matches_current(
    *,
    route_manifest: Mapping[str, Any],
    route_manifest_path: Path,
    lineage: Mapping[str, Any],
    route_fields: tuple[str, ...],
) -> bool:
    cutover_manifest_path = _manifest_input_path(
        route_manifest,
        route_manifest_path,
        "cutover_manifest",
    )
    if cutover_manifest_path is None or not cutover_manifest_path.is_file():
        return False
    cutover_config_path = cutover_manifest_path.with_name("cutover_config.json")
    if not cutover_config_path.is_file():
        return False
    current = load_cutover_lineage(cutover_config_path)
    current_fields = cutover_lineage_fields(current)
    return bool(
        current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in route_fields
        )
    )


def _frame_column_matches(frame: pd.DataFrame, column: str, expected: Any) -> bool:
    return bool(
        not frame.empty
        and column in frame.columns
        and frame[column].map(lambda value: _same(value, expected, column)).all()
    )


def _frame_text_column_matches(
    frame: pd.DataFrame,
    column: str,
    expected: Any,
) -> bool:
    return bool(
        not frame.empty
        and column in frame.columns
        and frame[column].map(lambda value: _same_text(value, expected)).all()
    )


def _request_payload_field_matches(
    requests: pd.DataFrame,
    column: str,
    expected: Any,
) -> bool:
    payloads = _request_payloads(requests)
    return bool(
        len(payloads) == len(requests)
        and all(_same(payload.get(column), expected, column) for payload in payloads)
    )


def _request_payload_boolean_matches(
    requests: pd.DataFrame,
    column: str,
    expected: bool,
) -> bool:
    payloads = _request_payloads(requests)
    return bool(
        len(payloads) == len(requests)
        and all(_bool(payload.get(column)) is expected for payload in payloads)
    )


def _request_payloads(requests: pd.DataFrame) -> list[dict[str, Any]]:
    if requests.empty or "request_payload_json" not in requests.columns:
        return []
    payloads: list[dict[str, Any]] = []
    for raw in requests["request_payload_json"]:
        try:
            value = json.loads(_text(raw))
        except (ValueError, TypeError, json.JSONDecodeError):
            return []
        if not isinstance(value, dict):
            return []
        payloads.append(value)
    return payloads


def _expected_ack_template_matches_requests(
    expected_acks: pd.DataFrame,
    requests: pd.DataFrame,
) -> bool:
    columns = (
        "dispatch_order_id",
        "source_order_id",
        "request_id",
        "idempotency_key",
        "route_dispatch_roundtrip_batch_id",
        "adapter",
        "target_mode",
    )
    if any(column not in expected_acks.columns for column in columns):
        return False
    if any(column not in requests.columns for column in columns):
        return False
    expected_records = sorted(
        tuple(_text(row.get(column)) for column in columns)
        for row in expected_acks.to_dict(orient="records")
    )
    request_records = sorted(
        tuple(_text(row.get(column)) for column in columns)
        for row in requests.to_dict(orient="records")
    )
    return expected_records == request_records


def _send_request_hashes_valid(requests: pd.DataFrame) -> bool:
    required_columns = {
        "request_id",
        "idempotency_key",
        "request_payload_hash",
        "request_payload_json",
    }
    if requests.empty or not required_columns.issubset(requests.columns):
        return False
    for index, row in enumerate(requests.to_dict(orient="records"), start=1):
        try:
            payload = json.loads(_text(row.get("request_payload_json")))
        except (ValueError, TypeError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if not _same_text(row.get("request_payload_hash"), payload_hash):
            return False
        if not _same_text(
            row.get("idempotency_key"), f"IDEMP-{payload_hash[:24]}"
        ):
            return False
        if not _same_text(
            row.get("request_id"), f"BDR-{index:06d}-{payload_hash[:12]}"
        ):
            return False
    return True


def _manifest_input_path(
    manifest: Mapping[str, Any],
    manifest_path: Path,
    input_name: str,
) -> Path | None:
    inputs = _mapping(manifest.get("inputs"))
    value = inputs.get(input_name)
    if not isinstance(value, Mapping):
        return None
    raw_path = _text(value.get("path"))
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


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


def _same_text(left: Any, right: Any) -> bool:
    return _text(left) == _text(right)


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
