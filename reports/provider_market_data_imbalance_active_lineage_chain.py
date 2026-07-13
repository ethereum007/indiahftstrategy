from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.provider_lineage_selection import (
    normalize_provider_lineage_selection_contract,
    provider_lineage_selection_contract_from_config,
    provider_lineage_selection_contract_from_manifest,
    provider_lineage_selection_contract_from_summary,
    provider_lineage_selection_contract_valid,
    provider_lineage_selection_contracts_match,
)


RUN_TYPE = "provider_market_data_imbalance_active_lineage_chain_audit"
CERTIFICATE_RUN_TYPE = (
    "provider_market_data_imbalance_broker_rehearsal_certificate"
)
READY_NEXT_GATE = "retain-provider-market-data-imbalance-active-lineage-chain-audit"
REPAIR_NEXT_GATE = "review-provider-market-data-imbalance-route-readiness"

CHAIN_ARTIFACTS = (
    "provider_market_data_imbalance_active_lineage_chain.csv",
    "provider_market_data_imbalance_active_lineage_manifest_inventory.csv",
    "provider_market_data_imbalance_active_lineage_chain_checks.csv",
    "provider_market_data_imbalance_active_lineage_chain_summary.csv",
    "provider_market_data_imbalance_active_lineage_chain_action_queue.csv",
    "provider_market_data_imbalance_active_lineage_chain_config.json",
    "provider_market_data_imbalance_active_lineage_chain_runbook.md",
)


@dataclass(frozen=True)
class _BoundarySpec:
    sequence: int
    stage: str
    run_type: str
    summary_file: str
    config_file: str
    runbook_file: str
    ready_field: str = "ready"

    @property
    def required_artifacts(self) -> tuple[str, ...]:
        return (self.summary_file, self.config_file, self.runbook_file)


BOUNDARIES = (
    _BoundarySpec(
        1,
        "route_readiness",
        "provider_market_data_imbalance_route_readiness",
        "provider_market_data_imbalance_route_readiness_summary.csv",
        "provider_market_data_imbalance_route_readiness_config.json",
        "provider_market_data_imbalance_route_readiness_runbook.md",
    ),
    _BoundarySpec(
        2,
        "scaleup",
        "provider_market_data_imbalance_scaleup_plan",
        "provider_market_data_imbalance_scaleup_summary.csv",
        "provider_market_data_imbalance_scaleup_config.json",
        "provider_market_data_imbalance_scaleup_runbook.md",
    ),
    _BoundarySpec(
        3,
        "runtime_telemetry",
        "provider_market_data_imbalance_runtime_telemetry_snapshot",
        "provider_market_data_imbalance_runtime_telemetry_summary.csv",
        "provider_market_data_imbalance_runtime_telemetry_config.json",
        "provider_market_data_imbalance_runtime_telemetry_runbook.md",
    ),
    _BoundarySpec(
        4,
        "runtime_guard",
        "provider_market_data_imbalance_runtime_guard",
        "provider_market_data_imbalance_runtime_guard_summary.csv",
        "provider_market_data_imbalance_runtime_guard_config.json",
        "provider_market_data_imbalance_runtime_guard_runbook.md",
    ),
    _BoundarySpec(
        5,
        "runtime_session",
        "provider_market_data_imbalance_runtime_session",
        "provider_market_data_imbalance_runtime_session_summary.csv",
        "provider_market_data_imbalance_runtime_session_config.json",
        "provider_market_data_imbalance_runtime_session_runbook.md",
    ),
    _BoundarySpec(
        6,
        "broker_readiness",
        "provider_market_data_imbalance_broker_readiness",
        "provider_market_data_imbalance_broker_readiness_summary.csv",
        "provider_market_data_imbalance_broker_readiness_config.json",
        "provider_market_data_imbalance_broker_readiness_runbook.md",
    ),
    _BoundarySpec(
        7,
        "cutover",
        "provider_market_data_imbalance_cutover",
        "provider_market_data_imbalance_cutover_summary.csv",
        "provider_market_data_imbalance_cutover_config.json",
        "provider_market_data_imbalance_cutover_runbook.md",
    ),
    _BoundarySpec(
        8,
        "route_enable",
        "provider_market_data_imbalance_route_enable",
        "provider_market_data_imbalance_route_enable_summary.csv",
        "provider_market_data_imbalance_route_enable_config.json",
        "provider_market_data_imbalance_route_enable_runbook.md",
    ),
    _BoundarySpec(
        9,
        "broker_dispatch",
        "provider_market_data_imbalance_broker_dispatch",
        "provider_market_data_imbalance_broker_dispatch_summary.csv",
        "provider_market_data_imbalance_broker_dispatch_config.json",
        "provider_market_data_imbalance_broker_dispatch_runbook.md",
    ),
    _BoundarySpec(
        10,
        "broker_dispatch_send",
        "provider_market_data_imbalance_broker_dispatch_send",
        "provider_market_data_imbalance_broker_dispatch_send_summary.csv",
        "provider_market_data_imbalance_broker_dispatch_send_config.json",
        "provider_market_data_imbalance_broker_dispatch_send_runbook.md",
    ),
    _BoundarySpec(
        11,
        "broker_dispatch_ack",
        "provider_market_data_imbalance_broker_dispatch_ack",
        "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
        "provider_market_data_imbalance_broker_dispatch_ack_config.json",
        "provider_market_data_imbalance_broker_dispatch_ack_runbook.md",
        "passed",
    ),
    _BoundarySpec(
        12,
        "broker_dispatch_roundtrip",
        "provider_market_data_imbalance_broker_dispatch_roundtrip",
        "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json",
        "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md",
        "passed",
    ),
    _BoundarySpec(
        13,
        "rehearsal_certificate",
        CERTIFICATE_RUN_TYPE,
        "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
        "provider_market_data_imbalance_broker_rehearsal_certificate.json",
        "provider_market_data_imbalance_broker_rehearsal_certificate_runbook.md",
    ),
)

MANIFEST_INVENTORY_COLUMNS = (
    "depth",
    "manifest_path",
    "bundle_path",
    "run_type",
    "manifest_sha256",
    "readable",
    "current",
    "artifact_count",
    "artifact_match_count",
    "input_fingerprint_count",
    "input_fingerprint_match_count",
    "direct_manifest_dependency_count",
    "expected_boundary",
    "error",
)

CHAIN_COLUMNS = (
    "sequence",
    "stage",
    "run_type",
    "manifest_count",
    "bundle_path",
    "manifest_path",
    "manifest_sha256",
    "summary_path",
    "config_path",
    "artifacts_readable",
    "manifest_current",
    "stage_ready",
    "summary_contract_valid",
    "config_contract_valid",
    "manifest_contract_valid",
    "contract_surfaces_match",
    "canonical_contract_match",
    "contract_sha256",
    "previous_stage",
    "previous_bundle_path",
    "direct_predecessor_bound",
    "authorizing_claim_count",
    "non_authorizing",
    "certificate_payload_sha256_current",
    "certificate_cycle_id_current",
    "passed",
    "reason",
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

ACTION_COLUMNS = (
    "priority",
    "queue_status",
    "stage",
    "check",
    "action",
    "reason",
    "next_gate",
    "next_gate_help_command",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceActiveLineageChainConfig:
    max_manifest_count: int = 256


@dataclass(frozen=True)
class ProviderMarketDataImbalanceActiveLineageChainReport:
    chain: pd.DataFrame
    manifest_inventory: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(not self.summary.empty and self.summary.iloc[0]["ready"])


def write_provider_market_data_imbalance_active_lineage_chain_audit(
    certificate_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceActiveLineageChainConfig | None = None,
) -> ProviderMarketDataImbalanceActiveLineageChainReport:
    config = config or ProviderMarketDataImbalanceActiveLineageChainConfig()
    _validate_config(config)
    certificate_root = Path(certificate_dir).resolve()
    out = Path(output_dir).resolve()
    _validate_output_location(certificate_root, out)

    certificate_manifest = certificate_root / "manifest.json"
    manifest_inventory, manifest_payloads, direct_dependencies, truncated = (
        _discover_manifests(
            certificate_manifest,
            max_manifest_count=config.max_manifest_count,
        )
    )
    _validate_discovered_output_locations(manifest_inventory, out)
    chain, canonical_contract = _build_chain(
        manifest_inventory,
        manifest_payloads,
        direct_dependencies,
    )
    chain_digest = _chain_digest(chain)
    checks = _checks(
        certificate_root,
        chain,
        manifest_inventory,
        canonical_contract,
        truncated=truncated,
    )
    ready = bool(not checks.empty and checks["passed"].map(_bool).all())
    action_queue = _action_queue(chain, checks)
    summary = _summary(
        certificate_root,
        chain,
        manifest_inventory,
        checks,
        action_queue,
        canonical_contract,
        chain_digest,
        truncated=truncated,
        ready=ready,
    )
    config_payload = {
        "schema_version": 1,
        "ready": ready,
        "authorizes_submission": False,
        "certificate_dir": str(certificate_root),
        "parameters": asdict(config),
        "provider_lineage_selection_contract": canonical_contract,
        "chain_digest_sha256": chain_digest,
        "summary": _jsonable(summary.iloc[0].to_dict()),
        "checks": _jsonable(checks.to_dict(orient="records")),
        "chain": _jsonable(chain.to_dict(orient="records")),
        "actions": _jsonable(action_queue.to_dict(orient="records")),
    }

    out.mkdir(parents=True, exist_ok=True)
    chain.to_csv(out / CHAIN_ARTIFACTS[0], index=False)
    manifest_inventory.to_csv(out / CHAIN_ARTIFACTS[1], index=False)
    checks.to_csv(out / CHAIN_ARTIFACTS[2], index=False)
    summary.to_csv(out / CHAIN_ARTIFACTS[3], index=False)
    action_queue.to_csv(out / CHAIN_ARTIFACTS[4], index=False)
    (out / CHAIN_ARTIFACTS[5]).write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / CHAIN_ARTIFACTS[6]).write_text(
        _runbook(summary.iloc[0], chain, checks, action_queue),
        encoding="utf-8",
    )

    stage_bundles = _existing_paths(chain.get("bundle_path", pd.Series(dtype=str)))
    stage_manifests = _existing_paths(
        chain.get("manifest_path", pd.Series(dtype=str))
    )
    recursive_dependencies = (
        manifest_dependency_paths(certificate_manifest)
        if certificate_manifest.is_file()
        else []
    )
    inputs: dict[str, Any] = {}
    if certificate_root.exists():
        inputs["rehearsal_certificate"] = certificate_root
    if certificate_manifest.is_file():
        inputs["rehearsal_certificate_manifest"] = certificate_manifest
    if stage_bundles:
        inputs["audited_stage_bundles"] = stage_bundles
    if stage_manifests:
        inputs["audited_stage_manifests"] = stage_manifests
    if recursive_dependencies:
        inputs["audited_recursive_dependencies"] = recursive_dependencies
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": ready,
            "authorizes_submission": False,
            "provider_lineage_selection_contract": canonical_contract,
            "chain_digest_sha256": chain_digest,
            "expected_stage_count": len(BOUNDARIES),
            "passed_stage_count": int(chain["passed"].map(_bool).sum()),
            "recursive_manifest_count": len(manifest_inventory),
            "current_recursive_manifest_count": int(
                manifest_inventory["current"].map(_bool).sum()
            )
            if not manifest_inventory.empty
            else 0,
        },
    )
    return ProviderMarketDataImbalanceActiveLineageChainReport(
        chain=chain,
        manifest_inventory=manifest_inventory,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config_payload,
        output_dir=out,
    )


def _discover_manifests(
    root_manifest: Path,
    *,
    max_manifest_count: int,
) -> tuple[pd.DataFrame, dict[Path, dict[str, Any]], dict[Path, set[Path]], bool]:
    queue: list[tuple[Path, int]] = [(root_manifest.resolve(), 0)]
    visited: set[Path] = set()
    payloads: dict[Path, dict[str, Any]] = {}
    dependencies: dict[Path, set[Path]] = {}
    rows: list[dict[str, Any]] = []
    truncated = False
    expected_run_types = {spec.run_type for spec in BOUNDARIES}

    while queue:
        manifest_path, depth = queue.pop(0)
        if manifest_path in visited:
            continue
        if len(visited) >= max_manifest_count:
            truncated = True
            break
        visited.add(manifest_path)
        payload, read_error = _read_json(manifest_path)
        payloads[manifest_path] = payload
        direct_paths = set(_manifest_input_paths(payload))
        dependencies[manifest_path] = direct_paths
        integrity = verify_experiment_manifest(
            manifest_path,
            require_input_fingerprints=False,
        )
        run_type = _text(payload.get("run_type"))
        rows.append(
            {
                "depth": depth,
                "manifest_path": str(manifest_path),
                "bundle_path": str(manifest_path.parent),
                "run_type": run_type,
                "manifest_sha256": (
                    file_sha256(manifest_path) if manifest_path.is_file() else ""
                ),
                "readable": not read_error,
                "current": bool(integrity.passed),
                "artifact_count": int(integrity.artifact_count),
                "artifact_match_count": int(integrity.artifact_match_count),
                "input_fingerprint_count": int(integrity.input_fingerprint_count),
                "input_fingerprint_match_count": int(
                    integrity.input_fingerprint_match_count
                ),
                "direct_manifest_dependency_count": sum(
                    _manifest_path_for_dependency(path).is_file()
                    for path in direct_paths
                ),
                "expected_boundary": run_type in expected_run_types,
                "error": read_error or integrity.error,
            }
        )
        for dependency in sorted(direct_paths, key=lambda path: str(path).lower()):
            child = _manifest_path_for_dependency(dependency)
            if child.is_file() and child not in visited:
                queue.append((child, depth + 1))

    return (
        pd.DataFrame(rows, columns=MANIFEST_INVENTORY_COLUMNS),
        payloads,
        dependencies,
        truncated,
    )


def _build_chain(
    manifest_inventory: pd.DataFrame,
    manifest_payloads: Mapping[Path, dict[str, Any]],
    direct_dependencies: Mapping[Path, set[Path]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifests_by_run_type: dict[str, list[Path]] = {}
    for _, row in manifest_inventory.iterrows():
        run_type = _text(row.get("run_type"))
        if run_type:
            manifests_by_run_type.setdefault(run_type, []).append(
                Path(_text(row.get("manifest_path"))).resolve()
            )

    evidence: list[dict[str, Any]] = []
    for spec in BOUNDARIES:
        candidates = sorted(
            set(manifests_by_run_type.get(spec.run_type, [])),
            key=lambda path: str(path).lower(),
        )
        manifest_path = candidates[0] if candidates else None
        bundle = manifest_path.parent if manifest_path is not None else None
        summary_path = bundle / spec.summary_file if bundle is not None else None
        config_path = bundle / spec.config_file if bundle is not None else None
        summary, summary_error = _read_csv(summary_path)
        config_payload, config_error = _read_json(config_path)
        manifest_payload = (
            manifest_payloads.get(manifest_path, {})
            if manifest_path is not None
            else {}
        )
        summary_contract = provider_lineage_selection_contract_from_summary(summary)
        config_contract = _stage_config_contract(spec, config_payload)
        manifest_contract = provider_lineage_selection_contract_from_manifest(
            manifest_payload
        )
        manifest_integrity = (
            verify_experiment_manifest(
                manifest_path,
                expected_run_type=spec.run_type,
                required_artifacts=spec.required_artifacts,
                require_input_fingerprints=True,
            )
            if manifest_path is not None
            else None
        )
        summary_row = (
            summary.iloc[0] if len(summary) == 1 else pd.Series(dtype=object)
        )
        certificate_sha_current, certificate_cycle_current = (
            _certificate_integrity(config_payload)
            if spec.run_type == CERTIFICATE_RUN_TYPE
            else (True, True)
        )
        evidence.append(
            {
                "spec": spec,
                "candidates": candidates,
                "manifest_path": manifest_path,
                "bundle": bundle,
                "summary_path": summary_path,
                "config_path": config_path,
                "summary_error": summary_error,
                "config_error": config_error,
                "summary_row": summary_row,
                "config_payload": config_payload,
                "manifest_payload": manifest_payload,
                "summary_contract": summary_contract,
                "config_contract": config_contract,
                "manifest_contract": manifest_contract,
                "manifest_integrity": manifest_integrity,
                "certificate_sha_current": certificate_sha_current,
                "certificate_cycle_current": certificate_cycle_current,
            }
        )

    canonical_contract = (
        evidence[0]["summary_contract"]
        if evidence
        else normalize_provider_lineage_selection_contract({})
    )
    rows: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for item in evidence:
        spec = item["spec"]
        manifest_path = item["manifest_path"]
        bundle = item["bundle"]
        summary_row = item["summary_row"]
        unique_manifest = len(item["candidates"]) == 1
        artifacts_readable = bool(
            unique_manifest
            and not item["summary_error"]
            and not item["config_error"]
            and len(summary_row) > 0
        )
        manifest_current = bool(
            item["manifest_integrity"] is not None
            and item["manifest_integrity"].passed
        )
        stage_ready = _bool(summary_row.get(spec.ready_field, False))
        summary_contract_valid = provider_lineage_selection_contract_valid(
            item["summary_contract"]
        )
        config_contract_valid = provider_lineage_selection_contract_valid(
            item["config_contract"]
        )
        manifest_contract_valid = provider_lineage_selection_contract_valid(
            item["manifest_contract"]
        )
        surfaces_match = provider_lineage_selection_contracts_match(
            item["summary_contract"],
            item["config_contract"],
            item["manifest_contract"],
        )
        canonical_match = bool(
            surfaces_match
            and provider_lineage_selection_contract_valid(canonical_contract)
            and item["summary_contract"] == canonical_contract
        )
        if previous is None:
            predecessor_bound = True
            previous_stage = ""
            previous_bundle = ""
        else:
            previous_stage = previous["spec"].stage
            previous_root = previous["bundle"]
            previous_manifest = previous["manifest_path"]
            previous_bundle = "" if previous_root is None else str(previous_root)
            direct = direct_dependencies.get(manifest_path, set())
            predecessor_bound = bool(
                previous_root is not None
                and previous_manifest is not None
                and (
                    previous_root.resolve() in direct
                    or previous_manifest.resolve() in direct
                )
            )
        authorizing_claim_count = _authorizing_claim_count(
            summary_row.to_dict(),
            item["config_payload"],
            _mapping(item["manifest_payload"].get("extra")),
        )
        non_authorizing = authorizing_claim_count == 0
        passed = bool(
            unique_manifest
            and artifacts_readable
            and manifest_current
            and stage_ready
            and summary_contract_valid
            and config_contract_valid
            and manifest_contract_valid
            and surfaces_match
            and canonical_match
            and predecessor_bound
            and non_authorizing
            and item["certificate_sha_current"]
            and item["certificate_cycle_current"]
        )
        reasons: list[str] = []
        if not unique_manifest:
            reasons.append(
                "stage manifest is missing"
                if not item["candidates"]
                else "stage manifest is ambiguous"
            )
        if not artifacts_readable:
            reasons.append("stage summary or config is unreadable")
        if not manifest_current:
            reasons.append("stage manifest or recorded inputs drifted")
        if not stage_ready:
            reasons.append("stage is not ready")
        if not (
            summary_contract_valid
            and config_contract_valid
            and manifest_contract_valid
        ):
            reasons.append("stage contract is incomplete")
        if not surfaces_match:
            reasons.append("stage contract differs across summary, config, and manifest")
        if not canonical_match:
            reasons.append("stage contract differs from route-readiness canonical contract")
        if not predecessor_bound:
            reasons.append("stage manifest does not bind its immediate predecessor")
        if not non_authorizing:
            reasons.append("stage contains an authorizing claim")
        if not item["certificate_sha_current"]:
            reasons.append("certificate payload hash is not current")
        if not item["certificate_cycle_current"]:
            reasons.append("certificate cycle id is not current")
        rows.append(
            {
                "sequence": spec.sequence,
                "stage": spec.stage,
                "run_type": spec.run_type,
                "manifest_count": len(item["candidates"]),
                "bundle_path": "" if bundle is None else str(bundle),
                "manifest_path": "" if manifest_path is None else str(manifest_path),
                "manifest_sha256": (
                    file_sha256(manifest_path)
                    if manifest_path is not None and manifest_path.is_file()
                    else ""
                ),
                "summary_path": (
                    "" if item["summary_path"] is None else str(item["summary_path"])
                ),
                "config_path": (
                    "" if item["config_path"] is None else str(item["config_path"])
                ),
                "artifacts_readable": artifacts_readable,
                "manifest_current": manifest_current,
                "stage_ready": stage_ready,
                "summary_contract_valid": summary_contract_valid,
                "config_contract_valid": config_contract_valid,
                "manifest_contract_valid": manifest_contract_valid,
                "contract_surfaces_match": surfaces_match,
                "canonical_contract_match": canonical_match,
                "contract_sha256": _text(item["summary_contract"].get("sha256")),
                "previous_stage": previous_stage,
                "previous_bundle_path": previous_bundle,
                "direct_predecessor_bound": predecessor_bound,
                "authorizing_claim_count": authorizing_claim_count,
                "non_authorizing": non_authorizing,
                "certificate_payload_sha256_current": item[
                    "certificate_sha_current"
                ],
                "certificate_cycle_id_current": item["certificate_cycle_current"],
                "passed": passed,
                "reason": "; ".join(dict.fromkeys(reasons)),
            }
        )
        previous = item
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS), canonical_contract


def _checks(
    certificate_root: Path,
    chain: pd.DataFrame,
    manifest_inventory: pd.DataFrame,
    canonical_contract: Mapping[str, Any],
    *,
    truncated: bool,
) -> pd.DataFrame:
    current_manifests = (
        int(manifest_inventory["current"].map(_bool).sum())
        if not manifest_inventory.empty
        else 0
    )
    return pd.DataFrame(
        [
            _check(
                "certificate_directory_exists",
                certificate_root.is_dir(),
                "is",
                True,
                "certificate",
                "rehearsal certificate directory does not exist",
            ),
            _check(
                "manifest_discovery_not_truncated",
                truncated,
                "is",
                False,
                "manifest_graph",
                "recursive manifest discovery exceeded its configured bound",
            ),
            _check(
                "expected_stage_manifests_discovered",
                int(chain["manifest_count"].gt(0).sum()),
                "==",
                len(BOUNDARIES),
                "chain",
                "one or more required provider chain stages are missing",
            ),
            _check(
                "expected_stage_manifests_unique",
                int(chain["manifest_count"].eq(1).sum()),
                "==",
                len(BOUNDARIES),
                "chain",
                "one or more provider chain stages are missing or ambiguous",
            ),
            _check(
                "recursive_manifests_current",
                current_manifests,
                "==",
                len(manifest_inventory),
                "manifest_graph",
                "one or more recursively discovered manifests or inputs drifted",
            ),
            _all_stage_check(
                chain,
                "artifacts_readable",
                "stage_artifacts_readable",
                "one or more stage summaries or configs are unreadable",
            ),
            _all_stage_check(
                chain,
                "manifest_current",
                "stage_manifests_current",
                "one or more stage manifests or recorded inputs drifted",
            ),
            _check(
                "canonical_contract_valid",
                provider_lineage_selection_contract_valid(canonical_contract),
                "is",
                True,
                "contract",
                "route-readiness canonical contract is incomplete",
            ),
            _all_stage_check(
                chain,
                "summary_contract_valid",
                "stage_summary_contracts_valid",
                "one or more stage summary contracts are incomplete",
            ),
            _all_stage_check(
                chain,
                "config_contract_valid",
                "stage_config_contracts_valid",
                "one or more stage config contracts are incomplete",
            ),
            _all_stage_check(
                chain,
                "manifest_contract_valid",
                "stage_manifest_contracts_valid",
                "one or more stage manifest contracts are incomplete",
            ),
            _all_stage_check(
                chain,
                "contract_surfaces_match",
                "stage_contract_surfaces_match",
                "one or more stage contracts disagree across artifact surfaces",
            ),
            _all_stage_check(
                chain,
                "canonical_contract_match",
                "stage_contracts_match_canonical",
                "one or more stages carry a different active-lineage contract",
            ),
            _all_stage_check(
                chain,
                "direct_predecessor_bound",
                "stage_predecessor_links_bound",
                "one or more stages do not directly bind their predecessor",
            ),
            _all_stage_check(
                chain,
                "stage_ready",
                "all_stages_ready",
                "one or more provider chain stages are not ready",
            ),
            _all_stage_check(
                chain,
                "non_authorizing",
                "all_stages_non_authorizing",
                "one or more provider chain stages contain an authorizing claim",
            ),
            _all_stage_check(
                chain,
                "certificate_payload_sha256_current",
                "certificate_payload_sha256_current",
                "rehearsal certificate payload hash is stale",
            ),
            _all_stage_check(
                chain,
                "certificate_cycle_id_current",
                "certificate_cycle_id_current",
                "rehearsal certificate cycle id is stale",
            ),
        ],
        columns=CHECK_COLUMNS,
    )


def _summary(
    certificate_root: Path,
    chain: pd.DataFrame,
    manifest_inventory: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    contract: Mapping[str, Any],
    chain_digest: str,
    *,
    truncated: bool,
    ready: bool,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].map(_bool), "check"].astype(str).tolist()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "authorizes_submission": False,
                "certificate_dir": str(certificate_root),
                "expected_stage_count": len(BOUNDARIES),
                "discovered_stage_count": int(chain["manifest_count"].gt(0).sum()),
                "unique_stage_count": int(chain["manifest_count"].eq(1).sum()),
                "passed_stage_count": int(chain["passed"].map(_bool).sum()),
                "recursive_manifest_count": len(manifest_inventory),
                "current_recursive_manifest_count": int(
                    manifest_inventory["current"].map(_bool).sum()
                )
                if not manifest_inventory.empty
                else 0,
                "manifest_discovery_truncated": truncated,
                "provider_lineage_selection_contract_version": _text(
                    contract.get("version")
                ),
                "provider_lineage_selection_contract_sha256": _text(
                    contract.get("sha256")
                ),
                "provider_lineage_selected_run_count": _integer(
                    contract.get("selected_run_count")
                ),
                "provider_lineage_selected_pair_count": _integer(
                    contract.get("selected_pair_count")
                ),
                "provider_lineage_selected_pair_ids": _text(
                    contract.get("selected_pair_ids")
                ),
                "provider_lineage_selected_run_dirs": _text(
                    contract.get("selected_run_dirs")
                ),
                "provider_lineage_selection_artifact": _text(
                    contract.get("artifact")
                ),
                "chain_digest_sha256": chain_digest,
                "failed_checks": len(failed),
                "failed_check_names": ";".join(failed),
                "action_queue_count": len(action_queue),
                "blocked_action_count": int(
                    action_queue.get("queue_status", pd.Series(dtype=str))
                    .astype(str)
                    .eq("blocked")
                    .sum()
                ),
                "recommendation": (
                    "retain_active_lineage_chain_audit"
                    if ready
                    else "repair_and_reaudit_active_lineage_chain"
                ),
                "next_gate": READY_NEXT_GATE if ready else REPAIR_NEXT_GATE,
                "next_gate_help_command": (
                    "" if ready else f"python -m hft_cli {REPAIR_NEXT_GATE} --help"
                ),
            }
        ]
    )


def _action_queue(chain: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, stage in chain.loc[~chain["passed"].map(_bool)].iterrows():
        stage_name = _text(stage.get("stage"))
        is_certificate = stage_name == "rehearsal_certificate"
        next_gate = (
            "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
            if is_certificate
            else REPAIR_NEXT_GATE
        )
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "stage": stage_name,
                "check": "stage_chain_integrity",
                "action": (
                    "reissue_provider_rehearsal_certificate"
                    if is_certificate
                    else "rebuild_provider_active_lineage_chain_from_route_readiness"
                ),
                "reason": _text(stage.get("reason")),
                "next_gate": next_gate,
                "next_gate_help_command": f"python -m hft_cli {next_gate} --help",
            }
        )
    stage_checks = {
        "stage_artifacts_readable",
        "stage_manifests_current",
        "stage_summary_contracts_valid",
        "stage_config_contracts_valid",
        "stage_manifest_contracts_valid",
        "stage_contract_surfaces_match",
        "stage_contracts_match_canonical",
        "stage_predecessor_links_bound",
        "all_stages_ready",
        "all_stages_non_authorizing",
        "certificate_payload_sha256_current",
        "certificate_cycle_id_current",
    }
    for _, check in checks.loc[~checks["passed"].map(_bool)].iterrows():
        name = _text(check.get("check"))
        if name in stage_checks and rows:
            continue
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "stage": _text(check.get("component")),
                "check": name,
                "action": "rebuild_provider_active_lineage_chain_from_route_readiness",
                "reason": _text(check.get("reason")),
                "next_gate": REPAIR_NEXT_GATE,
                "next_gate_help_command": (
                    f"python -m hft_cli {REPAIR_NEXT_GATE} --help"
                ),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_COLUMNS)


def _runbook(
    summary: pd.Series,
    chain: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Provider Active-Lineage Chain Audit",
        "",
        f"- Ready: {'yes' if _bool(summary['ready']) else 'no'}",
        "- Authorizes submission: no",
        f"- Certificate: `{summary['certificate_dir']}`",
        "- Stages: "
        f"{int(summary['passed_stage_count'])}/{int(summary['expected_stage_count'])} passed",
        "- Recursive manifests: "
        f"{int(summary['current_recursive_manifest_count'])}/"
        f"{int(summary['recursive_manifest_count'])} current",
        "- Provider lineage contract: "
        f"`{summary['provider_lineage_selection_contract_sha256']}`",
        f"- Chain digest: `{summary['chain_digest_sha256']}`",
        f"- Next gate: `{summary['next_gate']}`",
        "",
        "## Chain",
        "",
        "| # | Stage | Manifest | Contract | Parent | Ready | Passed |",
        "|---:|---|---|---|---|---|---|",
    ]
    for _, row in chain.iterrows():
        lines.append(
            "| "
            f"{int(row['sequence'])} | `{row['stage']}` | "
            f"{'current' if _bool(row['manifest_current']) else 'blocked'} | "
            f"{'match' if _bool(row['canonical_contract_match']) else 'mismatch'} | "
            f"{'bound' if _bool(row['direct_predecessor_bound']) else 'missing'} | "
            f"{'yes' if _bool(row['stage_ready']) else 'no'} | "
            f"{'yes' if _bool(row['passed']) else 'no'} |"
        )
    failed_checks = checks.loc[~checks["passed"].map(_bool)]
    lines.extend(["", "## Failed Checks", ""])
    if failed_checks.empty:
        lines.append("- None")
    else:
        for _, row in failed_checks.iterrows():
            lines.append(f"- `{row['check']}`: {row['reason']}")
    lines.extend(["", "## Actions", ""])
    if action_queue.empty:
        lines.append("- None")
    else:
        for _, row in action_queue.iterrows():
            lines.append(
                f"- `{row['stage']}` -> `{row['next_gate']}`: {row['reason']}"
            )
    return "\n".join(lines) + "\n"


def _stage_config_contract(
    spec: _BoundarySpec,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if spec.run_type == CERTIFICATE_RUN_TYPE:
        return normalize_provider_lineage_selection_contract(
            _mapping(_mapping(config.get("payload")).get("provider_lineage_selection_contract"))
        )
    return provider_lineage_selection_contract_from_config(config)


def _certificate_integrity(certificate: Mapping[str, Any]) -> tuple[bool, bool]:
    payload = _mapping(certificate.get("payload"))
    stored_sha = _text(certificate.get("certificate_sha256"))
    sha_current = bool(payload and stored_sha == _canonical_sha256(payload))
    core = dict(payload)
    cycle_id = _text(core.pop("cycle_id", ""))
    expected_cycle_id = (
        f"hft-rehearsal-{_canonical_sha256(core)[:24]}" if core else ""
    )
    cycle_current = bool(
        cycle_id
        and cycle_id == expected_cycle_id
        and _text(certificate.get("cycle_id")) == cycle_id
    )
    return sha_current, cycle_current


def _all_stage_check(
    chain: pd.DataFrame,
    field: str,
    name: str,
    reason: str,
) -> dict[str, Any]:
    passed_count = int(chain[field].map(_bool).sum()) if field in chain else 0
    return _check(
        name,
        passed_count,
        "==",
        len(BOUNDARIES),
        "chain",
        reason,
    )


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    component: str,
    reason: str,
) -> dict[str, Any]:
    if operator == "is":
        passed = _bool(value) is _bool(threshold)
    elif operator == "==":
        passed = value == threshold
    else:
        passed = False
    return {
        "check": name,
        "component": component,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": passed,
        "reason": "" if passed else reason,
    }


def _manifest_input_paths(manifest: Mapping[str, Any]) -> Iterable[Path]:
    for fingerprint in _iter_fingerprints(manifest.get("inputs", {})):
        raw_path = _text(fingerprint.get("path"))
        if raw_path:
            yield Path(raw_path).resolve()


def _iter_fingerprints(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if _text(value.get("kind")) in {"file", "directory"} and value.get("path"):
            yield value
            return
        for item in value.values():
            yield from _iter_fingerprints(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_fingerprints(item)


def _manifest_path_for_dependency(path: Path) -> Path:
    if path.is_file() and path.name == "manifest.json":
        return path.resolve()
    return (path / "manifest.json").resolve()


def _authorizing_claim_count(*values: Any) -> int:
    count = 0
    for value in values:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).startswith("authorizes_") and _bool(item):
                    count += 1
                count += _authorizing_claim_count(item)
        elif isinstance(value, list):
            count += sum(_authorizing_claim_count(item) for item in value)
    return count


def _chain_digest(chain: pd.DataFrame) -> str:
    records = [
        {
            "sequence": _integer(row.get("sequence")),
            "run_type": _text(row.get("run_type")),
            "manifest_sha256": _text(row.get("manifest_sha256")),
            "contract_sha256": _text(row.get("contract_sha256")),
        }
        for _, row in chain.sort_values("sequence", kind="stable").iterrows()
    ]
    return _canonical_sha256(records)


def _existing_paths(values: pd.Series) -> list[Path]:
    paths = {
        Path(_text(value)).resolve()
        for value in values.tolist()
        if _text(value) and Path(_text(value)).exists()
    }
    return sorted(paths, key=lambda path: str(path).lower())


def _validate_config(
    config: ProviderMarketDataImbalanceActiveLineageChainConfig,
) -> None:
    if config.max_manifest_count < len(BOUNDARIES):
        raise ValueError(
            f"max_manifest_count must be at least {len(BOUNDARIES)}"
        )


def _validate_output_location(certificate_root: Path, output: Path) -> None:
    if output == certificate_root or certificate_root in output.parents:
        raise ValueError("output directory cannot be inside the rehearsal certificate")


def _validate_discovered_output_locations(
    manifest_inventory: pd.DataFrame,
    output: Path,
) -> None:
    for raw_path in manifest_inventory.get("bundle_path", pd.Series(dtype=str)):
        bundle = Path(_text(raw_path)).resolve()
        if output == bundle or bundle in output.parents:
            raise ValueError("output directory cannot be inside an audited chain stage")


def _read_json(path: Path | None) -> tuple[dict[str, Any], str]:
    if path is None or not path.is_file():
        return {}, "json_missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}, "json_unreadable"
    if not isinstance(value, dict):
        return {}, "json_not_object"
    return value, ""


def _read_csv(path: Path | None) -> tuple[pd.DataFrame, str]:
    if path is None or not path.is_file():
        return pd.DataFrame(), "csv_missing"
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(), "csv_unreadable"
    if len(frame) != 1:
        return frame, "csv_must_have_one_row"
    return frame, ""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _integer(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return int(number) if number.is_integer() else 0


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value
