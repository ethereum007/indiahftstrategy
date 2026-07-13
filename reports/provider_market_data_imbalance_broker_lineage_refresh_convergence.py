from __future__ import annotations

import json
import shlex
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
    READY_STATUSES,
    RUN_TYPE as AUDIT_USAGE_RUN_TYPE,
    provider_broker_lineage_audit_usage_record,
)
from reports.provider_market_data_imbalance_broker_lineage_migration import (
    provider_broker_lineage_proof_evidence,
)


RUN_TYPE = "provider_market_data_imbalance_broker_lineage_refresh_convergence"
AUDIT_USAGE_ARTIFACTS = (
    "provider_broker_lineage_audit_usage_inventory.csv",
    "provider_broker_lineage_audit_usage_checks.csv",
    "provider_broker_lineage_audit_usage_summary.csv",
    "provider_broker_lineage_audit_usage_action_queue.csv",
    "provider_broker_lineage_audit_usage_config.json",
    "provider_broker_lineage_audit_usage_runbook.md",
)
SOURCE_OPTIONS = {
    "provider_ack": "--provider-broker-dispatch-send",
    "provider_roundtrip": "--provider-broker-dispatch-ack",
    "rehearsal_certificate": "--provider-broker-dispatch-roundtrip",
}
STRICT_OPTIONS = {
    "provider_ack": "--require-send-packet",
    "provider_roundtrip": "--require-ack-lineage",
    "rehearsal_certificate": "--require-ack-lineage",
}
INVENTORY_COLUMNS = (
    "priority",
    "bundle_type",
    "original_bundle_path",
    "source_usage_status",
    "plan_status",
    "plan_record_consistent",
    "command",
    "expected_output_path",
    "output_exists",
    "output_run_type",
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
    "reason",
)
ACTION_COLUMNS = (
    "priority",
    "queue_status",
    "bundle_type",
    "original_bundle_path",
    "expected_output_path",
    "convergence_status",
    "action",
    "command",
    "reason",
)
SOURCE_INVENTORY_COLUMNS = {
    "bundle_type",
    "bundle_path",
    "usage_status",
    "refresh_ready",
    "refresh_output_path",
    "refresh_command",
}
SOURCE_ACTION_COLUMNS = {
    "priority",
    "queue_status",
    "bundle_type",
    "bundle_path",
    "usage_status",
    "refresh_output_path",
    "command",
}


@dataclass(frozen=True)
class ProviderBrokerLineageRefreshConvergenceReport:
    inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(not self.summary.empty and self.summary.iloc[0]["ready"])


def write_provider_broker_lineage_refresh_convergence(
    audit_usage_dir: str | Path,
    output_dir: str | Path,
) -> ProviderBrokerLineageRefreshConvergenceReport:
    source = Path(audit_usage_dir).resolve()
    out = Path(output_dir).resolve()
    if out == source or source in out.parents:
        raise ValueError("output directory cannot be inside the audit-usage review")

    source_manifest_path = source / "manifest.json"
    source_integrity = verify_experiment_manifest(
        source_manifest_path,
        expected_run_type=AUDIT_USAGE_RUN_TYPE,
        required_artifacts=AUDIT_USAGE_ARTIFACTS,
        require_input_fingerprints=True,
    )
    source_manifest = _read_json(source_manifest_path)
    source_inventory = _read_csv(
        source / "provider_broker_lineage_audit_usage_inventory.csv"
    )
    source_summary = _read_csv(
        source / "provider_broker_lineage_audit_usage_summary.csv"
    )
    source_actions = _read_csv(
        source / "provider_broker_lineage_audit_usage_action_queue.csv"
    )
    source_config = _read_json(
        source / "provider_broker_lineage_audit_usage_config.json"
    )
    summary_row = (
        source_summary.iloc[0]
        if len(source_summary) == 1
        else pd.Series(dtype=object)
    )
    source_non_authorizing = _source_non_authorizing(
        summary_row,
        source_config,
        source_manifest,
    )
    source_consistent = _source_consistent(
        source_inventory,
        source_actions,
        summary_row,
        source_config,
        source_manifest,
    )
    source_trusted = bool(
        source_integrity.passed
        and source_non_authorizing
        and source_consistent
    )

    source_schema_ready = bool(
        SOURCE_INVENTORY_COLUMNS.issubset(source_inventory.columns)
        and SOURCE_ACTION_COLUMNS.issubset(source_actions.columns)
    )
    actions_for_rows = (
        source_actions
        if source_schema_ready
        else pd.DataFrame(columns=sorted(SOURCE_ACTION_COLUMNS))
    )
    rows = [
        _convergence_row(action, source_inventory)
        for _, action in actions_for_rows.sort_values(
            "priority", kind="stable"
        ).iterrows()
    ]
    inventory = pd.DataFrame(rows, columns=INVENTORY_COLUMNS)
    unresolved = _unresolved_count(inventory)
    checks = pd.DataFrame(
        [
            _check(
                "audit_usage_review_current",
                source_integrity.passed,
                "is",
                True,
                source_integrity.passed,
                source_integrity.error,
            ),
            _check(
                "audit_usage_review_non_authorizing",
                source_non_authorizing,
                "is",
                True,
                source_non_authorizing,
                "audit-usage review must explicitly prohibit broker submission",
            ),
            _check(
                "audit_usage_review_consistent",
                source_consistent,
                "is",
                True,
                source_consistent,
                "audit-usage inventory, actions, summary, config, or manifest disagree",
            ),
            _check(
                "unresolved_refresh_actions",
                unresolved,
                "==",
                0,
                unresolved == 0,
                "one or more planned strict refreshes have not converged",
            ),
        ]
    )
    action_queue = _action_queue(
        inventory,
        source_trusted=source_trusted,
        source=source,
        source_error=(
            source_integrity.error
            or ("source_not_non_authorizing" if not source_non_authorizing else "")
            or ("source_artifacts_disagree" if not source_consistent else "")
        ),
    )
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    ready = bool(failed_checks == 0)
    summary = pd.DataFrame(
        [
            {
                "ready": ready,
                "passed": ready,
                "authorizes_submission": False,
                "audit_usage_review_path": str(source),
                "audit_usage_review_current": bool(source_integrity.passed),
                "audit_usage_review_consistent": source_consistent,
                "refresh_required": bool(len(source_actions)),
                "planned_action_count": len(source_actions),
                "converged_action_count": _status_count(inventory, "converged"),
                "missing_output_count": _status_count(inventory, "output_missing"),
                "invalid_output_count": _status_count(inventory, "output_invalid"),
                "blocked_plan_count": _status_count(inventory, "plan_blocked"),
                "unresolved_action_count": unresolved,
                "failed_checks": failed_checks,
                "action_queue_count": len(action_queue),
                "ready_action_count": _queue_status_count(action_queue, "ready"),
                "blocked_action_count": _queue_status_count(action_queue, "blocked"),
                "recommendation": (
                    "no_refresh_required"
                    if ready and not len(source_actions)
                    else "strict_lineage_refresh_converged"
                    if ready
                    else "complete_or_replan_strict_lineage_refresh"
                ),
            }
        ]
    )
    config_payload = {
        "schema_version": 1,
        "ready": ready,
        "authorizes_submission": False,
        "audit_usage_review_path": str(source),
        "policy": {"max_unresolved_actions": 0},
        "summary": _jsonable(summary.iloc[0].to_dict()),
        "checks": _jsonable(checks.to_dict(orient="records")),
        "actions": _jsonable(action_queue.to_dict(orient="records")),
    }

    existing_outputs = [
        Path(path).resolve()
        for path in inventory.get(
            "expected_output_path", pd.Series(dtype=str)
        ).astype(str)
        if path and Path(path).is_dir()
    ]
    for output in existing_outputs:
        if out == output or output in out.parents:
            raise ValueError("output directory cannot be inside a refreshed proof")
    output_manifests = [output / "manifest.json" for output in existing_outputs]
    output_dependencies = _dependency_paths(output_manifests)

    out.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(
        out / "provider_broker_lineage_refresh_convergence_inventory.csv",
        index=False,
    )
    checks.to_csv(
        out / "provider_broker_lineage_refresh_convergence_checks.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_broker_lineage_refresh_convergence_summary.csv",
        index=False,
    )
    action_queue.to_csv(
        out / "provider_broker_lineage_refresh_convergence_action_queue.csv",
        index=False,
    )
    (out / "provider_broker_lineage_refresh_convergence_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_broker_lineage_refresh_convergence_runbook.md").write_text(
        _runbook(summary.iloc[0], inventory, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"policy": {"max_unresolved_actions": 0}},
        inputs={
            "audit_usage_review": source,
            "audit_usage_review_manifest": source_manifest_path,
            "audit_usage_review_dependencies": manifest_dependency_paths(
                source_manifest_path
            ),
            "refreshed_provider_bundles": existing_outputs,
            "refreshed_provider_manifests": output_manifests,
            "refreshed_provider_dependencies": output_dependencies,
        },
        extra={
            "ready": ready,
            "authorizes_submission": False,
            "planned_action_count": len(source_actions),
            "converged_action_count": int(
                summary.iloc[0]["converged_action_count"]
            ),
            "unresolved_action_count": unresolved,
        },
    )
    return ProviderBrokerLineageRefreshConvergenceReport(
        inventory=inventory,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config_payload,
        output_dir=out,
    )


def _convergence_row(
    action: pd.Series,
    source_inventory: pd.DataFrame,
) -> dict[str, Any]:
    bundle_type = _text(action.get("bundle_type"))
    original_path = _resolved_text(action.get("bundle_path"))
    expected_output = _resolved_text(action.get("refresh_output_path"))
    command = _text(action.get("command"))
    plan_status = _text(action.get("queue_status"))
    matches = source_inventory.loc[
        source_inventory.get(
            "bundle_path", pd.Series(dtype=str)
        ).map(_resolved_text).eq(original_path)
    ]
    source_row = matches.iloc[0] if len(matches) == 1 else pd.Series(dtype=object)
    plan_record_consistent = bool(
        len(matches) == 1
        and _text(source_row.get("bundle_type")) == bundle_type
        and _text(source_row.get("usage_status"))
        == _text(action.get("usage_status"))
        and _bool(source_row.get("refresh_ready")) == (plan_status == "ready")
        and _resolved_text(source_row.get("refresh_output_path"))
        == expected_output
        and _text(source_row.get("refresh_command")) == command
    )
    output = Path(expected_output) if expected_output else None
    output_exists = bool(output is not None and output.is_dir())
    original = provider_broker_lineage_proof_evidence(original_path)
    refreshed = (
        provider_broker_lineage_proof_evidence(output)
        if output_exists and output is not None
        else {}
    )
    try:
        usage = (
            provider_broker_lineage_audit_usage_record(output)
            if output_exists and output is not None
            else {}
        )
    except ValueError:
        usage = {}
    output_manifest = (
        _read_json(output / "manifest.json")
        if output_exists and output is not None
        else {}
    )
    output_non_authorizing = bool(
        "authorizes_submission" in _mapping(output_manifest.get("extra"))
        and not _bool(
            _mapping(output_manifest.get("extra")).get(
                "authorizes_submission"
            )
        )
    )
    command_output = _command_option(command, "--out")
    command_source = _command_option(command, SOURCE_OPTIONS.get(bundle_type, ""))
    output_source = _resolved_text(refreshed.get("source_path"))
    command_output_matches = bool(
        expected_output
        and _resolved_text(command_output) == expected_output
    )
    command_source_matches = bool(
        command_source
        and output_source
        and _resolved_text(command_source) == output_source
    )
    command_requires_strict = bool(
        STRICT_OPTIONS.get(bundle_type)
        and STRICT_OPTIONS[bundle_type] in _command_tokens(command)
    )
    command_omits_legacy = not any(
        option in _command_tokens(command)
        for option in (
            "--lineage-migration-audit",
            "--allow-legacy-send-lineage",
            "--allow-legacy-ack-lineage",
        )
    )
    policy_matches = bool(
        _text(original.get("policy_sha256"))
        and _text(original.get("policy_sha256"))
        == _text(refreshed.get("policy_sha256"))
    )
    evidence_matches = bool(
        _text(original.get("evidence_identity_sha256"))
        and _text(original.get("evidence_identity_sha256"))
        == _text(refreshed.get("evidence_identity_sha256"))
    )
    output_audit_provided = _bool(usage.get("audit_provided"))
    converged = bool(
        plan_status == "ready"
        and plan_record_consistent
        and output_exists
        and _text(refreshed.get("bundle_type")) == bundle_type
        and _bool(refreshed.get("manifest_current"))
        and _bool(refreshed.get("bundle_passed"))
        and _bool(refreshed.get("strict_lineage_required"))
        and _bool(refreshed.get("strict_lineage_current"))
        and _bool(refreshed.get("source_manifest_current"))
        and _text(refreshed.get("migration_status")) == "strict_ready"
        and _text(usage.get("usage_status")) == "strict_ready"
        and not output_audit_provided
        and output_non_authorizing
        and policy_matches
        and evidence_matches
        and command_output_matches
        and command_source_matches
        and command_requires_strict
        and command_omits_legacy
    )
    if plan_status != "ready" or not plan_record_consistent:
        status = "plan_blocked"
        reason = "source refresh plan is blocked or inconsistent"
    elif not output_exists:
        status = "output_missing"
        reason = "planned strict refresh output has not been generated"
    elif converged:
        status = "converged"
        reason = "planned strict sibling is current, equivalent, and audit-free"
    else:
        status = "output_invalid"
        reason = "generated output does not satisfy the sealed refresh plan"
    return {
        "priority": _int(action.get("priority"), default=0),
        "bundle_type": bundle_type,
        "original_bundle_path": original_path,
        "source_usage_status": _text(action.get("usage_status")),
        "plan_status": plan_status,
        "plan_record_consistent": plan_record_consistent,
        "command": command,
        "expected_output_path": expected_output,
        "output_exists": output_exists,
        "output_run_type": _text(refreshed.get("run_type")),
        "output_manifest_current": _bool(refreshed.get("manifest_current")),
        "output_bundle_passed": _bool(refreshed.get("bundle_passed")),
        "output_strict_lineage_required": _bool(
            refreshed.get("strict_lineage_required")
        ),
        "output_strict_lineage_current": _bool(
            refreshed.get("strict_lineage_current")
        ),
        "output_source_manifest_current": _bool(
            refreshed.get("source_manifest_current")
        ),
        "output_non_authorizing": output_non_authorizing,
        "output_audit_provided": output_audit_provided,
        "policy_matches": policy_matches,
        "evidence_identity_matches": evidence_matches,
        "command_output_matches": command_output_matches,
        "command_source_matches": command_source_matches,
        "command_requires_strict": command_requires_strict,
        "command_omits_legacy_audit": command_omits_legacy,
        "convergence_status": status,
        "reason": reason,
    }


def _source_non_authorizing(
    summary: pd.Series,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bool:
    return bool(
        not summary.empty
        and "authorizes_submission" in summary.index
        and not _bool(summary.get("authorizes_submission"))
        and config.get("authorizes_submission") is False
        and _mapping(manifest.get("extra")).get("authorizes_submission") is False
    )


def _source_consistent(
    inventory: pd.DataFrame,
    actions: pd.DataFrame,
    summary: pd.Series,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> bool:
    if (
        summary.empty
        or not SOURCE_INVENTORY_COLUMNS.issubset(inventory.columns)
        or not SOURCE_ACTION_COLUMNS.issubset(actions.columns)
    ):
        return False
    pending = inventory.loc[~inventory["usage_status"].isin(READY_STATUSES)]
    config_actions = config.get("actions", [])
    config_summary = _mapping(config.get("summary"))
    manifest_extra = _mapping(manifest.get("extra"))
    return bool(
        len(pending) == len(actions)
        and _int(summary.get("action_queue_count"), default=-1) == len(actions)
        and isinstance(config_actions, list)
        and len(config_actions) == len(actions)
        and _source_action_records_match(actions, config_actions)
        and _bool(config_summary.get("ready")) == _bool(summary.get("ready"))
        and _bool(config_summary.get("authorizes_submission"))
        == _bool(summary.get("authorizes_submission"))
        and _int(config_summary.get("action_queue_count"), default=-1)
        == len(actions)
        and _int(config_summary.get("ready_action_count"), default=-1)
        == _queue_status_count(actions, "ready")
        and _int(config_summary.get("blocked_action_count"), default=-1)
        == _queue_status_count(actions, "blocked")
        and _int(manifest_extra.get("ready_action_count"), default=-1)
        == _queue_status_count(actions, "ready")
        and _int(manifest_extra.get("blocked_action_count"), default=-1)
        == _queue_status_count(actions, "blocked")
        and actions["bundle_path"].map(_resolved_text).is_unique
    )


def _source_action_records_match(
    actions: pd.DataFrame,
    config_actions: list[Any],
) -> bool:
    if len(actions) != len(config_actions):
        return False
    config_rows = [
        _mapping(row) for row in config_actions if isinstance(row, Mapping)
    ]
    if len(config_rows) != len(config_actions):
        return False
    csv_rows = actions.sort_values("priority", kind="stable").to_dict(
        orient="records"
    )
    config_rows.sort(key=lambda row: _int(row.get("priority"), default=0))
    for csv_row, config_row in zip(csv_rows, config_rows):
        for field in SOURCE_ACTION_COLUMNS:
            left = csv_row.get(field)
            right = config_row.get(field)
            if field == "priority":
                matches = _int(left, default=-1) == _int(right, default=-1)
            elif field in {"bundle_path", "refresh_output_path"}:
                matches = _resolved_text(left) == _resolved_text(right)
            else:
                matches = _text(left) == _text(right)
            if not matches:
                return False
    return True


def _action_queue(
    inventory: pd.DataFrame,
    *,
    source_trusted: bool,
    source: Path,
    source_error: str,
) -> pd.DataFrame:
    if not source_trusted:
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "blocked",
                    "bundle_type": "audit_usage_review",
                    "original_bundle_path": str(source),
                    "expected_output_path": "",
                    "convergence_status": "source_review_invalid",
                    "action": "regenerate_current_audit_usage_review",
                    "command": "",
                    "reason": source_error or "audit-usage review is not trusted",
                }
            ],
            columns=ACTION_COLUMNS,
        )
    rows = []
    for _, row in inventory.loc[
        inventory.get("convergence_status", pd.Series(dtype=str)) != "converged"
    ].iterrows():
        status = _text(row.get("convergence_status"))
        missing = status == "output_missing"
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "ready" if missing else "blocked",
                "bundle_type": row.get("bundle_type", ""),
                "original_bundle_path": row.get("original_bundle_path", ""),
                "expected_output_path": row.get("expected_output_path", ""),
                "convergence_status": status,
                "action": (
                    "execute_planned_strict_refresh"
                    if missing
                    else "rerun_audit_usage_review_for_fresh_target"
                    if status == "output_invalid"
                    else "repair_source_proof_and_rerun_audit_usage_review"
                ),
                "command": row.get("command", "") if missing else "",
                "reason": row.get("reason", ""),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_COLUMNS)


def _runbook(
    summary: pd.Series,
    inventory: pd.DataFrame,
    actions: pd.DataFrame,
) -> str:
    lines = [
        "# Provider Broker Lineage Refresh Convergence",
        "",
        f"- Ready: {'yes' if _bool(summary['ready']) else 'no'}",
        f"- Planned actions: {int(summary['planned_action_count'])}",
        f"- Converged actions: {int(summary['converged_action_count'])}",
        f"- Unresolved actions: {int(summary['unresolved_action_count'])}",
        "- Authorizes broker submission: no",
        "",
        "## Convergence",
        "",
    ]
    if inventory.empty:
        lines.append("_No strict refresh was required._")
    else:
        lines.extend(["| Type | Status | Output |", "|---|---|---|"])
        for _, row in inventory.iterrows():
            lines.append(
                f"| {row['bundle_type']} | {row['convergence_status']} | `{row['expected_output_path']}` |"
            )
    lines.extend(["", "## Actions", ""])
    if actions.empty:
        lines.append("_No convergence actions._")
    else:
        for _, row in actions.iterrows():
            lines.append(
                f"- [{row['queue_status']}] {row['action']}: {row['reason']}"
            )
            if _text(row.get("command")):
                lines.append(f"  `{row['command']}`")
    return "\n".join(lines) + "\n"


def _command_tokens(command: str) -> list[str]:
    if not command:
        return []
    try:
        values = shlex.split(command, posix=False)
    except ValueError:
        return []
    return [value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value for value in values]


def _command_option(command: str, option: str) -> str:
    if not option:
        return ""
    tokens = _command_tokens(command)
    try:
        index = tokens.index(option)
    except ValueError:
        return ""
    return tokens[index + 1] if index + 1 < len(tokens) else ""


def _dependency_paths(manifests: list[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for manifest in manifests:
        if not manifest.is_file():
            continue
        for dependency in manifest_dependency_paths(manifest):
            resolved = dependency.resolve()
            found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)]


def _unresolved_count(inventory: pd.DataFrame) -> int:
    return int(len(inventory) - _status_count(inventory, "converged"))


def _status_count(inventory: pd.DataFrame, status: str) -> int:
    if inventory.empty:
        return 0
    return int(inventory["convergence_status"].astype(str).eq(status).sum())


def _queue_status_count(actions: pd.DataFrame, status: str) -> int:
    if actions.empty or "queue_status" not in actions:
        return 0
    return int(actions["queue_status"].astype(str).eq(status).sum())


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
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value
