from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from reports.manifest import (
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "provider_market_data_imbalance_broker_lineage_migration_audit"
TARGETS = {
    "provider_market_data_imbalance_broker_dispatch_ack": {
        "bundle_type": "provider_ack",
        "summary": "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
        "config": "provider_market_data_imbalance_broker_dispatch_ack_config.json",
    },
    "provider_market_data_imbalance_broker_dispatch_roundtrip": {
        "bundle_type": "provider_roundtrip",
        "summary": "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        "config": "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json",
    },
    "provider_market_data_imbalance_broker_rehearsal_certificate": {
        "bundle_type": "rehearsal_certificate",
        "summary": "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
        "config": "provider_market_data_imbalance_broker_rehearsal_certificate.json",
    },
}
STRICT_FIELDS = (
    "broker_dispatch_ack_lineage_required",
    "broker_dispatch_ack_lineage_provided",
    "broker_dispatch_ack_manifest_current",
    "broker_dispatch_ack_lineage_contract_consistent",
    "broker_dispatch_ack_non_authorizing",
    "broker_dispatch_ack_send_lineage_gate_passed",
    "broker_dispatch_ack_send_matches_current",
    "broker_dispatch_ack_expected_send_matches_current",
    "broker_dispatch_ack_lineage_gate_passed",
)
INVENTORY_COLUMNS = (
    "bundle_type",
    "run_type",
    "bundle_path",
    "manifest_path",
    "manifest_current",
    "manifest_error",
    "bundle_passed",
    "strict_lineage_required",
    "strict_lineage_current",
    "ack_manifest_path",
    "ack_manifest_sha256",
    "source_path",
    "source_path_exists",
    "source_manifest_current",
    "source_detail",
    "policy_sha256",
    "evidence_identity_sha256",
    "strict_replacement_path",
    "strict_replacement_current",
    "strict_replacement_matches_policy",
    "strict_replacement_matches_evidence",
    "strict_replacement_dependency_covered",
    "migration_status",
    "reason",
    "recommended_command",
)
ACTION_QUEUE_COLUMNS = (
    "priority",
    "queue_status",
    "bundle_type",
    "bundle_path",
    "migration_status",
    "action",
    "reason",
    "command",
)
AUDIT_ARTIFACTS = (
    "provider_broker_lineage_migration_inventory.csv",
    "provider_broker_lineage_migration_checks.csv",
    "provider_broker_lineage_migration_summary.csv",
    "provider_broker_lineage_migration_action_queue.csv",
    "provider_broker_lineage_migration_config.json",
    "provider_broker_lineage_migration_runbook.md",
)
LEGACY_SOURCE_ROLES = {
    "provider_send": ("provider_ack", "source_path"),
    "provider_ack": ("provider_ack", "bundle_path"),
    "provider_roundtrip": ("provider_roundtrip", "bundle_path"),
}


@dataclass(frozen=True)
class ProviderBrokerLineageMigrationConfig:
    recursive: bool = True
    max_bundles: int = 1000
    max_blocked_bundles: int = 0
    min_strict_ready_coverage: float = 1.0


@dataclass(frozen=True)
class ProviderBrokerLineageMigrationReport:
    inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready_for_strict_default"])


@dataclass(frozen=True)
class ProviderBrokerLineageMigrationAuditVerification:
    audit_dir: Path
    source_path: Path
    source_role: str
    manifest_current: bool
    policy_ready: bool
    source_covered: bool
    source_status: str
    ready: bool
    error: str
    checks: pd.DataFrame
    matched_inventory: pd.DataFrame


def provider_broker_lineage_migration_audit_inputs(
    audit_dir: str | Path | None,
) -> dict[str, Any]:
    if not audit_dir:
        return {}
    audit = Path(audit_dir).resolve()
    manifest = audit / "manifest.json"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"lineage migration audit manifest not found: {manifest}"
        )
    return {
        "lineage_migration_audit": audit,
        "lineage_migration_audit_manifest": manifest,
        "lineage_migration_audit_dependencies": manifest_dependency_paths(
            manifest
        ),
    }


def verify_provider_broker_lineage_migration_audit(
    audit_dir: str | Path,
    *,
    source_path: str | Path,
    source_role: str,
) -> ProviderBrokerLineageMigrationAuditVerification:
    role = str(source_role).strip()
    if role not in LEGACY_SOURCE_ROLES:
        choices = ", ".join(sorted(LEGACY_SOURCE_ROLES))
        raise ValueError(f"source_role must be one of: {choices}")

    audit = Path(audit_dir).resolve()
    source = Path(source_path).resolve()
    integrity = verify_experiment_manifest(
        audit / "manifest.json",
        expected_run_type=RUN_TYPE,
        required_artifacts=AUDIT_ARTIFACTS,
        require_input_fingerprints=True,
    )
    inventory = _read_csv(
        audit / "provider_broker_lineage_migration_inventory.csv"
    )
    audit_checks = _read_csv(
        audit / "provider_broker_lineage_migration_checks.csv"
    )
    summary = _read_csv(
        audit / "provider_broker_lineage_migration_summary.csv"
    )
    actions = _read_csv(
        audit / "provider_broker_lineage_migration_action_queue.csv"
    )
    config = _read_json(
        audit / "provider_broker_lineage_migration_config.json"
    )
    manifest = _read_json(audit / "manifest.json")
    summary_row = (
        summary.iloc[0] if len(summary) == 1 else pd.Series(dtype=object)
    )
    manifest_extra = _mapping(manifest.get("extra"))
    manifest_inputs = _mapping(manifest.get("inputs"))
    bundle_type, path_field = LEGACY_SOURCE_ROLES[role]
    matched = _matched_legacy_inventory(
        inventory,
        bundle_type=bundle_type,
        path_field=path_field,
        source=source,
    )
    source_status = (
        _text(matched.iloc[0].get("migration_status"))
        if len(matched) == 1
        else ""
    )
    source_covered = bool(
        len(matched) == 1
        and source_status == "covered_by_strict"
        and _covered_inventory_row_current(matched.iloc[0])
    )
    coverage = _float(summary_row.get("strict_ready_coverage"), default=-1.0)
    policy_ready = bool(
        len(summary) == 1
        and _bool(summary_row.get("ready_for_strict_default"))
        and not _bool(summary_row.get("authorizes_submission"))
        and coverage == 1.0
        and _int(summary_row.get("blocked_bundles"), default=-1) == 0
        and _int(summary_row.get("failed_checks"), default=-1) == 0
        and _int(summary_row.get("blocked_action_count"), default=-1) == 0
        and actions.empty
    )
    audit_checks_passed = _all_checks_passed(audit_checks)
    config_matches_summary = _audit_config_matches_summary(
        config,
        summary_row,
    )
    manifest_matches_summary = _audit_manifest_matches_summary(
        manifest_extra,
        summary_row,
    )
    manifest_inputs_match = _audit_manifest_inputs_match_summary(
        manifest_inputs,
        summary_row,
    )
    inventory_matches_summary = _audit_inventory_matches_summary(
        inventory,
        summary_row,
    )
    non_authorizing = bool(
        not _bool(config.get("authorizes_submission"))
        and not _bool(manifest_extra.get("authorizes_submission"))
    )
    checks = pd.DataFrame(
        [
            _check(
                "audit_manifest_current",
                integrity.error or integrity.passed,
                "is",
                True,
                integrity.passed,
            ),
            _check(
                "audit_manifest_seals_manifests",
                "audited_provider_manifests" in manifest_inputs,
                "is",
                True,
                "audited_provider_manifests" in manifest_inputs,
            ),
            _check(
                "audit_manifest_seals_dependencies",
                "audited_provider_dependencies" in manifest_inputs,
                "is",
                True,
                "audited_provider_dependencies" in manifest_inputs,
            ),
            _check(
                "audit_schema_current",
                _int(config.get("schema_version"), default=0),
                ">=",
                2,
                _int(config.get("schema_version"), default=0) >= 2,
            ),
            _check(
                "audit_policy_ready",
                policy_ready,
                "is",
                True,
                policy_ready,
            ),
            _check(
                "audit_checks_passed",
                audit_checks_passed,
                "is",
                True,
                audit_checks_passed,
            ),
            _check(
                "audit_config_matches_summary",
                config_matches_summary,
                "is",
                True,
                config_matches_summary,
            ),
            _check(
                "audit_manifest_matches_summary",
                manifest_matches_summary,
                "is",
                True,
                manifest_matches_summary,
            ),
            _check(
                "audit_manifest_inputs_match_summary",
                manifest_inputs_match,
                "is",
                True,
                manifest_inputs_match,
            ),
            _check(
                "audit_inventory_matches_summary",
                inventory_matches_summary,
                "is",
                True,
                inventory_matches_summary,
            ),
            _check(
                "audit_non_authorizing",
                non_authorizing,
                "is",
                True,
                non_authorizing,
            ),
            _check(
                "legacy_source_covered",
                source_covered,
                "is",
                True,
                source_covered,
            ),
        ]
    )
    ready = bool(checks["passed"].astype(bool).all())
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str)
    return ProviderBrokerLineageMigrationAuditVerification(
        audit_dir=audit,
        source_path=source,
        source_role=role,
        manifest_current=bool(integrity.passed),
        policy_ready=policy_ready,
        source_covered=source_covered,
        source_status=source_status,
        ready=ready,
        error="" if ready else ",".join(failed.tolist()),
        checks=checks,
        matched_inventory=matched,
    )


def write_provider_broker_lineage_migration_audit(
    roots: list[str | Path] | tuple[str | Path, ...],
    output_dir: str | Path,
    *,
    config: ProviderBrokerLineageMigrationConfig | None = None,
) -> ProviderBrokerLineageMigrationReport:
    config = config or ProviderBrokerLineageMigrationConfig()
    _validate_config(config)
    resolved_roots = tuple(Path(root).resolve() for root in roots)
    if not resolved_roots:
        raise ValueError("at least one provider proof root is required")
    out = Path(output_dir).resolve()
    _validate_output_location(resolved_roots, out)

    manifests, discovery_errors, truncated = _discover_manifests(
        resolved_roots,
        recursive=config.recursive,
        max_bundles=config.max_bundles,
        exclude_root=out,
    )
    audited_dependencies = _audited_dependency_paths(manifests)
    _validate_output_bundle_location(manifests, out)
    rows = [_inventory_row(path) for path in manifests]
    inventory = pd.DataFrame(rows, columns=INVENTORY_COLUMNS)
    inventory = _apply_strict_replacement_coverage(inventory)
    checks = _checks(
        inventory,
        discovery_errors=discovery_errors,
        truncated=truncated,
        config=config,
    )
    summary = _summary(
        inventory,
        checks,
        root_count=len(resolved_roots),
        discovery_error_count=len(discovery_errors),
        truncated=truncated,
        audited_manifest_count=len(manifests),
        audited_dependency_count=len(audited_dependencies),
    )
    action_queue = _action_queue(inventory)
    summary = _summary_with_actions(summary, action_queue)
    config_payload = _config_payload(
        resolved_roots,
        summary.iloc[0],
        checks,
        action_queue,
        config,
    )

    out.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(
        out / "provider_broker_lineage_migration_inventory.csv",
        index=False,
    )
    checks.to_csv(
        out / "provider_broker_lineage_migration_checks.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_broker_lineage_migration_summary.csv",
        index=False,
    )
    action_queue.to_csv(
        out / "provider_broker_lineage_migration_action_queue.csv",
        index=False,
    )
    (out / "provider_broker_lineage_migration_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_broker_lineage_migration_runbook.md").write_text(
        _runbook(summary.iloc[0], inventory, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "audited_provider_bundles": [path.parent for path in manifests],
            "audited_provider_manifests": manifests,
            "audited_provider_dependencies": audited_dependencies,
        },
        extra={
            "ready": bool(summary.iloc[0]["ready_for_strict_default"]),
            "authorizes_submission": False,
            "bundle_count": int(summary.iloc[0]["bundle_count"]),
            "strict_ready_bundles": int(
                summary.iloc[0]["strict_ready_bundles"]
            ),
            "regenerate_strict_bundles": int(
                summary.iloc[0]["regenerate_strict_bundles"]
            ),
            "strict_replacement_covered_bundles": int(
                summary.iloc[0]["strict_replacement_covered_bundles"]
            ),
            "blocked_bundles": int(summary.iloc[0]["blocked_bundles"]),
            "strict_ready_coverage": float(
                summary.iloc[0]["strict_ready_coverage"]
            ),
            "audited_manifest_count": int(
                summary.iloc[0]["audited_manifest_count"]
            ),
            "audited_dependency_count": int(
                summary.iloc[0]["audited_dependency_count"]
            ),
        },
    )
    return ProviderBrokerLineageMigrationReport(
        inventory=inventory,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config_payload,
        output_dir=out,
    )


def _discover_manifests(
    roots: tuple[Path, ...],
    *,
    recursive: bool,
    max_bundles: int,
    exclude_root: Path,
) -> tuple[list[Path], list[str], bool]:
    candidates: set[Path] = set()
    errors: list[str] = []
    for root in roots:
        if not root.exists():
            errors.append(f"missing_root:{root}")
            continue
        direct = root / "manifest.json" if root.is_dir() else root
        if direct.is_file() and not _within(direct, exclude_root):
            candidates.add(direct.resolve())
        if recursive and root.is_dir():
            for manifest_path in root.rglob("manifest.json"):
                if not _within(manifest_path, exclude_root):
                    candidates.add(manifest_path.resolve())

    selected: list[Path] = []
    for manifest_path in sorted(candidates, key=lambda path: str(path).lower()):
        manifest = _read_json(manifest_path)
        if _text(manifest.get("run_type")) in TARGETS:
            selected.append(manifest_path)
    truncated = len(selected) > max_bundles
    return selected[:max_bundles], errors, truncated


def _audited_dependency_paths(manifests: list[Path]) -> list[Path]:
    dependencies: dict[str, Path] = {}
    for manifest in manifests:
        for dependency in manifest_dependency_paths(manifest):
            resolved = dependency.resolve()
            dependencies[str(resolved)] = resolved
    return [dependencies[key] for key in sorted(dependencies)]


def _inventory_row(manifest_path: Path) -> dict[str, Any]:
    bundle = manifest_path.parent
    manifest = _read_json(manifest_path)
    run_type = _text(manifest.get("run_type"))
    target = TARGETS[run_type]
    summary = _read_csv(bundle / str(target["summary"]))
    config = _read_json(bundle / str(target["config"]))
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    bundle_type = str(target["bundle_type"])
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=run_type,
        require_input_fingerprints=True,
    )
    strict = _strict_record(bundle_type, row, config)
    source = _source_status(bundle_type, row, config)
    bundle_passed = _bundle_passed(bundle_type, row)
    strict_required = _bool(
        strict.get("broker_dispatch_ack_lineage_required", False)
    )
    strict_current = _strict_lineage_current(strict)
    if integrity.passed and bundle_passed and strict_current and source["ready"]:
        status = "strict_ready"
        reason = "bundle already satisfies strict acknowledgement lineage"
    elif source["ready"]:
        status = "regenerate_strict"
        reason = "current source evidence can regenerate a strict bundle"
    else:
        status = "blocked"
        reason = source["detail"] or "required source evidence is unavailable or stale"
    command = (
        ""
        if status == "strict_ready"
        else _regeneration_command(
            bundle_type,
            bundle,
            row,
            config,
        )
    )
    return {
        "bundle_type": target["bundle_type"],
        "run_type": run_type,
        "bundle_path": str(bundle),
        "manifest_path": str(manifest_path),
        "manifest_current": bool(integrity.passed),
        "manifest_error": integrity.error,
        "bundle_passed": bundle_passed,
        "strict_lineage_required": strict_required,
        "strict_lineage_current": strict_current,
        "ack_manifest_path": _text(
            strict.get("broker_dispatch_ack_manifest_path", "")
        ),
        "ack_manifest_sha256": _text(
            strict.get("broker_dispatch_ack_manifest_sha256", "")
        ),
        "source_path": source["path"],
        "source_path_exists": source["exists"],
        "source_manifest_current": source["manifest_current"],
        "source_detail": source["detail"],
        "policy_sha256": _policy_sha256(bundle_type, config, bundle),
        "evidence_identity_sha256": _evidence_identity_sha256(
            bundle_type, row, config
        ),
        "strict_replacement_path": "",
        "strict_replacement_current": False,
        "strict_replacement_matches_policy": False,
        "strict_replacement_matches_evidence": False,
        "strict_replacement_dependency_covered": False,
        "migration_status": status,
        "reason": reason,
        "recommended_command": command,
    }


def _strict_record(
    bundle_type: str,
    summary: pd.Series,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if bundle_type == "provider_ack":
        nested = _mapping(config.get("broker_dispatch_ack"))
        return _mapping(nested.get("summary"))
    if bundle_type == "provider_roundtrip":
        return summary.to_dict() if not summary.empty else {}
    payload = _mapping(config.get("payload"))
    return _mapping(payload.get("broker_dispatch_ack_lineage"))


def _strict_lineage_current(strict: Mapping[str, Any]) -> bool:
    return bool(
        _bool(strict.get("broker_dispatch_ack_lineage_required"))
        and _text(strict.get("broker_dispatch_ack_manifest_run_type"))
        == "broker_dispatch_ack_reconciliation"
        and _text(strict.get("broker_dispatch_ack_manifest_path"))
        and _text(strict.get("broker_dispatch_ack_manifest_sha256"))
        and all(_bool(strict.get(field, False)) for field in STRICT_FIELDS)
    )


def _policy_sha256(
    bundle_type: str,
    config: Mapping[str, Any],
    bundle: Path,
) -> str:
    parameters = _migration_parameters(config, bundle)
    parameters = dict(parameters)
    strict_field = (
        "require_send_packet"
        if bundle_type == "provider_ack"
        else "require_ack_lineage"
    )
    parameters.pop(strict_field, None)
    parameters.pop("lineage_migration_audit_dir", None)
    return _canonical_sha256(
        {"bundle_type": bundle_type, "parameters": parameters}
    )


def _evidence_identity_sha256(
    bundle_type: str,
    summary: pd.Series,
    config: Mapping[str, Any],
) -> str:
    if bundle_type == "provider_ack":
        identity = {
            "provider_send": _identity_path(
                summary.get("provider_broker_dispatch_send_dir")
            ),
            "broker_dispatch": _identity_path(summary.get("broker_dispatch_dir")),
            "broker_send": _identity_path(
                summary.get("broker_dispatch_send_dir")
            ),
            "acks": _identity_path(summary.get("acks_path")),
        }
    elif bundle_type == "provider_roundtrip":
        identity = {
            "provider_ack": _identity_path(
                summary.get("provider_broker_dispatch_ack_dir"),
                strip_strict=True,
            ),
            "broker_dispatch": _identity_path(summary.get("broker_dispatch_dir")),
            "broker_send": _identity_path(
                summary.get("broker_dispatch_send_dir")
            ),
            "broker_ack": _identity_path(summary.get("broker_dispatch_ack_dir")),
        }
    else:
        payload = _mapping(config.get("payload"))
        source_payload = _mapping(payload.get("source"))
        source = _text(summary.get("source_roundtrip_dir")) or _text(
            source_payload.get("path")
        )
        identity = {
            "provider_roundtrip": _identity_path(
                source,
                strip_strict=True,
            )
        }
    return _canonical_sha256(
        {"bundle_type": bundle_type, "evidence": identity}
    )


def _identity_path(value: Any, *, strip_strict: bool = False) -> str:
    path = _path(value)
    if path is None:
        return ""
    if strip_strict and path.name.endswith("_strict"):
        path = path.with_name(path.name[: -len("_strict")])
    return str(path)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _apply_strict_replacement_coverage(
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    if inventory.empty:
        return inventory
    out = inventory.copy()
    path_to_index = {
        str(Path(str(row["bundle_path"])).resolve()): index
        for index, row in out.iterrows()
    }
    ordered = out.assign(
        _bundle_order=out["bundle_type"].map(
            {
                "provider_ack": 1,
                "provider_roundtrip": 2,
                "rehearsal_certificate": 3,
            }
        )
    ).sort_values(["_bundle_order", "bundle_path"], kind="stable")
    for index, row in ordered.iterrows():
        if _text(row.get("migration_status")) == "strict_ready":
            continue
        bundle = Path(str(row["bundle_path"])).resolve()
        replacement = bundle.parent / f"{bundle.name}_strict"
        out.at[index, "strict_replacement_path"] = str(replacement)
        replacement_index = path_to_index.get(str(replacement))
        if replacement_index is None:
            continue
        replacement_row = out.loc[replacement_index]
        replacement_current = bool(
            _text(replacement_row.get("migration_status")) == "strict_ready"
            and _bool(replacement_row.get("manifest_current"))
            and _bool(replacement_row.get("bundle_passed"))
            and _bool(replacement_row.get("strict_lineage_current"))
        )
        policy_matches = bool(
            _text(row.get("policy_sha256"))
            and _text(row.get("policy_sha256"))
            == _text(replacement_row.get("policy_sha256"))
        )
        evidence_matches = bool(
            _text(row.get("evidence_identity_sha256"))
            and _text(row.get("evidence_identity_sha256"))
            == _text(replacement_row.get("evidence_identity_sha256"))
        )
        dependency_covered = _replacement_dependency_covered(
            row,
            out,
            path_to_index,
        )
        out.at[index, "strict_replacement_current"] = replacement_current
        out.at[index, "strict_replacement_matches_policy"] = policy_matches
        out.at[index, "strict_replacement_matches_evidence"] = evidence_matches
        out.at[
            index, "strict_replacement_dependency_covered"
        ] = dependency_covered
        if bool(
            replacement_current
            and policy_matches
            and evidence_matches
            and dependency_covered
            and _bool(row.get("manifest_current"))
            and _bool(row.get("bundle_passed"))
            and _bool(row.get("source_path_exists"))
            and _bool(row.get("source_manifest_current"))
            and not _text(row.get("source_detail"))
        ):
            out.at[index, "migration_status"] = "covered_by_strict"
            out.at[index, "reason"] = (
                "current policy-equivalent strict sibling covers legacy bundle"
            )
            out.at[index, "recommended_command"] = ""
    return out


def _replacement_dependency_covered(
    row: pd.Series,
    inventory: pd.DataFrame,
    path_to_index: Mapping[str, Any],
) -> bool:
    if _text(row.get("bundle_type")) == "provider_ack":
        return True
    source = _path(row.get("source_path"))
    if source is None:
        return False
    source_index = path_to_index.get(str(source))
    if source_index is None:
        return False
    source_status = _text(inventory.loc[source_index].get("migration_status"))
    return source_status in {"strict_ready", "covered_by_strict"}


def _source_status(
    bundle_type: str,
    summary: pd.Series,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if bundle_type == "provider_ack":
        source = _path(
            summary.get("provider_broker_dispatch_send_dir", "")
            if not summary.empty
            else ""
        )
        ack_file = _path(summary.get("acks_path", "") if not summary.empty else "")
        manifest_current = _source_manifest_current(
            source,
            "provider_market_data_imbalance_broker_dispatch_send",
        )
        ready = bool(
            source is not None
            and source.is_dir()
            and ack_file is not None
            and ack_file.is_file()
            and manifest_current
        )
        detail = "" if ready else "provider send bundle or raw acknowledgement file is missing/stale"
        return _source_record(source, ready, manifest_current, detail)
    if bundle_type == "provider_roundtrip":
        source = _path(
            summary.get("provider_broker_dispatch_ack_dir", "")
            if not summary.empty
            else ""
        )
        manifest_current = _source_manifest_current(
            source,
            "provider_market_data_imbalance_broker_dispatch_ack",
        )
        ready = bool(source is not None and source.is_dir() and manifest_current)
        detail = "" if ready else "provider acknowledgement bundle is missing or stale"
        return _source_record(source, ready, manifest_current, detail)
    payload = _mapping(config.get("payload"))
    source_payload = _mapping(payload.get("source"))
    source = _path(
        summary.get("source_roundtrip_dir", "")
        if not summary.empty
        else source_payload.get("path", "")
    )
    manifest_current = _source_manifest_current(
        source,
        "provider_market_data_imbalance_broker_dispatch_roundtrip",
    )
    source_summary = (
        _read_csv(
            source
            / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
        )
        if source is not None
        else pd.DataFrame()
    )
    strict_ready = bool(
        not source_summary.empty
        and _bool(source_summary.iloc[0].get("broker_dispatch_ack_lineage_gate_passed"))
    )
    ready = bool(
        source is not None
        and source.is_dir()
        and manifest_current
        and strict_ready
    )
    detail = "" if ready else "strict provider roundtrip source is missing, stale, or lineage-blocked"
    return _source_record(source, ready, manifest_current, detail)


def _source_record(
    source: Path | None,
    ready: bool,
    manifest_current: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "path": "" if source is None else str(source),
        "exists": bool(source is not None and source.exists()),
        "manifest_current": manifest_current,
        "ready": ready,
        "detail": detail,
    }


def _source_manifest_current(source: Path | None, run_type: str) -> bool:
    if source is None or not source.is_dir():
        return False
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        return False
    if not verify_experiment_manifest(
        manifest_path,
        expected_run_type=run_type,
        require_input_fingerprints=True,
    ).passed:
        return False
    for dependency in manifest_dependency_paths(manifest_path):
        nested_manifest = (
            dependency / "manifest.json"
            if dependency.is_dir()
            else dependency
            if dependency.name == "manifest.json"
            else None
        )
        if nested_manifest is None or not nested_manifest.is_file():
            continue
        nested = _read_json(nested_manifest)
        nested_run_type = _text(nested.get("run_type"))
        if not nested_run_type or not verify_experiment_manifest(
            nested_manifest,
            expected_run_type=nested_run_type,
        ).passed:
            return False
    return True


def _bundle_passed(bundle_type: str, row: pd.Series) -> bool:
    if row.empty:
        return False
    field = "ready" if bundle_type == "rehearsal_certificate" else "passed"
    return _bool(row.get(field, False))


def _regeneration_command(
    bundle_type: str,
    bundle: Path,
    row: pd.Series,
    config: Mapping[str, Any],
) -> str:
    output = _strict_output_path(bundle)
    parameters = _migration_parameters(config, bundle)
    if bundle_type == "provider_ack":
        provider_send = _text(row.get("provider_broker_dispatch_send_dir", ""))
        acks = _text(row.get("acks_path", ""))
        parts = [
            "python -m hft_cli",
            "reconcile-provider-market-data-imbalance-broker-dispatch",
            "--provider-broker-dispatch-send",
            _quote(provider_send),
            "--acks",
            _quote(acks),
            "--out",
            _quote(output),
        ]
        _append_path_option(parts, "--broker-dispatch", row.get("broker_dispatch_dir"))
        for field, option in (
            (
                "require_provider_broker_dispatch_send_ready",
                "--allow-unready-provider-broker-dispatch-send",
            ),
            (
                "require_broker_dispatch_ack_passed",
                "--allow-failed-broker-dispatch-ack",
            ),
            (
                "use_provider_broker_dispatch_send_inputs",
                "--no-use-provider-broker-dispatch-send-inputs",
            ),
            ("require_dispatch_ready", "--allow-unready-dispatch"),
            ("require_all_acked", "--allow-missing-acks"),
        ):
            _append_false_option(parts, parameters, field, option)
        for field, option in (
            ("require_route_readiness", "--require-route-readiness"),
            ("require_dispatch_roundtrip", "--require-dispatch-roundtrip"),
            ("allow_rejections", "--allow-rejections"),
        ):
            _append_true_option(parts, parameters, field, option)
        for field, option in (
            ("max_duplicate_ack_orders", "--max-duplicate-ack-orders"),
            ("max_unmatched_acks", "--max-unmatched-acks"),
        ):
            _append_value_option(parts, parameters, field, option)
        parts.extend(
            ["--require-send-packet", "--fail-on-blocked-actions", "--fail-on-breach"]
        )
        return " ".join(parts)
    if bundle_type == "provider_roundtrip":
        provider_ack = _strict_dependency_path(
            _path(row.get("provider_broker_dispatch_ack_dir", "")),
            "provider_market_data_imbalance_broker_dispatch_ack",
        )
        parts = [
            "python -m hft_cli",
            "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
            "--provider-broker-dispatch-ack",
            _quote(provider_ack),
            "--out",
            _quote(output),
        ]
        for option, field in (
            ("--broker-dispatch", "broker_dispatch_dir"),
            ("--broker-dispatch-send", "broker_dispatch_send_dir"),
            ("--broker-dispatch-ack", "broker_dispatch_ack_dir"),
        ):
            _append_path_option(parts, option, row.get(field))
        for field, option in (
            (
                "require_provider_broker_dispatch_ack_passed",
                "--allow-unready-provider-broker-dispatch-ack",
            ),
            (
                "require_broker_dispatch_roundtrip_passed",
                "--allow-failed-broker-dispatch-roundtrip",
            ),
            (
                "use_provider_broker_dispatch_ack_inputs",
                "--no-use-provider-broker-dispatch-ack-inputs",
            ),
            ("require_dispatch_ready", "--allow-unready-dispatch"),
            ("require_send_ready", "--allow-unready-send"),
            ("require_ack_passed", "--allow-failed-ack"),
            ("require_identity_match", "--allow-identity-mismatch"),
            ("require_submission_disabled", "--allow-submission-enabled"),
            ("require_all_requests_acked", "--allow-missing-request-acks"),
        ):
            _append_false_option(parts, parameters, field, option)
        target_mode = _text(parameters.get("target_mode"))
        if target_mode:
            parts.extend(["--target-mode", target_mode])
        for field, option in (
            ("require_route_readiness", "--require-route-readiness"),
            ("require_dispatch_roundtrip", "--require-dispatch-roundtrip"),
            ("allow_rejections", "--allow-rejections"),
        ):
            _append_true_option(parts, parameters, field, option)
        for field, option in (
            ("max_duplicate_ack_orders", "--max-duplicate-ack-orders"),
            ("max_unmatched_acks", "--max-unmatched-acks"),
            ("max_missing_request_acks", "--max-missing-request-acks"),
            (
                "max_total_failed_component_checks",
                "--max-total-failed-component-checks",
            ),
        ):
            _append_value_option(parts, parameters, field, option)
        parts.extend(
            ["--require-ack-lineage", "--fail-on-blocked-actions", "--fail-on-breach"]
        )
        return " ".join(parts)
    payload = _mapping(config.get("payload"))
    source_payload = _mapping(payload.get("source"))
    source = _text(row.get("source_roundtrip_dir", "")) or _text(
        source_payload.get("path", "")
    )
    source = _strict_dependency_path(
        _path(source),
        "provider_market_data_imbalance_broker_dispatch_roundtrip",
    )
    parts = [
        "python -m hft_cli",
        "certify-provider-market-data-imbalance-broker-rehearsal",
        "--provider-broker-dispatch-roundtrip",
        _quote(source),
        "--out",
        _quote(output),
    ]
    if parameters and not _bool(parameters.get("require_clean_recorded_git", True)):
        parts.append("--allow-recorded-dirty-git")
    _append_true_option(
        parts,
        parameters,
        "require_sealed_provider_receipts",
        "--require-sealed-provider-receipts",
    )
    _append_value_option(
        parts, parameters, "max_manifest_count", "--max-manifests"
    )
    parts.extend(
        ["--require-ack-lineage", "--fail-on-blocked-actions", "--fail-on-breach"]
    )
    return " ".join(parts)


def _migration_parameters(config: Mapping[str, Any], bundle: Path) -> dict[str, Any]:
    parameters = _mapping(config.get("parameters"))
    if parameters:
        return parameters
    manifest = _read_json(bundle / "manifest.json")
    return _mapping(_mapping(manifest.get("parameters")).get("config"))


def _strict_dependency_path(source: Path | None, run_type: str) -> str:
    if source is None:
        return ""
    if _bundle_has_strict_lineage(source, run_type):
        return str(source)
    replacement = source.parent / f"{source.name}_strict"
    if _strict_replacement_covers_path(source, replacement, run_type):
        return str(replacement)
    return str(_strict_output_path(source))


def _strict_output_path(bundle: Path) -> Path:
    candidate = bundle.parent / f"{bundle.name}_strict"
    if not candidate.exists():
        return candidate
    rebuilt = bundle.parent / f"{bundle.name}_strict_rebuilt"
    if not rebuilt.exists():
        return rebuilt
    index = 2
    while True:
        numbered = bundle.parent / f"{bundle.name}_strict_rebuilt_{index}"
        if not numbered.exists():
            return numbered
        index += 1


def _strict_replacement_covers_path(
    source: Path,
    replacement: Path,
    run_type: str,
) -> bool:
    target = TARGETS.get(run_type)
    if target is None or not source.is_dir() or not replacement.is_dir():
        return False
    source_integrity = verify_experiment_manifest(
        source / "manifest.json",
        expected_run_type=run_type,
        require_input_fingerprints=True,
    )
    replacement_integrity = verify_experiment_manifest(
        replacement / "manifest.json",
        expected_run_type=run_type,
        require_input_fingerprints=True,
    )
    if not source_integrity.passed or not replacement_integrity.passed:
        return False
    source_summary = _read_csv(source / str(target["summary"]))
    replacement_summary = _read_csv(replacement / str(target["summary"]))
    source_config = _read_json(source / str(target["config"]))
    replacement_config = _read_json(replacement / str(target["config"]))
    source_row = (
        source_summary.iloc[0]
        if not source_summary.empty
        else pd.Series(dtype=object)
    )
    replacement_row = (
        replacement_summary.iloc[0]
        if not replacement_summary.empty
        else pd.Series(dtype=object)
    )
    bundle_type = str(target["bundle_type"])
    source_status = _source_status(bundle_type, source_row, source_config)
    replacement_source_status = _source_status(
        bundle_type,
        replacement_row,
        replacement_config,
    )
    return bool(
        _bundle_passed(bundle_type, source_row)
        and _bundle_passed(bundle_type, replacement_row)
        and source_status["ready"]
        and replacement_source_status["ready"]
        and _strict_lineage_current(
            _strict_record(bundle_type, replacement_row, replacement_config)
        )
        and _policy_sha256(bundle_type, source_config, source)
        == _policy_sha256(bundle_type, replacement_config, replacement)
        and _evidence_identity_sha256(bundle_type, source_row, source_config)
        == _evidence_identity_sha256(
            bundle_type,
            replacement_row,
            replacement_config,
        )
    )


def _bundle_has_strict_lineage(source: Path, run_type: str) -> bool:
    target = TARGETS.get(run_type)
    if target is None or not source.is_dir():
        return False
    integrity = verify_experiment_manifest(
        source / "manifest.json",
        expected_run_type=run_type,
        require_input_fingerprints=True,
    )
    if not integrity.passed:
        return False
    summary = _read_csv(source / str(target["summary"]))
    config = _read_json(source / str(target["config"]))
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    source_status = _source_status(str(target["bundle_type"]), row, config)
    return bool(
        _bundle_passed(str(target["bundle_type"]), row)
        and source_status["ready"]
        and _strict_lineage_current(
            _strict_record(str(target["bundle_type"]), row, config)
        )
    )


def _append_path_option(parts: list[str], option: str, value: Any) -> None:
    text = _text(value)
    if text:
        parts.extend([option, _quote(text)])


def _append_false_option(
    parts: list[str],
    parameters: Mapping[str, Any],
    field: str,
    option: str,
) -> None:
    if field in parameters and not _bool(parameters.get(field)):
        parts.append(option)


def _append_true_option(
    parts: list[str],
    parameters: Mapping[str, Any],
    field: str,
    option: str,
) -> None:
    if _bool(parameters.get(field)):
        parts.append(option)


def _append_value_option(
    parts: list[str],
    parameters: Mapping[str, Any],
    field: str,
    option: str,
) -> None:
    if field in parameters and parameters.get(field) is not None:
        parts.extend([option, _text(parameters.get(field))])


def _checks(
    inventory: pd.DataFrame,
    *,
    discovery_errors: list[str],
    truncated: bool,
    config: ProviderBrokerLineageMigrationConfig,
) -> pd.DataFrame:
    bundle_count = len(inventory)
    blocked = _status_count(inventory, "blocked")
    strict_ready = _status_count(inventory, "strict_ready")
    covered = _status_count(inventory, "covered_by_strict")
    coverage = (strict_ready + covered) / bundle_count if bundle_count else 0.0
    return pd.DataFrame(
        [
            _check("bundles_discovered", bundle_count, ">", 0, bundle_count > 0),
            _check(
                "discovery_errors",
                len(discovery_errors),
                "==",
                0,
                not discovery_errors,
            ),
            _check("discovery_truncated", truncated, "is", False, not truncated),
            _check(
                "blocked_bundles",
                blocked,
                "<=",
                config.max_blocked_bundles,
                blocked <= config.max_blocked_bundles,
            ),
            _check(
                "strict_ready_coverage",
                coverage,
                ">=",
                config.min_strict_ready_coverage,
                coverage >= config.min_strict_ready_coverage,
            ),
        ]
    )


def _summary(
    inventory: pd.DataFrame,
    checks: pd.DataFrame,
    *,
    root_count: int,
    discovery_error_count: int,
    truncated: bool,
    audited_manifest_count: int,
    audited_dependency_count: int,
) -> pd.DataFrame:
    bundle_count = len(inventory)
    strict_ready = _status_count(inventory, "strict_ready")
    covered = _status_count(inventory, "covered_by_strict")
    regenerate = _status_count(inventory, "regenerate_strict")
    blocked = _status_count(inventory, "blocked")
    coverage = (strict_ready + covered) / bundle_count if bundle_count else 0.0
    failed_checks = int((~checks["passed"].astype(bool)).sum())
    ready = bool(bundle_count and failed_checks == 0)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "ready_for_strict_default": ready,
                "authorizes_submission": False,
                "root_count": root_count,
                "bundle_count": bundle_count,
                "audited_manifest_count": audited_manifest_count,
                "audited_dependency_count": audited_dependency_count,
                "provider_ack_bundles": _type_count(inventory, "provider_ack"),
                "provider_roundtrip_bundles": _type_count(
                    inventory, "provider_roundtrip"
                ),
                "rehearsal_certificate_bundles": _type_count(
                    inventory, "rehearsal_certificate"
                ),
                "strict_ready_bundles": strict_ready,
                "strict_replacement_covered_bundles": covered,
                "regenerate_strict_bundles": regenerate,
                "blocked_bundles": blocked,
                "strict_ready_coverage": coverage,
                "discovery_error_count": discovery_error_count,
                "discovery_truncated": truncated,
                "failed_checks": failed_checks,
                "recommendation": (
                    "enable_strict_provider_lineage_defaults"
                    if ready
                    else "regenerate_or_repair_provider_lineage_bundles"
                ),
            }
        ]
    )


def _action_queue(inventory: pd.DataFrame) -> pd.DataFrame:
    if inventory.empty:
        return pd.DataFrame(columns=ACTION_QUEUE_COLUMNS)
    pending = inventory.loc[
        ~inventory["migration_status"].isin(
            ["strict_ready", "covered_by_strict"]
        )
    ].copy()
    pending["bundle_order"] = pending["bundle_type"].map(
        {"provider_ack": 1, "provider_roundtrip": 2, "rehearsal_certificate": 3}
    )
    pending = pending.sort_values(
        ["bundle_order", "bundle_path"], kind="stable"
    )
    rows: list[dict[str, Any]] = []
    for priority, (_, row) in enumerate(pending.iterrows(), start=1):
        status = _text(row.get("migration_status"))
        rows.append(
            {
                "priority": priority,
                "queue_status": "ready" if status == "regenerate_strict" else "blocked",
                "bundle_type": _text(row.get("bundle_type")),
                "bundle_path": _text(row.get("bundle_path")),
                "migration_status": status,
                "action": (
                    "regenerate_with_strict_lineage"
                    if status == "regenerate_strict"
                    else "repair_missing_or_stale_source_evidence"
                ),
                "reason": _text(row.get("reason")),
                "command": _text(row.get("recommended_command")),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _summary_with_actions(
    summary: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    out = summary.copy()
    statuses = (
        action_queue["queue_status"].astype(str)
        if not action_queue.empty
        else pd.Series(dtype=str)
    )
    out["action_queue_count"] = len(action_queue)
    out["ready_action_count"] = int((statuses == "ready").sum())
    out["blocked_action_count"] = int((statuses == "blocked").sum())
    return out


def _config_payload(
    roots: tuple[Path, ...],
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderBrokerLineageMigrationConfig,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "authorizes_submission": False,
        "ready": _bool(summary.get("ready_for_strict_default", False)),
        "roots": [str(root) for root in roots],
        "parameters": asdict(config),
        "summary": _jsonable(summary.to_dict()),
        "checks": [_jsonable(row) for row in checks.to_dict(orient="records")],
        "actions": [
            _jsonable(row) for row in action_queue.to_dict(orient="records")
        ],
    }


def _runbook(
    summary: pd.Series,
    inventory: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Provider Broker Lineage Migration Audit",
        "",
        f"- Ready for strict defaults: {'yes' if _bool(summary['ready_for_strict_default']) else 'no'}",
        f"- Bundles audited: {int(summary['bundle_count'])}",
        f"- Audited manifests sealed: {int(summary['audited_manifest_count'])}",
        f"- Transitive dependencies sealed: {int(summary['audited_dependency_count'])}",
        f"- Strict ready: {int(summary['strict_ready_bundles'])}",
        "- Legacy bundles covered by strict siblings: "
        f"{int(summary['strict_replacement_covered_bundles'])}",
        f"- Regenerate strict: {int(summary['regenerate_strict_bundles'])}",
        f"- Blocked: {int(summary['blocked_bundles'])}",
        f"- Strict-ready coverage: {float(summary['strict_ready_coverage']):.2%}",
        "- Authorizes broker submission: no",
        "",
        "This audit is read-only. Regeneration commands target a new sibling "
        "`_strict` directory and never overwrite existing proof.",
        "",
        "## Inventory",
        "",
    ]
    if inventory.empty:
        lines.append("_No provider proof bundles discovered._")
    else:
        lines.extend(
            [
                "| Type | Status | Current manifest | Bundle |",
                "|---|---|---:|---|",
            ]
        )
        for _, row in inventory.iterrows():
            lines.append(
                f"| {_text(row['bundle_type'])} | {_text(row['migration_status'])} | "
                f"{'yes' if _bool(row['manifest_current']) else 'no'} | "
                f"`{_text(row['bundle_path'])}` |"
            )
    lines.extend(["", "## Actions", ""])
    if action_queue.empty:
        lines.append("_No migration actions. Strict defaults can be enabled._")
    else:
        for _, row in action_queue.iterrows():
            lines.append(
                f"- [{_text(row['queue_status'])}] `{_text(row['bundle_path'])}`: "
                f"{_text(row['reason'])}"
            )
            command = _text(row.get("command"))
            if command:
                lines.append(f"  `{command}`")
    return "\n".join(lines) + "\n"


def _matched_legacy_inventory(
    inventory: pd.DataFrame,
    *,
    bundle_type: str,
    path_field: str,
    source: Path,
) -> pd.DataFrame:
    if inventory.empty or not {
        "bundle_type",
        "migration_status",
        path_field,
    }.issubset(inventory.columns):
        return pd.DataFrame(columns=inventory.columns)
    normalized_paths = inventory[path_field].map(
        lambda value: str(_path(value) or "")
    )
    matched = inventory.loc[
        (inventory["bundle_type"].astype(str) == bundle_type)
        & (inventory["migration_status"].astype(str) == "covered_by_strict")
        & (normalized_paths == str(source))
    ]
    return matched.copy().reset_index(drop=True)


def _covered_inventory_row_current(row: pd.Series) -> bool:
    return bool(
        _text(row.get("strict_replacement_path"))
        and _bool(row.get("manifest_current"))
        and _bool(row.get("bundle_passed"))
        and _bool(row.get("source_path_exists"))
        and _bool(row.get("source_manifest_current"))
        and not _text(row.get("source_detail"))
        and _bool(row.get("strict_replacement_current"))
        and _bool(row.get("strict_replacement_matches_policy"))
        and _bool(row.get("strict_replacement_matches_evidence"))
        and _bool(row.get("strict_replacement_dependency_covered"))
    )


def _all_checks_passed(checks: pd.DataFrame) -> bool:
    required = {
        "bundles_discovered",
        "discovery_errors",
        "discovery_truncated",
        "blocked_bundles",
        "strict_ready_coverage",
    }
    if checks.empty or not {"check", "passed"}.issubset(checks.columns):
        return False
    return bool(
        required.issubset(set(checks["check"].astype(str)))
        and checks["passed"].map(_bool).all()
    )


def _audit_config_matches_summary(
    config: Mapping[str, Any],
    summary: pd.Series,
) -> bool:
    config_summary = _mapping(config.get("summary"))
    if summary.empty or not config_summary:
        return False
    return bool(
        _bool(config.get("ready"))
        == _bool(summary.get("ready_for_strict_default"))
        and not _bool(config.get("authorizes_submission"))
        and _summary_counts_match(config_summary, summary)
    )


def _audit_manifest_matches_summary(
    extra: Mapping[str, Any],
    summary: pd.Series,
) -> bool:
    if summary.empty or not extra:
        return False
    return bool(
        _bool(extra.get("ready"))
        == _bool(summary.get("ready_for_strict_default"))
        and not _bool(extra.get("authorizes_submission"))
        and _summary_counts_match(extra, summary, manifest_extra=True)
    )


def _audit_manifest_inputs_match_summary(
    inputs: Mapping[str, Any],
    summary: pd.Series,
) -> bool:
    if summary.empty:
        return False
    manifest_count = _int(
        summary.get("audited_manifest_count"),
        default=-1,
    )
    dependency_count = _int(
        summary.get("audited_dependency_count"),
        default=-1,
    )
    return bool(
        manifest_count > 0
        and dependency_count > 0
        and _input_item_count(inputs.get("audited_provider_bundles"))
        == manifest_count
        and _input_item_count(inputs.get("audited_provider_manifests"))
        == manifest_count
        and _input_item_count(inputs.get("audited_provider_dependencies"))
        == dependency_count
    )


def _audit_inventory_matches_summary(
    inventory: pd.DataFrame,
    summary: pd.Series,
) -> bool:
    required = {
        "migration_status",
        "manifest_current",
        "bundle_passed",
        "source_manifest_current",
        "strict_lineage_current",
    }
    if inventory.empty or summary.empty or not required.issubset(inventory.columns):
        return False
    statuses = inventory["migration_status"].astype(str)
    strict_rows = inventory.loc[statuses == "strict_ready"]
    covered_rows = inventory.loc[statuses == "covered_by_strict"]
    trusted_statuses = statuses.isin(["strict_ready", "covered_by_strict"])
    strict_current = bool(
        not strict_rows.empty
        and strict_rows["manifest_current"].map(_bool).all()
        and strict_rows["bundle_passed"].map(_bool).all()
        and strict_rows["source_manifest_current"].map(_bool).all()
        and strict_rows["strict_lineage_current"].map(_bool).all()
    )
    covered_current = bool(
        covered_rows.empty
        or all(
            _covered_inventory_row_current(row)
            for _, row in covered_rows.iterrows()
        )
    )
    strict_count = int((statuses == "strict_ready").sum())
    covered_count = int((statuses == "covered_by_strict").sum())
    bundle_count = len(inventory)
    coverage = (strict_count + covered_count) / bundle_count
    return bool(
        trusted_statuses.all()
        and strict_current
        and covered_current
        and bundle_count
        == _int(summary.get("bundle_count"), default=-1)
        and bundle_count
        == _int(summary.get("audited_manifest_count"), default=-1)
        and strict_count
        == _int(summary.get("strict_ready_bundles"), default=-1)
        and covered_count
        == _int(
            summary.get("strict_replacement_covered_bundles"),
            default=-1,
        )
        and _int(summary.get("regenerate_strict_bundles"), default=-1) == 0
        and _int(summary.get("blocked_bundles"), default=-1) == 0
        and coverage
        == _float(summary.get("strict_ready_coverage"), default=-1.0)
    )


def _input_item_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _summary_counts_match(
    record: Mapping[str, Any],
    summary: pd.Series,
    *,
    manifest_extra: bool = False,
) -> bool:
    int_fields = [
        "bundle_count",
        "strict_ready_bundles",
        "strict_replacement_covered_bundles",
        "regenerate_strict_bundles",
        "blocked_bundles",
        "audited_manifest_count",
        "audited_dependency_count",
    ]
    if not manifest_extra:
        int_fields.extend(
            ["failed_checks", "action_queue_count", "blocked_action_count"]
        )
    return bool(
        all(
            _int(record.get(field), default=-1)
            == _int(summary.get(field), default=-2)
            for field in int_fields
        )
        and _float(record.get("strict_ready_coverage"), default=-1.0)
        == _float(summary.get("strict_ready_coverage"), default=-2.0)
    )


def _status_count(inventory: pd.DataFrame, status: str) -> int:
    if inventory.empty:
        return 0
    return int((inventory["migration_status"].astype(str) == status).sum())


def _type_count(inventory: pd.DataFrame, bundle_type: str) -> int:
    if inventory.empty:
        return 0
    return int((inventory["bundle_type"].astype(str) == bundle_type).sum())


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
    }


def _validate_config(config: ProviderBrokerLineageMigrationConfig) -> None:
    if config.max_bundles <= 0:
        raise ValueError("max_bundles must be positive")
    if config.max_blocked_bundles < 0:
        raise ValueError("max_blocked_bundles must be non-negative")
    if not 0.0 <= config.min_strict_ready_coverage <= 1.0:
        raise ValueError("min_strict_ready_coverage must be between 0 and 1")


def _validate_output_location(roots: tuple[Path, ...], output: Path) -> None:
    for root in roots:
        if output == root or output in root.parents:
            raise ValueError(
                "provider lineage migration output must not overwrite an audited root"
            )


def _validate_output_bundle_location(
    manifests: list[Path], output: Path
) -> None:
    for manifest in manifests:
        bundle = manifest.parent.resolve()
        if output == bundle or bundle in output.parents:
            raise ValueError("output directory cannot be inside an audited provider bundle")


def _within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _path(value: Any) -> Path | None:
    text = _text(value)
    return Path(text).resolve() if text else None


def _quote(value: Any) -> str:
    return f'"{str(value).replace(chr(34), chr(34) * 2)}"'


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


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return _text(value).lower() in {"1", "true", "yes", "y", "ready", "pass"}


def _int(value: Any, *, default: int) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value: Any, *, default: float) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
