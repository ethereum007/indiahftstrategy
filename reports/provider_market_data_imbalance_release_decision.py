from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.provider_market_data_imbalance_release_review import (
    RUN_TYPE as RELEASE_REVIEW_RUN_TYPE,
    verify_provider_market_data_imbalance_release_review,
)


RUN_TYPE = "provider_market_data_imbalance_release_decision"
CONTRACT_VERSION = "provider_market_data_imbalance_release_decision/v1"
DECISION_ARTIFACTS = (
    "provider_market_data_imbalance_release_decision_checks.csv",
    "provider_market_data_imbalance_release_decision_proofs.csv",
    "provider_market_data_imbalance_release_decision_summary.csv",
    "provider_market_data_imbalance_release_decision.json",
    "provider_market_data_imbalance_release_decision_config.json",
    "provider_market_data_imbalance_release_decision_runbook.md",
)
OPERATOR_DECISION_COLUMNS = (
    "release_review_id",
    "packet_sha256",
    "strategy",
    "market",
    "target_mode",
    "strategy_evidence_manifest_sha256",
    "catalog_manifest_sha256",
    "active_lineage_chain_audit_manifest_sha256",
    "broker_rehearsal_certificate_manifest_sha256",
    "decision",
    "operator_id",
    "operator_role",
    "reviewed_at_utc",
    "risk_limits_acknowledged",
    "kill_switch_acknowledged",
    "rollback_plan_acknowledged",
    "notes",
    "authorizes_submission",
)
CHECK_COLUMNS = (
    "check",
    "component",
    "value",
    "operator",
    "threshold",
    "passed",
    "reason",
)
PROOF_COLUMNS = (
    "component",
    "path",
    "kind",
    "sha256",
    "digest_sha256",
    "current",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceReleaseDecisionConfig:
    max_dependency_count: int = 2048


@dataclass(frozen=True)
class ProviderMarketDataImbalanceReleaseDecisionReport:
    checks: pd.DataFrame
    proofs: pd.DataFrame
    summary: pd.DataFrame
    decision: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def sealed(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("sealed", False))
        )

    @property
    def ready(self) -> bool:
        return bool(
            self.sealed
            and _bool(
                self.summary.iloc[0].get(
                    "approved_for_live_dryrun",
                    False,
                )
            )
        )


@dataclass(frozen=True)
class ProviderMarketDataImbalanceReleaseDecisionVerification:
    verified: bool
    sealed: bool
    approved: bool
    ready: bool
    manifest_current: bool
    release_review_current: bool
    operator_decision_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    output_dir: Path
    release_review_dir: Path | None
    operator_decision_path: Path | None
    error: str = ""


def write_provider_market_data_imbalance_release_decision(
    release_review_dir: str | Path,
    operator_decision_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceReleaseDecisionConfig | None = None,
) -> ProviderMarketDataImbalanceReleaseDecisionReport:
    config = config or ProviderMarketDataImbalanceReleaseDecisionConfig()
    _validate_config(config)
    release_root = Path(release_review_dir).resolve()
    release_manifest_path = release_root / MANIFEST_NAME
    operator_path = Path(operator_decision_path).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(
            f"release-decision output already exists: {out}"
        )

    release_verification = (
        verify_provider_market_data_imbalance_release_review(release_root)
    )
    if not (
        release_verification.verified
        and release_verification.ready
        and release_verification.operator_approval_pending
    ):
        raise ValueError(
            "release decision requires a verified, ready, pending "
            "release-review packet: "
            f"{release_verification.error or 'release_review_not_ready'}"
        )

    release_manifest = _read_json(
        release_manifest_path,
        "release-review manifest",
    )
    if _text(release_manifest.get("run_type")) != RELEASE_REVIEW_RUN_TYPE:
        raise ValueError("release decision source is not a release-review run")
    release_manifest_sha256 = file_sha256(release_manifest_path)
    release_summary = _single_row(
        _read_csv(
            release_root
            / "provider_market_data_imbalance_release_review_summary.csv",
            "release-review summary",
        ),
        "release-review summary",
    )
    release_packet = _read_json(
        release_root
        / "provider_market_data_imbalance_release_review_packet.json",
        "release-review packet",
    )
    operator_frame = _read_csv(operator_path, "operator decision")
    operator_row = _single_row(operator_frame, "operator decision")
    _require_operator_columns(operator_frame)
    _reject_output_collision(
        out,
        release_root=release_root,
        operator_path=operator_path,
    )

    direct_paths = {
        release_root,
        release_manifest_path,
        operator_path,
    }
    recursive_dependencies = _recursive_dependencies(
        release_manifest_path,
        direct_paths,
    )
    checks = _decision_checks(
        release_verification=release_verification,
        release_summary=release_summary,
        release_packet=release_packet,
        operator_row=operator_row,
        operator_path=operator_path,
        release_root=release_root,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    failed_checks = checks.loc[
        ~checks["passed"].map(_bool),
        "check",
    ].astype(str).tolist()
    if failed_checks:
        raise ValueError(
            "operator decision contract failed: " + ", ".join(failed_checks)
        )

    operator_decision_sha256 = file_sha256(operator_path)
    proof_contract = _proof_contract(
        release_root=release_root,
        release_manifest_path=release_manifest_path,
        release_manifest_sha256=release_manifest_sha256,
        release_summary=release_summary,
        operator_path=operator_path,
        operator_decision_sha256=operator_decision_sha256,
    )
    decision_core = _decision_core(
        release_summary=release_summary,
        operator_row=operator_row,
        proof_contract=proof_contract,
    )
    decision_sha256 = _canonical_sha256(decision_core)
    decision_id = f"provider-release-decision-{decision_sha256[:24]}"
    decision = {
        **decision_core,
        "decision_id": decision_id,
        "decision_sha256": decision_sha256,
    }
    proofs = _proof_rows(proof_contract)
    summary = _summary(
        decision_id=decision_id,
        decision_sha256=decision_sha256,
        release_summary=release_summary,
        operator_row=operator_row,
        proof_contract=proof_contract,
        recursive_dependency_count=len(recursive_dependencies),
        checks=checks,
    )
    config_payload = _config_payload(
        config=config,
        decision_id=decision_id,
        decision_sha256=decision_sha256,
        release_root=release_root,
        operator_path=operator_path,
        proof_contract=proof_contract,
        approved=_decision_value(operator_row) == "approved",
    )

    out.mkdir(parents=True, exist_ok=True)
    checks.to_csv(
        out / "provider_market_data_imbalance_release_decision_checks.csv",
        index=False,
    )
    proofs.to_csv(
        out / "provider_market_data_imbalance_release_decision_proofs.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_market_data_imbalance_release_decision_summary.csv",
        index=False,
    )
    (
        out / "provider_market_data_imbalance_release_decision.json"
    ).write_text(
        json.dumps(_jsonable(decision), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_release_decision_config.json"
    ).write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_release_decision_runbook.md"
    ).write_text(
        _runbook_markdown(summary.iloc[0], proof_contract),
        encoding="utf-8",
    )

    final_release_verification = (
        verify_provider_market_data_imbalance_release_review(release_root)
    )
    if (
        not final_release_verification.verified
        or not final_release_verification.ready
        or file_sha256(release_manifest_path) != release_manifest_sha256
        or file_sha256(operator_path) != operator_decision_sha256
    ):
        raise RuntimeError(
            "release review or operator decision changed during finalization"
        )

    manifest_inputs: dict[str, Any] = {
        "release_review": release_root,
        "release_review_manifest": release_manifest_path,
        "operator_decision": operator_path,
    }
    if recursive_dependencies:
        manifest_inputs["release_review_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(
            decision_id=decision_id,
            decision_sha256=decision_sha256,
            release_summary=release_summary,
            proof_contract=proof_contract,
            approved=_decision_value(operator_row) == "approved",
        ),
    )
    return ProviderMarketDataImbalanceReleaseDecisionReport(
        checks=checks,
        proofs=proofs,
        summary=summary,
        decision=decision,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_release_decision(
    release_decision_dir: str | Path,
) -> ProviderMarketDataImbalanceReleaseDecisionVerification:
    candidate = Path(release_decision_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=DECISION_ARTIFACTS,
        require_input_fingerprints=True,
    )
    release_root: Path | None = None
    operator_path: Path | None = None
    try:
        manifest = _read_json(manifest_path, "release-decision manifest")
        checks_frame = _read_csv(
            root / "provider_market_data_imbalance_release_decision_checks.csv",
            "release-decision checks",
        )
        proofs_frame = _read_csv(
            root / "provider_market_data_imbalance_release_decision_proofs.csv",
            "release-decision proofs",
        )
        summary_frame = _read_csv(
            root / "provider_market_data_imbalance_release_decision_summary.csv",
            "release-decision summary",
        )
        summary = _single_row(summary_frame, "release-decision summary")
        saved_decision = _read_json(
            root / "provider_market_data_imbalance_release_decision.json",
            "sealed release decision",
        )
        saved_config = _read_json(
            root
            / "provider_market_data_imbalance_release_decision_config.json",
            "release-decision config",
        )
        runbook = (
            root
            / "provider_market_data_imbalance_release_decision_runbook.md"
        ).read_text(encoding="utf-8")

        inputs = _mapping(manifest.get("inputs"))
        release_record = _mapping(inputs.get("release_review"))
        operator_record = _mapping(inputs.get("operator_decision"))
        if (
            release_record.get("kind") != "directory"
            or not _text(release_record.get("path"))
            or operator_record.get("kind") != "file"
            or not _text(operator_record.get("path"))
        ):
            raise ValueError("release-decision input contract is invalid")
        release_root = Path(str(release_record["path"])).resolve()
        operator_path = Path(str(operator_record["path"])).resolve()
        release_manifest_path = release_root / MANIFEST_NAME
        release_verification = (
            verify_provider_market_data_imbalance_release_review(release_root)
        )
        release_current = bool(
            release_verification.verified
            and release_verification.ready
            and release_verification.operator_approval_pending
        )
        operator_current = bool(
            operator_path.is_file()
            and _valid_sha256(operator_record.get("sha256"))
            and file_sha256(operator_path)
            == _text(operator_record.get("sha256")).lower()
        )
        if not release_current or not operator_current:
            return ProviderMarketDataImbalanceReleaseDecisionVerification(
                verified=False,
                sealed=False,
                approved=False,
                ready=False,
                manifest_current=bool(integrity.passed),
                release_review_current=release_current,
                operator_decision_current=operator_current,
                artifacts_consistent=False,
                non_authorizing=_surfaces_non_authorizing(
                    summary,
                    saved_decision,
                    saved_config,
                    _mapping(manifest.get("extra")),
                ),
                output_dir=root,
                release_review_dir=release_root,
                operator_decision_path=operator_path,
                error=(
                    "release_decision_source_not_current:"
                    + (
                        release_verification.error
                        if not release_current
                        else "operator_decision_changed"
                    )
                ),
            )

        release_manifest = _read_json(
            release_manifest_path,
            "release-review manifest",
        )
        if _text(release_manifest.get("run_type")) != RELEASE_REVIEW_RUN_TYPE:
            raise ValueError("release-decision source has the wrong run type")
        release_manifest_sha256 = file_sha256(release_manifest_path)
        release_summary = _single_row(
            _read_csv(
                release_root
                / "provider_market_data_imbalance_release_review_summary.csv",
                "release-review summary",
            ),
            "release-review summary",
        )
        release_packet = _read_json(
            release_root
            / "provider_market_data_imbalance_release_review_packet.json",
            "release-review packet",
        )
        operator_frame = _read_csv(operator_path, "operator decision")
        operator_row = _single_row(operator_frame, "operator decision")
        _require_operator_columns(operator_frame)
        manifest_settings = dict(
            _mapping(_mapping(manifest.get("parameters")).get("config"))
        )
        config = ProviderMarketDataImbalanceReleaseDecisionConfig(
            **manifest_settings
        )
        _validate_config(config)
        direct_paths = {
            release_root,
            release_manifest_path,
            operator_path,
        }
        recursive_dependencies = _recursive_dependencies(
            release_manifest_path,
            direct_paths,
        )
        expected_checks = _decision_checks(
            release_verification=release_verification,
            release_summary=release_summary,
            release_packet=release_packet,
            operator_row=operator_row,
            operator_path=operator_path,
            release_root=release_root,
            recursive_dependency_count=len(recursive_dependencies),
            config=config,
        )
        failed_checks = expected_checks.loc[
            ~expected_checks["passed"].map(_bool),
            "check",
        ].astype(str).tolist()
        if failed_checks:
            return ProviderMarketDataImbalanceReleaseDecisionVerification(
                verified=False,
                sealed=False,
                approved=False,
                ready=False,
                manifest_current=bool(integrity.passed),
                release_review_current=True,
                operator_decision_current=True,
                artifacts_consistent=False,
                non_authorizing=_surfaces_non_authorizing(
                    summary,
                    saved_decision,
                    saved_config,
                    _mapping(manifest.get("extra")),
                ),
                output_dir=root,
                release_review_dir=release_root,
                operator_decision_path=operator_path,
                error=(
                    "operator_decision_contract_failed:"
                    + ",".join(failed_checks)
                ),
            )

        operator_decision_sha256 = file_sha256(operator_path)
        proof_contract = _proof_contract(
            release_root=release_root,
            release_manifest_path=release_manifest_path,
            release_manifest_sha256=release_manifest_sha256,
            release_summary=release_summary,
            operator_path=operator_path,
            operator_decision_sha256=operator_decision_sha256,
        )
        expected_core = _decision_core(
            release_summary=release_summary,
            operator_row=operator_row,
            proof_contract=proof_contract,
        )
        decision_sha256 = _canonical_sha256(expected_core)
        decision_id = f"provider-release-decision-{decision_sha256[:24]}"
        expected_decision = {
            **expected_core,
            "decision_id": decision_id,
            "decision_sha256": decision_sha256,
        }
        expected_proofs = _proof_rows(proof_contract)
        expected_summary = _summary(
            decision_id=decision_id,
            decision_sha256=decision_sha256,
            release_summary=release_summary,
            operator_row=operator_row,
            proof_contract=proof_contract,
            recursive_dependency_count=len(recursive_dependencies),
            checks=expected_checks,
        )
        approved = _decision_value(operator_row) == "approved"
        expected_config = _config_payload(
            config=config,
            decision_id=decision_id,
            decision_sha256=decision_sha256,
            release_root=release_root,
            operator_path=operator_path,
            proof_contract=proof_contract,
            approved=approved,
        )
        expected_extra = _manifest_extra(
            decision_id=decision_id,
            decision_sha256=decision_sha256,
            release_summary=release_summary,
            proof_contract=proof_contract,
            approved=approved,
        )
        expected_runbook = _runbook_markdown(
            expected_summary.iloc[0],
            proof_contract,
        )
        artifacts_consistent = bool(
            saved_decision == expected_decision
            and saved_config == expected_config
            and _dataframe_records_equal(checks_frame, expected_checks)
            and _dataframe_records_equal(proofs_frame, expected_proofs)
            and _dataframe_records_equal(summary_frame, expected_summary)
            and runbook == expected_runbook
            and dict(_mapping(manifest.get("extra"))) == expected_extra
            and _manifest_inputs_match(
                inputs,
                release_root=release_root,
                release_manifest_path=release_manifest_path,
                operator_path=operator_path,
                recursive_dependencies=recursive_dependencies,
            )
        )
        non_authorizing = _surfaces_non_authorizing(
            summary,
            saved_decision,
            saved_config,
            _mapping(manifest.get("extra")),
        )
        sealed = bool(
            _bool(summary.get("sealed", False))
            and _bool(saved_decision.get("sealed", False))
            and _bool(saved_config.get("sealed", False))
            and _bool(_mapping(manifest.get("extra")).get("sealed", False))
        )
        verified = bool(
            integrity.passed
            and release_current
            and operator_current
            and artifacts_consistent
            and non_authorizing
            and sealed
        )
        ready = bool(verified and approved)
        error = (
            integrity.error
            or (
                "release_decision_artifacts_disagree_with_sources"
                if not artifacts_consistent
                else ""
            )
            or (
                "release_decision_authorization_claim_invalid"
                if not non_authorizing
                else ""
            )
            or ("release_decision_not_sealed" if not sealed else "")
        )
        return ProviderMarketDataImbalanceReleaseDecisionVerification(
            verified=verified,
            sealed=bool(verified and sealed),
            approved=bool(verified and approved),
            ready=ready,
            manifest_current=bool(integrity.passed),
            release_review_current=release_current,
            operator_decision_current=operator_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            release_review_dir=release_root,
            operator_decision_path=operator_path,
            error=error,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ProviderMarketDataImbalanceReleaseDecisionVerification(
            verified=False,
            sealed=False,
            approved=False,
            ready=False,
            manifest_current=bool(integrity.passed),
            release_review_current=False,
            operator_decision_current=False,
            artifacts_consistent=False,
            non_authorizing=False,
            output_dir=root,
            release_review_dir=release_root,
            operator_decision_path=operator_path,
            error=f"release_decision_unreadable:{exc}",
        )


def _decision_checks(
    *,
    release_verification: Any,
    release_summary: pd.Series,
    release_packet: Mapping[str, Any],
    operator_row: pd.Series,
    operator_path: Path,
    release_root: Path,
    recursive_dependency_count: int,
    config: ProviderMarketDataImbalanceReleaseDecisionConfig,
) -> pd.DataFrame:
    expected = _release_bindings(release_summary, release_packet)
    decision = _decision_value(operator_row)
    notes = _text(operator_row.get("notes"))
    checks = [
        _check("release_review_verified", "release_review", release_verification.verified, "is", True, release_verification.verified, "release review is not semantically verified"),
        _check("release_review_ready", "release_review", release_verification.ready, "is", True, release_verification.ready, "release review is not ready"),
        _check("release_review_manifest_current", "release_review", release_verification.manifest_current, "is", True, release_verification.manifest_current, "release-review manifest is stale"),
        _check("release_review_source_current", "release_review", release_verification.source_current, "is", True, release_verification.source_current, "release-review evidence source is stale"),
        _check("release_review_artifacts_consistent", "release_review", release_verification.artifacts_consistent, "is", True, release_verification.artifacts_consistent, "release-review artifacts disagree"),
        _check("release_review_non_authorizing", "safety", release_verification.non_authorizing, "is", True, release_verification.non_authorizing, "release review contains an authorization claim"),
        _check("release_review_operator_pending", "release_review", release_verification.operator_approval_pending, "is", True, release_verification.operator_approval_pending, "release review is not awaiting a separate decision"),
        _check("operator_decision_separate", "operator", str(operator_path), "outside", str(release_root), not _is_relative_to(operator_path, release_root), "operator decision must be retained outside the immutable release packet"),
        _check("decision_completed", "operator", decision, "in", "approved,rejected", decision in {"approved", "rejected"}, "operator decision must be approved or rejected"),
        _check("operator_id_present", "operator", _text(operator_row.get("operator_id")), "nonempty", True, bool(_text(operator_row.get("operator_id"))), "operator ID is required"),
        _check("operator_role_present", "operator", _text(operator_row.get("operator_role")), "nonempty", True, bool(_text(operator_row.get("operator_role"))), "operator role is required"),
        _check("reviewed_at_utc_valid", "operator", _text(operator_row.get("reviewed_at_utc")), "timezone_aware_iso8601", True, _timestamp_valid(operator_row.get("reviewed_at_utc")), "review timestamp must be timezone-aware ISO-8601"),
        _check("risk_limits_acknowledged", "attestation", operator_row.get("risk_limits_acknowledged", False), "is", True, _explicit_true(operator_row, "risk_limits_acknowledged"), "risk limits must be explicitly acknowledged"),
        _check("kill_switch_acknowledged", "attestation", operator_row.get("kill_switch_acknowledged", False), "is", True, _explicit_true(operator_row, "kill_switch_acknowledged"), "kill-switch access must be explicitly acknowledged"),
        _check("rollback_plan_acknowledged", "attestation", operator_row.get("rollback_plan_acknowledged", False), "is", True, _explicit_true(operator_row, "rollback_plan_acknowledged"), "rollback plan must be explicitly acknowledged"),
        _check("decision_non_authorizing", "safety", operator_row.get("authorizes_submission", "missing"), "is", False, _explicit_false(operator_row, "authorizes_submission"), "operator decision must explicitly remain non-authorizing"),
        _check("rejection_notes_present", "operator", notes, "nonempty_if_rejected", True, decision != "rejected" or bool(notes), "a rejected decision requires notes"),
        _check("recursive_dependency_limit", "integrity", recursive_dependency_count, "<=", config.max_dependency_count, recursive_dependency_count <= config.max_dependency_count, "release-review recursive dependency graph exceeds the decision limit"),
    ]
    binding_columns = (
        "release_review_id",
        "packet_sha256",
        "strategy_evidence_manifest_sha256",
        "catalog_manifest_sha256",
        "active_lineage_chain_audit_manifest_sha256",
        "broker_rehearsal_certificate_manifest_sha256",
    )
    for column in binding_columns:
        actual = _text(operator_row.get(column)).lower()
        expected_value = _text(expected[column]).lower()
        checks.append(
            _check(
                f"{column}_matches",
                "binding",
                actual,
                "==",
                expected_value,
                bool(actual) and actual == expected_value,
                f"operator decision does not bind {column}",
            )
        )
    identity_columns = ("strategy", "market", "target_mode")
    for column in identity_columns:
        actual = (
            _normalize_strategy(operator_row.get(column))
            if column == "strategy"
            else _identity(operator_row.get(column))
        )
        expected_value = (
            _normalize_strategy(expected[column])
            if column == "strategy"
            else _identity(expected[column])
        )
        checks.append(
            _check(
                f"{column}_matches",
                "identity",
                actual,
                "==",
                expected_value,
                bool(actual) and actual == expected_value,
                f"operator decision {column} differs from release review",
            )
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _release_bindings(
    release_summary: pd.Series,
    release_packet: Mapping[str, Any],
) -> dict[str, str]:
    identity = _mapping(release_packet.get("identity"))
    return {
        "release_review_id": _text(release_summary.get("release_review_id")),
        "packet_sha256": _text(release_summary.get("packet_sha256")).lower(),
        "strategy": _text(release_summary.get("strategy"))
        or _text(identity.get("strategy")),
        "market": _text(release_summary.get("market"))
        or _text(identity.get("market")),
        "target_mode": _text(release_summary.get("target_mode"))
        or _text(identity.get("target_mode")),
        "strategy_evidence_manifest_sha256": _text(
            release_summary.get("strategy_evidence_manifest_sha256")
        ).lower(),
        "catalog_manifest_sha256": _text(
            release_summary.get("catalog_manifest_sha256")
        ).lower(),
        "active_lineage_chain_audit_manifest_sha256": _text(
            release_summary.get(
                "active_lineage_chain_audit_manifest_sha256"
            )
        ).lower(),
        "broker_rehearsal_certificate_manifest_sha256": _text(
            release_summary.get(
                "broker_rehearsal_certificate_manifest_sha256"
            )
        ).lower(),
    }


def _proof_contract(
    *,
    release_root: Path,
    release_manifest_path: Path,
    release_manifest_sha256: str,
    release_summary: pd.Series,
    operator_path: Path,
    operator_decision_sha256: str,
) -> dict[str, Any]:
    bindings = _release_bindings(release_summary, {})
    return {
        "release_review": {
            "path": str(release_root),
            "manifest_path": str(release_manifest_path),
            "manifest_sha256": release_manifest_sha256,
            "release_review_id": bindings["release_review_id"],
            "packet_sha256": bindings["packet_sha256"],
        },
        "strategy_evidence": {
            "manifest_sha256": bindings[
                "strategy_evidence_manifest_sha256"
            ],
        },
        "catalog": {
            "manifest_sha256": bindings["catalog_manifest_sha256"],
        },
        "active_lineage_chain_audit": {
            "manifest_sha256": bindings[
                "active_lineage_chain_audit_manifest_sha256"
            ],
        },
        "broker_rehearsal_certificate": {
            "manifest_sha256": bindings[
                "broker_rehearsal_certificate_manifest_sha256"
            ],
        },
        "operator_decision": {
            "path": str(operator_path),
            "sha256": operator_decision_sha256,
        },
    }


def _decision_core(
    *,
    release_summary: pd.Series,
    operator_row: pd.Series,
    proof_contract: Mapping[str, Any],
) -> dict[str, Any]:
    decision = _decision_value(operator_row)
    approved = decision == "approved"
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": (
            "provider_market_data_imbalance_live_dryrun_release_decision"
        ),
        "status": (
            "sealed_approved_for_live_dryrun"
            if approved
            else "sealed_rejected"
        ),
        "sealed": True,
        "decision": decision,
        "approved_for_live_dryrun": approved,
        "identity": {
            "strategy": _text(release_summary.get("strategy")),
            "market": _text(release_summary.get("market")),
            "target_mode": _text(release_summary.get("target_mode")),
        },
        "proof_contract": proof_contract,
        "operator": {
            "operator_id": _text(operator_row.get("operator_id")),
            "operator_role": _text(operator_row.get("operator_role")),
            "reviewed_at_utc": _text(operator_row.get("reviewed_at_utc")),
            "risk_limits_acknowledged": True,
            "kill_switch_acknowledged": True,
            "rollback_plan_acknowledged": True,
            "notes": _text(operator_row.get("notes")),
        },
        "safety": {
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
        },
    }


def _proof_rows(proof_contract: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for component in (
        "release_review",
        "strategy_evidence",
        "catalog",
        "active_lineage_chain_audit",
        "broker_rehearsal_certificate",
        "operator_decision",
    ):
        proof = _mapping(proof_contract.get(component))
        digest = _text(
            proof.get("sha256") or proof.get("manifest_sha256")
        ).lower()
        rows.append(
            {
                "component": component,
                "path": _text(proof.get("path") or proof.get("manifest_path")),
                "kind": "file" if component == "operator_decision" else "sha256_binding",
                "sha256": digest,
                "digest_sha256": digest,
                "current": True,
            }
        )
    return pd.DataFrame(rows, columns=PROOF_COLUMNS)


def _summary(
    *,
    decision_id: str,
    decision_sha256: str,
    release_summary: pd.Series,
    operator_row: pd.Series,
    proof_contract: Mapping[str, Any],
    recursive_dependency_count: int,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    decision = _decision_value(operator_row)
    approved = decision == "approved" and failed_checks == 0
    return pd.DataFrame(
        [
            {
                "passed": failed_checks == 0,
                "sealed": failed_checks == 0,
                "ready": approved,
                "approved_for_live_dryrun": approved,
                "status": (
                    "sealed_approved_for_live_dryrun"
                    if approved
                    else "sealed_rejected"
                ),
                "decision": decision,
                "failed_checks": failed_checks,
                "decision_id": decision_id,
                "decision_sha256": decision_sha256,
                "release_review_id": _text(
                    release_summary.get("release_review_id")
                ),
                "release_review_manifest_sha256": _mapping(
                    proof_contract.get("release_review")
                ).get("manifest_sha256", ""),
                "packet_sha256": _text(
                    release_summary.get("packet_sha256")
                ),
                "operator_decision_sha256": _mapping(
                    proof_contract.get("operator_decision")
                ).get("sha256", ""),
                "strategy": _text(release_summary.get("strategy")),
                "market": _text(release_summary.get("market")),
                "target_mode": _text(release_summary.get("target_mode")),
                "strategy_evidence_manifest_sha256": _text(
                    release_summary.get(
                        "strategy_evidence_manifest_sha256"
                    )
                ),
                "catalog_manifest_sha256": _text(
                    release_summary.get("catalog_manifest_sha256")
                ),
                "active_lineage_chain_audit_manifest_sha256": _text(
                    release_summary.get(
                        "active_lineage_chain_audit_manifest_sha256"
                    )
                ),
                "broker_rehearsal_certificate_manifest_sha256": _text(
                    release_summary.get(
                        "broker_rehearsal_certificate_manifest_sha256"
                    )
                ),
                "operator_id": _text(operator_row.get("operator_id")),
                "operator_role": _text(operator_row.get("operator_role")),
                "reviewed_at_utc": _text(
                    operator_row.get("reviewed_at_utc")
                ),
                "risk_limits_acknowledged": True,
                "kill_switch_acknowledged": True,
                "rollback_plan_acknowledged": True,
                "recursive_dependency_count": recursive_dependency_count,
                "release_approved": False,
                "dry_run_only": True,
                "submission_enabled": False,
                "broker_api_called": False,
                "authorizes_submission": False,
                "recommendation": (
                    "prepare_controlled_live_dryrun_handoff"
                    if approved
                    else "resolve_operator_rejection"
                ),
                "next_gate": (
                    "controlled_live_dryrun_handoff"
                    if approved
                    else "operator_re_review"
                ),
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderMarketDataImbalanceReleaseDecisionConfig,
    decision_id: str,
    decision_sha256: str,
    release_root: Path,
    operator_path: Path,
    proof_contract: Mapping[str, Any],
    approved: bool,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "decision_id": decision_id,
        "decision_sha256": decision_sha256,
        "release_review_dir": str(release_root),
        "operator_decision_path": str(operator_path),
        "proof_contract": proof_contract,
        "sealed": True,
        "approved_for_live_dryrun": approved,
        "dry_run_only": True,
        "submission_enabled": False,
        "broker_api_called": False,
        "authorizes_submission": False,
    }


def _manifest_extra(
    *,
    decision_id: str,
    decision_sha256: str,
    release_summary: pd.Series,
    proof_contract: Mapping[str, Any],
    approved: bool,
) -> dict[str, Any]:
    return {
        "passed": True,
        "sealed": True,
        "ready": approved,
        "approved_for_live_dryrun": approved,
        "decision": "approved" if approved else "rejected",
        "decision_id": decision_id,
        "decision_sha256": decision_sha256,
        "release_review_id": _text(
            release_summary.get("release_review_id")
        ),
        "release_review_manifest_sha256": _mapping(
            proof_contract.get("release_review")
        ).get("manifest_sha256", ""),
        "packet_sha256": _text(release_summary.get("packet_sha256")),
        "operator_decision_sha256": _mapping(
            proof_contract.get("operator_decision")
        ).get("sha256", ""),
        "strategy": _text(release_summary.get("strategy")),
        "market": _text(release_summary.get("market")),
        "target_mode": _text(release_summary.get("target_mode")),
        "release_approved": False,
        "dry_run_only": True,
        "submission_enabled": False,
        "broker_api_called": False,
        "authorizes_submission": False,
    }


def _runbook_markdown(
    summary: pd.Series,
    proof_contract: Mapping[str, Any],
) -> str:
    approved = _bool(summary.get("approved_for_live_dryrun", False))
    return "\n".join(
        [
            "# Provider Live-Dry-Run Release Decision",
            "",
            "## Sealed State",
            "",
            f"- Decision ID: `{summary['decision_id']}`",
            f"- Decision: `{summary['decision']}`",
            f"- Strategy: `{summary['strategy']}`",
            f"- Market: `{summary['market']}`",
            f"- Target mode: `{summary['target_mode']}`",
            "- Risk limits acknowledged: yes",
            "- Kill-switch access acknowledged: yes",
            "- Rollback plan acknowledged: yes",
            "- Authorizes broker submission: no",
            "",
            "## Proof Bindings",
            "",
            f"- Release-review manifest: `{summary['release_review_manifest_sha256']}`",
            f"- Release packet: `{summary['packet_sha256']}`",
            f"- Operator decision: `{summary['operator_decision_sha256']}`",
            f"- Strategy evidence: `{summary['strategy_evidence_manifest_sha256']}`",
            f"- Catalog manifest: `{summary['catalog_manifest_sha256']}`",
            f"- Active-lineage audit manifest: `{summary['active_lineage_chain_audit_manifest_sha256']}`",
            f"- Rehearsal certificate manifest: `{summary['broker_rehearsal_certificate_manifest_sha256']}`",
            "",
            "## Next Step",
            "",
            (
                "The operator approved a controlled live-dry-run handoff. "
                "This artifact remains non-submitting and cannot place orders."
                if approved
                else "The operator rejected this handoff. Repair the stated concerns and prepare a new release-review packet."
            ),
            "",
            f"- Release review: `{_mapping(proof_contract.get('release_review')).get('path', '')}`",
            f"- Operator decision: `{_mapping(proof_contract.get('operator_decision')).get('path', '')}`",
            "",
        ]
    )


def _surfaces_non_authorizing(
    summary: pd.Series,
    decision: Mapping[str, Any],
    config: Mapping[str, Any],
    manifest_extra: Mapping[str, Any],
) -> bool:
    safety = _mapping(decision.get("safety"))
    return bool(
        _explicit_false(summary, "authorizes_submission")
        and _explicit_false(summary, "release_approved")
        and _explicit_false(summary, "submission_enabled")
        and _explicit_false(summary, "broker_api_called")
        and _bool(summary.get("dry_run_only", False))
        and _explicit_false(safety, "authorizes_submission")
        and _explicit_false(safety, "submission_enabled")
        and _explicit_false(safety, "broker_api_called")
        and _bool(safety.get("dry_run_only", False))
        and _explicit_false(config, "authorizes_submission")
        and _explicit_false(config, "submission_enabled")
        and _explicit_false(config, "broker_api_called")
        and _bool(config.get("dry_run_only", False))
        and _explicit_false(manifest_extra, "authorizes_submission")
        and _explicit_false(manifest_extra, "release_approved")
        and _explicit_false(manifest_extra, "submission_enabled")
        and _explicit_false(manifest_extra, "broker_api_called")
        and _bool(manifest_extra.get("dry_run_only", False))
    )


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    release_root: Path,
    release_manifest_path: Path,
    operator_path: Path,
    recursive_dependencies: list[Path],
) -> bool:
    expected_names = {
        "release_review",
        "release_review_manifest",
        "operator_decision",
    }
    if recursive_dependencies:
        expected_names.add("release_review_recursive_dependencies")
    if set(inputs) != expected_names:
        return False
    direct = {
        "release_review": (release_root, "directory"),
        "release_review_manifest": (release_manifest_path, "file"),
        "operator_decision": (operator_path, "file"),
    }
    for name, (expected, expected_kind) in direct.items():
        record = _mapping(inputs.get(name))
        if (
            record.get("kind") != expected_kind
            or not _text(record.get("path"))
        ):
            return False
        if Path(str(record["path"])).resolve() != expected:
            return False
    if recursive_dependencies:
        actual = {
            path.resolve()
            for path in _fingerprint_paths(
                inputs.get("release_review_recursive_dependencies")
            )
        }
        expected = {path.resolve() for path in recursive_dependencies}
        if actual != expected or len(
            _fingerprint_paths(
                inputs.get("release_review_recursive_dependencies")
            )
        ) != len(recursive_dependencies):
            return False
    return True


def _fingerprint_paths(value: Any) -> list[Path]:
    if isinstance(value, Mapping):
        if value.get("kind") in {"file", "directory"} and _text(
            value.get("path")
        ):
            return [Path(str(value["path"]))]
        paths: list[Path] = []
        for item in value.values():
            paths.extend(_fingerprint_paths(item))
        return paths
    if isinstance(value, list):
        paths = []
        for item in value:
            paths.extend(_fingerprint_paths(item))
        return paths
    return []


def _recursive_dependencies(
    release_manifest_path: Path,
    direct_paths: set[Path],
) -> list[Path]:
    return _unique_paths(
        [
            path
            for path in manifest_dependency_paths(release_manifest_path)
            if path.resolve() not in direct_paths
        ]
    )


def _require_operator_columns(frame: pd.DataFrame) -> None:
    missing = [name for name in OPERATOR_DECISION_COLUMNS if name not in frame]
    if missing:
        raise ValueError(
            "operator decision is missing required columns: "
            + ", ".join(missing)
        )


def _decision_value(row: pd.Series) -> str:
    return _identity(row.get("decision"))


def _timestamp_valid(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return offset is not None and offset.total_seconds() == 0


def _reject_output_collision(
    out: Path,
    *,
    release_root: Path,
    operator_path: Path,
) -> None:
    if out == release_root or _is_relative_to(out, release_root):
        raise ValueError(
            "release-decision output must be outside the release-review packet"
        )
    if operator_path == out or _is_relative_to(operator_path, out):
        raise ValueError(
            "operator decision must be outside the release-decision output"
        )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _unique_paths(paths: list[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for path in paths:
        resolved = path.resolve()
        found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)]


def _validate_config(
    config: ProviderMarketDataImbalanceReleaseDecisionConfig,
) -> None:
    if config.max_dependency_count <= 0:
        raise ValueError("max_dependency_count must be positive")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if frame.empty:
        raise ValueError(f"{label} is empty: {path}")
    return frame


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


def _check(
    name: str,
    component: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "component": component,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _dataframe_records_equal(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
) -> bool:
    if list(actual.columns) != list(expected.columns) or len(actual) != len(
        expected
    ):
        return False
    for actual_row, expected_row in zip(
        actual.itertuples(index=False, name=None),
        expected.itertuples(index=False, name=None),
    ):
        for actual_value, expected_value in zip(actual_row, expected_row):
            actual_missing = _artifact_value_missing(actual_value)
            expected_missing = _artifact_value_missing(expected_value)
            if actual_missing or expected_missing:
                if actual_missing != expected_missing:
                    return False
                continue
            if isinstance(
                actual_value,
                (int, float, np.integer, np.floating),
            ) and isinstance(
                expected_value,
                (int, float, np.integer, np.floating),
            ):
                if float(actual_value) != float(expected_value):
                    return False
            elif str(actual_value) != str(expected_value):
                return False
    return True


def _artifact_value_missing(value: Any) -> bool:
    if value is None or (
        isinstance(value, str) and value.strip().lower() in {"", "nan"}
    ):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _explicit_true(value: Mapping[str, Any] | pd.Series, key: str) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        try:
            numeric = float(raw)
            return not bool(np.isnan(numeric)) and numeric == 1.0
        except (TypeError, ValueError):
            return False
    return _text(raw).lower() in {"1", "true", "yes"}


def _explicit_false(value: Mapping[str, Any] | pd.Series, key: str) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return not bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        try:
            numeric = float(raw)
            return not bool(np.isnan(numeric)) and numeric == 0.0
        except (TypeError, ValueError):
            return False
    return _text(raw).lower() in {
        "0",
        "false",
        "fail",
        "failed",
        "n",
        "no",
        "off",
    }


def _valid_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return bool(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text)
    )


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _identity(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _normalize_strategy(value: Any) -> str:
    identity = _identity(value)
    aliases = {
        "microprice_imbalance": "imbalance",
        "provider_market_data_imbalance": "imbalance",
    }
    return aliases.get(identity, identity)


def _bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            return bool(float(value)) and not bool(np.isnan(float(value)))
        except (TypeError, ValueError):
            return False
    return _text(value).lower() in {
        "1",
        "true",
        "yes",
        "y",
        "pass",
        "passed",
    }


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
        return float(value)
    return value
