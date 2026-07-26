from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from reports.leadlag_lineage import (
    LEADLAG_LINEAGE_BOOLEAN_FIELDS,
    LEADLAG_LINEAGE_FIELDS,
    LEADLAG_LINEAGE_INTEGER_FIELDS,
    LEADLAG_LINEAGE_NUMERIC_FIELDS,
    LEADLAG_LINEAGE_TEXT_FIELDS,
    leadlag_lineage_field_matches,
    leadlag_lineage_fields,
)
from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
)
from reports.runtime_guard import RUNTIME_LINEAGE_COLUMNS, SCALEUP_PROVENANCE_COLUMNS
from reports.scaleup_runtime_provenance import (
    BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_ACTIVE_FIELD,
    BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_CURRENT_SHA256_FIELD,
    BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
    BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SOURCE_VERDICT_FIELD,
    empty_scaleup_runtime_provenance,
    load_scaleup_runtime_provenance,
    scaleup_runtime_fields,
)


LINEAGE_COLUMNS = (*SCALEUP_PROVENANCE_COLUMNS, *RUNTIME_LINEAGE_COLUMNS)
RUNTIME_CONTRACT_IDENTITY_FIELDS = (
    (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_active"
    ),
    (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_sha256"
    ),
    (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_lineage_verified"
    ),
    (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_matches_current"
    ),
    (
        "runtime_lineage_broker_readiness_"
        "contract_identity_active"
    ),
    (
        "runtime_lineage_current_broker_readiness_"
        "contract_identity_sha256"
    ),
    (
        "runtime_lineage_broker_readiness_"
        "contract_identity_matches_current"
    ),
)
SCALEUP_PROVENANCE_DEFAULTS = scaleup_runtime_fields(
    empty_scaleup_runtime_provenance()
)
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
BROKER_DISPATCH_CONTRACT_IDENTITY_COLUMNS = (
    ("contract_identity_row_number", "contract_identity_row_number"),
    ("broker_order_id", "source_broker_order_id"),
    ("client_order_id", "client_order_id"),
    ("leg_group_id", "leg_group_id"),
    ("leg_role", "leg_role"),
    ("leg_index", "leg_index"),
    ("leg_count", "leg_count"),
    ("research_instrument_id", "research_instrument_id"),
    ("broker_instrument_id", "broker_instrument_id"),
    ("broker_instrument_token", "broker_instrument_token"),
    ("instrument_resolution_method", "instrument_resolution_method"),
    ("instrument_resolution_status", "instrument_resolution_status"),
    ("upload_instrument_column", "upload_instrument_column"),
    ("upload_instrument_id", "upload_instrument_id"),
    ("upload_identity_matches", "upload_identity_matches"),
    ("resolution_row_ready", "resolution_row_ready"),
)
BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS = tuple(
    request_column
    for _dispatch_column, request_column in (
        BROKER_DISPATCH_CONTRACT_IDENTITY_COLUMNS
    )
)
BROKER_DISPATCH_CONTRACT_IDENTITY_INTEGER_COLUMNS = {
    "contract_identity_row_number",
    "leg_index",
    "leg_count",
}
BROKER_DISPATCH_CONTRACT_IDENTITY_BOOLEAN_COLUMNS = {
    "upload_identity_matches",
    "resolution_row_ready",
}
BROKER_DISPATCH_ACK_REQUIRED_ARTIFACTS = (
    "broker_dispatch_acknowledgements.csv",
    "broker_dispatch_unmatched_acks.csv",
    "broker_dispatch_ack_checks.csv",
    "broker_dispatch_ack_summary.csv",
    "broker_dispatch_ack_action_queue.csv",
    "broker_dispatch_ack_config.json",
    "broker_dispatch_ack_runbook.md",
)
BROKER_DISPATCH_ROUNDTRIP_REQUIRED_ARTIFACTS = (
    "broker_dispatch_roundtrip_orders.csv",
    "broker_dispatch_roundtrip_checks.csv",
    "broker_dispatch_roundtrip_summary.csv",
    "broker_dispatch_roundtrip_action_queue.csv",
    "broker_dispatch_roundtrip_config.json",
    "broker_dispatch_roundtrip_runbook.md",
)
BROKER_READINESS_REQUIRED_ARTIFACTS = (
    "broker_readiness_items.csv",
    "broker_readiness_checks.csv",
    "broker_readiness_summary.csv",
    "broker_readiness_action_queue.csv",
    "broker_readiness_config.json",
    "broker_readiness_runbook.md",
)
ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    "leadlag_edge_lineage_required",
    *LEADLAG_LINEAGE_FIELDS,
    "leadlag_edge_lineage_matches_scaleup",
    "leadlag_cutover_contract_consistent",
)
ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_SOURCE_FIELDS = (
    "leadlag_edge_lineage_required",
    *LEADLAG_LINEAGE_FIELDS,
    "leadlag_edge_lineage_matches_scaleup",
)
BROKER_DISPATCH_STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    *ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_FIELDS,
    "leadlag_route_contract_consistent",
)
BROKER_DISPATCH_SEND_STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    *BROKER_DISPATCH_STRATEGY_PORTFOLIO_LEADLAG_FIELDS,
    "leadlag_dispatch_contract_consistent",
)
BROKER_DISPATCH_ACK_STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    *BROKER_DISPATCH_SEND_STRATEGY_PORTFOLIO_LEADLAG_FIELDS,
    "leadlag_send_contract_consistent",
)
BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    *BROKER_DISPATCH_ACK_STRATEGY_PORTFOLIO_LEADLAG_FIELDS,
    "leadlag_ack_contract_consistent",
)
BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_SOURCE_FIELDS = (
    ("contract_identity_active", "roundtrip_contract_identity_active"),
    ("contract_identity_required", "roundtrip_contract_identity_required"),
    (
        "contract_identity_send_gate_passed",
        "roundtrip_contract_identity_send_gate_passed",
    ),
    (
        "contract_identity_ack_gate_passed",
        "roundtrip_contract_identity_ack_gate_passed",
    ),
    (
        "contract_identity_request_columns_present",
        "roundtrip_contract_identity_request_columns_present",
    ),
    (
        "contract_identity_ack_columns_present",
        "roundtrip_contract_identity_ack_columns_present",
    ),
    (
        "contract_identity_request_orders",
        "roundtrip_contract_identity_request_orders",
    ),
    (
        "contract_identity_ack_orders",
        "roundtrip_contract_identity_ack_orders",
    ),
    (
        "contract_identity_roundtrip_orders",
        "roundtrip_contract_identity_roundtrip_orders",
    ),
    (
        "contract_identity_stage_digests_match",
        "roundtrip_contract_identity_stage_digests_match",
    ),
    (
        "contract_identity_acknowledgements_match_requests",
        "roundtrip_contract_identity_acknowledgements_match_requests",
    ),
    (
        "contract_identity_roundtrip_matches_requests",
        "roundtrip_contract_identity_roundtrip_matches_requests",
    ),
    ("contract_identity_sha256", "roundtrip_contract_identity_sha256"),
    (
        "contract_identity_consistency_error",
        "roundtrip_contract_identity_consistency_error",
    ),
    (
        "contract_identity_gate_passed",
        "roundtrip_contract_identity_gate_passed",
    ),
)
BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_FIELDS = (
    *(
        f"broker_dispatch_roundtrip_{field}"
        for field, _source_field in (
            BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_SOURCE_FIELDS
        )
    ),
    "broker_dispatch_roundtrip_contract_identity_lineage_verified",
    "broker_dispatch_roundtrip_contract_identity_lineage_error",
)
BROKER_DISPATCH_ACK_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD = (
    "broker_dispatch_ack_broker_dispatch_send_broker_dispatch_route_enable_"
    "cutover_runtime_telemetry_broker_readiness_roundtrip_"
    "contract_identity_sha256"
)
BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD = (
    "broker_dispatch_roundtrip_"
    f"{BROKER_DISPATCH_ACK_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD}"
)
BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELDS = (
    "broker_dispatch_roundtrip_ack_route_contract_identity_active",
    BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
    "broker_dispatch_roundtrip_current_ack_route_contract_identity_sha256",
    "broker_dispatch_roundtrip_ack_route_contract_identity_matches_current",
)
BROKER_READINESS_ROUNDTRIP_CONTRACT_IDENTITY_FIELD_MAP = tuple(
    (
        field.replace(
            "broker_dispatch_roundtrip_",
            "broker_readiness_roundtrip_",
            1,
        ),
        field,
    )
    for field in BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_FIELDS
)
BROKER_READINESS_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELD_MAP = tuple(
    (
        field.replace(
            "broker_dispatch_roundtrip_",
            "broker_readiness_roundtrip_",
            1,
        ),
        field,
    )
    for field in BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELDS
)
BROKER_READINESS_ROUNDTRIP_LINEAGE_BASE_FIELDS = (
    "broker_dispatch_roundtrip_lineage_required",
    "broker_dispatch_roundtrip_lineage_provided",
    "broker_dispatch_roundtrip_manifest_current",
    "broker_dispatch_roundtrip_manifest_run_type",
    "broker_dispatch_roundtrip_manifest_path",
    "broker_dispatch_roundtrip_manifest_sha256",
    "broker_dispatch_roundtrip_manifest_error",
    "broker_dispatch_roundtrip_lineage_contract_consistent",
    "broker_dispatch_roundtrip_lineage_contract_error",
    "broker_dispatch_roundtrip_non_authorizing",
    "broker_dispatch_roundtrip_ack_lineage_gate_passed",
    "broker_dispatch_roundtrip_ack_matches_current",
    "broker_dispatch_roundtrip_expected_ack_matches_current",
    "broker_dispatch_roundtrip_lineage_gate_passed",
    "broker_dispatch_roundtrip_lineage_dependency_count",
)
BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS = (
    *BROKER_READINESS_ROUNDTRIP_LINEAGE_BASE_FIELDS,
    *BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_FIELDS,
    *BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELDS,
    *(
        f"broker_dispatch_roundtrip_strategy_portfolio_{field}"
        for field in BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    ),
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
        "broker_readiness_required": False,
        "broker_readiness_source_matches_scaleup": not required,
        "current_broker_readiness_manifest_sha256": "",
        "broker_readiness_matches_current": not required,
        "broker_readiness_contract_identity_active": False,
        "current_broker_readiness_contract_identity_sha256": "",
        "broker_readiness_contract_identity_matches_current": not required,
        "broker_readiness_route_contract_identity_active": False,
        "current_broker_readiness_route_contract_identity_sha256": "",
        "broker_readiness_route_contract_identity_matches_current": (
            not required
        ),
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
    expected_broker_readiness_config_path: str | Path | None = None,
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

    broker_readiness = _runtime_session_broker_readiness_state(
        lineage=state,
        scaleup_config_path=scaleup_config_path,
        expected_broker_readiness_config_path=(
            expected_broker_readiness_config_path
        ),
    )
    state.update(broker_readiness)

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
        and state["broker_readiness_source_matches_scaleup"]
        and state["broker_readiness_matches_current"]
        and state["broker_readiness_contract_identity_matches_current"]
        and state["broker_readiness_route_contract_identity_matches_current"]
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
        "runtime_lineage_broker_readiness_required": _bool(
            lineage.get("broker_readiness_required", False)
        ),
        "runtime_lineage_broker_readiness_source_matches_scaleup": _bool(
            lineage.get("broker_readiness_source_matches_scaleup", False)
        ),
        "runtime_lineage_current_broker_readiness_manifest_sha256": _text(
            lineage.get("current_broker_readiness_manifest_sha256", "")
        ),
        "runtime_lineage_broker_readiness_matches_current": _bool(
            lineage.get("broker_readiness_matches_current", False)
        ),
        "runtime_lineage_broker_readiness_contract_identity_active": _bool(
            lineage.get("broker_readiness_contract_identity_active", False)
        ),
        (
            "runtime_lineage_current_broker_readiness_"
            "contract_identity_sha256"
        ): _text(
            lineage.get(
                "current_broker_readiness_contract_identity_sha256",
                "",
            )
        ),
        (
            "runtime_lineage_broker_readiness_"
            "contract_identity_matches_current"
        ): _bool(
            lineage.get(
                "broker_readiness_contract_identity_matches_current",
                False,
            )
        ),
        (
            "runtime_lineage_broker_readiness_"
            "route_contract_identity_active"
        ): _bool(
            lineage.get(
                "broker_readiness_route_contract_identity_active",
                False,
            )
        ),
        (
            "runtime_lineage_current_broker_readiness_"
            "route_contract_identity_sha256"
        ): _text(
            lineage.get(
                "current_broker_readiness_route_contract_identity_sha256",
                "",
            )
        ),
        (
            "runtime_lineage_broker_readiness_"
            "route_contract_identity_matches_current"
        ): _bool(
            lineage.get(
                "broker_readiness_route_contract_identity_matches_current",
                False,
            )
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


def _runtime_session_broker_readiness_state(
    *,
    lineage: Mapping[str, Any],
    scaleup_config_path: str | Path,
    expected_broker_readiness_config_path: str | Path | None,
) -> dict[str, Any]:
    required = bool(
        any(
            _bool(lineage.get(column, False))
            for column in (
                "scaleup_broker_readiness_required",
                "scaleup_broker_readiness_provided",
                "scaleup_broker_readiness_lineage_required",
                "scaleup_broker_readiness_lineage_provided",
            )
        )
        or _text(lineage.get("scaleup_broker_readiness_manifest_sha256", ""))
        or _text(
            lineage.get(
                "runtime_telemetry_broker_readiness_manifest_sha256",
                "",
            )
        )
    )
    if not required:
        return {
            "broker_readiness_required": False,
            "broker_readiness_source_matches_scaleup": True,
            "current_broker_readiness_manifest_sha256": "",
            "broker_readiness_matches_current": True,
            "broker_readiness_contract_identity_active": False,
            "current_broker_readiness_contract_identity_sha256": "",
            "broker_readiness_contract_identity_matches_current": True,
            "broker_readiness_route_contract_identity_active": False,
            "current_broker_readiness_route_contract_identity_sha256": "",
            "broker_readiness_route_contract_identity_matches_current": True,
        }

    scaleup_manifest_path = _source_manifest_path(scaleup_config_path)
    scaleup_manifest = _read_json(scaleup_manifest_path)
    bound_config_path = _manifest_input_path(
        scaleup_manifest,
        scaleup_manifest_path,
        "broker_readiness_config",
    )
    expected_config_path = (
        Path(expected_broker_readiness_config_path).resolve()
        if expected_broker_readiness_config_path is not None
        else None
    )
    source_matches_scaleup = bool(
        bound_config_path is not None
        and bound_config_path.is_file()
        and (
            expected_config_path is None
            or expected_config_path == bound_config_path
        )
    )
    current_config_path = expected_config_path or bound_config_path
    current_lineage = empty_broker_readiness_lineage(required=True)
    if current_config_path is not None and current_config_path.is_file():
        current_lineage = load_broker_readiness_lineage(current_config_path)
    current_fields = broker_readiness_lineage_fields(current_lineage)
    current_manifest_sha256 = _text(
        current_fields.get("broker_readiness_manifest_sha256", "")
    )
    carried_fields_match = all(
        _same(
            lineage.get(f"scaleup_{field}"),
            value,
            f"scaleup_{field}",
        )
        for field, value in current_fields.items()
    )
    source_claims_match = bool(
        _same(
            lineage.get("scaleup_broker_readiness_source_manifest_current"),
            current_fields.get("broker_readiness_manifest_current"),
            "scaleup_broker_readiness_source_manifest_current",
        )
        and _same(
            lineage.get("scaleup_broker_readiness_source_manifest_sha256"),
            current_manifest_sha256,
            "scaleup_broker_readiness_source_manifest_sha256",
        )
        and _same(
            lineage.get(
                "scaleup_broker_readiness_source_provenance_gate_passed"
            ),
            current_fields.get("broker_readiness_lineage_gate_passed"),
            "scaleup_broker_readiness_source_provenance_gate_passed",
        )
        and _bool(lineage.get("scaleup_broker_readiness_matches_current"))
    )
    telemetry_matches = bool(
        _same(
            lineage.get(
                "runtime_telemetry_broker_readiness_manifest_sha256"
            ),
            current_manifest_sha256,
            "runtime_telemetry_broker_readiness_manifest_sha256",
        )
        and _same(
            lineage.get(
                "runtime_telemetry_broker_readiness_lineage_gate_passed"
            ),
            current_fields.get("broker_readiness_lineage_gate_passed"),
            "runtime_telemetry_broker_readiness_lineage_gate_passed",
        )
        and _bool(
            lineage.get("runtime_telemetry_broker_readiness_matches_current")
        )
    )
    current_contract_identity_active = _bool(
        current_fields.get(
            "broker_readiness_roundtrip_contract_identity_active",
            False,
        )
    )
    runtime_contract_identity_active = _bool(
        lineage.get(
            (
                "runtime_telemetry_broker_readiness_roundtrip_"
                "contract_identity_active"
            ),
            False,
        )
    )
    scaleup_contract_identity_active = _bool(
        lineage.get(
            (
                "scaleup_broker_readiness_roundtrip_"
                "contract_identity_active"
            ),
            False,
        )
    )
    contract_identity_active = bool(
        current_contract_identity_active
        or runtime_contract_identity_active
        or scaleup_contract_identity_active
    )
    current_contract_identity_sha256 = _text(
        current_fields.get(
            "broker_readiness_roundtrip_contract_identity_sha256",
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            current_contract_identity_active
            and runtime_contract_identity_active
            and scaleup_contract_identity_active
            and current_contract_identity_sha256
            and _same(
                lineage.get(
                    (
                        "runtime_telemetry_broker_readiness_roundtrip_"
                        "contract_identity_sha256"
                    )
                ),
                current_contract_identity_sha256,
                "runtime_telemetry_broker_readiness_roundtrip_contract_identity_sha256",
            )
            and _bool(
                current_fields.get(
                    (
                        "broker_readiness_roundtrip_"
                        "contract_identity_lineage_verified"
                    ),
                    False,
                )
            )
            and _bool(
                lineage.get(
                    (
                        "runtime_telemetry_broker_readiness_roundtrip_"
                        "contract_identity_lineage_verified"
                    ),
                    False,
                )
            )
            and _bool(
                lineage.get(
                    (
                        "runtime_telemetry_broker_readiness_roundtrip_"
                        "contract_identity_matches_current"
                    ),
                    False,
                )
            )
            and _bool(
                lineage.get(
                    (
                        "scaleup_broker_readiness_roundtrip_"
                        "contract_identity_matches_current"
                    ),
                    False,
                )
            )
        )
    )
    current_route_identity_active = bool(
        _bool(
            current_fields.get(
                BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_ACTIVE_FIELD,
                False,
            )
        )
        or _text(
            current_fields.get(
                BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
                "",
            )
        )
        or _text(
            current_fields.get(
                BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_CURRENT_SHA256_FIELD,
                "",
            )
        )
    )
    runtime_route_identity_active = bool(
        _bool(
            lineage.get(
                (
                    "runtime_telemetry_broker_readiness_"
                    "route_contract_identity_active"
                ),
                False,
            )
        )
        or _text(
            lineage.get(
                (
                    "runtime_telemetry_broker_readiness_"
                    "route_contract_identity_sha256"
                ),
                "",
            )
        )
        or _text(
            lineage.get(
                (
                    "runtime_telemetry_current_broker_readiness_"
                    "route_contract_identity_sha256"
                ),
                "",
            )
        )
    )
    scaleup_route_identity_active = bool(
        _bool(
            lineage.get(
                (
                    "scaleup_broker_readiness_"
                    "route_contract_identity_active"
                ),
                False,
            )
        )
        or _text(
            lineage.get(
                (
                    "scaleup_broker_readiness_"
                    "route_contract_identity_sha256"
                ),
                "",
            )
        )
        or _text(
            lineage.get(
                (
                    "scaleup_broker_readiness_current_"
                    "route_contract_identity_sha256"
                ),
                "",
            )
        )
    )
    route_identity_active = bool(
        current_route_identity_active
        or runtime_route_identity_active
        or scaleup_route_identity_active
    )
    current_route_identity_sha256 = _text(
        current_fields.get(
            BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_CURRENT_SHA256_FIELD,
            "",
        )
        or current_fields.get(
            BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
            "",
        )
    )
    route_identity_matches_current = bool(
        not route_identity_active
        or (
            current_route_identity_active
            and runtime_route_identity_active
            and scaleup_route_identity_active
            and current_route_identity_sha256
            and _same(
                lineage.get(
                    (
                        "runtime_telemetry_broker_readiness_"
                        "route_contract_identity_sha256"
                    )
                ),
                current_route_identity_sha256,
                (
                    "runtime_telemetry_broker_readiness_"
                    "route_contract_identity_sha256"
                ),
            )
            and _same(
                lineage.get(
                    (
                        "runtime_telemetry_current_broker_readiness_"
                        "route_contract_identity_sha256"
                    )
                ),
                current_route_identity_sha256,
                (
                    "runtime_telemetry_current_broker_readiness_"
                    "route_contract_identity_sha256"
                ),
            )
            and _same(
                lineage.get(
                    (
                        "scaleup_broker_readiness_"
                        "route_contract_identity_sha256"
                    )
                ),
                current_route_identity_sha256,
                (
                    "scaleup_broker_readiness_"
                    "route_contract_identity_sha256"
                ),
            )
            and _same(
                lineage.get(
                    (
                        "scaleup_broker_readiness_current_"
                        "route_contract_identity_sha256"
                    )
                ),
                current_route_identity_sha256,
                (
                    "scaleup_broker_readiness_current_"
                    "route_contract_identity_sha256"
                ),
            )
            and _bool(
                current_fields.get(
                    BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SOURCE_VERDICT_FIELD,
                    False,
                )
            )
            and _bool(
                lineage.get(
                    (
                        "scaleup_broker_readiness_"
                        "route_contract_identity_matches_current"
                    ),
                    False,
                )
            )
            and _bool(
                lineage.get(
                    (
                        "runtime_telemetry_broker_readiness_"
                        "route_contract_identity_matches_current"
                    ),
                    False,
                )
            )
        )
    )
    matches_current = bool(
        source_matches_scaleup
        and current_fields.get("broker_readiness_lineage_gate_passed", False)
        and carried_fields_match
        and source_claims_match
        and telemetry_matches
        and contract_identity_matches_current
        and route_identity_matches_current
    )
    return {
        "broker_readiness_required": True,
        "broker_readiness_source_matches_scaleup": source_matches_scaleup,
        "current_broker_readiness_manifest_sha256": current_manifest_sha256,
        "broker_readiness_matches_current": matches_current,
        "broker_readiness_contract_identity_active": contract_identity_active,
        "current_broker_readiness_contract_identity_sha256": (
            current_contract_identity_sha256
        ),
        "broker_readiness_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
        "broker_readiness_route_contract_identity_active": (
            route_identity_active
        ),
        "current_broker_readiness_route_contract_identity_sha256": (
            current_route_identity_sha256
        ),
        "broker_readiness_route_contract_identity_matches_current": (
            route_identity_matches_current
        ),
    }


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
        "broker_readiness_required": False,
        "runtime_lineage_source_bound": not required,
        "current_runtime_session_manifest_sha256": "",
        "runtime_lineage_matches_current": not required,
        "runtime_contract_identity_active": False,
        "current_runtime_contract_identity_sha256": "",
        "runtime_contract_identity_matches_current": not required,
        "broker_readiness_source_matches_scaleup": not required,
        "current_broker_readiness_manifest_sha256": "",
        "broker_readiness_matches_current": not required,
        "scaleup_source_bound": not required,
        "current_scaleup_manifest_sha256": "",
        "current_scaleup_provenance_gate_passed": not required,
        "current_scaleup_contract_error": "",
        "current_scaleup_proof_refresh_active": False,
        "current_scaleup_proof_refresh_source_semantically_verified": False,
        "current_scaleup_proof_refresh_source_provenance_gate_passed": False,
        "current_scaleup_proof_refresh_matches_current": not required,
        "scaleup_provenance_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in SCALEUP_PROVENANCE_COLUMNS
        }
    )
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
    authorization_path = root / "cutover_authorization.csv"
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

    authorization = _read_csv(authorization_path)
    summary = _read_csv(summary_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in SCALEUP_PROVENANCE_COLUMNS
        }
    )
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
        authorization=authorization,
        summary=summary,
        config=config,
        manifest=manifest,
        lineage=state,
        scaleup_fields=tuple(SCALEUP_PROVENANCE_COLUMNS),
        runtime_fields=tuple(runtime_fields),
    )
    extra = _mapping(manifest.get("extra"))
    authorization_row = (
        authorization.iloc[0]
        if not authorization.empty
        else pd.Series(dtype=object)
    )
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and "authorizes_submission" in authorization_row.index
        and not _bool(authorization_row.get("authorizes_submission"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )
    runtime_gate = _bool(state.get("runtime_lineage_gate_passed", False))
    current_runtime = _cutover_current_runtime_lineage_state(
        lineage=state,
        manifest=manifest,
        manifest_path=manifest_path,
        runtime_fields=tuple(runtime_fields),
    )
    state.update(current_runtime)
    current_scaleup = _cutover_current_scaleup_provenance_state(
        lineage=state,
        manifest=manifest,
        manifest_path=manifest_path,
        scaleup_fields=tuple(SCALEUP_PROVENANCE_COLUMNS),
    )
    state.update(current_scaleup)
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
        and state["runtime_lineage_source_bound"]
        and state["runtime_lineage_matches_current"]
        and state["runtime_contract_identity_matches_current"]
        and state["broker_readiness_source_matches_scaleup"]
        and state["broker_readiness_matches_current"]
        and state["scaleup_source_bound"]
        and state["current_scaleup_provenance_gate_passed"]
        and state["scaleup_provenance_matches_current"]
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
        "cutover_broker_readiness_required": _bool(
            lineage.get("broker_readiness_required", False)
        ),
        "cutover_runtime_lineage_source_bound": _bool(
            lineage.get("runtime_lineage_source_bound", False)
        ),
        "cutover_current_runtime_session_manifest_sha256": _text(
            lineage.get("current_runtime_session_manifest_sha256", "")
        ),
        "cutover_runtime_lineage_matches_current": _bool(
            lineage.get("runtime_lineage_matches_current", False)
        ),
        "cutover_runtime_contract_identity_active": _bool(
            lineage.get("runtime_contract_identity_active", False)
        ),
        "cutover_current_runtime_contract_identity_sha256": _text(
            lineage.get("current_runtime_contract_identity_sha256", "")
        ),
        "cutover_runtime_contract_identity_matches_current": _bool(
            lineage.get("runtime_contract_identity_matches_current", False)
        ),
        "cutover_broker_readiness_source_matches_scaleup": _bool(
            lineage.get("broker_readiness_source_matches_scaleup", False)
        ),
        "cutover_current_broker_readiness_manifest_sha256": _text(
            lineage.get("current_broker_readiness_manifest_sha256", "")
        ),
        "cutover_broker_readiness_matches_current": _bool(
            lineage.get("broker_readiness_matches_current", False)
        ),
        "cutover_scaleup_source_bound": _bool(
            lineage.get("scaleup_source_bound", False)
        ),
        "cutover_current_scaleup_manifest_sha256": _text(
            lineage.get("current_scaleup_manifest_sha256", "")
        ),
        "cutover_current_scaleup_provenance_gate_passed": _bool(
            lineage.get("current_scaleup_provenance_gate_passed", False)
        ),
        "cutover_current_scaleup_contract_error": _text(
            lineage.get("current_scaleup_contract_error", "")
        ),
        "cutover_current_scaleup_proof_refresh_active": _bool(
            lineage.get("current_scaleup_proof_refresh_active", False)
        ),
        (
            "cutover_current_scaleup_proof_refresh_"
            "source_semantically_verified"
        ): _bool(
            lineage.get(
                "current_scaleup_proof_refresh_source_semantically_verified",
                False,
            )
        ),
        (
            "cutover_current_scaleup_proof_refresh_"
            "source_provenance_gate_passed"
        ): _bool(
            lineage.get(
                "current_scaleup_proof_refresh_source_provenance_gate_passed",
                False,
            )
        ),
        "cutover_current_scaleup_proof_refresh_matches_current": _bool(
            lineage.get(
                "current_scaleup_proof_refresh_matches_current",
                False,
            )
        ),
        "cutover_scaleup_provenance_matches_current": _bool(
            lineage.get("scaleup_provenance_matches_current", False)
        ),
        "cutover_lineage_gate_passed": _bool(lineage.get("gate_passed", False)),
        "cutover_lineage_dependency_count": int(lineage.get("dependency_count", 0)),
    }
    fields.update(
        {
            f"cutover_{column}": _normalize(
                lineage.get(column),
                column,
            )
            for column in SCALEUP_PROVENANCE_COLUMNS
        }
    )
    runtime_fields = runtime_session_lineage_fields(empty_runtime_session_lineage())
    fields.update(
        {
            f"cutover_{column}": _normalize(lineage.get(column), column)
            for column in runtime_fields
        }
    )
    return fields


def _cutover_current_runtime_lineage_state(
    *,
    lineage: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    runtime_fields: tuple[str, ...],
) -> dict[str, Any]:
    broker_required = bool(
        _bool(lineage.get("runtime_lineage_broker_readiness_required", False))
        or _text(
            lineage.get(
                "runtime_lineage_current_broker_readiness_manifest_sha256",
                "",
            )
        )
        or _text(
            lineage.get(
                "runtime_telemetry_broker_readiness_manifest_sha256",
                "",
            )
        )
    )
    if not broker_required:
        return {
            "broker_readiness_required": False,
            "runtime_lineage_source_bound": True,
            "current_runtime_session_manifest_sha256": "",
            "runtime_lineage_matches_current": True,
            "runtime_contract_identity_active": False,
            "current_runtime_contract_identity_sha256": "",
            "runtime_contract_identity_matches_current": True,
            "broker_readiness_source_matches_scaleup": True,
            "current_broker_readiness_manifest_sha256": "",
            "broker_readiness_matches_current": True,
        }

    runtime_summary_path = _manifest_input_path(
        manifest,
        manifest_path,
        "runtime_session_summary",
    )
    scaleup_config_path = _manifest_input_path(
        manifest,
        manifest_path,
        "scaleup_config",
    )
    broker_readiness_config_path = _manifest_input_path(
        manifest,
        manifest_path,
        "broker_readiness_config",
    )
    source_bound = bool(
        runtime_summary_path is not None
        and runtime_summary_path.is_file()
        and scaleup_config_path is not None
        and scaleup_config_path.is_file()
        and broker_readiness_config_path is not None
        and broker_readiness_config_path.is_file()
    )
    current = empty_runtime_session_lineage(required=True)
    if source_bound:
        current = load_runtime_session_lineage(
            runtime_summary_path,
            scaleup_config_path,
            expected_broker_readiness_config_path=broker_readiness_config_path,
        )
    current_fields = runtime_session_lineage_fields(current)
    runtime_matches_current = bool(
        source_bound
        and current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in runtime_fields
        )
    )
    current_contract_identity_active = _bool(
        current_fields.get(
            (
                "runtime_lineage_broker_readiness_"
                "contract_identity_active"
            ),
            False,
        )
    )
    carried_contract_identity_active = bool(
        _bool(
            lineage.get(
                (
                    "runtime_telemetry_broker_readiness_roundtrip_"
                    "contract_identity_active"
                ),
                False,
            )
        )
        or _bool(
            lineage.get(
                (
                    "runtime_lineage_broker_readiness_"
                    "contract_identity_active"
                ),
                False,
            )
        )
        or _text(
            lineage.get(
                (
                    "runtime_telemetry_broker_readiness_roundtrip_"
                    "contract_identity_sha256"
                ),
                "",
            )
        )
        or _text(
            lineage.get(
                (
                    "runtime_lineage_current_broker_readiness_"
                    "contract_identity_sha256"
                ),
                "",
            )
        )
    )
    contract_identity_active = bool(
        current_contract_identity_active
        or carried_contract_identity_active
    )
    current_contract_identity_sha256 = _text(
        current_fields.get(
            (
                "runtime_telemetry_broker_readiness_roundtrip_"
                "contract_identity_sha256"
            ),
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            source_bound
            and current.get("gate_passed", False)
            and current_contract_identity_active
            and current_contract_identity_sha256
            and all(
                _same(
                    lineage.get(column),
                    current_fields.get(column),
                    column,
                )
                for column in RUNTIME_CONTRACT_IDENTITY_FIELDS
            )
        )
    )
    return {
        "broker_readiness_required": True,
        "runtime_lineage_source_bound": source_bound,
        "current_runtime_session_manifest_sha256": _text(
            current.get("manifest_sha256", "")
        ),
        "runtime_lineage_matches_current": runtime_matches_current,
        "runtime_contract_identity_active": contract_identity_active,
        "current_runtime_contract_identity_sha256": (
            current_contract_identity_sha256
        ),
        "runtime_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
        "broker_readiness_source_matches_scaleup": bool(
            source_bound
            and current.get("broker_readiness_source_matches_scaleup", False)
        ),
        "current_broker_readiness_manifest_sha256": _text(
            current.get("current_broker_readiness_manifest_sha256", "")
        ),
        "broker_readiness_matches_current": bool(
            source_bound
            and current.get("broker_readiness_matches_current", False)
        ),
    }


def _cutover_current_scaleup_provenance_state(
    *,
    lineage: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    scaleup_fields: tuple[str, ...],
) -> dict[str, Any]:
    scaleup_config_path = _manifest_input_path(
        manifest,
        manifest_path,
        "scaleup_config",
    )
    scaleup_manifest_path = _manifest_input_path(
        manifest,
        manifest_path,
        "scaleup_manifest",
    )
    if scaleup_config_path is None and scaleup_manifest_path is not None:
        scaleup_config_path = scaleup_manifest_path.with_name(
            "scaleup_config.json"
        )
    if scaleup_manifest_path is None and scaleup_config_path is not None:
        scaleup_manifest_path = scaleup_config_path.with_name("manifest.json")

    carried_manifest_path = _existing_path(
        lineage.get("scaleup_manifest_path")
    )
    source_bound = bool(
        scaleup_config_path is not None
        and scaleup_config_path.is_file()
        and scaleup_manifest_path is not None
        and scaleup_manifest_path.is_file()
        and carried_manifest_path is not None
        and carried_manifest_path.resolve() == scaleup_manifest_path.resolve()
        and scaleup_config_path.parent == scaleup_manifest_path.parent
    )
    current = empty_scaleup_runtime_provenance(required=True)
    if source_bound:
        current = load_scaleup_runtime_provenance(scaleup_config_path)
    current_fields = scaleup_runtime_fields(current)
    matches_current = bool(
        source_bound
        and current.get("provenance_gate_passed", False)
        and all(
            _same(
                lineage.get(column),
                current_fields.get(column),
                column,
            )
            for column in scaleup_fields
        )
    )
    return {
        "scaleup_source_bound": source_bound,
        "current_scaleup_manifest_sha256": _text(
            current.get("manifest_sha256", "")
        ),
        "current_scaleup_provenance_gate_passed": _bool(
            current.get("provenance_gate_passed", False)
        ),
        "current_scaleup_contract_error": _text(
            current.get("contract_error", "")
        ),
        "current_scaleup_proof_refresh_active": _bool(
            current.get("proof_refresh_active", False)
        ),
        "current_scaleup_proof_refresh_source_semantically_verified": _bool(
            current.get(
                "proof_refresh_source_semantically_verified",
                False,
            )
        ),
        "current_scaleup_proof_refresh_source_provenance_gate_passed": _bool(
            current.get(
                "proof_refresh_source_provenance_gate_passed",
                False,
            )
        ),
        "current_scaleup_proof_refresh_matches_current": _bool(
            current.get("proof_refresh_matches_current", False)
        ),
        "scaleup_provenance_matches_current": matches_current,
    }


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
        "cutover_contract_identity_active": False,
        "current_cutover_contract_identity_sha256": "",
        "cutover_contract_identity_matches_current": not required,
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
    state.update(_empty_strategy_portfolio_leadlag_fields())
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
    state.update(_route_enable_strategy_portfolio_leadlag_state(row))
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
    current_cutover = _route_current_cutover_lineage_state(
        route_manifest=manifest,
        route_manifest_path=manifest_path,
        lineage=state,
        route_fields=tuple(route_fields),
    )
    state.update(current_cutover)
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and cutover_gate
        and state["cutover_matches_current"]
        and state["cutover_contract_identity_matches_current"]
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
        "route_enable_cutover_contract_identity_active": _bool(
            lineage.get("cutover_contract_identity_active", False)
        ),
        "route_enable_current_cutover_contract_identity_sha256": _text(
            lineage.get("current_cutover_contract_identity_sha256", "")
        ),
        "route_enable_cutover_contract_identity_matches_current": _bool(
            lineage.get("cutover_contract_identity_matches_current", False)
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
    fields.update(
        {
            f"route_enable_strategy_portfolio_{field}": _normalize(
                lineage.get(f"strategy_portfolio_{field}"),
                field,
            )
            for field in ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
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
        "route_contract_identity_active": False,
        "current_route_contract_identity_sha256": "",
        "route_contract_identity_matches_current": not required,
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
    state.update(_empty_broker_dispatch_leadlag_fields())
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
    orders = _read_csv_text(orders_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    state.update(_broker_dispatch_strategy_portfolio_leadlag_state(row))
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
    current_route = _dispatch_current_route_enable_lineage_state(
        dispatch_manifest=manifest,
        dispatch_manifest_path=manifest_path,
        lineage=state,
        route_fields=tuple(route_fields),
    )
    state.update(current_route)
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and route_gate
        and state["route_enable_matches_current"]
        and state["route_contract_identity_matches_current"]
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
        "broker_dispatch_route_contract_identity_active": _bool(
            lineage.get("route_contract_identity_active", False)
        ),
        "broker_dispatch_current_route_contract_identity_sha256": _text(
            lineage.get("current_route_contract_identity_sha256", "")
        ),
        "broker_dispatch_route_contract_identity_matches_current": _bool(
            lineage.get("route_contract_identity_matches_current", False)
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
    fields.update(
        {
            f"broker_dispatch_strategy_portfolio_{field}": _normalize(
                lineage.get(f"strategy_portfolio_{field}"),
                field,
            )
            for field in BROKER_DISPATCH_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
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
        "dispatch_route_contract_identity_active": False,
        "current_dispatch_route_contract_identity_sha256": "",
        "dispatch_route_contract_identity_matches_current": not required,
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
    state.update(_empty_broker_dispatch_send_leadlag_fields())
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
    requests = _read_csv_text(requests_path)
    expected_acks = _read_csv_text(expected_acks_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    state.update(_broker_dispatch_send_strategy_portfolio_leadlag_state(row))
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
    current_dispatch = _send_current_broker_dispatch_lineage_state(
        send_manifest=manifest,
        send_manifest_path=manifest_path,
        lineage=state,
        dispatch_fields=tuple(dispatch_fields),
    )
    state.update(current_dispatch)
    expected_dispatch_matches_current = _send_matches_expected_dispatch(
        lineage=state,
        expected_broker_dispatch_config_path=expected_broker_dispatch_config_path,
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["expected_dispatch_matches_current"] = expected_dispatch_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and dispatch_gate
        and state["broker_dispatch_matches_current"]
        and expected_dispatch_matches_current
        and state["dispatch_route_contract_identity_matches_current"]
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
        "broker_dispatch_send_dispatch_route_contract_identity_active": _bool(
            lineage.get("dispatch_route_contract_identity_active", False)
        ),
        "broker_dispatch_send_current_dispatch_route_contract_identity_sha256": (
            _text(
                lineage.get(
                    "current_dispatch_route_contract_identity_sha256",
                    "",
                )
            )
        ),
        "broker_dispatch_send_dispatch_route_contract_identity_matches_current": (
            _bool(
                lineage.get(
                    "dispatch_route_contract_identity_matches_current",
                    False,
                )
            )
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
    fields.update(
        {
            f"broker_dispatch_send_strategy_portfolio_{field}": _normalize(
                lineage.get(f"strategy_portfolio_{field}"),
                field,
            )
            for field in BROKER_DISPATCH_SEND_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
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


def empty_broker_dispatch_ack_lineage(*, required: bool = False) -> dict[str, Any]:
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
        "send_lineage_gate_passed": not required,
        "send_matches_current": not required,
        "expected_send_matches_current": not required,
        "send_route_contract_identity_active": False,
        "current_send_route_contract_identity_sha256": "",
        "send_route_contract_identity_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in broker_dispatch_send_lineage_fields(
                empty_broker_dispatch_send_lineage()
            )
        }
    )
    state.update(_empty_broker_dispatch_ack_leadlag_fields())
    return state


def load_broker_dispatch_ack_lineage(
    broker_dispatch_ack_config_path: str | Path,
    expected_broker_dispatch_send_config_path: str | Path | None = None,
    expected_broker_dispatch_config_path: str | Path | None = None,
) -> dict[str, Any]:
    config_path = Path(broker_dispatch_ack_config_path).resolve()
    root = config_path.parent
    summary_path = root / "broker_dispatch_ack_summary.csv"
    acknowledgements_path = root / "broker_dispatch_acknowledgements.csv"
    unmatched_path = root / "broker_dispatch_unmatched_acks.csv"
    checks_path = root / "broker_dispatch_ack_checks.csv"
    manifest_path = root / "manifest.json"
    state = empty_broker_dispatch_ack_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in BROKER_DISPATCH_ACK_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    acknowledgements = _read_csv_text(acknowledgements_path)
    unmatched = _read_csv(unmatched_path)
    checks = _read_csv(checks_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    state.update(_broker_dispatch_ack_strategy_portfolio_leadlag_state(row))
    send_fields = broker_dispatch_send_lineage_fields(
        empty_broker_dispatch_send_lineage()
    )
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in send_fields
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="broker_dispatch_ack_reconciliation",
            required_artifacts=BROKER_DISPATCH_ACK_REQUIRED_ARTIFACTS,
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

    errors = _broker_dispatch_ack_contract_errors(
        summary=summary,
        acknowledgements=acknowledgements,
        unmatched=unmatched,
        checks=checks,
        config=config,
        manifest=manifest,
        manifest_path=manifest_path,
        lineage=state,
        send_fields=tuple(send_fields),
    )
    extra = _mapping(manifest.get("extra"))
    acknowledgements_non_authorizing = bool(
        not acknowledgements.empty
        and "authorizes_submission" in acknowledgements.columns
        and not acknowledgements["authorizes_submission"].map(_bool).any()
    )
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and acknowledgements_non_authorizing
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )
    send_lineage_gate_passed = _bool(
        state.get("broker_dispatch_send_lineage_gate_passed", False)
    )
    current_send = _ack_current_broker_dispatch_send_lineage_state(
        ack_manifest=manifest,
        ack_manifest_path=manifest_path,
        lineage=state,
        send_fields=tuple(send_fields),
        expected_broker_dispatch_config_path=(
            expected_broker_dispatch_config_path
        ),
    )
    state.update(current_send)
    expected_send_matches_current = _ack_matches_expected_send(
        lineage=state,
        expected_broker_dispatch_send_config_path=(
            expected_broker_dispatch_send_config_path
        ),
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["send_lineage_gate_passed"] = send_lineage_gate_passed
    state["expected_send_matches_current"] = expected_send_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and send_lineage_gate_passed
        and state["send_matches_current"]
        and expected_send_matches_current
        and state["send_route_contract_identity_matches_current"]
    )
    return state


def broker_dispatch_ack_lineage_fields(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "broker_dispatch_ack_lineage_required": _bool(
            lineage.get("required", False)
        ),
        "broker_dispatch_ack_lineage_provided": _bool(
            lineage.get("provided", False)
        ),
        "broker_dispatch_ack_manifest_current": _bool(
            lineage.get("manifest_current", False)
        ),
        "broker_dispatch_ack_manifest_run_type": _text(
            lineage.get("manifest_run_type", "")
        ),
        "broker_dispatch_ack_manifest_path": _text(
            lineage.get("manifest_path", "")
        ),
        "broker_dispatch_ack_manifest_sha256": _text(
            lineage.get("manifest_sha256", "")
        ),
        "broker_dispatch_ack_manifest_error": _text(
            lineage.get("manifest_error", "")
        ),
        "broker_dispatch_ack_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "broker_dispatch_ack_lineage_contract_error": _text(
            lineage.get("contract_error", "")
        ),
        "broker_dispatch_ack_non_authorizing": _bool(
            lineage.get("non_authorizing", False)
        ),
        "broker_dispatch_ack_send_lineage_gate_passed": _bool(
            lineage.get("send_lineage_gate_passed", False)
        ),
        "broker_dispatch_ack_send_matches_current": _bool(
            lineage.get("send_matches_current", False)
        ),
        "broker_dispatch_ack_expected_send_matches_current": _bool(
            lineage.get("expected_send_matches_current", False)
        ),
        "broker_dispatch_ack_send_route_contract_identity_active": _bool(
            lineage.get("send_route_contract_identity_active", False)
        ),
        "broker_dispatch_ack_current_send_route_contract_identity_sha256": (
            _text(
                lineage.get(
                    "current_send_route_contract_identity_sha256",
                    "",
                )
            )
        ),
        "broker_dispatch_ack_send_route_contract_identity_matches_current": (
            _bool(
                lineage.get(
                    "send_route_contract_identity_matches_current",
                    False,
                )
            )
        ),
        "broker_dispatch_ack_lineage_gate_passed": _bool(
            lineage.get("gate_passed", False)
        ),
        "broker_dispatch_ack_lineage_dependency_count": int(
            lineage.get("dependency_count", 0)
        ),
    }
    send_fields = broker_dispatch_send_lineage_fields(
        empty_broker_dispatch_send_lineage()
    )
    fields.update(
        {
            f"broker_dispatch_ack_{column}": _normalize(
                lineage.get(column), column
            )
            for column in send_fields
        }
    )
    fields.update(
        {
            f"broker_dispatch_ack_strategy_portfolio_{field}": _normalize(
                lineage.get(f"strategy_portfolio_{field}"),
                field,
            )
            for field in BROKER_DISPATCH_ACK_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
        }
    )
    return fields


def broker_dispatch_ack_lineage_manifest_inputs(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["broker_dispatch_ack_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["broker_dispatch_ack_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["broker_dispatch_ack_dependencies"] = dependencies
    return inputs


def empty_broker_dispatch_roundtrip_lineage(
    *,
    required: bool = False,
) -> dict[str, Any]:
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
        "ack_lineage_gate_passed": not required,
        "ack_matches_current": not required,
        "expected_ack_matches_current": not required,
        "ack_route_contract_identity_active": False,
        "current_ack_route_contract_identity_sha256": "",
        "ack_route_contract_identity_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            column: _field_default(column)
            for column in broker_dispatch_ack_lineage_fields(
                empty_broker_dispatch_ack_lineage()
            )
        }
    )
    state.update(
        {
            f"strategy_portfolio_{field}": _field_default(field)
            for field in (
                BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
            )
        }
    )
    state.update(
        {
            field: _field_default(
                f"broker_dispatch_roundtrip_{field}"
            )
            for field, _source_field in (
                BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_SOURCE_FIELDS
            )
        }
    )
    state["contract_identity_lineage_verified"] = False
    state["contract_identity_lineage_error"] = ""
    return state


def load_broker_dispatch_roundtrip_lineage(
    broker_dispatch_roundtrip_config_path: str | Path,
    expected_broker_dispatch_ack_config_path: str | Path | None = None,
    expected_broker_dispatch_send_config_path: str | Path | None = None,
    expected_broker_dispatch_config_path: str | Path | None = None,
) -> dict[str, Any]:
    config_path = Path(broker_dispatch_roundtrip_config_path).resolve()
    root = config_path.parent
    summary_path = root / "broker_dispatch_roundtrip_summary.csv"
    orders_path = root / "broker_dispatch_roundtrip_orders.csv"
    checks_path = root / "broker_dispatch_roundtrip_checks.csv"
    manifest_path = root / "manifest.json"
    state = empty_broker_dispatch_roundtrip_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in BROKER_DISPATCH_ROUNDTRIP_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    summary = _read_csv(summary_path)
    orders = _read_csv_text(orders_path)
    checks = _read_csv(checks_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    ack_fields = broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage()
    )
    state.update(
        {
            column: _normalize(row.get(column), column)
            for column in ack_fields
        }
    )
    state.update(_broker_dispatch_roundtrip_strategy_portfolio_state(row))
    state.update(
        {
            field: _normalize(
                row.get(source_field),
                f"broker_dispatch_roundtrip_{field}",
            )
            for field, source_field in (
                BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_SOURCE_FIELDS
            )
        }
    )

    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="broker_dispatch_roundtrip",
            required_artifacts=BROKER_DISPATCH_ROUNDTRIP_REQUIRED_ARTIFACTS,
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

    leadlag_active = _broker_dispatch_roundtrip_leadlag_active(
        row,
        config,
        state,
    )
    ack_config_path = _manifest_input_path(
        manifest,
        manifest_path,
        "ack_config",
    )
    current_ack = empty_broker_dispatch_ack_lineage(required=True)
    if ack_config_path is not None:
        current_ack = load_broker_dispatch_ack_lineage(
            ack_config_path,
            expected_broker_dispatch_send_config_path=(
                expected_broker_dispatch_send_config_path
            ),
            expected_broker_dispatch_config_path=(
                expected_broker_dispatch_config_path
            ),
    )
    current_ack_fields = broker_dispatch_ack_lineage_fields(current_ack)
    ack_lineage_gate_passed = bool(current_ack.get("gate_passed", False))
    current_ack_state = (
        _roundtrip_current_broker_dispatch_ack_lineage_state(
            lineage=state,
            ack_fields=tuple(ack_fields),
            current_ack=current_ack,
            current_ack_fields=current_ack_fields,
            source_bound=bool(
                ack_config_path is not None and ack_config_path.is_file()
            ),
        )
    )
    state.update(current_ack_state)
    expected_ack_matches_current = _roundtrip_matches_expected_ack(
        manifest=manifest,
        manifest_path=manifest_path,
        expected_broker_dispatch_ack_config_path=(
            expected_broker_dispatch_ack_config_path
        ),
    )
    extra = _mapping(manifest.get("extra"))
    contract_identity_errors = (
        _broker_dispatch_roundtrip_contract_identity_errors(
            row=row,
            orders=orders,
            config=config,
            extra=extra,
            manifest=manifest,
            manifest_path=manifest_path,
        )
    )
    errors = _broker_dispatch_roundtrip_contract_errors(
        summary=summary,
        orders=orders,
        checks=checks,
        config=config,
        manifest=manifest,
        manifest_path=manifest_path,
        lineage=state,
        ack_fields=tuple(ack_fields),
        current_ack=current_ack,
        leadlag_active=leadlag_active,
        contract_identity_errors=contract_identity_errors,
    )
    contract_identity_active = bool(
        state["contract_identity_active"]
        or _bool(
            _mapping(config.get("contract_identity")).get("active")
        )
        or _bool(extra.get("roundtrip_contract_identity_active"))
        or all(
            column in orders.columns
            for column in BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
        )
    )
    state["contract_identity_active"] = contract_identity_active
    state["contract_identity_lineage_verified"] = bool(
        contract_identity_active
        and (
            not contract_identity_errors
            and state["contract_identity_gate_passed"]
        )
    )
    state["contract_identity_lineage_error"] = ";".join(
        sorted(set(contract_identity_errors))
    )
    orders_non_authorizing = bool(
        not orders.empty
        and "authorizes_submission" in orders.columns
        and not orders["authorizes_submission"].map(_bool).any()
    )
    non_authorizing = bool(
        config
        and "authorizes_submission" in config
        and not _bool(config.get("authorizes_submission"))
        and "authorizes_submission" in row.index
        and not _bool(row.get("authorizes_submission"))
        and orders_non_authorizing
        and extra
        and "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["non_authorizing"] = non_authorizing
    state["ack_lineage_gate_passed"] = ack_lineage_gate_passed
    state["expected_ack_matches_current"] = expected_ack_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and non_authorizing
        and ack_lineage_gate_passed
        and state["ack_matches_current"]
        and expected_ack_matches_current
        and state["ack_route_contract_identity_matches_current"]
    )
    return state


def broker_dispatch_roundtrip_lineage_fields(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "broker_dispatch_roundtrip_lineage_required": _bool(
            lineage.get("required", False)
        ),
        "broker_dispatch_roundtrip_lineage_provided": _bool(
            lineage.get("provided", False)
        ),
        "broker_dispatch_roundtrip_manifest_current": _bool(
            lineage.get("manifest_current", False)
        ),
        "broker_dispatch_roundtrip_manifest_run_type": _text(
            lineage.get("manifest_run_type", "")
        ),
        "broker_dispatch_roundtrip_manifest_path": _text(
            lineage.get("manifest_path", "")
        ),
        "broker_dispatch_roundtrip_manifest_sha256": _text(
            lineage.get("manifest_sha256", "")
        ),
        "broker_dispatch_roundtrip_manifest_error": _text(
            lineage.get("manifest_error", "")
        ),
        "broker_dispatch_roundtrip_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "broker_dispatch_roundtrip_lineage_contract_error": _text(
            lineage.get("contract_error", "")
        ),
        "broker_dispatch_roundtrip_non_authorizing": _bool(
            lineage.get("non_authorizing", False)
        ),
        "broker_dispatch_roundtrip_ack_lineage_gate_passed": _bool(
            lineage.get("ack_lineage_gate_passed", False)
        ),
        "broker_dispatch_roundtrip_ack_matches_current": _bool(
            lineage.get("ack_matches_current", False)
        ),
        "broker_dispatch_roundtrip_expected_ack_matches_current": _bool(
            lineage.get("expected_ack_matches_current", False)
        ),
        "broker_dispatch_roundtrip_ack_route_contract_identity_active": _bool(
            lineage.get("ack_route_contract_identity_active", False)
        ),
        "broker_dispatch_roundtrip_current_ack_route_contract_identity_sha256": (
            _text(
                lineage.get(
                    "current_ack_route_contract_identity_sha256",
                    "",
                )
            )
        ),
        "broker_dispatch_roundtrip_ack_route_contract_identity_matches_current": (
            _bool(
                lineage.get(
                    "ack_route_contract_identity_matches_current",
                    False,
                )
            )
        ),
        "broker_dispatch_roundtrip_lineage_gate_passed": _bool(
            lineage.get("gate_passed", False)
        ),
        "broker_dispatch_roundtrip_lineage_dependency_count": int(
            lineage.get("dependency_count", 0)
        ),
    }
    ack_fields = broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage()
    )
    fields.update(
        {
            f"broker_dispatch_roundtrip_{column}": _normalize(
                lineage.get(column),
                column,
            )
            for column in ack_fields
        }
    )
    fields.update(
        {
            f"broker_dispatch_roundtrip_strategy_portfolio_{field}": (
                _normalize(
                    lineage.get(f"strategy_portfolio_{field}"),
                    field,
                )
            )
            for field in (
                BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
            )
        }
    )
    fields.update(
        {
            f"broker_dispatch_roundtrip_{field}": _normalize(
                lineage.get(field),
                f"broker_dispatch_roundtrip_{field}",
            )
            for field, _source_field in (
                BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_SOURCE_FIELDS
            )
        }
    )
    fields.update(
        {
            "broker_dispatch_roundtrip_contract_identity_lineage_verified": (
                _bool(
                    lineage.get(
                        "contract_identity_lineage_verified",
                        False,
                    )
                )
            ),
            "broker_dispatch_roundtrip_contract_identity_lineage_error": (
                _text(
                    lineage.get(
                        "contract_identity_lineage_error",
                        "",
                    )
                )
            ),
        }
    )
    return fields


def broker_dispatch_roundtrip_lineage_manifest_inputs(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["broker_dispatch_roundtrip_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["broker_dispatch_roundtrip_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["broker_dispatch_roundtrip_dependencies"] = dependencies
    return inputs


def empty_broker_readiness_lineage(
    *,
    required: bool = False,
) -> dict[str, Any]:
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
        "roundtrip_lineage_required": False,
        "roundtrip_lineage_gate_passed": not required,
        "roundtrip_matches_current": not required,
        "gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
    }
    state.update(
        {
            field: _field_default(field)
            for field in BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS
        }
    )
    return state


def load_broker_readiness_lineage(
    broker_readiness_config_path: str | Path,
) -> dict[str, Any]:
    config_path = Path(broker_readiness_config_path).resolve()
    root = config_path.parent
    items_path = root / "broker_readiness_items.csv"
    checks_path = root / "broker_readiness_checks.csv"
    summary_path = root / "broker_readiness_summary.csv"
    manifest_path = root / "manifest.json"
    state = empty_broker_readiness_lineage(required=True)
    state.update(
        {
            "provided": summary_path.is_file(),
            "manifest_path": str(manifest_path),
            "artifact_paths": [
                str(root / name)
                for name in BROKER_READINESS_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )

    items = _read_csv(items_path)
    checks = _read_csv(checks_path)
    summary = _read_csv(summary_path)
    config = _read_json(config_path)
    manifest = _read_json(manifest_path)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    state.update(
        {
            field: _normalize(row.get(field), field)
            for field in BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS
        }
    )

    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="broker_readiness",
            required_artifacts=BROKER_READINESS_REQUIRED_ARTIFACTS,
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

    dispatch_config = _mapping(config.get("dispatch_roundtrip"))
    thresholds_config = _mapping(config.get("thresholds"))
    roundtrip_manifest_inputs = {
        name: _manifest_input_path(manifest, manifest_path, name)
        for name in (
            "dispatch_roundtrip",
            "dispatch_roundtrip_config",
            "dispatch_roundtrip_manifest",
            "broker_dispatch_roundtrip_manifest",
        )
    }
    dispatch_items = (
        items.loc[items["component"].map(_text) == "dispatch_roundtrip"]
        if "component" in items.columns
        else pd.DataFrame()
    )
    dispatch_item_requires_roundtrip = bool(
        not dispatch_items.empty
        and any(
            field in dispatch_items.columns
            and dispatch_items[field].map(_bool).any()
            for field in ("required", "provided", "ready")
        )
    )
    roundtrip_required = bool(
        _bool(row.get("broker_dispatch_roundtrip_lineage_required", False))
        or _bool(row.get("dispatch_roundtrip_provided", False))
        or _bool(dispatch_config.get("provided", False))
        or _bool(thresholds_config.get("require_dispatch_roundtrip", False))
        or dispatch_item_requires_roundtrip
        or any(path is not None for path in roundtrip_manifest_inputs.values())
    )
    roundtrip_config_path = roundtrip_manifest_inputs[
        "dispatch_roundtrip_config"
    ]
    if roundtrip_config_path is None:
        for manifest_input in (
            "broker_dispatch_roundtrip_manifest",
            "dispatch_roundtrip_manifest",
        ):
            roundtrip_manifest_path = roundtrip_manifest_inputs[
                manifest_input
            ]
            if roundtrip_manifest_path is not None:
                roundtrip_config_path = (
                    roundtrip_manifest_path.parent
                    / "broker_dispatch_roundtrip_config.json"
                ).resolve()
                break
    current_roundtrip = empty_broker_dispatch_roundtrip_lineage(
        required=roundtrip_required
    )
    if roundtrip_config_path is not None:
        current_roundtrip = load_broker_dispatch_roundtrip_lineage(
            roundtrip_config_path
        )
    current_roundtrip_fields = broker_dispatch_roundtrip_lineage_fields(
        current_roundtrip
    )
    errors = _broker_readiness_contract_errors(
        items=items,
        checks=checks,
        summary=summary,
        config=config,
        manifest=manifest,
        current_roundtrip_fields=current_roundtrip_fields,
        roundtrip_required=roundtrip_required,
        roundtrip_config_path=roundtrip_config_path,
    )
    route_identity_active_field = (
        "broker_dispatch_roundtrip_ack_route_contract_identity_active"
    )
    current_route_identity_field = (
        "broker_dispatch_roundtrip_current_ack_route_contract_identity_sha256"
    )
    route_identity_verdict_field = (
        "broker_dispatch_roundtrip_ack_route_contract_identity_matches_current"
    )
    carried_route_identity_sha256 = _text(
        state.get(
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
            "",
        )
    )
    current_route_identity_sha256 = _text(
        current_roundtrip_fields.get(current_route_identity_field, "")
    )
    route_identity_active = bool(
        _bool(state.get(route_identity_active_field, False))
        or _bool(
            current_roundtrip_fields.get(
                route_identity_active_field,
                False,
            )
        )
        or carried_route_identity_sha256
        or _text(state.get(current_route_identity_field, ""))
        or _text(
            current_roundtrip_fields.get(
                BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
                "",
            )
        )
        or current_route_identity_sha256
    )
    route_identity_fields_match = all(
        _same(
            state.get(field),
            current_roundtrip_fields.get(field),
            field,
        )
        for field in (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELDS
        )
    )
    route_identity_matches_current = bool(
        not route_identity_active
        or (
            current_roundtrip.get("gate_passed", False)
            and _bool(state.get(route_identity_active_field, False))
            and _bool(
                current_roundtrip_fields.get(
                    route_identity_active_field,
                    False,
                )
            )
            and carried_route_identity_sha256
            and current_route_identity_sha256
            and (
                carried_route_identity_sha256
                == current_route_identity_sha256
            )
            and route_identity_fields_match
            and _bool(state.get(route_identity_verdict_field, False))
        )
    )
    state[route_identity_active_field] = route_identity_active
    state[current_route_identity_field] = current_route_identity_sha256
    state[route_identity_verdict_field] = (
        route_identity_matches_current
    )
    roundtrip_lineage_gate_passed = bool(
        not roundtrip_required or current_roundtrip.get("gate_passed", False)
    )
    roundtrip_matches_current = bool(
        not roundtrip_required
        or (
            current_roundtrip.get("gate_passed", False)
            and not any(error.startswith("roundtrip_") for error in errors)
        )
    )
    state["contract_consistent"] = not errors
    state["contract_error"] = ";".join(sorted(set(errors)))
    state["roundtrip_lineage_required"] = roundtrip_required
    state["roundtrip_lineage_gate_passed"] = roundtrip_lineage_gate_passed
    state["roundtrip_matches_current"] = roundtrip_matches_current
    state["gate_passed"] = bool(
        state["provided"]
        and state["manifest_current"]
        and state["contract_consistent"]
        and roundtrip_lineage_gate_passed
        and roundtrip_matches_current
        and route_identity_matches_current
    )
    return state


def broker_readiness_lineage_fields(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "broker_readiness_lineage_required": _bool(
            lineage.get("required", False)
        ),
        "broker_readiness_lineage_provided": _bool(
            lineage.get("provided", False)
        ),
        "broker_readiness_manifest_current": _bool(
            lineage.get("manifest_current", False)
        ),
        "broker_readiness_manifest_run_type": _text(
            lineage.get("manifest_run_type", "")
        ),
        "broker_readiness_manifest_path": _text(
            lineage.get("manifest_path", "")
        ),
        "broker_readiness_manifest_sha256": _text(
            lineage.get("manifest_sha256", "")
        ),
        "broker_readiness_manifest_error": _text(
            lineage.get("manifest_error", "")
        ),
        "broker_readiness_lineage_contract_consistent": _bool(
            lineage.get("contract_consistent", False)
        ),
        "broker_readiness_lineage_contract_error": _text(
            lineage.get("contract_error", "")
        ),
        "broker_readiness_roundtrip_lineage_required": _bool(
            lineage.get("roundtrip_lineage_required", False)
        ),
        "broker_readiness_roundtrip_lineage_gate_passed": _bool(
            lineage.get("roundtrip_lineage_gate_passed", False)
        ),
        "broker_readiness_roundtrip_matches_current": _bool(
            lineage.get("roundtrip_matches_current", False)
        ),
        "broker_readiness_lineage_gate_passed": _bool(
            lineage.get("gate_passed", False)
        ),
        "broker_readiness_lineage_dependency_count": int(
            lineage.get("dependency_count", 0)
        ),
    }
    fields.update(
        {
            target_field: _normalize(
                lineage.get(source_field),
                target_field,
            )
            for (
                target_field,
                source_field,
            ) in BROKER_READINESS_ROUNDTRIP_CONTRACT_IDENTITY_FIELD_MAP
        }
    )
    fields.update(
        {
            target_field: _normalize(
                lineage.get(source_field),
                target_field,
            )
            for (
                target_field,
                source_field,
            ) in (
                BROKER_READINESS_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
            )
        }
    )
    identity_errors = [
        _text(
            lineage.get(
                "broker_dispatch_roundtrip_contract_identity_lineage_error",
                "",
            )
        ),
        *(
            error
            for error in _text(lineage.get("contract_error", "")).split(";")
            if "contract_identity" in error
        ),
    ]
    identity_error = ";".join(
        dict.fromkeys(error for error in identity_errors if error)
    )
    fields[
        "broker_readiness_roundtrip_contract_identity_lineage_verified"
    ] = bool(
        fields[
            "broker_readiness_roundtrip_contract_identity_lineage_verified"
        ]
        and not identity_error
    )
    fields[
        "broker_readiness_roundtrip_contract_identity_lineage_error"
    ] = identity_error
    return fields


def broker_readiness_lineage_manifest_inputs(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(lineage.get("manifest_path"))
    if manifest_path is not None:
        inputs["broker_readiness_manifest"] = manifest_path
    artifacts = _existing_paths(lineage.get("artifact_paths"))
    if artifacts:
        inputs["broker_readiness_artifacts"] = artifacts
    dependencies = _existing_paths(lineage.get("dependency_paths"))
    if dependencies:
        inputs["broker_readiness_dependencies"] = dependencies
    return inputs


def _broker_readiness_contract_errors(
    *,
    items: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    current_roundtrip_fields: Mapping[str, Any],
    roundtrip_required: bool,
    roundtrip_config_path: Path | None,
) -> list[str]:
    errors: list[str] = []
    if len(summary) != 1:
        errors.append("summary_row_count")
    if items.empty:
        errors.append("items_missing")
    elif "component" not in items.columns:
        errors.append("items_component_missing")
    if checks.empty or "passed" not in checks.columns:
        errors.append("checks_missing_or_invalid")
    if not config:
        errors.append("config_missing_or_invalid")
    if not manifest:
        errors.append("manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    for field in ("ready", "adapter", "failed_checks"):
        if field not in row.index:
            errors.append(f"summary_{field}_missing")
    for field in ("ready", "adapter", "component_counts"):
        if field not in config:
            errors.append(f"config_{field}_missing")
    if "ready" not in extra:
        errors.append("manifest_ready_missing")
    ready = _bool(row.get("ready", False))
    if _bool(config.get("ready", False)) != ready:
        errors.append("config_ready_mismatch")
    if _bool(extra.get("ready", False)) != ready:
        errors.append("manifest_ready_mismatch")
    if not _same_text(config.get("adapter"), row.get("adapter")):
        errors.append("config_adapter_mismatch")
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    if _integer(row.get("failed_checks", -1), fallback=-1) != failed_checks:
        errors.append("summary_failed_checks_mismatch")
    component_counts = _mapping(config.get("component_counts"))
    if _integer(component_counts.get("failed_checks", -1), fallback=-1) != failed_checks:
        errors.append("config_failed_checks_mismatch")

    if not roundtrip_required:
        return errors
    if roundtrip_config_path is None or not roundtrip_config_path.is_file():
        errors.append("roundtrip_config_missing_from_manifest")
        return errors

    dispatch_items = items.loc[
        items["component"].map(_text) == "dispatch_roundtrip"
    ]
    if len(dispatch_items) != 1:
        errors.append("roundtrip_item_row_count")
        return errors
    dispatch_item = dispatch_items.iloc[0]
    config_lineage = _mapping(
        _mapping(config.get("dispatch_roundtrip")).get("lineage")
    )
    contract_identity_active = any(
        _bool(value)
        for value in (
            current_roundtrip_fields.get(
                "broker_dispatch_roundtrip_contract_identity_active"
            ),
            row.get(
                "broker_dispatch_roundtrip_contract_identity_active"
            ),
            dispatch_item.get(
                "broker_dispatch_roundtrip_contract_identity_active"
            ),
            config_lineage.get("contract_identity_active"),
            extra.get(
                "broker_dispatch_roundtrip_contract_identity_active"
            ),
        )
    )
    for field in BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS:
        if (
            field
            in BROKER_DISPATCH_ROUNDTRIP_CONTRACT_IDENTITY_FIELDS
            and not contract_identity_active
        ):
            continue
        config_field = field.removeprefix("broker_dispatch_roundtrip_")
        sources = {
            "summary": (field in row.index, row.get(field)),
            "items": (field in dispatch_item.index, dispatch_item.get(field)),
            "config": (
                config_field in config_lineage,
                config_lineage.get(config_field),
            ),
            "manifest": (field in extra, extra.get(field)),
        }
        for source, (present, value) in sources.items():
            if not present:
                errors.append(f"roundtrip_{field}_missing:{source}")
            elif not _same(value, current_roundtrip_fields.get(field), field):
                errors.append(f"roundtrip_{field}_mismatch:{source}")
    return errors


def _broker_dispatch_roundtrip_strategy_portfolio_state(
    row: pd.Series,
) -> dict[str, Any]:
    return {
        f"strategy_portfolio_{field}": _normalize(
            row.get(f"strategy_portfolio_{field}"),
            field,
        )
        for field in (
            BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
        )
    }


def _broker_dispatch_roundtrip_leadlag_active(
    row: pd.Series,
    config: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> bool:
    strategy_portfolio = _mapping(config.get("strategy_portfolio"))
    return bool(
        _text(row.get("strategy_portfolio_selected_profile")).lower()
        == "leadlag"
        or _text(strategy_portfolio.get("selected_profile")).lower()
        == "leadlag"
        or _bool(
            lineage.get(
                "strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(
            strategy_portfolio.get(
                "leadlag_edge_lineage_required",
                False,
            )
        )
    )


def _broker_dispatch_roundtrip_contract_errors(
    *,
    summary: pd.DataFrame,
    orders: pd.DataFrame,
    checks: pd.DataFrame,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    lineage: Mapping[str, Any],
    ack_fields: tuple[str, ...],
    current_ack: Mapping[str, Any],
    leadlag_active: bool,
    contract_identity_errors: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("broker_dispatch_roundtrip_summary_missing_or_empty")
    if orders.empty:
        errors.append("broker_dispatch_roundtrip_orders_missing_or_empty")
    if checks.empty:
        errors.append("broker_dispatch_roundtrip_checks_missing_or_empty")
    if not config:
        errors.append("broker_dispatch_roundtrip_config_missing_or_invalid")
    if not manifest:
        errors.append("broker_dispatch_roundtrip_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_ack_lineage = _mapping(
        config.get("broker_dispatch_ack_lineage")
    )
    for column in ack_fields:
        expected = lineage[column]
        if column not in row.index:
            errors.append(
                f"broker_dispatch_roundtrip_summary_{column}_missing"
            )
        if not _frame_column_matches(orders, column, expected):
            errors.append(
                f"broker_dispatch_roundtrip_orders_{column}_mismatch"
            )
        if column not in config_ack_lineage or not _same(
            config_ack_lineage.get(column),
            expected,
            column,
        ):
            errors.append(
                f"broker_dispatch_roundtrip_config_{column}_mismatch"
            )
        if column not in extra or not _same(
            extra.get(column),
            expected,
            column,
        ):
            errors.append(
                f"broker_dispatch_roundtrip_manifest_{column}_mismatch"
            )

    errors.extend(
        _broker_dispatch_roundtrip_leadlag_contract_errors(
            row=row,
            orders=orders,
            config=config,
            extra=extra,
            lineage=lineage,
            current_ack=current_ack,
            active=leadlag_active,
        )
    )
    errors.extend(
        contract_identity_errors
        if contract_identity_errors is not None
        else _broker_dispatch_roundtrip_contract_identity_errors(
            row=row,
            orders=orders,
            config=config,
            extra=extra,
            manifest=manifest,
            manifest_path=manifest_path,
        )
    )
    for column in (
        "target_mode",
        "strategy",
        "market",
        "scenario_key",
        "adapter",
    ):
        expected = row.get(column)
        if column not in row.index or column not in config or not _same_text(
            config.get(column),
            expected,
        ):
            errors.append(
                f"broker_dispatch_roundtrip_config_{column}_mismatch"
            )
    if "passed" not in config or not _same(
        config.get("passed"),
        row.get("passed"),
        "passed",
    ):
        errors.append("broker_dispatch_roundtrip_config_passed_mismatch")
    if "passed" not in extra or not _same(
        extra.get("passed"),
        row.get("passed"),
        "passed",
    ):
        errors.append("broker_dispatch_roundtrip_manifest_passed_mismatch")
    if "passed" not in checks.columns:
        errors.append("broker_dispatch_roundtrip_checks_passed_missing")
        return errors
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    checks_passed = failed_checks == 0
    if _bool(row.get("passed")) != checks_passed:
        errors.append("broker_dispatch_roundtrip_summary_checks_mismatch")
    if (
        "failed_check_count" not in row.index
        or _integer(row.get("failed_check_count")) != failed_checks
    ):
        errors.append(
            "broker_dispatch_roundtrip_summary_failed_check_count_mismatch"
        )
    if (
        "failed_check_count" not in config
        or _integer(config.get("failed_check_count")) != failed_checks
    ):
        errors.append(
            "broker_dispatch_roundtrip_config_failed_check_count_mismatch"
        )
    return errors


def _broker_dispatch_roundtrip_contract_identity_errors(
    *,
    row: pd.Series,
    orders: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_path: Path,
) -> list[str]:
    identity = _mapping(config.get("contract_identity"))
    columns_present = all(
        column in orders.columns
        for column in BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
    )
    active = bool(
        _bool(row.get("roundtrip_contract_identity_active"))
        or _bool(identity.get("active"))
        or _bool(extra.get("roundtrip_contract_identity_active"))
        or columns_present
    )
    if not active:
        return []

    errors: list[str] = []
    boolean_fields = {
        "active": "roundtrip_contract_identity_active",
        "required": "roundtrip_contract_identity_required",
        "send_gate_passed": (
            "roundtrip_contract_identity_send_gate_passed"
        ),
        "ack_gate_passed": "roundtrip_contract_identity_ack_gate_passed",
        "request_columns_present": (
            "roundtrip_contract_identity_request_columns_present"
        ),
        "ack_columns_present": (
            "roundtrip_contract_identity_ack_columns_present"
        ),
        "stage_digests_match": (
            "roundtrip_contract_identity_stage_digests_match"
        ),
        "acknowledgements_match_requests": (
            "roundtrip_contract_identity_acknowledgements_match_requests"
        ),
        "roundtrip_matches_requests": (
            "roundtrip_contract_identity_roundtrip_matches_requests"
        ),
        "gate_passed": "roundtrip_contract_identity_gate_passed",
    }
    integer_fields = {
        "request_orders": "roundtrip_contract_identity_request_orders",
        "ack_orders": "roundtrip_contract_identity_ack_orders",
        "roundtrip_orders": "roundtrip_contract_identity_roundtrip_orders",
    }
    text_fields = {
        "identity_sha256": "roundtrip_contract_identity_sha256",
        "consistency_error": (
            "roundtrip_contract_identity_consistency_error"
        ),
    }
    for config_field, summary_field in boolean_fields.items():
        if _bool(identity.get(config_field)) != _bool(row.get(summary_field)):
            errors.append(
                f"broker_dispatch_roundtrip_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in integer_fields.items():
        if _integer(identity.get(config_field)) != _integer(
            row.get(summary_field)
        ):
            errors.append(
                f"broker_dispatch_roundtrip_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in text_fields.items():
        if not _same_text(identity.get(config_field), row.get(summary_field)):
            errors.append(
                f"broker_dispatch_roundtrip_config_{summary_field}_mismatch"
            )

    for field in (
        "roundtrip_contract_identity_active",
        "roundtrip_contract_identity_gate_passed",
    ):
        if _bool(extra.get(field)) != _bool(row.get(field)):
            errors.append(
                f"broker_dispatch_roundtrip_manifest_{field}_mismatch"
            )
    if not _same_text(
        extra.get("roundtrip_contract_identity_sha256"),
        row.get("roundtrip_contract_identity_sha256"),
    ):
        errors.append(
            "broker_dispatch_roundtrip_manifest_contract_identity_sha256_mismatch"
        )

    all_fields = (
        *boolean_fields.values(),
        *integer_fields.values(),
        *text_fields.values(),
    )
    for field in all_fields:
        if not _frame_column_matches(orders, field, row.get(field)):
            errors.append(
                f"broker_dispatch_roundtrip_orders_{field}_mismatch"
            )

    if not columns_present:
        errors.append(
            "broker_dispatch_roundtrip_contract_identity_columns_missing"
        )
        return errors
    output_records = broker_dispatch_contract_identity_records(orders)
    output_sha256 = broker_dispatch_contract_identity_records_sha256(
        output_records
    )
    if not _same_text(
        row.get("roundtrip_contract_identity_sha256"),
        output_sha256,
    ):
        errors.append(
            "broker_dispatch_roundtrip_contract_identity_digest_mismatch"
        )
    if _integer(row.get("roundtrip_contract_identity_roundtrip_orders")) != len(
        output_records
    ):
        errors.append(
            "broker_dispatch_roundtrip_contract_identity_count_mismatch"
        )

    requests_path = _manifest_input_path(
        manifest,
        manifest_path,
        "send_requests",
    )
    acknowledgements_path = _manifest_input_path(
        manifest,
        manifest_path,
        "acknowledgements",
    )
    requests = (
        _read_csv_text(requests_path)
        if requests_path is not None
        else pd.DataFrame()
    )
    acknowledgements = (
        _read_csv_text(acknowledgements_path)
        if acknowledgements_path is not None
        else pd.DataFrame()
    )
    if requests.empty:
        errors.append(
            "broker_dispatch_roundtrip_request_identity_source_missing"
        )
    if acknowledgements.empty:
        errors.append(
            "broker_dispatch_roundtrip_ack_identity_source_missing"
        )
    if not requests.empty and not acknowledgements.empty:
        if not _roundtrip_contract_identity_sources_match(
            orders=orders,
            requests=requests,
            acknowledgements=acknowledgements,
        ):
            errors.append(
                "broker_dispatch_roundtrip_contract_identity_source_mismatch"
            )
    if not _bool(row.get("roundtrip_contract_identity_gate_passed")):
        errors.append(
            "broker_dispatch_roundtrip_contract_identity_gate_failed"
        )
    return errors


def _roundtrip_contract_identity_sources_match(
    *,
    orders: pd.DataFrame,
    requests: pd.DataFrame,
    acknowledgements: pd.DataFrame,
) -> bool:
    if len(requests) != len(orders) or len(acknowledgements) != len(orders):
        return False
    for output in orders.to_dict(orient="records"):
        request = _matching_identity_rows(requests, output)
        acknowledgement = _matching_identity_rows(
            acknowledgements,
            output,
        )
        if len(request) != 1 or len(acknowledgement) != 1:
            return False
        expected = broker_dispatch_contract_identity_record(request.iloc[0])
        if broker_dispatch_contract_identity_record(output) != expected:
            return False
        if (
            broker_dispatch_contract_identity_record(
                acknowledgement.iloc[0]
            )
            != expected
        ):
            return False
    return True


def _broker_dispatch_roundtrip_leadlag_contract_errors(
    *,
    row: pd.Series,
    orders: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    lineage: Mapping[str, Any],
    current_ack: Mapping[str, Any],
    active: bool,
) -> list[str]:
    strategy_portfolio = _mapping(config.get("strategy_portfolio"))
    direct_fields = (
        BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    )
    if not active:
        return []

    errors: list[str] = []
    summary_profile = _text(
        row.get("strategy_portfolio_selected_profile")
    ).lower()
    config_profile = _text(
        strategy_portfolio.get("selected_profile")
    ).lower()
    if active and (
        summary_profile != "leadlag" or config_profile != "leadlag"
    ):
        errors.append(
            "broker_dispatch_roundtrip_strategy_portfolio_profile_mismatch"
        )
    for field in direct_fields:
        column = f"strategy_portfolio_{field}"
        expected = lineage[column]
        if column not in row.index:
            errors.append(
                f"broker_dispatch_roundtrip_summary_{column}_missing"
            )
        if not _frame_column_matches(orders, column, expected):
            errors.append(
                f"broker_dispatch_roundtrip_orders_{column}_mismatch"
            )
        if field not in strategy_portfolio or not _same(
            strategy_portfolio.get(field),
            expected,
            field,
        ):
            errors.append(
                f"broker_dispatch_roundtrip_config_{column}_mismatch"
            )
        if column not in extra or not _same(
            extra.get(column),
            expected,
            field,
        ):
            errors.append(
                f"broker_dispatch_roundtrip_manifest_{column}_mismatch"
            )
        if (
            active
            and field
            in BROKER_DISPATCH_ACK_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
            and not _same(
                expected,
                current_ack.get(column),
                field,
            )
        ):
            errors.append(
                "broker_dispatch_roundtrip_broker_dispatch_ack_"
                f"strategy_portfolio_{field}_mismatch"
            )
    if active and not _bool(
        lineage.get(
            "strategy_portfolio_leadlag_ack_contract_consistent",
            False,
        )
    ):
        errors.append(
            "broker_dispatch_roundtrip_leadlag_ack_contract_not_consistent"
        )
    return errors


def _roundtrip_matches_expected_ack(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    expected_broker_dispatch_ack_config_path: str | Path | None,
) -> bool:
    if expected_broker_dispatch_ack_config_path is None:
        return True
    expected_path = Path(
        expected_broker_dispatch_ack_config_path
    ).resolve()
    current_path = _manifest_input_path(
        manifest,
        manifest_path,
        "ack_config",
    )
    return bool(
        current_path is not None
        and current_path.is_file()
        and current_path == expected_path
    )


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
    authorization: pd.DataFrame,
    summary: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    lineage: Mapping[str, Any],
    scaleup_fields: tuple[str, ...],
    runtime_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if authorization.empty:
        errors.append("cutover_authorization_missing_or_empty")
    if summary.empty:
        errors.append("cutover_summary_missing_or_empty")
    if not config:
        errors.append("cutover_config_missing_or_invalid")
    if not manifest:
        errors.append("cutover_manifest_missing_or_invalid")
    if errors:
        return errors

    authorization_row = authorization.iloc[0]
    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_scaleup = _mapping(config.get("scaleup_provenance"))
    for column in scaleup_fields:
        expected = lineage[column]
        for source, record in (
            ("authorization", authorization_row),
            ("summary", row),
        ):
            if column not in record.index:
                errors.append(f"cutover_{source}_{column}_missing")
            elif not _same(record.get(column), expected, column):
                errors.append(f"cutover_{source}_{column}_mismatch")
        if column not in config_scaleup:
            errors.append(f"cutover_config_{column}_missing")
        elif not _same(config_scaleup.get(column), expected, column):
            errors.append(f"cutover_config_{column}_mismatch")
        if column not in extra:
            errors.append(f"cutover_manifest_{column}_missing")
        elif not _same(extra.get(column), expected, column):
            errors.append(f"cutover_manifest_{column}_mismatch")

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
    errors.extend(
        _route_enable_leadlag_contract_errors(
            row=row,
            packet_row=packet_row,
            config=config,
            extra=extra,
            lineage=lineage,
        )
    )
    if not _same(config.get("route_enabled"), row.get("ready"), "ready"):
        errors.append("route_enable_config_ready_mismatch")
    if not _same(packet_row.get("route_enabled"), row.get("ready"), "ready"):
        errors.append("route_enable_packet_ready_mismatch")
    if not _same(extra.get("ready"), row.get("ready"), "ready"):
        errors.append("route_enable_manifest_ready_mismatch")
    return errors


def _empty_strategy_portfolio_leadlag_fields() -> dict[str, Any]:
    fields: dict[str, Any] = {
        "strategy_portfolio_leadlag_edge_lineage_required": False,
        "strategy_portfolio_leadlag_edge_lineage_matches_scaleup": False,
        "strategy_portfolio_leadlag_cutover_contract_consistent": False,
    }
    fields.update(
        {
            f"strategy_portfolio_{field}": False
            for field in LEADLAG_LINEAGE_BOOLEAN_FIELDS
        }
    )
    fields.update(
        {
            f"strategy_portfolio_{field}": 0
            for field in LEADLAG_LINEAGE_INTEGER_FIELDS
        }
    )
    fields.update(
        {
            f"strategy_portfolio_{field}": ""
            for field in LEADLAG_LINEAGE_TEXT_FIELDS
        }
    )
    fields.update(
        {
            f"strategy_portfolio_{field}": 0.0
            for field in LEADLAG_LINEAGE_NUMERIC_FIELDS
        }
    )
    return fields


def _route_enable_strategy_portfolio_leadlag_state(
    row: pd.Series,
) -> dict[str, Any]:
    return {
        "strategy_portfolio_leadlag_edge_lineage_required": _bool(
            row.get("strategy_portfolio_leadlag_edge_lineage_required", False)
        ),
        **leadlag_lineage_fields(
            row,
            source_prefix="strategy_portfolio_",
            target_prefix="strategy_portfolio_",
        ),
        "strategy_portfolio_leadlag_edge_lineage_matches_scaleup": _bool(
            row.get(
                "strategy_portfolio_leadlag_edge_lineage_matches_scaleup",
                False,
            )
        ),
        "strategy_portfolio_leadlag_cutover_contract_consistent": _bool(
            row.get(
                "strategy_portfolio_leadlag_cutover_contract_consistent",
                False,
            )
        ),
    }


def _route_enable_leadlag_contract_errors(
    *,
    row: pd.Series,
    packet_row: pd.Series,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> list[str]:
    strategy_portfolio = _mapping(config.get("strategy_portfolio"))
    summary_profile = _text(row.get("strategy_portfolio_selected_profile")).lower()
    packet_profile = _text(packet_row.get("strategy_portfolio_selected_profile")).lower()
    config_profile = _text(strategy_portfolio.get("selected_profile")).lower()
    active = bool(
        "leadlag" in {summary_profile, packet_profile, config_profile}
        or _bool(
            lineage.get(
                "strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(strategy_portfolio.get("leadlag_edge_lineage_required", False))
        or _bool(
            packet_row.get(
                "strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
    )
    if not active:
        return []

    errors: list[str] = []
    if packet_profile != summary_profile:
        errors.append("route_enable_packet_strategy_portfolio_profile_mismatch")
    if config_profile != summary_profile:
        errors.append("route_enable_config_strategy_portfolio_profile_mismatch")
    for field in ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
        summary_column = f"strategy_portfolio_{field}"
        expected = lineage[summary_column]
        if not _same(packet_row.get(summary_column), expected, field):
            errors.append(f"route_enable_packet_strategy_portfolio_{field}_mismatch")
        if not _same(strategy_portfolio.get(field), expected, field):
            errors.append(f"route_enable_config_strategy_portfolio_{field}_mismatch")
        if not _same(extra.get(summary_column), expected, field):
            errors.append(f"route_enable_manifest_strategy_portfolio_{field}_mismatch")
    return errors


def _empty_broker_dispatch_leadlag_fields() -> dict[str, Any]:
    fields = _empty_strategy_portfolio_leadlag_fields()
    fields["strategy_portfolio_leadlag_route_contract_consistent"] = False
    return fields


def _broker_dispatch_strategy_portfolio_leadlag_state(
    row: pd.Series,
) -> dict[str, Any]:
    fields = _route_enable_strategy_portfolio_leadlag_state(row)
    fields["strategy_portfolio_leadlag_route_contract_consistent"] = _bool(
        row.get(
            "strategy_portfolio_leadlag_route_contract_consistent",
            False,
        )
    )
    return fields


def _empty_broker_dispatch_send_leadlag_fields() -> dict[str, Any]:
    fields = _empty_broker_dispatch_leadlag_fields()
    fields[
        "strategy_portfolio_leadlag_dispatch_contract_consistent"
    ] = False
    return fields


def _broker_dispatch_send_strategy_portfolio_leadlag_state(
    row: pd.Series,
) -> dict[str, Any]:
    fields = _broker_dispatch_strategy_portfolio_leadlag_state(row)
    fields[
        "strategy_portfolio_leadlag_dispatch_contract_consistent"
    ] = _bool(
        row.get(
            "strategy_portfolio_leadlag_dispatch_contract_consistent",
            False,
        )
    )
    return fields


def _empty_broker_dispatch_ack_leadlag_fields() -> dict[str, Any]:
    fields = _empty_broker_dispatch_send_leadlag_fields()
    fields["strategy_portfolio_leadlag_send_contract_consistent"] = False
    return fields


def _broker_dispatch_ack_strategy_portfolio_leadlag_state(
    row: pd.Series,
) -> dict[str, Any]:
    fields = _broker_dispatch_send_strategy_portfolio_leadlag_state(row)
    fields["strategy_portfolio_leadlag_send_contract_consistent"] = _bool(
        row.get(
            "strategy_portfolio_leadlag_send_contract_consistent",
            False,
        )
    )
    return fields


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
    errors.extend(
        _broker_dispatch_leadlag_contract_errors(
            row=row,
            orders=orders,
            config=config,
            extra=extra,
            lineage=lineage,
        )
    )

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
    errors.extend(
        _broker_dispatch_contract_identity_errors(
            row=row,
            orders=orders,
            config=config,
            extra=extra,
        )
    )
    return errors


def _broker_dispatch_contract_identity_errors(
    *,
    row: pd.Series,
    orders: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
) -> list[str]:
    upload = _mapping(config.get("upload"))
    identity = _mapping(upload.get("contract_identity"))
    all_columns_present = all(
        dispatch_column in orders.columns
        for dispatch_column, _request_column in (
            BROKER_DISPATCH_CONTRACT_IDENTITY_COLUMNS
        )
    )
    active = bool(
        _bool(row.get("upload_contract_identity_active"))
        or _bool(identity.get("active"))
        or _bool(extra.get("upload_contract_identity_active"))
        or all_columns_present
    )
    if not active:
        return []

    errors: list[str] = []
    boolean_fields = {
        "active": "upload_contract_identity_active",
        "required": "upload_contract_identity_required",
        "provided": "upload_contract_identity_provided",
        "token_required": "upload_contract_identity_token_required",
        "gate_required": "upload_contract_identity_gate_required",
        "proof_required": "upload_contract_identity_proof_required",
        "adapter_matches_route": "upload_contract_identity_adapter_matches_route",
        "manifest_current": "upload_contract_identity_manifest_current",
        "artifacts_consistent": "upload_contract_identity_artifacts_consistent",
        "upload_file_bound": "upload_contract_identity_upload_file_bound",
        "sidecar_present": "upload_contract_identity_present",
        "upload_ids_match": "upload_contract_identity_upload_ids_match",
        "gate_passed": "upload_contract_identity_gate_passed",
    }
    integer_fields = {
        "orders": "upload_contract_identity_orders",
        "ready_orders": "upload_contract_identity_ready_orders",
        "research_id_orders": "upload_contract_identity_research_id_orders",
        "broker_id_orders": "upload_contract_identity_broker_id_orders",
        "token_orders": "upload_contract_identity_token_orders",
    }
    text_fields = {
        "adapter": "upload_contract_identity_adapter",
        "sidecar_sha256": "upload_contract_identity_sha256",
        "manifest_sha256": "upload_pack_manifest_sha256",
        "consistency_error": "upload_contract_identity_consistency_error",
    }
    for config_field, summary_field in boolean_fields.items():
        if _bool(identity.get(config_field)) != _bool(row.get(summary_field)):
            errors.append(
                f"broker_dispatch_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in integer_fields.items():
        if _integer(identity.get(config_field)) != _integer(
            row.get(summary_field)
        ):
            errors.append(
                f"broker_dispatch_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in text_fields.items():
        if not _same_text(identity.get(config_field), row.get(summary_field)):
            errors.append(
                f"broker_dispatch_config_{summary_field}_mismatch"
            )

    for field in (
        "upload_contract_identity_active",
        "upload_contract_identity_gate_passed",
    ):
        if _bool(extra.get(field)) != _bool(row.get(field)):
            errors.append(f"broker_dispatch_manifest_{field}_mismatch")
    for field in (
        "upload_contract_identity_sha256",
        "upload_pack_manifest_sha256",
    ):
        if not _same_text(extra.get(field), row.get(field)):
            errors.append(f"broker_dispatch_manifest_{field}_mismatch")

    if not all_columns_present:
        errors.append("broker_dispatch_orders_contract_identity_columns_missing")
        return errors
    records = _dispatch_contract_identity_records(orders)
    order_count = len(orders)
    if len(records) != order_count:
        errors.append("broker_dispatch_orders_contract_identity_count_mismatch")
        return errors
    if [
        record["contract_identity_row_number"] for record in records
    ] != list(range(order_count)):
        errors.append("broker_dispatch_orders_contract_identity_row_number_mismatch")
    ready_orders = sum(
        bool(record["resolution_row_ready"]) for record in records
    )
    token_orders = sum(
        bool(record["broker_instrument_token"]) for record in records
    )
    if _integer(row.get("upload_contract_identity_orders")) != order_count:
        errors.append("broker_dispatch_summary_contract_identity_order_count_mismatch")
    if (
        _integer(row.get("upload_contract_identity_ready_orders"))
        != ready_orders
    ):
        errors.append("broker_dispatch_summary_contract_identity_ready_count_mismatch")
    if (
        _integer(row.get("upload_contract_identity_token_orders"))
        != token_orders
    ):
        errors.append("broker_dispatch_summary_contract_identity_token_count_mismatch")
    if not _bool(row.get("upload_contract_identity_gate_passed")):
        errors.append("broker_dispatch_contract_identity_gate_failed")
    return errors


def _broker_dispatch_send_contract_identity_errors(
    *,
    row: pd.Series,
    requests: pd.DataFrame,
    expected_acks: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
) -> list[str]:
    identity = _mapping(config.get("contract_identity"))
    request_columns_present = all(
        column in requests.columns
        for column in BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
    )
    ack_columns_present = all(
        column in expected_acks.columns
        for column in BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
    )
    active = bool(
        _bool(row.get("send_contract_identity_active"))
        or _bool(identity.get("active"))
        or _bool(extra.get("send_contract_identity_active"))
        or request_columns_present
        or ack_columns_present
    )
    if not active:
        return []

    errors: list[str] = []
    boolean_fields = {
        "active": "send_contract_identity_active",
        "required": "send_contract_identity_required",
        "provided": "send_contract_identity_provided",
        "token_required": "send_contract_identity_token_required",
        "gate_required": "send_contract_identity_gate_required",
        "proof_required": "send_contract_identity_proof_required",
        "dispatch_gate_passed": "send_contract_identity_dispatch_gate_passed",
        "source_present": "send_contract_identity_source_present",
        "source_manifest_current": (
            "send_contract_identity_source_manifest_current"
        ),
        "source_artifacts_consistent": (
            "send_contract_identity_source_artifacts_consistent"
        ),
        "source_matches_dispatch": (
            "send_contract_identity_source_matches_dispatch"
        ),
        "proof_hashes_match": "send_contract_identity_proof_hashes_match",
        "adapter_matches": "send_contract_identity_adapter_matches",
        "requests_match_dispatch": (
            "send_contract_identity_requests_match_dispatch"
        ),
        "payloads_match_requests": (
            "send_contract_identity_payloads_match_requests"
        ),
        "vendor_order_isolated": (
            "send_contract_identity_vendor_order_isolated"
        ),
        "expected_acks_match_requests": (
            "send_contract_identity_expected_acks_match_requests"
        ),
        "gate_passed": "send_contract_identity_gate_passed",
    }
    integer_fields = {
        "dispatch_orders": "send_contract_identity_dispatch_orders",
        "ready_orders": "send_contract_identity_ready_orders",
        "token_orders": "send_contract_identity_token_orders",
        "request_orders": "send_contract_identity_request_orders",
        "expected_ack_orders": "send_contract_identity_expected_ack_orders",
    }
    text_fields = {
        "identity_sha256": "send_contract_identity_sha256",
        "source_identity_sha256": "send_contract_identity_source_sha256",
        "source_manifest_sha256": (
            "send_contract_identity_source_manifest_sha256"
        ),
        "consistency_error": "send_contract_identity_consistency_error",
    }
    for config_field, summary_field in boolean_fields.items():
        if _bool(identity.get(config_field)) != _bool(row.get(summary_field)):
            errors.append(
                f"broker_dispatch_send_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in integer_fields.items():
        if _integer(identity.get(config_field)) != _integer(
            row.get(summary_field)
        ):
            errors.append(
                f"broker_dispatch_send_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in text_fields.items():
        if not _same_text(identity.get(config_field), row.get(summary_field)):
            errors.append(
                f"broker_dispatch_send_config_{summary_field}_mismatch"
            )

    for field in (
        "send_contract_identity_active",
        "send_contract_identity_gate_passed",
    ):
        if _bool(extra.get(field)) != _bool(row.get(field)):
            errors.append(f"broker_dispatch_send_manifest_{field}_mismatch")
    for field in (
        "send_contract_identity_sha256",
        "send_contract_identity_source_sha256",
        "send_contract_identity_source_manifest_sha256",
    ):
        if not _same_text(extra.get(field), row.get(field)):
            errors.append(f"broker_dispatch_send_manifest_{field}_mismatch")

    if not request_columns_present:
        errors.append("broker_dispatch_send_request_identity_columns_missing")
        return errors
    if not ack_columns_present:
        errors.append("broker_dispatch_send_expected_ack_identity_columns_missing")
        return errors
    request_records = _send_contract_identity_records(requests)
    ack_records = _send_contract_identity_records(expected_acks)
    if request_records != ack_records:
        errors.append("broker_dispatch_send_expected_ack_identity_mismatch")
    payload_records = _request_payload_contract_identity_records(requests)
    if request_records != payload_records:
        errors.append("broker_dispatch_send_payload_identity_mismatch")
    if not _request_vendor_orders_exclude_internal_identity(requests):
        errors.append("broker_dispatch_send_vendor_order_identity_leak")
    identity_sha256 = _contract_identity_records_sha256(request_records)
    if not _same_text(
        identity_sha256,
        row.get("send_contract_identity_sha256"),
    ):
        errors.append("broker_dispatch_send_identity_sha256_mismatch")
    if _integer(row.get("send_contract_identity_request_orders")) != len(
        request_records
    ):
        errors.append("broker_dispatch_send_identity_request_count_mismatch")
    if _integer(
        row.get("send_contract_identity_expected_ack_orders")
    ) != len(ack_records):
        errors.append("broker_dispatch_send_identity_expected_ack_count_mismatch")
    if not _bool(row.get("send_contract_identity_gate_passed")):
        errors.append("broker_dispatch_send_contract_identity_gate_failed")
    return errors


def _dispatch_contract_identity_records(
    orders: pd.DataFrame,
) -> list[dict[str, Any]]:
    return [
        {
            request_column: _contract_identity_value(
                row.get(dispatch_column),
                request_column,
            )
            for dispatch_column, request_column in (
                BROKER_DISPATCH_CONTRACT_IDENTITY_COLUMNS
            )
        }
        for row in orders.to_dict(orient="records")
    ]


def broker_dispatch_contract_identity_record(
    row: Mapping[str, Any] | pd.Series,
) -> dict[str, Any]:
    return {
        column: _contract_identity_value(row.get(column), column)
        for column in BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
    }


def broker_dispatch_contract_identity_records(
    frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    return _send_contract_identity_records(frame)


def broker_dispatch_contract_identity_records_sha256(
    records: list[dict[str, Any]],
) -> str:
    return _contract_identity_records_sha256(records)


def _send_contract_identity_records(
    frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    return [
        broker_dispatch_contract_identity_record(row)
        for row in frame.to_dict(orient="records")
    ]


def _request_payload_contract_identity_records(
    requests: pd.DataFrame,
) -> list[dict[str, Any]]:
    payloads = _request_payloads(requests)
    if len(payloads) != len(requests):
        return []
    records: list[dict[str, Any]] = []
    for payload in payloads:
        identity = payload.get("contract_identity")
        if not isinstance(identity, Mapping):
            return []
        records.append(
            {
                column: _contract_identity_value(
                    identity.get(column),
                    column,
                )
                for column in (
                    BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
                )
            }
        )
    return records


def _request_vendor_orders_exclude_internal_identity(
    requests: pd.DataFrame,
) -> bool:
    internal_fields = {
        "research_instrument_id",
        "broker_instrument_id",
        "broker_instrument_token",
        "instrument_resolution_method",
        "instrument_resolution_status",
        "upload_instrument_column",
        "upload_identity_matches",
        "resolution_row_ready",
    }
    payloads = _request_payloads(requests)
    if len(payloads) != len(requests):
        return False
    return all(
        isinstance(payload.get("order"), Mapping)
        and not internal_fields.intersection(payload["order"])
        for payload in payloads
    )


def _contract_identity_records_sha256(
    records: list[dict[str, Any]],
) -> str:
    if not records:
        return ""
    return hashlib.sha256(
        json.dumps(
            records,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _contract_identity_value(value: Any, column: str) -> Any:
    if column in BROKER_DISPATCH_CONTRACT_IDENTITY_BOOLEAN_COLUMNS:
        return _bool(value)
    if column in BROKER_DISPATCH_CONTRACT_IDENTITY_INTEGER_COLUMNS:
        text = _text(value)
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else None
    return _text(value)


def _broker_dispatch_leadlag_contract_errors(
    *,
    row: pd.Series,
    orders: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> list[str]:
    strategy_portfolio = _mapping(config.get("strategy_portfolio"))
    summary_profile = _text(row.get("strategy_portfolio_selected_profile")).lower()
    config_profile = _text(strategy_portfolio.get("selected_profile")).lower()
    active = bool(
        "leadlag" in {summary_profile, config_profile}
        or _bool(
            lineage.get(
                "strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(
            lineage.get(
                "route_enable_strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(strategy_portfolio.get("leadlag_edge_lineage_required", False))
    )
    if not active:
        return []

    errors: list[str] = []
    if config_profile != summary_profile:
        errors.append("broker_dispatch_config_strategy_portfolio_profile_mismatch")
    for field in BROKER_DISPATCH_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
        summary_column = f"strategy_portfolio_{field}"
        expected = lineage[summary_column]
        if not _frame_column_matches(orders, summary_column, expected):
            errors.append(f"broker_dispatch_orders_strategy_portfolio_{field}_mismatch")
        if not _same(strategy_portfolio.get(field), expected, field):
            errors.append(f"broker_dispatch_config_strategy_portfolio_{field}_mismatch")
        if not _same(extra.get(summary_column), expected, field):
            errors.append(f"broker_dispatch_manifest_strategy_portfolio_{field}_mismatch")
        if field in ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
            route_value = lineage.get(
                f"route_enable_strategy_portfolio_{field}"
            )
            if not _same(expected, route_value, field):
                errors.append(
                    f"broker_dispatch_route_enable_strategy_portfolio_{field}_mismatch"
                )
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
    errors.extend(
        _broker_dispatch_send_leadlag_contract_errors(
            row=row,
            requests=requests,
            expected_acks=expected_acks,
            config=config,
            extra=extra,
            lineage=lineage,
        )
    )

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
    errors.extend(
        _broker_dispatch_send_contract_identity_errors(
            row=row,
            requests=requests,
            expected_acks=expected_acks,
            config=config,
            extra=extra,
        )
    )
    return errors


def _broker_dispatch_send_leadlag_contract_errors(
    *,
    row: pd.Series,
    requests: pd.DataFrame,
    expected_acks: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> list[str]:
    strategy_portfolio = _mapping(config.get("strategy_portfolio"))
    summary_profile = _text(row.get("strategy_portfolio_selected_profile")).lower()
    config_profile = _text(strategy_portfolio.get("selected_profile")).lower()
    active = bool(
        "leadlag" in {summary_profile, config_profile}
        or _bool(
            lineage.get(
                "strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(
            lineage.get(
                "broker_dispatch_strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(strategy_portfolio.get("leadlag_edge_lineage_required", False))
    )
    if not active:
        return []

    errors: list[str] = []
    if config_profile != summary_profile:
        errors.append(
            "broker_dispatch_send_config_strategy_portfolio_profile_mismatch"
        )
    for field in BROKER_DISPATCH_SEND_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
        summary_column = f"strategy_portfolio_{field}"
        expected = lineage[summary_column]
        if not _frame_column_matches(requests, summary_column, expected):
            errors.append(
                f"broker_dispatch_send_requests_strategy_portfolio_{field}_mismatch"
            )
        if not _request_payload_field_matches(
            requests,
            summary_column,
            expected,
        ):
            errors.append(
                f"broker_dispatch_send_payload_strategy_portfolio_{field}_mismatch"
            )
        if not _frame_column_matches(expected_acks, summary_column, expected):
            errors.append(
                f"broker_dispatch_send_expected_acks_strategy_portfolio_{field}_mismatch"
            )
        if not _same(strategy_portfolio.get(field), expected, field):
            errors.append(
                f"broker_dispatch_send_config_strategy_portfolio_{field}_mismatch"
            )
        if not _same(extra.get(summary_column), expected, field):
            errors.append(
                f"broker_dispatch_send_manifest_strategy_portfolio_{field}_mismatch"
            )
        if field in BROKER_DISPATCH_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
            dispatch_value = lineage.get(
                f"broker_dispatch_strategy_portfolio_{field}"
            )
            if not _same(expected, dispatch_value, field):
                errors.append(
                    f"broker_dispatch_send_broker_dispatch_strategy_portfolio_{field}_mismatch"
                )
    return errors


def _broker_dispatch_ack_contract_errors(
    *,
    summary: pd.DataFrame,
    acknowledgements: pd.DataFrame,
    unmatched: pd.DataFrame,
    checks: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    lineage: Mapping[str, Any],
    send_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        errors.append("broker_dispatch_ack_summary_missing_or_empty")
    if acknowledgements.empty:
        errors.append("broker_dispatch_acknowledgements_missing_or_empty")
    if checks.empty:
        errors.append("broker_dispatch_ack_checks_missing_or_empty")
    if not config:
        errors.append("broker_dispatch_ack_config_missing_or_invalid")
    if not manifest:
        errors.append("broker_dispatch_ack_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    extra = _mapping(manifest.get("extra"))
    config_lineage = _mapping(config.get("broker_dispatch_send_lineage"))
    for column in send_fields:
        expected = lineage[column]
        if not _frame_column_matches(acknowledgements, column, expected):
            errors.append(f"broker_dispatch_ack_rows_{column}_mismatch")
        if column not in config_lineage or not _same(
            config_lineage.get(column), expected, column
        ):
            errors.append(f"broker_dispatch_ack_config_{column}_mismatch")
        if column not in extra or not _same(
            extra.get(column), expected, column
        ):
            errors.append(f"broker_dispatch_ack_manifest_{column}_mismatch")
    errors.extend(
        _broker_dispatch_ack_leadlag_contract_errors(
            row=row,
            acknowledgements=acknowledgements,
            config=config,
            extra=extra,
            lineage=lineage,
        )
    )
    errors.extend(
        _broker_dispatch_ack_contract_identity_errors(
            row=row,
            acknowledgements=acknowledgements,
            config=config,
            extra=extra,
            manifest=manifest,
            manifest_path=manifest_path,
        )
    )

    for column in (
        "target_mode",
        "strategy",
        "market",
        "scenario_key",
        "adapter",
    ):
        expected = row.get(column)
        if column not in row.index or column not in config or not _same_text(
            config.get(column), expected
        ):
            errors.append(f"broker_dispatch_ack_config_{column}_mismatch")
    if "passed" not in config or not _same(
        config.get("passed"), row.get("passed"), "passed"
    ):
        errors.append("broker_dispatch_ack_config_passed_mismatch")
    if "passed" not in extra or not _same(
        extra.get("passed"), row.get("passed"), "passed"
    ):
        errors.append("broker_dispatch_ack_manifest_passed_mismatch")
    errors.extend(
        _broker_dispatch_ack_count_contract_errors(
            row=row,
            acknowledgements=acknowledgements,
            unmatched=unmatched,
            checks=checks,
            config=config,
        )
    )
    return errors


def _broker_dispatch_ack_contract_identity_errors(
    *,
    row: pd.Series,
    acknowledgements: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_path: Path,
) -> list[str]:
    identity = _mapping(config.get("contract_identity"))
    columns_present = all(
        column in acknowledgements.columns
        for column in BROKER_DISPATCH_SEND_CONTRACT_IDENTITY_COLUMNS
    )
    active = bool(
        _bool(row.get("ack_contract_identity_active"))
        or _bool(identity.get("active"))
        or _bool(extra.get("ack_contract_identity_active"))
        or columns_present
    )
    if not active:
        return []

    errors: list[str] = []
    boolean_fields = {
        "active": "ack_contract_identity_active",
        "required": "ack_contract_identity_required",
        "send_gate_passed": "ack_contract_identity_send_gate_passed",
        "expected_columns_present": (
            "ack_contract_identity_expected_columns_present"
        ),
        "broker_columns_present": (
            "ack_contract_identity_broker_columns_present"
        ),
        "expected_matches_send": (
            "ack_contract_identity_expected_matches_send"
        ),
        "broker_acks_match_expected": (
            "ack_contract_identity_broker_acks_match_expected"
        ),
        "reconciled_matches_expected": (
            "ack_contract_identity_reconciled_matches_expected"
        ),
        "gate_passed": "ack_contract_identity_gate_passed",
    }
    integer_fields = {
        "expected_orders": "ack_contract_identity_expected_orders",
        "broker_ack_orders": "ack_contract_identity_broker_ack_orders",
        "reconciled_orders": "ack_contract_identity_reconciled_orders",
    }
    text_fields = {
        "identity_sha256": "ack_contract_identity_sha256",
        "consistency_error": "ack_contract_identity_consistency_error",
    }
    for config_field, summary_field in boolean_fields.items():
        if _bool(identity.get(config_field)) != _bool(row.get(summary_field)):
            errors.append(
                f"broker_dispatch_ack_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in integer_fields.items():
        if _integer(identity.get(config_field)) != _integer(
            row.get(summary_field)
        ):
            errors.append(
                f"broker_dispatch_ack_config_{summary_field}_mismatch"
            )
    for config_field, summary_field in text_fields.items():
        if not _same_text(identity.get(config_field), row.get(summary_field)):
            errors.append(
                f"broker_dispatch_ack_config_{summary_field}_mismatch"
            )

    for field in (
        "ack_contract_identity_active",
        "ack_contract_identity_gate_passed",
    ):
        if _bool(extra.get(field)) != _bool(row.get(field)):
            errors.append(f"broker_dispatch_ack_manifest_{field}_mismatch")
    if not _same_text(
        extra.get("ack_contract_identity_sha256"),
        row.get("ack_contract_identity_sha256"),
    ):
        errors.append(
            "broker_dispatch_ack_manifest_ack_contract_identity_sha256_mismatch"
        )

    all_fields = (
        *boolean_fields.values(),
        *integer_fields.values(),
        *text_fields.values(),
    )
    for field in all_fields:
        if not _frame_column_matches(
            acknowledgements,
            field,
            row.get(field),
        ):
            errors.append(f"broker_dispatch_ack_rows_{field}_mismatch")

    if not columns_present:
        errors.append("broker_dispatch_ack_contract_identity_columns_missing")
        return errors
    output_records = broker_dispatch_contract_identity_records(
        acknowledgements
    )
    output_sha256 = broker_dispatch_contract_identity_records_sha256(
        output_records
    )
    if not _same_text(
        row.get("ack_contract_identity_sha256"),
        output_sha256,
    ):
        errors.append("broker_dispatch_ack_contract_identity_digest_mismatch")
    if _integer(row.get("ack_contract_identity_reconciled_orders")) != len(
        output_records
    ):
        errors.append(
            "broker_dispatch_ack_contract_identity_reconciled_count_mismatch"
        )

    expected_path = _manifest_input_path(
        manifest,
        manifest_path,
        "send_expected_acks",
    )
    broker_acks_path = _manifest_input_path(
        manifest,
        manifest_path,
        "broker_acks",
    )
    expected_acks = (
        _read_csv_text(expected_path)
        if expected_path is not None
        else pd.DataFrame()
    )
    broker_acks = (
        _read_csv_text(broker_acks_path)
        if broker_acks_path is not None
        else pd.DataFrame()
    )
    if expected_acks.empty:
        errors.append(
            "broker_dispatch_ack_expected_identity_source_missing"
        )
    if broker_acks.empty:
        errors.append("broker_dispatch_ack_broker_identity_source_missing")
    if not expected_acks.empty and not broker_acks.empty:
        if not _ack_contract_identity_sources_match(
            acknowledgements=acknowledgements,
            expected_acks=expected_acks,
            broker_acks=broker_acks,
        ):
            errors.append(
                "broker_dispatch_ack_contract_identity_source_mismatch"
            )
    if not _bool(row.get("ack_contract_identity_gate_passed")):
        errors.append("broker_dispatch_ack_contract_identity_gate_failed")
    return errors


def _ack_contract_identity_sources_match(
    *,
    acknowledgements: pd.DataFrame,
    expected_acks: pd.DataFrame,
    broker_acks: pd.DataFrame,
) -> bool:
    if len(expected_acks) != len(acknowledgements):
        return False
    for output in acknowledgements.to_dict(orient="records"):
        expected = _matching_identity_rows(expected_acks, output)
        actual = _matching_identity_rows(broker_acks, output)
        if len(expected) != 1 or actual.empty:
            return False
        expected_record = broker_dispatch_contract_identity_record(
            expected.iloc[0]
        )
        if broker_dispatch_contract_identity_record(output) != expected_record:
            return False
        if any(
            broker_dispatch_contract_identity_record(actual_row)
            != expected_record
            for _index, actual_row in actual.iterrows()
        ):
            return False
    return True


def _matching_identity_rows(
    frame: pd.DataFrame,
    row: Mapping[str, Any] | pd.Series,
) -> pd.DataFrame:
    for column in ("dispatch_order_id", "source_order_id"):
        value = _text(row.get(column))
        if value and column in frame.columns:
            matches = frame.loc[frame[column].map(_text) == value]
            if not matches.empty:
                return matches.reset_index(drop=True)
    return frame.iloc[:0].copy()


def _broker_dispatch_ack_leadlag_contract_errors(
    *,
    row: pd.Series,
    acknowledgements: pd.DataFrame,
    config: Mapping[str, Any],
    extra: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> list[str]:
    strategy_portfolio = _mapping(config.get("strategy_portfolio"))
    summary_profile = _text(
        row.get("strategy_portfolio_selected_profile")
    ).lower()
    config_profile = _text(strategy_portfolio.get("selected_profile")).lower()
    active = bool(
        "leadlag" in {summary_profile, config_profile}
        or _bool(
            lineage.get(
                "strategy_portfolio_leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(
            lineage.get(
                "broker_dispatch_send_strategy_portfolio_"
                "leadlag_edge_lineage_required",
                False,
            )
        )
        or _bool(strategy_portfolio.get("leadlag_edge_lineage_required", False))
    )
    if not active:
        return []

    errors: list[str] = []
    if config_profile != summary_profile:
        errors.append(
            "broker_dispatch_ack_config_strategy_portfolio_profile_mismatch"
        )
    for field in BROKER_DISPATCH_ACK_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
        summary_column = f"strategy_portfolio_{field}"
        expected = lineage[summary_column]
        if not _frame_column_matches(
            acknowledgements,
            summary_column,
            expected,
        ):
            errors.append(
                f"broker_dispatch_ack_rows_strategy_portfolio_{field}_mismatch"
            )
        if not _same(strategy_portfolio.get(field), expected, field):
            errors.append(
                f"broker_dispatch_ack_config_strategy_portfolio_{field}_mismatch"
            )
        if not _same(extra.get(summary_column), expected, field):
            errors.append(
                f"broker_dispatch_ack_manifest_strategy_portfolio_{field}_mismatch"
            )
        if field in BROKER_DISPATCH_SEND_STRATEGY_PORTFOLIO_LEADLAG_FIELDS:
            send_value = lineage.get(
                f"broker_dispatch_send_strategy_portfolio_{field}"
            )
            if not _same(expected, send_value, field):
                errors.append(
                    "broker_dispatch_ack_broker_dispatch_send_"
                    f"strategy_portfolio_{field}_mismatch"
                )
    return errors


def _broker_dispatch_ack_count_contract_errors(
    *,
    row: pd.Series,
    acknowledgements: pd.DataFrame,
    unmatched: pd.DataFrame,
    checks: pd.DataFrame,
    config: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    required_columns = {
        "dispatch_order_id",
        "acked",
        "missing_ack",
        "rejected",
        "duplicate_ack",
    }
    if not required_columns.issubset(acknowledgements.columns):
        return ["broker_dispatch_ack_row_contract_missing"]
    if acknowledgements["dispatch_order_id"].map(_text).eq("").any():
        errors.append("broker_dispatch_ack_dispatch_order_id_missing")
    if acknowledgements["dispatch_order_id"].map(_text).duplicated().any():
        errors.append("broker_dispatch_ack_dispatch_order_id_duplicate")

    derived = {
        "dispatch_orders": len(acknowledgements),
        "acked_orders": int(acknowledgements["acked"].map(_bool).sum()),
        "missing_acks": int(acknowledgements["missing_ack"].map(_bool).sum()),
        "rejected_orders": int(acknowledgements["rejected"].map(_bool).sum()),
        "duplicate_ack_orders": int(
            acknowledgements["duplicate_ack"].map(_bool).sum()
        ),
        "unmatched_acks": len(unmatched),
    }
    for column, expected in derived.items():
        if column not in row.index or _integer(row.get(column)) != expected:
            errors.append(f"broker_dispatch_ack_summary_{column}_mismatch")
        if column not in config or _integer(config.get(column)) != expected:
            errors.append(f"broker_dispatch_ack_config_{column}_mismatch")

    if "passed" not in checks.columns:
        errors.append("broker_dispatch_ack_checks_passed_missing")
        return errors
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    checks_passed = failed_checks == 0
    if _bool(row.get("passed")) != checks_passed:
        errors.append("broker_dispatch_ack_summary_checks_mismatch")
    if (
        "failed_check_count" not in row.index
        or _integer(row.get("failed_check_count")) != failed_checks
    ):
        errors.append("broker_dispatch_ack_summary_failed_check_count_mismatch")
    if (
        "failed_check_count" not in config
        or _integer(config.get("failed_check_count")) != failed_checks
    ):
        errors.append("broker_dispatch_ack_config_failed_check_count_mismatch")
    return errors


def _roundtrip_current_broker_dispatch_ack_lineage_state(
    *,
    lineage: Mapping[str, Any],
    ack_fields: tuple[str, ...],
    current_ack: Mapping[str, Any],
    current_ack_fields: Mapping[str, Any],
    source_bound: bool,
) -> dict[str, Any]:
    identity_fields = tuple(
        column for column in ack_fields if "contract_identity" in column
    )
    carried_identity_active = bool(
        any(
            _bool(lineage.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(lineage.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    current_identity_active = bool(
        _bool(
            current_ack_fields.get(
                "broker_dispatch_ack_send_route_contract_identity_active",
                False,
            )
        )
        or any(
            _bool(current_ack_fields.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(current_ack_fields.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    contract_identity_active = bool(
        carried_identity_active or current_identity_active
    )
    current_identity_sha256 = _text(
        current_ack_fields.get(
            "broker_dispatch_ack_current_send_route_contract_identity_sha256",
            "",
        )
    )
    carried_identity_sha256 = _text(
        lineage.get(
            BROKER_DISPATCH_ACK_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            source_bound
            and current_ack.get("gate_passed", False)
            and current_identity_active
            and carried_identity_sha256
            and current_identity_sha256
            and carried_identity_sha256 == current_identity_sha256
            and all(
                _same(
                    lineage.get(column),
                    current_ack_fields.get(column),
                    column,
                )
                for column in identity_fields
            )
        )
    )
    ack_matches_current = bool(
        source_bound
        and current_ack.get("gate_passed", False)
        and all(
            _same(
                lineage.get(column),
                current_ack_fields.get(column),
                column,
            )
            for column in ack_fields
        )
    )
    return {
        "ack_matches_current": ack_matches_current,
        "ack_route_contract_identity_active": contract_identity_active,
        "current_ack_route_contract_identity_sha256": (
            current_identity_sha256
        ),
        "ack_route_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
    }


def _ack_current_broker_dispatch_send_lineage_state(
    *,
    ack_manifest: Mapping[str, Any],
    ack_manifest_path: Path,
    lineage: Mapping[str, Any],
    send_fields: tuple[str, ...],
    expected_broker_dispatch_config_path: str | Path | None,
) -> dict[str, Any]:
    identity_fields = tuple(
        column for column in send_fields if "contract_identity" in column
    )
    carried_identity_active = bool(
        any(
            _bool(lineage.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(lineage.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    send_manifest_path = _manifest_input_path(
        ack_manifest,
        ack_manifest_path,
        "broker_dispatch_send_manifest",
    ) or _manifest_input_path(
        ack_manifest,
        ack_manifest_path,
        "send_manifest",
    )
    send_config_path = (
        send_manifest_path.with_name("broker_dispatch_send_config.json")
        if send_manifest_path is not None
        else None
    )
    source_bound = bool(
        send_manifest_path is not None
        and send_manifest_path.is_file()
        and send_config_path is not None
        and send_config_path.is_file()
    )
    current = empty_broker_dispatch_send_lineage(required=True)
    if source_bound and send_config_path is not None:
        current = load_broker_dispatch_send_lineage(
            send_config_path,
            expected_broker_dispatch_config_path=(
                expected_broker_dispatch_config_path
            ),
        )
    current_fields = broker_dispatch_send_lineage_fields(current)
    current_identity_active = bool(
        _bool(
            current_fields.get(
                (
                    "broker_dispatch_send_dispatch_route_"
                    "contract_identity_active"
                ),
                False,
            )
        )
        or any(
            _bool(current_fields.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(current_fields.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    contract_identity_active = bool(
        carried_identity_active or current_identity_active
    )
    current_identity_sha256 = _text(
        current_fields.get(
            (
                "broker_dispatch_send_current_dispatch_route_"
                "contract_identity_sha256"
            ),
            "",
        )
    )
    carried_identity_sha256 = _text(
        lineage.get(
            (
                "broker_dispatch_send_broker_dispatch_route_enable_"
                "cutover_runtime_telemetry_broker_readiness_"
                "roundtrip_contract_identity_sha256"
            ),
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            source_bound
            and current.get("gate_passed", False)
            and current_identity_active
            and carried_identity_sha256
            and current_identity_sha256
            and carried_identity_sha256 == current_identity_sha256
            and all(
                _same(
                    lineage.get(column),
                    current_fields.get(column),
                    column,
                )
                for column in identity_fields
            )
        )
    )
    send_matches_current = bool(
        source_bound
        and current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in send_fields
        )
    )
    return {
        "send_matches_current": send_matches_current,
        "send_route_contract_identity_active": (
            contract_identity_active
        ),
        "current_send_route_contract_identity_sha256": (
            current_identity_sha256
        ),
        "send_route_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
    }


def _ack_matches_expected_send(
    *,
    lineage: Mapping[str, Any],
    expected_broker_dispatch_send_config_path: str | Path | None,
) -> bool:
    if expected_broker_dispatch_send_config_path is None:
        return True
    expected_config_path = Path(
        expected_broker_dispatch_send_config_path
    ).resolve()
    expected_manifest_path = expected_config_path.with_name("manifest.json")
    if not expected_config_path.is_file() or not expected_manifest_path.is_file():
        return False
    return bool(
        _same_text(
            lineage.get("broker_dispatch_send_manifest_path"),
            str(expected_manifest_path),
        )
        and _same_text(
            lineage.get("broker_dispatch_send_manifest_sha256"),
            file_sha256(expected_manifest_path),
        )
    )


def _send_current_broker_dispatch_lineage_state(
    *,
    send_manifest: Mapping[str, Any],
    send_manifest_path: Path,
    lineage: Mapping[str, Any],
    dispatch_fields: tuple[str, ...],
) -> dict[str, Any]:
    identity_fields = tuple(
        column for column in dispatch_fields if "contract_identity" in column
    )
    carried_identity_active = bool(
        any(
            _bool(lineage.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(lineage.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    dispatch_manifest_path = _manifest_input_path(
        send_manifest,
        send_manifest_path,
        "broker_dispatch_manifest",
    ) or _manifest_input_path(
        send_manifest,
        send_manifest_path,
        "dispatch_manifest",
    )
    dispatch_config_path = (
        dispatch_manifest_path.with_name("broker_dispatch_config.json")
        if dispatch_manifest_path is not None
        else None
    )
    source_bound = bool(
        dispatch_manifest_path is not None
        and dispatch_manifest_path.is_file()
        and dispatch_config_path is not None
        and dispatch_config_path.is_file()
    )
    current = empty_broker_dispatch_lineage(required=True)
    if source_bound and dispatch_config_path is not None:
        current = load_broker_dispatch_lineage(dispatch_config_path)
    current_fields = broker_dispatch_lineage_fields(current)
    current_identity_active = bool(
        _bool(
            current_fields.get(
                "broker_dispatch_route_contract_identity_active",
                False,
            )
        )
        or any(
            _bool(current_fields.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(current_fields.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    contract_identity_active = bool(
        carried_identity_active or current_identity_active
    )
    current_identity_sha256 = _text(
        current_fields.get(
            "broker_dispatch_current_route_contract_identity_sha256",
            "",
        )
    )
    carried_identity_sha256 = _text(
        lineage.get(
            (
                "broker_dispatch_route_enable_cutover_runtime_telemetry_"
                "broker_readiness_roundtrip_contract_identity_sha256"
            ),
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            source_bound
            and current.get("gate_passed", False)
            and current_identity_active
            and carried_identity_sha256
            and current_identity_sha256
            and carried_identity_sha256 == current_identity_sha256
            and all(
                _same(
                    lineage.get(column),
                    current_fields.get(column),
                    column,
                )
                for column in identity_fields
            )
        )
    )
    broker_dispatch_matches_current = bool(
        source_bound
        and current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in dispatch_fields
        )
    )
    return {
        "broker_dispatch_matches_current": broker_dispatch_matches_current,
        "dispatch_route_contract_identity_active": (
            contract_identity_active
        ),
        "current_dispatch_route_contract_identity_sha256": (
            current_identity_sha256
        ),
        "dispatch_route_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
    }


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


def _dispatch_current_route_enable_lineage_state(
    *,
    dispatch_manifest: Mapping[str, Any],
    dispatch_manifest_path: Path,
    lineage: Mapping[str, Any],
    route_fields: tuple[str, ...],
) -> dict[str, Any]:
    identity_fields = tuple(
        column for column in route_fields if "contract_identity" in column
    )
    carried_identity_active = bool(
        any(
            _bool(lineage.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(lineage.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    route_manifest_path = _manifest_input_path(
        dispatch_manifest,
        dispatch_manifest_path,
        "route_enable_manifest",
    )
    route_enable_config_path = (
        route_manifest_path.with_name("route_enable_config.json")
        if route_manifest_path is not None
        else None
    )
    source_bound = bool(
        route_manifest_path is not None
        and route_manifest_path.is_file()
        and route_enable_config_path is not None
        and route_enable_config_path.is_file()
    )
    current = empty_route_enable_lineage(required=True)
    if source_bound and route_enable_config_path is not None:
        current = load_route_enable_lineage(route_enable_config_path)
    current_fields = route_enable_lineage_fields(current)
    current_identity_active = bool(
        _bool(
            current_fields.get(
                "route_enable_cutover_contract_identity_active",
                False,
            )
        )
        or any(
            _bool(current_fields.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(current_fields.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    contract_identity_active = bool(
        carried_identity_active or current_identity_active
    )
    current_identity_sha256 = _text(
        current_fields.get(
            "route_enable_current_cutover_contract_identity_sha256",
            "",
        )
    )
    carried_identity_sha256 = _text(
        lineage.get(
            (
                "route_enable_cutover_runtime_telemetry_"
                "broker_readiness_roundtrip_contract_identity_sha256"
            ),
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            source_bound
            and current.get("gate_passed", False)
            and current_identity_active
            and carried_identity_sha256
            and current_identity_sha256
            and carried_identity_sha256 == current_identity_sha256
            and all(
                _same(
                    lineage.get(column),
                    current_fields.get(column),
                    column,
                )
                for column in identity_fields
            )
        )
    )
    route_enable_matches_current = bool(
        source_bound
        and current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in route_fields
        )
    )
    return {
        "route_enable_matches_current": route_enable_matches_current,
        "route_contract_identity_active": contract_identity_active,
        "current_route_contract_identity_sha256": (
            current_identity_sha256
        ),
        "route_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
    }


def _route_current_cutover_lineage_state(
    *,
    route_manifest: Mapping[str, Any],
    route_manifest_path: Path,
    lineage: Mapping[str, Any],
    route_fields: tuple[str, ...],
) -> dict[str, Any]:
    identity_fields = tuple(
        column for column in route_fields if "contract_identity" in column
    )
    carried_identity_active = bool(
        any(
            _bool(lineage.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(lineage.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    cutover_manifest_path = _manifest_input_path(
        route_manifest,
        route_manifest_path,
        "cutover_manifest",
    )
    cutover_config_path = (
        cutover_manifest_path.with_name("cutover_config.json")
        if cutover_manifest_path is not None
        else None
    )
    source_bound = bool(
        cutover_manifest_path is not None
        and cutover_manifest_path.is_file()
        and cutover_config_path is not None
        and cutover_config_path.is_file()
    )
    current = empty_cutover_lineage(required=True)
    if source_bound and cutover_config_path is not None:
        current = load_cutover_lineage(cutover_config_path)
    current_fields = cutover_lineage_fields(current)
    current_identity_active = bool(
        _bool(
            current_fields.get(
                "cutover_runtime_contract_identity_active",
                False,
            )
        )
        or any(
            _bool(current_fields.get(column, False))
            for column in identity_fields
            if column.endswith("_active")
        )
        or any(
            _text(current_fields.get(column, ""))
            for column in identity_fields
            if column.endswith("_sha256")
        )
    )
    contract_identity_active = bool(
        carried_identity_active or current_identity_active
    )
    current_identity_sha256 = _text(
        current_fields.get(
            "cutover_current_runtime_contract_identity_sha256",
            "",
        )
    )
    carried_identity_sha256 = _text(
        lineage.get(
            (
                "cutover_runtime_telemetry_broker_readiness_"
                "roundtrip_contract_identity_sha256"
            ),
            "",
        )
    )
    contract_identity_matches_current = bool(
        not contract_identity_active
        or (
            source_bound
            and current.get("gate_passed", False)
            and current_identity_active
            and carried_identity_sha256
            and current_identity_sha256
            and carried_identity_sha256 == current_identity_sha256
            and all(
                _same(
                    lineage.get(column),
                    current_fields.get(column),
                    column,
                )
                for column in identity_fields
            )
        )
    )
    cutover_matches_current = bool(
        source_bound
        and current.get("gate_passed", False)
        and all(
            _same(lineage.get(column), current_fields.get(column), column)
            for column in route_fields
        )
        and cutover_config_path is not None
        and _route_leadlag_matches_current_cutover(
            lineage=lineage,
            cutover_config_path=cutover_config_path,
        )
    )
    return {
        "cutover_matches_current": cutover_matches_current,
        "cutover_contract_identity_active": contract_identity_active,
        "current_cutover_contract_identity_sha256": (
            current_identity_sha256
        ),
        "cutover_contract_identity_matches_current": (
            contract_identity_matches_current
        ),
    }


def _route_leadlag_matches_current_cutover(
    *,
    lineage: Mapping[str, Any],
    cutover_config_path: Path,
) -> bool:
    if not _bool(
        lineage.get("strategy_portfolio_leadlag_edge_lineage_required", False)
    ):
        return True

    root = cutover_config_path.parent
    summary = _read_csv(root / "cutover_summary.csv")
    authorization = _read_csv(root / "cutover_authorization.csv")
    config = _read_json(cutover_config_path)
    manifest = _read_json(root / "manifest.json")
    if summary.empty or authorization.empty or not config or not manifest:
        return False

    row = summary.iloc[0]
    authorization_row = authorization.iloc[0]
    runtime_session = _mapping(config.get("runtime_session"))
    strategy_portfolio = _mapping(runtime_session.get("strategy_portfolio"))
    extra = _mapping(manifest.get("extra"))
    prefixes = ("runtime_strategy_portfolio_", "strategy_portfolio_")
    prefix = next(
        (
            candidate
            for candidate in prefixes
            if any(
                f"{candidate}{field}" in row.index
                for field in ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_SOURCE_FIELDS
            )
        ),
        prefixes[0],
    )
    if _text(row.get(f"{prefix}selected_profile")).lower() != "leadlag":
        return False
    if _text(authorization_row.get(f"{prefix}selected_profile")).lower() != "leadlag":
        return False
    if _text(strategy_portfolio.get("selected_profile")).lower() != "leadlag":
        return False

    for field in ROUTE_ENABLE_STRATEGY_PORTFOLIO_LEADLAG_SOURCE_FIELDS:
        expected = lineage[f"strategy_portfolio_{field}"]
        source_column = f"{prefix}{field}"
        if not _same(row.get(source_column), expected, field):
            return False
        if not _same(authorization_row.get(source_column), expected, field):
            return False
        if not _same(strategy_portfolio.get(field), expected, field):
            return False
        if not _same(extra.get(source_column), expected, field):
            return False
    return True


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


def _leadlag_contract_field(column: str) -> str:
    return next(
        (
            field
            for field in (
                BROKER_DISPATCH_ROUNDTRIP_STRATEGY_PORTFOLIO_LEADLAG_FIELDS
            )
            if column.endswith(field)
        ),
        "",
    )


def _field_default(column: str) -> Any:
    for provenance_column, default in SCALEUP_PROVENANCE_DEFAULTS.items():
        if column == provenance_column or column.endswith(
            f"_{provenance_column}"
        ):
            return default
    leadlag_field = _leadlag_contract_field(column)
    if leadlag_field in {
        "leadlag_edge_lineage_required",
        "leadlag_edge_lineage_matches_scaleup",
        "leadlag_cutover_contract_consistent",
        "leadlag_route_contract_consistent",
        "leadlag_dispatch_contract_consistent",
        "leadlag_send_contract_consistent",
        "leadlag_ack_contract_consistent",
        *LEADLAG_LINEAGE_BOOLEAN_FIELDS,
    }:
        return False
    if leadlag_field in LEADLAG_LINEAGE_INTEGER_FIELDS:
        return 0
    if leadlag_field in LEADLAG_LINEAGE_NUMERIC_FIELDS:
        return 0.0
    if leadlag_field in LEADLAG_LINEAGE_TEXT_FIELDS:
        return ""
    if column.endswith(("_count", "_orders")):
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
    if isinstance(default, float):
        return _number(value)
    return _text(value)


def _same(left: Any, right: Any, column: str) -> bool:
    leadlag_field = _leadlag_contract_field(column)
    if leadlag_field in LEADLAG_LINEAGE_FIELDS:
        return leadlag_lineage_field_matches(leadlag_field, left, right)
    if leadlag_field:
        return _bool(left) == _bool(right)
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


def _read_csv_text(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
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


def _number(value: Any, *, fallback: float = 0.0) -> float:
    if _missing(value):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
