from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict, dataclass, fields
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from adapters.vendor_intake import (
    RECEIPT_FILE as INTAKE_RECEIPT_FILE,
    SOURCE_PROFILE_FILE as INTAKE_SOURCE_PROFILE_FILE,
    verify_vendor_csv_intake_report,
)
from adapters.vendor_mapping_scope_review import (
    ApprovedMappingScopeReviewInputs,
    RECEIPT_FILE as SCOPE_REVIEW_RECEIPT_FILE,
    approved_mapping_scope_review_inputs,
)
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "vendor_mapping_target_application"
CONTRACT_VERSION = "vendor_mapping_target_application/v1"
CHECKS_FILE = "vendor_mapping_application_checks.csv"
ACTION_QUEUE_FILE = "vendor_mapping_application_action_queue.csv"
SUMMARY_FILE = "vendor_mapping_application_summary.csv"
RECEIPT_FILE = "vendor_mapping_application_receipt.json"
CONFIG_FILE = "vendor_mapping_application_config.json"
RUNBOOK_FILE = "vendor_mapping_application_runbook.md"
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


@dataclass(frozen=True)
class VendorMappingApplicationConfig:
    output_mapping_file: str = "target_applied_vendor_mapping.csv"


@dataclass(frozen=True)
class VerifiedVendorIntakeInputs:
    intake_dir: Path
    source_path: Path
    adapter: str
    requested_kind: str
    best_kind: str
    intake_receipt_id: str
    intake_receipt_sha256: str
    source_file_sha256: str
    source_header_sha256: str


@dataclass(frozen=True)
class ApprovedVendorMappingApplicationInputs:
    application_dir: Path
    scope_review_dir: Path
    target_intake_dir: Path
    target_source_path: Path
    applied_mapping_path: Path
    adapter: str
    kind: str
    mapping_application_id: str
    mapping_application_sha256: str
    mapping_scope_review_id: str
    mapping_scope_review_sha256: str
    target_intake_receipt_id: str
    target_source_file_sha256: str
    source_header_sha256: str
    reviewed_mapping_sha256: str


@dataclass(frozen=True)
class VendorMappingApplicationReport:
    checks: pd.DataFrame
    mapping: pd.DataFrame
    action_queue: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(not self.summary.empty and _bool(self.summary.iloc[0].get("ready")))


@dataclass(frozen=True)
class VendorMappingApplicationVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    scope_review_current: bool
    target_intake_current: bool
    target_source_current: bool
    artifacts_consistent: bool
    target_bound: bool
    application_only: bool
    non_routing: bool
    output_dir: Path
    scope_review_dir: Path | None = None
    target_intake_dir: Path | None = None
    target_source_path: Path | None = None
    error: str = ""


def approved_vendor_mapping_application_inputs(
    application_dir: str | Path,
) -> ApprovedVendorMappingApplicationInputs:
    """Resolve only a verified, target-bound mapping application."""
    root = Path(application_dir).resolve()
    verification = verify_vendor_mapping_application(root)
    if not verification.verified or not verification.ready:
        raise ValueError(
            "mapping normalization requires a verified ready target application: "
            f"{verification.error}"
        )
    receipt = _read_json(root / RECEIPT_FILE, "mapping application receipt")
    identity = _mapping(receipt.get("identity"))
    application = _mapping(receipt.get("application"))
    scope_review = _mapping(receipt.get("scope_review"))
    target_intake = _mapping(receipt.get("target_intake"))
    target_source = _mapping(receipt.get("target_source"))
    mapping = _mapping(receipt.get("mapping"))
    output_name = _text(mapping.get("output_file"))
    output_path = Path(output_name)
    if (
        not output_name
        or output_path.is_absolute()
        or len(output_path.parts) != 1
        or output_path.name in {"", ".", ".."}
    ):
        raise ValueError("mapping application does not name a safe output mapping")
    applied_mapping_path = (root / output_path.name).resolve()
    scope_root = Path(_text(scope_review.get("path"))).resolve()
    intake_root = Path(_text(target_intake.get("path"))).resolve()
    source_path = Path(_text(target_source.get("path"))).resolve()
    adapter = _identity(identity.get("adapter"))
    kind = _identity(identity.get("kind"))
    application_id = _text(application.get("id"))
    application_sha256 = _text(application.get("sha256"))
    scope_review_id = _text(scope_review.get("id"))
    scope_review_sha256 = _text(scope_review.get("sha256"))
    intake_receipt_id = _text(target_intake.get("receipt_id"))
    source_file_sha256 = _text(target_source.get("file_sha256"))
    source_header_sha256 = _text(target_source.get("header_sha256"))
    reviewed_mapping_sha256 = _text(mapping.get("reviewed_sha256"))
    if not all(
        (
            applied_mapping_path.is_file(),
            scope_root.is_dir(),
            intake_root.is_dir(),
            source_path.is_file(),
            adapter,
            kind,
            application_id,
            application_sha256,
            scope_review_id,
            scope_review_sha256,
            intake_receipt_id,
            source_file_sha256,
            source_header_sha256,
            reviewed_mapping_sha256,
        )
    ):
        raise ValueError("mapping application identity or fingerprints are incomplete")
    if file_sha256(source_path) != source_file_sha256:
        raise ValueError("mapping application target source fingerprint is stale")
    if file_sha256(applied_mapping_path) != reviewed_mapping_sha256:
        raise ValueError("mapping application mapping fingerprint is stale")
    if (
        verification.scope_review_dir != scope_root
        or verification.target_intake_dir != intake_root
        or verification.target_source_path != source_path
    ):
        raise ValueError("mapping application retained input paths are inconsistent")
    return ApprovedVendorMappingApplicationInputs(
        application_dir=root,
        scope_review_dir=scope_root,
        target_intake_dir=intake_root,
        target_source_path=source_path,
        applied_mapping_path=applied_mapping_path,
        adapter=adapter,
        kind=kind,
        mapping_application_id=application_id,
        mapping_application_sha256=application_sha256,
        mapping_scope_review_id=scope_review_id,
        mapping_scope_review_sha256=scope_review_sha256,
        target_intake_receipt_id=intake_receipt_id,
        target_source_file_sha256=source_file_sha256,
        source_header_sha256=source_header_sha256,
        reviewed_mapping_sha256=reviewed_mapping_sha256,
    )


def write_vendor_mapping_application(
    scope_review_dir: str | Path,
    target_intake_dir: str | Path,
    output_dir: str | Path,
    *,
    config: VendorMappingApplicationConfig | None = None,
) -> VendorMappingApplicationReport:
    config = config or VendorMappingApplicationConfig()
    _validate_config(config)
    scope_root = Path(scope_review_dir).resolve()
    intake_root = Path(target_intake_dir).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"vendor mapping application output already exists: {out}")
    scope = approved_mapping_scope_review_inputs(scope_root)
    intake = _verified_intake_inputs(intake_root)
    _reject_collisions(
        out,
        scope_root=scope_root,
        intake_root=intake_root,
        source_path=intake.source_path,
    )
    scope_manifest_sha256 = file_sha256(scope_root / MANIFEST_NAME)
    intake_manifest_sha256 = file_sha256(intake_root / MANIFEST_NAME)
    source_sha256 = file_sha256(intake.source_path)
    mapping_sha256 = file_sha256(scope.scoped_mapping_path)
    report = _assemble_report(scope=scope, intake=intake, config=config)

    out.mkdir(parents=True)
    _write_csv(report.checks, out / CHECKS_FILE)
    shutil.copyfile(scope.scoped_mapping_path, out / config.output_mapping_file)
    _write_csv(report.action_queue, out / ACTION_QUEUE_FILE)
    _write_csv(report.summary, out / SUMMARY_FILE)
    _write_json(out / RECEIPT_FILE, report.receipt)
    _write_json(out / CONFIG_FILE, report.config)
    (out / RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], report.checks),
        encoding="utf-8",
    )

    final_scope = approved_mapping_scope_review_inputs(scope_root)
    final_intake = _verified_intake_inputs(intake_root)
    if (
        file_sha256(scope_root / MANIFEST_NAME) != scope_manifest_sha256
        or file_sha256(intake_root / MANIFEST_NAME) != intake_manifest_sha256
        or file_sha256(final_intake.source_path) != source_sha256
        or file_sha256(final_scope.scoped_mapping_path) != mapping_sha256
        or final_scope != scope
        or final_intake != intake
    ):
        raise RuntimeError(
            "mapping scope review, target intake, source, or mapping changed while applying"
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "scope_review": scope_root,
            "scope_review_manifest": scope_root / MANIFEST_NAME,
            "scope_review_receipt": scope_root / SCOPE_REVIEW_RECEIPT_FILE,
            "scope_mapping": scope.scoped_mapping_path,
            "target_intake": intake_root,
            "target_intake_manifest": intake_root / MANIFEST_NAME,
            "target_intake_receipt": intake_root / INTAKE_RECEIPT_FILE,
            "target_intake_source_profile": (
                intake_root / INTAKE_SOURCE_PROFILE_FILE
            ),
            "target_source": intake.source_path,
        },
        extra=_manifest_extra(report),
    )
    return VendorMappingApplicationReport(
        checks=report.checks,
        mapping=report.mapping,
        action_queue=report.action_queue,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_vendor_mapping_application(
    application_dir: str | Path,
) -> VendorMappingApplicationVerification:
    root = Path(application_dir).resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=STATIC_ARTIFACTS,
        require_input_fingerprints=True,
    )
    scope_root: Path | None = None
    intake_root: Path | None = None
    source_path: Path | None = None
    scope_current = False
    intake_current = False
    source_current = False
    try:
        manifest = _read_json(manifest_path, "mapping application manifest")
        config = _config_from_manifest(manifest)
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=RUN_TYPE,
            required_artifacts=(*STATIC_ARTIFACTS, config.output_mapping_file),
            require_input_fingerprints=True,
        )
        inputs = _mapping(manifest.get("inputs"))
        scope_root = _fingerprint_path(inputs.get("scope_review"), "directory")
        intake_root = _fingerprint_path(inputs.get("target_intake"), "directory")
        source_path = _fingerprint_path(inputs.get("target_source"), "file")
        scope = approved_mapping_scope_review_inputs(scope_root)
        scope_current = True
        intake = _verified_intake_inputs(intake_root)
        intake_current = True
        source_current = _fingerprint_current(inputs.get("target_source"), source_path)
        if not source_current:
            raise ValueError("mapping application target source fingerprint is stale")
        if not _manifest_input_contract_current(
            inputs,
            scope=scope,
            intake=intake,
        ):
            raise ValueError("mapping application manifest input contract is inconsistent")

        expected = _assemble_report(scope=scope, intake=intake, config=config)
        actual_checks = _read_csv(root / CHECKS_FILE, "mapping application checks")
        actual_mapping = _read_csv(
            root / config.output_mapping_file,
            "target-applied vendor mapping",
        )
        actual_actions = _read_csv(
            root / ACTION_QUEUE_FILE,
            "mapping application action queue",
        )
        actual_summary = _read_csv(root / SUMMARY_FILE, "mapping application summary")
        actual_receipt = _read_json(root / RECEIPT_FILE, "mapping application receipt")
        actual_config = _read_json(root / CONFIG_FILE, "mapping application config")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        artifacts_consistent = bool(
            _frame_equal(actual_checks, expected.checks)
            and _frame_equal(actual_mapping, expected.mapping)
            and (root / config.output_mapping_file).read_bytes()
            == scope.scoped_mapping_path.read_bytes()
            and _frame_equal(actual_actions, expected.action_queue)
            and _frame_equal(actual_summary, expected.summary)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config)
            and actual_runbook
            == _runbook_markdown(expected.summary.iloc[0], expected.checks)
            and _jsonable(manifest.get("parameters"))
            == {"config": _jsonable(asdict(config))}
            and _jsonable(manifest.get("extra"))
            == _jsonable(_manifest_extra(expected))
        )
        target_bound = _surfaces_target_bound(
            actual_summary.iloc[0],
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
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
        verified = bool(
            integrity.passed
            and scope_current
            and intake_current
            and source_current
            and artifacts_consistent
            and target_bound
            and application_only
            and non_routing
        )
        return VendorMappingApplicationVerification(
            verified=verified,
            ready=verified,
            manifest_current=integrity.passed,
            scope_review_current=scope_current,
            target_intake_current=intake_current,
            target_source_current=source_current,
            artifacts_consistent=artifacts_consistent,
            target_bound=target_bound,
            application_only=application_only,
            non_routing=non_routing,
            output_dir=root,
            scope_review_dir=scope_root,
            target_intake_dir=intake_root,
            target_source_path=source_path,
            error="" if verified else (integrity.error or "mapping application verification failed"),
        )
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return _failed_verification(
            root,
            scope_root=scope_root,
            intake_root=intake_root,
            source_path=source_path,
            manifest_current=integrity.passed,
            scope_current=scope_current,
            intake_current=intake_current,
            source_current=source_current,
            error=str(exc),
        )


def _verified_intake_inputs(intake_dir: Path) -> VerifiedVendorIntakeInputs:
    root = intake_dir.resolve()
    verification = verify_vendor_csv_intake_report(root)
    if not verification.verified:
        raise ValueError(
            "mapping application requires a semantically verified target intake: "
            f"{verification.error}"
        )
    receipt = _read_json(root / INTAKE_RECEIPT_FILE, "target intake receipt")
    source = _mapping(receipt.get("source"))
    mapping = _mapping(receipt.get("mapping"))
    settings = _mapping(receipt.get("settings"))
    source_path = Path(_text(source.get("source_path"))).resolve()
    adapter = _identity(settings.get("adapter"))
    requested_kind = _identity(settings.get("kind"))
    best_kind = _identity(mapping.get("best_kind"))
    receipt_id = _text(receipt.get("intake_receipt_id"))
    receipt_sha256 = _text(receipt.get("intake_receipt_sha256"))
    source_sha256 = _text(source.get("file_sha256"))
    header_sha256 = _text(source.get("header_sha256"))
    if not all(
        (
            source_path.is_file(),
            adapter,
            requested_kind,
            best_kind,
            receipt_id,
            receipt_sha256,
            source_sha256,
            header_sha256,
        )
    ):
        raise ValueError("target intake identity or fingerprints are incomplete")
    if verification.source_path != source_path:
        raise ValueError("target intake source path is inconsistent")
    if file_sha256(source_path) != source_sha256:
        raise ValueError("target intake source fingerprint is stale")
    return VerifiedVendorIntakeInputs(
        intake_dir=root,
        source_path=source_path,
        adapter=adapter,
        requested_kind=requested_kind,
        best_kind=best_kind,
        intake_receipt_id=receipt_id,
        intake_receipt_sha256=receipt_sha256,
        source_file_sha256=source_sha256,
        source_header_sha256=header_sha256,
    )


def _assemble_report(
    *,
    scope: ApprovedMappingScopeReviewInputs,
    intake: VerifiedVendorIntakeInputs,
    config: VendorMappingApplicationConfig,
) -> VendorMappingApplicationReport:
    checks = _application_checks(scope, intake)
    failed = checks.loc[~checks["passed"].map(_bool)]
    if not failed.empty:
        raise ValueError(
            "target mapping application contract failed: "
            + ", ".join(failed["check"].astype(str).tolist())
        )
    mapping = _read_csv(scope.scoped_mapping_path, "scope-approved vendor mapping")
    receipt_core = _receipt_core(
        scope=scope,
        intake=intake,
        checks=checks,
        config=config,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "application": {
            "id": f"vendor-mapping-application-{receipt_sha256[:24]}",
            "sha256": receipt_sha256,
        },
    }
    action_queue = pd.DataFrame(columns=ACTION_QUEUE_COLUMNS)
    summary = _summary(receipt, checks)
    config_payload = _config_payload(
        config=config,
        scope=scope,
        intake=intake,
        receipt=receipt,
    )
    return VendorMappingApplicationReport(
        checks=checks,
        mapping=mapping,
        action_queue=action_queue,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _application_checks(
    scope: ApprovedMappingScopeReviewInputs,
    intake: VerifiedVendorIntakeInputs,
) -> pd.DataFrame:
    rows = [
        _check(
            "scope_review_semantically_verified",
            "scope_review",
            True,
            "is",
            True,
            True,
            "mapping scope review is not semantically verified",
        ),
        _check(
            "scope_review_approved",
            "scope_review",
            True,
            "is",
            True,
            True,
            "mapping scope review is not approved",
        ),
        _check(
            "target_intake_semantically_verified",
            "target_intake",
            True,
            "is",
            True,
            True,
            "target intake is not semantically verified",
        ),
        _check(
            "adapter_matches",
            "identity",
            intake.adapter,
            "==",
            scope.adapter,
            intake.adapter == scope.adapter,
            "target intake adapter does not match the approved mapping scope",
        ),
        _check(
            "requested_kind_compatible",
            "identity",
            intake.requested_kind,
            "in",
            f"{scope.kind};auto",
            intake.requested_kind in {scope.kind, "auto"},
            "target intake requested kind does not match the approved scope",
        ),
        _check(
            "best_kind_matches",
            "identity",
            intake.best_kind,
            "==",
            scope.kind,
            intake.best_kind == scope.kind,
            "target intake inferred kind does not match the approved scope",
        ),
        _check(
            "reuse_scope_exact_header",
            "scope",
            scope.reuse_scope,
            "==",
            "exact_header",
            scope.reuse_scope == "exact_header",
            "mapping scope is not exact-header reuse",
        ),
        _check(
            "ordered_header_matches",
            "scope",
            intake.source_header_sha256,
            "==",
            scope.source_header_sha256,
            intake.source_header_sha256 == scope.source_header_sha256,
            "target source ordered header does not match the approved scope",
        ),
        _check(
            "target_source_current",
            "target_source",
            file_sha256(intake.source_path),
            "==",
            intake.source_file_sha256,
            file_sha256(intake.source_path) == intake.source_file_sha256,
            "target source no longer matches its intake receipt",
        ),
        _check(
            "scope_mapping_current",
            "mapping",
            file_sha256(scope.scoped_mapping_path),
            "==",
            scope.reviewed_mapping_sha256,
            file_sha256(scope.scoped_mapping_path)
            == scope.reviewed_mapping_sha256,
            "scope mapping no longer matches the approved mapping hash",
        ),
    ]
    return pd.DataFrame(rows, columns=CHECK_COLUMNS)


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
    scope: ApprovedMappingScopeReviewInputs,
    intake: VerifiedVendorIntakeInputs,
    checks: pd.DataFrame,
    config: VendorMappingApplicationConfig,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "target_bound_vendor_mapping_application",
        "sealed": True,
        "ready": True,
        "identity": {"adapter": scope.adapter, "kind": scope.kind},
        "scope_review": {
            "path": str(scope.scope_review_dir),
            "id": scope.mapping_scope_review_id,
            "sha256": scope.mapping_scope_review_sha256,
            "reuse_scope": scope.reuse_scope,
            "source_header_sha256": scope.source_header_sha256,
        },
        "mapping_review": {
            "path": str(scope.mapping_review_dir),
            "id": scope.mapping_review_id,
            "sha256": scope.mapping_review_sha256,
        },
        "target_intake": {
            "path": str(intake.intake_dir),
            "receipt_id": intake.intake_receipt_id,
            "receipt_sha256": intake.intake_receipt_sha256,
            "requested_kind": intake.requested_kind,
            "best_kind": intake.best_kind,
        },
        "target_source": {
            "path": str(intake.source_path),
            "file_sha256": intake.source_file_sha256,
            "header_sha256": intake.source_header_sha256,
        },
        "mapping": {
            "source_path": str(scope.scoped_mapping_path),
            "reviewed_sha256": scope.reviewed_mapping_sha256,
            "output_file": config.output_mapping_file,
            "bytes_preserved": True,
        },
        "outcome": {
            "check_count": int(len(checks)),
            "failed_check_count": 0,
            "failed_check_names": [],
        },
        "safety": _safety_payload(),
    }


def _summary(receipt: Mapping[str, Any], checks: pd.DataFrame) -> pd.DataFrame:
    application = _mapping(receipt.get("application"))
    identity = _mapping(receipt.get("identity"))
    scope_review = _mapping(receipt.get("scope_review"))
    mapping_review = _mapping(receipt.get("mapping_review"))
    intake = _mapping(receipt.get("target_intake"))
    source = _mapping(receipt.get("target_source"))
    mapping = _mapping(receipt.get("mapping"))
    return pd.DataFrame(
        [
            {
                "ready": True,
                "sealed": True,
                "target_bound": True,
                "mapping_application_id": _text(application.get("id")),
                "mapping_application_sha256": _text(application.get("sha256")),
                "contract_version": CONTRACT_VERSION,
                "adapter": _text(identity.get("adapter")),
                "kind": _text(identity.get("kind")),
                "reuse_scope": _text(scope_review.get("reuse_scope")),
                "mapping_scope_review_id": _text(scope_review.get("id")),
                "mapping_scope_review_sha256": _text(scope_review.get("sha256")),
                "mapping_review_id": _text(mapping_review.get("id")),
                "mapping_review_sha256": _text(mapping_review.get("sha256")),
                "target_intake_receipt_id": _text(intake.get("receipt_id")),
                "target_source_path": _text(source.get("path")),
                "target_source_file_sha256": _text(source.get("file_sha256")),
                "source_header_sha256": _text(source.get("header_sha256")),
                "reviewed_mapping_sha256": _text(mapping.get("reviewed_sha256")),
                "check_count": int(len(checks)),
                "failed_check_count": 0,
                "failed_check_names": "",
                "blocked_action_count": 0,
                "next_gate": "verify-vendor-mapping-application",
                "next_gate_help_command": (
                    "python -m hft_cli verify-vendor-mapping-application --help"
                ),
                **_safety_payload(),
                "recommendation": "normalize_target_bound_mapping",
            }
        ]
    )


def _config_payload(
    *,
    config: VendorMappingApplicationConfig,
    scope: ApprovedMappingScopeReviewInputs,
    intake: VerifiedVendorIntakeInputs,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    application = _mapping(receipt.get("application"))
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "ready": True,
        "mapping_application_id": _text(application.get("id")),
        "mapping_application_sha256": _text(application.get("sha256")),
        "identity": {"adapter": scope.adapter, "kind": scope.kind},
        "scope_review": {
            "path": str(scope.scope_review_dir),
            "id": scope.mapping_scope_review_id,
            "sha256": scope.mapping_scope_review_sha256,
        },
        "target_intake": {
            "path": str(intake.intake_dir),
            "receipt_id": intake.intake_receipt_id,
            "receipt_sha256": intake.intake_receipt_sha256,
        },
        "target_source": {
            "path": str(intake.source_path),
            "file_sha256": intake.source_file_sha256,
            "header_sha256": intake.source_header_sha256,
        },
        "mapping": {
            "source_path": str(scope.scoped_mapping_path),
            "reviewed_sha256": scope.reviewed_mapping_sha256,
            "output_file": config.output_mapping_file,
            "bytes_preserved": True,
        },
        "next_gate": "verify-vendor-mapping-application",
        "safety": _safety_payload(),
    }


def _manifest_extra(report: VendorMappingApplicationReport) -> dict[str, Any]:
    row = report.summary.iloc[0]
    return {
        "contract_version": CONTRACT_VERSION,
        "mapping_application_id": _text(row.get("mapping_application_id")),
        "mapping_application_sha256": _text(
            row.get("mapping_application_sha256")
        ),
        "target_binding": {
            "target_source_file_sha256": _text(
                row.get("target_source_file_sha256")
            ),
            "source_header_sha256": _text(row.get("source_header_sha256")),
            "reviewed_mapping_sha256": _text(
                row.get("reviewed_mapping_sha256")
            ),
        },
        "safety": _safety_payload(),
    }


def _safety_payload() -> dict[str, bool]:
    return {
        "target_file_bound": True,
        "exact_header_verified": True,
        "header_order_sensitive": True,
        "scope_review_required": True,
        "target_intake_required": True,
        "mapping_bytes_preserved": True,
        "authorizes_target_mapping_application": True,
        "normalization_executed": False,
        "authorizes_normalization": False,
        "authorizes_strategy_research": False,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "authorizes_live_release": False,
    }


def _surfaces_target_bound(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        all(
            _explicit_bool(_safety_surface(surface).get(field)) is True
            for field in (
                "target_file_bound",
                "exact_header_verified",
                "header_order_sensitive",
                "scope_review_required",
                "target_intake_required",
                "mapping_bytes_preserved",
                "authorizes_target_mapping_application",
            )
        )
        for surface in surfaces
    )


def _surfaces_application_only(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        all(
            _explicit_bool(_safety_surface(surface).get(field)) is False
            for field in ("normalization_executed", "authorizes_normalization")
        )
        for surface in surfaces
    )


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


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame) -> str:
    lines = [
        "# Vendor Mapping Target Application",
        "",
        f"- Ready: {_yes_no(_bool(summary.get('ready')))}",
        f"- Target bound: {_yes_no(_bool(summary.get('target_bound')))}",
        f"- Adapter: {_text(summary.get('adapter'))}",
        f"- Kind: {_text(summary.get('kind'))}",
        f"- Target source: `{_text(summary.get('target_source_path'))}`",
        f"- Target source SHA-256: `{_text(summary.get('target_source_file_sha256'))}`",
        f"- Ordered header SHA-256: `{_text(summary.get('source_header_sha256'))}`",
        f"- Mapping scope review ID: `{_text(summary.get('mapping_scope_review_id'))}`",
        f"- Failed checks: {int((~checks['passed'].map(_bool)).sum())}",
        "",
        "This receipt binds the approved mapping to this exact target source and",
        "ordered header. It does not execute or authorize normalization, strategy",
        "research, routing, submission, or live release.",
        "",
    ]
    return "\n".join(lines)


def _config_from_manifest(
    manifest: Mapping[str, Any],
) -> VendorMappingApplicationConfig:
    payload = _mapping(_mapping(manifest.get("parameters")).get("config"))
    expected = {field.name for field in fields(VendorMappingApplicationConfig)}
    if set(payload) != expected:
        raise ValueError("mapping application config contract is incomplete or unknown")
    config = VendorMappingApplicationConfig(
        output_mapping_file=str(payload["output_mapping_file"]),
    )
    _validate_config(config)
    return config


def _validate_config(config: VendorMappingApplicationConfig) -> None:
    path = Path(config.output_mapping_file)
    reserved = {name.lower() for name in (*STATIC_ARTIFACTS, MANIFEST_NAME)}
    if (
        not config.output_mapping_file
        or path.is_absolute()
        or len(path.parts) != 1
        or path.name in {"", ".", ".."}
    ):
        raise ValueError(
            "output_mapping_file must be a filename within mapping application output"
        )
    if path.name.lower() in reserved:
        raise ValueError("output_mapping_file conflicts with an application artifact")


def _reject_collisions(
    out: Path,
    *,
    scope_root: Path,
    intake_root: Path,
    source_path: Path,
) -> None:
    if _is_relative_to(out, scope_root) or _is_relative_to(scope_root, out):
        raise ValueError("mapping application output cannot overlap scope-review evidence")
    if _is_relative_to(out, intake_root) or _is_relative_to(intake_root, out):
        raise ValueError("mapping application output cannot overlap target-intake evidence")
    if _is_relative_to(intake_root, scope_root) or _is_relative_to(
        scope_root,
        intake_root,
    ):
        raise ValueError("scope-review and target-intake evidence cannot overlap")
    if _is_relative_to(source_path, out):
        raise ValueError("target source cannot be stored inside application output")


def _manifest_input_contract_current(
    inputs: Mapping[str, Any],
    *,
    scope: ApprovedMappingScopeReviewInputs,
    intake: VerifiedVendorIntakeInputs,
) -> bool:
    expected = {
        "scope_review": (scope.scope_review_dir, "directory"),
        "scope_review_manifest": (
            scope.scope_review_dir / MANIFEST_NAME,
            "file",
        ),
        "scope_review_receipt": (
            scope.scope_review_dir / SCOPE_REVIEW_RECEIPT_FILE,
            "file",
        ),
        "scope_mapping": (scope.scoped_mapping_path, "file"),
        "target_intake": (intake.intake_dir, "directory"),
        "target_intake_manifest": (intake.intake_dir / MANIFEST_NAME, "file"),
        "target_intake_receipt": (
            intake.intake_dir / INTAKE_RECEIPT_FILE,
            "file",
        ),
        "target_intake_source_profile": (
            intake.intake_dir / INTAKE_SOURCE_PROFILE_FILE,
            "file",
        ),
        "target_source": (intake.source_path, "file"),
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
        raise ValueError(f"mapping application manifest lacks a {kind} fingerprint")
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
    scope_root: Path | None,
    intake_root: Path | None,
    source_path: Path | None,
    manifest_current: bool,
    scope_current: bool,
    intake_current: bool,
    source_current: bool,
    error: str,
) -> VendorMappingApplicationVerification:
    return VendorMappingApplicationVerification(
        verified=False,
        ready=False,
        manifest_current=manifest_current,
        scope_review_current=scope_current,
        target_intake_current=intake_current,
        target_source_current=source_current,
        artifacts_consistent=False,
        target_bound=False,
        application_only=False,
        non_routing=False,
        output_dir=root,
        scope_review_dir=scope_root,
        target_intake_dir=intake_root,
        target_source_path=source_path,
        error=error,
    )


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
