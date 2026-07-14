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
from adapters.vendor_mapping_application import (
    RECEIPT_FILE as MAPPING_APPLICATION_RECEIPT_FILE,
    approved_vendor_mapping_application_inputs,
)
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "target_applied_mapped_data_normalization"
CONTRACT_VERSION = "target_applied_mapped_data_normalization/v1"
CHECKS_FILE = "mapped_data_checks.csv"
BINDING_CHECKS_FILE = "mapped_data_application_checks.csv"
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
class AppliedMappedDataConfig:
    output_filename: str = "normalized_data.csv"
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    filter_session: bool = True
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    require_all_mapped: bool = True


@dataclass(frozen=True)
class AppliedMappedDataReport:
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
class AppliedMappedDataVerification:
    verified: bool
    ready: bool
    blocked: bool
    manifest_current: bool
    mapping_application_current: bool
    source_current: bool
    applied_mapping_current: bool
    artifacts_consistent: bool
    target_bound: bool
    normalization_only: bool
    non_routing: bool
    output_dir: Path
    mapping_application_dir: Path | None = None
    source_path: Path | None = None
    applied_mapping_path: Path | None = None
    error: str = ""


def write_applied_mapped_data_normalization(
    mapping_application_dir: str | Path,
    *,
    output_dir: str | Path,
    config: AppliedMappedDataConfig | None = None,
) -> AppliedMappedDataReport:
    """Normalize only the target and mapping retained by a verified application."""
    config = config or AppliedMappedDataConfig()
    _validate_config(config)
    application_root = Path(mapping_application_dir).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"applied mapped-data output already exists: {out}")
    if _is_relative_to(out, application_root):
        raise ValueError(
            "target-applied normalization output cannot modify mapping-application evidence"
        )

    application = _application_contract(application_root)
    source_path = Path(application["source_path"])
    mapping_path = Path(application["mapping_path"])
    source_sha256 = file_sha256(source_path)
    mapping_sha256 = file_sha256(mapping_path)
    report = _assemble_report(application=application, config=config)

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

    final_application = _application_contract(application_root)
    if (
        final_application != application
        or file_sha256(source_path) != source_sha256
        or file_sha256(mapping_path) != mapping_sha256
    ):
        raise RuntimeError(
            "mapping application, target source, or applied mapping changed during normalization"
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "mapping_application": application_root,
            "mapping_application_manifest": application_root / MANIFEST_NAME,
            "mapping_application_receipt": (
                application_root / MAPPING_APPLICATION_RECEIPT_FILE
            ),
            "target_source": source_path,
            "applied_mapping": mapping_path,
        },
        extra=_manifest_extra(report),
    )
    return AppliedMappedDataReport(
        data=report.data,
        checks=report.checks,
        binding_checks=report.binding_checks,
        action_queue=report.action_queue,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_applied_mapped_data_normalization(
    normalization_dir: str | Path,
) -> AppliedMappedDataVerification:
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
    application_root: Path | None = None
    source_path: Path | None = None
    mapping_path: Path | None = None
    application_current = False
    source_current = False
    mapping_current = False
    try:
        manifest = _read_json(manifest_path, "target-applied mapped-data manifest")
        config = _config_from_manifest(manifest)
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=RUN_TYPE,
            required_artifacts=(*STATIC_ARTIFACTS, config.output_filename),
            require_input_fingerprints=True,
        )
        inputs = _mapping(manifest.get("inputs"))
        application_root = _fingerprint_path(
            inputs.get("mapping_application"), "directory"
        )
        source_path = _fingerprint_path(inputs.get("target_source"), "file")
        mapping_path = _fingerprint_path(inputs.get("applied_mapping"), "file")
        source_current = _fingerprint_current(
            inputs.get("target_source"), source_path
        )
        mapping_current = _fingerprint_current(
            inputs.get("applied_mapping"), mapping_path
        )
        application = _application_contract(application_root)
        application_current = True
        if not (application_current and source_current and mapping_current):
            return _failed_verification(
                root,
                application_root=application_root,
                source_path=source_path,
                mapping_path=mapping_path,
                manifest_current=integrity.passed,
                application_current=application_current,
                source_current=source_current,
                mapping_current=mapping_current,
                error="target-applied mapped-data source is stale",
            )
        if (
            application["source_path"] != source_path
            or application["mapping_path"] != mapping_path
        ):
            raise ValueError(
                "normalization inputs do not match the verified target application"
            )
        expected = _assemble_report(application=application, config=config)
        actual_data = _read_csv(
            root / config.output_filename,
            "target-applied normalized data",
        )
        actual_checks = _read_csv(root / CHECKS_FILE, "mapped-data checks")
        actual_binding = _read_csv(
            root / BINDING_CHECKS_FILE,
            "mapped-data application checks",
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
                application_root=application_root,
                source_path=source_path,
                mapping_path=mapping_path,
            )
        )
        target_bound = _target_bound_surfaces(
            summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
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
            and application_current
            and source_current
            and mapping_current
            and artifacts_consistent
            and target_bound
            and normalization_only
            and non_routing
        )
        ready = bool(verified and expected.ready)
        return AppliedMappedDataVerification(
            verified=verified,
            ready=ready,
            blocked=bool(verified and not ready),
            manifest_current=integrity.passed,
            mapping_application_current=application_current,
            source_current=source_current,
            applied_mapping_current=mapping_current,
            artifacts_consistent=artifacts_consistent,
            target_bound=target_bound,
            normalization_only=normalization_only,
            non_routing=non_routing,
            output_dir=root,
            mapping_application_dir=application_root,
            source_path=source_path,
            applied_mapping_path=mapping_path,
            error=(
                ""
                if verified
                else (
                    integrity.error
                    or "target-applied mapped-data semantic verification failed"
                )
            ),
        )
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return _failed_verification(
            root,
            application_root=application_root,
            source_path=source_path,
            mapping_path=mapping_path,
            manifest_current=integrity.passed,
            application_current=application_current,
            source_current=source_current,
            mapping_current=mapping_current,
            error=str(exc),
        )


def _application_contract(application_root: Path) -> dict[str, Any]:
    inputs = approved_vendor_mapping_application_inputs(application_root)
    receipt = _read_json(
        application_root / MAPPING_APPLICATION_RECEIPT_FILE,
        "mapping application receipt",
    )
    safety = _mapping(receipt.get("safety"))
    if not _application_safety_valid(safety):
        raise ValueError("mapping application safety contract is inconsistent")
    return {
        "root": inputs.application_dir,
        "scope_review_dir": inputs.scope_review_dir,
        "target_intake_dir": inputs.target_intake_dir,
        "source_path": inputs.target_source_path,
        "mapping_path": inputs.applied_mapping_path,
        "adapter": inputs.adapter,
        "kind": inputs.kind,
        "mapping_application_id": inputs.mapping_application_id,
        "mapping_application_sha256": inputs.mapping_application_sha256,
        "mapping_application_manifest_sha256": file_sha256(
            application_root / MANIFEST_NAME
        ),
        "mapping_application_receipt_sha256": file_sha256(
            application_root / MAPPING_APPLICATION_RECEIPT_FILE
        ),
        "mapping_scope_review_id": inputs.mapping_scope_review_id,
        "mapping_scope_review_sha256": inputs.mapping_scope_review_sha256,
        "target_intake_receipt_id": inputs.target_intake_receipt_id,
        "source_sha256": inputs.target_source_file_sha256,
        "source_header_sha256": inputs.source_header_sha256,
        "mapping_sha256": inputs.reviewed_mapping_sha256,
    }


def _assemble_report(
    *,
    application: Mapping[str, Any],
    config: AppliedMappedDataConfig,
) -> AppliedMappedDataReport:
    source_path = Path(application["source_path"])
    mapping_path = Path(application["mapping_path"])
    raw = _read_csv(source_path, "target vendor source")
    mapping = _read_csv(mapping_path, "target-applied vendor mapping")
    normalization_config = MappedDataConfig(
        adapter=str(application["adapter"]),
        kind=str(application["kind"]),
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
        action_queue["next_gate"] = "normalize-applied-vendor-mapping"
        action_queue["next_gate_help_command"] = (
            "python -m hft_cli normalize-applied-vendor-mapping --help"
        )
    binding_checks = _binding_checks(application)
    if not binding_checks["passed"].map(_bool).all():
        failed = binding_checks.loc[
            ~binding_checks["passed"].map(_bool),
            "check",
        ].astype(str).tolist()
        raise ValueError(
            "target-applied mapped-data binding contract failed: "
            + ", ".join(failed)
        )

    summary = normalized.summary.copy()
    index = summary.index[0]
    summary.at[index, "next_gate"] = (
        "" if action_queue.empty else "normalize-applied-vendor-mapping"
    )
    summary.at[index, "next_gate_help_command"] = (
        ""
        if action_queue.empty
        else "python -m hft_cli normalize-applied-vendor-mapping --help"
    )
    summary.at[index, "target_application_bound"] = True
    summary.at[index, "mapping_application_verified"] = True
    summary.at[index, "mapping_application_ready"] = True
    summary.at[index, "mapping_application_id"] = str(
        application["mapping_application_id"]
    )
    summary.at[index, "mapping_application_sha256"] = str(
        application["mapping_application_sha256"]
    )
    summary.at[index, "mapping_application_manifest_sha256"] = str(
        application["mapping_application_manifest_sha256"]
    )
    summary.at[index, "mapping_scope_review_id"] = str(
        application["mapping_scope_review_id"]
    )
    summary.at[index, "mapping_scope_review_sha256"] = str(
        application["mapping_scope_review_sha256"]
    )
    summary.at[index, "target_intake_receipt_id"] = str(
        application["target_intake_receipt_id"]
    )
    summary.at[index, "source_file_sha256"] = str(application["source_sha256"])
    summary.at[index, "source_header_sha256"] = str(
        application["source_header_sha256"]
    )
    summary.at[index, "reviewed_mapping_sha256"] = str(
        application["mapping_sha256"]
    )
    summary.at[index, "application_binding_check_count"] = int(
        len(binding_checks)
    )
    summary.at[index, "failed_application_binding_check_count"] = 0
    for field, value in _safety_payload().items():
        summary.at[index, field] = value

    receipt_core = _receipt_core(
        application=application,
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
            f"target-applied-mapped-data-{receipt_sha256[:24]}"
        ),
        "normalization_receipt_sha256": receipt_sha256,
    }
    summary.at[index, "normalization_receipt_id"] = str(
        receipt["normalization_receipt_id"]
    )
    summary.at[index, "normalization_receipt_sha256"] = receipt_sha256
    config_payload = _config_payload(
        application=application,
        config=config,
        summary=summary.iloc[0],
        action_queue=action_queue,
        receipt=receipt,
    )
    return AppliedMappedDataReport(
        data=normalized.data,
        checks=normalized.checks,
        binding_checks=binding_checks,
        action_queue=action_queue,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _binding_checks(application: Mapping[str, Any]) -> pd.DataFrame:
    application_root = Path(application["root"])
    source_path = Path(application["source_path"])
    mapping_path = Path(application["mapping_path"])
    source_sha256 = file_sha256(source_path)
    mapping_sha256 = file_sha256(mapping_path)
    rows = [
        _binding_check(
            "mapping_application_semantically_verified",
            "mapping_application",
            True,
            "is",
            True,
            True,
            "mapping application is not semantically verified",
        ),
        _binding_check(
            "mapping_application_ready",
            "mapping_application",
            True,
            "is",
            True,
            True,
            "mapping application is not ready",
        ),
        _binding_check(
            "target_file_bound",
            "mapping_application",
            True,
            "is",
            True,
            True,
            "mapping application is not target-file bound",
        ),
        _binding_check(
            "exact_ordered_header_verified",
            "mapping_application",
            application["source_header_sha256"],
            "is_sha256",
            True,
            _is_sha256(application["source_header_sha256"]),
            "mapping application lacks an exact ordered-header fingerprint",
        ),
        _binding_check(
            "application_remains_non_authorizing",
            "mapping_application",
            False,
            "is",
            False,
            True,
            "mapping application incorrectly authorizes normalization",
        ),
        _binding_check(
            "target_source_current",
            "source",
            source_sha256,
            "==",
            application["source_sha256"],
            source_sha256 == application["source_sha256"],
            "target source does not match the mapping application",
        ),
        _binding_check(
            "applied_mapping_current",
            "mapping",
            mapping_sha256,
            "==",
            application["mapping_sha256"],
            mapping_sha256 == application["mapping_sha256"],
            "applied mapping does not match the mapping application",
        ),
        _binding_check(
            "adapter_derived_from_application",
            "identity",
            application["adapter"],
            "nonempty",
            True,
            bool(application["adapter"]),
            "mapping application adapter is missing",
        ),
        _binding_check(
            "kind_derived_from_application",
            "identity",
            application["kind"],
            "nonempty",
            True,
            bool(application["kind"]),
            "mapping application data kind is missing",
        ),
        _binding_check(
            "mapping_application_directory_current",
            "mapping_application",
            str(application_root),
            "verified_directory",
            True,
            application_root.is_dir(),
            "mapping application directory is missing",
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
    application: Mapping[str, Any],
    config: AppliedMappedDataConfig,
    data: pd.DataFrame,
    checks: pd.DataFrame,
    binding_checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    summary: pd.Series,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "target_application_bound_mapped_data_normalization",
        "sealed": True,
        "ready": _bool(summary.get("ready", False)),
        "identity": {
            "adapter": str(application["adapter"]),
            "kind": str(application["kind"]),
            "market": config.market,
        },
        "mapping_application": {
            "path": str(application["root"]),
            "id": str(application["mapping_application_id"]),
            "sha256": str(application["mapping_application_sha256"]),
            "manifest_sha256": str(
                application["mapping_application_manifest_sha256"]
            ),
            "receipt_sha256": str(
                application["mapping_application_receipt_sha256"]
            ),
            "verified": True,
            "ready": True,
            "authorizes_normalization": False,
        },
        "mapping_scope_review": {
            "path": str(application["scope_review_dir"]),
            "id": str(application["mapping_scope_review_id"]),
            "sha256": str(application["mapping_scope_review_sha256"]),
        },
        "target_intake": {
            "path": str(application["target_intake_dir"]),
            "receipt_id": str(application["target_intake_receipt_id"]),
        },
        "source": {
            "path": str(application["source_path"]),
            "file_sha256": str(application["source_sha256"]),
            "header_sha256": str(application["source_header_sha256"]),
            "size_bytes": int(Path(application["source_path"]).stat().st_size),
        },
        "mapping": {
            "path": str(application["mapping_path"]),
            "file_sha256": str(application["mapping_sha256"]),
        },
        "normalization": {
            "settings": _jsonable(asdict(config)),
            "output_file": config.output_filename,
            "input_rows": _int(summary.get("input_rows")),
            "output_rows": _int(summary.get("output_rows")),
            "failed_mapping_count": _int(summary.get("failed_mappings")),
            "normalized_data_sha256": _csv_sha256(data),
            "mapping_checks_sha256": _csv_sha256(checks),
            "application_checks_sha256": _csv_sha256(binding_checks),
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
    application: Mapping[str, Any],
    config: AppliedMappedDataConfig,
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
            "adapter": str(application["adapter"]),
            "kind": str(application["kind"]),
            "market": config.market,
        },
        "inputs": {
            "mapping_application": str(application["root"]),
            "target_source": str(application["source_path"]),
            "applied_mapping": str(application["mapping_path"]),
        },
        "mapping_application": {
            "id": str(application["mapping_application_id"]),
            "sha256": str(application["mapping_application_sha256"]),
            "verified": True,
            "ready": True,
            "authorizes_normalization": False,
        },
        "mapping_scope_review": {
            "id": str(application["mapping_scope_review_id"]),
            "sha256": str(application["mapping_scope_review_sha256"]),
        },
        "target_intake_receipt_id": str(application["target_intake_receipt_id"]),
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


def _manifest_extra(report: AppliedMappedDataReport) -> dict[str, Any]:
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
        "mapping_application": _jsonable(
            _mapping(report.receipt.get("mapping_application"))
        ),
        "mapping_scope_review": _jsonable(
            _mapping(report.receipt.get("mapping_scope_review"))
        ),
        "target_intake": _jsonable(
            _mapping(report.receipt.get("target_intake"))
        ),
        "source": _jsonable(_mapping(report.receipt.get("source"))),
        "mapping": _jsonable(_mapping(report.receipt.get("mapping"))),
        "safety": _jsonable(_mapping(report.receipt.get("safety"))),
    }


def _safety_payload() -> dict[str, bool]:
    return {
        "target_application_bound": True,
        "exact_header_verified": True,
        "operator_approved_mapping_required": True,
        "target_application_normalization_only": True,
        "normalization_executed": True,
        "application_authorizes_normalization": False,
        "authorizes_strategy_research": False,
        "provider_network_called": False,
        "credential_environment_read": False,
        "credential_values_stored": False,
        "broker_api_called": False,
        "routing_enabled": False,
        "submission_enabled": False,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "authorizes_live_release": False,
    }


def _application_safety_valid(safety: Mapping[str, Any]) -> bool:
    true_fields = (
        "target_file_bound",
        "exact_header_verified",
        "header_order_sensitive",
        "scope_review_required",
        "target_intake_required",
        "mapping_bytes_preserved",
        "authorizes_target_mapping_application",
    )
    false_fields = (
        "normalization_executed",
        "authorizes_normalization",
        "authorizes_strategy_research",
        "authorizes_routing",
        "authorizes_submission",
        "authorizes_live_release",
    )
    return bool(
        all(_explicit_true_mapping(safety, field) for field in true_fields)
        and all(_explicit_false_mapping(safety, field) for field in false_fields)
    )


def _target_bound_surfaces(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        _explicit_true_mapping(_surface_safety(surface), "target_application_bound")
        and _explicit_true_mapping(_surface_safety(surface), "exact_header_verified")
        and _explicit_true_mapping(
            _surface_safety(surface), "operator_approved_mapping_required"
        )
        for surface in surfaces
    )


def _normalization_only_surfaces(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        _explicit_true_mapping(
            _surface_safety(surface), "target_application_normalization_only"
        )
        and _explicit_true_mapping(_surface_safety(surface), "normalization_executed")
        and _explicit_false_mapping(
            _surface_safety(surface), "application_authorizes_normalization"
        )
        and _explicit_false_mapping(
            _surface_safety(surface), "authorizes_strategy_research"
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
        "authorizes_live_release",
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
        "# Target-Applied Mapped-Data Normalization Runbook",
        "",
        "- Semantically sealed: yes",
        f"- Ready: {_yes_no(_bool(summary.get('ready', False)))}",
        f"- Mapping application: `{_text(summary.get('mapping_application_id'))}`",
        f"- Mapping scope review: `{_text(summary.get('mapping_scope_review_id'))}`",
        f"- Adapter: `{_text(summary.get('adapter'))}`",
        f"- Kind: `{_text(summary.get('kind'))}`",
        f"- Input rows: {_int(summary.get('input_rows'))}",
        f"- Output rows: {_int(summary.get('output_rows'))}",
        f"- Failed mappings: {_int(summary.get('failed_mappings'))}",
        f"- Blocked actions: {_int(summary.get('blocked_action_count'))}",
        f"- Primary next gate: {_code(summary.get('next_gate'))}",
        "",
        "This receipt proves deterministic normalization of the exact target source "
        "under its verified target-applied mapping. The mapping application itself "
        "remains non-authorizing. This operation does not authorize strategy research, "
        "routing, submission, or live release.",
        "",
        "## Application Binding",
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


def _config_from_manifest(manifest: Mapping[str, Any]) -> AppliedMappedDataConfig:
    payload = _mapping(_mapping(manifest.get("parameters")).get("config"))
    expected = {field.name for field in fields(AppliedMappedDataConfig)}
    if set(payload) != expected:
        raise ValueError(
            "target-applied mapped-data config contract is incomplete or unknown"
        )
    config = AppliedMappedDataConfig(
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


def _validate_config(config: AppliedMappedDataConfig) -> None:
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
    application_root: Path,
    source_path: Path,
    mapping_path: Path,
) -> bool:
    expected = {
        "mapping_application": (application_root, "directory"),
        "mapping_application_manifest": (
            application_root / MANIFEST_NAME,
            "file",
        ),
        "mapping_application_receipt": (
            application_root / MAPPING_APPLICATION_RECEIPT_FILE,
            "file",
        ),
        "target_source": (source_path, "file"),
        "applied_mapping": (mapping_path, "file"),
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
            f"target-applied mapped-data manifest lacks a {kind} fingerprint"
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
    application_root: Path | None,
    source_path: Path | None,
    mapping_path: Path | None,
    manifest_current: bool,
    application_current: bool,
    source_current: bool,
    mapping_current: bool,
    error: str,
) -> AppliedMappedDataVerification:
    return AppliedMappedDataVerification(
        verified=False,
        ready=False,
        blocked=False,
        manifest_current=manifest_current,
        mapping_application_current=application_current,
        source_current=source_current,
        applied_mapping_current=mapping_current,
        artifacts_consistent=False,
        target_bound=False,
        normalization_only=False,
        non_routing=False,
        output_dir=root,
        mapping_application_dir=application_root,
        source_path=source_path,
        applied_mapping_path=mapping_path,
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


def _is_sha256(value: Any) -> bool:
    text = _text(value)
    return bool(
        len(text) == 64
        and text == text.lower()
        and all(character in "0123456789abcdef" for character in text)
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")
