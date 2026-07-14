from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from adapters.reviewed_mapped_data import (
    ApprovedMappingReviewInputs,
    approved_mapping_review_inputs,
)
from adapters.vendor_mapping_review import (
    RECEIPT_FILE as MAPPING_REVIEW_RECEIPT_FILE,
    verify_vendor_mapping_review,
)
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "vendor_mapping_scope_review"
CONTRACT_VERSION = "vendor_mapping_scope_review/v1"
REUSE_SCOPE = "exact_header"
CHECKS_FILE = "vendor_mapping_scope_review_checks.csv"
ACTION_QUEUE_FILE = "vendor_mapping_scope_review_action_queue.csv"
SUMMARY_FILE = "vendor_mapping_scope_review_summary.csv"
RECEIPT_FILE = "vendor_mapping_scope_review_receipt.json"
CONFIG_FILE = "vendor_mapping_scope_review_config.json"
RUNBOOK_FILE = "vendor_mapping_scope_review_runbook.md"
STATIC_ARTIFACTS = (
    CHECKS_FILE,
    ACTION_QUEUE_FILE,
    SUMMARY_FILE,
    RECEIPT_FILE,
    CONFIG_FILE,
    RUNBOOK_FILE,
)
CHECK_COLUMNS = (
    "check",
    "component",
    "value",
    "operator",
    "expected",
    "passed",
    "reason",
)
ACTION_QUEUE_COLUMNS = (
    "priority",
    "queue_status",
    "check",
    "component",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
)
ATTESTATION_COLUMNS = (
    "vendor_documentation_checked",
    "schema_stability_confirmed",
    "field_semantics_stable_across_files_confirmed",
    "timestamp_semantics_stable_across_files_confirmed",
    "price_quantity_units_stable_across_files_confirmed",
    "transform_semantics_stable_across_files_confirmed",
    "partitioning_semantics_confirmed",
)
DECISION_COLUMNS = (
    "mapping_review_id",
    "mapping_review_sha256",
    "reviewed_mapping_sha256",
    "source_header_sha256",
    "adapter",
    "kind",
    "reuse_scope",
    "decision",
    "operator_id",
    "operator_role",
    "reviewed_at_utc",
    *ATTESTATION_COLUMNS,
    "notes",
    "authorizes_header_scoped_application",
    "authorizes_routing",
    "authorizes_submission",
)


@dataclass(frozen=True)
class VendorMappingScopeReviewConfig:
    output_mapping_file: str = "scope_approved_vendor_mapping.csv"


@dataclass(frozen=True)
class VendorMappingScopeReviewReport:
    checks: pd.DataFrame
    mapping: pd.DataFrame
    action_queue: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def sealed(self) -> bool:
        return bool(not self.summary.empty and _bool(self.summary.iloc[0].get("sealed")))

    @property
    def approved(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("approved_for_header_scoped_application"))
        )


@dataclass(frozen=True)
class VendorMappingScopeReviewVerification:
    verified: bool
    sealed: bool
    approved: bool
    rejected: bool
    manifest_current: bool
    mapping_review_current: bool
    operator_decision_current: bool
    artifacts_consistent: bool
    application_only: bool
    non_routing: bool
    output_dir: Path
    mapping_review_dir: Path | None = None
    operator_decision_path: Path | None = None
    error: str = ""


def write_vendor_mapping_scope_review(
    mapping_review_dir: str | Path,
    operator_decision_path: str | Path,
    output_dir: str | Path,
    *,
    config: VendorMappingScopeReviewConfig | None = None,
) -> VendorMappingScopeReviewReport:
    config = config or VendorMappingScopeReviewConfig()
    _validate_config(config)
    review_root = Path(mapping_review_dir).resolve()
    decision_path = Path(operator_decision_path).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"vendor mapping scope-review output already exists: {out}")
    if not decision_path.is_file():
        raise FileNotFoundError(f"mapping scope operator decision not found: {decision_path}")
    _reject_collisions(out, review_root=review_root, decision_path=decision_path)
    review = approved_mapping_review_inputs(review_root)
    decision_sha256 = file_sha256(decision_path)
    review_manifest_sha256 = file_sha256(review_root / MANIFEST_NAME)
    reviewed_mapping_sha256 = file_sha256(review.reviewed_mapping_path)
    report = _assemble_report(
        review=review,
        decision=_read_csv(decision_path, "mapping scope operator decision"),
        config=config,
    )

    out.mkdir(parents=True)
    _write_csv(report.checks, out / CHECKS_FILE)
    shutil.copyfile(
        review.reviewed_mapping_path,
        out / config.output_mapping_file,
    )
    _write_csv(report.action_queue, out / ACTION_QUEUE_FILE)
    _write_csv(report.summary, out / SUMMARY_FILE)
    _write_json(out / RECEIPT_FILE, report.receipt)
    _write_json(out / CONFIG_FILE, report.config)
    (out / RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], report.checks, report.action_queue),
        encoding="utf-8",
    )

    final_review = verify_vendor_mapping_review(review_root)
    if (
        not final_review.verified
        or not final_review.approved
        or file_sha256(decision_path) != decision_sha256
        or file_sha256(review_root / MANIFEST_NAME) != review_manifest_sha256
        or file_sha256(review.reviewed_mapping_path) != reviewed_mapping_sha256
    ):
        raise RuntimeError("mapping review or scope decision changed while sealing scope review")
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "mapping_review": review_root,
            "mapping_review_manifest": review_root / MANIFEST_NAME,
            "mapping_review_receipt": review_root / MAPPING_REVIEW_RECEIPT_FILE,
            "reviewed_mapping": review.reviewed_mapping_path,
            "review_seed_source": review.source_path,
            "operator_decision": decision_path,
        },
        extra=_manifest_extra(report),
    )
    return VendorMappingScopeReviewReport(
        checks=report.checks,
        mapping=report.mapping,
        action_queue=report.action_queue,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_vendor_mapping_scope_review(
    scope_review_dir: str | Path,
) -> VendorMappingScopeReviewVerification:
    root = Path(scope_review_dir).resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=STATIC_ARTIFACTS,
        require_input_fingerprints=True,
    )
    review_root: Path | None = None
    decision_path: Path | None = None
    mapping_review_current = False
    decision_current = False
    try:
        manifest = _read_json(manifest_path, "mapping scope-review manifest")
        config = _config_from_manifest(manifest)
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=RUN_TYPE,
            required_artifacts=(*STATIC_ARTIFACTS, config.output_mapping_file),
            require_input_fingerprints=True,
        )
        inputs = _mapping(manifest.get("inputs"))
        review_root = _fingerprint_path(inputs.get("mapping_review"), "directory")
        decision_path = _fingerprint_path(inputs.get("operator_decision"), "file")
        review = approved_mapping_review_inputs(review_root)
        mapping_review_current = True
        decision_current = _fingerprint_current(inputs.get("operator_decision"), decision_path)
        if not decision_current:
            raise ValueError("mapping scope operator decision fingerprint is stale")
        if not _manifest_input_contract_current(
            inputs,
            review=review,
            decision_path=decision_path,
        ):
            raise ValueError("mapping scope-review manifest input contract is inconsistent")

        expected = _assemble_report(
            review=review,
            decision=_read_csv(decision_path, "mapping scope operator decision"),
            config=config,
        )
        actual_checks = _read_csv(root / CHECKS_FILE, "mapping scope-review checks")
        actual_mapping = _read_csv(
            root / config.output_mapping_file,
            "scope-approved vendor mapping",
        )
        actual_action_queue = _read_csv(
            root / ACTION_QUEUE_FILE,
            "mapping scope-review action queue",
        )
        actual_summary = _read_csv(root / SUMMARY_FILE, "mapping scope-review summary")
        actual_receipt = _read_json(root / RECEIPT_FILE, "mapping scope-review receipt")
        actual_config = _read_json(root / CONFIG_FILE, "mapping scope-review config")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        artifacts_consistent = bool(
            _frame_equal(actual_checks, expected.checks)
            and _frame_equal(actual_mapping, expected.mapping)
            and (root / config.output_mapping_file).read_bytes()
            == review.reviewed_mapping_path.read_bytes()
            and _frame_equal(actual_action_queue, expected.action_queue)
            and _frame_equal(actual_summary, expected.summary)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config)
            and actual_runbook
            == _runbook_markdown(
                expected.summary.iloc[0],
                expected.checks,
                expected.action_queue,
            )
            and _jsonable(manifest.get("parameters"))
            == {"config": _jsonable(asdict(config))}
            and _jsonable(manifest.get("extra"))
            == _jsonable(_manifest_extra(expected))
        )
        application_only = _surfaces_application_only(
            actual_summary.iloc[0],
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        non_routing = _surfaces_non_routing(
            actual_summary.iloc[0],
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        approved = expected.approved
        verified = bool(
            integrity.passed
            and mapping_review_current
            and decision_current
            and artifacts_consistent
            and application_only
            and non_routing
        )
        return VendorMappingScopeReviewVerification(
            verified=verified,
            sealed=verified,
            approved=bool(verified and approved),
            rejected=bool(verified and not approved),
            manifest_current=integrity.passed,
            mapping_review_current=mapping_review_current,
            operator_decision_current=decision_current,
            artifacts_consistent=artifacts_consistent,
            application_only=application_only,
            non_routing=non_routing,
            output_dir=root,
            mapping_review_dir=review_root,
            operator_decision_path=decision_path,
            error="" if verified else (integrity.error or "mapping scope-review verification failed"),
        )
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return _failed_verification(
            root,
            review_root=review_root,
            decision_path=decision_path,
            manifest_current=integrity.passed,
            mapping_review_current=mapping_review_current,
            decision_current=decision_current,
            error=str(exc),
        )


def _assemble_report(
    *,
    review: ApprovedMappingReviewInputs,
    decision: pd.DataFrame,
    config: VendorMappingScopeReviewConfig,
) -> VendorMappingScopeReviewReport:
    row = _single_row(decision, "mapping scope operator decision")
    checks = _decision_checks(review, decision, row)
    failed = checks.loc[~checks["passed"].map(_bool)]
    if not failed.empty:
        raise ValueError(
            "mapping scope operator decision contract failed: "
            + ", ".join(failed["check"].astype(str).tolist())
        )
    approved = _identity(row.get("decision")) == "approved"
    mapping = _read_csv(review.reviewed_mapping_path, "reviewed vendor mapping")
    receipt_core = _receipt_core(
        review=review,
        operator_row=row,
        approved=approved,
        checks=checks,
        config=config,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "mapping_scope_review_id": f"vendor-mapping-scope-{receipt_sha256[:24]}",
        "mapping_scope_review_sha256": receipt_sha256,
    }
    action_queue = _action_queue(approved)
    summary = _summary(receipt, checks, action_queue)
    config_payload = _config_payload(
        config=config,
        review=review,
        receipt=receipt,
        action_queue=action_queue,
    )
    return VendorMappingScopeReviewReport(
        checks=checks,
        mapping=mapping,
        action_queue=action_queue,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _decision_checks(
    review: ApprovedMappingReviewInputs,
    decision: pd.DataFrame,
    row: pd.Series,
) -> pd.DataFrame:
    checks = [
        _check(
            "operator_columns_known",
            "operator",
            ";".join(sorted(str(column) for column in decision.columns)),
            "set_equals",
            ";".join(sorted(DECISION_COLUMNS)),
            set(decision.columns) == set(DECISION_COLUMNS),
            "operator decision columns are incomplete or include unknown claims",
        ),
        _binding_check("mapping_review_id", row, review.mapping_review_id),
        _binding_check("mapping_review_sha256", row, review.mapping_review_sha256),
        _binding_check(
            "reviewed_mapping_sha256",
            row,
            review.reviewed_mapping_sha256,
        ),
        _binding_check("source_header_sha256", row, review.source_header_sha256),
        _binding_check("adapter", row, review.adapter, identity=True),
        _binding_check("kind", row, review.kind, identity=True),
        _binding_check("reuse_scope", row, REUSE_SCOPE, identity=True),
    ]
    decision_value = _identity(row.get("decision"))
    checks.extend(
        [
            _check(
                "decision_valid",
                "operator",
                decision_value,
                "in",
                "approved;rejected",
                decision_value in {"approved", "rejected"},
                "scope decision must be approved or rejected",
            ),
            _nonempty_check("operator_id", row),
            _nonempty_check("operator_role", row),
            _check(
                "reviewed_at_utc_valid",
                "operator",
                _text(row.get("reviewed_at_utc")),
                "is",
                "strict_utc_timestamp",
                _is_strict_utc(row.get("reviewed_at_utc")),
                "reviewed_at_utc must be an explicit UTC timestamp",
            ),
            _nonempty_check("notes", row),
        ]
    )
    for column in ATTESTATION_COLUMNS:
        checks.append(
            _check(
                f"{column}_attested",
                "operator",
                row.get(column),
                "is",
                True,
                _explicit_bool(row.get(column)) is True,
                f"{column} must be explicitly attested",
            )
        )
    expected_application = decision_value == "approved"
    checks.extend(
        [
            _check(
                "header_scoped_application_authority_consistent",
                "operator",
                row.get("authorizes_header_scoped_application"),
                "is",
                expected_application,
                _explicit_bool(row.get("authorizes_header_scoped_application"))
                is expected_application,
                "application authority must match the approved/rejected decision",
            ),
            _check(
                "routing_not_authorized",
                "safety",
                row.get("authorizes_routing"),
                "is",
                False,
                _explicit_bool(row.get("authorizes_routing")) is False,
                "mapping scope review cannot authorize routing",
            ),
            _check(
                "submission_not_authorized",
                "safety",
                row.get("authorizes_submission"),
                "is",
                False,
                _explicit_bool(row.get("authorizes_submission")) is False,
                "mapping scope review cannot authorize submission",
            ),
        ]
    )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _binding_check(
    field: str,
    row: pd.Series,
    expected: str,
    *,
    identity: bool = False,
) -> dict[str, Any]:
    actual = _identity(row.get(field)) if identity else _text(row.get(field))
    return _check(
        f"{field}_matches",
        "binding",
        actual,
        "==",
        expected,
        bool(actual and actual == expected),
        f"operator decision {field} does not match the approved mapping review",
    )


def _nonempty_check(field: str, row: pd.Series) -> dict[str, Any]:
    value = _text(row.get(field))
    return _check(
        f"{field}_present",
        "operator",
        value,
        "nonempty",
        True,
        bool(value),
        f"operator decision {field} is required",
    )


def _check(
    check: str,
    component: str,
    value: Any,
    operator: str,
    expected: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "component": component,
        "value": value,
        "operator": operator,
        "expected": expected,
        "passed": bool(passed),
        "reason": reason,
    }


def _receipt_core(
    *,
    review: ApprovedMappingReviewInputs,
    operator_row: pd.Series,
    approved: bool,
    checks: pd.DataFrame,
    config: VendorMappingScopeReviewConfig,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "operator_attested_vendor_mapping_scope_review",
        "sealed": True,
        "decision": "approved" if approved else "rejected",
        "approved_for_header_scoped_application": approved,
        "identity": {
            "adapter": review.adapter,
            "kind": review.kind,
        },
        "scope": {
            "reuse_scope": REUSE_SCOPE,
            "source_header_sha256": review.source_header_sha256,
            "header_order_sensitive": True,
            "exact_header_match_required": True,
        },
        "mapping_review": {
            "path": str(review.mapping_review_dir),
            "mapping_review_id": review.mapping_review_id,
            "mapping_review_sha256": review.mapping_review_sha256,
            "seed_source_path": str(review.source_path),
            "seed_source_sha256": review.source_file_sha256,
        },
        "mapping": {
            "source_path": str(review.reviewed_mapping_path),
            "reviewed_sha256": review.reviewed_mapping_sha256,
            "output_file": config.output_mapping_file,
        },
        "operator": {
            "operator_id": _text(operator_row.get("operator_id")),
            "operator_role": _text(operator_row.get("operator_role")),
            "reviewed_at_utc": _text(operator_row.get("reviewed_at_utc")),
            "attestations": {column: True for column in ATTESTATION_COLUMNS},
            "notes": _text(operator_row.get("notes")),
        },
        "outcome": {
            "check_count": int(len(checks)),
            "failed_check_count": 0,
            "failed_check_names": [],
        },
        "safety": _safety_payload(approved),
    }


def _summary(
    receipt: Mapping[str, Any],
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    approved = _bool(receipt.get("approved_for_header_scoped_application"))
    mapping_review = _mapping(receipt.get("mapping_review"))
    mapping = _mapping(receipt.get("mapping"))
    scope = _mapping(receipt.get("scope"))
    identity = _mapping(receipt.get("identity"))
    safety = _mapping(receipt.get("safety"))
    return pd.DataFrame(
        [
            {
                "ready": approved,
                "sealed": True,
                "approved_for_header_scoped_application": approved,
                "rejected": not approved,
                "decision": _text(receipt.get("decision")),
                "mapping_scope_review_id": _text(receipt.get("mapping_scope_review_id")),
                "mapping_scope_review_sha256": _text(
                    receipt.get("mapping_scope_review_sha256")
                ),
                "contract_version": CONTRACT_VERSION,
                "reuse_scope": _text(scope.get("reuse_scope")),
                "source_header_sha256": _text(scope.get("source_header_sha256")),
                "adapter": _text(identity.get("adapter")),
                "kind": _text(identity.get("kind")),
                "mapping_review_id": _text(mapping_review.get("mapping_review_id")),
                "mapping_review_sha256": _text(
                    mapping_review.get("mapping_review_sha256")
                ),
                "reviewed_mapping_sha256": _text(mapping.get("reviewed_sha256")),
                "check_count": int(len(checks)),
                "failed_check_count": 0,
                "failed_check_names": "",
                "blocked_action_count": int(len(action_queue)),
                "next_gate": "" if action_queue.empty else "review-vendor-mapping-scope",
                "next_gate_help_command": (
                    ""
                    if action_queue.empty
                    else "python -m hft_cli review-vendor-mapping-scope --help"
                ),
                **{field: value for field, value in safety.items()},
                "recommendation": (
                    "apply_mapping_to_exact_header_sources"
                    if approved
                    else "retain_rejection_or_submit_new_scope_decision"
                ),
            }
        ]
    )


def _action_queue(approved: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not approved:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "check": "mapping_scope_approved",
                "component": "operator_decision",
                "next_gate": "review-vendor-mapping-scope",
                "next_gate_help_command": (
                    "python -m hft_cli review-vendor-mapping-scope --help"
                ),
                "reason": "operator rejected exact-header mapping reuse",
                "recommendation": "retain_rejection_or_submit_new_scope_decision",
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _config_payload(
    *,
    config: VendorMappingScopeReviewConfig,
    review: ApprovedMappingReviewInputs,
    receipt: Mapping[str, Any],
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "sealed": True,
        "approved_for_header_scoped_application": _bool(
            receipt.get("approved_for_header_scoped_application")
        ),
        "mapping_scope_review_id": _text(receipt.get("mapping_scope_review_id")),
        "mapping_scope_review_sha256": _text(
            receipt.get("mapping_scope_review_sha256")
        ),
        "mapping_review": {
            "path": str(review.mapping_review_dir),
            "id": review.mapping_review_id,
            "sha256": review.mapping_review_sha256,
        },
        "scope": {
            "reuse_scope": REUSE_SCOPE,
            "source_header_sha256": review.source_header_sha256,
            "header_order_sensitive": True,
            "exact_header_match_required": True,
        },
        "mapping": {
            "source_path": str(review.reviewed_mapping_path),
            "reviewed_sha256": review.reviewed_mapping_sha256,
            "output_file": config.output_mapping_file,
        },
        "blocked_action_count": int(len(action_queue)),
        "next_gate": "" if action_queue.empty else "review-vendor-mapping-scope",
        "safety": _safety_payload(
            _bool(receipt.get("approved_for_header_scoped_application"))
        ),
    }


def _manifest_extra(report: VendorMappingScopeReviewReport) -> dict[str, Any]:
    row = report.summary.iloc[0]
    return {
        "contract_version": CONTRACT_VERSION,
        "mapping_scope_review_id": _text(row.get("mapping_scope_review_id")),
        "mapping_scope_review_sha256": _text(
            row.get("mapping_scope_review_sha256")
        ),
        "approved_for_header_scoped_application": _bool(
            row.get("approved_for_header_scoped_application")
        ),
        "scope": _mapping(report.receipt.get("scope")),
        "safety": _mapping(report.receipt.get("safety")),
    }


def _safety_payload(approved: bool) -> dict[str, bool]:
    return {
        "header_scoped_reuse_review_only": True,
        "operator_approved_scope_required": True,
        "exact_header_match_required": True,
        "header_order_sensitive": True,
        "authorizes_header_scoped_application": bool(approved),
        "authorizes_normalization": False,
        "authorizes_strategy_research": False,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "authorizes_live_release": False,
    }


def _surfaces_application_only(*surfaces: Mapping[str, Any]) -> bool:
    for surface in surfaces:
        safety = _safety_surface(surface)
        if not all(
            _explicit_bool(safety.get(field)) is True
            for field in (
                "header_scoped_reuse_review_only",
                "operator_approved_scope_required",
                "exact_header_match_required",
                "header_order_sensitive",
            )
        ):
            return False
        if _explicit_bool(safety.get("authorizes_normalization")) is not False:
            return False
    return True


def _surfaces_non_routing(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        all(
            _explicit_bool(_safety_surface(surface).get(field)) is False
            for field in (
                "authorizes_strategy_research",
                "authorizes_routing",
                "authorizes_submission",
                "authorizes_live_release",
            )
        )
        for surface in surfaces
    )


def _safety_surface(surface: Mapping[str, Any]) -> Mapping[str, Any]:
    safety = surface.get("safety")
    return safety if isinstance(safety, Mapping) else surface


def _runbook_markdown(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    failed = checks.loc[~checks["passed"].map(_bool)]
    lines = [
        "# Vendor Mapping Scope Review",
        "",
        f"- Sealed: {_yes_no(_bool(summary.get('sealed')))}",
        "- Approved for exact-header application: "
        + _yes_no(_bool(summary.get("approved_for_header_scoped_application"))),
        f"- Decision: {_text(summary.get('decision'))}",
        f"- Adapter: {_text(summary.get('adapter'))}",
        f"- Kind: {_text(summary.get('kind'))}",
        f"- Reuse scope: {_text(summary.get('reuse_scope'))}",
        f"- Source header SHA-256: `{_text(summary.get('source_header_sha256'))}`",
        f"- Mapping review ID: `{_text(summary.get('mapping_review_id'))}`",
        f"- Failed checks: {len(failed)}",
        f"- Blocked actions: {len(action_queue)}",
        "",
        "This approval covers mapping application only when a future source has",
        "the exact same ordered header. It does not authorize normalization,",
        "strategy research, routing, submission, or live release.",
        "",
    ]
    return "\n".join(lines)


def _config_from_manifest(manifest: Mapping[str, Any]) -> VendorMappingScopeReviewConfig:
    payload = _mapping(_mapping(manifest.get("parameters")).get("config"))
    expected = {field.name for field in fields(VendorMappingScopeReviewConfig)}
    if set(payload) != expected:
        raise ValueError("mapping scope-review config contract is incomplete or unknown")
    config = VendorMappingScopeReviewConfig(
        output_mapping_file=str(payload["output_mapping_file"]),
    )
    _validate_config(config)
    return config


def _validate_config(config: VendorMappingScopeReviewConfig) -> None:
    path = Path(config.output_mapping_file)
    reserved = {name.lower() for name in (*STATIC_ARTIFACTS, MANIFEST_NAME)}
    if (
        not config.output_mapping_file
        or path.is_absolute()
        or len(path.parts) != 1
        or path.name in {"", ".", ".."}
    ):
        raise ValueError("output_mapping_file must be a filename within scope-review output")
    if path.name.lower() in reserved:
        raise ValueError("output_mapping_file conflicts with a scope-review artifact")


def _reject_collisions(
    out: Path,
    *,
    review_root: Path,
    decision_path: Path,
) -> None:
    if _is_relative_to(decision_path, review_root):
        raise ValueError("scope operator decision must remain outside mapping-review evidence")
    if _is_relative_to(decision_path, out):
        raise ValueError("scope operator decision cannot be stored inside its output")
    if _is_relative_to(out, review_root):
        raise ValueError("scope-review output cannot modify mapping-review evidence")
    if _is_relative_to(review_root, out):
        raise ValueError("scope-review output cannot contain mapping-review evidence")


def _manifest_input_contract_current(
    inputs: Mapping[str, Any],
    *,
    review: ApprovedMappingReviewInputs,
    decision_path: Path,
) -> bool:
    expected = {
        "mapping_review": (review.mapping_review_dir, "directory"),
        "mapping_review_manifest": (review.mapping_review_dir / MANIFEST_NAME, "file"),
        "mapping_review_receipt": (
            review.mapping_review_dir / MAPPING_REVIEW_RECEIPT_FILE,
            "file",
        ),
        "reviewed_mapping": (review.reviewed_mapping_path, "file"),
        "review_seed_source": (review.source_path, "file"),
        "operator_decision": (decision_path, "file"),
    }
    if set(inputs) != set(expected):
        return False
    return all(
        _fingerprint_path(inputs.get(name), kind) == path.resolve()
        for name, (path, kind) in expected.items()
    )


def _fingerprint_path(value: Any, kind: str) -> Path:
    record = _mapping(value)
    if record.get("kind") != kind or not record.get("path"):
        raise ValueError(f"mapping scope-review manifest lacks a {kind} fingerprint")
    return Path(str(record["path"])).resolve()


def _fingerprint_current(value: Any, path: Path) -> bool:
    record = _mapping(value)
    return bool(
        path.is_file()
        and record.get("kind") == "file"
        and Path(str(record.get("path", ""))).resolve() == path.resolve()
        and _int(record.get("size_bytes")) == int(path.stat().st_size)
        and _text(record.get("sha256")) == file_sha256(path)
    )


def _failed_verification(
    root: Path,
    *,
    review_root: Path | None,
    decision_path: Path | None,
    manifest_current: bool,
    mapping_review_current: bool,
    decision_current: bool,
    error: str,
) -> VendorMappingScopeReviewVerification:
    return VendorMappingScopeReviewVerification(
        verified=False,
        sealed=False,
        approved=False,
        rejected=False,
        manifest_current=manifest_current,
        mapping_review_current=mapping_review_current,
        operator_decision_current=decision_current,
        artifacts_consistent=False,
        application_only=False,
        non_routing=False,
        output_dir=root,
        mapping_review_dir=review_root,
        operator_decision_path=decision_path,
        error=error,
    )


def _is_strict_utc(value: Any) -> bool:
    text = _text(value)
    if not text or (not text.endswith("Z") and "+00:00" not in text):
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return bool(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed))


def _explicit_bool(value: Any) -> bool | None:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        if float(value) in {0.0, 1.0}:
            return bool(value)
    return None


def _frame_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    if list(left.columns) != list(right.columns) or len(left) != len(right):
        return False
    for left_row, right_row in zip(
        left.itertuples(index=False, name=None),
        right.itertuples(index=False, name=None),
    ):
        for left_value, right_value in zip(left_row, right_row):
            left_missing = _missing(left_value)
            right_missing = _missing(right_value)
            if left_missing or right_missing:
                if left_missing != right_missing:
                    return False
                continue
            if isinstance(left_value, Real) and isinstance(right_value, Real):
                if not math.isclose(
                    float(left_value),
                    float(right_value),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    return False
            elif str(left_value) != str(right_value):
                return False
    return True


def _missing(value: Any) -> bool:
    if value is None or (
        isinstance(value, str) and value.strip().lower() in {"", "nan"}
    ):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): _jsonable(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.write_bytes(frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _identity(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    parsed = _explicit_bool(value)
    return bool(parsed) if parsed is not None else False


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
