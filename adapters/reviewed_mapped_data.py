from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from adapters.mapped_data import MappedDataConfig, normalize_mapped_data
from adapters.vendor_mapping_review import (
    CONFIG_FILE as MAPPING_REVIEW_CONFIG_FILE,
    RECEIPT_FILE as MAPPING_REVIEW_RECEIPT_FILE,
    verify_vendor_mapping_review,
)
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "reviewed_mapped_data_normalization"
CONTRACT_VERSION = "reviewed_mapped_data_normalization/v1"
CHECKS_FILE = "mapped_data_checks.csv"
BINDING_CHECKS_FILE = "mapped_data_review_checks.csv"
ACTION_QUEUE_FILE = "mapped_data_action_queue.csv"
SUMMARY_FILE = "mapped_data_summary.csv"
RECEIPT_FILE = "mapped_data_receipt.json"
CONFIG_FILE = "mapped_data_config.json"
RUNBOOK_FILE = "mapped_data_runbook.md"
STATIC_ARTIFACTS = (
    CHECKS_FILE,
    BINDING_CHECKS_FILE,
    ACTION_QUEUE_FILE,
    SUMMARY_FILE,
    RECEIPT_FILE,
    CONFIG_FILE,
    RUNBOOK_FILE,
)
BINDING_CHECK_COLUMNS = (
    "check",
    "component",
    "value",
    "operator",
    "expected",
    "passed",
    "reason",
)


@dataclass(frozen=True)
class ReviewedMappedDataConfig:
    output_filename: str = "normalized_data.csv"
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    filter_session: bool = True
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    require_all_mapped: bool = True


@dataclass(frozen=True)
class ApprovedMappingReviewInputs:
    mapping_review_dir: Path
    source_path: Path
    reviewed_mapping_path: Path
    adapter: str
    kind: str
    mapping_review_id: str
    mapping_review_sha256: str
    source_file_sha256: str
    source_header_sha256: str
    reviewed_mapping_sha256: str


@dataclass(frozen=True)
class ReviewedMappedDataReport:
    data: pd.DataFrame
    checks: pd.DataFrame
    binding_checks: pd.DataFrame
    action_queue: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("ready", False))
        )


@dataclass(frozen=True)
class ReviewedMappedDataVerification:
    verified: bool
    ready: bool
    blocked: bool
    manifest_current: bool
    mapping_review_current: bool
    source_current: bool
    reviewed_mapping_current: bool
    artifacts_consistent: bool
    normalization_only: bool
    non_routing: bool
    output_dir: Path
    mapping_review_dir: Path | None = None
    source_path: Path | None = None
    reviewed_mapping_path: Path | None = None
    error: str = ""


def approved_mapping_review_inputs(
    mapping_review_dir: str | Path,
) -> ApprovedMappingReviewInputs:
    """Resolve only semantically verified, approved review-bound inputs."""
    review = _review_contract(Path(mapping_review_dir).resolve())
    return ApprovedMappingReviewInputs(
        mapping_review_dir=Path(review["root"]),
        source_path=Path(review["source_path"]),
        reviewed_mapping_path=Path(review["mapping_path"]),
        adapter=str(review["adapter"]),
        kind=str(review["kind"]),
        mapping_review_id=str(review["mapping_review_id"]),
        mapping_review_sha256=str(review["mapping_review_sha256"]),
        source_file_sha256=str(review["source_sha256"]),
        source_header_sha256=str(review["source_header_sha256"]),
        reviewed_mapping_sha256=str(review["mapping_sha256"]),
    )


def write_reviewed_mapped_data_normalization(
    mapping_review_dir: str | Path,
    *,
    output_dir: str | Path,
    config: ReviewedMappedDataConfig | None = None,
) -> ReviewedMappedDataReport:
    config = config or ReviewedMappedDataConfig()
    _validate_config(config)
    review_root = Path(mapping_review_dir).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"reviewed mapped-data output already exists: {out}")
    if _is_relative_to(out, review_root):
        raise ValueError("reviewed normalization output cannot modify mapping-review evidence")

    review = _review_contract(review_root)
    source_path = review["source_path"]
    mapping_path = review["mapping_path"]
    source_sha256 = file_sha256(source_path)
    mapping_sha256 = file_sha256(mapping_path)
    report = _assemble_report(review=review, config=config)

    out.mkdir(parents=True)
    _write_csv(report.data, out / config.output_filename)
    _write_csv(report.checks, out / CHECKS_FILE)
    _write_csv(report.binding_checks, out / BINDING_CHECKS_FILE)
    _write_csv(report.action_queue, out / ACTION_QUEUE_FILE)
    _write_csv(report.summary, out / SUMMARY_FILE)
    _write_json(out / RECEIPT_FILE, report.receipt)
    _write_json(out / CONFIG_FILE, report.config)
    (out / RUNBOOK_FILE).write_text(
        _runbook_markdown(
            report.summary.iloc[0],
            report.binding_checks,
            report.action_queue,
        ),
        encoding="utf-8",
    )

    final_review = verify_vendor_mapping_review(review_root)
    if (
        not final_review.verified
        or not final_review.approved
        or file_sha256(source_path) != source_sha256
        or file_sha256(mapping_path) != mapping_sha256
    ):
        raise RuntimeError(
            "mapping review, vendor source, or reviewed mapping changed during normalization"
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "mapping_review": review_root,
            "mapping_review_manifest": review_root / MANIFEST_NAME,
            "mapping_review_receipt": review_root / MAPPING_REVIEW_RECEIPT_FILE,
            "vendor_source": source_path,
            "reviewed_mapping": mapping_path,
        },
        extra=_manifest_extra(report),
    )
    return ReviewedMappedDataReport(
        data=report.data,
        checks=report.checks,
        binding_checks=report.binding_checks,
        action_queue=report.action_queue,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_reviewed_mapped_data_normalization(
    normalization_dir: str | Path,
) -> ReviewedMappedDataVerification:
    candidate = Path(normalization_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=STATIC_ARTIFACTS,
        require_input_fingerprints=True,
    )
    review_root: Path | None = None
    source_path: Path | None = None
    mapping_path: Path | None = None
    review_current = False
    source_current = False
    mapping_current = False
    try:
        manifest = _read_json(manifest_path, "reviewed mapped-data manifest")
        config = _config_from_manifest(manifest)
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=RUN_TYPE,
            required_artifacts=(*STATIC_ARTIFACTS, config.output_filename),
            require_input_fingerprints=True,
        )
        inputs = _mapping(manifest.get("inputs"))
        review_root = _fingerprint_path(inputs.get("mapping_review"), "directory")
        source_path = _fingerprint_path(inputs.get("vendor_source"), "file")
        mapping_path = _fingerprint_path(inputs.get("reviewed_mapping"), "file")
        review_verification = verify_vendor_mapping_review(review_root)
        review_current = bool(
            review_verification.verified and review_verification.approved
        )
        source_current = _fingerprint_current(
            inputs.get("vendor_source"), source_path
        )
        mapping_current = _fingerprint_current(
            inputs.get("reviewed_mapping"), mapping_path
        )
        if not (review_current and source_current and mapping_current):
            return _failed_verification(
                root,
                review_root=review_root,
                source_path=source_path,
                mapping_path=mapping_path,
                manifest_current=integrity.passed,
                review_current=review_current,
                source_current=source_current,
                mapping_current=mapping_current,
                error="reviewed mapped-data source is stale",
            )

        review = _review_contract(review_root)
        if review["source_path"] != source_path or review["mapping_path"] != mapping_path:
            raise ValueError("normalization inputs do not match the approved mapping review")
        expected = _assemble_report(review=review, config=config)
        actual_data = _read_csv(
            root / config.output_filename,
            "reviewed normalized data",
        )
        actual_checks = _read_csv(root / CHECKS_FILE, "mapped-data checks")
        actual_binding = _read_csv(
            root / BINDING_CHECKS_FILE,
            "mapped-data review checks",
        )
        actual_actions = _read_csv(root / ACTION_QUEUE_FILE, "mapped-data actions")
        actual_summary = _read_csv(root / SUMMARY_FILE, "mapped-data summary")
        actual_receipt = _read_json(root / RECEIPT_FILE, "mapped-data receipt")
        actual_config = _read_json(root / CONFIG_FILE, "mapped-data config")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        summary_row = _single_row(actual_summary, "mapped-data summary")
        artifacts_consistent = bool(
            _dataframe_equal(actual_data, expected.data)
            and _dataframe_equal(actual_checks, expected.checks)
            and _dataframe_equal(actual_binding, expected.binding_checks)
            and _dataframe_equal(actual_actions, expected.action_queue)
            and _dataframe_equal(actual_summary, expected.summary)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config)
            and actual_runbook
            == _runbook_markdown(
                expected.summary.iloc[0],
                expected.binding_checks,
                expected.action_queue,
            )
            and _jsonable(manifest.get("parameters"))
            == {"config": _jsonable(asdict(config))}
            and _jsonable(manifest.get("extra"))
            == _jsonable(_manifest_extra(expected))
            and _manifest_input_contract_current(
                inputs,
                review_root=review_root,
                source_path=source_path,
                mapping_path=mapping_path,
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
        verified = bool(
            integrity.passed
            and review_current
            and source_current
            and mapping_current
            and artifacts_consistent
            and normalization_only
            and non_routing
        )
        ready = bool(verified and expected.ready)
        return ReviewedMappedDataVerification(
            verified=verified,
            ready=ready,
            blocked=bool(verified and not ready),
            manifest_current=integrity.passed,
            mapping_review_current=review_current,
            source_current=source_current,
            reviewed_mapping_current=mapping_current,
            artifacts_consistent=artifacts_consistent,
            normalization_only=normalization_only,
            non_routing=non_routing,
            output_dir=root,
            mapping_review_dir=review_root,
            source_path=source_path,
            reviewed_mapping_path=mapping_path,
            error=""
            if verified
            else (integrity.error or "reviewed mapped-data semantic verification failed"),
        )
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return _failed_verification(
            root,
            review_root=review_root,
            source_path=source_path,
            mapping_path=mapping_path,
            manifest_current=integrity.passed,
            review_current=review_current,
            source_current=source_current,
            mapping_current=mapping_current,
            error=str(exc),
        )


def _assemble_report(
    *,
    review: Mapping[str, Any],
    config: ReviewedMappedDataConfig,
) -> ReviewedMappedDataReport:
    source_path = Path(str(review["source_path"]))
    mapping_path = Path(str(review["mapping_path"]))
    raw = _read_csv(source_path, "reviewed vendor source")
    mapping = _read_csv(mapping_path, "approved reviewed mapping")
    normalization_config = MappedDataConfig(
        adapter=str(review["adapter"]),
        kind=str(review["kind"]),
        output_filename=config.output_filename,
        timestamp_unit=config.timestamp_unit,
        timestamp_tz=config.timestamp_tz,
        filter_session=config.filter_session,
        market=config.market,
        require_all_mapped=config.require_all_mapped,
    )
    normalized = normalize_mapped_data(raw, mapping, config=normalization_config)
    action_queue = (
        normalized.action_queue.copy()
        if normalized.action_queue is not None
        else pd.DataFrame()
    )
    if not action_queue.empty:
        action_queue["next_gate"] = "normalize-reviewed-mapped-data"
        action_queue["next_gate_help_command"] = (
            "python -m hft_cli normalize-reviewed-mapped-data --help"
        )
    binding_checks = _binding_checks(review)
    if not binding_checks["passed"].map(_bool).all():
        failed = binding_checks.loc[
            ~binding_checks["passed"].map(_bool),
            "check",
        ].astype(str).tolist()
        raise ValueError(
            "reviewed mapped-data binding contract failed: " + ", ".join(failed)
        )

    summary = normalized.summary.copy()
    index = summary.index[0]
    summary.at[index, "next_gate"] = (
        "" if action_queue.empty else "normalize-reviewed-mapped-data"
    )
    summary.at[index, "next_gate_help_command"] = (
        ""
        if action_queue.empty
        else "python -m hft_cli normalize-reviewed-mapped-data --help"
    )
    summary.at[index, "review_bound"] = True
    summary.at[index, "mapping_review_verified"] = True
    summary.at[index, "mapping_review_approved"] = True
    summary.at[index, "mapping_review_id"] = str(review["mapping_review_id"])
    summary.at[index, "mapping_review_sha256"] = str(
        review["mapping_review_sha256"]
    )
    summary.at[index, "mapping_review_manifest_sha256"] = str(
        review["mapping_review_manifest_sha256"]
    )
    summary.at[index, "source_file_sha256"] = str(review["source_sha256"])
    summary.at[index, "reviewed_mapping_sha256"] = str(review["mapping_sha256"])
    summary.at[index, "binding_check_count"] = int(len(binding_checks))
    summary.at[index, "failed_binding_check_count"] = 0
    for field, value in _safety_payload().items():
        summary.at[index, field] = value

    receipt_core = _receipt_core(
        review=review,
        config=config,
        data=normalized.data,
        checks=normalized.checks,
        binding_checks=binding_checks,
        action_queue=action_queue,
        summary=summary.iloc[0],
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "normalization_receipt_id": (
            f"reviewed-mapped-data-{receipt_sha256[:24]}"
        ),
        "normalization_receipt_sha256": receipt_sha256,
    }
    summary.at[index, "normalization_receipt_id"] = str(
        receipt["normalization_receipt_id"]
    )
    summary.at[index, "normalization_receipt_sha256"] = receipt_sha256
    config_payload = _config_payload(
        review=review,
        config=config,
        summary=summary.iloc[0],
        action_queue=action_queue,
        receipt=receipt,
    )
    return ReviewedMappedDataReport(
        data=normalized.data,
        checks=normalized.checks,
        binding_checks=binding_checks,
        action_queue=action_queue,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _review_contract(review_root: Path) -> dict[str, Any]:
    verification = verify_vendor_mapping_review(review_root)
    if not verification.verified or not verification.approved:
        state = "rejected" if verification.rejected else "stale_or_inconsistent"
        raise ValueError(
            "reviewed normalization requires a verified approved mapping review: "
            f"{state}; {verification.error}"
        )
    receipt = _read_json(
        review_root / MAPPING_REVIEW_RECEIPT_FILE,
        "vendor mapping review receipt",
    )
    review_config = _read_json(
        review_root / MAPPING_REVIEW_CONFIG_FILE,
        "vendor mapping review config",
    )
    identity = _mapping(receipt.get("identity"))
    intake = _mapping(receipt.get("intake"))
    mapping = _mapping(receipt.get("mapping"))
    safety = _mapping(receipt.get("safety"))
    output_name = str(mapping.get("reviewed_file", ""))
    output_path = Path(output_name)
    if (
        not output_name
        or output_path.is_absolute()
        or len(output_path.parts) != 1
        or output_path.name in {"", ".", ".."}
    ):
        raise ValueError("mapping review does not name a safe reviewed mapping file")
    source_path = Path(str(intake.get("source_path", ""))).resolve()
    mapping_path = (review_root / output_path.name).resolve()
    if not source_path.is_file() or not mapping_path.is_file():
        raise ValueError("mapping review source or reviewed mapping is missing")
    adapter = _identity(identity.get("adapter"))
    kind = _identity(identity.get("kind"))
    review_id = _text(receipt.get("mapping_review_id"))
    review_sha256 = _text(receipt.get("mapping_review_sha256"))
    source_sha256 = _text(intake.get("source_file_sha256"))
    source_header_sha256 = _text(intake.get("source_header_sha256"))
    mapping_sha256 = _text(mapping.get("reviewed_sha256"))
    if not all(
        (
            adapter,
            kind,
            review_id,
            review_sha256,
            source_sha256,
            source_header_sha256,
            mapping_sha256,
        )
    ):
        raise ValueError("mapping review identity or fingerprints are incomplete")
    if file_sha256(source_path) != source_sha256:
        raise ValueError("mapping review vendor source fingerprint is stale")
    if file_sha256(mapping_path) != mapping_sha256:
        raise ValueError("mapping review reviewed-mapping fingerprint is stale")
    if not _explicit_true_mapping(safety, "authorizes_normalization"):
        raise ValueError("mapping review does not authorize normalization")
    if not _mapping_review_safety_valid(safety):
        raise ValueError("mapping review safety contract is inconsistent")
    if not _bool(review_config.get("approved_for_normalization", False)):
        raise ValueError("mapping review config does not preserve approval")
    return {
        "root": review_root,
        "source_path": source_path,
        "mapping_path": mapping_path,
        "adapter": adapter,
        "kind": kind,
        "mapping_review_id": review_id,
        "mapping_review_sha256": review_sha256,
        "mapping_review_manifest_sha256": file_sha256(review_root / MANIFEST_NAME),
        "mapping_review_receipt_sha256": file_sha256(
            review_root / MAPPING_REVIEW_RECEIPT_FILE
        ),
        "source_sha256": source_sha256,
        "source_header_sha256": source_header_sha256,
        "mapping_sha256": mapping_sha256,
    }


def _binding_checks(review: Mapping[str, Any]) -> pd.DataFrame:
    review_root = Path(str(review["root"]))
    source_path = Path(str(review["source_path"]))
    mapping_path = Path(str(review["mapping_path"]))
    rows = [
        _binding_check(
            "mapping_review_semantically_verified",
            "mapping_review",
            True,
            "is",
            True,
            True,
            "mapping review is not semantically verified",
        ),
        _binding_check(
            "mapping_review_approved",
            "mapping_review",
            True,
            "is",
            True,
            True,
            "mapping review is not approved",
        ),
        _binding_check(
            "vendor_source_current",
            "source",
            file_sha256(source_path),
            "==",
            review["source_sha256"],
            file_sha256(source_path) == review["source_sha256"],
            "vendor source does not match the mapping review",
        ),
        _binding_check(
            "reviewed_mapping_current",
            "mapping",
            file_sha256(mapping_path),
            "==",
            review["mapping_sha256"],
            file_sha256(mapping_path) == review["mapping_sha256"],
            "reviewed mapping does not match the mapping review",
        ),
        _binding_check(
            "adapter_derived_from_review",
            "identity",
            review["adapter"],
            "nonempty",
            True,
            bool(review["adapter"]),
            "mapping review adapter is missing",
        ),
        _binding_check(
            "kind_derived_from_review",
            "identity",
            review["kind"],
            "nonempty",
            True,
            bool(review["kind"]),
            "mapping review data kind is missing",
        ),
        _binding_check(
            "mapping_review_directory_current",
            "mapping_review",
            str(review_root),
            "verified_directory",
            True,
            review_root.is_dir(),
            "mapping review directory is missing",
        ),
    ]
    return pd.DataFrame(rows, columns=BINDING_CHECK_COLUMNS)


def _binding_check(
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
        "reason": "" if passed else reason,
    }


def _receipt_core(
    *,
    review: Mapping[str, Any],
    config: ReviewedMappedDataConfig,
    data: pd.DataFrame,
    checks: pd.DataFrame,
    binding_checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    summary: pd.Series,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "operator_review_bound_mapped_data_normalization",
        "sealed": True,
        "ready": _bool(summary.get("ready", False)),
        "identity": {
            "adapter": str(review["adapter"]),
            "kind": str(review["kind"]),
            "market": config.market,
        },
        "mapping_review": {
            "path": str(review["root"]),
            "mapping_review_id": str(review["mapping_review_id"]),
            "mapping_review_sha256": str(review["mapping_review_sha256"]),
            "manifest_sha256": str(review["mapping_review_manifest_sha256"]),
            "receipt_sha256": str(review["mapping_review_receipt_sha256"]),
            "verified": True,
            "approved": True,
        },
        "source": {
            "path": str(review["source_path"]),
            "file_sha256": str(review["source_sha256"]),
            "size_bytes": int(Path(str(review["source_path"])).stat().st_size),
        },
        "mapping": {
            "path": str(review["mapping_path"]),
            "file_sha256": str(review["mapping_sha256"]),
        },
        "normalization": {
            "settings": _jsonable(asdict(config)),
            "output_file": config.output_filename,
            "input_rows": _int(summary.get("input_rows")),
            "output_rows": _int(summary.get("output_rows")),
            "failed_mapping_count": _int(summary.get("failed_mappings")),
            "normalized_data_sha256": _csv_sha256(data),
            "mapping_checks_sha256": _csv_sha256(checks),
            "binding_checks_sha256": _csv_sha256(binding_checks),
            "action_queue_sha256": _csv_sha256(action_queue),
        },
        "outcome": {
            "ready": _bool(summary.get("ready", False)),
            "failed_check_count": _int(summary.get("failed_check_count")),
            "failed_check_names": _split_items(summary.get("failed_check_names")),
            "action_queue_count": int(len(action_queue)),
            "blocked_action_count": _int(summary.get("blocked_action_count")),
        },
        "safety": _safety_payload(),
    }


def _config_payload(
    *,
    review: Mapping[str, Any],
    config: ReviewedMappedDataConfig,
    summary: pd.Series,
    action_queue: pd.DataFrame,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "normalization_receipt_id": _text(receipt.get("normalization_receipt_id")),
        "normalization_receipt_sha256": _text(
            receipt.get("normalization_receipt_sha256")
        ),
        "ready": _bool(summary.get("ready", False)),
        "identity": {
            "adapter": str(review["adapter"]),
            "kind": str(review["kind"]),
            "market": config.market,
        },
        "inputs": {
            "mapping_review": str(review["root"]),
            "vendor_source": str(review["source_path"]),
            "reviewed_mapping": str(review["mapping_path"]),
        },
        "mapping_review": {
            "mapping_review_id": str(review["mapping_review_id"]),
            "mapping_review_sha256": str(review["mapping_review_sha256"]),
            "verified": True,
            "approved": True,
        },
        "settings": _jsonable(asdict(config)),
        "normalization": {
            "input_rows": _int(summary.get("input_rows")),
            "output_rows": _int(summary.get("output_rows")),
            "output_file": config.output_filename,
            "failed_mappings": _int(summary.get("failed_mappings")),
        },
        "failed_check_count": _int(summary.get("failed_check_count")),
        "failed_check_names": _split_items(summary.get("failed_check_names")),
        "first_failed_reason": _text(summary.get("first_failed_reason")),
        "action_queue_count": int(len(action_queue)),
        "blocked_action_count": _int(summary.get("blocked_action_count")),
        "next_gate": _text(summary.get("next_gate")),
        "next_gate_help_command": _text(summary.get("next_gate_help_command")),
        "primary_action_status": _text(summary.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _records(action_queue),
        "safety": _safety_payload(),
    }


def _manifest_extra(report: ReviewedMappedDataReport) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "normalization_receipt_id": _text(
            report.receipt.get("normalization_receipt_id")
        ),
        "normalization_receipt_sha256": _text(
            report.receipt.get("normalization_receipt_sha256")
        ),
        "ready": report.ready,
        "identity": _jsonable(_mapping(report.receipt.get("identity"))),
        "mapping_review": _jsonable(
            _mapping(report.receipt.get("mapping_review"))
        ),
        "source": _jsonable(_mapping(report.receipt.get("source"))),
        "mapping": _jsonable(_mapping(report.receipt.get("mapping"))),
        "safety": _jsonable(_mapping(report.receipt.get("safety"))),
    }


def _safety_payload() -> dict[str, bool]:
    return {
        "reviewed_normalization_only": True,
        "operator_approved_mapping_required": True,
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


def _mapping_review_safety_valid(safety: Mapping[str, Any]) -> bool:
    false_fields = (
        "authorizes_strategy_research",
        "provider_network_called",
        "credential_environment_read",
        "credential_values_stored",
        "broker_api_called",
        "routing_enabled",
        "submission_enabled",
        "authorizes_routing",
        "authorizes_submission",
    )
    return bool(
        _explicit_true_mapping(safety, "mapping_review_only")
        and _explicit_true_mapping(safety, "operator_attested")
        and all(_explicit_false_mapping(safety, field) for field in false_fields)
    )


def _normalization_only_surfaces(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        _explicit_true_mapping(
            _surface_safety(surface),
            "reviewed_normalization_only",
        )
        and _explicit_true_mapping(
            _surface_safety(surface),
            "operator_approved_mapping_required",
        )
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
    nested = _mapping(surface.get("safety"))
    return nested if nested else surface


def _runbook_markdown(
    summary: pd.Series,
    binding_checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Reviewed Mapped-Data Normalization Runbook",
        "",
        f"- Semantically sealed: yes",
        f"- Ready: {_yes_no(_bool(summary.get('ready', False)))}",
        f"- Mapping review: `{_text(summary.get('mapping_review_id'))}`",
        f"- Adapter: `{_text(summary.get('adapter'))}`",
        f"- Kind: `{_text(summary.get('kind'))}`",
        f"- Input rows: {_int(summary.get('input_rows'))}",
        f"- Output rows: {_int(summary.get('output_rows'))}",
        f"- Failed mappings: {_int(summary.get('failed_mappings'))}",
        f"- Blocked actions: {_int(summary.get('blocked_action_count'))}",
        f"- Primary next gate: {_code(summary.get('next_gate'))}",
        "",
        "This receipt proves deterministic normalization under the exact approved mapping. "
        "It does not authorize strategy research, routing, submission, or live release.",
        "",
        "## Review Binding",
        "",
        _binding_checks_table(binding_checks),
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _binding_checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "No binding checks were recorded."
    lines = ["| Check | Component | Passed | Reason |", "|---|---|---:|---|"]
    for row in checks.to_dict(orient="records"):
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(row.get("check")),
                    _escape_cell(row.get("component")),
                    _yes_no(_bool(row.get("passed", False))),
                    _escape_cell(row.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No normalization actions are pending."
    lines = [
        "| Priority | Status | Check | Next gate | Reason |",
        "|---:|---|---|---|---|",
    ]
    for row in action_queue.to_dict(orient="records"):
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(row.get("priority")),
                    _escape_cell(row.get("queue_status")),
                    _escape_cell(row.get("check")),
                    _escape_cell(row.get("next_gate")),
                    _escape_cell(row.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _config_from_manifest(
    manifest: Mapping[str, Any],
) -> ReviewedMappedDataConfig:
    payload = _mapping(_mapping(manifest.get("parameters")).get("config"))
    expected = {field.name for field in fields(ReviewedMappedDataConfig)}
    if set(payload) != expected:
        raise ValueError(
            "reviewed mapped-data config contract is incomplete or unknown"
        )
    config = ReviewedMappedDataConfig(
        output_filename=str(payload["output_filename"]),
        timestamp_unit=str(payload["timestamp_unit"]),
        timestamp_tz=(
            None if payload["timestamp_tz"] is None else str(payload["timestamp_tz"])
        ),
        filter_session=_strict_bool(payload["filter_session"], "filter_session"),
        market=str(payload["market"]),
        require_all_mapped=_strict_bool(
            payload["require_all_mapped"],
            "require_all_mapped",
        ),
    )
    _validate_config(config)
    return config


def _validate_config(config: ReviewedMappedDataConfig) -> None:
    output = Path(config.output_filename)
    reserved = {name.lower() for name in (*STATIC_ARTIFACTS, MANIFEST_NAME)}
    if (
        not config.output_filename
        or output.is_absolute()
        or len(output.parts) != 1
        or output.name in {"", ".", ".."}
    ):
        raise ValueError("output_filename must be a filename within the output")
    if output.name.lower() in reserved:
        raise ValueError("output_filename conflicts with a normalization artifact")
    if not config.timestamp_unit:
        raise ValueError("timestamp_unit is required")
    if not config.market:
        raise ValueError("market is required")


def _manifest_input_contract_current(
    inputs: Mapping[str, Any],
    *,
    review_root: Path,
    source_path: Path,
    mapping_path: Path,
) -> bool:
    expected = {
        "mapping_review": (review_root, "directory"),
        "mapping_review_manifest": (review_root / MANIFEST_NAME, "file"),
        "mapping_review_receipt": (
            review_root / MAPPING_REVIEW_RECEIPT_FILE,
            "file",
        ),
        "vendor_source": (source_path, "file"),
        "reviewed_mapping": (mapping_path, "file"),
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
        raise ValueError(
            f"reviewed mapped-data manifest lacks a {kind} fingerprint"
        )
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
    review_root: Path | None,
    source_path: Path | None,
    mapping_path: Path | None,
    manifest_current: bool,
    review_current: bool,
    source_current: bool,
    mapping_current: bool,
    error: str,
) -> ReviewedMappedDataVerification:
    return ReviewedMappedDataVerification(
        verified=False,
        ready=False,
        blocked=False,
        manifest_current=manifest_current,
        mapping_review_current=review_current,
        source_current=source_current,
        reviewed_mapping_current=mapping_current,
        artifacts_consistent=False,
        normalization_only=False,
        non_routing=False,
        output_dir=root,
        mapping_review_dir=review_root,
        source_path=source_path,
        reviewed_mapping_path=mapping_path,
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
    if value is None or (
        isinstance(value, str) and value.strip().lower() in {"", "nan"}
    ):
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
    if isinstance(value, bool):
        return value
    if isinstance(value, Real):
        if _missing(value):
            return None
        return int(value) if float(value).is_integer() else float(value)
    if _missing(value):
        return None
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): _jsonable(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _first_action_record(frame: pd.DataFrame) -> dict[str, Any]:
    records = _records(frame)
    return records[0] if records else {}


def _split_items(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [item for item in text.split(";") if item]


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


def _strict_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a JSON boolean")


def _explicit_true_mapping(payload: Mapping[str, Any], field: str) -> bool:
    return field in payload and _bool(payload.get(field))


def _explicit_false_mapping(payload: Mapping[str, Any], field: str) -> bool:
    return field in payload and not _bool(payload.get(field), default=True)


def _int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else "none"


def _escape_cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")
