from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from adapters.mapped_data import MAPPED_DATA_TRANSFORMS
from adapters.vendor_intake import (
    RECEIPT_FILE as INTAKE_RECEIPT_FILE,
    SOURCE_PROFILE_FILE as INTAKE_SOURCE_PROFILE_FILE,
    SUMMARY_FILE as INTAKE_SUMMARY_FILE,
    verify_vendor_csv_intake_report,
)
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "vendor_mapping_review"
CONTRACT_VERSION = "vendor_mapping_review/v1"
CHECKS_FILE = "vendor_mapping_review_checks.csv"
ACTION_QUEUE_FILE = "vendor_mapping_review_action_queue.csv"
SUMMARY_FILE = "vendor_mapping_review_summary.csv"
RECEIPT_FILE = "vendor_mapping_review_receipt.json"
CONFIG_FILE = "vendor_mapping_review_config.json"
RUNBOOK_FILE = "vendor_mapping_review_runbook.md"
STATIC_ARTIFACTS = (
    CHECKS_FILE,
    ACTION_QUEUE_FILE,
    SUMMARY_FILE,
    RECEIPT_FILE,
    CONFIG_FILE,
    RUNBOOK_FILE,
)
CANONICAL_MAPPING_COLUMNS = (
    "normalized_column",
    "source_column",
    "default_value",
    "required",
    "transform",
)
OPERATOR_DECISION_COLUMNS = (
    "intake_receipt_id",
    "source_file_sha256",
    "mapping_candidate_sha256",
    "adapter",
    "kind",
    "decision",
    "operator_id",
    "operator_role",
    "reviewed_at_utc",
    "vendor_documentation_checked",
    "source_columns_confirmed",
    "field_semantics_confirmed",
    "timestamp_semantics_confirmed",
    "price_quantity_units_confirmed",
    "transform_semantics_confirmed",
    "notes",
    "authorizes_routing",
    "authorizes_submission",
)
ATTESTATION_COLUMNS = (
    "vendor_documentation_checked",
    "source_columns_confirmed",
    "field_semantics_confirmed",
    "timestamp_semantics_confirmed",
    "price_quantity_units_confirmed",
    "transform_semantics_confirmed",
)
CHECK_COLUMNS = (
    "check",
    "component",
    "normalized_column",
    "value",
    "operator",
    "threshold",
    "passed",
    "reason",
)
ACTION_QUEUE_COLUMNS = (
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "normalized_column",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
)


@dataclass(frozen=True)
class VendorMappingReviewConfig:
    output_mapping_file: str = "reviewed_vendor_mapping.csv"


@dataclass(frozen=True)
class VendorMappingReviewReport:
    checks: pd.DataFrame
    mapping: pd.DataFrame
    action_queue: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def sealed(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("sealed", False))
        )

    @property
    def approved(self) -> bool:
        return bool(
            self.sealed
            and _bool(
                self.summary.iloc[0].get(
                    "approved_for_normalization",
                    False,
                )
            )
        )


@dataclass(frozen=True)
class VendorMappingReviewVerification:
    verified: bool
    sealed: bool
    approved: bool
    rejected: bool
    manifest_current: bool
    intake_current: bool
    mapping_candidate_current: bool
    operator_decision_current: bool
    artifacts_consistent: bool
    normalization_only: bool
    non_routing: bool
    output_dir: Path
    intake_dir: Path | None = None
    mapping_candidate_path: Path | None = None
    operator_decision_path: Path | None = None
    error: str = ""


def write_vendor_mapping_review(
    intake_dir: str | Path,
    mapping_candidate_path: str | Path,
    operator_decision_path: str | Path,
    output_dir: str | Path,
    *,
    config: VendorMappingReviewConfig | None = None,
) -> VendorMappingReviewReport:
    config = config or VendorMappingReviewConfig()
    _validate_config(config)
    intake_root = Path(intake_dir).resolve()
    mapping_path = Path(mapping_candidate_path).resolve()
    decision_path = Path(operator_decision_path).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"vendor mapping review output already exists: {out}")
    if not mapping_path.is_file():
        raise FileNotFoundError(f"vendor mapping candidate not found: {mapping_path}")
    if not decision_path.is_file():
        raise FileNotFoundError(f"vendor mapping decision not found: {decision_path}")
    _reject_collisions(
        out,
        intake_root=intake_root,
        mapping_path=mapping_path,
        decision_path=decision_path,
    )
    intake_verification = verify_vendor_csv_intake_report(intake_root)
    if not intake_verification.verified or intake_verification.source_path is None:
        raise ValueError(
            "vendor mapping review requires a semantically verified, current intake: "
            f"{intake_verification.error or 'intake_not_verified'}"
        )
    mapping_sha256 = file_sha256(mapping_path)
    decision_sha256 = file_sha256(decision_path)
    report = _assemble_report(
        intake_root=intake_root,
        mapping_path=mapping_path,
        decision_path=decision_path,
        config=config,
        intake_verification=intake_verification,
    )
    out.mkdir(parents=True)
    _write_csv(report.checks, out / CHECKS_FILE)
    _write_csv(report.mapping, out / config.output_mapping_file)
    _write_csv(report.action_queue, out / ACTION_QUEUE_FILE)
    _write_csv(report.summary, out / SUMMARY_FILE)
    _write_json(out / RECEIPT_FILE, report.receipt)
    _write_json(out / CONFIG_FILE, report.config)
    (out / RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], report.action_queue),
        encoding="utf-8",
    )
    final_intake = verify_vendor_csv_intake_report(intake_root)
    if (
        not final_intake.verified
        or file_sha256(mapping_path) != mapping_sha256
        or file_sha256(decision_path) != decision_sha256
    ):
        raise RuntimeError(
            "vendor intake, mapping candidate, or operator decision changed during review"
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "vendor_intake": intake_root,
            "vendor_intake_manifest": intake_root / MANIFEST_NAME,
            "vendor_intake_receipt": intake_root / INTAKE_RECEIPT_FILE,
            "vendor_source": intake_verification.source_path,
            "mapping_candidate": mapping_path,
            "operator_decision": decision_path,
        },
        extra=_manifest_extra(report),
    )
    return VendorMappingReviewReport(
        checks=report.checks,
        mapping=report.mapping,
        action_queue=report.action_queue,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_vendor_mapping_review(
    review_dir: str | Path,
) -> VendorMappingReviewVerification:
    candidate = Path(review_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=STATIC_ARTIFACTS,
        require_input_fingerprints=True,
    )
    intake_root: Path | None = None
    mapping_path: Path | None = None
    decision_path: Path | None = None
    intake_current = False
    mapping_current = False
    decision_current = False
    try:
        manifest = _read_json(manifest_path, "vendor mapping review manifest")
        config = _config_from_manifest(manifest)
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=RUN_TYPE,
            required_artifacts=(*STATIC_ARTIFACTS, config.output_mapping_file),
            require_input_fingerprints=True,
        )
        inputs = _mapping(manifest.get("inputs"))
        intake_root = _fingerprint_path(inputs.get("vendor_intake"), "directory")
        mapping_path = _fingerprint_path(inputs.get("mapping_candidate"), "file")
        decision_path = _fingerprint_path(inputs.get("operator_decision"), "file")
        intake_verification = verify_vendor_csv_intake_report(intake_root)
        intake_current = intake_verification.verified
        mapping_current = _fingerprint_current(
            inputs.get("mapping_candidate"),
            mapping_path,
        )
        decision_current = _fingerprint_current(
            inputs.get("operator_decision"),
            decision_path,
        )
        if not (intake_current and mapping_current and decision_current):
            return _failed_verification(
                root,
                intake_root=intake_root,
                mapping_path=mapping_path,
                decision_path=decision_path,
                manifest_current=integrity.passed,
                intake_current=intake_current,
                mapping_current=mapping_current,
                decision_current=decision_current,
                error="vendor mapping review source is stale",
            )
        expected = _assemble_report(
            intake_root=intake_root,
            mapping_path=mapping_path,
            decision_path=decision_path,
            config=config,
            intake_verification=intake_verification,
        )
        actual_checks = _read_csv(root / CHECKS_FILE, "vendor mapping review checks")
        actual_mapping = _read_csv(
            root / config.output_mapping_file,
            "reviewed vendor mapping",
        )
        actual_actions = _read_csv(
            root / ACTION_QUEUE_FILE,
            "vendor mapping review action queue",
        )
        actual_summary = _read_csv(root / SUMMARY_FILE, "vendor mapping review summary")
        actual_receipt = _read_json(root / RECEIPT_FILE, "vendor mapping review receipt")
        actual_config = _read_json(root / CONFIG_FILE, "vendor mapping review config")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        summary_row = _single_row(actual_summary, "vendor mapping review summary")
        artifacts_consistent = bool(
            _dataframe_equal(actual_checks, expected.checks)
            and _dataframe_equal(actual_mapping, expected.mapping)
            and _dataframe_equal(actual_actions, expected.action_queue)
            and _dataframe_equal(actual_summary, expected.summary)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config)
            and actual_runbook
            == _runbook_markdown(expected.summary.iloc[0], expected.action_queue)
            and _jsonable(manifest.get("parameters"))
            == {"config": _jsonable(asdict(config))}
            and _jsonable(manifest.get("extra"))
            == _jsonable(_manifest_extra(expected))
            and _manifest_input_contract_current(
                inputs,
                intake_root=intake_root,
                source_path=intake_verification.source_path,
                mapping_path=mapping_path,
                decision_path=decision_path,
            )
        )
        normalization_only = _normalization_only_surfaces(
            summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        non_routing = _non_routing_surfaces(
            summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        approved = expected.approved
        verified = bool(
            integrity.passed
            and intake_current
            and mapping_current
            and decision_current
            and artifacts_consistent
            and normalization_only
            and non_routing
        )
        return VendorMappingReviewVerification(
            verified=verified,
            sealed=expected.sealed,
            approved=approved,
            rejected=bool(expected.sealed and not approved),
            manifest_current=integrity.passed,
            intake_current=intake_current,
            mapping_candidate_current=mapping_current,
            operator_decision_current=decision_current,
            artifacts_consistent=artifacts_consistent,
            normalization_only=normalization_only,
            non_routing=non_routing,
            output_dir=root,
            intake_dir=intake_root,
            mapping_candidate_path=mapping_path,
            operator_decision_path=decision_path,
            error=""
            if verified
            else (integrity.error or "vendor mapping review semantic verification failed"),
        )
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return _failed_verification(
            root,
            intake_root=intake_root,
            mapping_path=mapping_path,
            decision_path=decision_path,
            manifest_current=integrity.passed,
            intake_current=intake_current,
            mapping_current=mapping_current,
            decision_current=decision_current,
            error=str(exc),
        )


def _assemble_report(
    *,
    intake_root: Path,
    mapping_path: Path,
    decision_path: Path,
    config: VendorMappingReviewConfig,
    intake_verification: Any,
) -> VendorMappingReviewReport:
    intake_summary = _single_row(
        _read_csv(intake_root / INTAKE_SUMMARY_FILE, "vendor intake summary"),
        "vendor intake summary",
    )
    intake_receipt = _read_json(
        intake_root / INTAKE_RECEIPT_FILE,
        "vendor intake receipt",
    )
    source_profile = _read_json(
        intake_root / INTAKE_SOURCE_PROFILE_FILE,
        "vendor intake source profile",
    )
    candidate = _read_csv(mapping_path, "vendor mapping candidate")
    operator_frame = _read_csv(decision_path, "vendor mapping operator decision")
    operator_row = _single_row(operator_frame, "vendor mapping operator decision")
    expected_targets = _expected_targets(intake_root, intake_summary)
    source_columns = [str(value) for value in source_profile.get("header_columns", [])]
    canonical_mapping = _canonical_mapping(candidate, expected_targets)
    mapping_checks = _mapping_checks(
        candidate,
        canonical_mapping=canonical_mapping,
        expected_targets=expected_targets,
        source_columns=source_columns,
    )
    decision_checks = _operator_checks(
        operator_frame,
        operator_row=operator_row,
        intake_summary=intake_summary,
        intake_receipt=intake_receipt,
        mapping_sha256=file_sha256(mapping_path),
    )
    source_checks = pd.DataFrame(
        [
            _check(
                "intake_semantically_verified",
                "intake",
                "",
                bool(intake_verification.verified),
                "is",
                True,
                bool(intake_verification.verified),
                "vendor intake is not semantically verified",
            ),
            _check(
                "intake_source_current",
                "intake",
                "",
                bool(intake_verification.source_current),
                "is",
                True,
                bool(intake_verification.source_current),
                "vendor intake source is stale",
            ),
            _check(
                "mapping_candidate_separate",
                "mapping",
                "",
                str(mapping_path),
                "outside",
                str(intake_root),
                not _is_relative_to(mapping_path, intake_root),
                "mapping candidate must remain outside immutable intake evidence",
            ),
            _check(
                "operator_decision_separate",
                "operator",
                "",
                str(decision_path),
                "outside",
                str(intake_root),
                not _is_relative_to(decision_path, intake_root),
                "operator decision must remain outside immutable intake evidence",
            ),
        ],
        columns=CHECK_COLUMNS,
    )
    checks = pd.concat(
        [source_checks, mapping_checks, decision_checks],
        ignore_index=True,
    )
    decision_contract_valid = bool(decision_checks["passed"].map(_bool).all())
    if not decision_contract_valid:
        failed = decision_checks.loc[
            ~decision_checks["passed"].map(_bool),
            "check",
        ].astype(str).tolist()
        raise ValueError(
            "vendor mapping operator decision contract failed: "
            + ", ".join(failed)
        )
    mapping_valid = bool(mapping_checks["passed"].map(_bool).all())
    decision = _decision_value(operator_row)
    if decision == "approved" and not mapping_valid:
        failed = mapping_checks.loc[
            ~mapping_checks["passed"].map(_bool),
            "check",
        ].astype(str).tolist()
        raise ValueError(
            "approved vendor mapping failed structural review: "
            + ", ".join(failed)
        )
    approved = decision == "approved" and mapping_valid
    reviewed_mapping_sha256 = _csv_sha256(canonical_mapping)
    receipt_core = _receipt_core(
        intake_root=intake_root,
        mapping_path=mapping_path,
        decision_path=decision_path,
        intake_summary=intake_summary,
        intake_receipt=intake_receipt,
        source_profile=source_profile,
        operator_row=operator_row,
        expected_targets=expected_targets,
        mapping_valid=mapping_valid,
        reviewed_mapping_sha256=reviewed_mapping_sha256,
        approved=approved,
        checks=checks,
        config=config,
    )
    review_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "mapping_review_id": f"vendor-mapping-review-{review_sha256[:24]}",
        "mapping_review_sha256": review_sha256,
    }
    action_queue = _action_queue(checks, decision=decision)
    summary = _summary(
        receipt=receipt,
        intake_summary=intake_summary,
        mapping_valid=mapping_valid,
        approved=approved,
        checks=checks,
        action_queue=action_queue,
        config=config,
    )
    config_payload = _config_payload(
        config=config,
        receipt=receipt,
        intake_root=intake_root,
        mapping_path=mapping_path,
        decision_path=decision_path,
    )
    return VendorMappingReviewReport(
        checks=checks,
        mapping=canonical_mapping,
        action_queue=action_queue,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _expected_targets(intake_root: Path, intake_summary: pd.Series) -> list[str]:
    mapping_name = _text(intake_summary.get("output_mapping_file"))
    if not mapping_name:
        raise ValueError("vendor intake summary lacks its mapping draft filename")
    draft = _read_csv(intake_root / mapping_name, "vendor intake mapping draft")
    if "normalized_column" not in draft.columns or draft.empty:
        raise ValueError("vendor intake mapping draft lacks normalized columns")
    targets = [
        _text(value)
        for value in draft["normalized_column"].tolist()
        if _text(value)
    ]
    if len(targets) != len(set(targets)):
        raise ValueError("vendor intake mapping draft has duplicate normalized columns")
    return targets


def _canonical_mapping(
    candidate: pd.DataFrame,
    expected_targets: list[str],
) -> pd.DataFrame:
    frame = candidate.copy()
    if "normalized_column" not in frame.columns:
        return pd.DataFrame(
            [
                {
                    "normalized_column": target,
                    "source_column": "",
                    "default_value": "",
                    "required": True,
                    "transform": "identity",
                }
                for target in expected_targets
            ],
            columns=CANONICAL_MAPPING_COLUMNS,
        )
    for column, default in (
        ("source_column", ""),
        ("default_value", ""),
        ("required", True),
        ("transform", "identity"),
    ):
        if column not in frame.columns:
            frame[column] = default
    rows: list[dict[str, Any]] = []
    for target in expected_targets:
        matches = frame.loc[
            frame["normalized_column"].map(_text).eq(target)
        ]
        row = matches.iloc[0] if not matches.empty else pd.Series(dtype=object)
        transform = _transform_key(row.get("transform"))
        rows.append(
            {
                "normalized_column": target,
                "source_column": _text(row.get("source_column")),
                "default_value": _text(row.get("default_value")),
                "required": _bool(row.get("required", True)),
                "transform": transform,
            }
        )
    return pd.DataFrame(rows, columns=CANONICAL_MAPPING_COLUMNS)


def _mapping_checks(
    candidate: pd.DataFrame,
    *,
    canonical_mapping: pd.DataFrame,
    expected_targets: list[str],
    source_columns: list[str],
) -> pd.DataFrame:
    has_target = "normalized_column" in candidate.columns
    raw_targets = (
        candidate["normalized_column"].map(_text).tolist()
        if has_target
        else []
    )
    nonempty_targets = [target for target in raw_targets if target]
    duplicates = sorted(
        {
            target
            for target in nonempty_targets
            if nonempty_targets.count(target) > 1
        }
    )
    unknown = sorted(set(nonempty_targets) - set(expected_targets))
    missing = [target for target in expected_targets if target not in nonempty_targets]
    checks = [
        _check(
            "mapping_candidate_not_empty",
            "mapping",
            "",
            len(candidate),
            ">",
            0,
            not candidate.empty,
            "mapping candidate is empty",
        ),
        _check(
            "normalized_column_present",
            "mapping",
            "",
            has_target,
            "is",
            True,
            has_target,
            "mapping candidate lacks normalized_column",
        ),
        _check(
            "normalized_targets_complete",
            "mapping",
            "",
            ";".join(missing),
            "empty",
            True,
            not missing,
            "mapping candidate omits required normalized targets",
        ),
        _check(
            "normalized_targets_unique",
            "mapping",
            "",
            ";".join(duplicates),
            "empty",
            True,
            not duplicates,
            "mapping candidate has duplicate normalized targets",
        ),
        _check(
            "normalized_targets_known",
            "mapping",
            "",
            ";".join(unknown),
            "empty",
            True,
            not unknown,
            "mapping candidate has unknown normalized targets",
        ),
    ]
    source_set = set(source_columns)
    for row in canonical_mapping.to_dict(orient="records"):
        target = _text(row.get("normalized_column"))
        source = _text(row.get("source_column"))
        default = _text(row.get("default_value"))
        required = _bool(row.get("required", True))
        transform = _transform_key(row.get("transform"))
        checks.extend(
            [
                _check(
                    f"required_not_downgraded:{target}",
                    "mapping",
                    target,
                    required,
                    "is",
                    True,
                    required,
                    "required normalized target cannot be downgraded",
                ),
                _check(
                    f"source_or_default_present:{target}",
                    "mapping",
                    target,
                    source or default,
                    "nonempty",
                    True,
                    bool(source or default),
                    "normalized target lacks both source column and default",
                ),
                _check(
                    f"source_column_known:{target}",
                    "mapping",
                    target,
                    source,
                    "in_source_header_or_blank",
                    True,
                    not source or source in source_set,
                    "mapping references a source column absent from the intake header",
                ),
                _check(
                    f"transform_supported:{target}",
                    "mapping",
                    target,
                    transform,
                    "in",
                    ";".join(sorted(MAPPED_DATA_TRANSFORMS)),
                    transform in MAPPED_DATA_TRANSFORMS,
                    "mapping uses an unsupported normalization transform",
                ),
            ]
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _operator_checks(
    operator_frame: pd.DataFrame,
    *,
    operator_row: pd.Series,
    intake_summary: pd.Series,
    intake_receipt: Mapping[str, Any],
    mapping_sha256: str,
) -> pd.DataFrame:
    missing_columns = [
        column for column in OPERATOR_DECISION_COLUMNS if column not in operator_frame.columns
    ]
    unknown_columns = [
        column for column in operator_frame.columns if column not in OPERATOR_DECISION_COLUMNS
    ]
    decision = _decision_value(operator_row)
    notes = _text(operator_row.get("notes"))
    checks = [
        _check(
            "operator_columns_complete",
            "operator",
            "",
            ";".join(missing_columns),
            "empty",
            True,
            not missing_columns,
            "operator decision is missing required columns",
        ),
        _check(
            "operator_columns_known",
            "operator",
            "",
            ";".join(unknown_columns),
            "empty",
            True,
            not unknown_columns,
            "operator decision contains columns outside the review contract",
        ),
        _check(
            "decision_completed",
            "operator",
            "",
            decision,
            "in",
            "approved,rejected",
            decision in {"approved", "rejected"},
            "operator decision must be approved or rejected",
        ),
        _check(
            "operator_id_present",
            "operator",
            "",
            _text(operator_row.get("operator_id")),
            "nonempty",
            True,
            bool(_text(operator_row.get("operator_id"))),
            "operator ID is required",
        ),
        _check(
            "operator_role_present",
            "operator",
            "",
            _text(operator_row.get("operator_role")),
            "nonempty",
            True,
            bool(_text(operator_row.get("operator_role"))),
            "operator role is required",
        ),
        _check(
            "reviewed_at_utc_valid",
            "operator",
            "",
            _text(operator_row.get("reviewed_at_utc")),
            "timezone_aware_iso8601",
            True,
            _timestamp_valid(operator_row.get("reviewed_at_utc")),
            "review timestamp must be timezone-aware ISO-8601",
        ),
        _check(
            "rejection_notes_present",
            "operator",
            "",
            notes,
            "nonempty_if_rejected",
            True,
            decision != "rejected" or bool(notes),
            "a rejected mapping decision requires notes",
        ),
        _check(
            "routing_not_authorized",
            "safety",
            "",
            operator_row.get("authorizes_routing", "missing"),
            "is",
            False,
            _explicit_false(operator_row, "authorizes_routing"),
            "mapping review cannot authorize routing",
        ),
        _check(
            "submission_not_authorized",
            "safety",
            "",
            operator_row.get("authorizes_submission", "missing"),
            "is",
            False,
            _explicit_false(operator_row, "authorizes_submission"),
            "mapping review cannot authorize submission",
        ),
    ]
    expected_bindings = {
        "intake_receipt_id": _text(intake_receipt.get("intake_receipt_id")),
        "source_file_sha256": _text(intake_summary.get("source_file_sha256")),
        "mapping_candidate_sha256": mapping_sha256,
        "adapter": _identity(intake_summary.get("adapter")),
        "kind": _identity(intake_summary.get("best_kind")),
    }
    for column, expected in expected_bindings.items():
        actual = (
            _identity(operator_row.get(column))
            if column in {"adapter", "kind"}
            else _text(operator_row.get(column)).lower()
        )
        expected_value = (
            _identity(expected)
            if column in {"adapter", "kind"}
            else _text(expected).lower()
        )
        checks.append(
            _check(
                f"{column}_matches",
                "binding",
                "",
                actual,
                "==",
                expected_value,
                bool(actual) and actual == expected_value,
                f"operator decision does not bind current {column}",
            )
        )
    for column in ATTESTATION_COLUMNS:
        checks.append(
            _check(
                column,
                "attestation",
                "",
                operator_row.get(column, False),
                "is",
                True,
                _explicit_true(operator_row, column),
                f"{column} must be explicitly attested",
            )
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _receipt_core(
    *,
    intake_root: Path,
    mapping_path: Path,
    decision_path: Path,
    intake_summary: pd.Series,
    intake_receipt: Mapping[str, Any],
    source_profile: Mapping[str, Any],
    operator_row: pd.Series,
    expected_targets: list[str],
    mapping_valid: bool,
    reviewed_mapping_sha256: str,
    approved: bool,
    checks: pd.DataFrame,
    config: VendorMappingReviewConfig,
) -> dict[str, Any]:
    failed_checks = checks.loc[
        ~checks["passed"].map(_bool),
        "check",
    ].astype(str).tolist()
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "operator_attested_vendor_mapping_review",
        "sealed": True,
        "decision": _decision_value(operator_row),
        "approved_for_normalization": approved,
        "identity": {
            "adapter": _identity(intake_summary.get("adapter")),
            "kind": _identity(intake_summary.get("best_kind")),
        },
        "intake": {
            "path": str(intake_root),
            "manifest_path": str(intake_root / MANIFEST_NAME),
            "manifest_sha256": file_sha256(intake_root / MANIFEST_NAME),
            "receipt_id": _text(intake_receipt.get("intake_receipt_id")),
            "receipt_sha256": file_sha256(intake_root / INTAKE_RECEIPT_FILE),
            "source_path": _text(source_profile.get("source_path")),
            "source_file_sha256": _text(source_profile.get("file_sha256")),
            "source_header_sha256": _text(source_profile.get("header_sha256")),
        },
        "mapping": {
            "candidate_path": str(mapping_path),
            "candidate_sha256": file_sha256(mapping_path),
            "reviewed_file": config.output_mapping_file,
            "reviewed_sha256": reviewed_mapping_sha256,
            "expected_targets": expected_targets,
            "mapping_valid": mapping_valid,
        },
        "operator": {
            "decision_path": str(decision_path),
            "decision_sha256": file_sha256(decision_path),
            "operator_id": _text(operator_row.get("operator_id")),
            "operator_role": _text(operator_row.get("operator_role")),
            "reviewed_at_utc": _text(operator_row.get("reviewed_at_utc")),
            "attestations": {
                column: True for column in ATTESTATION_COLUMNS
            },
            "notes": _text(operator_row.get("notes")),
        },
        "outcome": {
            "check_count": int(len(checks)),
            "failed_check_count": int(len(failed_checks)),
            "failed_check_names": failed_checks,
        },
        "safety": _safety_payload(approved),
    }


def _summary(
    *,
    receipt: Mapping[str, Any],
    intake_summary: pd.Series,
    mapping_valid: bool,
    approved: bool,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: VendorMappingReviewConfig,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].map(_bool)]
    primary = failed.iloc[0] if not failed.empty else pd.Series(dtype=object)
    decision = _text(receipt.get("decision"))
    return pd.DataFrame(
        [
            {
                "ready": approved,
                "sealed": True,
                "approved_for_normalization": approved,
                "rejected": decision == "rejected",
                "decision": decision,
                "mapping_review_id": _text(receipt.get("mapping_review_id")),
                "mapping_review_sha256": _text(receipt.get("mapping_review_sha256")),
                "contract_version": CONTRACT_VERSION,
                "adapter": _identity(intake_summary.get("adapter")),
                "kind": _identity(intake_summary.get("best_kind")),
                "intake_receipt_id": _text(_mapping(receipt.get("intake")).get("receipt_id")),
                "source_file_sha256": _text(intake_summary.get("source_file_sha256")),
                "mapping_candidate_sha256": _text(_mapping(receipt.get("mapping")).get("candidate_sha256")),
                "reviewed_mapping_sha256": _text(_mapping(receipt.get("mapping")).get("reviewed_sha256")),
                "mapping_valid": mapping_valid,
                "normalized_target_count": int(len(_mapping(receipt.get("mapping")).get("expected_targets", []))),
                "check_count": int(len(checks)),
                "failed_check_count": int(len(failed)),
                "failed_check_names": ";".join(failed["check"].astype(str).tolist()),
                "first_failed_reason": _text(primary.get("reason")),
                "primary_blocker_check": _text(primary.get("check")),
                "primary_blocker_value": _text(primary.get("value")),
                "primary_blocker_operator": _text(primary.get("operator")),
                "primary_blocker_threshold": _text(primary.get("threshold")),
                "primary_blocker_reason": _text(primary.get("reason")),
                "action_queue_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": "" if approved else "review-vendor-mapping",
                "next_gate_help_command": ""
                if approved
                else "python -m hft_cli review-vendor-mapping --help",
                "primary_action_status": "" if approved else "blocked",
                "output_mapping_file": config.output_mapping_file,
                **_safety_payload(approved),
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, *, decision: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].map(_bool)]
    for item in failed.to_dict(orient="records"):
        rows.append(
            {
                "queue_status": "blocked",
                "source": "vendor_mapping_review_checks",
                "component": _text(item.get("component")),
                "check": _text(item.get("check")),
                "normalized_column": _text(item.get("normalized_column")),
                "next_gate": "review-vendor-mapping",
                "next_gate_help_command": "python -m hft_cli review-vendor-mapping --help",
                "reason": _text(item.get("reason")),
                "recommendation": "correct_mapping_or_operator_decision_then_rerun_review",
            }
        )
    if decision == "rejected" and not rows:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "vendor_mapping_operator_decision",
                "component": "operator",
                "check": "mapping_review_rejected",
                "normalized_column": "",
                "next_gate": "review-vendor-mapping",
                "next_gate_help_command": "python -m hft_cli review-vendor-mapping --help",
                "reason": "operator rejected the candidate mapping",
                "recommendation": "revise_mapping_and_complete_a_new_operator_decision",
            }
        )
    ordered: list[dict[str, Any]] = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered.append(item)
    return pd.DataFrame(ordered, columns=ACTION_QUEUE_COLUMNS)


def _config_payload(
    *,
    config: VendorMappingReviewConfig,
    receipt: Mapping[str, Any],
    intake_root: Path,
    mapping_path: Path,
    decision_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "mapping_review_id": _text(receipt.get("mapping_review_id")),
        "sealed": True,
        "approved_for_normalization": _bool(
            receipt.get("approved_for_normalization", False)
        ),
        "inputs": {
            "vendor_intake": str(intake_root),
            "mapping_candidate": str(mapping_path),
            "operator_decision": str(decision_path),
        },
        "settings": _jsonable(asdict(config)),
        "safety": _mapping(receipt.get("safety")),
    }


def _manifest_extra(report: VendorMappingReviewReport) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "mapping_review_id": _text(report.receipt.get("mapping_review_id")),
        "mapping_review_sha256": _text(report.receipt.get("mapping_review_sha256")),
        "decision": _text(report.receipt.get("decision")),
        "approved_for_normalization": report.approved,
        "identity": _jsonable(_mapping(report.receipt.get("identity"))),
        "intake": _jsonable(_mapping(report.receipt.get("intake"))),
        "mapping": _jsonable(_mapping(report.receipt.get("mapping"))),
        "safety": _jsonable(_mapping(report.receipt.get("safety"))),
    }


def _safety_payload(approved: bool) -> dict[str, bool]:
    return {
        "mapping_review_only": True,
        "operator_attested": True,
        "authorizes_normalization": approved,
        "authorizes_strategy_research": False,
        "provider_network_called": False,
        "credential_environment_read": False,
        "credential_values_stored": False,
        "broker_api_called": False,
        "routing_enabled": False,
        "submission_enabled": False,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }


def _normalization_only_surfaces(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        _explicit_true_mapping(_surface_safety(surface), "mapping_review_only")
        and _explicit_true_mapping(_surface_safety(surface), "operator_attested")
        and _explicit_false_mapping(
            _surface_safety(surface),
            "authorizes_strategy_research",
        )
        for surface in surfaces
    )


def _non_routing_surfaces(*surfaces: Mapping[str, Any]) -> bool:
    false_fields = (
        "provider_network_called",
        "credential_environment_read",
        "credential_values_stored",
        "broker_api_called",
        "routing_enabled",
        "submission_enabled",
        "authorizes_routing",
        "authorizes_submission",
    )
    return all(
        all(
            _explicit_false_mapping(_surface_safety(surface), field)
            for field in false_fields
        )
        for surface in surfaces
    )


def _surface_safety(surface: Mapping[str, Any]) -> Mapping[str, Any]:
    safety = surface.get("safety")
    return safety if isinstance(safety, Mapping) else surface


def _runbook_markdown(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Vendor Mapping Review Runbook",
        "",
        f"- Review ID: `{_text(summary_row.get('mapping_review_id'))}`",
        f"- Decision: {_text(summary_row.get('decision'))}",
        f"- Approved for normalization: {_yes_no(_bool(summary_row.get('approved_for_normalization')))}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Kind: {_text(summary_row.get('kind'))}",
        f"- Mapping valid: {_yes_no(_bool(summary_row.get('mapping_valid')))}",
        f"- Reviewed mapping: `{_text(summary_row.get('output_mapping_file'))}`",
        "- Authorizes strategy research, routing, or submission: no",
        "",
        "## Actions",
        "",
    ]
    if action_queue.empty:
        lines.append("No blocked actions.")
    else:
        lines.extend(
            [
                "| priority | check | normalized column | reason |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in action_queue.to_dict(orient="records"):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _text(row.get("priority")),
                        _text(row.get("check")),
                        _text(row.get("normalized_column")),
                        _text(row.get("reason")),
                    ]
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def _check(
    name: str,
    component: str,
    normalized_column: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "component": component,
        "normalized_column": normalized_column,
        "value": _jsonable(value),
        "operator": operator,
        "threshold": _jsonable(threshold),
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _decision_value(row: pd.Series) -> str:
    return _text(row.get("decision")).lower().replace("-", "_")


def _timestamp_valid(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _explicit_true(row: pd.Series, column: str) -> bool:
    return column in row.index and _bool(row.get(column))


def _explicit_false(row: pd.Series, column: str) -> bool:
    return column in row.index and not _bool(row.get(column), default=True)


def _explicit_true_mapping(payload: Mapping[str, Any], field: str) -> bool:
    return field in payload and _bool(payload.get(field))


def _explicit_false_mapping(payload: Mapping[str, Any], field: str) -> bool:
    return field in payload and not _bool(payload.get(field), default=True)


def _transform_key(value: Any) -> str:
    key = _text(value).lower().replace("-", "_")
    return "identity" if key in {"", "none"} else key


def _config_from_manifest(manifest: Mapping[str, Any]) -> VendorMappingReviewConfig:
    payload = _mapping(_mapping(manifest.get("parameters")).get("config"))
    expected = {field.name for field in fields(VendorMappingReviewConfig)}
    if set(payload) != expected:
        raise ValueError("vendor mapping review config contract is incomplete or unknown")
    config = VendorMappingReviewConfig(
        output_mapping_file=str(payload["output_mapping_file"]),
    )
    _validate_config(config)
    return config


def _validate_config(config: VendorMappingReviewConfig) -> None:
    path = Path(config.output_mapping_file)
    reserved = {name.lower() for name in (*STATIC_ARTIFACTS, MANIFEST_NAME)}
    if (
        not config.output_mapping_file
        or path.is_absolute()
        or len(path.parts) != 1
        or path.name in {"", ".", ".."}
    ):
        raise ValueError("output_mapping_file must be a filename within the review output")
    if path.name.lower() in reserved:
        raise ValueError("output_mapping_file conflicts with a mapping review artifact")


def _reject_collisions(
    out: Path,
    *,
    intake_root: Path,
    mapping_path: Path,
    decision_path: Path,
) -> None:
    if mapping_path == decision_path:
        raise ValueError("mapping candidate and operator decision must be separate files")
    if _is_relative_to(mapping_path, intake_root):
        raise ValueError("mapping candidate must remain outside immutable intake evidence")
    if _is_relative_to(decision_path, intake_root):
        raise ValueError("operator decision must remain outside immutable intake evidence")
    if _is_relative_to(mapping_path, out) or _is_relative_to(decision_path, out):
        raise ValueError("mapping review inputs cannot be stored inside its output")
    if _is_relative_to(out, intake_root):
        raise ValueError("mapping review output cannot modify immutable intake evidence")


def _manifest_input_contract_current(
    inputs: Mapping[str, Any],
    *,
    intake_root: Path,
    source_path: Path | None,
    mapping_path: Path,
    decision_path: Path,
) -> bool:
    if source_path is None:
        return False
    expected = {
        "vendor_intake": (intake_root, "directory"),
        "vendor_intake_manifest": (intake_root / MANIFEST_NAME, "file"),
        "vendor_intake_receipt": (intake_root / INTAKE_RECEIPT_FILE, "file"),
        "vendor_source": (source_path, "file"),
        "mapping_candidate": (mapping_path, "file"),
        "operator_decision": (decision_path, "file"),
    }
    if set(inputs) != set(expected):
        return False
    for name, (path, kind) in expected.items():
        record = _mapping(inputs.get(name))
        if record.get("kind") != kind:
            return False
        if Path(str(record.get("path", ""))).resolve() != path.resolve():
            return False
    return True


def _fingerprint_path(value: Any, kind: str) -> Path:
    record = _mapping(value)
    if record.get("kind") != kind or not record.get("path"):
        raise ValueError(f"mapping review manifest lacks a {kind} fingerprint")
    return Path(str(record["path"])).resolve()


def _fingerprint_current(value: Any, path: Path) -> bool:
    record = _mapping(value)
    return bool(
        path.is_file()
        and record.get("kind") == "file"
        and Path(str(record.get("path", ""))).resolve() == path
        and _int(record.get("size_bytes")) == int(path.stat().st_size)
        and _text(record.get("sha256")) == file_sha256(path)
    )


def _failed_verification(
    root: Path,
    *,
    intake_root: Path | None,
    mapping_path: Path | None,
    decision_path: Path | None,
    manifest_current: bool,
    intake_current: bool,
    mapping_current: bool,
    decision_current: bool,
    error: str,
) -> VendorMappingReviewVerification:
    return VendorMappingReviewVerification(
        verified=False,
        sealed=False,
        approved=False,
        rejected=False,
        manifest_current=manifest_current,
        intake_current=intake_current,
        mapping_candidate_current=mapping_current,
        operator_decision_current=decision_current,
        artifacts_consistent=False,
        normalization_only=False,
        non_routing=False,
        output_dir=root,
        intake_dir=intake_root,
        mapping_candidate_path=mapping_path,
        operator_decision_path=decision_path,
        error=error,
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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


def _csv_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dataframe_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> bool:
    if list(actual.columns) != list(expected.columns) or len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(
        actual.itertuples(index=False, name=None),
        expected.itertuples(index=False, name=None),
    ):
        for actual_value, expected_value in zip(actual_row, expected_row):
            actual_missing = _missing(actual_value)
            expected_missing = _missing(expected_value)
            if actual_missing or expected_missing:
                if actual_missing != expected_missing:
                    return False
                continue
            if isinstance(actual_value, Real) and isinstance(expected_value, Real):
                if not math.isclose(
                    float(actual_value),
                    float(expected_value),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    return False
            elif str(actual_value) != str(expected_value):
                return False
    return True


def _missing(value: Any) -> bool:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan"}):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            pass
    return value


def _identity(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "passed", "approved"}:
        return True
    if text in {"false", "0", "no", "n", "failed", "rejected"}:
        return False
    return default


def _int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
