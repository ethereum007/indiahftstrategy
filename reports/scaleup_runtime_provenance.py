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
from reports.proof_refresh import (
    load_proof_refresh_evidence,
    proof_refresh_evidence_record,
)
from reports.scaleup import load_strategy_portfolio_provenance


SCALEUP_REQUIRED_ARTIFACTS = (
    "scaleup_plan.csv",
    "scaleup_checks.csv",
    "scaleup_summary.csv",
    "scaleup_config.json",
)

BROKER_READINESS_BASE_LINEAGE_FIELDS = (
    ("lineage_required", "broker_readiness_lineage_required"),
    ("lineage_provided", "broker_readiness_lineage_provided"),
    ("manifest_current", "broker_readiness_manifest_current"),
    ("manifest_run_type", "broker_readiness_manifest_run_type"),
    ("manifest_path", "broker_readiness_manifest_path"),
    ("manifest_sha256", "broker_readiness_manifest_sha256"),
    ("manifest_error", "broker_readiness_manifest_error"),
    (
        "lineage_contract_consistent",
        "broker_readiness_lineage_contract_consistent",
    ),
    ("lineage_contract_error", "broker_readiness_lineage_contract_error"),
    (
        "roundtrip_lineage_required",
        "broker_readiness_roundtrip_lineage_required",
    ),
    (
        "roundtrip_lineage_gate_passed",
        "broker_readiness_roundtrip_lineage_gate_passed",
    ),
    (
        "roundtrip_matches_current",
        "broker_readiness_roundtrip_matches_current",
    ),
    ("lineage_gate_passed", "broker_readiness_lineage_gate_passed"),
    (
        "lineage_dependency_count",
        "broker_readiness_lineage_dependency_count",
    ),
)
BROKER_READINESS_CONTRACT_IDENTITY_SUFFIXES = (
    "active",
    "required",
    "send_gate_passed",
    "ack_gate_passed",
    "request_columns_present",
    "ack_columns_present",
    "request_orders",
    "ack_orders",
    "roundtrip_orders",
    "stage_digests_match",
    "acknowledgements_match_requests",
    "roundtrip_matches_requests",
    "sha256",
    "consistency_error",
    "gate_passed",
    "lineage_verified",
    "lineage_error",
)
BROKER_READINESS_CONTRACT_IDENTITY_GATE_CHECKS = (
    (
        "required",
        "terminal round-trip contract identity is not required",
    ),
    (
        "send_gate_passed",
        "terminal round-trip send identity gate failed",
    ),
    (
        "ack_gate_passed",
        "terminal round-trip acknowledgement identity gate failed",
    ),
    (
        "request_columns_present",
        "sent requests are missing contract identity columns",
    ),
    (
        "ack_columns_present",
        "acknowledgements are missing contract identity columns",
    ),
    (
        "stage_digests_match",
        "terminal round-trip identity digests disagree across stages",
    ),
    (
        "acknowledgements_match_requests",
        "acknowledgement identities do not match sent requests",
    ),
    (
        "roundtrip_matches_requests",
        "terminal round-trip identities do not match sent requests",
    ),
    (
        "gate_passed",
        "terminal round-trip contract identity gate failed",
    ),
    (
        "lineage_verified",
        "terminal round-trip contract identity lineage is not current",
    ),
)
BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS = tuple(
    (
        f"roundtrip_contract_identity_{suffix}",
        f"broker_readiness_roundtrip_contract_identity_{suffix}",
    )
    for suffix in BROKER_READINESS_CONTRACT_IDENTITY_SUFFIXES
)
BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SUFFIXES = (
    "ack_route_contract_identity_active",
    (
        "broker_dispatch_ack_broker_dispatch_send_broker_dispatch_"
        "route_enable_cutover_runtime_telemetry_broker_readiness_"
        "roundtrip_contract_identity_sha256"
    ),
    "current_ack_route_contract_identity_sha256",
    "ack_route_contract_identity_matches_current",
)
BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS = tuple(
    (
        f"roundtrip_{suffix}",
        f"broker_readiness_roundtrip_{suffix}",
    )
    for suffix in BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_SUFFIXES
)
BROKER_READINESS_IDENTITY_LINEAGE_FIELDS = (
    *BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS,
    *BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS,
)
BROKER_READINESS_LINEAGE_FIELDS = (
    *BROKER_READINESS_BASE_LINEAGE_FIELDS,
    *BROKER_READINESS_IDENTITY_LINEAGE_FIELDS,
)

PROOF_REFRESH_REPORT_FIELDS = (
    ("requested", "proof_refresh_requested"),
    ("provided", "proof_refresh_provided"),
    ("reported_ready", "proof_refresh_reported_ready"),
    ("ready", "proof_refresh_ready"),
    ("verified", "proof_refresh_verified"),
    ("strategy", "proof_refresh_strategy"),
    ("market", "proof_refresh_market"),
    ("mixed_identity", "proof_refresh_mixed_identity"),
    ("proof_source", "proof_source"),
    ("read_error", "proof_refresh_read_error"),
    ("reason", "proof_refresh_reason"),
)

PROOF_REFRESH_MANIFEST_FIELDS = (
    ("required", "proof_refresh_manifest_required", "manifest_required"),
    ("current", "proof_refresh_manifest_current", "manifest_current"),
    ("sha256", "proof_refresh_manifest_sha256", "manifest_sha256"),
)

PROOF_REFRESH_SEMANTIC_FIELDS = (
    (
        "required",
        "proof_refresh_semantic_verification_required",
        "semantic_verification_required",
    ),
    (
        "verified",
        "proof_refresh_semantically_verified",
        "semantically_verified",
    ),
    (
        "inputs_current",
        "proof_refresh_verification_inputs_current",
        "verification_inputs_current",
    ),
    (
        "artifacts_consistent",
        "proof_refresh_verification_artifacts_consistent",
        "verification_artifacts_consistent",
    ),
    (
        "non_authorizing",
        "proof_refresh_verification_non_authorizing",
        "verification_non_authorizing",
    ),
    (
        "error",
        "proof_refresh_verification_error",
        "verification_error",
    ),
)


def empty_scaleup_runtime_provenance(*, required: bool = False) -> dict[str, Any]:
    evidence = {
        "manifest_required": required,
        "manifest_provided": False,
        "manifest_current": not required,
        "manifest_run_type": "",
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_error": "manifest_missing" if required else "",
        "contract_consistent": not required,
        "contract_error": "",
        "non_authorizing": not required,
        "source_ready": not required,
        "provenance_gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
        "proof_refresh_active": False,
        "proof_refresh_required": False,
        "proof_refresh_requested": False,
        "proof_refresh_provided": False,
        "proof_refresh_reported_ready": False,
        "proof_refresh_ready": False,
        "proof_refresh_verified": False,
        "proof_refresh_manifest_required": False,
        "proof_refresh_manifest_current": False,
        "proof_refresh_manifest_sha256": "",
        "proof_refresh_semantic_verification_required": False,
        "proof_refresh_semantically_verified": False,
        "proof_refresh_verification_inputs_current": False,
        "proof_refresh_verification_artifacts_consistent": False,
        "proof_refresh_verification_non_authorizing": False,
        "proof_refresh_verification_error": "",
        "proof_refresh_read_error": "",
        "proof_refresh_reason": "",
        "proof_refresh_source_manifest_current": False,
        "proof_refresh_source_manifest_sha256": "",
        "proof_refresh_source_semantically_verified": False,
        "proof_refresh_source_provenance_gate_passed": False,
        "proof_refresh_matches_current": True,
        "strategy_portfolio_required": False,
        "strategy_portfolio_provided": False,
        "strategy_portfolio_manifest_required": False,
        "strategy_portfolio_manifest_current": False,
        "strategy_portfolio_manifest_sha256": "",
        "strategy_portfolio_provenance_gate_passed": False,
        "scorecard_manifest_required": False,
        "scorecard_manifest_current": False,
        "scorecard_manifest_sha256": "",
        "scorecard_provenance_gate_passed": False,
        "research_family_bound": False,
        "research_family_provenance_current": False,
        "research_family_id": "",
        "research_family_registration_id": "",
        "research_family_manifest_sha256": "",
        "broker_readiness_required": False,
        "broker_readiness_provided": False,
        "broker_readiness_lineage_required": False,
        "broker_readiness_lineage_provided": False,
        "broker_readiness_manifest_current": False,
        "broker_readiness_manifest_run_type": "",
        "broker_readiness_manifest_path": "",
        "broker_readiness_manifest_sha256": "",
        "broker_readiness_manifest_error": "",
        "broker_readiness_lineage_contract_consistent": False,
        "broker_readiness_lineage_contract_error": "",
        "broker_readiness_roundtrip_lineage_required": False,
        "broker_readiness_roundtrip_lineage_gate_passed": False,
        "broker_readiness_roundtrip_matches_current": False,
        "broker_readiness_lineage_gate_passed": False,
        "broker_readiness_lineage_dependency_count": 0,
        "broker_readiness_source_manifest_current": False,
        "broker_readiness_source_manifest_sha256": "",
        "broker_readiness_source_provenance_gate_passed": False,
        "broker_readiness_matches_current": not required,
    }
    evidence.update(
        {
            report_field: _broker_readiness_contract_identity_value(
                {},
                config_field,
                report_field,
            )
            for (
                config_field,
                report_field,
            ) in BROKER_READINESS_IDENTITY_LINEAGE_FIELDS
        }
    )
    evidence["broker_readiness_contract_identity_matches_current"] = (
        not required
    )
    return evidence


def load_scaleup_runtime_provenance(
    scaleup_config_path: str | Path,
    *,
    scaleup_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_path = Path(scaleup_config_path).resolve()
    root = config_path.parent
    manifest_path = root / "manifest.json"
    evidence = empty_scaleup_runtime_provenance(required=True)
    evidence.update(
        {
            "manifest_path": str(manifest_path),
            "manifest_provided": manifest_path.is_file(),
            "artifact_paths": [
                str(root / name)
                for name in SCALEUP_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )
    config = scaleup_config if isinstance(scaleup_config, dict) else _read_json(config_path)
    manifest = _read_json(manifest_path)
    summary = _read_csv(root / "scaleup_summary.csv")
    checks = _read_csv(root / "scaleup_checks.csv")
    plan = _read_csv(root / "scaleup_plan.csv")

    proof_refresh_active = _proof_refresh_active(config, manifest)
    proof_refresh_path = _manifest_input_path(
        manifest,
        "proof_refresh",
    )
    current_proof_refresh: dict[str, object] = {}
    if proof_refresh_path is not None:
        current_proof_refresh = proof_refresh_evidence_record(
            load_proof_refresh_evidence(proof_refresh_path)
        )
    broker_readiness_active = _broker_readiness_active(config, manifest)
    broker_readiness_config_path = _manifest_input_path(
        manifest,
        "broker_readiness_config",
    )
    current_broker_readiness_fields: dict[str, Any] = {}
    if broker_readiness_config_path is not None:
        current_broker_readiness_fields = _broker_readiness_lineage_fields(
            _load_broker_readiness_lineage(broker_readiness_config_path)
        )

    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="scaleup_plan",
            required_artifacts=SCALEUP_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        evidence.update(
            {
                "manifest_current": bool(integrity.passed),
                "manifest_run_type": integrity.run_type,
                "manifest_sha256": file_sha256(manifest_path),
                "manifest_error": integrity.error,
                "dependency_paths": [
                    str(path) for path in manifest_dependency_paths(manifest_path)
                ],
            }
        )
    evidence["dependency_count"] = len(evidence["dependency_paths"])

    errors = _scaleup_contract_errors(
        config=config,
        manifest=manifest,
        summary=summary,
        checks=checks,
        plan=plan,
        proof_refresh_active=proof_refresh_active,
        proof_refresh_path=proof_refresh_path,
        current_proof_refresh=current_proof_refresh,
        broker_readiness_active=broker_readiness_active,
        broker_readiness_config_path=broker_readiness_config_path,
        current_broker_readiness_fields=current_broker_readiness_fields,
    )
    non_authorizing = _scaleup_non_authorizing(config, manifest, summary, plan)
    source_ready = _bool(config.get("ready", False))
    evidence.update(_lineage(config))
    proof_refresh_errors = [
        error
        for error in errors
        if error.startswith("scaleup_proof_refresh_")
    ]
    evidence.update(
        {
            "proof_refresh_active": proof_refresh_active,
            "proof_refresh_source_manifest_current": _bool(
                current_proof_refresh.get("manifest_current", False)
            ),
            "proof_refresh_source_manifest_sha256": _text(
                current_proof_refresh.get("manifest_sha256", "")
            ),
            "proof_refresh_source_semantically_verified": _bool(
                current_proof_refresh.get(
                    "semantically_verified",
                    False,
                )
            ),
            "proof_refresh_source_provenance_gate_passed": _bool(
                current_proof_refresh.get("verified", False)
            ),
            "proof_refresh_matches_current": bool(
                not proof_refresh_active
                or (
                    proof_refresh_path is not None
                    and not proof_refresh_errors
                    and _bool(
                        current_proof_refresh.get("verified", False)
                    )
                )
            ),
        }
    )
    broker_readiness_errors = [
        error
        for error in errors
        if error.startswith("scaleup_broker_readiness_")
    ]
    broker_contract_identity_active = any(
        _broker_readiness_contract_identity_present(value, report_field)
        for _config_field, report_field in (
            BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS
        )
        for value in (
            evidence.get(report_field),
            current_broker_readiness_fields.get(report_field),
        )
    )
    broker_contract_identity_errors = [
        error
        for error in broker_readiness_errors
        if error.startswith(
            "scaleup_broker_readiness_roundtrip_contract_identity_"
        )
    ]
    evidence.update(
        {
            "broker_readiness_source_manifest_current": _bool(
                current_broker_readiness_fields.get(
                    "broker_readiness_manifest_current",
                    False,
                )
            ),
            "broker_readiness_source_manifest_sha256": _text(
                current_broker_readiness_fields.get(
                    "broker_readiness_manifest_sha256",
                    "",
                )
            ),
            "broker_readiness_source_provenance_gate_passed": _bool(
                current_broker_readiness_fields.get(
                    "broker_readiness_lineage_gate_passed",
                    False,
                )
            ),
            "broker_readiness_matches_current": bool(
                not broker_readiness_active
                or (
                    broker_readiness_config_path is not None
                    and not broker_readiness_errors
                    and _bool(
                        current_broker_readiness_fields.get(
                            "broker_readiness_lineage_gate_passed",
                            False,
                        )
                    )
                )
            ),
            "broker_readiness_contract_identity_matches_current": bool(
                not broker_contract_identity_active
                or (
                    broker_readiness_config_path is not None
                    and not broker_contract_identity_errors
                    and _bool(
                        current_broker_readiness_fields.get(
                            (
                                "broker_readiness_roundtrip_"
                                "contract_identity_active"
                            ),
                            False,
                        )
                    )
                    and _bool(
                        current_broker_readiness_fields.get(
                            (
                                "broker_readiness_roundtrip_"
                                "contract_identity_lineage_verified"
                            ),
                            False,
                        )
                    )
                )
            ),
        }
    )
    evidence["contract_consistent"] = not errors
    evidence["contract_error"] = ";".join(sorted(set(errors)))
    evidence["non_authorizing"] = non_authorizing
    evidence["source_ready"] = source_ready
    evidence["provenance_gate_passed"] = bool(
        evidence["manifest_provided"]
        and evidence["manifest_current"]
        and evidence["contract_consistent"]
        and non_authorizing
        and source_ready
    )
    return evidence


def scaleup_runtime_manifest_inputs(provenance: Mapping[str, Any]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(provenance.get("manifest_path"))
    if manifest_path is not None:
        inputs["scaleup_manifest"] = manifest_path
    artifacts = _existing_paths(provenance.get("artifact_paths"))
    if artifacts:
        inputs["scaleup_artifacts"] = artifacts
    dependencies = _existing_paths(provenance.get("dependency_paths"))
    if dependencies:
        inputs["scaleup_dependencies"] = dependencies
    return inputs


def scaleup_runtime_manifest_extra(provenance: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "scaleup_manifest_current": _bool(provenance.get("manifest_current", False)),
        "scaleup_manifest_sha256": _text(provenance.get("manifest_sha256", "")),
        "scaleup_contract_consistent": _bool(provenance.get("contract_consistent", False)),
        "scaleup_non_authorizing": _bool(provenance.get("non_authorizing", False)),
        "scaleup_provenance_gate_passed": _bool(
            provenance.get("provenance_gate_passed", False)
        ),
        "proof_refresh_manifest_sha256": _text(
            provenance.get("proof_refresh_manifest_sha256", "")
        ),
        "proof_refresh_source_manifest_sha256": _text(
            provenance.get(
                "proof_refresh_source_manifest_sha256",
                "",
            )
        ),
        "proof_refresh_verified": _bool(
            provenance.get("proof_refresh_verified", False)
        ),
        "proof_refresh_matches_current": _bool(
            provenance.get("proof_refresh_matches_current", False)
        ),
        "strategy_portfolio_manifest_sha256": _text(
            provenance.get("strategy_portfolio_manifest_sha256", "")
        ),
        "scorecard_manifest_sha256": _text(
            provenance.get("scorecard_manifest_sha256", "")
        ),
        "research_family_bound": _bool(
            provenance.get("research_family_bound", False)
        ),
        "research_family_id": _text(provenance.get("research_family_id", "")),
        "research_family_registration_id": _text(
            provenance.get("research_family_registration_id", "")
        ),
        "research_family_manifest_sha256": _text(
            provenance.get("research_family_manifest_sha256", "")
        ),
        "broker_readiness_manifest_sha256": _text(
            provenance.get("broker_readiness_manifest_sha256", "")
        ),
        "broker_readiness_source_manifest_sha256": _text(
            provenance.get("broker_readiness_source_manifest_sha256", "")
        ),
        "broker_readiness_lineage_gate_passed": _bool(
            provenance.get("broker_readiness_lineage_gate_passed", False)
        ),
        "broker_readiness_matches_current": _bool(
            provenance.get("broker_readiness_matches_current", False)
        ),
        "authorizes_submission": False,
    }
    fields.update(
        {
            report_field: _broker_readiness_contract_identity_normalize(
                provenance.get(report_field),
                report_field,
            )
            for _config_field, report_field in (
                BROKER_READINESS_IDENTITY_LINEAGE_FIELDS
            )
        }
    )
    fields[
        "broker_readiness_roundtrip_contract_identity_matches_current"
    ] = _bool(
        provenance.get(
            "broker_readiness_contract_identity_matches_current",
            False,
        )
    )
    return fields


def scaleup_runtime_fields(provenance: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "scaleup_manifest_required": _bool(provenance.get("manifest_required", False)),
        "scaleup_manifest_provided": _bool(provenance.get("manifest_provided", False)),
        "scaleup_manifest_current": _bool(provenance.get("manifest_current", False)),
        "scaleup_manifest_run_type": _text(provenance.get("manifest_run_type", "")),
        "scaleup_manifest_path": _text(provenance.get("manifest_path", "")),
        "scaleup_manifest_sha256": _text(provenance.get("manifest_sha256", "")),
        "scaleup_manifest_error": _text(provenance.get("manifest_error", "")),
        "scaleup_contract_consistent": _bool(provenance.get("contract_consistent", False)),
        "scaleup_contract_error": _text(provenance.get("contract_error", "")),
        "scaleup_non_authorizing": _bool(provenance.get("non_authorizing", False)),
        "scaleup_source_ready": _bool(provenance.get("source_ready", False)),
        "scaleup_provenance_gate_passed": _bool(
            provenance.get("provenance_gate_passed", False)
        ),
        "scaleup_dependency_count": int(provenance.get("dependency_count", 0)),
        "scaleup_proof_refresh_active": _bool(
            provenance.get("proof_refresh_active", False)
        ),
        "scaleup_proof_refresh_required": _bool(
            provenance.get("proof_refresh_required", False)
        ),
        "scaleup_proof_refresh_requested": _bool(
            provenance.get("proof_refresh_requested", False)
        ),
        "scaleup_proof_refresh_provided": _bool(
            provenance.get("proof_refresh_provided", False)
        ),
        "scaleup_proof_refresh_reported_ready": _bool(
            provenance.get("proof_refresh_reported_ready", False)
        ),
        "scaleup_proof_refresh_ready": _bool(
            provenance.get("proof_refresh_ready", False)
        ),
        "scaleup_proof_refresh_verified": _bool(
            provenance.get("proof_refresh_verified", False)
        ),
        "scaleup_proof_refresh_manifest_required": _bool(
            provenance.get("proof_refresh_manifest_required", False)
        ),
        "scaleup_proof_refresh_manifest_current": _bool(
            provenance.get("proof_refresh_manifest_current", False)
        ),
        "scaleup_proof_refresh_manifest_sha256": _text(
            provenance.get("proof_refresh_manifest_sha256", "")
        ),
        "scaleup_proof_refresh_semantic_verification_required": _bool(
            provenance.get(
                "proof_refresh_semantic_verification_required",
                False,
            )
        ),
        "scaleup_proof_refresh_semantically_verified": _bool(
            provenance.get(
                "proof_refresh_semantically_verified",
                False,
            )
        ),
        "scaleup_proof_refresh_verification_inputs_current": _bool(
            provenance.get(
                "proof_refresh_verification_inputs_current",
                False,
            )
        ),
        "scaleup_proof_refresh_verification_artifacts_consistent": _bool(
            provenance.get(
                "proof_refresh_verification_artifacts_consistent",
                False,
            )
        ),
        "scaleup_proof_refresh_verification_non_authorizing": _bool(
            provenance.get(
                "proof_refresh_verification_non_authorizing",
                False,
            )
        ),
        "scaleup_proof_refresh_verification_error": _text(
            provenance.get("proof_refresh_verification_error", "")
        ),
        "scaleup_proof_refresh_read_error": _text(
            provenance.get("proof_refresh_read_error", "")
        ),
        "scaleup_proof_refresh_reason": _text(
            provenance.get("proof_refresh_reason", "")
        ),
        "scaleup_proof_refresh_source_manifest_current": _bool(
            provenance.get(
                "proof_refresh_source_manifest_current",
                False,
            )
        ),
        "scaleup_proof_refresh_source_manifest_sha256": _text(
            provenance.get(
                "proof_refresh_source_manifest_sha256",
                "",
            )
        ),
        "scaleup_proof_refresh_source_semantically_verified": _bool(
            provenance.get(
                "proof_refresh_source_semantically_verified",
                False,
            )
        ),
        "scaleup_proof_refresh_source_provenance_gate_passed": _bool(
            provenance.get(
                "proof_refresh_source_provenance_gate_passed",
                False,
            )
        ),
        "scaleup_proof_refresh_matches_current": _bool(
            provenance.get("proof_refresh_matches_current", False)
        ),
        "scaleup_strategy_portfolio_required": _bool(
            provenance.get("strategy_portfolio_required", False)
        ),
        "scaleup_strategy_portfolio_provided": _bool(
            provenance.get("strategy_portfolio_provided", False)
        ),
        "scaleup_strategy_portfolio_manifest_required": _bool(
            provenance.get("strategy_portfolio_manifest_required", False)
        ),
        "scaleup_strategy_portfolio_manifest_current": _bool(
            provenance.get("strategy_portfolio_manifest_current", False)
        ),
        "scaleup_strategy_portfolio_manifest_sha256": _text(
            provenance.get("strategy_portfolio_manifest_sha256", "")
        ),
        "scaleup_strategy_portfolio_provenance_gate_passed": _bool(
            provenance.get("strategy_portfolio_provenance_gate_passed", False)
        ),
        "scaleup_scorecard_manifest_required": _bool(
            provenance.get("scorecard_manifest_required", False)
        ),
        "scaleup_scorecard_manifest_current": _bool(
            provenance.get("scorecard_manifest_current", False)
        ),
        "scaleup_scorecard_manifest_sha256": _text(
            provenance.get("scorecard_manifest_sha256", "")
        ),
        "scaleup_scorecard_provenance_gate_passed": _bool(
            provenance.get("scorecard_provenance_gate_passed", False)
        ),
        "scaleup_research_family_bound": _bool(
            provenance.get("research_family_bound", False)
        ),
        "scaleup_research_family_provenance_current": _bool(
            provenance.get("research_family_provenance_current", False)
        ),
        "scaleup_research_family_id": _text(provenance.get("research_family_id", "")),
        "scaleup_research_family_registration_id": _text(
            provenance.get("research_family_registration_id", "")
        ),
        "scaleup_research_family_manifest_sha256": _text(
            provenance.get("research_family_manifest_sha256", "")
        ),
        "scaleup_broker_readiness_required": _bool(
            provenance.get("broker_readiness_required", False)
        ),
        "scaleup_broker_readiness_provided": _bool(
            provenance.get("broker_readiness_provided", False)
        ),
        "scaleup_broker_readiness_lineage_required": _bool(
            provenance.get("broker_readiness_lineage_required", False)
        ),
        "scaleup_broker_readiness_lineage_provided": _bool(
            provenance.get("broker_readiness_lineage_provided", False)
        ),
        "scaleup_broker_readiness_manifest_current": _bool(
            provenance.get("broker_readiness_manifest_current", False)
        ),
        "scaleup_broker_readiness_manifest_run_type": _text(
            provenance.get("broker_readiness_manifest_run_type", "")
        ),
        "scaleup_broker_readiness_manifest_path": _text(
            provenance.get("broker_readiness_manifest_path", "")
        ),
        "scaleup_broker_readiness_manifest_sha256": _text(
            provenance.get("broker_readiness_manifest_sha256", "")
        ),
        "scaleup_broker_readiness_manifest_error": _text(
            provenance.get("broker_readiness_manifest_error", "")
        ),
        "scaleup_broker_readiness_lineage_contract_consistent": _bool(
            provenance.get(
                "broker_readiness_lineage_contract_consistent",
                False,
            )
        ),
        "scaleup_broker_readiness_lineage_contract_error": _text(
            provenance.get("broker_readiness_lineage_contract_error", "")
        ),
        "scaleup_broker_readiness_roundtrip_lineage_required": _bool(
            provenance.get("broker_readiness_roundtrip_lineage_required", False)
        ),
        "scaleup_broker_readiness_roundtrip_lineage_gate_passed": _bool(
            provenance.get(
                "broker_readiness_roundtrip_lineage_gate_passed",
                False,
            )
        ),
        "scaleup_broker_readiness_roundtrip_matches_current": _bool(
            provenance.get("broker_readiness_roundtrip_matches_current", False)
        ),
        "scaleup_broker_readiness_lineage_gate_passed": _bool(
            provenance.get("broker_readiness_lineage_gate_passed", False)
        ),
        "scaleup_broker_readiness_lineage_dependency_count": int(
            provenance.get("broker_readiness_lineage_dependency_count", 0)
        ),
        "scaleup_broker_readiness_source_manifest_current": _bool(
            provenance.get("broker_readiness_source_manifest_current", False)
        ),
        "scaleup_broker_readiness_source_manifest_sha256": _text(
            provenance.get("broker_readiness_source_manifest_sha256", "")
        ),
        "scaleup_broker_readiness_source_provenance_gate_passed": _bool(
            provenance.get(
                "broker_readiness_source_provenance_gate_passed",
                False,
            )
        ),
        "scaleup_broker_readiness_matches_current": _bool(
            provenance.get("broker_readiness_matches_current", False)
        ),
    }
    fields.update(
        {
            f"scaleup_{report_field}": (
                _broker_readiness_contract_identity_normalize(
                    provenance.get(report_field),
                    report_field,
                )
            )
            for _config_field, report_field in (
                BROKER_READINESS_IDENTITY_LINEAGE_FIELDS
            )
        }
    )
    fields[
        "scaleup_broker_readiness_roundtrip_contract_identity_matches_current"
    ] = _bool(
        provenance.get(
            "broker_readiness_contract_identity_matches_current",
            False,
        )
    )
    return fields


def _scaleup_contract_errors(
    *,
    config: dict[str, Any],
    manifest: dict[str, Any],
    summary: pd.DataFrame,
    checks: pd.DataFrame,
    plan: pd.DataFrame,
    proof_refresh_active: bool,
    proof_refresh_path: Path | None,
    current_proof_refresh: Mapping[str, Any],
    broker_readiness_active: bool,
    broker_readiness_config_path: Path | None,
    current_broker_readiness_fields: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not config:
        errors.append("scaleup_config_missing_or_invalid")
    if summary.empty:
        errors.append("scaleup_summary_missing_or_empty")
    if checks.empty or "passed" not in checks.columns:
        errors.append("scaleup_checks_missing_or_invalid")
    if plan.empty:
        errors.append("scaleup_plan_missing_or_empty")
    if not manifest:
        errors.append("scaleup_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    plan_row = plan.iloc[0]
    extra = _mapping(manifest.get("extra"))
    ready = _bool(config.get("ready", False))
    for source, value in (
        ("summary", row.get("ready", False)),
        ("plan", plan_row.get("ready", False)),
        ("manifest", extra.get("ready", False)),
    ):
        if _bool(value) != ready:
            errors.append(f"scaleup_{source}_ready_mismatch")
    checks_ready = bool(checks["passed"].map(_bool).all())
    if checks_ready != ready:
        errors.append("scaleup_checks_ready_mismatch")
    failed_count = int((~checks["passed"].map(_bool)).sum())
    if _integer(config.get("failed_check_count", -1), fallback=-1) != failed_count:
        errors.append("scaleup_failed_check_count_mismatch")

    for field in ("target_mode", "strategy", "market", "scenario_key", "adapter"):
        if not _same(row.get(field, ""), config.get(field, "")):
            errors.append(f"scaleup_summary_{field}_mismatch")
        if field in plan_row.index and not _same(plan_row.get(field, ""), config.get(field, "")):
            errors.append(f"scaleup_plan_{field}_mismatch")
    limits = _mapping(config.get("limits"))
    for config_field, summary_field in (
        ("max_orders_per_session", "max_orders_per_session"),
        ("max_notional_per_session", "max_notional_per_session"),
        ("pre_portfolio_max_notional_per_session", "pre_portfolio_max_notional_per_session"),
    ):
        if config_field in limits and summary_field in row.index:
            if not _same(row.get(summary_field), limits.get(config_field)):
                errors.append(f"scaleup_summary_{summary_field}_mismatch")

    if proof_refresh_active:
        errors.extend(
            _proof_refresh_contract_errors(
                manifest_extra=extra,
                summary=row,
                plan=plan_row,
                scaleup_ready=ready,
                proof_refresh=_mapping(
                    config.get("proof_freshness")
                ),
                proof_refresh_path=proof_refresh_path,
                current=current_proof_refresh,
            )
        )
    portfolio = _mapping(config.get("strategy_portfolio"))
    portfolio_active = _bool(portfolio.get("required", False)) or _bool(
        portfolio.get("provided", False)
    )
    if portfolio_active:
        errors.extend(
            _portfolio_contract_errors(
                manifest=manifest,
                manifest_extra=extra,
                summary=row,
                portfolio=portfolio,
            )
        )
    if broker_readiness_active:
        errors.extend(
            _broker_readiness_contract_errors(
                manifest_extra=extra,
                summary=row,
                plan=plan_row,
                broker_readiness=_mapping(config.get("broker_readiness")),
                broker_readiness_config_path=broker_readiness_config_path,
                current_fields=current_broker_readiness_fields,
            )
        )
    return errors


def _proof_refresh_contract_errors(
    *,
    manifest_extra: dict[str, Any],
    summary: pd.Series,
    plan: pd.Series,
    scaleup_ready: bool,
    proof_refresh: dict[str, Any],
    proof_refresh_path: Path | None,
    current: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not proof_refresh:
        errors.append("scaleup_proof_refresh_config_missing")

    for config_field, report_field in PROOF_REFRESH_REPORT_FIELDS:
        _compare_proof_refresh_report_field(
            errors,
            config=proof_refresh,
            config_field=config_field,
            report_field=report_field,
            summary=summary,
            plan=plan,
        )

    for config_field, report_field in (
        ("fresh_proof_required", "fresh_proof_required"),
        ("recommendation", "proof_refresh_recommendation"),
    ):
        if config_field not in proof_refresh:
            errors.append(
                f"scaleup_proof_refresh_{config_field}_missing:config"
            )
        elif report_field not in plan.index:
            errors.append(
                f"scaleup_proof_refresh_{config_field}_missing:plan"
            )
        elif not _same(
            plan.get(report_field),
            proof_refresh.get(config_field),
        ):
            errors.append(
                f"scaleup_proof_refresh_{config_field}_plan_mismatch"
            )

    if "required" not in proof_refresh:
        errors.append("scaleup_proof_refresh_required_missing:config")
    refresh_manifest = _mapping(proof_refresh.get("manifest"))
    for config_field, report_field, _ in PROOF_REFRESH_MANIFEST_FIELDS:
        _compare_proof_refresh_nested_field(
            errors,
            section=refresh_manifest,
            section_name="manifest",
            config_field=config_field,
            report_field=report_field,
            summary=summary,
            plan=plan,
        )
    semantic = _mapping(
        proof_refresh.get("semantic_verification")
    )
    for config_field, report_field, _ in PROOF_REFRESH_SEMANTIC_FIELDS:
        _compare_proof_refresh_nested_field(
            errors,
            section=semantic,
            section_name="semantic_verification",
            config_field=config_field,
            report_field=report_field,
            summary=summary,
            plan=plan,
        )
    if scaleup_ready:
        for field, value in (
            ("provided", proof_refresh.get("provided", False)),
            ("ready", proof_refresh.get("ready", False)),
            ("verified", proof_refresh.get("verified", False)),
            (
                "manifest_current",
                refresh_manifest.get("current", False),
            ),
            (
                "semantically_verified",
                semantic.get("verified", False),
            ),
            (
                "verification_inputs_current",
                semantic.get("inputs_current", False),
            ),
            (
                "verification_artifacts_consistent",
                semantic.get("artifacts_consistent", False),
            ),
            (
                "verification_non_authorizing",
                semantic.get("non_authorizing", False),
            ),
        ):
            if not _bool(value):
                errors.append(
                    f"scaleup_proof_refresh_{field}_not_ready"
                )

    for extra_field, expected in (
        (
            "proof_refresh_verified",
            proof_refresh.get("verified", False),
        ),
        (
            "proof_refresh_manifest_current",
            refresh_manifest.get("current", False),
        ),
        (
            "proof_refresh_manifest_sha256",
            refresh_manifest.get("sha256", ""),
        ),
    ):
        if extra_field not in manifest_extra:
            errors.append(
                f"scaleup_{extra_field}_missing:manifest"
            )
        elif not _same(
            manifest_extra.get(extra_field),
            expected,
        ):
            errors.append(
                f"scaleup_{extra_field}_manifest_mismatch"
            )

    if proof_refresh_path is None:
        errors.append("scaleup_proof_refresh_source_missing")
        return errors

    for config_field, _, source_field in (
        *(
            (config_field, report_field, config_field)
            for config_field, report_field
            in PROOF_REFRESH_REPORT_FIELDS
        ),
        (
            "fresh_proof_required",
            "fresh_proof_required",
            "fresh_proof_required",
        ),
        (
            "recommendation",
            "proof_refresh_recommendation",
            "recommendation",
        ),
    ):
        if not _proof_refresh_source_same(
            config_field,
            proof_refresh.get(config_field),
            current.get(source_field),
        ):
            errors.append(
                f"scaleup_proof_refresh_{config_field}_source_mismatch"
            )
    for config_field, _, source_field in PROOF_REFRESH_MANIFEST_FIELDS:
        if not _same(
            refresh_manifest.get(config_field),
            current.get(source_field),
        ):
            errors.append(
                "scaleup_proof_refresh_manifest_"
                f"{config_field}_source_mismatch"
            )
    for config_field, _, source_field in PROOF_REFRESH_SEMANTIC_FIELDS:
        if not _same(
            semantic.get(config_field),
            current.get(source_field),
        ):
            errors.append(
                "scaleup_proof_refresh_semantic_verification_"
                f"{config_field}_source_mismatch"
            )
    if not _bool(current.get("verified", False)):
        errors.append(
            "scaleup_proof_refresh_source_provenance_not_current"
        )
    return errors


def _compare_proof_refresh_report_field(
    errors: list[str],
    *,
    config: Mapping[str, Any],
    config_field: str,
    report_field: str,
    summary: pd.Series,
    plan: pd.Series,
) -> None:
    if config_field not in config:
        errors.append(
            f"scaleup_proof_refresh_{config_field}_missing:config"
        )
        return
    expected = config.get(config_field)
    for source, row in (("summary", summary), ("plan", plan)):
        if report_field not in row.index:
            errors.append(
                f"scaleup_proof_refresh_{config_field}_missing:{source}"
            )
        elif not _same(row.get(report_field), expected):
            errors.append(
                f"scaleup_proof_refresh_{config_field}_{source}_mismatch"
            )


def _compare_proof_refresh_nested_field(
    errors: list[str],
    *,
    section: Mapping[str, Any],
    section_name: str,
    config_field: str,
    report_field: str,
    summary: pd.Series,
    plan: pd.Series,
) -> None:
    error_prefix = (
        f"scaleup_proof_refresh_{section_name}_{config_field}"
    )
    if config_field not in section:
        errors.append(f"{error_prefix}_missing:config")
        return
    expected = section.get(config_field)
    for source, row in (("summary", summary), ("plan", plan)):
        if report_field not in row.index:
            errors.append(f"{error_prefix}_missing:{source}")
        elif not _same(row.get(report_field), expected):
            errors.append(f"{error_prefix}_{source}_mismatch")


def _broker_readiness_contract_errors(
    *,
    manifest_extra: dict[str, Any],
    summary: pd.Series,
    plan: pd.Series,
    broker_readiness: dict[str, Any],
    broker_readiness_config_path: Path | None,
    current_fields: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    lineage = _mapping(broker_readiness.get("lineage"))
    contract_identity_active = any(
        _broker_readiness_contract_identity_present(value, report_field)
        for config_field, report_field in (
            BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS
        )
        for value in (
            lineage.get(config_field),
            summary.get(report_field),
            plan.get(report_field),
            manifest_extra.get(report_field),
            current_fields.get(report_field),
        )
    )
    route_identity_active = any(
        _broker_readiness_contract_identity_present(value, report_field)
        for config_field, report_field in (
            BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS
        )
        for value in (
            lineage.get(config_field),
            summary.get(report_field),
            plan.get(report_field),
            manifest_extra.get(report_field),
            current_fields.get(report_field),
        )
    )
    lineage_fields = (
        *BROKER_READINESS_BASE_LINEAGE_FIELDS,
        *(
            BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS
            if contract_identity_active
            else ()
        ),
        *(
            BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS
            if route_identity_active
            else ()
        ),
    )
    for config_field, report_field in lineage_fields:
        if config_field not in lineage:
            errors.append(
                f"scaleup_broker_readiness_{config_field}_missing:config"
            )
            expected: Any = None
        else:
            expected = lineage.get(config_field)
        for source, row in (("summary", summary), ("plan", plan)):
            if report_field not in row.index:
                errors.append(
                    f"scaleup_broker_readiness_{config_field}_missing:{source}"
                )
            elif config_field in lineage and not _same(row.get(report_field), expected):
                errors.append(
                    f"scaleup_broker_readiness_{config_field}_{source}_mismatch"
                )
        if report_field not in manifest_extra:
            errors.append(
                f"scaleup_broker_readiness_{config_field}_missing:manifest"
            )
        elif config_field in lineage and not _same(
            manifest_extra.get(report_field),
            expected,
        ):
            errors.append(
                f"scaleup_broker_readiness_{config_field}_manifest_mismatch"
            )

    if broker_readiness_config_path is None:
        errors.append("scaleup_broker_readiness_source_missing")
        return errors
    for config_field, report_field in lineage_fields:
        if config_field not in lineage:
            continue
        if not _same(lineage.get(config_field), current_fields.get(report_field)):
            errors.append(
                f"scaleup_broker_readiness_{config_field}_source_mismatch"
            )
    if not _bool(
        current_fields.get("broker_readiness_lineage_gate_passed", False)
    ):
        errors.append("scaleup_broker_readiness_source_provenance_not_current")
    return errors


def _portfolio_contract_errors(
    *,
    manifest: dict[str, Any],
    manifest_extra: dict[str, Any],
    summary: pd.Series,
    portfolio: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    summary_fields = {
        "required": "strategy_portfolio_required",
        "provided": "strategy_portfolio_provided",
        "manifest_required": "strategy_portfolio_manifest_required",
        "manifest_provided": "strategy_portfolio_manifest_provided",
        "manifest_current": "strategy_portfolio_manifest_current",
        "manifest_sha256": "strategy_portfolio_manifest_sha256",
        "contract_consistent": "strategy_portfolio_contract_consistent",
        "non_authorizing": "strategy_portfolio_non_authorizing",
        "provenance_gate_passed": "strategy_portfolio_provenance_gate_passed",
    }
    for config_field, summary_field in summary_fields.items():
        if not _same(summary.get(summary_field, ""), portfolio.get(config_field, "")):
            errors.append(f"scaleup_portfolio_{config_field}_summary_mismatch")

    scorecard = _mapping(portfolio.get("scorecard_provenance"))
    for config_field, summary_field in (
        ("manifest_required", "strategy_portfolio_scorecard_manifest_required"),
        ("manifest_current", "strategy_portfolio_scorecard_manifest_current"),
        ("manifest_sha256", "strategy_portfolio_scorecard_manifest_sha256"),
        ("contract_consistent", "strategy_portfolio_scorecard_contract_consistent"),
        ("non_authorizing", "strategy_portfolio_scorecard_non_authorizing"),
        ("gate_passed", "strategy_portfolio_scorecard_provenance_gate_passed"),
    ):
        if not _same(summary.get(summary_field, ""), scorecard.get(config_field, "")):
            errors.append(f"scaleup_scorecard_{config_field}_summary_mismatch")

    family = _mapping(portfolio.get("research_family"))
    for config_field, summary_field in (
        ("bound", "strategy_portfolio_research_family_bound"),
        ("provenance_current", "strategy_portfolio_research_family_provenance_current"),
        ("family_id", "strategy_portfolio_research_family_id"),
        ("registration_id", "strategy_portfolio_research_family_registration_id"),
        ("manifest_sha256", "strategy_portfolio_research_family_manifest_sha256"),
    ):
        if not _same(summary.get(summary_field, ""), family.get(config_field, "")):
            errors.append(f"scaleup_family_{config_field}_summary_mismatch")

    for extra_field, expected in (
        ("strategy_portfolio_manifest_required", portfolio.get("manifest_required", False)),
        ("strategy_portfolio_manifest_current", portfolio.get("manifest_current", False)),
        ("strategy_portfolio_manifest_sha256", portfolio.get("manifest_sha256", "")),
        ("research_family_bound", family.get("bound", False)),
        ("research_family_id", family.get("family_id", "")),
        ("research_family_registration_id", family.get("registration_id", "")),
        ("research_family_manifest_sha256", family.get("manifest_sha256", "")),
    ):
        if not _same(manifest_extra.get(extra_field, ""), expected):
            errors.append(f"scaleup_manifest_{extra_field}_mismatch")

    portfolio_summary_path = _manifest_input_path(manifest, "strategy_portfolio")
    if portfolio_summary_path is None:
        errors.append("scaleup_portfolio_source_missing")
        return errors
    allocations_path = portfolio_summary_path.parent / "strategy_portfolio_allocations.csv"
    fresh = load_strategy_portfolio_provenance(
        portfolio_summary_path,
        _read_csv(portfolio_summary_path),
        _read_csv(allocations_path),
    )
    comparisons = (
        ("manifest_required", "manifest_required"),
        ("manifest_provided", "manifest_provided"),
        ("manifest_current", "manifest_current"),
        ("manifest_sha256", "manifest_sha256"),
        ("contract_consistent", "contract_consistent"),
        ("non_authorizing", "non_authorizing"),
        ("provenance_gate_passed", "gate_passed"),
    )
    for config_field, fresh_field in comparisons:
        if not _same(portfolio.get(config_field, ""), fresh.get(fresh_field, "")):
            errors.append(f"scaleup_portfolio_{config_field}_source_mismatch")
    for config_field, fresh_field in (
        ("manifest_required", "scorecard_manifest_required"),
        ("manifest_current", "scorecard_manifest_current"),
        ("manifest_sha256", "scorecard_manifest_sha256"),
        ("contract_consistent", "scorecard_contract_consistent"),
        ("non_authorizing", "scorecard_non_authorizing"),
        ("gate_passed", "scorecard_provenance_gate_passed"),
    ):
        if not _same(scorecard.get(config_field, ""), fresh.get(fresh_field, "")):
            errors.append(f"scaleup_scorecard_{config_field}_source_mismatch")
    for config_field, fresh_field in (
        ("bound", "research_family_bound"),
        ("provenance_current", "research_family_provenance_current"),
        ("family_id", "research_family_id"),
        ("registration_id", "research_family_registration_id"),
        ("manifest_sha256", "research_family_manifest_sha256"),
    ):
        if not _same(family.get(config_field, ""), fresh.get(fresh_field, "")):
            errors.append(f"scaleup_family_{config_field}_source_mismatch")
    if not _bool(fresh.get("gate_passed", False)):
        errors.append("scaleup_portfolio_source_provenance_not_current")
    return errors


def _scaleup_non_authorizing(
    config: dict[str, Any],
    manifest: dict[str, Any],
    summary: pd.DataFrame,
    plan: pd.DataFrame,
) -> bool:
    extra = _mapping(manifest.get("extra"))
    required_claims = (
        "authorizes_submission" in config,
        "authorizes_submission" in extra,
        not summary.empty and "authorizes_submission" in summary.columns,
        not plan.empty and "authorizes_submission" in plan.columns,
    )
    if not all(required_claims):
        return False
    return bool(
        not _bool(config.get("authorizes_submission", True))
        and not _bool(extra.get("authorizes_submission", True))
        and not summary["authorizes_submission"].map(_bool).any()
        and not plan["authorizes_submission"].map(_bool).any()
    )


def _lineage(config: dict[str, Any]) -> dict[str, Any]:
    proof_refresh = _mapping(config.get("proof_freshness"))
    proof_refresh_manifest = _mapping(
        proof_refresh.get("manifest")
    )
    proof_refresh_semantic = _mapping(
        proof_refresh.get("semantic_verification")
    )
    portfolio = _mapping(config.get("strategy_portfolio"))
    scorecard = _mapping(portfolio.get("scorecard_provenance"))
    family = _mapping(portfolio.get("research_family"))
    broker_readiness = _mapping(config.get("broker_readiness"))
    broker_lineage = _mapping(broker_readiness.get("lineage"))
    lineage_state = {
        "proof_refresh_required": _bool(
            proof_refresh.get("required", False)
        ),
        "proof_refresh_requested": _bool(
            proof_refresh.get("requested", False)
        ),
        "proof_refresh_provided": _bool(
            proof_refresh.get("provided", False)
        ),
        "proof_refresh_reported_ready": _bool(
            proof_refresh.get("reported_ready", False)
        ),
        "proof_refresh_ready": _bool(
            proof_refresh.get("ready", False)
        ),
        "proof_refresh_verified": _bool(
            proof_refresh.get("verified", False)
        ),
        "proof_refresh_manifest_required": _bool(
            proof_refresh_manifest.get("required", False)
        ),
        "proof_refresh_manifest_current": _bool(
            proof_refresh_manifest.get("current", False)
        ),
        "proof_refresh_manifest_sha256": _text(
            proof_refresh_manifest.get("sha256", "")
        ),
        "proof_refresh_semantic_verification_required": _bool(
            proof_refresh_semantic.get("required", False)
        ),
        "proof_refresh_semantically_verified": _bool(
            proof_refresh_semantic.get("verified", False)
        ),
        "proof_refresh_verification_inputs_current": _bool(
            proof_refresh_semantic.get("inputs_current", False)
        ),
        "proof_refresh_verification_artifacts_consistent": _bool(
            proof_refresh_semantic.get(
                "artifacts_consistent",
                False,
            )
        ),
        "proof_refresh_verification_non_authorizing": _bool(
            proof_refresh_semantic.get("non_authorizing", False)
        ),
        "proof_refresh_verification_error": _text(
            proof_refresh_semantic.get("error", "")
        ),
        "proof_refresh_read_error": _text(
            proof_refresh.get("read_error", "")
        ),
        "proof_refresh_reason": _text(
            proof_refresh.get("reason", "")
        ),
        "strategy_portfolio_required": _bool(portfolio.get("required", False)),
        "strategy_portfolio_provided": _bool(portfolio.get("provided", False)),
        "strategy_portfolio_manifest_required": _bool(
            portfolio.get("manifest_required", False)
        ),
        "strategy_portfolio_manifest_current": _bool(
            portfolio.get("manifest_current", False)
        ),
        "strategy_portfolio_manifest_sha256": _text(
            portfolio.get("manifest_sha256", "")
        ),
        "strategy_portfolio_provenance_gate_passed": _bool(
            portfolio.get("provenance_gate_passed", False)
        ),
        "scorecard_manifest_required": _bool(scorecard.get("manifest_required", False)),
        "scorecard_manifest_current": _bool(scorecard.get("manifest_current", False)),
        "scorecard_manifest_sha256": _text(scorecard.get("manifest_sha256", "")),
        "scorecard_provenance_gate_passed": _bool(scorecard.get("gate_passed", False)),
        "research_family_bound": _bool(family.get("bound", False)),
        "research_family_provenance_current": _bool(
            family.get("provenance_current", False)
        ),
        "research_family_id": _text(family.get("family_id", "")),
        "research_family_registration_id": _text(family.get("registration_id", "")),
        "research_family_manifest_sha256": _text(family.get("manifest_sha256", "")),
        "broker_readiness_required": _bool(
            broker_readiness.get("required", False)
        ),
        "broker_readiness_provided": _bool(
            broker_readiness.get("provided", False)
        ),
        "broker_readiness_lineage_required": _bool(
            broker_lineage.get("lineage_required", False)
        ),
        "broker_readiness_lineage_provided": _bool(
            broker_lineage.get("lineage_provided", False)
        ),
        "broker_readiness_manifest_current": _bool(
            broker_lineage.get("manifest_current", False)
        ),
        "broker_readiness_manifest_run_type": _text(
            broker_lineage.get("manifest_run_type", "")
        ),
        "broker_readiness_manifest_path": _text(
            broker_lineage.get("manifest_path", "")
        ),
        "broker_readiness_manifest_sha256": _text(
            broker_lineage.get("manifest_sha256", "")
        ),
        "broker_readiness_manifest_error": _text(
            broker_lineage.get("manifest_error", "")
        ),
        "broker_readiness_lineage_contract_consistent": _bool(
            broker_lineage.get("lineage_contract_consistent", False)
        ),
        "broker_readiness_lineage_contract_error": _text(
            broker_lineage.get("lineage_contract_error", "")
        ),
        "broker_readiness_roundtrip_lineage_required": _bool(
            broker_lineage.get("roundtrip_lineage_required", False)
        ),
        "broker_readiness_roundtrip_lineage_gate_passed": _bool(
            broker_lineage.get("roundtrip_lineage_gate_passed", False)
        ),
        "broker_readiness_roundtrip_matches_current": _bool(
            broker_lineage.get("roundtrip_matches_current", False)
        ),
        "broker_readiness_lineage_gate_passed": _bool(
            broker_lineage.get("lineage_gate_passed", False)
        ),
        "broker_readiness_lineage_dependency_count": _integer(
            broker_lineage.get("lineage_dependency_count", 0)
        ),
    }
    lineage_state.update(
        {
            report_field: _broker_readiness_contract_identity_value(
                broker_lineage,
                config_field,
                report_field,
            )
            for (
                config_field,
                report_field,
            ) in BROKER_READINESS_IDENTITY_LINEAGE_FIELDS
        }
    )
    return lineage_state


def _broker_readiness_contract_identity_value(
    lineage: Mapping[str, Any],
    config_field: str,
    report_field: str,
) -> Any:
    return _broker_readiness_contract_identity_normalize(
        lineage.get(config_field),
        report_field,
    )


def _broker_readiness_contract_identity_normalize(
    value: Any,
    report_field: str,
) -> Any:
    if report_field.endswith("_orders"):
        return _integer(value)
    if report_field.endswith(("_sha256", "_error")):
        return _text(value)
    return _bool(value)


def _broker_readiness_contract_identity_present(
    value: Any,
    report_field: str,
) -> bool:
    if report_field.endswith("_orders"):
        return _integer(value) > 0
    if report_field.endswith(("_sha256", "_error")):
        return bool(_text(value))
    return _bool(value)


def _broker_readiness_active(
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    broker_readiness = _mapping(config.get("broker_readiness"))
    lineage = _mapping(broker_readiness.get("lineage"))
    inputs = _mapping(manifest.get("inputs"))
    return bool(
        _bool(broker_readiness.get("required", False))
        or _bool(broker_readiness.get("provided", False))
        or _bool(lineage.get("lineage_required", False))
        or _bool(lineage.get("lineage_provided", False))
        or _bool(
            lineage.get(
                "roundtrip_contract_identity_active",
                False,
            )
        )
        or bool(
            _text(
                lineage.get(
                    "roundtrip_contract_identity_sha256",
                    "",
                )
            )
        )
        or any(
            _manifest_input_is_fingerprint(inputs.get(name))
            for name in (
                "broker_readiness",
                "broker_readiness_config",
                "broker_readiness_manifest",
            )
        )
    )


def _proof_refresh_active(
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    proof_refresh = _mapping(config.get("proof_freshness"))
    refresh_manifest = _mapping(proof_refresh.get("manifest"))
    semantic = _mapping(
        proof_refresh.get("semantic_verification")
    )
    parameters = _mapping(manifest.get("parameters"))
    thresholds = _mapping(parameters.get("thresholds"))
    inputs = _mapping(manifest.get("inputs"))
    return bool(
        _bool(proof_refresh.get("required", False))
        or _bool(proof_refresh.get("requested", False))
        or _bool(proof_refresh.get("provided", False))
        or _bool(refresh_manifest.get("required", False))
        or _bool(semantic.get("required", False))
        or _bool(thresholds.get("require_proof_refresh", False))
        or _manifest_input_is_fingerprint(
            inputs.get("proof_refresh")
        )
    )


def _manifest_input_is_fingerprint(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(_text(value.get("path")))


def _load_broker_readiness_lineage(config_path: str | Path) -> dict[str, Any]:
    from reports.operational_lineage import load_broker_readiness_lineage

    return load_broker_readiness_lineage(config_path)


def _broker_readiness_lineage_fields(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    from reports.operational_lineage import broker_readiness_lineage_fields

    return broker_readiness_lineage_fields(lineage)


def _manifest_input_path(manifest: dict[str, Any], name: str) -> Path | None:
    value = _mapping(manifest.get("inputs")).get(name)
    if isinstance(value, Mapping):
        return _existing_path(value.get("path"))
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return _bool(actual) == expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if pd.isna(actual_number) and pd.isna(expected_number):
            return True
        return abs(actual_number - expected_number) <= 1e-9
    return _text(actual) == _text(expected)


def _proof_refresh_source_same(
    field: str,
    actual: Any,
    expected: Any,
) -> bool:
    if field == "strategy":
        return _strategy_identity(actual) == _strategy_identity(expected)
    if field == "market":
        return _identity_key(actual) == _identity_key(expected)
    return _same(actual, expected)


def _strategy_identity(value: Any) -> str:
    key = _identity_key(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice": "imbalance",
        "microprice_imbalance": "imbalance",
        "order_book_imbalance": "imbalance",
        "obi": "imbalance",
        "surface": "surface_mm",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(key, key)


def _identity_key(value: Any) -> str:
    return (
        _text(value)
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
    )


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _integer(value: Any, *, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


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
