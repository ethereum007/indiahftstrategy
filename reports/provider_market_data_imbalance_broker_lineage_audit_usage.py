from __future__ import annotations

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
from reports.provider_market_data_imbalance_broker_lineage_migration import (
    provider_broker_lineage_migration_audit_evidence,
    provider_broker_lineage_strict_refresh_plan,
)


RUN_TYPE = "provider_market_data_imbalance_broker_lineage_audit_usage_review"
PROOF_TARGETS = {
    "provider_market_data_imbalance_broker_dispatch_ack": {
        "bundle_type": "provider_ack",
        "summary": "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
        "config": "provider_market_data_imbalance_broker_dispatch_ack_config.json",
        "source_role": "provider_send",
        "source_field": "provider_broker_dispatch_send_dir",
        "strict_field": "require_send_packet",
    },
    "provider_market_data_imbalance_broker_dispatch_roundtrip": {
        "bundle_type": "provider_roundtrip",
        "summary": "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        "config": "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json",
        "source_role": "provider_ack",
        "source_field": "provider_broker_dispatch_ack_dir",
        "strict_field": "require_ack_lineage",
    },
    "provider_market_data_imbalance_broker_rehearsal_certificate": {
        "bundle_type": "rehearsal_certificate",
        "summary": "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
        "config": "provider_market_data_imbalance_broker_rehearsal_certificate.json",
        "source_role": "provider_roundtrip",
        "source_field": "source_roundtrip_dir",
        "strict_field": "require_ack_lineage",
    },
}
EVIDENCE_KEYS = (
    "provided",
    "ready",
    "authorizes_submission",
    "path",
    "manifest_path",
    "manifest_sha256",
    "manifest_current",
    "policy_ready",
    "strict_ready_coverage",
    "blocked_bundles",
    "blocked_action_count",
    "source_role",
    "source_path",
    "source_covered",
    "source_status",
    "strict_replacement_path",
    "strict_replacement_manifest_path",
    "strict_replacement_manifest_sha256",
    "error",
)
BOOL_EVIDENCE_KEYS = {
    "provided",
    "ready",
    "authorizes_submission",
    "manifest_current",
    "policy_ready",
    "source_covered",
}
INT_EVIDENCE_KEYS = {"blocked_bundles", "blocked_action_count"}
FLOAT_EVIDENCE_KEYS = {"strict_ready_coverage"}
READY_STATUSES = {"strict_ready", "audited_legacy_ready"}
INVENTORY_COLUMNS = (
    "bundle_type",
    "run_type",
    "bundle_path",
    "manifest_path",
    "manifest_current",
    "manifest_error",
    "bundle_passed",
    "strict_lineage_required",
    "audit_provided",
    "audit_path",
    "audit_manifest_sha256",
    "audit_manifest_current",
    "audit_policy_ready",
    "audit_source_role",
    "audit_source_path",
    "audit_source_status",
    "audit_source_covered",
    "audit_strict_replacement_path",
    "audit_strict_replacement_manifest_sha256",
    "stored_evidence_consistent",
    "current_evidence_matches_stored",
    "usage_status",
    "reason",
    "refresh_ready",
    "refresh_output_path",
    "refresh_command",
    "refresh_reason",
)
ACTION_COLUMNS = (
    "priority",
    "queue_status",
    "bundle_type",
    "bundle_path",
    "usage_status",
    "action",
    "refresh_output_path",
    "command",
    "reason",
)


@dataclass(frozen=True)
class ProviderBrokerLineageAuditUsageConfig:
    recursive: bool = True
    max_bundles: int = 1000
    max_unaudited_legacy_bundles: int = 0
    max_drifted_audit_bundles: int = 0
    max_strict_with_audit_bundles: int = 0


@dataclass(frozen=True)
class ProviderBrokerLineageAuditUsageReport:
    inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(
            not self.summary.empty
            and self.summary.iloc[0]["ready"]
        )


def provider_broker_lineage_audit_usage_record(
    bundle_dir: str | Path,
) -> dict[str, Any]:
    bundle = Path(bundle_dir).resolve()
    manifest = _read_json(bundle / "manifest.json")
    run_type = _text(manifest.get("run_type"))
    if run_type not in PROOF_TARGETS:
        raise ValueError("provider proof run type is missing or unsupported")
    return _inventory_row(bundle / "manifest.json")


def write_provider_broker_lineage_audit_usage_review(
    roots: list[str | Path] | tuple[str | Path, ...],
    output_dir: str | Path,
    *,
    config: ProviderBrokerLineageAuditUsageConfig | None = None,
) -> ProviderBrokerLineageAuditUsageReport:
    config = config or ProviderBrokerLineageAuditUsageConfig()
    _validate_config(config)
    resolved_roots = tuple(Path(root).resolve() for root in roots)
    if not resolved_roots:
        raise ValueError("at least one provider proof root is required")
    out = Path(output_dir).resolve()
    manifests, discovery_errors, truncated = _discover_manifests(
        resolved_roots,
        recursive=config.recursive,
        max_bundles=config.max_bundles,
        exclude_root=out,
    )
    _validate_output_location(manifests, out)
    dependencies = _dependency_paths(manifests)
    inventory = pd.DataFrame(
        [_inventory_row(path) for path in manifests],
        columns=INVENTORY_COLUMNS,
    )
    checks = _checks(
        inventory,
        discovery_errors=discovery_errors,
        truncated=truncated,
        config=config,
    )
    action_queue = _action_queue(inventory)
    summary = _summary(
        inventory,
        checks,
        action_queue,
        root_count=len(resolved_roots),
        discovery_error_count=len(discovery_errors),
        truncated=truncated,
        dependency_count=len(dependencies),
    )
    config_payload = {
        "schema_version": 1,
        "authorizes_submission": False,
        "ready": bool(summary.iloc[0]["ready"]),
        "roots": [str(root) for root in resolved_roots],
        "parameters": asdict(config),
        "summary": _jsonable(summary.iloc[0].to_dict()),
        "checks": _jsonable(checks.to_dict(orient="records")),
        "actions": _jsonable(action_queue.to_dict(orient="records")),
    }

    out.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(out / "provider_broker_lineage_audit_usage_inventory.csv", index=False)
    checks.to_csv(out / "provider_broker_lineage_audit_usage_checks.csv", index=False)
    summary.to_csv(out / "provider_broker_lineage_audit_usage_summary.csv", index=False)
    action_queue.to_csv(out / "provider_broker_lineage_audit_usage_action_queue.csv", index=False)
    (out / "provider_broker_lineage_audit_usage_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_broker_lineage_audit_usage_runbook.md").write_text(
        _runbook(summary.iloc[0], inventory, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "reviewed_provider_bundles": [path.parent for path in manifests],
            "reviewed_provider_manifests": manifests,
            "reviewed_provider_dependencies": dependencies,
        },
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "authorizes_submission": False,
            "bundle_count": int(summary.iloc[0]["bundle_count"]),
            "strict_ready_bundles": int(summary.iloc[0]["strict_ready_bundles"]),
            "audited_legacy_ready_bundles": int(summary.iloc[0]["audited_legacy_ready_bundles"]),
            "unaudited_legacy_bundles": int(summary.iloc[0]["unaudited_legacy_bundles"]),
            "drifted_audit_bundles": int(summary.iloc[0]["drifted_audit_bundles"]),
            "ready_action_count": int(summary.iloc[0]["ready_action_count"]),
            "blocked_action_count": int(summary.iloc[0]["blocked_action_count"]),
        },
    )
    return ProviderBrokerLineageAuditUsageReport(
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
            for manifest in root.rglob("manifest.json"):
                if not _within(manifest, exclude_root):
                    candidates.add(manifest.resolve())
    selected = []
    for manifest in sorted(candidates, key=lambda path: str(path).lower()):
        if _text(_read_json(manifest).get("run_type")) in PROOF_TARGETS:
            selected.append(manifest)
    truncated = len(selected) > max_bundles
    return selected[:max_bundles], errors, truncated


def _inventory_row(manifest_path: Path) -> dict[str, Any]:
    bundle = manifest_path.parent
    manifest = _read_json(manifest_path)
    run_type = _text(manifest.get("run_type"))
    target = PROOF_TARGETS[run_type]
    summary = _read_csv(bundle / str(target["summary"]))
    summary_row = summary.iloc[0] if len(summary) == 1 else pd.Series(dtype=object)
    config = _read_json(bundle / str(target["config"]))
    parameters = _mapping(_mapping(manifest.get("parameters")).get("config"))
    strict_required = _bool(parameters.get(str(target["strict_field"])))
    bundle_passed = _bool(
        summary_row.get("ready")
        if target["bundle_type"] == "rehearsal_certificate"
        else summary_row.get("passed")
    )
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=run_type,
        require_input_fingerprints=True,
    )
    summary_evidence = _summary_evidence(summary_row)
    config_evidence = _config_evidence(str(target["bundle_type"]), config)
    manifest_evidence = _mapping(_mapping(manifest.get("extra")).get("lineage_migration_audit"))
    evidence_surfaces = (
        summary_evidence,
        config_evidence,
        manifest_evidence,
    )
    audit_provided = any(_audit_claimed(evidence) for evidence in evidence_surfaces)
    stored_consistent = bool(
        not audit_provided
        or (
            all(
                evidence and _bool(evidence.get("provided"))
                for evidence in evidence_surfaces
            )
            and _evidence_matches(summary_evidence, config_evidence)
            and _evidence_matches(summary_evidence, manifest_evidence)
        )
    )
    source_path = _text(summary_row.get(str(target["source_field"])))
    if not source_path and audit_provided:
        source_path = _text(summary_evidence.get("source_path"))
    audit_path = _text(summary_evidence.get("path")) or _text(
        config_evidence.get("path")
    ) or _text(manifest_evidence.get("path"))
    current_evidence = (
        provider_broker_lineage_migration_audit_evidence(
            audit_path,
            source_path=source_path or bundle,
            source_role=str(target["source_role"]),
        )
        if audit_provided
        else {}
    )
    current_matches = bool(
        not audit_provided
        or _evidence_matches(summary_evidence, current_evidence)
    )
    if not integrity.passed:
        status = "audited_legacy_drifted" if audit_provided else "proof_manifest_drifted"
        reason = integrity.error or "provider proof manifest is not current"
    elif strict_required and audit_provided:
        status = "strict_with_audit"
        reason = "strict lineage proof unexpectedly carries a legacy migration audit"
    elif strict_required:
        status = "strict_ready"
        reason = "strict lineage proof is current"
    elif not audit_provided:
        status = "unaudited_legacy"
        reason = "legacy lineage proof has no accepted migration audit"
    elif not stored_consistent:
        status = "audited_legacy_drifted"
        reason = "stored audit evidence disagrees across summary, config, or manifest"
    elif not _bool(current_evidence.get("ready")) or not current_matches:
        status = "audited_legacy_drifted"
        reason = _text(current_evidence.get("error")) or "accepted audit or strict replacement drifted"
    else:
        status = "audited_legacy_ready"
        reason = "legacy lineage proof retains a current exact-source migration audit"
    refresh_plan = (
        provider_broker_lineage_strict_refresh_plan(bundle)
        if status not in READY_STATUSES
        else None
    )
    evidence = (
        current_evidence
        or summary_evidence
        or config_evidence
        or manifest_evidence
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
        "audit_provided": audit_provided,
        "audit_path": _text(evidence.get("path")),
        "audit_manifest_sha256": _text(evidence.get("manifest_sha256")),
        "audit_manifest_current": _bool(evidence.get("manifest_current")),
        "audit_policy_ready": _bool(evidence.get("policy_ready")),
        "audit_source_role": _text(evidence.get("source_role")),
        "audit_source_path": _text(evidence.get("source_path")),
        "audit_source_status": _text(evidence.get("source_status")),
        "audit_source_covered": _bool(evidence.get("source_covered")),
        "audit_strict_replacement_path": _text(evidence.get("strict_replacement_path")),
        "audit_strict_replacement_manifest_sha256": _text(
            evidence.get("strict_replacement_manifest_sha256")
        ),
        "stored_evidence_consistent": stored_consistent,
        "current_evidence_matches_stored": current_matches,
        "usage_status": status,
        "reason": reason,
        "refresh_ready": bool(refresh_plan and refresh_plan.ready),
        "refresh_output_path": (
            ""
            if refresh_plan is None or refresh_plan.output_path is None
            else str(refresh_plan.output_path)
        ),
        "refresh_command": "" if refresh_plan is None else refresh_plan.command,
        "refresh_reason": "" if refresh_plan is None else refresh_plan.reason,
    }


def _summary_evidence(summary: pd.Series) -> dict[str, Any]:
    return {
        key: summary.get(f"lineage_migration_audit_{key}")
        for key in EVIDENCE_KEYS
        if f"lineage_migration_audit_{key}" in summary.index
    }


def _config_evidence(bundle_type: str, config: Mapping[str, Any]) -> dict[str, Any]:
    if bundle_type == "rehearsal_certificate":
        return _mapping(_mapping(config.get("payload")).get("lineage_migration_audit"))
    return _mapping(config.get("lineage_migration_audit"))


def _evidence_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if not left or not right:
        return False
    return all(
        _normalized_evidence_value(key, left.get(key))
        == _normalized_evidence_value(key, right.get(key))
        for key in EVIDENCE_KEYS
    )


def _audit_claimed(evidence: Mapping[str, Any]) -> bool:
    return bool(
        _bool(evidence.get("provided"))
        or _text(evidence.get("path"))
        or _text(evidence.get("manifest_path"))
        or _text(evidence.get("manifest_sha256"))
    )


def _normalized_evidence_value(key: str, value: Any) -> Any:
    if key in BOOL_EVIDENCE_KEYS:
        return _bool(value)
    if key in INT_EVIDENCE_KEYS:
        return _int(value, default=0)
    if key in FLOAT_EVIDENCE_KEYS:
        return _float(value, default=0.0)
    return _text(value)


def _checks(
    inventory: pd.DataFrame,
    *,
    discovery_errors: list[str],
    truncated: bool,
    config: ProviderBrokerLineageAuditUsageConfig,
) -> pd.DataFrame:
    unaudited = _status_count(inventory, "unaudited_legacy")
    drifted = _status_count(inventory, "audited_legacy_drifted") + _status_count(
        inventory, "proof_manifest_drifted"
    )
    strict_with_audit = _status_count(inventory, "strict_with_audit")
    return pd.DataFrame(
        [
            _check("bundles_discovered", len(inventory), ">", 0, len(inventory) > 0),
            _check("discovery_errors", len(discovery_errors), "==", 0, not discovery_errors),
            _check("discovery_truncated", truncated, "is", False, not truncated),
            _check(
                "unaudited_legacy_bundles",
                unaudited,
                "<=",
                config.max_unaudited_legacy_bundles,
                unaudited <= config.max_unaudited_legacy_bundles,
            ),
            _check(
                "drifted_audit_bundles",
                drifted,
                "<=",
                config.max_drifted_audit_bundles,
                drifted <= config.max_drifted_audit_bundles,
            ),
            _check(
                "strict_with_audit_bundles",
                strict_with_audit,
                "<=",
                config.max_strict_with_audit_bundles,
                strict_with_audit <= config.max_strict_with_audit_bundles,
            ),
        ]
    )


def _summary(
    inventory: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    *,
    root_count: int,
    discovery_error_count: int,
    truncated: bool,
    dependency_count: int,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    ready = bool(len(inventory) and failed_checks == 0)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "passed": ready,
                "authorizes_submission": False,
                "root_count": root_count,
                "bundle_count": len(inventory),
                "dependency_count": dependency_count,
                "strict_ready_bundles": _status_count(inventory, "strict_ready"),
                "audited_legacy_ready_bundles": _status_count(inventory, "audited_legacy_ready"),
                "unaudited_legacy_bundles": _status_count(inventory, "unaudited_legacy"),
                "drifted_audit_bundles": _status_count(inventory, "audited_legacy_drifted")
                + _status_count(inventory, "proof_manifest_drifted"),
                "strict_with_audit_bundles": _status_count(inventory, "strict_with_audit"),
                "failed_checks": failed_checks,
                "action_queue_count": len(action_queue),
                "ready_action_count": int(
                    action_queue.get("queue_status", pd.Series(dtype=str)).astype(str).eq("ready").sum()
                ),
                "blocked_action_count": int(
                    action_queue.get("queue_status", pd.Series(dtype=str)).astype(str).eq("blocked").sum()
                ),
                "discovery_error_count": discovery_error_count,
                "discovery_truncated": truncated,
                "recommendation": (
                    "retain_strict_or_audited_legacy_lineage"
                    if ready
                    else "repair_or_regenerate_provider_lineage_proofs"
                ),
            }
        ]
    )


def _action_queue(inventory: pd.DataFrame) -> pd.DataFrame:
    if inventory.empty:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    pending = inventory.loc[
        ~inventory["usage_status"].isin(READY_STATUSES)
    ].copy()
    pending["stage_order"] = pending["bundle_type"].map(
        {
            "provider_ack": 1,
            "provider_roundtrip": 2,
            "rehearsal_certificate": 3,
        }
    ).fillna(99)
    pending = pending.sort_values(
        ["stage_order", "bundle_path"],
        kind="stable",
    )
    rows = []
    for priority, (_, row) in enumerate(pending.iterrows(), start=1):
        status = _text(row["usage_status"])
        action = {
            "unaudited_legacy": "regenerate_with_strict_lineage_or_attach_covered_audit",
            "audited_legacy_drifted": "rerun_migration_audit_and_regenerate_proof",
            "proof_manifest_drifted": "regenerate_current_provider_proof",
            "strict_with_audit": "remove_legacy_audit_from_strict_proof",
        }.get(status, "review_provider_lineage_proof")
        refresh_ready = _bool(row.get("refresh_ready"))
        if refresh_ready:
            action = "regenerate_as_strict_lineage_proof"
        rows.append(
            {
                "priority": priority,
                "queue_status": "ready" if refresh_ready else "blocked",
                "bundle_type": row["bundle_type"],
                "bundle_path": row["bundle_path"],
                "usage_status": status,
                "action": action,
                "refresh_output_path": row.get("refresh_output_path", ""),
                "command": row.get("refresh_command", ""),
                "reason": (
                    f"{row['reason']}; {row.get('refresh_reason', '')}".rstrip("; ")
                ),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_COLUMNS)


def _dependency_paths(manifests: list[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for manifest in manifests:
        for dependency in manifest_dependency_paths(manifest):
            resolved = dependency.resolve()
            found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)]


def _runbook(
    summary: pd.Series,
    inventory: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Provider Broker Lineage Audit Usage Review",
        "",
        f"- Ready: {'yes' if _bool(summary['ready']) else 'no'}",
        f"- Provider proofs reviewed: {int(summary['bundle_count'])}",
        f"- Strict current: {int(summary['strict_ready_bundles'])}",
        f"- Audited legacy current: {int(summary['audited_legacy_ready_bundles'])}",
        f"- Unaudited legacy: {int(summary['unaudited_legacy_bundles'])}",
        f"- Drifted audit/proof: {int(summary['drifted_audit_bundles'])}",
        f"- Strict proofs carrying an audit: {int(summary['strict_with_audit_bundles'])}",
        f"- Ready refresh actions: {int(summary['ready_action_count'])}",
        f"- Blocked refresh actions: {int(summary['blocked_action_count'])}",
        "- Authorizes broker submission: no",
        "",
        "## Proofs",
        "",
    ]
    if inventory.empty:
        lines.append("_No provider lineage proofs discovered._")
    else:
        lines.extend(["| Type | Usage | Proof |", "|---|---|---|"])
        for _, row in inventory.iterrows():
            lines.append(
                f"| {_text(row['bundle_type'])} | {_text(row['usage_status'])} | `{_text(row['bundle_path'])}` |"
            )
    lines.extend(["", "## Actions", ""])
    if action_queue.empty:
        lines.append("_No lineage audit usage actions._")
    else:
        for _, row in action_queue.iterrows():
            lines.append(
                f"- [{row['queue_status']}] `{row['bundle_path']}`: {row['action']} - {row['reason']}"
            )
            command = _text(row.get("command"))
            if command:
                lines.append(f"  `{command}`")
    return "\n".join(lines) + "\n"


def _status_count(inventory: pd.DataFrame, status: str) -> int:
    if inventory.empty:
        return 0
    return int(inventory["usage_status"].astype(str).eq(status).sum())


def _check(name: str, value: Any, operator: str, threshold: Any, passed: bool) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
    }


def _validate_config(config: ProviderBrokerLineageAuditUsageConfig) -> None:
    if config.max_bundles <= 0:
        raise ValueError("max_bundles must be positive")
    for name in (
        "max_unaudited_legacy_bundles",
        "max_drifted_audit_bundles",
        "max_strict_with_audit_bundles",
    ):
        if getattr(config, name) < 0:
            raise ValueError(f"{name} must be non-negative")


def _validate_output_location(manifests: list[Path], output: Path) -> None:
    for manifest in manifests:
        bundle = manifest.parent.resolve()
        if output == bundle or bundle in output.parents:
            raise ValueError("output directory cannot be inside a reviewed provider proof")


def _within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


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
    return _text(value).lower() in {"1", "true", "yes", "y", "ready", "pass", "passed"}


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
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value
