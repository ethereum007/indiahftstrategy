from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.data_readiness import (
    DATA_READINESS_SUMMARY_FILE,
    verify_data_readiness_report,
)
from reports.manifest import (
    MANIFEST_NAME,
    ManifestIntegrity,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


DATA_READINESS_COMPARISON_RUN_TYPE = "data_readiness_comparison"
DATA_READINESS_COMPARISON_RUNS_FILE = "data_readiness_runs.csv"
DATA_READINESS_COMPARISON_CHECKS_FILE = (
    "data_readiness_comparison_checks.csv"
)
DATA_READINESS_COMPARISON_SUMMARY_FILE = "data_readiness_comparison_summary.csv"
DATA_READINESS_COMPARISON_ACTION_QUEUE_FILE = (
    "data_readiness_comparison_action_queue.csv"
)
DATA_READINESS_COMPARISON_CONFIG_FILE = (
    "data_readiness_comparison_config.json"
)
DATA_READINESS_COMPARISON_RUNBOOK_FILE = (
    "data_readiness_comparison_runbook.md"
)
DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS = (
    DATA_READINESS_COMPARISON_RUNS_FILE,
    DATA_READINESS_COMPARISON_CHECKS_FILE,
    DATA_READINESS_COMPARISON_SUMMARY_FILE,
    DATA_READINESS_COMPARISON_ACTION_QUEUE_FILE,
    DATA_READINESS_COMPARISON_CONFIG_FILE,
    DATA_READINESS_COMPARISON_RUNBOOK_FILE,
)
DATA_READINESS_COMPARISON_REQUIRED_SUMMARY_COLUMNS = (
    "accepted",
    "dataset_count",
    "ready_rate",
    "total_failed_checks",
    "recommendation",
)


@dataclass(frozen=True)
class DataReadinessComparisonThresholds:
    min_datasets: int = 1
    min_ready_datasets: int | None = None
    min_ready_rate: float = 1.0
    max_total_failed_checks: int = 0
    min_unique_source_files: int | None = None
    min_unique_observation_dates: int | None = None
    min_source_file_fingerprint_coverage: float | None = None
    min_mapping_coverage: float | None = None
    require_market_calendar: bool = False
    require_consistent_market_calendar: bool = False


@dataclass(frozen=True)
class DataReadinessComparisonReport:
    dataset_runs: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def accepted(self) -> bool:
        return bool(self.summary.iloc[0]["accepted"]) if not self.summary.empty else False


@dataclass(frozen=True)
class DataReadinessComparisonReportVerification:
    verified: bool
    accepted: bool
    manifest_current: bool
    inputs_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    output_dir: Path
    manifest_path: Path
    manifest_artifact_count: int = 0
    manifest_artifact_match_count: int = 0
    manifest_input_fingerprint_count: int = 0
    manifest_input_fingerprint_match_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class DataReadinessComparisonEvidence:
    summary: pd.DataFrame
    requested_path: Path | None = None
    root: Path | None = None
    summary_path: Path | None = None
    manifest_path: Path | None = None
    manifest_integrity: ManifestIntegrity | None = None
    verification: DataReadinessComparisonReportVerification | None = None
    read_error: str = ""

    @property
    def requested(self) -> bool:
        return self.requested_path is not None

    @property
    def provided(self) -> bool:
        return not self.summary.empty

    @property
    def accepted(self) -> bool:
        return bool(self.provided and _to_bool(self.summary.iloc[0].get("accepted", False)))

    @property
    def manifest_current(self) -> bool:
        return bool(self.manifest_integrity is not None and self.manifest_integrity.passed)

    @property
    def semantically_verified(self) -> bool:
        return bool(
            self.verification is not None
            and self.verification.verified
        )

    @property
    def passed(self) -> bool:
        return bool(
            not self.read_error
            and self.accepted
            and self.manifest_current
            and self.semantically_verified
        )

    @property
    def reason(self) -> str:
        if not self.requested:
            return "data_readiness_comparison_missing"
        if self.read_error:
            return f"data_readiness_comparison_{self.read_error}"
        if not self.manifest_current:
            error = (
                self.manifest_integrity.error
                if self.manifest_integrity is not None and self.manifest_integrity.error
                else "invalid"
            )
            suffix = error if error.startswith("manifest_") else f"manifest_{error}"
            return f"data_readiness_comparison_{suffix}"
        if not self.semantically_verified:
            error = (
                self.verification.error
                if self.verification is not None
                else ""
            )
            return (
                "data_readiness_comparison_"
                + _verification_error_slug(error)
            )
        if not self.accepted:
            return "data_readiness_comparison_not_accepted"
        return "accepted"

    @property
    def recommendation(self) -> str:
        if (
            not self.provided
            or not self.manifest_current
            or not self.semantically_verified
            or self.read_error
        ):
            return self.reason
        value = str(self.summary.iloc[0].get("recommendation", "")).strip()
        return value or self.reason


def load_data_readiness_comparison_evidence(
    path: str | Path | None,
) -> DataReadinessComparisonEvidence:
    if path is None:
        return DataReadinessComparisonEvidence(summary=pd.DataFrame())

    requested = Path(path).resolve()
    if requested.is_file() or requested.suffix.lower() == ".csv":
        root = requested.parent
        summary_path = requested
    else:
        root = requested
        summary_path = root / DATA_READINESS_COMPARISON_SUMMARY_FILE
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    verification = verify_data_readiness_comparison(root)

    summary = pd.DataFrame()
    read_error = ""
    if not summary_path.is_file():
        read_error = "summary_missing"
    else:
        try:
            summary = pd.read_csv(summary_path)
        except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
            read_error = "summary_unreadable"
        if not read_error and summary.empty:
            read_error = "summary_empty"
        if not read_error and len(summary.index) != 1:
            read_error = "summary_row_count_invalid"
        if not read_error:
            missing = [
                column
                for column in DATA_READINESS_COMPARISON_REQUIRED_SUMMARY_COLUMNS
                if column not in summary.columns
            ]
            if missing:
                read_error = "summary_schema_invalid"

    return DataReadinessComparisonEvidence(
        summary=summary,
        requested_path=requested,
        root=root,
        summary_path=summary_path,
        manifest_path=manifest_path,
        manifest_integrity=integrity,
        verification=verification,
        read_error=read_error,
    )


def data_readiness_comparison_evidence_record(
    evidence: DataReadinessComparisonEvidence,
) -> dict[str, object]:
    row = evidence.summary.iloc[0] if evidence.provided else pd.Series(dtype=object)
    integrity = evidence.manifest_integrity
    verification = evidence.verification
    manifest_path = evidence.manifest_path
    manifest_sha256 = ""
    if manifest_path is not None and manifest_path.is_file():
        try:
            manifest_sha256 = file_sha256(manifest_path)
        except OSError:
            manifest_sha256 = ""
    return {
        "requested": evidence.requested,
        "provided": evidence.provided,
        "manifest_required": evidence.requested,
        "semantic_verification_required": evidence.requested,
        "verified": evidence.passed,
        "read_error": evidence.read_error,
        "input_dir": str(evidence.root or ""),
        "summary_path": str(evidence.summary_path or ""),
        "accepted": evidence.accepted,
        "manifest_provided": bool(integrity is not None and integrity.exists),
        "manifest_current": evidence.manifest_current,
        "manifest_error": str(integrity.error if integrity is not None else ""),
        "manifest_run_type": str(integrity.run_type if integrity is not None else ""),
        "manifest_run_type_matches": bool(
            integrity is not None and integrity.run_type_matches
        ),
        "manifest_path": str(manifest_path or ""),
        "manifest_sha256": manifest_sha256,
        "manifest_artifact_count": int(integrity.artifact_count if integrity is not None else 0),
        "manifest_artifact_match_count": int(
            integrity.artifact_match_count if integrity is not None else 0
        ),
        "manifest_input_fingerprint_count": int(
            integrity.input_fingerprint_count if integrity is not None else 0
        ),
        "manifest_input_fingerprint_match_count": int(
            integrity.input_fingerprint_match_count if integrity is not None else 0
        ),
        "semantically_verified": evidence.semantically_verified,
        "verification_inputs_current": bool(
            verification is not None
            and verification.inputs_current
        ),
        "verification_artifacts_consistent": bool(
            verification is not None
            and verification.artifacts_consistent
        ),
        "verification_non_authorizing": bool(
            verification is not None
            and verification.non_authorizing
        ),
        "verification_error": str(
            verification.error if verification is not None else ""
        ),
        "dataset_count": int(_number(row, "dataset_count", fallback=0.0)),
        "ready_rate": _number(row, "ready_rate", fallback=0.0),
        "failed_checks": int(_number(row, "total_failed_checks", fallback=0.0)),
        "reason": evidence.reason,
        "recommendation": evidence.recommendation,
    }


def data_readiness_comparison_check(
    evidence: DataReadinessComparisonEvidence,
    *,
    required: bool,
) -> dict[str, object] | None:
    if not evidence.requested and not required:
        return None
    details = data_readiness_comparison_evidence_record(evidence)
    passed = evidence.passed
    return {
        **details,
        "check": "data_readiness_comparison",
        "value": bool(details["accepted"]),
        "operator": "accepted_and_manifest_current",
        "threshold": True,
        "passed": bool(passed),
        "required": bool(required),
        "failed_checks": 0
        if passed
        else max(1, int(details["failed_checks"])),
    }


def compare_data_readiness(
    datasets: pd.DataFrame,
    *,
    thresholds: DataReadinessComparisonThresholds | None = None,
) -> DataReadinessComparisonReport:
    thresholds = thresholds or DataReadinessComparisonThresholds()
    _validate_thresholds(thresholds)
    _require(datasets, ["dataset", "ready", "failed_checks"], "data_readiness_runs")
    runs = datasets.copy().reset_index(drop=True)
    runs["ready"] = runs["ready"].map(_to_bool)
    lineage_columns_present = "data_readiness_manifest_required" in runs.columns
    verification_columns_present = (
        "data_readiness_report_verification_required" in runs.columns
    )
    if "reported_ready" not in runs.columns:
        runs["reported_ready"] = runs["ready"]
    runs["reported_ready"] = runs["reported_ready"].map(_to_bool)
    for column in (
        "data_readiness_manifest_required",
        "data_readiness_manifest_provided",
        "data_readiness_manifest_current",
    ):
        if column not in runs.columns:
            runs[column] = False
        runs[column] = runs[column].map(_to_bool)
    if not lineage_columns_present:
        runs["data_readiness_manifest_required"] = False
    for column in (
        "data_readiness_report_verification_required",
        "data_readiness_report_verified",
        "data_readiness_report_inputs_current",
        "data_readiness_report_artifacts_consistent",
        "data_readiness_report_non_authorizing",
    ):
        if column not in runs.columns:
            runs[column] = False
        runs[column] = runs[column].map(_to_bool)
    if not verification_columns_present:
        runs["data_readiness_report_verification_required"] = False
    runs["ready"] = runs["ready"] & (
        ~runs["data_readiness_report_verification_required"]
        | runs["data_readiness_report_verified"]
    )
    for column in (
        "data_readiness_manifest_error",
        "data_readiness_manifest_path",
        "data_readiness_manifest_sha256",
        "data_readiness_report_verification_error",
    ):
        if column not in runs.columns:
            runs[column] = ""
        runs[column] = runs[column].fillna("").astype(str).str.strip()
    for column in (
        "data_readiness_manifest_artifact_count",
        "data_readiness_manifest_artifact_match_count",
        "data_readiness_manifest_input_fingerprint_count",
        "data_readiness_manifest_input_fingerprint_match_count",
        "data_readiness_dependency_count",
    ):
        if column not in runs.columns:
            runs[column] = 0
        runs[column] = pd.to_numeric(runs[column], errors="coerce").fillna(0)
    for column in ("components", "required_components", "provided_components", "ready_components", "failed_checks"):
        if column not in runs.columns:
            runs[column] = 0.0
        runs[column] = pd.to_numeric(runs[column], errors="coerce")
    _coalesce_column(runs, "source_file_sha256", "vendor_intake_source_file_sha256", default="")
    _coalesce_column(runs, "source_header_sha256", "vendor_intake_source_header_sha256", default="")
    _coalesce_column(runs, "mapping_draft_sha256", "vendor_intake_mapping_draft_sha256", default="")
    _coalesce_column(runs, "mapping_coverage", "vendor_intake_mapping_coverage", default=np.nan)
    for column in (
        "source_file_sha256",
        "source_header_sha256",
        "mapping_draft_sha256",
        "market_calendar_id",
        "market_calendar_sha256",
        "market_calendar_valid_from",
        "market_calendar_valid_to",
    ):
        if column not in runs.columns:
            runs[column] = ""
        runs[column] = runs[column].fillna("").astype(str).str.strip()
    if "observation_dates" not in runs.columns:
        runs["observation_dates"] = ""
    normalized_observation_dates = runs["observation_dates"].map(
        _normalize_observation_dates
    )
    runs["observation_dates"] = normalized_observation_dates.map(
        lambda value: value[0]
    )
    runs["observation_date_count"] = normalized_observation_dates.map(
        lambda value: value[1]
    )
    runs["observation_date_parse_error_count"] = (
        normalized_observation_dates.map(lambda value: value[2])
    )
    if "mapping_coverage" not in runs.columns:
        runs["mapping_coverage"] = np.nan
    runs["mapping_coverage"] = pd.to_numeric(runs["mapping_coverage"], errors="coerce")
    summary = _summary(runs)
    checks = _checks(summary.iloc[0], thresholds)
    action_queue = _action_queue(checks)
    accepted = bool(checks["passed"].all()) if not checks.empty else False
    summary["accepted"] = accepted
    summary["non_authorizing"] = True
    summary["authorizes_routing"] = False
    summary["authorizes_submission"] = False
    summary["recommendation"] = "feed_walkforward_research" if accepted else "collect_or_fix_data"
    summary["ready_action_count"] = 0
    summary["blocked_action_count"] = int(len(action_queue))
    summary["next_gate"] = _primary_next_gate(action_queue)
    summary["next_gate_help_command"] = summary["next_gate"].map(_next_gate_help_command)
    return DataReadinessComparisonReport(
        dataset_runs=runs,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
    )


def write_data_readiness_comparison(
    readiness_dirs: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    thresholds: DataReadinessComparisonThresholds | None = None,
) -> DataReadinessComparisonReport:
    if not readiness_dirs:
        raise ValueError("at least one data readiness directory is required")
    if labels is not None and len(labels) != len(readiness_dirs):
        raise ValueError("labels must match readiness directories")
    thresholds = thresholds or DataReadinessComparisonThresholds()
    runs = _read_readiness_runs(readiness_dirs, labels=labels)
    report = compare_data_readiness(runs, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.dataset_runs.to_csv(
        out / DATA_READINESS_COMPARISON_RUNS_FILE,
        index=False,
    )
    report.checks.to_csv(
        out / DATA_READINESS_COMPARISON_CHECKS_FILE,
        index=False,
    )
    report.summary.to_csv(out / DATA_READINESS_COMPARISON_SUMMARY_FILE, index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(
        out / DATA_READINESS_COMPARISON_ACTION_QUEUE_FILE,
        index=False,
    )
    (out / DATA_READINESS_COMPARISON_CONFIG_FILE).write_text(
        json.dumps(
            _config(report.summary.iloc[0], report.dataset_runs, report.checks, action_queue, thresholds),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / DATA_READINESS_COMPARISON_RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], report.dataset_runs, report.checks, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        parameters={"labels": labels, "thresholds": asdict(thresholds)},
        inputs=_comparison_manifest_inputs(readiness_dirs),
        extra=_data_readiness_comparison_manifest_extra(report),
    )
    return DataReadinessComparisonReport(report.dataset_runs, report.checks, report.summary, out, action_queue)


def verify_data_readiness_comparison(
    report_dir: str | Path,
) -> DataReadinessComparisonReportVerification:
    requested = Path(report_dir)
    root = requested.parent if requested.is_file() else requested
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    inputs_current = False
    artifacts_consistent = False
    non_authorizing = False
    try:
        manifest = _read_json_object(
            manifest_path,
            "data-readiness comparison manifest",
        )
        parameters = _mapping(manifest.get("parameters"))
        labels, thresholds = _comparison_parameters_from_manifest(
            parameters
        )
        inputs = _mapping(manifest.get("inputs"))
        readiness_dirs = _comparison_readiness_paths_from_manifest(inputs)
        expected_report = compare_data_readiness(
            _read_readiness_runs(readiness_dirs, labels=labels),
            thresholds=thresholds,
        )
        expected_parameters = {
            "labels": labels,
            "thresholds": asdict(thresholds),
        }
        expected_extra = _data_readiness_comparison_manifest_extra(
            expected_report
        )
        inputs_current = bool(
            _comparison_input_contract_current(inputs, readiness_dirs)
            and integrity.input_fingerprint_count
            == integrity.input_fingerprint_match_count
            and integrity.input_fingerprint_count > 0
        )
        artifacts_consistent = bool(
            _comparison_artifacts_consistent(
                root,
                expected_report,
                thresholds,
                manifest,
            )
            and dict(parameters) == expected_parameters
            and _mapping(manifest.get("extra")) == expected_extra
        )
        non_authorizing = _comparison_authority_consistent(
            root,
            _mapping(manifest.get("extra")),
            expected_report.accepted,
        )
        verified = bool(
            integrity.passed
            and inputs_current
            and artifacts_consistent
            and non_authorizing
        )
        error = ""
        if not verified:
            error = (
                integrity.error
                or (
                    "input contract is invalid"
                    if not inputs_current
                    else ""
                )
                or (
                    "artifacts do not reconstruct from inputs"
                    if not artifacts_consistent
                    else ""
                )
                or "report widens authority"
            )
        return DataReadinessComparisonReportVerification(
            verified=verified,
            accepted=bool(verified and expected_report.accepted),
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            manifest_artifact_count=integrity.artifact_count,
            manifest_artifact_match_count=(
                integrity.artifact_match_count
            ),
            manifest_input_fingerprint_count=(
                integrity.input_fingerprint_count
            ),
            manifest_input_fingerprint_match_count=(
                integrity.input_fingerprint_match_count
            ),
            error=error,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        return DataReadinessComparisonReportVerification(
            verified=False,
            accepted=False,
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            manifest_artifact_count=integrity.artifact_count,
            manifest_artifact_match_count=(
                integrity.artifact_match_count
            ),
            manifest_input_fingerprint_count=(
                integrity.input_fingerprint_count
            ),
            manifest_input_fingerprint_match_count=(
                integrity.input_fingerprint_match_count
            ),
            error=integrity.error or str(exc),
        )


def _data_readiness_comparison_manifest_extra(
    report: DataReadinessComparisonReport,
) -> dict[str, object]:
    return {
        "accepted": report.accepted,
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }


def _comparison_parameters_from_manifest(
    parameters: Mapping[str, Any],
) -> tuple[list[str] | None, DataReadinessComparisonThresholds]:
    if set(parameters) != {"labels", "thresholds"}:
        raise ValueError(
            "comparison manifest parameters must contain labels and thresholds"
        )
    raw_labels = parameters.get("labels")
    if raw_labels is None:
        labels = None
    elif isinstance(raw_labels, list) and all(
        isinstance(value, str) for value in raw_labels
    ):
        labels = list(raw_labels)
    else:
        raise ValueError("comparison manifest labels must be a string list")
    values = _mapping(parameters.get("thresholds"))
    expected_fields = {
        field.name
        for field in fields(DataReadinessComparisonThresholds)
    }
    if set(values) != expected_fields:
        raise ValueError(
            "comparison manifest threshold contract is incomplete"
        )
    thresholds = DataReadinessComparisonThresholds(**dict(values))
    _validate_thresholds(thresholds)
    expected = {
        "labels": labels,
        "thresholds": asdict(thresholds),
    }
    if dict(parameters) != expected:
        raise ValueError(
            "comparison manifest parameters are not canonical"
        )
    return labels, thresholds


def _comparison_readiness_paths_from_manifest(
    inputs: Mapping[str, Any],
) -> list[Path]:
    value = inputs.get("readiness")
    if not isinstance(value, list) or not value:
        raise ValueError(
            "comparison manifest lacks readiness input fingerprints"
        )
    paths = [
        _manifest_path_fingerprint(item, "readiness")
        for item in value
    ]
    return paths


def _manifest_path_fingerprint(value: Any, label: str) -> Path:
    fingerprint = _mapping(value)
    if fingerprint.get("kind") not in {"file", "directory"}:
        raise ValueError(
            f"comparison manifest {label} input is not fingerprinted"
        )
    raw_path = str(fingerprint.get("path", "")).strip()
    if not raw_path:
        raise ValueError(
            f"comparison manifest {label} input path is missing"
        )
    return Path(raw_path).resolve()


def _comparison_input_contract_current(
    inputs: Mapping[str, Any],
    readiness_dirs: list[Path],
) -> bool:
    expected = _comparison_manifest_inputs(readiness_dirs)
    if set(inputs) != set(expected):
        return False
    return all(
        _manifest_input_path_contract(inputs.get(name))
        == _expected_input_path_contract(value)
        for name, value in expected.items()
    )


def _manifest_input_path_contract(value: Any) -> Any:
    if isinstance(value, list):
        return [
            _manifest_input_path_contract(item)
            for item in value
        ]
    fingerprint = _mapping(value)
    kind = str(fingerprint.get("kind", ""))
    raw_path = str(fingerprint.get("path", "")).strip()
    if kind not in {"file", "directory"} or not raw_path:
        return None
    return kind, str(Path(raw_path).resolve())


def _expected_input_path_contract(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [
            _expected_input_path_contract(item)
            for item in value
        ]
    if not isinstance(value, (str, Path)):
        return None
    path = Path(value).resolve()
    kind = (
        "file"
        if path.is_file()
        else "directory"
        if path.is_dir()
        else ""
    )
    return (kind, str(path)) if kind else None


def _comparison_artifacts_consistent(
    root: Path,
    expected: DataReadinessComparisonReport,
    thresholds: DataReadinessComparisonThresholds,
    manifest: Mapping[str, Any],
) -> bool:
    action_queue = (
        expected.action_queue
        if expected.action_queue is not None
        else _action_queue(expected.checks)
    )
    expected_config = _config(
        expected.summary.iloc[0],
        expected.dataset_runs,
        expected.checks,
        action_queue,
        thresholds,
    )
    return bool(
        _comparison_manifest_artifacts_exact(manifest)
        and _csv_frame_matches(
            root / DATA_READINESS_COMPARISON_RUNS_FILE,
            expected.dataset_runs,
        )
        and _csv_frame_matches(
            root / DATA_READINESS_COMPARISON_CHECKS_FILE,
            expected.checks,
        )
        and _csv_frame_matches(
            root / DATA_READINESS_COMPARISON_SUMMARY_FILE,
            expected.summary,
        )
        and _csv_frame_matches(
            root / DATA_READINESS_COMPARISON_ACTION_QUEUE_FILE,
            action_queue,
        )
        and _read_json_object(
            root / DATA_READINESS_COMPARISON_CONFIG_FILE,
            "data-readiness comparison config",
        )
        == expected_config
        and (root / DATA_READINESS_COMPARISON_RUNBOOK_FILE).read_text(
            encoding="utf-8"
        )
        == _runbook_markdown(
            expected.summary.iloc[0],
            expected.dataset_runs,
            expected.checks,
            action_queue,
        )
    )


def _comparison_manifest_artifacts_exact(
    manifest: Mapping[str, Any],
) -> bool:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    names = [
        str(item.get("path", "")).replace("\\", "/")
        for item in artifacts
        if isinstance(item, Mapping)
    ]
    return bool(
        len(names) == len(DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS)
        and len(names) == len(artifacts)
        and set(names)
        == set(DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS)
    )


def _comparison_authority_consistent(
    root: Path,
    manifest_extra: Mapping[str, Any],
    accepted: bool,
) -> bool:
    summary = _read_csv_frame(
        root / DATA_READINESS_COMPARISON_SUMMARY_FILE,
        "data-readiness comparison summary",
    )
    config = _read_json_object(
        root / DATA_READINESS_COMPARISON_CONFIG_FILE,
        "data-readiness comparison config",
    )
    if len(summary.index) != 1:
        return False
    row = summary.iloc[0]
    expected = {
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }
    return bool(
        _to_bool(row.get("non_authorizing", False))
        and not _to_bool(row.get("authorizes_routing", True))
        and not _to_bool(row.get("authorizes_submission", True))
        and _to_bool(config.get("non_authorizing", False))
        and not _to_bool(config.get("authorizes_routing", True))
        and not _to_bool(config.get("authorizes_submission", True))
        and dict(manifest_extra)
        == {
            "accepted": bool(accepted),
            **expected,
        }
    )


def _csv_frame_matches(path: Path, expected: pd.DataFrame) -> bool:
    actual = _read_csv_frame(path, path.name)
    expected_roundtrip = pd.read_csv(
        StringIO(expected.to_csv(index=False)),
        keep_default_na=False,
    )
    return bool(
        list(actual.columns) == list(expected_roundtrip.columns)
        and actual.to_dict(orient="records")
        == expected_roundtrip.to_dict(orient="records")
    )


def _read_csv_frame(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, keep_default_na=False)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _verification_error_slug(error: str) -> str:
    text = str(error).strip().lower()
    prefix = "data-readiness comparison "
    if text.startswith(prefix):
        text = text[len(prefix):]
    slug = "".join(
        character if character.isalnum() else "_"
        for character in text
    )
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "semantic_verification_failed"


def _read_readiness_runs(readiness_dirs: list[str | Path], *, labels: list[str] | None) -> pd.DataFrame:
    rows = []
    for idx, raw_path in enumerate(readiness_dirs):
        path = Path(raw_path)
        root, summary_path = _readiness_report_paths(path)
        if not summary_path.exists():
            raise FileNotFoundError(f"{DATA_READINESS_SUMMARY_FILE} not found for {path}")
        summary = pd.read_csv(summary_path)
        if summary.empty:
            raise ValueError(f"data readiness summary is empty: {summary_path}")
        if len(summary.index) != 1:
            raise ValueError(
                f"data readiness summary must contain exactly one row: {summary_path}"
            )
        manifest_path = root / MANIFEST_NAME
        verification = verify_data_readiness_report(root)
        manifest_sha256 = ""
        if manifest_path.is_file():
            try:
                manifest_sha256 = file_sha256(manifest_path)
            except OSError:
                manifest_sha256 = ""
        dependencies = manifest_dependency_paths(manifest_path)
        row = summary.iloc[0]
        label = labels[idx] if labels is not None else path.stem
        reported_ready = _to_bool(row.get("ready", False))
        reported_failed_checks = _number(row, "failed_checks", fallback=0.0)
        manifest_current = bool(verification.manifest_current)
        report_verified = bool(verification.verified)
        rows.append(
            {
                "dataset": label,
                "dataset_path": str(path),
                "data_readiness_root": str(root.resolve()),
                "reported_ready": reported_ready,
                "ready": bool(reported_ready and report_verified),
                "components": _number(row, "components", fallback=0.0),
                "required_components": _number(row, "required_components", fallback=0.0),
                "provided_components": _number(row, "provided_components", fallback=0.0),
                "ready_components": _number(row, "ready_components", fallback=0.0),
                "reported_failed_checks": reported_failed_checks,
                "failed_checks": reported_failed_checks
                + (0 if report_verified else 1),
                "data_readiness_manifest_required": True,
                "data_readiness_manifest_provided": manifest_path.is_file(),
                "data_readiness_manifest_current": manifest_current,
                "data_readiness_manifest_error": (
                    "" if manifest_current else verification.error
                ),
                "data_readiness_manifest_path": str(manifest_path.resolve()),
                "data_readiness_manifest_sha256": manifest_sha256,
                "data_readiness_manifest_artifact_count": int(
                    verification.manifest_artifact_count
                ),
                "data_readiness_manifest_artifact_match_count": int(
                    verification.manifest_artifact_match_count
                ),
                "data_readiness_manifest_input_fingerprint_count": int(
                    verification.manifest_input_fingerprint_count
                ),
                "data_readiness_manifest_input_fingerprint_match_count": int(
                    verification.manifest_input_fingerprint_match_count
                ),
                "data_readiness_report_verification_required": True,
                "data_readiness_report_verified": report_verified,
                "data_readiness_report_inputs_current": bool(
                    verification.inputs_current
                ),
                "data_readiness_report_artifacts_consistent": bool(
                    verification.artifacts_consistent
                ),
                "data_readiness_report_non_authorizing": bool(
                    verification.non_authorizing
                ),
                "data_readiness_report_verification_error": str(
                    verification.error
                ),
                "data_readiness_dependency_count": int(len(dependencies)),
                "source_file_sha256": _text(
                    row,
                    "vendor_intake_source_file_sha256",
                    fallback=_text(row, "source_file_sha256"),
                ),
                "source_header_sha256": _text(
                    row,
                    "vendor_intake_source_header_sha256",
                    fallback=_text(row, "source_header_sha256"),
                ),
                "mapping_draft_sha256": _text(
                    row,
                    "vendor_intake_mapping_draft_sha256",
                    fallback=_text(row, "mapping_draft_sha256"),
                ),
                "mapping_coverage": _number(
                    row,
                    "vendor_intake_mapping_coverage",
                    fallback=_number(row, "mapping_coverage"),
                ),
                "observation_dates": _text(row, "observation_dates"),
                "market_calendar_id": _text(row, "market_calendar_id"),
                "market_calendar_sha256": _text(
                    row,
                    "market_calendar_sha256",
                ),
                "market_calendar_valid_from": _text(
                    row,
                    "market_calendar_valid_from",
                ),
                "market_calendar_valid_to": _text(
                    row,
                    "market_calendar_valid_to",
                ),
                "recommendation": str(row.get("recommendation", "")),
            }
        )
    return pd.DataFrame(rows)


def _readiness_report_paths(path: Path) -> tuple[Path, Path]:
    if path.is_file() or path.suffix.lower() == ".csv":
        return path.parent, path
    return path, path / DATA_READINESS_SUMMARY_FILE


def _comparison_manifest_inputs(
    readiness_dirs: list[str | Path],
) -> dict[str, object]:
    manifest_paths: dict[str, Path] = {}
    dependency_paths: dict[str, Path] = {}
    for raw_path in readiness_dirs:
        root, _ = _readiness_report_paths(Path(raw_path))
        manifest_path = (root / MANIFEST_NAME).resolve()
        if not manifest_path.is_file():
            continue
        manifest_paths[str(manifest_path)] = manifest_path
        for dependency in manifest_dependency_paths(manifest_path):
            resolved = dependency.resolve()
            dependency_paths[str(resolved)] = resolved

    inputs: dict[str, object] = {"readiness": readiness_dirs}
    if manifest_paths:
        inputs["readiness_manifests"] = [
            manifest_paths[key] for key in sorted(manifest_paths)
        ]
    if dependency_paths:
        inputs["readiness_dependencies"] = [
            dependency_paths[key] for key in sorted(dependency_paths)
        ]
    return inputs


def _summary(runs: pd.DataFrame) -> pd.DataFrame:
    dataset_count = int(len(runs))
    ready_datasets = int(runs["ready"].sum()) if dataset_count else 0
    failed_datasets = dataset_count - ready_datasets
    observation_dates = _joined_observation_dates(runs)
    unique_observation_dates = (
        len(observation_dates.split(";")) if observation_dates else 0
    )
    observation_date_memberships = int(
        pd.to_numeric(
            runs.get(
                "observation_date_count",
                pd.Series(dtype=float),
            ),
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )
    lineage_required = bool(
        runs["data_readiness_manifest_required"].any()
        if "data_readiness_manifest_required" in runs.columns
        else False
    )
    manifest_provided = int(
        runs["data_readiness_manifest_provided"].sum()
        if "data_readiness_manifest_provided" in runs.columns
        else 0
    )
    current_manifests = int(
        runs["data_readiness_manifest_current"].sum()
        if "data_readiness_manifest_current" in runs.columns
        else 0
    )
    verification_required = bool(
        runs["data_readiness_report_verification_required"].any()
        if "data_readiness_report_verification_required" in runs.columns
        else False
    )
    verified_reports = int(
        runs["data_readiness_report_verified"].sum()
        if "data_readiness_report_verified" in runs.columns
        else 0
    )
    return pd.DataFrame(
        [
            {
                "dataset_count": dataset_count,
                "ready_datasets": ready_datasets,
                "failed_datasets": failed_datasets,
                "data_readiness_manifest_required": lineage_required,
                "data_readiness_manifests_provided": manifest_provided,
                "current_data_readiness_manifests": current_manifests,
                "data_readiness_manifest_coverage": (
                    current_manifests / dataset_count
                    if lineage_required and dataset_count
                    else np.nan
                ),
                "data_readiness_manifest_errors": _joined_text_values(
                    runs,
                    "data_readiness_manifest_error",
                ),
                "data_readiness_report_verification_required": (
                    verification_required
                ),
                "verified_data_readiness_reports": verified_reports,
                "data_readiness_report_verification_coverage": (
                    verified_reports / dataset_count
                    if verification_required and dataset_count
                    else np.nan
                ),
                "data_readiness_report_verification_errors": (
                    _joined_text_values(
                        runs,
                        "data_readiness_report_verification_error",
                    )
                ),
                "data_readiness_dependency_count": int(
                    pd.to_numeric(
                        runs.get(
                            "data_readiness_dependency_count",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).sum(skipna=True)
                ),
                "ready_rate": ready_datasets / dataset_count if dataset_count else 0.0,
                "total_failed_checks": int(pd.to_numeric(runs["failed_checks"], errors="coerce").sum(skipna=True)),
                "unique_source_files": _unique_text_count(runs, "source_file_sha256"),
                "source_file_fingerprint_coverage": _text_coverage(runs, "source_file_sha256"),
                "observation_dates": observation_dates,
                "unique_observation_dates": unique_observation_dates,
                "observation_date_coverage": _positive_number_coverage(
                    runs,
                    "observation_date_count",
                ),
                "observation_date_parse_error_count": int(
                    pd.to_numeric(
                        runs.get(
                            "observation_date_parse_error_count",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                ),
                "overlapping_observation_date_memberships": max(
                    observation_date_memberships
                    - unique_observation_dates,
                    0,
                ),
                "unique_header_fingerprints": _unique_text_count(runs, "source_header_sha256"),
                "unique_mapping_drafts": _unique_text_count(runs, "mapping_draft_sha256"),
                "min_mapping_coverage": _min_number(runs, "mapping_coverage"),
                "market_calendar_coverage": _market_calendar_coverage(runs),
                "unique_market_calendar_ids": _unique_text_count(
                    runs,
                    "market_calendar_id",
                ),
                "unique_market_calendar_fingerprints": _unique_text_count(
                    runs,
                    "market_calendar_sha256",
                ),
                "market_calendar_ids": _joined_text_values(
                    runs,
                    "market_calendar_id",
                ),
                "market_calendar_fingerprints": _joined_text_values(
                    runs,
                    "market_calendar_sha256",
                ),
                "median_ready_components": float(pd.to_numeric(runs["ready_components"], errors="coerce").median(skipna=True))
                if dataset_count
                else np.nan,
                "min_ready_components": float(pd.to_numeric(runs["ready_components"], errors="coerce").min(skipna=True))
                if dataset_count
                else np.nan,
                "recommendation": "",
            }
        ]
    )


def _checks(row: pd.Series, thresholds: DataReadinessComparisonThresholds) -> pd.DataFrame:
    min_ready = thresholds.min_ready_datasets if thresholds.min_ready_datasets is not None else thresholds.min_datasets
    checks = [
        _threshold_check("dataset_count", row["dataset_count"], ">=", thresholds.min_datasets),
        _threshold_check("ready_datasets", row["ready_datasets"], ">=", min_ready),
        _threshold_check("ready_rate", row["ready_rate"], ">=", thresholds.min_ready_rate),
        _threshold_check(
            "total_failed_checks",
            row["total_failed_checks"],
            "<=",
            thresholds.max_total_failed_checks,
        ),
    ]
    if _to_bool(row.get("data_readiness_manifest_required", False)):
        checks.insert(
            1,
            _threshold_check(
                "data_readiness_manifest_coverage",
                row["data_readiness_manifest_coverage"],
                ">=",
                1.0,
            ),
        )
    if _to_bool(
        row.get("data_readiness_report_verification_required", False)
    ):
        checks.insert(
            2,
            _threshold_check(
                "data_readiness_report_verification_coverage",
                row["data_readiness_report_verification_coverage"],
                ">=",
                1.0,
            ),
        )
    if thresholds.min_unique_source_files is not None:
        checks.append(
            _threshold_check(
                "unique_source_files",
                row["unique_source_files"],
                ">=",
                thresholds.min_unique_source_files,
            )
        )
    if thresholds.min_unique_observation_dates is not None:
        checks.extend(
            [
                _threshold_check(
                    "observation_date_coverage",
                    row["observation_date_coverage"],
                    ">=",
                    1.0,
                ),
                _threshold_check(
                    "observation_date_parse_error_count",
                    row["observation_date_parse_error_count"],
                    "<=",
                    0,
                ),
                _threshold_check(
                    "unique_observation_dates",
                    row["unique_observation_dates"],
                    ">=",
                    thresholds.min_unique_observation_dates,
                ),
            ]
        )
    if thresholds.min_source_file_fingerprint_coverage is not None:
        checks.append(
            _threshold_check(
                "source_file_fingerprint_coverage",
                row["source_file_fingerprint_coverage"],
                ">=",
                thresholds.min_source_file_fingerprint_coverage,
            )
        )
    if thresholds.min_mapping_coverage is not None:
        checks.append(
            _threshold_check(
                "min_mapping_coverage",
                row["min_mapping_coverage"],
                ">=",
                thresholds.min_mapping_coverage,
            )
        )
    if thresholds.require_market_calendar or thresholds.require_consistent_market_calendar:
        checks.append(
            _threshold_check(
                "market_calendar_coverage",
                row["market_calendar_coverage"],
                ">=",
                1.0,
            )
        )
    if thresholds.require_consistent_market_calendar:
        checks.extend(
            [
                _threshold_check(
                    "unique_market_calendar_ids",
                    row["unique_market_calendar_ids"],
                    "<=",
                    1,
                ),
                _threshold_check(
                    "unique_market_calendar_fingerprints",
                    row["unique_market_calendar_fingerprints"],
                    "<=",
                    1,
                ),
            ]
        )
    return pd.DataFrame(checks)


def _config(
    summary_row: pd.Series,
    dataset_runs: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    thresholds: DataReadinessComparisonThresholds,
) -> dict[str, object]:
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    failed_checks = (
        checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
        if not checks.empty and "passed" in checks.columns
        else []
    )
    return {
        "schema_version": 1,
        "accepted": _to_bool(summary_row.get("accepted", False)),
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "recommendation": _value_text(summary_row.get("recommendation")),
        "thresholds": asdict(thresholds),
        "summary": _jsonable_record(summary_row.to_dict()),
        "dataset_count": int(_value_number(summary_row.get("dataset_count"))),
        "ready_datasets": int(_value_number(summary_row.get("ready_datasets"))),
        "failed_datasets": int(_value_number(summary_row.get("failed_datasets"))),
        "data_readiness_lineage": {
            "manifest_required": _to_bool(
                summary_row.get("data_readiness_manifest_required", False)
            ),
            "manifests_provided": int(
                _value_number(
                    summary_row.get("data_readiness_manifests_provided")
                )
            ),
            "current_manifests": int(
                _value_number(
                    summary_row.get("current_data_readiness_manifests")
                )
            ),
            "manifest_coverage": float(
                _value_number(
                    summary_row.get("data_readiness_manifest_coverage")
                )
            ),
            "manifest_errors": (
                _value_text(
                    summary_row.get("data_readiness_manifest_errors")
                ).split(";")
                if _value_text(
                    summary_row.get("data_readiness_manifest_errors")
                )
                else []
            ),
            "report_verification_required": _to_bool(
                summary_row.get(
                    "data_readiness_report_verification_required",
                    False,
                )
            ),
            "verified_reports": int(
                _value_number(
                    summary_row.get("verified_data_readiness_reports")
                )
            ),
            "report_verification_coverage": float(
                _value_number(
                    summary_row.get(
                        "data_readiness_report_verification_coverage"
                    )
                )
            ),
            "report_verification_errors": (
                _value_text(
                    summary_row.get(
                        "data_readiness_report_verification_errors"
                    )
                ).split(";")
                if _value_text(
                    summary_row.get(
                        "data_readiness_report_verification_errors"
                    )
                )
                else []
            ),
            "dependency_count": int(
                _value_number(
                    summary_row.get("data_readiness_dependency_count")
                )
            ),
        },
        "market_calendar": {
            "required": bool(thresholds.require_market_calendar),
            "consistent_required": bool(
                thresholds.require_consistent_market_calendar
            ),
            "coverage": float(
                _value_number(summary_row.get("market_calendar_coverage"))
            ),
            "ids": _value_text(summary_row.get("market_calendar_ids")).split(";")
            if _value_text(summary_row.get("market_calendar_ids"))
            else [],
            "fingerprints": _value_text(
                summary_row.get("market_calendar_fingerprints")
            ).split(";")
            if _value_text(summary_row.get("market_calendar_fingerprints"))
            else [],
        },
        "failed_checks": failed_checks,
        "datasets": _records(dataset_runs),
        "ready_action_count": int(len(ready_actions)),
        "blocked_action_count": int(len(blocked_actions)),
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _value_text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _records(action_queue),
        "ready_actions": _records(ready_actions),
        "blocked_actions": _records(blocked_actions),
    }


def _first_action_record(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return _jsonable_record(frame.iloc[0].to_dict())


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [_jsonable_record(row) for row in frame.to_dict(orient="records")]


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Path):
            record[str(key)] = str(value)
            continue
        try:
            if pd.isna(value):
                record[str(key)] = None
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(value, np.generic):
            record[str(key)] = value.item()
            continue
        record[str(key)] = value
    return record


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _value_text(action_queue.iloc[0].get(column))


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not checks.empty and "passed" in checks.columns:
        failed = checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)
        for priority, row in enumerate(failed.to_dict(orient="records"), start=1):
            check_name = _value_text(row.get("check"))
            next_gate = _next_gate_for_check(check_name)
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "blocked",
                    "check": check_name,
                    "next_gate": next_gate,
                    "next_gate_help_command": _next_gate_help_command(next_gate),
                    "actual": _value_text(row.get("value")),
                    "operator": _value_text(row.get("operator")),
                    "expected": _value_text(row.get("threshold")),
                    "reason": _value_text(row.get("reason")),
                    "recommendation": _action_recommendation(check_name),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "check",
            "next_gate",
            "next_gate_help_command",
            "actual",
            "operator",
            "expected",
            "reason",
            "recommendation",
        ],
    )


def _next_gate_for_check(check_name: str) -> str:
    if check_name in {
        "dataset_count",
        "unique_source_files",
        "observation_date_coverage",
        "observation_date_parse_error_count",
        "unique_observation_dates",
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
    }:
        return "pipeline-vendor-market-data-batch"
    if check_name in {
        "market_calendar_coverage",
        "unique_market_calendar_ids",
        "unique_market_calendar_fingerprints",
    }:
        return "market-calendar-report"
    if check_name in {
        "data_readiness_manifest_coverage",
        "data_readiness_report_verification_coverage",
        "ready_datasets",
        "ready_rate",
        "total_failed_checks",
    }:
        return "review-data-readiness"
    return "compare-data-readiness"


def _next_gate_help_command(next_gate: str) -> str:
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _primary_next_gate(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return ""
    return _value_text(action_queue.iloc[0].get("next_gate"))


def _action_recommendation(check_name: str) -> str:
    if check_name == "dataset_count":
        return "collect_additional_vendor_data_days"
    if check_name == "data_readiness_manifest_coverage":
        return "regenerate_current_manifest_bound_data_readiness"
    if check_name == "data_readiness_report_verification_coverage":
        return "regenerate_semantically_verified_data_readiness"
    if check_name in {"ready_datasets", "ready_rate", "total_failed_checks"}:
        return "fix_failed_data_readiness_runs"
    if check_name == "unique_source_files":
        return "rerun_batch_with_distinct_raw_source_files"
    if check_name == "observation_date_coverage":
        return "regenerate_readiness_with_local_observation_dates"
    if check_name == "observation_date_parse_error_count":
        return "regenerate_canonical_local_observation_dates"
    if check_name == "unique_observation_dates":
        return "collect_additional_vendor_data_days"
    if check_name == "source_file_fingerprint_coverage":
        return "rerun_batch_with_source_file_fingerprints"
    if check_name == "min_mapping_coverage":
        return "improve_vendor_mapping_coverage"
    if check_name == "market_calendar_coverage":
        return "bind_every_dataset_to_a_validated_market_calendar"
    if check_name in {
        "unique_market_calendar_ids",
        "unique_market_calendar_fingerprints",
    }:
        return "rerun_with_one_market_calendar_source"
    return "review_data_readiness_comparison_gap"


def _runbook_markdown(
    summary_row: pd.Series,
    dataset_runs: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    accepted_label = "yes" if _to_bool(summary_row.get("accepted", False)) else "no"
    lines = [
        "# Data Readiness Comparison Runbook",
        "",
        f"- Accepted: {accepted_label}",
        "- Non-authorizing: yes",
        "- Authorizes routing: no",
        "- Authorizes submission: no",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Dataset count: {int(_value_number(summary_row.get('dataset_count')))}",
        f"- Ready datasets: {int(_value_number(summary_row.get('ready_datasets')))}",
        f"- Failed datasets: {int(_value_number(summary_row.get('failed_datasets')))}",
        f"- Current readiness-manifest coverage: {_format_number(summary_row.get('data_readiness_manifest_coverage'))}",
        f"- Readiness-manifest errors: {_value_text(summary_row.get('data_readiness_manifest_errors'))}",
        f"- Semantic readiness-report coverage: {_format_number(summary_row.get('data_readiness_report_verification_coverage'))}",
        f"- Semantic readiness-report errors: {_value_text(summary_row.get('data_readiness_report_verification_errors'))}",
        f"- Bound readiness dependencies: {int(_value_number(summary_row.get('data_readiness_dependency_count')))}",
        f"- Local observation dates: {_value_text(summary_row.get('observation_dates'))}",
        f"- Unique local observation dates: {int(_value_number(summary_row.get('unique_observation_dates')))}",
        f"- Observation-date coverage: {_format_number(summary_row.get('observation_date_coverage'))}",
        f"- Overlapping date memberships: {int(_value_number(summary_row.get('overlapping_observation_date_memberships')))}",
        f"- Market-calendar coverage: {_format_number(summary_row.get('market_calendar_coverage'))}",
        f"- Market-calendar IDs: {_value_text(summary_row.get('market_calendar_ids'))}",
        f"- Market-calendar fingerprints: {_value_text(summary_row.get('market_calendar_fingerprints'))}",
        f"- Blocked actions: {int(_value_number(summary_row.get('blocked_action_count')))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
        "## Datasets",
        "",
        _dataset_table(dataset_runs),
        "",
        "## Failed Checks",
        "",
        _failed_checks_table(checks),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Check", "Next gate", "Help", "Recommendation"],
        [
            [
                str(int(_value_number(row.get("priority")))),
                _value_text(row.get("check")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _value_text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _dataset_table(dataset_runs: pd.DataFrame) -> str:
    if dataset_runs.empty:
        return "_None_"
    return _markdown_table(
        [
            "Dataset",
            "Reported ready",
            "Ready",
            "Manifest current",
            "Semantically verified",
            "Manifest error",
            "Failed checks",
            "Observation dates",
            "Source hash",
            "Calendar ID",
            "Calendar hash",
            "Mapping coverage",
            "Recommendation",
        ],
        [
            [
                _value_text(row.get("dataset")),
                "yes" if _to_bool(row.get("reported_ready")) else "no",
                "yes" if _to_bool(row.get("ready")) else "no",
                "yes"
                if _to_bool(row.get("data_readiness_manifest_current"))
                else "no",
                "yes"
                if _to_bool(row.get("data_readiness_report_verified"))
                else "no",
                _value_text(row.get("data_readiness_manifest_error")),
                str(int(_value_number(row.get("failed_checks")))),
                _value_text(row.get("observation_dates")),
                _value_text(row.get("source_file_sha256")),
                _value_text(row.get("market_calendar_id")),
                _value_text(row.get("market_calendar_sha256")),
                _format_number(row.get("mapping_coverage")),
                _value_text(row.get("recommendation")),
            ]
            for row in dataset_runs.to_dict(orient="records")
        ],
    )


def _failed_checks_table(checks: pd.DataFrame) -> str:
    if checks.empty or "passed" not in checks.columns:
        return "_None_"
    failed = checks.loc[~checks["passed"].astype(bool)]
    if failed.empty:
        return "_None_"
    return _markdown_table(
        ["Check", "Actual", "Op", "Expected", "Reason"],
        [
            [
                _value_text(row.get("check")),
                _value_text(row.get("value")),
                _value_text(row.get("operator")),
                _value_text(row.get("threshold")),
                _value_text(row.get("reason")),
            ]
            for row in failed.to_dict(orient="records")
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _code(value: object) -> str:
    text = _value_text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: object) -> str:
    return _value_text(value).replace("|", "\\|").replace("\n", " ")


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float) or np.isnan(threshold_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} or threshold is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_thresholds(thresholds: DataReadinessComparisonThresholds) -> None:
    if thresholds.min_datasets <= 0:
        raise ValueError("min_datasets must be positive")
    if thresholds.min_ready_datasets is not None and thresholds.min_ready_datasets <= 0:
        raise ValueError("min_ready_datasets must be positive")
    if not 0 <= thresholds.min_ready_rate <= 1:
        raise ValueError("min_ready_rate must be between 0 and 1")
    if thresholds.max_total_failed_checks < 0:
        raise ValueError("max_total_failed_checks must be non-negative")
    if thresholds.min_unique_source_files is not None and thresholds.min_unique_source_files <= 0:
        raise ValueError("min_unique_source_files must be positive")
    if (
        thresholds.min_unique_observation_dates is not None
        and thresholds.min_unique_observation_dates <= 0
    ):
        raise ValueError("min_unique_observation_dates must be positive")
    if (
        thresholds.min_source_file_fingerprint_coverage is not None
        and not 0 <= thresholds.min_source_file_fingerprint_coverage <= 1
    ):
        raise ValueError("min_source_file_fingerprint_coverage must be between 0 and 1")
    if thresholds.min_mapping_coverage is not None and not 0 <= thresholds.min_mapping_coverage <= 1:
        raise ValueError("min_mapping_coverage must be between 0 and 1")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _coalesce_column(frame: pd.DataFrame, column: str, fallback_column: str, *, default: object) -> None:
    if column not in frame.columns:
        frame[column] = frame[fallback_column] if fallback_column in frame.columns else default
        return
    if fallback_column not in frame.columns:
        return
    current = frame[column]
    if pd.api.types.is_numeric_dtype(current):
        missing = current.isna()
    else:
        missing = current.isna() | (current.astype(str).str.strip() == "")
    frame.loc[missing, column] = frame.loc[missing, fallback_column]


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _text(row: pd.Series, column: str, fallback: str = "") -> str:
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return str(value).strip()


def _value_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _value_number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    try:
        if pd.isna(number):
            return 0.0
    except (TypeError, ValueError):
        pass
    return number


def _format_number(value: object) -> str:
    text = _value_text(value)
    if not text:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return text
    if pd.isna(number):
        return ""
    return f"{number:.6g}"


def _unique_text_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return int(values.nunique())


def _joined_text_values(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return ";".join(sorted(set(values)))


def _text_coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = frame[column].fillna("").astype(str).str.strip()
    return float((values != "").sum() / len(values)) if len(values) else 0.0


def _positive_number_coverage(
    frame: pd.DataFrame,
    column: str,
) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return float(values.gt(0).mean())


def _normalize_observation_dates(value: object) -> tuple[str, int, int]:
    if value is None:
        return "", 0, 0
    try:
        if pd.isna(value):
            return "", 0, 0
    except (TypeError, ValueError):
        pass
    dates: set[str] = set()
    parse_errors = 0
    for raw_part in str(value).split(";"):
        part = raw_part.strip()
        if not part:
            continue
        try:
            parsed = date.fromisoformat(part)
        except ValueError:
            parse_errors += 1
            continue
        if parsed.isoformat() != part:
            parse_errors += 1
            continue
        dates.add(part)
    normalized = ";".join(sorted(dates))
    return normalized, len(dates), parse_errors


def _joined_observation_dates(frame: pd.DataFrame) -> str:
    if frame.empty or "observation_dates" not in frame.columns:
        return ""
    dates: set[str] = set()
    for value in frame["observation_dates"].tolist():
        normalized, _, _ = _normalize_observation_dates(value)
        dates.update(normalized.split(";") if normalized else [])
    return ";".join(sorted(dates))


def _market_calendar_coverage(frame: pd.DataFrame) -> float:
    columns = (
        "market_calendar_id",
        "market_calendar_sha256",
        "market_calendar_valid_from",
        "market_calendar_valid_to",
    )
    if frame.empty or any(column not in frame.columns for column in columns):
        return 0.0
    present = pd.Series(True, index=frame.index, dtype=bool)
    for column in columns:
        values = frame[column].fillna("").astype(str).str.strip()
        present &= values != ""
    return float(present.sum() / len(frame)) if len(frame) else 0.0


def _min_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.min(skipna=True)) if values.notna().any() else np.nan


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed", "accepted"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)
