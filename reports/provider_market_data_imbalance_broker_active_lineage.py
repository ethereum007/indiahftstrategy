from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from reports.manifest import (
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.provider_market_data_imbalance_broker_lineage_audit_usage import (
    provider_broker_lineage_audit_usage_record,
)
from reports.provider_market_data_imbalance_broker_lineage_migration import (
    provider_broker_lineage_proof_evidence,
)
from reports.provider_market_data_imbalance_broker_lineage_refresh_convergence import (
    RUN_TYPE as CONVERGENCE_RUN_TYPE,
)


RUN_TYPE = "provider_market_data_imbalance_broker_active_lineage_index"
CONVERGENCE_ARTIFACTS = (
    "provider_broker_lineage_refresh_convergence_inventory.csv",
    "provider_broker_lineage_refresh_convergence_checks.csv",
    "provider_broker_lineage_refresh_convergence_summary.csv",
    "provider_broker_lineage_refresh_convergence_action_queue.csv",
    "provider_broker_lineage_refresh_convergence_config.json",
    "provider_broker_lineage_refresh_convergence_runbook.md",
)
INDEX_ARTIFACTS = (
    "provider_broker_active_lineage_index.csv",
    "provider_broker_active_lineage_checks.csv",
    "provider_broker_active_lineage_summary.csv",
    "provider_broker_active_lineage_action_queue.csv",
    "provider_broker_active_lineage_config.json",
    "provider_broker_active_lineage_runbook.md",
)
CONVERGENCE_COLUMNS = {
    "priority",
    "bundle_type",
    "original_bundle_path",
    "source_usage_status",
    "plan_status",
    "plan_record_consistent",
    "expected_output_path",
    "output_manifest_current",
    "output_bundle_passed",
    "output_strict_lineage_required",
    "output_strict_lineage_current",
    "output_source_manifest_current",
    "output_non_authorizing",
    "output_audit_provided",
    "policy_matches",
    "evidence_identity_matches",
    "command_output_matches",
    "command_source_matches",
    "command_requires_strict",
    "command_omits_legacy_audit",
    "convergence_status",
}
INDEX_COLUMNS = (
    "priority",
    "lineage_pair_id",
    "bundle_type",
    "run_type",
    "bundle_path",
    "manifest_path",
    "counterpart_bundle_path",
    "lineage_role",
    "selection_status",
    "catalog_selectable",
    "retained_only",
    "source_usage_status",
    "manifest_current",
    "bundle_passed",
    "strict_lineage_required",
    "strict_lineage_current",
    "source_manifest_current",
    "audit_provided",
    "non_authorizing",
    "policy_sha256",
    "evidence_identity_sha256",
    "pair_policy_matches",
    "pair_evidence_identity_matches",
    "pair_valid",
    "reason",
)
ACTION_COLUMNS = (
    "priority",
    "queue_status",
    "lineage_pair_id",
    "bundle_type",
    "original_bundle_path",
    "strict_bundle_path",
    "action",
    "command",
    "reason",
)
BOOL_INDEX_COLUMNS = {
    "catalog_selectable",
    "retained_only",
    "manifest_current",
    "bundle_passed",
    "strict_lineage_required",
    "strict_lineage_current",
    "source_manifest_current",
    "audit_provided",
    "non_authorizing",
    "pair_policy_matches",
    "pair_evidence_identity_matches",
    "pair_valid",
}
PATH_INDEX_COLUMNS = {
    "bundle_path",
    "manifest_path",
    "counterpart_bundle_path",
}


@dataclass(frozen=True)
class ProviderBrokerActiveLineageReport:
    inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(not self.summary.empty and _bool(self.summary.iloc[0]["ready"]))


@dataclass(frozen=True)
class ProviderBrokerActiveLineageVerification:
    ready: bool
    manifest_current: bool
    source_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    error: str = ""


@dataclass(frozen=True)
class _ConvergenceSource:
    path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    manifest_current: bool
    manifest_error: str
    non_authorizing: bool
    consistent: bool
    ready: bool


def write_provider_broker_active_lineage_index(
    convergence_dir: str | Path,
    output_dir: str | Path,
) -> ProviderBrokerActiveLineageReport:
    source = _load_convergence_source(convergence_dir)
    out = Path(output_dir).resolve()
    if out == source.path or source.path in out.parents:
        raise ValueError("output directory cannot be inside the convergence proof")

    inventory, invalid_pairs = _expected_index(source)
    indexed_paths = _indexed_paths(inventory)
    for bundle in indexed_paths:
        if out == bundle or bundle in out.parents:
            raise ValueError("output directory cannot be inside an indexed provider proof")

    selection_conflicts = _selection_conflict_count(inventory)
    checks = _checks(source, inventory, invalid_pairs, selection_conflicts)
    action_queue = _action_queue(source, invalid_pairs)
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    ready = bool(failed_checks == 0)
    summary = _summary(
        source,
        inventory,
        action_queue,
        invalid_pair_count=len(invalid_pairs),
        selection_conflict_count=selection_conflicts,
        failed_checks=failed_checks,
        ready=ready,
    )
    config_payload = {
        "schema_version": 1,
        "ready": ready,
        "authorizes_submission": False,
        "refresh_convergence_path": str(source.path),
        "policy": {
            "required_selectable_entries_per_pair": 1,
            "required_retained_only_entries_per_pair": 1,
            "max_invalid_pairs": 0,
            "max_selection_conflicts": 0,
        },
        "summary": _jsonable(summary.iloc[0].to_dict()),
        "checks": _jsonable(checks.to_dict(orient="records")),
        "entries": _jsonable(inventory.to_dict(orient="records")),
        "actions": _jsonable(action_queue.to_dict(orient="records")),
    }

    indexed_manifests = [path / "manifest.json" for path in indexed_paths]
    indexed_dependencies = _dependency_paths(indexed_manifests)
    out.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(out / INDEX_ARTIFACTS[0], index=False)
    checks.to_csv(out / INDEX_ARTIFACTS[1], index=False)
    summary.to_csv(out / INDEX_ARTIFACTS[2], index=False)
    action_queue.to_csv(out / INDEX_ARTIFACTS[3], index=False)
    (out / INDEX_ARTIFACTS[4]).write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / INDEX_ARTIFACTS[5]).write_text(
        _runbook(summary.iloc[0], inventory, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"policy": config_payload["policy"]},
        inputs={
            "refresh_convergence": source.path,
            "refresh_convergence_manifest": source.manifest_path,
            "refresh_convergence_dependencies": manifest_dependency_paths(
                source.manifest_path
            ),
            "indexed_provider_bundles": indexed_paths,
            "indexed_provider_manifests": indexed_manifests,
            "indexed_provider_dependencies": indexed_dependencies,
        },
        extra={
            "ready": ready,
            "authorizes_submission": False,
            "lineage_pair_count": int(summary.iloc[0]["lineage_pair_count"]),
            "selectable_bundle_count": int(
                summary.iloc[0]["selectable_bundle_count"]
            ),
            "retained_only_bundle_count": int(
                summary.iloc[0]["retained_only_bundle_count"]
            ),
            "invalid_pair_count": len(invalid_pairs),
            "selection_conflict_count": selection_conflicts,
        },
    )
    return ProviderBrokerActiveLineageReport(
        inventory=inventory,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_broker_active_lineage_index(
    index_dir: str | Path,
) -> ProviderBrokerActiveLineageVerification:
    root = Path(index_dir).resolve()
    manifest_path = root / "manifest.json"
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=INDEX_ARTIFACTS,
        require_input_fingerprints=True,
    )
    manifest = _read_json(manifest_path)
    inventory = _read_csv(root / INDEX_ARTIFACTS[0])
    checks = _read_csv(root / INDEX_ARTIFACTS[1])
    summary = _read_csv(root / INDEX_ARTIFACTS[2])
    actions = _read_csv(root / INDEX_ARTIFACTS[3])
    config = _read_json(root / INDEX_ARTIFACTS[4])
    source_path = _text(config.get("refresh_convergence_path"))
    source = _load_convergence_source(source_path or root / "missing_convergence")
    non_authorizing = _index_non_authorizing(summary, config, manifest)
    consistent = _index_consistent(
        inventory,
        checks,
        summary,
        actions,
        config,
        manifest,
        source,
    )
    summary_ready = bool(
        len(summary) == 1 and _bool(summary.iloc[0].get("ready"))
    )
    ready = bool(
        integrity.passed
        and source.ready
        and non_authorizing
        and consistent
        and summary_ready
    )
    error = (
        integrity.error
        or ("source_convergence_not_current_or_ready" if not source.ready else "")
        or ("index_authorization_claim_invalid" if not non_authorizing else "")
        or ("index_artifacts_disagree" if not consistent else "")
        or ("index_not_ready" if not summary_ready else "")
    )
    return ProviderBrokerActiveLineageVerification(
        ready=ready,
        manifest_current=bool(integrity.passed),
        source_current=source.manifest_current,
        artifacts_consistent=consistent,
        non_authorizing=non_authorizing,
        inventory=inventory,
        checks=checks,
        summary=summary,
        error=error,
    )


def verified_provider_broker_active_lineage_records(
    index_dir: str | Path,
) -> pd.DataFrame:
    verification = verify_provider_broker_active_lineage_index(index_dir)
    if not verification.ready:
        raise ValueError(
            "provider broker active-lineage index is not trusted: "
            f"{verification.error or 'verification_failed'}"
        )
    return verification.inventory.copy()


def resolve_provider_broker_active_lineage_bundle(
    index_dir: str | Path,
    *,
    bundle_type: str,
    original_bundle_path: str | Path | None = None,
) -> Path:
    inventory = verified_provider_broker_active_lineage_records(index_dir)
    matches = inventory.loc[
        inventory["bundle_type"].astype(str).eq(str(bundle_type))
        & inventory["selection_status"].astype(str).eq("selectable")
        & inventory["catalog_selectable"].map(_bool)
    ]
    if original_bundle_path is not None:
        original = _resolved_text(original_bundle_path)
        matches = matches.loc[
            matches["counterpart_bundle_path"].map(_resolved_text).eq(original)
        ]
    if len(matches) != 1:
        qualifier = (
            ""
            if original_bundle_path is None
            else f" for original {Path(original_bundle_path).resolve()}"
        )
        raise ValueError(
            f"expected exactly one selectable {bundle_type} bundle{qualifier}; "
            f"found {len(matches)}"
        )
    return Path(_text(matches.iloc[0]["bundle_path"])).resolve()


def _load_convergence_source(path: str | Path) -> _ConvergenceSource:
    root = Path(path).resolve()
    manifest_path = root / "manifest.json"
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=CONVERGENCE_RUN_TYPE,
        required_artifacts=CONVERGENCE_ARTIFACTS,
        require_input_fingerprints=True,
    )
    manifest = _read_json(manifest_path)
    inventory = _read_csv(root / CONVERGENCE_ARTIFACTS[0])
    checks = _read_csv(root / CONVERGENCE_ARTIFACTS[1])
    summary = _read_csv(root / CONVERGENCE_ARTIFACTS[2])
    actions = _read_csv(root / CONVERGENCE_ARTIFACTS[3])
    config = _read_json(root / CONVERGENCE_ARTIFACTS[4])
    non_authorizing = _source_non_authorizing(summary, config, manifest)
    consistent = _source_consistent(
        inventory,
        checks,
        summary,
        actions,
        config,
        manifest,
    )
    summary_ready = bool(
        len(summary) == 1 and _bool(summary.iloc[0].get("ready"))
    )
    return _ConvergenceSource(
        path=root,
        manifest_path=manifest_path,
        manifest=manifest,
        inventory=inventory,
        checks=checks,
        summary=summary,
        action_queue=actions,
        config=config,
        manifest_current=bool(integrity.passed),
        manifest_error=integrity.error,
        non_authorizing=non_authorizing,
        consistent=consistent,
        ready=bool(
            integrity.passed
            and non_authorizing
            and consistent
            and summary_ready
        ),
    )


def _source_non_authorizing(
    summary: pd.DataFrame,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bool:
    return bool(
        len(summary) == 1
        and "authorizes_submission" in summary.columns
        and not _bool(summary.iloc[0].get("authorizes_submission"))
        and config.get("authorizes_submission") is False
        and _mapping(manifest.get("extra")).get("authorizes_submission") is False
    )


def _source_consistent(
    inventory: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    actions: pd.DataFrame,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bool:
    if (
        len(summary) != 1
        or not CONVERGENCE_COLUMNS.issubset(inventory.columns)
        or "passed" not in checks.columns
        or "queue_status" not in actions.columns
    ):
        return False
    row = summary.iloc[0]
    config_summary = _mapping(config.get("summary"))
    manifest_extra = _mapping(manifest.get("extra"))
    original_paths = inventory["original_bundle_path"].map(_resolved_text)
    strict_paths = inventory["expected_output_path"].map(_resolved_text)
    all_converged = bool(
        inventory.empty
        or inventory["convergence_status"].astype(str).eq("converged").all()
    )
    return bool(
        config.get("schema_version") == 1
        and _mapping(config.get("policy")).get("max_unresolved_actions") == 0
        and _bool(row.get("ready"))
        and _bool(row.get("passed"))
        and _int(row.get("failed_checks"), default=-1) == 0
        and _int(row.get("planned_action_count"), default=-1) == len(inventory)
        and _int(row.get("converged_action_count"), default=-1) == len(inventory)
        and _int(row.get("unresolved_action_count"), default=-1) == 0
        and _int(row.get("action_queue_count"), default=-1) == 0
        and actions.empty
        and checks["passed"].map(_bool).all()
        and all_converged
        and _bool(config.get("ready"))
        and isinstance(config.get("actions"), list)
        and len(config.get("actions", [])) == 0
        and _summary_values_match(row, config_summary)
        and _bool(manifest_extra.get("ready"))
        and _int(manifest_extra.get("planned_action_count"), default=-1)
        == len(inventory)
        and _int(manifest_extra.get("converged_action_count"), default=-1)
        == len(inventory)
        and _int(manifest_extra.get("unresolved_action_count"), default=-1) == 0
        and original_paths.is_unique
        and strict_paths.is_unique
        and not set(original_paths).intersection(set(strict_paths))
    )


def _expected_index(
    source: _ConvergenceSource,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    if not source.ready:
        return pd.DataFrame(columns=INDEX_COLUMNS), []
    rows: list[dict[str, Any]] = []
    invalid_pairs: list[dict[str, str]] = []
    for _, convergence_row in source.inventory.sort_values(
        "priority", kind="stable"
    ).iterrows():
        pair_rows, valid, reason = _pair_rows(convergence_row, len(rows) + 1)
        rows.extend(pair_rows)
        if not valid:
            invalid_pairs.append(
                {
                    "lineage_pair_id": _text(pair_rows[0].get("lineage_pair_id")),
                    "bundle_type": _text(convergence_row.get("bundle_type")),
                    "original_bundle_path": _resolved_text(
                        convergence_row.get("original_bundle_path")
                    ),
                    "strict_bundle_path": _resolved_text(
                        convergence_row.get("expected_output_path")
                    ),
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows, columns=INDEX_COLUMNS), invalid_pairs


def _pair_rows(
    convergence: pd.Series,
    first_priority: int,
) -> tuple[list[dict[str, Any]], bool, str]:
    bundle_type = _text(convergence.get("bundle_type"))
    original_path = _resolved_text(convergence.get("original_bundle_path"))
    strict_path = _resolved_text(convergence.get("expected_output_path"))
    original = provider_broker_lineage_proof_evidence(original_path)
    strict = provider_broker_lineage_proof_evidence(strict_path)
    try:
        original_usage = provider_broker_lineage_audit_usage_record(original_path)
    except ValueError:
        original_usage = {}
    try:
        strict_usage = provider_broker_lineage_audit_usage_record(strict_path)
    except ValueError:
        strict_usage = {}
    original_non_authorizing = _bundle_non_authorizing(original_path)
    strict_non_authorizing = _bundle_non_authorizing(strict_path)
    policy_matches = bool(
        _text(original.get("policy_sha256"))
        and _text(original.get("policy_sha256"))
        == _text(strict.get("policy_sha256"))
    )
    evidence_matches = bool(
        _text(original.get("evidence_identity_sha256"))
        and _text(original.get("evidence_identity_sha256"))
        == _text(strict.get("evidence_identity_sha256"))
    )
    source_usage_status = _text(convergence.get("source_usage_status"))
    source_assertions = (
        "plan_record_consistent",
        "output_manifest_current",
        "output_bundle_passed",
        "output_strict_lineage_required",
        "output_strict_lineage_current",
        "output_source_manifest_current",
        "output_non_authorizing",
        "policy_matches",
        "evidence_identity_matches",
        "command_output_matches",
        "command_source_matches",
        "command_requires_strict",
        "command_omits_legacy_audit",
    )
    valid = bool(
        original_path
        and strict_path
        and original_path != strict_path
        and _text(convergence.get("plan_status")) == "ready"
        and _text(convergence.get("convergence_status")) == "converged"
        and all(_bool(convergence.get(field)) for field in source_assertions)
        and not _bool(convergence.get("output_audit_provided"))
        and _text(original.get("bundle_type")) == bundle_type
        and _bool(original.get("manifest_current"))
        and _bool(original.get("bundle_passed"))
        and original_non_authorizing
        and _text(original_usage.get("usage_status")) == source_usage_status
        and _text(strict.get("bundle_type")) == bundle_type
        and _bool(strict.get("manifest_current"))
        and _bool(strict.get("bundle_passed"))
        and _bool(strict.get("strict_lineage_required"))
        and _bool(strict.get("strict_lineage_current"))
        and _bool(strict.get("source_manifest_current"))
        and _text(strict.get("migration_status")) == "strict_ready"
        and _text(strict_usage.get("usage_status")) == "strict_ready"
        and not _bool(strict_usage.get("audit_provided"))
        and strict_non_authorizing
        and policy_matches
        and evidence_matches
    )
    reason = (
        "strict sibling is the only selectable member of this lineage pair"
        if valid
        else "convergence pair no longer satisfies strict selection invariants"
    )
    pair_id = _pair_id(
        bundle_type,
        original_path,
        strict_path,
        _text(original.get("policy_sha256")),
        _text(original.get("evidence_identity_sha256")),
    )
    original_row = _index_row(
        priority=first_priority,
        pair_id=pair_id,
        bundle_type=bundle_type,
        path=original_path,
        counterpart=strict_path,
        role="legacy_original",
        selection_status="retained_only" if valid else "blocked",
        selectable=False,
        retained_only=valid,
        usage=original_usage,
        evidence=original,
        non_authorizing=original_non_authorizing,
        policy_matches=policy_matches,
        evidence_matches=evidence_matches,
        pair_valid=valid,
        reason=(
            "superseded by a current equivalent strict-lineage sibling"
            if valid
            else reason
        ),
    )
    strict_row = _index_row(
        priority=first_priority + 1,
        pair_id=pair_id,
        bundle_type=bundle_type,
        path=strict_path,
        counterpart=original_path,
        role="active_strict",
        selection_status="selectable" if valid else "blocked",
        selectable=valid,
        retained_only=False,
        usage=strict_usage,
        evidence=strict,
        non_authorizing=strict_non_authorizing,
        policy_matches=policy_matches,
        evidence_matches=evidence_matches,
        pair_valid=valid,
        reason=reason,
    )
    return [original_row, strict_row], valid, reason


def _index_row(
    *,
    priority: int,
    pair_id: str,
    bundle_type: str,
    path: str,
    counterpart: str,
    role: str,
    selection_status: str,
    selectable: bool,
    retained_only: bool,
    usage: Mapping[str, Any],
    evidence: Mapping[str, Any],
    non_authorizing: bool,
    policy_matches: bool,
    evidence_matches: bool,
    pair_valid: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "lineage_pair_id": pair_id,
        "bundle_type": bundle_type,
        "run_type": _text(evidence.get("run_type")),
        "bundle_path": path,
        "manifest_path": str(Path(path) / "manifest.json") if path else "",
        "counterpart_bundle_path": counterpart,
        "lineage_role": role,
        "selection_status": selection_status,
        "catalog_selectable": selectable,
        "retained_only": retained_only,
        "source_usage_status": _text(usage.get("usage_status")),
        "manifest_current": _bool(evidence.get("manifest_current")),
        "bundle_passed": _bool(evidence.get("bundle_passed")),
        "strict_lineage_required": _bool(
            evidence.get("strict_lineage_required")
        ),
        "strict_lineage_current": _bool(evidence.get("strict_lineage_current")),
        "source_manifest_current": _bool(evidence.get("source_manifest_current")),
        "audit_provided": _bool(usage.get("audit_provided")),
        "non_authorizing": non_authorizing,
        "policy_sha256": _text(evidence.get("policy_sha256")),
        "evidence_identity_sha256": _text(
            evidence.get("evidence_identity_sha256")
        ),
        "pair_policy_matches": policy_matches,
        "pair_evidence_identity_matches": evidence_matches,
        "pair_valid": pair_valid,
        "reason": reason,
    }


def _checks(
    source: _ConvergenceSource,
    inventory: pd.DataFrame,
    invalid_pairs: list[dict[str, str]],
    selection_conflicts: int,
) -> pd.DataFrame:
    pair_count = int(inventory["lineage_pair_id"].nunique()) if not inventory.empty else 0
    selectable = _status_count(inventory, "selectable")
    retained = _status_count(inventory, "retained_only")
    shape_ready = bool(
        len(inventory) == pair_count * 2
        and selectable == pair_count
        and retained == pair_count
    )
    return pd.DataFrame(
        [
            _check(
                "refresh_convergence_current",
                source.manifest_current,
                "is",
                True,
                source.manifest_current,
                source.manifest_error or "convergence proof is not current",
            ),
            _check(
                "refresh_convergence_non_authorizing",
                source.non_authorizing,
                "is",
                True,
                source.non_authorizing,
                "convergence proof must explicitly prohibit broker submission",
            ),
            _check(
                "refresh_convergence_consistent",
                source.consistent,
                "is",
                True,
                source.consistent,
                "convergence inventory, checks, summary, config, or manifest disagree",
            ),
            _check(
                "refresh_convergence_ready",
                source.ready,
                "is",
                True,
                source.ready,
                "strict refresh convergence must pass before retirement",
            ),
            _check(
                "invalid_lineage_pairs",
                len(invalid_pairs),
                "==",
                0,
                not invalid_pairs,
                "one or more converged pairs failed independent selection checks",
            ),
            _check(
                "selection_conflicts",
                selection_conflicts,
                "==",
                0,
                selection_conflicts == 0,
                "bundle paths or pair roles conflict",
            ),
            _check(
                "lineage_pair_cardinality",
                shape_ready,
                "is",
                True,
                shape_ready,
                "each pair requires one selectable and one retained-only entry",
            ),
        ]
    )


def _summary(
    source: _ConvergenceSource,
    inventory: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    invalid_pair_count: int,
    selection_conflict_count: int,
    failed_checks: int,
    ready: bool,
) -> pd.DataFrame:
    pair_count = int(inventory["lineage_pair_id"].nunique()) if not inventory.empty else 0
    blocked_actions = _queue_status_count(actions, "blocked")
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "passed": ready,
                "authorizes_submission": False,
                "refresh_convergence_path": str(source.path),
                "refresh_convergence_current": source.manifest_current,
                "refresh_convergence_consistent": source.consistent,
                "refresh_convergence_ready": source.ready,
                "lineage_pair_count": pair_count,
                "index_entry_count": len(inventory),
                "selectable_bundle_count": _status_count(inventory, "selectable"),
                "retained_only_bundle_count": _status_count(
                    inventory, "retained_only"
                ),
                "blocked_bundle_count": _status_count(inventory, "blocked"),
                "invalid_pair_count": invalid_pair_count,
                "selection_conflict_count": selection_conflict_count,
                "failed_checks": failed_checks,
                "action_queue_count": len(actions),
                "ready_action_count": _queue_status_count(actions, "ready"),
                "blocked_action_count": blocked_actions,
                "recommendation": (
                    "no_retirements_required"
                    if ready and pair_count == 0
                    else "use_selectable_strict_lineage_only"
                    if ready
                    else "repair_convergence_before_lineage_selection"
                ),
            }
        ]
    )


def _action_queue(
    source: _ConvergenceSource,
    invalid_pairs: list[dict[str, str]],
) -> pd.DataFrame:
    if not source.ready:
        reason = (
            source.manifest_error
            or ("convergence_not_non_authorizing" if not source.non_authorizing else "")
            or ("convergence_artifacts_disagree" if not source.consistent else "")
            or "strict refresh convergence is not ready"
        )
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "blocked",
                    "lineage_pair_id": "",
                    "bundle_type": "refresh_convergence",
                    "original_bundle_path": "",
                    "strict_bundle_path": "",
                    "action": "regenerate_current_refresh_convergence",
                    "command": "",
                    "reason": reason,
                }
            ],
            columns=ACTION_COLUMNS,
        )
    rows = []
    for pair in invalid_pairs:
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "lineage_pair_id": pair["lineage_pair_id"],
                "bundle_type": pair["bundle_type"],
                "original_bundle_path": pair["original_bundle_path"],
                "strict_bundle_path": pair["strict_bundle_path"],
                "action": "repair_pair_and_rerun_refresh_convergence",
                "command": "",
                "reason": pair["reason"],
            }
        )
    return pd.DataFrame(rows, columns=ACTION_COLUMNS)


def _index_non_authorizing(
    summary: pd.DataFrame,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bool:
    return bool(
        len(summary) == 1
        and "authorizes_submission" in summary.columns
        and not _bool(summary.iloc[0].get("authorizes_submission"))
        and config.get("authorizes_submission") is False
        and _mapping(manifest.get("extra")).get("authorizes_submission") is False
    )


def _index_consistent(
    inventory: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    actions: pd.DataFrame,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    source: _ConvergenceSource,
) -> bool:
    if (
        len(summary) != 1
        or not set(INDEX_COLUMNS).issubset(inventory.columns)
        or not set(ACTION_COLUMNS).issubset(actions.columns)
        or "passed" not in checks.columns
    ):
        return False
    row = summary.iloc[0]
    config_summary = _mapping(config.get("summary"))
    config_entries = config.get("entries")
    config_actions = config.get("actions")
    manifest_extra = _mapping(manifest.get("extra"))
    expected, invalid_pairs = _expected_index(source)
    conflicts = _selection_conflict_count(inventory)
    pair_count = int(inventory["lineage_pair_id"].nunique()) if not inventory.empty else 0
    ready = _bool(row.get("ready"))
    checks_passed = bool(checks["passed"].map(_bool).all())
    return bool(
        config.get("schema_version") == 1
        and _mapping(config.get("policy"))
        == {
            "required_selectable_entries_per_pair": 1,
            "required_retained_only_entries_per_pair": 1,
            "max_invalid_pairs": 0,
            "max_selection_conflicts": 0,
        }
        and _resolved_text(config.get("refresh_convergence_path"))
        == str(source.path)
        and isinstance(config_entries, list)
        and isinstance(config_actions, list)
        and _records_match(inventory, config_entries, INDEX_COLUMNS)
        and _records_match(actions, config_actions, ACTION_COLUMNS)
        and _frames_match(inventory, expected, INDEX_COLUMNS)
        and _summary_values_match(row, config_summary)
        and _int(row.get("lineage_pair_count"), default=-1) == pair_count
        and _int(row.get("index_entry_count"), default=-1) == len(inventory)
        and _int(row.get("selectable_bundle_count"), default=-1)
        == _status_count(inventory, "selectable")
        and _int(row.get("retained_only_bundle_count"), default=-1)
        == _status_count(inventory, "retained_only")
        and _int(row.get("blocked_bundle_count"), default=-1)
        == _status_count(inventory, "blocked")
        and _int(row.get("invalid_pair_count"), default=-1) == len(invalid_pairs)
        and _int(row.get("selection_conflict_count"), default=-1) == conflicts
        and _int(row.get("action_queue_count"), default=-1) == len(actions)
        and _int(row.get("blocked_action_count"), default=-1)
        == _queue_status_count(actions, "blocked")
        and _int(row.get("failed_checks"), default=-1)
        == int((~checks["passed"].map(_bool)).sum())
        and ready == checks_passed
        and _bool(config.get("ready")) == ready
        and _bool(manifest_extra.get("ready")) == ready
        and _int(manifest_extra.get("lineage_pair_count"), default=-1)
        == pair_count
        and _int(manifest_extra.get("selectable_bundle_count"), default=-1)
        == _status_count(inventory, "selectable")
        and _int(manifest_extra.get("retained_only_bundle_count"), default=-1)
        == _status_count(inventory, "retained_only")
        and _int(manifest_extra.get("invalid_pair_count"), default=-1)
        == len(invalid_pairs)
        and _int(manifest_extra.get("selection_conflict_count"), default=-1)
        == conflicts
    )


def _selection_conflict_count(inventory: pd.DataFrame) -> int:
    if inventory.empty:
        return 0
    conflicts = int(inventory["bundle_path"].map(_resolved_text).duplicated().sum())
    for _, pair in inventory.groupby("lineage_pair_id", sort=False):
        roles = pair["lineage_role"].astype(str).tolist()
        statuses = pair["selection_status"].astype(str).tolist()
        if len(pair) != 2 or sorted(roles) != ["active_strict", "legacy_original"]:
            conflicts += 1
        if _bool(pair["pair_valid"].iloc[0]):
            if sorted(statuses) != ["retained_only", "selectable"]:
                conflicts += 1
            if int(pair["catalog_selectable"].map(_bool).sum()) != 1:
                conflicts += 1
    return conflicts


def _records_match(
    frame: pd.DataFrame,
    records: list[Any],
    columns: tuple[str, ...],
) -> bool:
    if len(frame) != len(records):
        return False
    mappings = [_mapping(record) for record in records]
    if any(not record and columns for record in mappings):
        return False
    ordered_frame = frame.sort_values("priority", kind="stable").to_dict(
        orient="records"
    )
    mappings.sort(key=lambda record: _int(record.get("priority"), default=0))
    return all(
        all(_field_matches(column, left.get(column), right.get(column)) for column in columns)
        for left, right in zip(ordered_frame, mappings)
    )


def _frames_match(
    left: pd.DataFrame,
    right: pd.DataFrame,
    columns: tuple[str, ...],
) -> bool:
    return _records_match(left, right.to_dict(orient="records"), columns)


def _field_matches(field: str, left: Any, right: Any) -> bool:
    if field == "priority":
        return _int(left, default=-1) == _int(right, default=-1)
    if field in BOOL_INDEX_COLUMNS:
        return _bool(left) == _bool(right)
    if field in PATH_INDEX_COLUMNS or field.endswith("_bundle_path"):
        return _resolved_text(left) == _resolved_text(right)
    return _text(left) == _text(right)


def _summary_values_match(row: pd.Series, stored: Mapping[str, Any]) -> bool:
    if not stored:
        return False
    for field in row.index:
        left = row.get(field)
        right = stored.get(field)
        if field.endswith("_path"):
            matches = _resolved_text(left) == _resolved_text(right)
        elif field in {"ready", "passed", "authorizes_submission"} or field.endswith(
            ("_current", "_consistent")
        ):
            matches = _bool(left) == _bool(right)
        elif field.endswith("_count") or field == "failed_checks":
            matches = _int(left, default=-1) == _int(right, default=-1)
        else:
            matches = _text(left) == _text(right)
        if not matches:
            return False
    return True


def _bundle_non_authorizing(path: str) -> bool:
    if not path:
        return False
    manifest = _read_json(Path(path) / "manifest.json")
    extra = _mapping(manifest.get("extra"))
    return bool(
        "authorizes_submission" in extra
        and not _bool(extra.get("authorizes_submission"))
    )


def _pair_id(
    bundle_type: str,
    original: str,
    strict: str,
    policy_sha256: str,
    evidence_sha256: str,
) -> str:
    payload = json.dumps(
        {
            "bundle_type": bundle_type,
            "original_bundle_path": original,
            "strict_bundle_path": strict,
            "policy_sha256": policy_sha256,
            "evidence_identity_sha256": evidence_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _indexed_paths(inventory: pd.DataFrame) -> list[Path]:
    if inventory.empty:
        return []
    found = {
        _resolved_text(path): Path(_resolved_text(path))
        for path in inventory["bundle_path"]
        if _resolved_text(path)
    }
    return [found[key] for key in sorted(found)]


def _dependency_paths(manifests: list[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for manifest in manifests:
        if not manifest.is_file():
            continue
        for dependency in manifest_dependency_paths(manifest):
            resolved = dependency.resolve()
            found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)]


def _runbook(
    summary: pd.Series,
    inventory: pd.DataFrame,
    actions: pd.DataFrame,
) -> str:
    lines = [
        "# Provider Broker Active Lineage Index",
        "",
        f"- Ready: {'yes' if _bool(summary['ready']) else 'no'}",
        f"- Lineage pairs: {int(summary['lineage_pair_count'])}",
        f"- Selectable strict bundles: {int(summary['selectable_bundle_count'])}",
        f"- Retained-only legacy bundles: {int(summary['retained_only_bundle_count'])}",
        "- Authorizes broker submission: no",
        "",
        "## Selection Index",
        "",
    ]
    if inventory.empty:
        lines.append("_No lineage retirements were required._")
    else:
        lines.extend(
            [
                "| Type | Role | Selection | Bundle |",
                "|---|---|---|---|",
            ]
        )
        for _, row in inventory.iterrows():
            lines.append(
                f"| {row['bundle_type']} | {row['lineage_role']} | "
                f"{row['selection_status']} | `{row['bundle_path']}` |"
            )
    lines.extend(["", "## Actions", ""])
    if actions.empty:
        lines.append("_No retirement-index actions._")
    else:
        for _, row in actions.iterrows():
            lines.append(
                f"- [{row['queue_status']}] {row['action']}: {row['reason']}"
            )
    lines.extend(
        [
            "",
            "Legacy originals remain retained for audit and reproducibility, but",
            "only entries marked `selectable` may be resolved for downstream use.",
        ]
    )
    return "\n".join(lines) + "\n"


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _status_count(inventory: pd.DataFrame, status: str) -> int:
    if inventory.empty or "selection_status" not in inventory.columns:
        return 0
    return int(inventory["selection_status"].astype(str).eq(status).sum())


def _queue_status_count(actions: pd.DataFrame, status: str) -> int:
    if actions.empty or "queue_status" not in actions.columns:
        return 0
    return int(actions["queue_status"].astype(str).eq(status).sum())


def _resolved_text(value: Any) -> str:
    text = _text(value)
    return str(Path(text).resolve()) if text else ""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {
        "1",
        "true",
        "yes",
        "y",
        "ready",
        "pass",
        "passed",
    }


def _int(value: Any, *, default: int) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return str(value)
