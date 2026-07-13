from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from reports.evidence import verify_strategy_evidence_review
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "provider_market_data_imbalance_release_review"
SOURCE_RUN_TYPE = "strategy_evidence_review"
CONTRACT_VERSION = "provider_market_data_imbalance_release_review/v1"
PROVIDER_EVIDENCE_PROFILE = "provider_imbalance_ops_launch"
CERTIFICATE_RUN_TYPE = (
    "provider_market_data_imbalance_broker_rehearsal_certificate"
)
SOURCE_INPUTS = (
    "catalog",
    "source_catalog_manifest",
    "selected_provider_active_lineage_chain_audit",
    "selected_provider_active_lineage_chain_audit_manifest",
    "selected_provider_broker_rehearsal_certificate",
    "selected_provider_broker_rehearsal_certificate_manifest",
)
RELEASE_REVIEW_ARTIFACTS = (
    "provider_market_data_imbalance_release_review_checks.csv",
    "provider_market_data_imbalance_release_review_proofs.csv",
    "provider_market_data_imbalance_release_review_operator_approval_template.csv",
    "provider_market_data_imbalance_release_review_action_queue.csv",
    "provider_market_data_imbalance_release_review_summary.csv",
    "provider_market_data_imbalance_release_review_packet.json",
    "provider_market_data_imbalance_release_review_config.json",
    "provider_market_data_imbalance_release_review_runbook.md",
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
    "tree_sha256",
    "digest_sha256",
    "current",
)
ACTION_COLUMNS = (
    "priority",
    "queue_status",
    "component",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
)
OPERATOR_APPROVAL_COLUMNS = (
    "release_review_id",
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


@dataclass(frozen=True)
class ProviderMarketDataImbalanceReleaseReviewConfig:
    target_mode: str = "live_dryrun"
    max_dependency_count: int = 1024


@dataclass(frozen=True)
class ProviderMarketDataImbalanceReleaseReviewReport:
    checks: pd.DataFrame
    proofs: pd.DataFrame
    operator_approval: pd.DataFrame
    action_queue: pd.DataFrame
    summary: pd.DataFrame
    packet: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("ready", False))
        )


@dataclass(frozen=True)
class ProviderMarketDataImbalanceReleaseReviewVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    source_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    operator_approval_pending: bool
    output_dir: Path
    strategy_evidence_dir: Path | None
    error: str = ""


def write_provider_market_data_imbalance_release_review(
    strategy_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceReleaseReviewConfig | None = None,
) -> ProviderMarketDataImbalanceReleaseReviewReport:
    config = config or ProviderMarketDataImbalanceReleaseReviewConfig()
    _validate_config(config)
    source_root = Path(strategy_evidence_dir).resolve()
    source_manifest_path = source_root / MANIFEST_NAME
    out = Path(output_dir).resolve()

    verification = verify_strategy_evidence_review(source_root)
    if not verification.verified or not verification.ready:
        raise ValueError(
            "provider release review requires a verified and ready strategy "
            f"evidence root: {verification.error or 'source_not_ready'}"
        )

    source_manifest = _read_json(source_manifest_path, "strategy evidence manifest")
    if _text(source_manifest.get("run_type")) != SOURCE_RUN_TYPE:
        raise ValueError(
            "provider release review requires a strategy evidence review "
            "manifest"
        )
    source_manifest_sha256 = file_sha256(source_manifest_path)
    source_summary = _single_row(
        verification.summary,
        "strategy evidence summary",
    )
    input_records = {
        name: _required_input(source_manifest, name) for name in SOURCE_INPUTS
    }
    catalog_path = Path(input_records["catalog"]["path"]).resolve()
    catalog = _read_csv(catalog_path, "strategy evidence catalog")
    certificate_dir = Path(
        input_records["selected_provider_broker_rehearsal_certificate"]["path"]
    ).resolve()
    audit_dir = Path(
        input_records["selected_provider_active_lineage_chain_audit"]["path"]
    ).resolve()
    certificate_row = _selected_certificate_row(
        catalog,
        catalog_path,
        certificate_dir,
    )
    target_mode = _identity(certificate_row.get("summary_target_mode", ""))
    strategy = _text(source_summary.get("strategy")) or _text(
        certificate_row.get("summary_strategy")
    )
    market = _text(source_summary.get("market")) or _text(
        certificate_row.get("summary_market")
    )
    certificate_sha256 = _text(
        certificate_row.get("summary_certificate_sha256")
    ).lower()
    certificate_cycle_id = _text(certificate_row.get("summary_cycle_id"))
    chain_digest_sha256 = _text(
        source_summary.get(
            "selected_provider_active_lineage_chain_audit_chain_digest_sha256"
        )
    ).lower()
    lineage_contract_sha256 = _text(
        source_summary.get("provider_lineage_selection_contract_sha256")
    ).lower()

    direct_paths = {
        source_root,
        source_manifest_path,
        *(Path(str(record["path"])).resolve() for record in input_records.values()),
    }
    recursive_dependencies = [
        path
        for path in manifest_dependency_paths(source_manifest_path)
        if path.resolve() not in direct_paths
    ]
    recursive_dependencies = _unique_paths(recursive_dependencies)
    _reject_output_collision(
        out,
        source_root=source_root,
        catalog_path=catalog_path,
        audit_dir=audit_dir,
        certificate_dir=certificate_dir,
    )

    checks = _release_checks(
        verification=verification,
        source_summary=source_summary,
        input_records=input_records,
        catalog_path=catalog_path,
        audit_dir=audit_dir,
        certificate_dir=certificate_dir,
        certificate_row=certificate_row,
        strategy=strategy,
        market=market,
        target_mode=target_mode,
        certificate_sha256=certificate_sha256,
        chain_digest_sha256=chain_digest_sha256,
        lineage_contract_sha256=lineage_contract_sha256,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    failed_checks = checks.loc[~checks["passed"].map(_bool), "check"].astype(str).tolist()
    if failed_checks:
        raise ValueError(
            "provider release review source contract failed: "
            + ", ".join(failed_checks)
        )

    proof_contract = _proof_contract(
        source_root=source_root,
        source_manifest_path=source_manifest_path,
        source_manifest_sha256=source_manifest_sha256,
        input_records=input_records,
        chain_digest_sha256=chain_digest_sha256,
        lineage_contract_sha256=lineage_contract_sha256,
        certificate_sha256=certificate_sha256,
        certificate_cycle_id=certificate_cycle_id,
    )
    packet_core = _packet_core(
        strategy=strategy,
        market=market,
        target_mode=target_mode,
        source_root=source_root,
        source_manifest_sha256=source_manifest_sha256,
        proof_contract=proof_contract,
    )
    packet_sha256 = _canonical_sha256(packet_core)
    release_review_id = f"provider-release-review-{packet_sha256[:24]}"
    packet = {
        **packet_core,
        "release_review_id": release_review_id,
        "packet_sha256": packet_sha256,
    }
    proofs = _proof_rows(
        source_manifest_path=source_manifest_path,
        source_manifest_sha256=source_manifest_sha256,
        input_records=input_records,
        chain_digest_sha256=chain_digest_sha256,
        lineage_contract_sha256=lineage_contract_sha256,
        certificate_sha256=certificate_sha256,
    )
    operator_approval = _operator_approval_template(
        release_review_id=release_review_id,
        strategy=strategy,
        market=market,
        target_mode=target_mode,
        source_manifest_sha256=source_manifest_sha256,
        proof_contract=proof_contract,
    )
    action_queue = _action_queue(source_root)
    summary = _summary(
        release_review_id=release_review_id,
        packet_sha256=packet_sha256,
        strategy=strategy,
        market=market,
        target_mode=target_mode,
        source_root=source_root,
        source_manifest_sha256=source_manifest_sha256,
        proof_contract=proof_contract,
        recursive_dependency_count=len(recursive_dependencies),
        checks=checks,
        action_queue=action_queue,
    )
    config_payload = {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "release_review_id": release_review_id,
        "packet_sha256": packet_sha256,
        "strategy_evidence_dir": str(source_root),
        "proof_contract": proof_contract,
        "operator_approval_status": "pending",
        "operator_approved": False,
        "submission_enabled": False,
        "broker_api_called": False,
        "authorizes_submission": False,
    }

    out.mkdir(parents=True, exist_ok=True)
    checks.to_csv(
        out / "provider_market_data_imbalance_release_review_checks.csv",
        index=False,
    )
    proofs.to_csv(
        out / "provider_market_data_imbalance_release_review_proofs.csv",
        index=False,
    )
    operator_approval.to_csv(
        out
        / "provider_market_data_imbalance_release_review_operator_approval_template.csv",
        index=False,
    )
    action_queue.to_csv(
        out / "provider_market_data_imbalance_release_review_action_queue.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_market_data_imbalance_release_review_summary.csv",
        index=False,
    )
    (out / "provider_market_data_imbalance_release_review_packet.json").write_text(
        json.dumps(_jsonable(packet), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_release_review_config.json").write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_release_review_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], proof_contract, source_root),
        encoding="utf-8",
    )

    final_verification = verify_strategy_evidence_review(source_root)
    if (
        not final_verification.verified
        or not final_verification.ready
        or file_sha256(source_manifest_path) != source_manifest_sha256
    ):
        raise RuntimeError(
            "strategy evidence changed while preparing the release review"
        )

    manifest_inputs: dict[str, Any] = {
        "strategy_evidence": source_root,
        "strategy_evidence_manifest": source_manifest_path,
        **{
            name: Path(str(record["path"]))
            for name, record in input_records.items()
        },
    }
    if recursive_dependencies:
        manifest_inputs["strategy_evidence_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra={
            "ready": True,
            "ready_for_operator_review": True,
            "operator_approval_required": True,
            "operator_approval_status": "pending",
            "operator_approved": False,
            "release_approved": False,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
            "release_review_id": release_review_id,
            "packet_sha256": packet_sha256,
            "strategy": strategy,
            "market": market,
            "target_mode": target_mode,
            "strategy_evidence_manifest_sha256": source_manifest_sha256,
            "catalog_manifest_sha256": proof_contract["catalog"][
                "manifest_sha256"
            ],
            "active_lineage_chain_audit_manifest_sha256": proof_contract[
                "active_lineage_chain_audit"
            ]["manifest_sha256"],
            "broker_rehearsal_certificate_manifest_sha256": proof_contract[
                "broker_rehearsal_certificate"
            ]["manifest_sha256"],
        },
    )
    return ProviderMarketDataImbalanceReleaseReviewReport(
        checks=checks,
        proofs=proofs,
        operator_approval=operator_approval,
        action_queue=action_queue,
        summary=summary,
        packet=packet,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_release_review(
    release_review_dir: str | Path,
) -> ProviderMarketDataImbalanceReleaseReviewVerification:
    candidate = Path(release_review_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=RELEASE_REVIEW_ARTIFACTS,
        require_input_fingerprints=True,
    )
    source_root: Path | None = None
    try:
        manifest = _read_json(manifest_path, "release-review manifest")
        checks_frame = _read_csv(
            root / "provider_market_data_imbalance_release_review_checks.csv",
            "release-review checks",
        )
        summary_frame = _read_csv(
            root / "provider_market_data_imbalance_release_review_summary.csv",
            "release-review summary",
        )
        summary = _single_row(
            summary_frame,
            "release-review summary",
        )
        packet = _read_json(
            root / "provider_market_data_imbalance_release_review_packet.json",
            "release-review packet",
        )
        saved_config = _read_json(
            root / "provider_market_data_imbalance_release_review_config.json",
            "release-review config",
        )
        proofs_frame = _read_csv(
            root / "provider_market_data_imbalance_release_review_proofs.csv",
            "release-review proof inventory",
        )
        action_queue_frame = _read_csv(
            root
            / "provider_market_data_imbalance_release_review_action_queue.csv",
            "release-review action queue",
        )
        operator_approval_frame = _read_csv(
            root
            / "provider_market_data_imbalance_release_review_operator_approval_template.csv",
            "release-review operator approval template",
        )
        operator_approval = _single_row(
            operator_approval_frame,
            "release-review operator approval template",
        )
        runbook = (
            root / "provider_market_data_imbalance_release_review_runbook.md"
        ).read_text(encoding="utf-8")
        source_record = _mapping(_mapping(manifest.get("inputs")).get("strategy_evidence"))
        if source_record.get("kind") != "directory" or not _text(
            source_record.get("path")
        ):
            raise ValueError("release-review strategy_evidence input is invalid")
        source_root = Path(str(source_record["path"])).resolve()
        source_verification = verify_strategy_evidence_review(source_root)
        source_current = bool(
            source_verification.verified and source_verification.ready
        )
        if not source_current:
            return ProviderMarketDataImbalanceReleaseReviewVerification(
                verified=False,
                ready=False,
                manifest_current=bool(integrity.passed),
                source_current=False,
                artifacts_consistent=False,
                non_authorizing=_release_surfaces_non_authorizing(
                    summary,
                    packet,
                    saved_config,
                    operator_approval,
                    manifest,
                ),
                operator_approval_pending=_operator_approval_is_pending(
                    summary,
                    packet,
                    saved_config,
                    operator_approval,
                    manifest,
                ),
                output_dir=root,
                strategy_evidence_dir=source_root,
                error=(
                    "release_review_source_not_current:"
                    f"{source_verification.error or 'source_not_ready'}"
                ),
            )

        source_manifest_path = source_root / MANIFEST_NAME
        source_manifest = _read_json(
            source_manifest_path,
            "strategy evidence manifest",
        )
        if _text(source_manifest.get("run_type")) != SOURCE_RUN_TYPE:
            raise ValueError(
                "release-review source manifest is not strategy evidence"
            )
        source_manifest_sha256 = file_sha256(source_manifest_path)
        source_summary = _single_row(
            source_verification.summary,
            "strategy evidence summary",
        )
        input_records = {
            name: _required_input(source_manifest, name)
            for name in SOURCE_INPUTS
        }
        catalog_path = Path(input_records["catalog"]["path"]).resolve()
        certificate_dir = Path(
            input_records[
                "selected_provider_broker_rehearsal_certificate"
            ]["path"]
        ).resolve()
        catalog = _read_csv(catalog_path, "strategy evidence catalog")
        certificate_row = _selected_certificate_row(
            catalog,
            catalog_path,
            certificate_dir,
        )
        strategy = _text(source_summary.get("strategy")) or _text(
            certificate_row.get("summary_strategy")
        )
        market = _text(source_summary.get("market")) or _text(
            certificate_row.get("summary_market")
        )
        target_mode = _identity(
            certificate_row.get("summary_target_mode", "")
        )
        proof_contract = _proof_contract(
            source_root=source_root,
            source_manifest_path=source_manifest_path,
            source_manifest_sha256=source_manifest_sha256,
            input_records=input_records,
            chain_digest_sha256=_text(
                source_summary.get(
                    "selected_provider_active_lineage_chain_audit_chain_digest_sha256"
                )
            ).lower(),
            lineage_contract_sha256=_text(
                source_summary.get(
                    "provider_lineage_selection_contract_sha256"
                )
            ).lower(),
            certificate_sha256=_text(
                certificate_row.get("summary_certificate_sha256")
            ).lower(),
            certificate_cycle_id=_text(
                certificate_row.get("summary_cycle_id")
            ),
        )
        expected_core = _packet_core(
            strategy=strategy,
            market=market,
            target_mode=target_mode,
            source_root=source_root,
            source_manifest_sha256=source_manifest_sha256,
            proof_contract=proof_contract,
        )
        packet_sha256 = _canonical_sha256(expected_core)
        release_review_id = f"provider-release-review-{packet_sha256[:24]}"
        expected_packet = {
            **expected_core,
            "release_review_id": release_review_id,
            "packet_sha256": packet_sha256,
        }
        expected_proofs = _proof_rows(
            source_manifest_path=source_manifest_path,
            source_manifest_sha256=source_manifest_sha256,
            input_records=input_records,
            chain_digest_sha256=proof_contract[
                "active_lineage_chain_audit"
            ]["chain_digest_sha256"],
            lineage_contract_sha256=proof_contract[
                "active_lineage_chain_audit"
            ]["provider_lineage_selection_contract_sha256"],
            certificate_sha256=proof_contract[
                "broker_rehearsal_certificate"
            ]["certificate_sha256"],
        )
        expected_operator_approval = _operator_approval_template(
            release_review_id=release_review_id,
            strategy=strategy,
            market=market,
            target_mode=target_mode,
            source_manifest_sha256=source_manifest_sha256,
            proof_contract=proof_contract,
        )
        expected_action_queue = _action_queue(source_root)
        manifest_settings = dict(
            _mapping(
                _mapping(manifest.get("parameters")).get("config")
            )
        )
        review_config = ProviderMarketDataImbalanceReleaseReviewConfig(
            **manifest_settings
        )
        _validate_config(review_config)
        audit_dir = Path(
            input_records[
                "selected_provider_active_lineage_chain_audit"
            ]["path"]
        ).resolve()
        direct_paths = {
            source_root,
            source_manifest_path,
            *(
                Path(str(record["path"])).resolve()
                for record in input_records.values()
            ),
        }
        recursive_dependencies = _unique_paths(
            [
                path
                for path in manifest_dependency_paths(source_manifest_path)
                if path.resolve() not in direct_paths
            ]
        )
        expected_checks = _release_checks(
            verification=source_verification,
            source_summary=source_summary,
            input_records=input_records,
            catalog_path=catalog_path,
            audit_dir=audit_dir,
            certificate_dir=certificate_dir,
            certificate_row=certificate_row,
            strategy=strategy,
            market=market,
            target_mode=target_mode,
            certificate_sha256=proof_contract[
                "broker_rehearsal_certificate"
            ]["certificate_sha256"],
            chain_digest_sha256=proof_contract[
                "active_lineage_chain_audit"
            ]["chain_digest_sha256"],
            lineage_contract_sha256=proof_contract[
                "active_lineage_chain_audit"
            ]["provider_lineage_selection_contract_sha256"],
            recursive_dependency_count=len(recursive_dependencies),
            config=review_config,
        )
        expected_summary = _summary(
            release_review_id=release_review_id,
            packet_sha256=packet_sha256,
            strategy=strategy,
            market=market,
            target_mode=target_mode,
            source_root=source_root,
            source_manifest_sha256=source_manifest_sha256,
            proof_contract=proof_contract,
            recursive_dependency_count=len(recursive_dependencies),
            checks=expected_checks,
            action_queue=expected_action_queue,
        )
        expected_saved_config = {
            "contract_version": CONTRACT_VERSION,
            "settings": asdict(review_config),
            "release_review_id": release_review_id,
            "packet_sha256": packet_sha256,
            "strategy_evidence_dir": str(source_root),
            "proof_contract": proof_contract,
            "operator_approval_status": "pending",
            "operator_approved": False,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
        }
        expected_runbook = _runbook_markdown(
            expected_summary.iloc[0],
            proof_contract,
            source_root,
        )
        expected_manifest_extra = {
            "ready": True,
            "ready_for_operator_review": True,
            "operator_approval_required": True,
            "operator_approval_status": "pending",
            "operator_approved": False,
            "release_approved": False,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
            "release_review_id": release_review_id,
            "packet_sha256": packet_sha256,
            "strategy": strategy,
            "market": market,
            "target_mode": target_mode,
            "strategy_evidence_manifest_sha256": source_manifest_sha256,
            "catalog_manifest_sha256": proof_contract["catalog"][
                "manifest_sha256"
            ],
            "active_lineage_chain_audit_manifest_sha256": proof_contract[
                "active_lineage_chain_audit"
            ]["manifest_sha256"],
            "broker_rehearsal_certificate_manifest_sha256": proof_contract[
                "broker_rehearsal_certificate"
            ]["manifest_sha256"],
        }
        manifest_extra = _mapping(manifest.get("extra"))
        artifacts_consistent = bool(
            packet == expected_packet
            and saved_config == expected_saved_config
            and _dataframe_records_equal(checks_frame, expected_checks)
            and _dataframe_records_equal(summary_frame, expected_summary)
            and _dataframe_records_equal(proofs_frame, expected_proofs)
            and _dataframe_records_equal(
                operator_approval_frame,
                expected_operator_approval,
            )
            and _dataframe_records_equal(
                action_queue_frame,
                expected_action_queue,
            )
            and runbook == expected_runbook
            and dict(manifest_extra) == expected_manifest_extra
            and _text(summary.get("release_review_id")) == release_review_id
            and _text(summary.get("packet_sha256")) == packet_sha256
            and _normalize_strategy(summary.get("strategy"))
            == _normalize_strategy(strategy)
            and _identity(summary.get("market")) == _identity(market)
            and _identity(summary.get("target_mode")) == target_mode
            and _text(summary.get("strategy_evidence_manifest_sha256"))
            == source_manifest_sha256
            and _text(summary.get("catalog_sha256"))
            == proof_contract["catalog"]["sha256"]
            and _text(summary.get("catalog_manifest_sha256"))
            == proof_contract["catalog"]["manifest_sha256"]
            and _text(
                summary.get("active_lineage_chain_audit_tree_sha256")
            )
            == proof_contract["active_lineage_chain_audit"]["tree_sha256"]
            and _text(
                summary.get(
                    "active_lineage_chain_audit_manifest_sha256"
                )
            )
            == proof_contract["active_lineage_chain_audit"][
                "manifest_sha256"
            ]
            and _text(summary.get("active_lineage_chain_digest_sha256"))
            == proof_contract["active_lineage_chain_audit"][
                "chain_digest_sha256"
            ]
            and _text(
                summary.get(
                    "provider_lineage_selection_contract_sha256"
                )
            )
            == proof_contract["active_lineage_chain_audit"][
                "provider_lineage_selection_contract_sha256"
            ]
            and _text(
                summary.get(
                    "broker_rehearsal_certificate_tree_sha256"
                )
            )
            == proof_contract["broker_rehearsal_certificate"]["tree_sha256"]
            and _text(
                summary.get(
                    "broker_rehearsal_certificate_manifest_sha256"
                )
            )
            == proof_contract["broker_rehearsal_certificate"][
                "manifest_sha256"
            ]
            and _text(summary.get("broker_rehearsal_certificate_sha256"))
            == proof_contract["broker_rehearsal_certificate"][
                "certificate_sha256"
            ]
            and _text(operator_approval.get("release_review_id"))
            == release_review_id
            and _normalize_strategy(operator_approval.get("strategy"))
            == _normalize_strategy(strategy)
            and _identity(operator_approval.get("market"))
            == _identity(market)
            and _identity(operator_approval.get("target_mode"))
            == target_mode
            and _text(
                operator_approval.get(
                    "strategy_evidence_manifest_sha256"
                )
            )
            == source_manifest_sha256
            and _text(
                operator_approval.get("catalog_manifest_sha256")
            )
            == proof_contract["catalog"]["manifest_sha256"]
            and _text(
                operator_approval.get(
                    "active_lineage_chain_audit_manifest_sha256"
                )
            )
            == proof_contract["active_lineage_chain_audit"][
                "manifest_sha256"
            ]
            and _text(
                operator_approval.get(
                    "broker_rehearsal_certificate_manifest_sha256"
                )
            )
            == proof_contract["broker_rehearsal_certificate"][
                "manifest_sha256"
            ]
            and _text(manifest_extra.get("release_review_id"))
            == release_review_id
            and _text(manifest_extra.get("packet_sha256"))
            == packet_sha256
            and _normalize_strategy(manifest_extra.get("strategy"))
            == _normalize_strategy(strategy)
            and _identity(manifest_extra.get("market")) == _identity(market)
            and _identity(manifest_extra.get("target_mode"))
            == target_mode
            and _text(
                manifest_extra.get("strategy_evidence_manifest_sha256")
            )
            == source_manifest_sha256
        )
        non_authorizing = _release_surfaces_non_authorizing(
            summary,
            packet,
            saved_config,
            operator_approval,
            manifest,
        )
        operator_pending = _operator_approval_is_pending(
            summary,
            packet,
            saved_config,
            operator_approval,
            manifest,
        )
        ready = bool(
            _bool(summary.get("ready_for_operator_review", False))
            and _bool(summary.get("ready", False))
            and _identity(summary.get("target_mode")) == "live_dryrun"
        )
        verified = bool(
            integrity.passed
            and source_current
            and artifacts_consistent
            and non_authorizing
            and operator_pending
            and ready
        )
        error = (
            integrity.error
            or (
                "release_review_artifacts_disagree_with_source"
                if not artifacts_consistent
                else ""
            )
            or (
                "release_review_authorization_claim_invalid"
                if not non_authorizing
                else ""
            )
            or (
                "release_review_operator_approval_not_pending"
                if not operator_pending
                else ""
            )
            or ("release_review_not_ready" if not ready else "")
        )
        return ProviderMarketDataImbalanceReleaseReviewVerification(
            verified=verified,
            ready=verified,
            manifest_current=bool(integrity.passed),
            source_current=source_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            operator_approval_pending=operator_pending,
            output_dir=root,
            strategy_evidence_dir=source_root,
            error=error,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ProviderMarketDataImbalanceReleaseReviewVerification(
            verified=False,
            ready=False,
            manifest_current=bool(integrity.passed),
            source_current=False,
            artifacts_consistent=False,
            non_authorizing=False,
            operator_approval_pending=False,
            output_dir=root,
            strategy_evidence_dir=source_root,
            error=f"release_review_unreadable:{exc}",
        )


def _release_checks(
    *,
    verification: Any,
    source_summary: pd.Series,
    input_records: Mapping[str, Mapping[str, Any]],
    catalog_path: Path,
    audit_dir: Path,
    certificate_dir: Path,
    certificate_row: pd.Series,
    strategy: str,
    market: str,
    target_mode: str,
    certificate_sha256: str,
    chain_digest_sha256: str,
    lineage_contract_sha256: str,
    recursive_dependency_count: int,
    config: ProviderMarketDataImbalanceReleaseReviewConfig,
) -> pd.DataFrame:
    expected_catalog = (
        verification.catalog_path.resolve()
        if verification.catalog_path is not None
        else None
    )
    certificate_strategy = _normalize_strategy(
        certificate_row.get("summary_strategy")
    )
    certificate_market = _identity(certificate_row.get("summary_market"))
    expected_strategy = _normalize_strategy(strategy)
    expected_market = _identity(market)
    expected_target_mode = _identity(config.target_mode)
    checks = [
        _check("strategy_evidence_verified", "evidence", verification.verified, "is", True, verification.verified, "strategy evidence is not semantically verified"),
        _check("strategy_evidence_ready", "evidence", verification.ready, "is", True, verification.ready, "strategy evidence is not launch ready"),
        _check("strategy_evidence_manifest_current", "evidence", verification.manifest_current, "is", True, verification.manifest_current, "strategy evidence manifest is stale"),
        _check("strategy_evidence_sources_current", "evidence", verification.source_current, "is", True, verification.source_current, "strategy evidence retained sources are stale"),
        _check("strategy_evidence_artifacts_consistent", "evidence", verification.artifacts_consistent, "is", True, verification.artifacts_consistent, "strategy evidence artifacts disagree with retained sources"),
        _check("strategy_evidence_input_contract_current", "evidence", verification.manifest_input_contract_current, "is", True, verification.manifest_input_contract_current, "strategy evidence six-input contract is incomplete"),
        _check("provider_retained_proofs_current", "evidence", verification.provider_retained_proofs_current, "is", True, verification.provider_retained_proofs_current, "provider retained proofs are not current"),
        _check("strategy_evidence_non_authorizing", "safety", verification.non_authorizing, "is", True, verification.non_authorizing, "strategy evidence contains an authorizing claim"),
        _check("provider_evidence_profile", "identity", _text(source_summary.get("evidence_profile")), "==", PROVIDER_EVIDENCE_PROFILE, _text(source_summary.get("evidence_profile")) == PROVIDER_EVIDENCE_PROFILE, "strategy evidence is not the provider launch profile"),
        _check("single_strategy_identity", "identity", source_summary.get("strategy_count", 0), "==", 1, bool(expected_strategy) and _integer(source_summary.get("strategy_count", 0)) == 1, "strategy evidence does not resolve to one strategy"),
        _check("single_market_identity", "identity", source_summary.get("market_count", 0), "==", 1, bool(expected_market) and _integer(source_summary.get("market_count", 0)) == 1, "strategy evidence does not resolve to one market"),
        _check("certificate_strategy_matches", "identity", certificate_strategy, "==", expected_strategy, bool(certificate_strategy) and certificate_strategy == expected_strategy, "selected certificate strategy differs from strategy evidence"),
        _check("certificate_market_matches", "identity", certificate_market, "==", expected_market, bool(certificate_market) and certificate_market == expected_market, "selected certificate market differs from strategy evidence"),
        _check("source_catalog_matches_verification", "proof", str(catalog_path), "==", str(expected_catalog or ""), expected_catalog == catalog_path, "catalog path differs from the verified evidence source"),
        _check("target_mode_live_dryrun", "identity", target_mode, "==", expected_target_mode, target_mode == expected_target_mode, "selected certificate is not for live_dryrun"),
        _check("certificate_catalog_status", "proof", certificate_row.get("summary_status", False), "is", True, _bool(certificate_row.get("summary_status", False)), "selected certificate is not passed in the source catalog"),
        _check("certificate_non_authorizing", "safety", certificate_row.get("summary_authorizes_submission", "missing"), "is", False, _explicit_false(certificate_row, "summary_authorizes_submission"), "selected certificate is missing an explicit non-authorizing claim"),
        _check("provider_certificate_payload_hashed", "proof", certificate_sha256, "is", "sha256", _valid_sha256(certificate_sha256), "selected certificate payload SHA-256 is missing"),
        _check("active_lineage_chain_digest_hashed", "proof", chain_digest_sha256, "is", "sha256", _valid_sha256(chain_digest_sha256), "active-lineage chain digest SHA-256 is missing"),
        _check("provider_lineage_contract_hashed", "proof", lineage_contract_sha256, "is", "sha256", _valid_sha256(lineage_contract_sha256), "provider lineage selection contract SHA-256 is missing"),
        _check("recursive_dependency_limit", "integrity", recursive_dependency_count, "<=", config.max_dependency_count, recursive_dependency_count <= config.max_dependency_count, "strategy evidence recursive dependency graph exceeds the release-review limit"),
    ]
    summary_paths = {
        "source_catalog_manifest": _text(
            source_summary.get("source_catalog_manifest_path")
        ),
        "selected_provider_active_lineage_chain_audit": _text(
            source_summary.get("selected_provider_active_lineage_chain_audit_dir")
        ),
        "selected_provider_broker_rehearsal_certificate": _text(
            source_summary.get("selected_provider_broker_rehearsal_certificate_dir")
        ),
    }
    expected_paths = {
        "source_catalog_manifest": str(
            Path(input_records["source_catalog_manifest"]["path"]).resolve()
        ),
        "selected_provider_active_lineage_chain_audit": str(audit_dir),
        "selected_provider_broker_rehearsal_certificate": str(certificate_dir),
    }
    for name, expected in expected_paths.items():
        actual = str(Path(summary_paths[name]).resolve()) if summary_paths[name] else ""
        checks.append(
            _check(
                f"{name}_path_bound",
                "proof",
                actual,
                "==",
                expected,
                actual == expected,
                f"strategy evidence summary does not bind {name}",
            )
        )
    hash_bindings = {
        "source_catalog_manifest": (
            "source_catalog_manifest_sha256",
            input_records["source_catalog_manifest"].get("sha256", ""),
        ),
        "selected_provider_active_lineage_chain_audit_manifest": (
            "selected_provider_active_lineage_chain_audit_manifest_sha256",
            input_records[
                "selected_provider_active_lineage_chain_audit_manifest"
            ].get("sha256", ""),
        ),
        "selected_provider_broker_rehearsal_certificate_manifest": (
            "selected_provider_broker_rehearsal_certificate_manifest_sha256",
            input_records[
                "selected_provider_broker_rehearsal_certificate_manifest"
            ].get("sha256", ""),
        ),
    }
    for name, (summary_column, expected) in hash_bindings.items():
        actual = _text(source_summary.get(summary_column)).lower()
        checks.append(
            _check(
                f"{name}_hash_bound",
                "proof",
                actual,
                "==",
                expected,
                _valid_sha256(actual) and actual == expected,
                f"strategy evidence summary does not bind {name}",
            )
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _packet_core(
    *,
    strategy: str,
    market: str,
    target_mode: str,
    source_root: Path,
    source_manifest_sha256: str,
    proof_contract: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "packet_type": (
            "provider_market_data_imbalance_live_dryrun_release_review"
        ),
        "status": "ready_for_operator_review",
        "identity": {
            "strategy": strategy,
            "market": market,
            "target_mode": target_mode,
        },
        "source_evidence": {
            "path": str(source_root),
            "manifest_sha256": source_manifest_sha256,
            "verified": True,
            "ready": True,
            "profile": PROVIDER_EVIDENCE_PROFILE,
        },
        "proof_contract": proof_contract,
        "safety": {
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
        },
        "operator_approval": {
            "required": True,
            "status": "pending",
            "approved": False,
            "template_artifact": (
                "provider_market_data_imbalance_release_review_operator_approval_template.csv"
            ),
            "authorizes_submission": False,
        },
    }


def _release_surfaces_non_authorizing(
    summary: pd.Series,
    packet: Mapping[str, Any],
    saved_config: Mapping[str, Any],
    operator_approval: pd.Series,
    manifest: Mapping[str, Any],
) -> bool:
    safety = _mapping(packet.get("safety"))
    packet_approval = _mapping(packet.get("operator_approval"))
    manifest_extra = _mapping(manifest.get("extra"))
    return bool(
        _explicit_false(summary, "authorizes_submission")
        and _explicit_false(summary, "submission_enabled")
        and _explicit_false(summary, "broker_api_called")
        and _explicit_false(summary, "release_approved")
        and _explicit_false(safety, "authorizes_submission")
        and _explicit_false(safety, "submission_enabled")
        and _explicit_false(safety, "broker_api_called")
        and _bool(safety.get("dry_run_only", False))
        and _explicit_false(packet_approval, "authorizes_submission")
        and _explicit_false(saved_config, "authorizes_submission")
        and _explicit_false(saved_config, "submission_enabled")
        and _explicit_false(saved_config, "broker_api_called")
        and _explicit_false(operator_approval, "authorizes_submission")
        and _explicit_false(manifest_extra, "authorizes_submission")
        and _explicit_false(manifest_extra, "submission_enabled")
        and _explicit_false(manifest_extra, "broker_api_called")
        and _explicit_false(manifest_extra, "release_approved")
    )


def _operator_approval_is_pending(
    summary: pd.Series,
    packet: Mapping[str, Any],
    saved_config: Mapping[str, Any],
    operator_approval: pd.Series,
    manifest: Mapping[str, Any],
) -> bool:
    packet_approval = _mapping(packet.get("operator_approval"))
    manifest_extra = _mapping(manifest.get("extra"))
    return bool(
        _identity(summary.get("operator_approval_status")) == "pending"
        and _explicit_false(summary, "operator_approved")
        and _identity(packet_approval.get("status")) == "pending"
        and _explicit_false(packet_approval, "approved")
        and _identity(saved_config.get("operator_approval_status"))
        == "pending"
        and _explicit_false(saved_config, "operator_approved")
        and _identity(operator_approval.get("decision")) == "pending"
        and not _text(operator_approval.get("operator_id"))
        and not _text(operator_approval.get("reviewed_at_utc"))
        and _identity(manifest_extra.get("operator_approval_status"))
        == "pending"
        and _explicit_false(manifest_extra, "operator_approved")
    )


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


def _proof_contract(
    *,
    source_root: Path,
    source_manifest_path: Path,
    source_manifest_sha256: str,
    input_records: Mapping[str, Mapping[str, Any]],
    chain_digest_sha256: str,
    lineage_contract_sha256: str,
    certificate_sha256: str,
    certificate_cycle_id: str,
) -> dict[str, Any]:
    return {
        "strategy_evidence": {
            "path": str(source_root),
            "manifest_path": str(source_manifest_path),
            "manifest_sha256": source_manifest_sha256,
        },
        "catalog": {
            "path": input_records["catalog"]["path"],
            "sha256": input_records["catalog"].get("sha256", ""),
            "manifest_path": input_records["source_catalog_manifest"]["path"],
            "manifest_sha256": input_records["source_catalog_manifest"].get(
                "sha256", ""
            ),
        },
        "active_lineage_chain_audit": {
            "path": input_records[
                "selected_provider_active_lineage_chain_audit"
            ]["path"],
            "tree_sha256": input_records[
                "selected_provider_active_lineage_chain_audit"
            ].get("tree_sha256", ""),
            "manifest_path": input_records[
                "selected_provider_active_lineage_chain_audit_manifest"
            ]["path"],
            "manifest_sha256": input_records[
                "selected_provider_active_lineage_chain_audit_manifest"
            ].get("sha256", ""),
            "chain_digest_sha256": chain_digest_sha256,
            "provider_lineage_selection_contract_sha256": (
                lineage_contract_sha256
            ),
        },
        "broker_rehearsal_certificate": {
            "path": input_records[
                "selected_provider_broker_rehearsal_certificate"
            ]["path"],
            "tree_sha256": input_records[
                "selected_provider_broker_rehearsal_certificate"
            ].get("tree_sha256", ""),
            "manifest_path": input_records[
                "selected_provider_broker_rehearsal_certificate_manifest"
            ]["path"],
            "manifest_sha256": input_records[
                "selected_provider_broker_rehearsal_certificate_manifest"
            ].get("sha256", ""),
            "certificate_sha256": certificate_sha256,
            "cycle_id": certificate_cycle_id,
        },
    }


def _proof_rows(
    *,
    source_manifest_path: Path,
    source_manifest_sha256: str,
    input_records: Mapping[str, Mapping[str, Any]],
    chain_digest_sha256: str,
    lineage_contract_sha256: str,
    certificate_sha256: str,
) -> pd.DataFrame:
    rows = [
        {
            "component": "strategy_evidence_manifest",
            "path": str(source_manifest_path),
            "kind": "file",
            "sha256": source_manifest_sha256,
            "tree_sha256": "",
            "digest_sha256": source_manifest_sha256,
            "current": True,
        }
    ]
    for name in SOURCE_INPUTS:
        record = input_records[name]
        sha256 = _text(record.get("sha256")).lower()
        tree_sha256 = _text(record.get("tree_sha256")).lower()
        rows.append(
            {
                "component": name,
                "path": record["path"],
                "kind": record["kind"],
                "sha256": sha256,
                "tree_sha256": tree_sha256,
                "digest_sha256": sha256 or tree_sha256,
                "current": True,
            }
        )
    for component, digest in (
        ("active_lineage_chain_digest", chain_digest_sha256),
        ("provider_lineage_selection_contract", lineage_contract_sha256),
        ("broker_rehearsal_certificate_payload", certificate_sha256),
    ):
        rows.append(
            {
                "component": component,
                "path": "",
                "kind": "sha256_digest",
                "sha256": digest,
                "tree_sha256": "",
                "digest_sha256": digest,
                "current": True,
            }
        )
    return pd.DataFrame(rows, columns=PROOF_COLUMNS)


def _operator_approval_template(
    *,
    release_review_id: str,
    strategy: str,
    market: str,
    target_mode: str,
    source_manifest_sha256: str,
    proof_contract: Mapping[str, Any],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "release_review_id": release_review_id,
                "strategy": strategy,
                "market": market,
                "target_mode": target_mode,
                "strategy_evidence_manifest_sha256": source_manifest_sha256,
                "catalog_manifest_sha256": proof_contract["catalog"][
                    "manifest_sha256"
                ],
                "active_lineage_chain_audit_manifest_sha256": proof_contract[
                    "active_lineage_chain_audit"
                ]["manifest_sha256"],
                "broker_rehearsal_certificate_manifest_sha256": proof_contract[
                    "broker_rehearsal_certificate"
                ]["manifest_sha256"],
                "decision": "pending",
                "operator_id": "",
                "operator_role": "",
                "reviewed_at_utc": "",
                "risk_limits_acknowledged": False,
                "kill_switch_acknowledged": False,
                "rollback_plan_acknowledged": False,
                "notes": "",
                "authorizes_submission": False,
            }
        ],
        columns=OPERATOR_APPROVAL_COLUMNS,
    )


def _action_queue(source_root: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "priority": 1,
                "queue_status": "ready",
                "component": "operator_release_review",
                "action": "complete_operator_release_review",
                "reason": "verified provider evidence is ready for human release review",
                "recommendation": "review_limits_kill_switch_and_rollback_plan",
                "next_gate": "operator_release_review",
                "next_gate_help_command": (
                    "hft verify-strategy-evidence --evidence "
                    f'"{source_root}" --fail-on-breach'
                ),
            }
        ],
        columns=ACTION_COLUMNS,
    )


def _summary(
    *,
    release_review_id: str,
    packet_sha256: str,
    strategy: str,
    market: str,
    target_mode: str,
    source_root: Path,
    source_manifest_sha256: str,
    proof_contract: Mapping[str, Any],
    recursive_dependency_count: int,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    return pd.DataFrame(
        [
            {
                "passed": failed_checks == 0,
                "ready": failed_checks == 0,
                "ready_for_operator_review": failed_checks == 0,
                "status": "ready_for_operator_review",
                "failed_checks": failed_checks,
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(
                    action_queue["queue_status"].astype(str).eq("blocked").sum()
                ),
                "recommendation": "complete_operator_release_review",
                "next_gate": "operator_release_review",
                "release_review_id": release_review_id,
                "packet_sha256": packet_sha256,
                "strategy": strategy,
                "market": market,
                "target_mode": target_mode,
                "strategy_evidence_dir": str(source_root),
                "strategy_evidence_verified": True,
                "strategy_evidence_ready": True,
                "strategy_evidence_manifest_sha256": source_manifest_sha256,
                "catalog_sha256": proof_contract["catalog"]["sha256"],
                "catalog_manifest_sha256": proof_contract["catalog"][
                    "manifest_sha256"
                ],
                "active_lineage_chain_audit_tree_sha256": proof_contract[
                    "active_lineage_chain_audit"
                ]["tree_sha256"],
                "active_lineage_chain_audit_manifest_sha256": proof_contract[
                    "active_lineage_chain_audit"
                ]["manifest_sha256"],
                "active_lineage_chain_digest_sha256": proof_contract[
                    "active_lineage_chain_audit"
                ]["chain_digest_sha256"],
                "provider_lineage_selection_contract_sha256": proof_contract[
                    "active_lineage_chain_audit"
                ]["provider_lineage_selection_contract_sha256"],
                "broker_rehearsal_certificate_tree_sha256": proof_contract[
                    "broker_rehearsal_certificate"
                ]["tree_sha256"],
                "broker_rehearsal_certificate_manifest_sha256": proof_contract[
                    "broker_rehearsal_certificate"
                ]["manifest_sha256"],
                "broker_rehearsal_certificate_sha256": proof_contract[
                    "broker_rehearsal_certificate"
                ]["certificate_sha256"],
                "recursive_dependency_count": recursive_dependency_count,
                "operator_approval_required": True,
                "operator_approval_status": "pending",
                "operator_approved": False,
                "release_approved": False,
                "submission_enabled": False,
                "broker_api_called": False,
                "authorizes_submission": False,
            }
        ]
    )


def _runbook_markdown(
    summary: pd.Series,
    proof_contract: Mapping[str, Any],
    source_root: Path,
) -> str:
    return "\n".join(
        [
            "# Provider Live-Dry-Run Release Review Runbook",
            "",
            "## Packet State",
            "",
            f"- Release review ID: `{summary['release_review_id']}`",
            f"- Strategy: `{summary['strategy']}`",
            f"- Market: `{summary['market']}`",
            f"- Target mode: `{summary['target_mode']}`",
            "- Evidence verified and ready: yes",
            "- Operator approval: pending",
            "- Submission enabled: no",
            "- Broker API called: no",
            "- Authorizes submission: no",
            "",
            "## Retained Proofs",
            "",
            f"- Strategy evidence manifest: `{summary['strategy_evidence_manifest_sha256']}`",
            f"- Catalog manifest: `{summary['catalog_manifest_sha256']}`",
            f"- Active-lineage audit manifest: `{summary['active_lineage_chain_audit_manifest_sha256']}`",
            f"- Active-lineage chain digest: `{summary['active_lineage_chain_digest_sha256']}`",
            f"- Rehearsal certificate manifest: `{summary['broker_rehearsal_certificate_manifest_sha256']}`",
            f"- Rehearsal certificate payload: `{summary['broker_rehearsal_certificate_sha256']}`",
            "",
            "## Operator Review",
            "",
            "1. Re-run the strict evidence verifier immediately before review:",
            "",
            "```powershell",
            f'hft verify-strategy-evidence --evidence "{source_root}" --fail-on-breach',
            "```",
            "",
            "2. Confirm risk limits, kill-switch access, and the rollback plan.",
            "3. Record any decision in a separately retained approval artifact; the emitted CSV is an immutable template.",
            "4. Do not submit orders from this packet. It contains no broker command or credential value.",
            "",
            "## Source Paths",
            "",
            f"- Catalog: `{proof_contract['catalog']['path']}`",
            f"- Active-lineage audit: `{proof_contract['active_lineage_chain_audit']['path']}`",
            f"- Rehearsal certificate: `{proof_contract['broker_rehearsal_certificate']['path']}`",
            "",
        ]
    )


def _selected_certificate_row(
    catalog: pd.DataFrame,
    catalog_path: Path,
    certificate_dir: Path,
) -> pd.Series:
    if "run_type" not in catalog.columns or "run_dir" not in catalog.columns:
        raise ValueError("strategy evidence catalog is missing run_type or run_dir")
    matches = catalog.loc[
        catalog["run_type"].astype(str).eq(CERTIFICATE_RUN_TYPE)
        & catalog["run_dir"].map(
            lambda value: _catalog_path(value, catalog_path) == certificate_dir
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            "strategy evidence catalog must contain exactly one selected "
            "provider rehearsal certificate"
        )
    return matches.iloc[0]


def _required_input(
    manifest: Mapping[str, Any],
    name: str,
) -> Mapping[str, Any]:
    inputs = _mapping(manifest.get("inputs"))
    record = _mapping(inputs.get(name))
    expected_kind = "directory" if name in {
        "selected_provider_active_lineage_chain_audit",
        "selected_provider_broker_rehearsal_certificate",
    } else "file"
    if (
        record.get("kind") != expected_kind
        or not _text(record.get("path"))
        or (
            expected_kind == "file"
            and not _valid_sha256(record.get("sha256"))
        )
        or (
            expected_kind == "directory"
            and not _valid_sha256(record.get("tree_sha256"))
        )
    ):
        raise ValueError(f"strategy evidence input {name} is invalid")
    return record


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


def _catalog_path(value: Any, catalog_path: Path) -> Path:
    path = Path(_text(value))
    if not path.is_absolute():
        path = catalog_path.parent / path
    return path.resolve()


def _unique_paths(paths: list[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for path in paths:
        resolved = path.resolve()
        found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)]


def _reject_output_collision(
    out: Path,
    *,
    source_root: Path,
    catalog_path: Path,
    audit_dir: Path,
    certificate_dir: Path,
) -> None:
    protected_roots = (
        source_root,
        catalog_path.parent.resolve(),
        audit_dir,
        certificate_dir,
    )
    for root in protected_roots:
        if out == root or _is_relative_to(out, root):
            raise ValueError(
                "release-review output must be outside every retained proof "
                f"directory: {root}"
            )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_config(config: ProviderMarketDataImbalanceReleaseReviewConfig) -> None:
    if _identity(config.target_mode) != "live_dryrun":
        raise ValueError("target_mode must be live_dryrun")
    if config.max_dependency_count <= 0:
        raise ValueError("max_dependency_count must be positive")


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


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dataframe_records_equal(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
) -> bool:
    if list(actual.columns) != list(expected.columns) or len(actual) != len(expected):
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


def _valid_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return bool(
        len(text) == 64 and all(character in "0123456789abcdef" for character in text)
    )


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


def _integer(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            return bool(float(value)) and not bool(np.isnan(float(value)))
        except (TypeError, ValueError):
            return False
    return _text(value).lower() in {"1", "true", "yes", "y", "pass", "passed"}


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
