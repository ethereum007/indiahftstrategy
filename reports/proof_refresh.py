from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import (
    MANIFEST_NAME,
    ManifestIntegrity,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.proof import ProofReportVerification, verify_proof_report


PROOF_REFRESH_RUN_TYPE = "proof_refresh_gate"
PROOF_REFRESH_DECISION_FILE = "proof_refresh_decision.csv"
PROOF_REFRESH_CHECKS_FILE = "proof_refresh_checks.csv"
PROOF_REFRESH_SUMMARY_FILE = "proof_refresh_summary.csv"
PROOF_REFRESH_ACTION_QUEUE_FILE = "proof_refresh_action_queue.csv"
PROOF_REFRESH_CONFIG_FILE = "proof_refresh_config.json"
PROOF_REFRESH_RUNBOOK_FILE = "proof_refresh_runbook.md"
PROOF_REFRESH_REQUIRED_ARTIFACTS = (
    PROOF_REFRESH_DECISION_FILE,
    PROOF_REFRESH_CHECKS_FILE,
    PROOF_REFRESH_SUMMARY_FILE,
    PROOF_REFRESH_ACTION_QUEUE_FILE,
    PROOF_REFRESH_CONFIG_FILE,
    PROOF_REFRESH_RUNBOOK_FILE,
)
PROOF_REFRESH_REQUIRED_SUMMARY_COLUMNS = (
    "ready",
    "proof_source",
    "fresh_proof_required",
    "strategy",
    "market",
    "mixed_identity",
    "failed_checks",
    "recommendation",
)


@dataclass(frozen=True)
class ProofRefreshThresholds:
    require_calibrated_replay_when_drift_fails: bool = False
    expected_strategy: str | None = None
    expected_market: str | None = None


@dataclass(frozen=True)
class ProofRefreshReport:
    decision: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    config: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


@dataclass(frozen=True)
class ProofRefreshReportVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    inputs_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    baseline_proof_verified: bool
    latest_proof_provided: bool
    latest_proof_verified: bool
    output_dir: Path
    manifest_path: Path
    manifest_artifact_count: int = 0
    manifest_artifact_match_count: int = 0
    manifest_input_fingerprint_count: int = 0
    manifest_input_fingerprint_match_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class ProofRefreshEvidence:
    summary: pd.DataFrame
    requested_path: Path | None = None
    root: Path | None = None
    summary_path: Path | None = None
    manifest_path: Path | None = None
    manifest_integrity: ManifestIntegrity | None = None
    verification: ProofRefreshReportVerification | None = None
    read_error: str = ""

    @property
    def requested(self) -> bool:
        return self.requested_path is not None

    @property
    def provided(self) -> bool:
        return not self.summary.empty

    @property
    def reported_ready(self) -> bool:
        return bool(
            self.provided
            and _value_bool(
                self.summary.iloc[0].get("ready", False)
            )
        )

    @property
    def manifest_current(self) -> bool:
        return bool(
            self.manifest_integrity is not None
            and self.manifest_integrity.passed
        )

    @property
    def semantically_verified(self) -> bool:
        return bool(
            self.verification is not None
            and self.verification.verified
        )

    @property
    def verified(self) -> bool:
        return bool(
            not self.read_error
            and self.provided
            and self.manifest_current
            and self.semantically_verified
        )

    @property
    def ready(self) -> bool:
        return bool(self.verified and self.reported_ready)

    @property
    def reason(self) -> str:
        if not self.requested:
            return "proof_refresh_missing"
        if self.read_error:
            return f"proof_refresh_{self.read_error}"
        if not self.manifest_current:
            error = (
                self.manifest_integrity.error
                if self.manifest_integrity is not None
                and self.manifest_integrity.error
                else "invalid"
            )
            suffix = (
                error
                if error.startswith("manifest_")
                else f"manifest_{error}"
            )
            return f"proof_refresh_{suffix}"
        if not self.semantically_verified:
            error = (
                self.verification.error
                if self.verification is not None
                else ""
            )
            return (
                "proof_refresh_"
                + _proof_refresh_verification_error_slug(error)
            )
        if not self.reported_ready:
            return "proof_refresh_not_ready"
        return "ready"

    @property
    def recommendation(self) -> str:
        if not self.verified:
            return self.reason
        value = str(
            self.summary.iloc[0].get("recommendation", "")
        ).strip()
        return value or self.reason


def evaluate_proof_refresh(
    *,
    drift_summary: pd.DataFrame,
    baseline_proof_summary: pd.DataFrame,
    latest_proof_summary: pd.DataFrame | None = None,
    calibrated_replay_summary: pd.DataFrame | None = None,
    thresholds: ProofRefreshThresholds | None = None,
    baseline_proof_verification: ProofReportVerification | None = None,
    latest_proof_verification: ProofReportVerification | None = None,
) -> ProofRefreshReport:
    thresholds = thresholds or ProofRefreshThresholds()
    drift_passed = _frame_bool(drift_summary, "passed")
    baseline_reported_passed = _frame_bool(
        baseline_proof_summary,
        "all_passed",
    )
    baseline_verification_enforced = baseline_proof_verification is not None
    baseline_verified = bool(
        baseline_proof_verification is not None
        and baseline_proof_verification.verified
    )
    baseline_passed = bool(
        baseline_reported_passed
        and (
            baseline_verified
            if baseline_verification_enforced
            else True
        )
    )
    latest_available = latest_proof_summary is not None and not latest_proof_summary.empty
    latest_reported_passed = (
        _frame_bool(latest_proof_summary, "all_passed")
        if latest_available
        else False
    )
    latest_verification_enforced = bool(
        latest_available and latest_proof_verification is not None
    )
    latest_verified = bool(
        latest_proof_verification is not None
        and latest_proof_verification.verified
    )
    latest_passed = bool(
        latest_reported_passed
        and (
            latest_verified
            if latest_verification_enforced
            else True
        )
    )
    calibrated_available = calibrated_replay_summary is not None and not calibrated_replay_summary.empty
    calibrated_ready = _frame_bool(calibrated_replay_summary, "ready") if calibrated_available else False
    calibrated_strategy = _frame_str(calibrated_replay_summary, "strategy") if calibrated_available else ""
    identities = _input_identities(
        baseline_proof_summary=baseline_proof_summary,
        latest_proof_summary=latest_proof_summary if latest_available else None,
        calibrated_replay_summary=calibrated_replay_summary if calibrated_available else None,
    )
    strategies = _identity_values(identities, "strategy", normalizer=_strategy_key)
    markets = _identity_values(identities, "market", normalizer=_identity_key)
    mixed_identity = bool((len(strategies) > 1) or (len(markets) > 1))

    checks = _checks(
        drift_passed=drift_passed,
        baseline_reported_passed=baseline_reported_passed,
        baseline_verification_enforced=baseline_verification_enforced,
        baseline_verified=baseline_verified,
        latest_available=latest_available,
        latest_reported_passed=latest_reported_passed,
        latest_verification_enforced=latest_verification_enforced,
        latest_verified=latest_verified,
        calibrated_available=calibrated_available,
        calibrated_ready=calibrated_ready,
        calibrated_strategy=calibrated_strategy,
        identities=identities,
        thresholds=thresholds,
    )
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed_checks == 0
    proof_source = _proof_source(drift_passed, baseline_passed, latest_passed, ready)
    recommendation = _recommendation(ready, drift_passed)
    decision = pd.DataFrame(
        [
            {
                "action": recommendation,
                "proof_source": proof_source,
                "strategy": _single_identity(strategies),
                "market": _single_identity(markets),
                "mixed_identity": mixed_identity,
                "fresh_proof_required": not drift_passed,
                "reason": _reason(ready, drift_passed, latest_available, latest_passed, calibrated_ready),
            }
        ]
    )
    summary = pd.DataFrame(
        [
            {
                "ready": ready,
                "drift_passed": drift_passed,
                "fresh_proof_required": not drift_passed,
                "proof_source": proof_source,
                "baseline_proof_reported_passed": baseline_reported_passed,
                "baseline_proof_passed": baseline_passed,
                "latest_proof_available": latest_available,
                "latest_proof_reported_passed": latest_reported_passed,
                "latest_proof_passed": latest_passed,
                "calibrated_replay_required": (not drift_passed)
                and thresholds.require_calibrated_replay_when_drift_fails,
                "calibrated_replay_available": calibrated_available,
                "calibrated_replay_ready": calibrated_ready,
                "strategy": _single_identity(strategies),
                "strategy_count": int(len(strategies)),
                "missing_strategy_sources": _missing_identity_count(identities, "strategy"),
                "expected_strategy": _strategy_key(thresholds.expected_strategy)
                if thresholds.expected_strategy is not None
                else "",
                "market": _single_identity(markets),
                "market_count": int(len(markets)),
                "missing_market_sources": _missing_identity_count(identities, "market"),
                "expected_market": _identity_key(thresholds.expected_market)
                if thresholds.expected_market is not None
                else "",
                "mixed_identity": mixed_identity,
                "failed_checks": failed_checks,
                "recommendation": recommendation,
                "non_authorizing": True,
                "authorizes_routing": False,
                "authorizes_submission": False,
                **_proof_verification_summary_fields(
                    "baseline_proof",
                    baseline_proof_verification,
                ),
                **_proof_verification_summary_fields(
                    "latest_proof",
                    latest_proof_verification,
                ),
            }
        ]
    )
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(decision.iloc[0], summary.iloc[0], thresholds, action_queue)
    return ProofRefreshReport(
        decision=decision,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config,
    )


def write_proof_refresh_report(
    *,
    drift_path: str | Path,
    baseline_proof_path: str | Path,
    output_dir: str | Path,
    latest_proof_path: str | Path | None = None,
    calibrated_replay_path: str | Path | None = None,
    thresholds: ProofRefreshThresholds | None = None,
) -> ProofRefreshReport:
    thresholds = thresholds or ProofRefreshThresholds()
    drift_file = _summary_path(drift_path, "fill_model_drift_summary.csv")
    baseline_file = _summary_path(baseline_proof_path, "proof_summary.csv")
    latest_file = _optional_summary_path(latest_proof_path, "proof_summary.csv")
    calibrated_file = _optional_summary_path(calibrated_replay_path, "calibrated_replay_summary.csv")
    baseline_verification = verify_proof_report(baseline_file.parent)
    latest_verification = (
        verify_proof_report(latest_file.parent)
        if latest_file is not None
        else None
    )
    report = evaluate_proof_refresh(
        drift_summary=_read_summary(drift_file),
        baseline_proof_summary=_read_summary(baseline_file),
        latest_proof_summary=_read_summary(latest_file) if latest_file is not None else None,
        calibrated_replay_summary=_read_summary(calibrated_file) if calibrated_file is not None else None,
        thresholds=thresholds,
        baseline_proof_verification=baseline_verification,
        latest_proof_verification=latest_verification,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.decision.to_csv(out / PROOF_REFRESH_DECISION_FILE, index=False)
    report.checks.to_csv(out / PROOF_REFRESH_CHECKS_FILE, index=False)
    report.summary.to_csv(out / PROOF_REFRESH_SUMMARY_FILE, index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / PROOF_REFRESH_ACTION_QUEUE_FILE, index=False)
    config_payload = report.config or _config(
        report.decision.iloc[0],
        report.summary.iloc[0],
        thresholds,
        action_queue,
    )
    (out / PROOF_REFRESH_CONFIG_FILE).write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / PROOF_REFRESH_RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=PROOF_REFRESH_RUN_TYPE,
        parameters={"thresholds": asdict(thresholds)},
        inputs=_proof_refresh_manifest_inputs(
            drift_file=drift_file,
            baseline_proof_dir=baseline_file.parent,
            latest_proof_dir=(
                latest_file.parent
                if latest_file is not None
                else None
            ),
            calibrated_file=calibrated_file,
        ),
        extra=_proof_refresh_manifest_extra(report),
    )
    return ProofRefreshReport(
        report.decision,
        report.checks,
        report.summary,
        out,
        action_queue,
        config_payload,
    )


def verify_proof_refresh_report(
    report_dir: str | Path,
) -> ProofRefreshReportVerification:
    requested = Path(report_dir)
    root = requested.parent if requested.is_file() else requested
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=PROOF_REFRESH_RUN_TYPE,
        required_artifacts=PROOF_REFRESH_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    inputs_current = False
    artifacts_consistent = False
    non_authorizing = False
    baseline_proof_verified = False
    latest_proof_provided = False
    latest_proof_verified = False
    try:
        manifest = _read_json_object(
            manifest_path,
            "proof-refresh manifest",
        )
        parameters = _mapping(manifest.get("parameters"))
        thresholds = _proof_refresh_thresholds_from_manifest(parameters)
        inputs = _mapping(manifest.get("inputs"))
        (
            drift_file,
            baseline_proof_dir,
            latest_proof_dir,
            calibrated_file,
        ) = _proof_refresh_primary_inputs_from_manifest(inputs)
        baseline_file = _summary_path(
            baseline_proof_dir,
            "proof_summary.csv",
        )
        latest_file = (
            _summary_path(latest_proof_dir, "proof_summary.csv")
            if latest_proof_dir is not None
            else None
        )
        baseline_verification = verify_proof_report(
            baseline_proof_dir
        )
        latest_verification = (
            verify_proof_report(latest_proof_dir)
            if latest_proof_dir is not None
            else None
        )
        baseline_proof_verified = baseline_verification.verified
        latest_proof_provided = latest_proof_dir is not None
        latest_proof_verified = bool(
            latest_verification is not None
            and latest_verification.verified
        )
        expected_report = evaluate_proof_refresh(
            drift_summary=_read_summary(drift_file),
            baseline_proof_summary=_read_summary(baseline_file),
            latest_proof_summary=(
                _read_summary(latest_file)
                if latest_file is not None
                else None
            ),
            calibrated_replay_summary=(
                _read_summary(calibrated_file)
                if calibrated_file is not None
                else None
            ),
            thresholds=thresholds,
            baseline_proof_verification=baseline_verification,
            latest_proof_verification=latest_verification,
        )
        expected_parameters = {
            "thresholds": asdict(thresholds),
        }
        expected_extra = _proof_refresh_manifest_extra(
            expected_report
        )
        inputs_current = bool(
            _proof_refresh_input_contract_current(
                inputs,
                drift_file=drift_file,
                baseline_proof_dir=baseline_proof_dir,
                latest_proof_dir=latest_proof_dir,
                calibrated_file=calibrated_file,
            )
            and integrity.input_fingerprint_count
            == integrity.input_fingerprint_match_count
            and integrity.input_fingerprint_count > 0
        )
        artifacts_consistent = bool(
            _proof_refresh_artifacts_consistent(
                root,
                expected_report,
                thresholds,
                manifest,
            )
            and dict(parameters) == expected_parameters
            and _mapping(manifest.get("extra")) == expected_extra
        )
        non_authorizing = _proof_refresh_authority_consistent(
            root,
            _mapping(manifest.get("extra")),
            expected_report,
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
        return ProofRefreshReportVerification(
            verified=verified,
            ready=bool(verified and expected_report.ready),
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            baseline_proof_verified=baseline_proof_verified,
            latest_proof_provided=latest_proof_provided,
            latest_proof_verified=latest_proof_verified,
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
        return ProofRefreshReportVerification(
            verified=False,
            ready=False,
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            baseline_proof_verified=baseline_proof_verified,
            latest_proof_provided=latest_proof_provided,
            latest_proof_verified=latest_proof_verified,
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


def load_proof_refresh_evidence(
    path: str | Path | None,
) -> ProofRefreshEvidence:
    if path is None:
        return ProofRefreshEvidence(summary=pd.DataFrame())

    requested = Path(path).resolve()
    if requested.is_file() or requested.suffix.lower() == ".csv":
        root = requested.parent
        summary_path = requested
    else:
        root = requested
        summary_path = root / PROOF_REFRESH_SUMMARY_FILE
    canonical_summary_path = root / PROOF_REFRESH_SUMMARY_FILE
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=PROOF_REFRESH_RUN_TYPE,
        required_artifacts=PROOF_REFRESH_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    verification = verify_proof_refresh_report(root)

    summary = pd.DataFrame()
    read_error = (
        ""
        if summary_path.resolve() == canonical_summary_path.resolve()
        else "summary_path_invalid"
    )
    if not read_error and not summary_path.is_file():
        read_error = "summary_missing"
    elif not read_error:
        try:
            summary = pd.read_csv(summary_path)
        except (
            OSError,
            UnicodeDecodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ):
            read_error = "summary_unreadable"
        if not read_error and summary.empty:
            read_error = "summary_empty"
        if not read_error and len(summary.index) != 1:
            read_error = "summary_row_count_invalid"
        if not read_error:
            missing = [
                column
                for column in PROOF_REFRESH_REQUIRED_SUMMARY_COLUMNS
                if column not in summary.columns
            ]
            if missing:
                read_error = "summary_schema_invalid"

    return ProofRefreshEvidence(
        summary=summary,
        requested_path=requested,
        root=root,
        summary_path=summary_path,
        manifest_path=manifest_path,
        manifest_integrity=integrity,
        verification=verification,
        read_error=read_error,
    )


def proof_refresh_evidence_record(
    evidence: ProofRefreshEvidence,
) -> dict[str, object]:
    row = (
        evidence.summary.iloc[0]
        if evidence.provided
        else pd.Series(dtype=object)
    )
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
        "verified": evidence.verified,
        "read_error": evidence.read_error,
        "input_dir": str(evidence.root or ""),
        "summary_path": str(evidence.summary_path or ""),
        "reported_ready": evidence.reported_ready,
        "ready": evidence.ready,
        "proof_source": _value_text(row.get("proof_source")),
        "fresh_proof_required": _value_bool(
            row.get("fresh_proof_required", False)
        ),
        "strategy": _strategy_key(row.get("strategy", "")),
        "market": _identity_key(row.get("market", "")),
        "mixed_identity": _value_bool(
            row.get("mixed_identity", False)
        ),
        "failed_checks": _value_int(row.get("failed_checks", 0)),
        "manifest_provided": bool(
            integrity is not None and integrity.exists
        ),
        "manifest_current": evidence.manifest_current,
        "manifest_error": str(
            integrity.error if integrity is not None else ""
        ),
        "manifest_run_type": str(
            integrity.run_type if integrity is not None else ""
        ),
        "manifest_run_type_matches": bool(
            integrity is not None and integrity.run_type_matches
        ),
        "manifest_path": str(manifest_path or ""),
        "manifest_sha256": manifest_sha256,
        "manifest_artifact_count": int(
            integrity.artifact_count if integrity is not None else 0
        ),
        "manifest_artifact_match_count": int(
            integrity.artifact_match_count
            if integrity is not None
            else 0
        ),
        "manifest_input_fingerprint_count": int(
            integrity.input_fingerprint_count
            if integrity is not None
            else 0
        ),
        "manifest_input_fingerprint_match_count": int(
            integrity.input_fingerprint_match_count
            if integrity is not None
            else 0
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
        "verification_baseline_proof_verified": bool(
            verification is not None
            and verification.baseline_proof_verified
        ),
        "verification_latest_proof_provided": bool(
            verification is not None
            and verification.latest_proof_provided
        ),
        "verification_latest_proof_verified": bool(
            verification is not None
            and verification.latest_proof_verified
        ),
        "verification_error": str(
            verification.error if verification is not None else ""
        ),
        "reason": evidence.reason,
        "recommendation": evidence.recommendation,
    }


def proof_refresh_evidence_manifest_inputs(
    evidence: ProofRefreshEvidence,
) -> dict[str, object]:
    if not evidence.requested or evidence.root is None:
        return {}
    inputs: dict[str, object] = {
        "proof_refresh": evidence.root,
    }
    manifest_path = evidence.manifest_path
    if manifest_path is not None and manifest_path.is_file():
        inputs["proof_refresh_manifest"] = manifest_path
        dependencies = manifest_dependency_paths(manifest_path)
        if dependencies:
            inputs["proof_refresh_dependencies"] = dependencies
    return inputs


def _proof_verification_summary_fields(
    prefix: str,
    verification: ProofReportVerification | None,
) -> dict[str, object]:
    available = verification is not None
    return {
        f"{prefix}_verification_enforced": available,
        f"{prefix}_semantically_verified": bool(
            available and verification.verified
        ),
        f"{prefix}_verification_passed": bool(
            available and verification.passed
        ),
        f"{prefix}_manifest_current": bool(
            available and verification.manifest_current
        ),
        f"{prefix}_inputs_current": bool(
            available and verification.inputs_current
        ),
        f"{prefix}_replay_manifests_current": bool(
            available and verification.replay_manifests_current
        ),
        f"{prefix}_artifacts_consistent": bool(
            available and verification.artifacts_consistent
        ),
        f"{prefix}_non_authorizing": bool(
            available and verification.non_authorizing
        ),
        f"{prefix}_manifest_artifact_count": (
            verification.manifest_artifact_count
            if available
            else 0
        ),
        f"{prefix}_manifest_artifact_match_count": (
            verification.manifest_artifact_match_count
            if available
            else 0
        ),
        f"{prefix}_manifest_input_fingerprint_count": (
            verification.manifest_input_fingerprint_count
            if available
            else 0
        ),
        f"{prefix}_manifest_input_fingerprint_match_count": (
            verification.manifest_input_fingerprint_match_count
            if available
            else 0
        ),
        f"{prefix}_replay_manifest_count": (
            verification.replay_manifest_count
            if available
            else 0
        ),
        f"{prefix}_replay_manifest_current_count": (
            verification.replay_manifest_current_count
            if available
            else 0
        ),
        f"{prefix}_verification_error": (
            verification.error
            if available
            else ""
        ),
    }


def _proof_refresh_manifest_inputs(
    *,
    drift_file: Path,
    baseline_proof_dir: Path,
    latest_proof_dir: Path | None,
    calibrated_file: Path | None,
) -> dict[str, object]:
    inputs: dict[str, object] = {
        "fill_model_drift": drift_file.resolve(),
        **_proof_bundle_manifest_inputs(
            "baseline_proof",
            baseline_proof_dir,
        ),
    }
    if latest_proof_dir is not None:
        inputs.update(
            _proof_bundle_manifest_inputs(
                "latest_proof",
                latest_proof_dir,
            )
        )
    if calibrated_file is not None:
        inputs["calibrated_replay"] = calibrated_file.resolve()
    return inputs


def _proof_bundle_manifest_inputs(
    prefix: str,
    proof_dir: Path,
) -> dict[str, object]:
    root = proof_dir.resolve()
    manifest_path = root / MANIFEST_NAME
    inputs: dict[str, object] = {prefix: root}
    if not manifest_path.is_file():
        return inputs
    inputs[f"{prefix}_manifest"] = manifest_path
    dependencies = manifest_dependency_paths(manifest_path)
    if dependencies:
        inputs[f"{prefix}_dependencies"] = dependencies
    return inputs


def _proof_refresh_manifest_extra(
    report: ProofRefreshReport,
) -> dict[str, object]:
    row = (
        report.summary.iloc[0]
        if not report.summary.empty
        else pd.Series(dtype=object)
    )
    return {
        "ready": report.ready,
        "proof_source": _value_text(row.get("proof_source")),
        "baseline_proof_verified": _value_bool(
            row.get("baseline_proof_semantically_verified")
        ),
        "latest_proof_available": _value_bool(
            row.get("latest_proof_available")
        ),
        "latest_proof_verified": _value_bool(
            row.get("latest_proof_semantically_verified")
        ),
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }


def _proof_refresh_thresholds_from_manifest(
    parameters: Mapping[str, Any],
) -> ProofRefreshThresholds:
    if set(parameters) != {"thresholds"}:
        raise ValueError(
            "proof-refresh manifest parameters must contain thresholds"
        )
    values = _mapping(parameters.get("thresholds"))
    expected_fields = {
        field.name
        for field in fields(ProofRefreshThresholds)
    }
    if set(values) != expected_fields:
        raise ValueError(
            "proof-refresh manifest threshold contract is incomplete"
        )
    thresholds = ProofRefreshThresholds(**dict(values))
    if dict(parameters) != {"thresholds": asdict(thresholds)}:
        raise ValueError(
            "proof-refresh manifest parameters are not canonical"
        )
    return thresholds


def _proof_refresh_primary_inputs_from_manifest(
    inputs: Mapping[str, Any],
) -> tuple[Path, Path, Path | None, Path | None]:
    drift_file = _manifest_path_fingerprint(
        inputs.get("fill_model_drift"),
        "fill_model_drift",
        expected_kind="file",
    )
    baseline_proof_dir = _manifest_path_fingerprint(
        inputs.get("baseline_proof"),
        "baseline_proof",
        expected_kind="directory",
    )
    latest_proof_dir = (
        _manifest_path_fingerprint(
            inputs.get("latest_proof"),
            "latest_proof",
            expected_kind="directory",
        )
        if "latest_proof" in inputs
        else None
    )
    calibrated_file = (
        _manifest_path_fingerprint(
            inputs.get("calibrated_replay"),
            "calibrated_replay",
            expected_kind="file",
        )
        if "calibrated_replay" in inputs
        else None
    )
    return (
        drift_file,
        baseline_proof_dir,
        latest_proof_dir,
        calibrated_file,
    )


def _manifest_path_fingerprint(
    value: Any,
    label: str,
    *,
    expected_kind: str,
) -> Path:
    fingerprint = _mapping(value)
    if fingerprint.get("kind") != expected_kind:
        raise ValueError(
            f"proof-refresh manifest {label} input is not a "
            f"{expected_kind} fingerprint"
        )
    raw_path = str(fingerprint.get("path", "")).strip()
    if not raw_path:
        raise ValueError(
            f"proof-refresh manifest {label} input path is missing"
        )
    return Path(raw_path).resolve()


def _proof_refresh_input_contract_current(
    inputs: Mapping[str, Any],
    *,
    drift_file: Path,
    baseline_proof_dir: Path,
    latest_proof_dir: Path | None,
    calibrated_file: Path | None,
) -> bool:
    expected = _proof_refresh_manifest_inputs(
        drift_file=drift_file,
        baseline_proof_dir=baseline_proof_dir,
        latest_proof_dir=latest_proof_dir,
        calibrated_file=calibrated_file,
    )
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


def _proof_refresh_artifacts_consistent(
    root: Path,
    expected: ProofRefreshReport,
    thresholds: ProofRefreshThresholds,
    manifest: Mapping[str, Any],
) -> bool:
    action_queue = (
        expected.action_queue
        if expected.action_queue is not None
        else _action_queue(expected.checks)
    )
    expected_config = expected.config or _config(
        expected.decision.iloc[0],
        expected.summary.iloc[0],
        thresholds,
        action_queue,
    )
    return bool(
        _proof_refresh_manifest_artifacts_exact(manifest)
        and _csv_frame_matches(
            root / PROOF_REFRESH_DECISION_FILE,
            expected.decision,
        )
        and _csv_frame_matches(
            root / PROOF_REFRESH_CHECKS_FILE,
            expected.checks,
        )
        and _csv_frame_matches(
            root / PROOF_REFRESH_SUMMARY_FILE,
            expected.summary,
        )
        and _csv_frame_matches(
            root / PROOF_REFRESH_ACTION_QUEUE_FILE,
            action_queue,
        )
        and _read_json_object(
            root / PROOF_REFRESH_CONFIG_FILE,
            "proof-refresh config",
        )
        == expected_config
        and (root / PROOF_REFRESH_RUNBOOK_FILE).read_text(
            encoding="utf-8"
        )
        == _runbook_markdown(
            expected.summary.iloc[0],
            action_queue,
        )
    )


def _proof_refresh_manifest_artifacts_exact(
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
        len(names) == len(PROOF_REFRESH_REQUIRED_ARTIFACTS)
        and len(names) == len(artifacts)
        and set(names) == set(PROOF_REFRESH_REQUIRED_ARTIFACTS)
    )


def _proof_refresh_authority_consistent(
    root: Path,
    manifest_extra: Mapping[str, Any],
    expected: ProofRefreshReport,
) -> bool:
    summary = _read_csv_frame(
        root / PROOF_REFRESH_SUMMARY_FILE,
        "proof-refresh summary",
    )
    config = _read_json_object(
        root / PROOF_REFRESH_CONFIG_FILE,
        "proof-refresh config",
    )
    if len(summary.index) != 1:
        return False
    row = summary.iloc[0]
    authority = _mapping(config.get("authority"))
    return bool(
        _value_bool(row.get("non_authorizing", False))
        and not _value_bool(row.get("authorizes_routing", True))
        and not _value_bool(row.get("authorizes_submission", True))
        and _value_bool(authority.get("non_authorizing", False))
        and not _value_bool(authority.get("authorizes_routing", True))
        and not _value_bool(
            authority.get("authorizes_submission", True)
        )
        and dict(manifest_extra)
        == _proof_refresh_manifest_extra(expected)
    )


def _csv_frame_matches(
    path: Path,
    expected: pd.DataFrame,
) -> bool:
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


def _read_json_object(
    path: Path,
    label: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _checks(
    *,
    drift_passed: bool,
    baseline_reported_passed: bool,
    baseline_verification_enforced: bool,
    baseline_verified: bool,
    latest_available: bool,
    latest_reported_passed: bool,
    latest_verification_enforced: bool,
    latest_verified: bool,
    calibrated_available: bool,
    calibrated_ready: bool,
    calibrated_strategy: str,
    identities: pd.DataFrame,
    thresholds: ProofRefreshThresholds,
) -> pd.DataFrame:
    checks = []
    if baseline_verification_enforced:
        checks.append(
            _check(
                "baseline_proof_verified",
                baseline_verified,
                "is",
                True,
                baseline_verified,
                "baseline proof bundle failed semantic verification",
            )
        )
    if latest_available and latest_verification_enforced:
        checks.append(
            _check(
                "latest_proof_verified",
                latest_verified,
                "is",
                True,
                latest_verified,
                "latest proof bundle failed semantic verification",
            )
        )
    if drift_passed:
        checks.append(
            _check(
                "reusable_proof_passed",
                baseline_reported_passed or latest_reported_passed,
                "is",
                True,
                baseline_reported_passed or latest_reported_passed,
                "neither baseline nor latest proof passed under reusable fill-model assumptions",
            )
        )
    else:
        checks.extend(
            [
                _check(
                    "latest_proof_available",
                    latest_available,
                    "is",
                    True,
                    latest_available,
                    "fill-model drift failed, so a fresh/latest proof report is required",
                ),
                _check(
                    "latest_proof_passed",
                    latest_reported_passed,
                    "is",
                    True,
                    latest_reported_passed,
                    "latest proof report did not pass",
                ),
            ]
        )
        if thresholds.require_calibrated_replay_when_drift_fails:
            checks.extend(
                [
                    _check(
                        "calibrated_replay_available",
                        calibrated_available,
                        "is",
                        True,
                        calibrated_available,
                        "fill-model drift failed, so a calibrated replay plan is required",
                    ),
                    _check(
                        "calibrated_replay_ready",
                        calibrated_ready,
                        "is",
                        True,
                        calibrated_ready,
                        "calibrated replay plan is not ready",
                    ),
                ]
            )
        if thresholds.expected_strategy is not None:
            expected = _strategy_key(thresholds.expected_strategy)
            actual = _strategy_key(calibrated_strategy) if calibrated_strategy else ""
            checks.append(
                _check(
                    "calibrated_replay_strategy_matches",
                    actual,
                    "==",
                    expected,
                    bool(actual) and actual == expected,
                    "calibrated replay plan strategy does not match expected strategy",
                )
            )

    checks.extend(_identity_checks(identities, thresholds))
    return pd.DataFrame(checks)


def _identity_checks(identities: pd.DataFrame, thresholds: ProofRefreshThresholds) -> list[dict[str, object]]:
    strategies = _identity_values(identities, "strategy", normalizer=_strategy_key)
    markets = _identity_values(identities, "market", normalizer=_identity_key)
    rows = [
        _check(
            "same_strategy",
            ";".join(sorted(strategies)) if strategies else "",
            "count<=",
            1,
            len(strategies) <= 1,
            "proof refresh inputs mix strategy identities",
        ),
        _check(
            "same_market",
            ";".join(sorted(markets)) if markets else "",
            "count<=",
            1,
            len(markets) <= 1,
            "proof refresh inputs mix market identities",
        ),
    ]
    if thresholds.expected_strategy is not None:
        expected = _strategy_key(thresholds.expected_strategy)
        rows.append(
            _check(
                "expected_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "==",
                expected,
                not strategies or strategies == {expected},
                "available proof refresh strategies do not match expected strategy",
            )
        )
    if thresholds.expected_market is not None:
        expected = _identity_key(thresholds.expected_market)
        rows.append(
            _check(
                "expected_market",
                ";".join(sorted(markets)) if markets else "",
                "==",
                expected,
                not markets or markets == {expected},
                "available proof refresh markets do not match expected market",
            )
        )
    return rows


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


def _summary_with_actions(
    summary: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    out = summary.copy()
    failed = _failed_check_rows(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    out["failed_check_count"] = int(len(failed))
    out["failed_check_names"] = ";".join(failed["check"].astype(str).tolist()) if not failed.empty else ""
    out["first_failed_reason"] = _value_text(failed.iloc[0].get("reason")) if not failed.empty else ""
    out["primary_blocker_check"] = _value_text(failed.iloc[0].get("check")) if not failed.empty else ""
    out["primary_blocker_value"] = _value_text(failed.iloc[0].get("value")) if not failed.empty else ""
    out["primary_blocker_operator"] = _value_text(failed.iloc[0].get("operator")) if not failed.empty else ""
    out["primary_blocker_threshold"] = _value_text(failed.iloc[0].get("threshold")) if not failed.empty else ""
    out["primary_blocker_reason"] = _value_text(failed.iloc[0].get("reason")) if not failed.empty else ""
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _value_text(row.get("check"))
        rows.append(
            _action_row(
                component=_component(check),
                check=check,
                actual=row.get("value"),
                operator=_value_text(row.get("operator")),
                expected=row.get("threshold"),
                reason=_value_text(row.get("reason")),
                recommendation=_action_recommendation(check),
            )
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _action_row(
    *,
    component: str,
    check: str,
    actual: object,
    operator: str,
    expected: object,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    next_gate = "review-proof-refresh"
    return {
        "queue_status": "blocked",
        "source": "proof_refresh_checks",
        "component": component,
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _proof_verification_config(
    summary_row: pd.Series,
    prefix: str,
) -> dict[str, object]:
    return {
        "enforced": _value_bool(
            summary_row.get(f"{prefix}_verification_enforced")
        ),
        "verified": _value_bool(
            summary_row.get(f"{prefix}_semantically_verified")
        ),
        "passed": _value_bool(
            summary_row.get(f"{prefix}_verification_passed")
        ),
        "manifest_current": _value_bool(
            summary_row.get(f"{prefix}_manifest_current")
        ),
        "inputs_current": _value_bool(
            summary_row.get(f"{prefix}_inputs_current")
        ),
        "replay_manifests_current": _value_bool(
            summary_row.get(f"{prefix}_replay_manifests_current")
        ),
        "artifacts_consistent": _value_bool(
            summary_row.get(f"{prefix}_artifacts_consistent")
        ),
        "non_authorizing": _value_bool(
            summary_row.get(f"{prefix}_non_authorizing")
        ),
        "manifest_artifact_count": _value_int(
            summary_row.get(f"{prefix}_manifest_artifact_count")
        ),
        "manifest_artifact_match_count": _value_int(
            summary_row.get(f"{prefix}_manifest_artifact_match_count")
        ),
        "manifest_input_fingerprint_count": _value_int(
            summary_row.get(
                f"{prefix}_manifest_input_fingerprint_count"
            )
        ),
        "manifest_input_fingerprint_match_count": _value_int(
            summary_row.get(
                f"{prefix}_manifest_input_fingerprint_match_count"
            )
        ),
        "replay_manifest_count": _value_int(
            summary_row.get(f"{prefix}_replay_manifest_count")
        ),
        "replay_manifest_current_count": _value_int(
            summary_row.get(
                f"{prefix}_replay_manifest_current_count"
            )
        ),
        "error": _value_text(
            summary_row.get(f"{prefix}_verification_error")
        ),
    }


def _config(
    decision_row: pd.Series,
    summary_row: pd.Series,
    thresholds: ProofRefreshThresholds,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "ready": _value_bool(summary_row.get("ready")),
        "authority": {
            "non_authorizing": _value_bool(
                summary_row.get("non_authorizing")
            ),
            "authorizes_routing": _value_bool(
                summary_row.get("authorizes_routing")
            ),
            "authorizes_submission": _value_bool(
                summary_row.get("authorizes_submission")
            ),
        },
        "decision": {
            "action": _value_text(decision_row.get("action")),
            "proof_source": _value_text(decision_row.get("proof_source")),
            "fresh_proof_required": _value_bool(decision_row.get("fresh_proof_required")),
            "reason": _value_text(decision_row.get("reason")),
        },
        "thresholds": asdict(thresholds),
        "identity": {
            "strategy": _value_text(summary_row.get("strategy")),
            "strategy_count": _value_int(summary_row.get("strategy_count")),
            "missing_strategy_sources": _value_int(summary_row.get("missing_strategy_sources")),
            "expected_strategy": _value_text(summary_row.get("expected_strategy")),
            "market": _value_text(summary_row.get("market")),
            "market_count": _value_int(summary_row.get("market_count")),
            "missing_market_sources": _value_int(summary_row.get("missing_market_sources")),
            "expected_market": _value_text(summary_row.get("expected_market")),
            "mixed_identity": _value_bool(summary_row.get("mixed_identity")),
        },
        "proof": {
            "drift_passed": _value_bool(summary_row.get("drift_passed")),
            "fresh_proof_required": _value_bool(summary_row.get("fresh_proof_required")),
            "proof_source": _value_text(summary_row.get("proof_source")),
            "baseline_proof_reported_passed": _value_bool(
                summary_row.get("baseline_proof_reported_passed")
            ),
            "baseline_proof_passed": _value_bool(summary_row.get("baseline_proof_passed")),
            "baseline_proof_verification": _proof_verification_config(
                summary_row,
                "baseline_proof",
            ),
            "latest_proof_available": _value_bool(summary_row.get("latest_proof_available")),
            "latest_proof_reported_passed": _value_bool(
                summary_row.get("latest_proof_reported_passed")
            ),
            "latest_proof_passed": _value_bool(summary_row.get("latest_proof_passed")),
            "latest_proof_verification": _proof_verification_config(
                summary_row,
                "latest_proof",
            ),
            "calibrated_replay_required": _value_bool(summary_row.get("calibrated_replay_required")),
            "calibrated_replay_available": _value_bool(summary_row.get("calibrated_replay_available")),
            "calibrated_replay_ready": _value_bool(summary_row.get("calibrated_replay_ready")),
        },
        "failed_check_count": _value_int(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _value_text(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _value_text(summary_row.get("primary_blocker_check")),
            "value": _value_text(summary_row.get("primary_blocker_value")),
            "operator": _value_text(summary_row.get("primary_blocker_operator")),
            "threshold": _value_text(summary_row.get("primary_blocker_threshold")),
            "reason": _value_text(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _value_int(summary_row.get("action_queue_count")),
        "ready_action_count": _value_int(summary_row.get("ready_action_count")),
        "blocked_action_count": _value_int(summary_row.get("blocked_action_count")),
        "review_action_count": _value_int(summary_row.get("review_action_count")),
        "next_gate": _value_text(summary_row.get("next_gate")),
        "next_gate_help_command": _value_text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _value_text(summary_row.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
        "recommendation": _value_text(summary_row.get("recommendation")),
    }


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _value_bool(summary_row.get("ready")) else "no"
    lines = [
        "# Proof Refresh Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Drift passed: {_value_text(summary_row.get('drift_passed'))}",
        f"- Fresh proof required: {_value_text(summary_row.get('fresh_proof_required'))}",
        f"- Proof source: {_value_text(summary_row.get('proof_source'))}",
        f"- Baseline proof reported passed: {_value_text(summary_row.get('baseline_proof_reported_passed'))}",
        f"- Baseline proof semantically verified: {_value_text(summary_row.get('baseline_proof_semantically_verified'))}",
        f"- Baseline proof effective passed: {_value_text(summary_row.get('baseline_proof_passed'))}",
        f"- Latest proof available: {_value_text(summary_row.get('latest_proof_available'))}",
        f"- Latest proof reported passed: {_value_text(summary_row.get('latest_proof_reported_passed'))}",
        f"- Latest proof semantically verified: {_value_text(summary_row.get('latest_proof_semantically_verified'))}",
        f"- Latest proof effective passed: {_value_text(summary_row.get('latest_proof_passed'))}",
        f"- Calibrated replay required: {_value_text(summary_row.get('calibrated_replay_required'))}",
        f"- Calibrated replay ready: {_value_text(summary_row.get('calibrated_replay_ready'))}",
        f"- Strategy: {_value_text(summary_row.get('strategy'))}",
        f"- Market: {_value_text(summary_row.get('market'))}",
        f"- Mixed identity: {_value_text(summary_row.get('mixed_identity'))}",
        f"- Non-authorizing: {_value_text(summary_row.get('non_authorizing'))}",
        f"- Authorizes routing: {_value_text(summary_row.get('authorizes_routing'))}",
        f"- Authorizes submission: {_value_text(summary_row.get('authorizes_submission'))}",
        f"- Failed checks: {_value_int(summary_row.get('failed_check_count'))}",
        f"- Blocked actions: {_value_int(summary_row.get('blocked_action_count'))}",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No proof-refresh actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _value_text(item.get("priority")),
                    _value_text(item.get("queue_status")),
                    _value_text(item.get("component")),
                    _value_text(item.get("check")),
                    _value_text(item.get("actual")),
                    _value_text(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _value_text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].copy()


def _component(check: str) -> str:
    if check in {
        "baseline_proof_verified",
        "latest_proof_verified",
        "reusable_proof_passed",
        "latest_proof_available",
        "latest_proof_passed",
    }:
        return "proof_evidence"
    if check in {
        "calibrated_replay_available",
        "calibrated_replay_ready",
        "calibrated_replay_strategy_matches",
    }:
        return "calibrated_replay"
    if check in {"same_strategy", "expected_strategy"}:
        return "strategy_identity"
    if check in {"same_market", "expected_market"}:
        return "market_identity"
    return "proof_refresh"


def _action_recommendation(check: str) -> str:
    if check == "baseline_proof_verified":
        return "regenerate_and_verify_baseline_proof"
    if check == "latest_proof_verified":
        return "regenerate_and_verify_latest_proof"
    if check == "reusable_proof_passed":
        return "repair_or_rerun_reusable_proof_before_promotion"
    if check in {"latest_proof_available", "latest_proof_passed"}:
        return "rerun_latest_calibrated_proof"
    if check in {"calibrated_replay_available", "calibrated_replay_ready"}:
        return "run_calibrated_replay_plan_before_proof_refresh"
    if check == "calibrated_replay_strategy_matches":
        return "regenerate_calibrated_replay_for_expected_strategy"
    if check in {"same_strategy", "expected_strategy"}:
        return "align_proof_refresh_strategy_identity"
    if check in {"same_market", "expected_market"}:
        return "align_proof_refresh_market_identity"
    return "repair_proof_refresh_inputs"


def _proof_source(drift_passed: bool, baseline_passed: bool, latest_passed: bool, ready: bool) -> str:
    if not ready:
        return "none"
    if not drift_passed:
        return "latest"
    if baseline_passed:
        return "baseline"
    return "latest" if latest_passed else "none"


def _recommendation(ready: bool, drift_passed: bool) -> str:
    if ready and drift_passed:
        return "reuse_existing_proof"
    if ready:
        return "use_latest_calibrated_proof"
    if drift_passed:
        return "repair_proof_before_promotion"
    return "rerun_calibrated_proof_before_promotion"


def _reason(
    ready: bool,
    drift_passed: bool,
    latest_available: bool,
    latest_passed: bool,
    calibrated_ready: bool,
) -> str:
    if ready and drift_passed:
        return "fill-model drift passed, so reusable proof assumptions remain valid"
    if ready:
        return "fill-model drift failed, but latest calibrated proof evidence passed"
    if drift_passed:
        return "fill-model drift passed, but no passing proof report is available"
    if not latest_available:
        return "fill-model drift failed and no latest proof report was supplied"
    if not latest_passed:
        return "fill-model drift failed and latest proof report did not pass"
    if not calibrated_ready:
        return "fill-model drift failed and calibrated replay plan is not ready"
    return "proof refresh gate has unresolved failed checks"


def _summary_path(path: str | Path, filename: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / filename
    if not candidate.exists():
        raise FileNotFoundError(f"summary artifact not found: {candidate}")
    return candidate


def _optional_summary_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    return _summary_path(path, filename)


def _read_summary(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"summary artifact is empty: {path}")
    return frame


def _frame_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    value = frame.iloc[0][column]
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _frame_str(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    value = frame.iloc[0][column]
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _input_identities(
    *,
    baseline_proof_summary: pd.DataFrame,
    latest_proof_summary: pd.DataFrame | None,
    calibrated_replay_summary: pd.DataFrame | None,
) -> pd.DataFrame:
    rows = [
        _identity_row("baseline_proof", baseline_proof_summary),
    ]
    if latest_proof_summary is not None and not latest_proof_summary.empty:
        rows.append(_identity_row("latest_proof", latest_proof_summary))
    if calibrated_replay_summary is not None and not calibrated_replay_summary.empty:
        rows.append(_identity_row("calibrated_replay", calibrated_replay_summary))
    return pd.DataFrame(rows)


def _identity_row(source: str, frame: pd.DataFrame) -> dict[str, str]:
    row = frame.iloc[0] if frame is not None and not frame.empty else pd.Series(dtype=object)
    return {
        "source": source,
        "strategy": _strategy_key(_first_identity(row, ("strategy", "strategy_name", "strategy_id"))),
        "market": _identity_key(_first_identity(row, ("market", "market_profile", "market_name", "market_id"))),
    }


def _identity_values(frame: pd.DataFrame, column: str, *, normalizer) -> set[str]:
    if frame.empty or column not in frame.columns:
        return set()
    return {value for value in frame[column].map(normalizer) if value}


def _missing_identity_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty:
        return 0
    if column not in frame.columns:
        return int(len(frame))
    return int((frame[column].map(_identity_key) == "").sum())


def _single_identity(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else ""


def _first_identity(row: pd.Series, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(row, key)
        if value:
            return value
    return ""


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


def _strategy_key(strategy: object) -> str:
    key = _identity_key(strategy)
    aliases = {
        "lead_lag": "leadlag",
        "lead_lag_taker": "leadlag",
        "leadlag_taker": "leadlag",
        "leadlag_replay": "leadlag",
        "microprice": "imbalance",
        "microprice_imbalance": "imbalance",
        "order_book_imbalance": "imbalance",
        "obi": "imbalance",
        "surface": "surface_mm",
        "surface_market_making": "surface_mm",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _value_text(action_queue.iloc[0].get(column))


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_value(value) for key, value in row.items()}


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _split_items(value: object) -> list[str]:
    text = _value_text(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _proof_refresh_verification_error_slug(error: str) -> str:
    text = str(error).strip().lower()
    if not text:
        return "verification_failed"
    normalized = "".join(
        character if character.isalnum() else "_"
        for character in text
    )
    return (
        "verification_"
        + "_".join(part for part in normalized.split("_") if part)
    )


def _help_command(next_gate: str) -> str:
    gate = _value_text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _value_text(value)
    return f"`{text}`" if text else ""


def _value_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _value_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _value_int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }
