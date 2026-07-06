from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.cutover import CutoverGateReport, CutoverGateThresholds, write_cutover_gate_report
from reports.manifest import write_experiment_manifest


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_cutover"

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]

VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES = (
    "dispatch_roundtrip_vendor_market_data_batch",
    "broker_dispatch_roundtrip_vendor_market_data_batch",
)
UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES = (
    "upstream_dispatch_roundtrip_vendor_market_data_batch",
    "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
)
VENDOR_MARKET_DATA_BATCH_BOOL_SUFFIXES = (
    "provided",
    "ready",
    "comparison_accepted",
)
VENDOR_MARKET_DATA_BATCH_INT_SUFFIXES = (
    "dataset_count",
    "ready_datasets",
    "failed_datasets",
    "unique_source_files",
    "unique_header_fingerprints",
    "unique_mapping_drafts",
    "comparison_failed_checks",
)
VENDOR_MARKET_DATA_BATCH_FLOAT_SUFFIXES = (
    "ready_rate",
    "source_file_fingerprint_coverage",
    "min_mapping_coverage",
)
VENDOR_MARKET_DATA_BATCH_TEXT_SUFFIXES = (
    "adapter",
    "kind",
    "manifest_run_type",
    "market",
    "mapping_sources",
    "datasets_json",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceCutoverConfig:
    require_provider_broker_readiness_ready: bool = True
    require_cutover_ready: bool = True
    use_provider_broker_readiness_inputs: bool = True
    target_mode: str = ""
    require_scaleup_ready: bool = True
    require_broker_readiness: bool = True
    require_runtime_session: bool = True
    require_runtime_guard_continue: bool = True
    require_route_readiness: bool = True
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
    require_operator_approval: bool = False
    require_operator_identity_ack: bool = False
    require_operator_limits_ack: bool = False
    max_failed_scaleup_checks: int = 0


@dataclass(frozen=True)
class ProviderMarketDataImbalanceCutoverReport:
    cutover: CutoverGateReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_imbalance_cutover(
    provider_broker_readiness_dir: str | Path,
    output_dir: str | Path,
    *,
    scaleup_dir: str | Path | None = None,
    broker_readiness_dir: str | Path | None = None,
    runtime_session_dir: str | Path | None = None,
    operator_review_path: str | Path | None = None,
    config: ProviderMarketDataImbalanceCutoverConfig | None = None,
) -> ProviderMarketDataImbalanceCutoverReport:
    config = config or ProviderMarketDataImbalanceCutoverConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    provider_root = Path(provider_broker_readiness_dir)
    provider_summary, provider_summary_error = _read_csv(
        provider_root / "provider_market_data_imbalance_broker_readiness_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_root / "provider_market_data_imbalance_broker_readiness_config.json"
    )
    inferred_scaleup_dir = _inferred_scaleup_dir(provider_summary, provider_config)
    inferred_broker_readiness_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "broker_readiness_dir")),
        _path_from_text((provider_config.get("broker_readiness", {}) or {}).get("output_dir")),
    )
    inferred_runtime_session_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "runtime_session_dir")),
        _path_from_text((provider_config.get("broker_inputs", {}) or {}).get("runtime_session_dir")),
    )
    inferred_provider_dispatch_roundtrip_dir, inferred_dispatch_roundtrip_dir = _inferred_dispatch_roundtrip_dirs(
        provider_summary,
        provider_config,
    )
    inferred_upstream_provider_dispatch_roundtrip_dir, inferred_upstream_dispatch_roundtrip_dir = (
        _inferred_upstream_dispatch_roundtrip_dirs(provider_summary, provider_config)
    )
    resolved_scaleup_dir = _explicit_or_inferred(scaleup_dir, inferred_scaleup_dir, config)
    resolved_broker_readiness_dir = _explicit_or_inferred(
        broker_readiness_dir,
        inferred_broker_readiness_dir,
        config,
    )
    resolved_runtime_session_dir = _explicit_or_inferred(
        runtime_session_dir,
        inferred_runtime_session_dir,
        config,
    )
    resolved_operator_review_path = Path(operator_review_path) if operator_review_path is not None else None

    prechecks = _prechecks(
        provider_root,
        provider_summary,
        provider_summary_error,
        provider_config_error,
        resolved_scaleup_dir,
        resolved_broker_readiness_dir,
        resolved_runtime_session_dir,
        config,
    )
    cutover: CutoverGateReport | None = None
    cutover_error = ""
    cutover_dir = out / "cutover"
    if bool(prechecks["passed"].all()):
        try:
            cutover = write_cutover_gate_report(
                scaleup_dir=_path_or_empty(resolved_scaleup_dir),
                broker_readiness_dir=_path_or_empty(resolved_broker_readiness_dir),
                runtime_session_dir=resolved_runtime_session_dir,
                operator_review_path=resolved_operator_review_path,
                output_dir=cutover_dir,
                thresholds=_thresholds(config, provider_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            cutover_error = str(exc)
    else:
        cutover_error = "provider imbalance cutover prerequisites are not ready"

    checks = _checks(prechecks, cutover, cutover_error, provider_summary, provider_config, config)
    summary = _summary(
        provider_root,
        resolved_scaleup_dir,
        resolved_broker_readiness_dir,
        resolved_runtime_session_dir,
        resolved_operator_review_path,
        inferred_provider_dispatch_roundtrip_dir,
        inferred_dispatch_roundtrip_dir,
        inferred_upstream_provider_dispatch_roundtrip_dir,
        inferred_upstream_dispatch_roundtrip_dir,
        cutover,
        checks,
        out,
        provider_summary,
        provider_config,
    )
    action_queue = _action_queue(summary.iloc[0], checks, cutover)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        cutover,
        checks,
        action_queue,
        config,
        {
            "scaleup_dir": resolved_scaleup_dir,
            "broker_readiness_dir": resolved_broker_readiness_dir,
            "runtime_session_dir": resolved_runtime_session_dir,
            "operator_review_path": resolved_operator_review_path,
            "provider_dispatch_roundtrip_dir": inferred_provider_dispatch_roundtrip_dir,
            "dispatch_roundtrip_dir": inferred_dispatch_roundtrip_dir,
            "upstream_provider_dispatch_roundtrip_dir": inferred_upstream_provider_dispatch_roundtrip_dir,
            "upstream_dispatch_roundtrip_dir": inferred_upstream_dispatch_roundtrip_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_cutover_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_cutover_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_cutover_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_cutover_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_cutover_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_broker_readiness_dir": provider_root}
    for name, value in {
        "scaleup": resolved_scaleup_dir,
        "broker_readiness": resolved_broker_readiness_dir,
        "runtime_session": resolved_runtime_session_dir,
        "operator_review": resolved_operator_review_path,
        "provider_dispatch_roundtrip": inferred_provider_dispatch_roundtrip_dir,
        "dispatch_roundtrip": inferred_dispatch_roundtrip_dir,
        "upstream_provider_dispatch_roundtrip": inferred_upstream_provider_dispatch_roundtrip_dir,
        "upstream_dispatch_roundtrip": inferred_upstream_dispatch_roundtrip_dir,
    }.items():
        if value is not None:
            inputs[name] = Path(value)
    if cutover is not None and cutover.output_dir is not None:
        inputs["cutover"] = cutover.output_dir
    summary_row = summary.iloc[0]
    for name, value in {
        "capture_bundle": _path_from_text(summary_row["capture_bundle_path"]),
        "capture_env_template": _path_from_text(summary_row["capture_env_template_path"]),
        "adapter_handoff": _path_from_text(summary_row["adapter_handoff_path"]),
        "dispatch_roundtrip_capture_bundle": _path_from_text(summary_row["dispatch_roundtrip_capture_bundle_path"]),
        "dispatch_roundtrip_capture_env_template": _path_from_text(
            summary_row["dispatch_roundtrip_capture_env_template_path"]
        ),
        "dispatch_roundtrip_adapter_handoff": _path_from_text(summary_row["dispatch_roundtrip_adapter_handoff_path"]),
        "dispatch_roundtrip_source_credential_env_template": _path_from_text(
            summary_row["dispatch_roundtrip_source_credential_env_template_path"]
        ),
        "source_credential_env_template": _path_from_text(summary_row["source_credential_env_template_path"]),
    }.items():
        if value is not None:
            inputs[name] = value

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config), "cutover_inputs": _jsonable(payload["cutover_inputs"])},
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "cutover_ready": bool(summary_row["cutover_ready"]),
            "profile": PROFILE,
            "strategy": str(summary_row["strategy"]),
            "market": str(summary_row["market"]),
            "exchange": str(summary_row["exchange"]),
            "source_session": _source_session_contract_from_summary(summary_row),
            "market_session": _market_session_contract_from_summary(summary_row),
            "provider_profile": _mapping(payload.get("provider_profile")),
            "provider_profile_matches_session": bool(summary_row["provider_profile_matches_session"]),
            "provider_profile_matches_bundle": bool(summary_row["provider_profile_matches_bundle"]),
            "capture_bundle_provided": bool(summary_row["capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary_row["capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary_row["capture_bundle_ready"]),
            "capture_env_template_exists": bool(summary_row["capture_env_template_exists"]),
            "adapter_handoff_provided": bool(summary_row["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary_row["adapter_handoff_exists"]),
            "capture_env_template": {
                "path": str(summary_row["capture_env_template_path"]),
                "exists": bool(summary_row["capture_env_template_exists"]),
                "sha256": str(summary_row["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(summary_row["adapter_handoff_path"]),
                "exists": bool(summary_row["adapter_handoff_exists"]),
                "sha256": str(summary_row["adapter_handoff_sha256"]),
            },
            "capture_bundle_metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "provider_capture_command_count": int(summary_row["provider_capture_command_count"]),
            "provider_capture_command_providers": str(summary_row["provider_capture_command_providers"]),
            "provider_capture_command_transports": str(summary_row["provider_capture_command_transports"]),
            "capture_bundle_provider_capture_command_count": int(
                summary_row["capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                summary_row["capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                summary_row["capture_bundle_provider_capture_commands_match_session"]
            ),
            "synthetic_sidecar_proof": _mapping(payload.get("synthetic_sidecar_proof")),
            "synthetic_dataset_count": int(summary_row["synthetic_dataset_count"]),
            "synthetic_sidecar_proof_ready": bool(summary_row["synthetic_sidecar_proof_ready"]),
            "synthetic_sidecar_count": int(summary_row["synthetic_sidecar_count"]),
            "synthetic_sidecar_readable_count": int(summary_row["synthetic_sidecar_readable_count"]),
            "route_readiness_provided": bool(summary_row["route_readiness_provided"]),
            "route_readiness_ops_launch_controls_present": bool(
                summary_row["route_readiness_ops_launch_controls_present"]
            ),
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                summary_row["route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"]
            ),
            "dispatch_roundtrip_route_readiness_provided": bool(
                summary_row["dispatch_roundtrip_route_readiness_provided"]
            ),
            "dispatch_roundtrip_route_readiness_ops_launch_controls_present": bool(
                summary_row["dispatch_roundtrip_route_readiness_ops_launch_controls_present"]
            ),
            "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                summary_row[
                    "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"
                ]
            ),
            "dispatch_roundtrip_synthetic_sidecar_proof": _mapping(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get("synthetic_sidecar_proof")
            ),
            "dispatch_roundtrip_synthetic_dataset_count": int(
                summary_row["dispatch_roundtrip_synthetic_dataset_count"]
            ),
            "dispatch_roundtrip_synthetic_sidecar_proof_ready": bool(
                summary_row["dispatch_roundtrip_synthetic_sidecar_proof_ready"]
            ),
            "dispatch_roundtrip_synthetic_sidecar_count": int(
                summary_row["dispatch_roundtrip_synthetic_sidecar_count"]
            ),
            "dispatch_roundtrip_synthetic_sidecar_readable_count": int(
                summary_row["dispatch_roundtrip_synthetic_sidecar_readable_count"]
            ),
            "capture_bundle": {
                "exchange": str(summary_row["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary_row),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary_row),
                "provider_profile": _mapping(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_profile")
                ),
                "provider_capture_commands": _list(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
                ),
                "provider_capture_command_count": int(
                    summary_row["capture_bundle_provider_capture_command_count"]
                ),
                "provider_capture_commands_match_session": bool(
                    summary_row["capture_bundle_provider_capture_commands_match_session"]
                ),
                "metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
                "adapter_execution_contract": _mapping(
                    _mapping(payload.get("capture_bundle")).get("adapter_execution_contract")
                ),
            },
            "source_credential_env_template": {
                "path": str(summary_row["source_credential_env_template_path"]),
                "exists": bool(summary_row["source_credential_env_template_exists"]),
                "sha256": str(summary_row["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary_row["source_live_fetch_contract_available"]),
                "next_gate": str(summary_row["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary_row["source_live_fetch_contract_command_template"]),
                "exchange": str(summary_row["source_live_fetch_contract_exchange"]),
                "market": str(summary_row["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary_row),
            },
            "adapter_execution_contract": _mapping(payload.get("adapter_execution_contract")),
            "adapter_contract_provider": str(summary_row["adapter_contract_provider"]),
            "adapter_contract_transport": str(summary_row["adapter_contract_transport"]),
            "adapter_contract_market": str(summary_row["adapter_contract_market"]),
            "adapter_contract_exchange": str(summary_row["adapter_contract_exchange"]),
            "adapter_contract_values_stored": bool(summary_row["adapter_contract_values_stored"]),
            "adapter_contract_metadata_matches_evidence": bool(
                summary_row["adapter_contract_metadata_matches_evidence"]
            ),
            "adapter_contract_provider_profile_sha256": str(summary_row["adapter_contract_provider_profile_sha256"]),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary_row["adapter_contract_provider_profile_matches_evidence"]
            ),
            "provider_capture_commands": _list(payload.get("provider_capture_commands")),
            "capture_bundle_provider_capture_commands": _list(
                payload.get("capture_bundle_provider_capture_commands")
            ),
            "dispatch_roundtrip_capture_provenance_consistent": bool(
                summary_row["dispatch_roundtrip_capture_provenance_consistent"]
            ),
            "dispatch_roundtrip_capture_bundle_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_bundle_matches_session"]
            ),
            "dispatch_roundtrip_capture_env_template_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_env_template_matches_session"]
            ),
            "dispatch_roundtrip_adapter_handoff_matches_session": bool(
                summary_row["dispatch_roundtrip_adapter_handoff_matches_session"]
            ),
            "dispatch_roundtrip_capture_env_template": {
                "path": str(summary_row["dispatch_roundtrip_capture_env_template_path"]),
                "exists": bool(summary_row["dispatch_roundtrip_capture_env_template_exists"]),
                "sha256": str(summary_row["dispatch_roundtrip_capture_env_template_sha256"]),
                "matches_session": bool(summary_row["dispatch_roundtrip_capture_env_template_matches_session"]),
            },
            "dispatch_roundtrip_adapter_handoff": {
                "path": str(summary_row["dispatch_roundtrip_adapter_handoff_path"]),
                "exists": bool(summary_row["dispatch_roundtrip_adapter_handoff_exists"]),
                "sha256": str(summary_row["dispatch_roundtrip_adapter_handoff_sha256"]),
                "matches_session": bool(summary_row["dispatch_roundtrip_adapter_handoff_matches_session"]),
            },
            "dispatch_roundtrip_source_provenance_consistent": bool(
                summary_row["dispatch_roundtrip_source_provenance_consistent"]
            ),
            "dispatch_roundtrip_source_credential_env_template_matches_session": bool(
                summary_row["dispatch_roundtrip_source_credential_env_template_matches_session"]
            ),
            "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": bool(
                summary_row["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"]
            ),
            "dispatch_roundtrip_provider_capture_command_count": int(
                summary_row["dispatch_roundtrip_provider_capture_command_count"]
            ),
            "dispatch_roundtrip_provider_capture_command_providers": str(
                summary_row["dispatch_roundtrip_provider_capture_command_providers"]
            ),
            "dispatch_roundtrip_provider_capture_command_transports": str(
                summary_row["dispatch_roundtrip_provider_capture_command_transports"]
            ),
            "dispatch_roundtrip_capture_bundle_provider_capture_command_count": int(
                summary_row["dispatch_roundtrip_capture_bundle_provider_capture_command_count"]
            ),
            "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": int(
                summary_row["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"]
            ),
            "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": bool(
                summary_row["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
            ),
            "dispatch_roundtrip_provider_capture_commands_match_runtime_session": bool(
                summary_row["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
            ),
            "dispatch_roundtrip_adapter_execution_contract": _mapping(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get("adapter_execution_contract")
            ),
            "dispatch_roundtrip_adapter_contract_provider": str(
                summary_row["dispatch_roundtrip_adapter_contract_provider"]
            ),
            "dispatch_roundtrip_adapter_contract_transport": str(
                summary_row["dispatch_roundtrip_adapter_contract_transport"]
            ),
            "dispatch_roundtrip_adapter_contract_market": str(
                summary_row["dispatch_roundtrip_adapter_contract_market"]
            ),
            "dispatch_roundtrip_adapter_contract_exchange": str(
                summary_row["dispatch_roundtrip_adapter_contract_exchange"]
            ),
            "dispatch_roundtrip_adapter_contract_values_stored": bool(
                summary_row["dispatch_roundtrip_adapter_contract_values_stored"]
            ),
            "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": bool(
                summary_row["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"]
            ),
            "dispatch_roundtrip_adapter_contract_matches_runtime_session": bool(
                summary_row["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
            ),
            "dispatch_roundtrip_provider_profile": _mapping(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get("provider_profile")
            ),
            "dispatch_roundtrip_capture_bundle_provider_profile": _mapping(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get("capture_bundle_provider_profile")
            ),
            "dispatch_roundtrip_provider_profile_sha256": str(
                summary_row["dispatch_roundtrip_provider_profile_sha256"]
            ),
            "dispatch_roundtrip_provider_profile_matches_session": bool(
                summary_row["dispatch_roundtrip_provider_profile_matches_session"]
            ),
            "dispatch_roundtrip_provider_profile_matches_bundle": bool(
                summary_row["dispatch_roundtrip_provider_profile_matches_bundle"]
            ),
            "dispatch_roundtrip_provider_profile_matches_runtime_session": bool(
                summary_row["dispatch_roundtrip_provider_profile_matches_runtime_session"]
            ),
            "dispatch_roundtrip_adapter_contract_provider_profile_sha256": str(
                summary_row["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
            ),
            "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence": bool(
                summary_row["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
            ),
            "dispatch_roundtrip_provider_capture_commands": _list(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get("provider_capture_commands")
            ),
            "dispatch_roundtrip_capture_bundle_provider_capture_commands": _list(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get(
                    "capture_bundle_provider_capture_commands"
                )
            ),
            "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"]
            ),
            "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"]
            ),
            "dispatch_roundtrip_exchange_matches_session": bool(
                summary_row["dispatch_roundtrip_exchange_matches_session"]
            ),
            "dispatch_roundtrip_source_session_matches_session": bool(
                summary_row["dispatch_roundtrip_source_session_matches_session"]
            ),
            "dispatch_roundtrip_market_session_matches_session": bool(
                summary_row["dispatch_roundtrip_market_session_matches_session"]
            ),
            "dispatch_roundtrip_metadata_consistent": bool(summary_row["dispatch_roundtrip_metadata_consistent"]),
            "dispatch_roundtrip_capture_bundle_exchange_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_bundle_exchange_matches_session"]
            ),
            "dispatch_roundtrip_capture_bundle_source_session_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_bundle_source_session_matches_session"]
            ),
            "dispatch_roundtrip_capture_bundle_market_session_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_bundle_market_session_matches_session"]
            ),
            "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"]
            ),
            "dispatch_roundtrip_source_live_fetch_contract_market_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"]
            ),
            "dispatch_roundtrip_source_live_fetch_contract_session_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"]
            ),
            "dispatch_roundtrip": {
                "exchange": str(summary_row["dispatch_roundtrip_exchange"]),
                "source_session": _dispatch_roundtrip_source_session_contract_from_summary(summary_row),
                "market_session": _dispatch_roundtrip_market_session_contract_from_summary(summary_row),
                "metadata_consistent": bool(summary_row["dispatch_roundtrip_metadata_consistent"]),
                "capture_bundle": {
                    "exchange": str(summary_row["dispatch_roundtrip_capture_bundle_exchange"]),
                    "source_session": _dispatch_roundtrip_capture_bundle_source_session_contract_from_summary(
                        summary_row
                    ),
                    "market_session": _dispatch_roundtrip_capture_bundle_market_session_contract_from_summary(
                        summary_row
                    ),
                    "provider_capture_commands": _list(
                        _mapping(payload.get("dispatch_roundtrip_provenance")).get(
                            "capture_bundle_provider_capture_commands"
                        )
                    ),
                    "provider_capture_command_count": int(
                        summary_row["dispatch_roundtrip_capture_bundle_provider_capture_command_count"]
                    ),
                    "provider_capture_commands_match_session": bool(
                        summary_row["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
                    ),
                    "provider_capture_commands_match_runtime_session": bool(
                        summary_row["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
                    ),
                    "metadata_matches_session": bool(
                        summary_row["dispatch_roundtrip_capture_bundle_metadata_matches_session"]
                    ),
                    "live_fetch_contract_metadata_matches_session": bool(
                        summary_row["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"]
                    ),
                },
                "adapter_execution_contract": _mapping(
                    _mapping(payload.get("dispatch_roundtrip_provenance")).get("adapter_execution_contract")
                ),
                "adapter_contract_provider": str(summary_row["dispatch_roundtrip_adapter_contract_provider"]),
                "adapter_contract_transport": str(summary_row["dispatch_roundtrip_adapter_contract_transport"]),
                "adapter_contract_market": str(summary_row["dispatch_roundtrip_adapter_contract_market"]),
                "adapter_contract_exchange": str(summary_row["dispatch_roundtrip_adapter_contract_exchange"]),
                "adapter_contract_values_stored": bool(
                    summary_row["dispatch_roundtrip_adapter_contract_values_stored"]
                ),
                "adapter_contract_metadata_matches_evidence": bool(
                    summary_row["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"]
                ),
                "adapter_contract_matches_runtime_session": bool(
                    summary_row["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
                ),
                "synthetic_sidecar_proof": _mapping(
                    _mapping(payload.get("dispatch_roundtrip_provenance")).get("synthetic_sidecar_proof")
                ),
                "synthetic_dataset_count": int(summary_row["dispatch_roundtrip_synthetic_dataset_count"]),
                "synthetic_sidecar_proof_ready": bool(
                    summary_row["dispatch_roundtrip_synthetic_sidecar_proof_ready"]
                ),
                "synthetic_sidecar_count": int(summary_row["dispatch_roundtrip_synthetic_sidecar_count"]),
                "synthetic_sidecar_readable_count": int(
                    summary_row["dispatch_roundtrip_synthetic_sidecar_readable_count"]
                ),
                "route_readiness_provided": bool(summary_row["dispatch_roundtrip_route_readiness_provided"]),
                "route_readiness_ops_launch_controls_present": bool(
                    summary_row["dispatch_roundtrip_route_readiness_ops_launch_controls_present"]
                ),
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    summary_row[
                        "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"
                    ]
                ),
                "provider_profile": _mapping(
                    _mapping(payload.get("dispatch_roundtrip_provenance")).get("provider_profile")
                ),
                "provider_profile_matches_session": bool(
                    summary_row["dispatch_roundtrip_provider_profile_matches_session"]
                ),
                "provider_profile_matches_bundle": bool(
                    summary_row["dispatch_roundtrip_provider_profile_matches_bundle"]
                ),
                "provider_profile_matches_runtime_session": bool(
                    summary_row["dispatch_roundtrip_provider_profile_matches_runtime_session"]
                ),
                "live_fetch_contract": {
                    "exchange": str(summary_row["dispatch_roundtrip_source_live_fetch_contract_exchange"]),
                    "market": str(summary_row["dispatch_roundtrip_source_live_fetch_contract_market"]),
                    "session": _dispatch_roundtrip_source_live_fetch_contract_session_from_summary(summary_row),
                },
            },
            "dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
        },
    )
    return ProviderMarketDataImbalanceCutoverReport(cutover, checks, summary, action_queue, payload, out)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"{path.name} does not exist"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} is not readable: {exc}"
    return value if isinstance(value, dict) else {}, ""


def _prechecks(
    provider_root: Path,
    provider_summary: pd.DataFrame,
    provider_summary_error: str,
    provider_config_error: str,
    scaleup_dir: Path | None,
    broker_readiness_dir: Path | None,
    runtime_session_dir: Path | None,
    config: ProviderMarketDataImbalanceCutoverConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_broker_readiness_dir_exists",
                str(provider_root),
                "exists",
                True,
                provider_root.exists(),
                "provider imbalance broker-readiness directory is required",
            ),
            _check(
                "provider_broker_readiness_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance broker-readiness summary could not be read",
            ),
            _check(
                "provider_broker_readiness_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider imbalance broker-readiness config could not be read",
            ),
            _check(
                "provider_broker_readiness_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_broker_readiness_ready,
                "provider imbalance broker-readiness is not ready",
            ),
            _check(
                "nested_scaleup_config_exists",
                _path_text(scaleup_dir),
                "exists",
                True,
                bool(scaleup_dir and (scaleup_dir / "scaleup_config.json").exists()),
                "nested scaleup_config.json is required for cutover",
            ),
            _check(
                "nested_broker_readiness_summary_exists",
                _path_text(broker_readiness_dir),
                "exists",
                True,
                bool(broker_readiness_dir and (broker_readiness_dir / "broker_readiness_summary.csv").exists()),
                "nested broker_readiness_summary.csv is required for cutover",
            ),
            _check(
                "nested_runtime_session_summary_exists",
                _path_text(runtime_session_dir),
                "exists",
                True,
                bool(runtime_session_dir and (runtime_session_dir / "runtime_session_summary.csv").exists()),
                "nested runtime_session_summary.csv is required for cutover",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    cutover: CutoverGateReport | None,
    cutover_error: str,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    config: ProviderMarketDataImbalanceCutoverConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    cutover_summary = cutover.summary if cutover is not None else pd.DataFrame()
    rows.append(
        _check(
            "cutover_runnable",
            cutover_error or ("ran" if cutover is not None else "not_run"),
            "is",
            "ran",
            cutover is not None and not cutover_error,
            cutover_error or "generic cutover gate was not run",
        )
    )
    rows.append(
        _check(
            "cutover_ready",
            bool(cutover is not None and cutover.ready),
            "is",
            True,
            bool(cutover is not None and (cutover.ready or not config.require_cutover_ready)),
            _cutover_failure_reason(cutover) or "cutover gate is not ready",
        )
    )
    strategy = _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            _identity_key(strategy) == PROFILE,
            "provider cutover did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    cutover_market = _first_text(cutover_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            cutover_market or expected_market,
            "is",
            expected_market or "present",
            bool(cutover is not None)
            and bool(expected_market)
            and (not cutover_market or _identity_key(cutover_market) == _identity_key(expected_market)),
            "cutover market identity does not match provider broker-readiness",
        )
    )
    bundle_provided = _first_bool(provider_summary, "capture_bundle_provided")
    provider_capture_command_count = int(_first_number(provider_summary, "provider_capture_command_count"))
    bundle_provider_capture_command_count = int(
        _first_number(provider_summary, "capture_bundle_provider_capture_command_count")
    )
    bundle_provider_capture_command_missing_count = int(
        _first_number(provider_summary, "capture_bundle_provider_capture_command_missing_count")
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and _first_bool(provider_summary, "capture_bundle_provider_capture_commands_match_session")
    )
    adapter_contract_carried = _adapter_contract_carried(provider_summary)
    provider_profile_carried = _provider_profile_carried(provider_summary)
    synthetic_dataset_count = int(_first_number(provider_summary, "synthetic_dataset_count"))
    synthetic_sidecar_count = int(_first_number(provider_summary, "synthetic_sidecar_count"))
    synthetic_sidecar_proof_required = synthetic_dataset_count > 0
    synthetic_sidecar_proof_ready = _first_bool(provider_summary, "synthetic_sidecar_proof_ready")
    synthetic_sidecar_count_matches = synthetic_sidecar_count == synthetic_dataset_count
    route_sidecar_breach_pairs = int(
        _first_number(
            provider_summary,
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
        )
    )
    route_sidecar_gate_active = (
        _first_bool(provider_summary, "route_readiness_provided")
        or _first_bool(provider_summary, "route_readiness_ops_launch_controls_present")
        or route_sidecar_breach_pairs > 0
    )
    rows.append(
        _check(
            "provider_broker_readiness_provider_capture_commands_carried",
            bundle_provider_capture_command_count,
            "==",
            provider_capture_command_count,
            bundle_provider_capture_commands_carried if bundle_provided else True,
            "provider imbalance broker-readiness is missing capture-bundle provider command proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_provider_capture_commands_match_session",
            bundle_provider_capture_command_count,
            "matches",
            provider_capture_command_count,
            bundle_provider_capture_commands_match_session if bundle_provided else True,
            "provider imbalance broker-readiness command proof no longer matches the session packet",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_adapter_execution_contract_carried",
            _adapter_contract_metadata_text(provider_summary),
            "is_not",
            "",
            adapter_contract_carried if bundle_provided else True,
            "provider imbalance broker-readiness is missing credential-safe adapter execution contract proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_adapter_execution_contract_matches_evidence",
            _adapter_contract_metadata_text(provider_summary),
            "matches",
            "live evidence",
            _first_bool(provider_summary, "adapter_contract_metadata_matches_evidence") if bundle_provided else True,
            "provider imbalance broker-readiness adapter execution contract no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_provider_profile_carried",
            _first_text(provider_summary, "provider_profile_sha256"),
            "has",
            "provider profile",
            provider_profile_carried,
            "provider imbalance broker-readiness is missing provider-profile proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_provider_profile_matches_session",
            _first_text(provider_summary, "provider_profile_sha256"),
            "matches",
            "live session",
            _first_bool(provider_summary, "provider_profile_matches_session"),
            "provider imbalance broker-readiness provider-profile proof no longer matches the live session packet",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_provider_profile_matches_bundle",
            _first_text(provider_summary, "capture_bundle_provider_profile_sha256"),
            "matches",
            _first_text(provider_summary, "provider_profile_sha256"),
            _first_bool(provider_summary, "provider_profile_matches_bundle") if bundle_provided else True,
            "provider imbalance broker-readiness provider-profile proof no longer matches the capture bundle",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_adapter_provider_profile_matches_evidence",
            _first_text(provider_summary, "adapter_contract_provider_profile_sha256"),
            "==",
            _first_text(provider_summary, "provider_profile_sha256"),
            _first_bool(provider_summary, "adapter_contract_provider_profile_matches_evidence")
            if bundle_provided
            else True,
            "provider imbalance broker-readiness adapter contract provider-profile SHA no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_synthetic_sidecar_proof_carried",
            synthetic_sidecar_count,
            "==",
            synthetic_dataset_count,
            synthetic_sidecar_count_matches if synthetic_sidecar_proof_required else True,
            "provider imbalance broker-readiness is missing synthetic rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_synthetic_sidecar_proof_ready",
            synthetic_sidecar_proof_ready,
            "is",
            True,
            synthetic_sidecar_proof_ready if synthetic_sidecar_proof_required else True,
            "provider imbalance broker-readiness synthetic rehearsal sidecar proof is not ready",
        )
    )
    rows.append(
        _check(
            "provider_broker_readiness_route_readiness_provider_sidecar_breach_pairs",
            route_sidecar_breach_pairs,
            "<=",
            0,
            route_sidecar_breach_pairs <= 0 if route_sidecar_gate_active else True,
            "provider imbalance broker-readiness carries breached route-readiness broker round-trip synthetic sidecar proof",
        )
    )
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    dispatch_bundle_provided = _dispatch_roundtrip_bool(
        provider_summary,
        dispatch_roundtrip,
        "dispatch_roundtrip_capture_bundle_provided",
        "capture_bundle_provided",
    )
    dispatch_provider_capture_command_count = int(
        _dispatch_roundtrip_number(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_provider_capture_command_count",
            "provider_capture_command_count",
        )
    )
    dispatch_bundle_provider_capture_command_count = int(
        _dispatch_roundtrip_number(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
            "capture_bundle_provider_capture_command_count",
        )
    )
    dispatch_bundle_provider_capture_command_missing_count = int(
        _dispatch_roundtrip_number(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
            "capture_bundle_provider_capture_command_missing_count",
        )
    )
    dispatch_bundle_provider_capture_commands_carried = (
        dispatch_provider_capture_command_count >= 1
        and dispatch_bundle_provider_capture_command_count == dispatch_provider_capture_command_count
        and dispatch_bundle_provider_capture_command_missing_count == 0
    )
    dispatch_bundle_provider_capture_commands_match_session = (
        dispatch_bundle_provider_capture_commands_carried
        and _dispatch_roundtrip_bool(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
            "capture_bundle_provider_capture_commands_match_session",
        )
    )
    dispatch_provider_capture_commands_match_runtime_session = _dispatch_roundtrip_bool(
        provider_summary,
        dispatch_roundtrip,
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "provider_capture_commands_match_runtime_session",
    )
    dispatch_adapter_contract_carried = _dispatch_roundtrip_adapter_contract_carried(
        provider_summary,
        dispatch_roundtrip,
    )
    dispatch_adapter_contract_matches_runtime_session = _dispatch_roundtrip_bool(
        provider_summary,
        dispatch_roundtrip,
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "adapter_contract_matches_runtime_session",
    )
    dispatch_provider_profile_carried = _dispatch_roundtrip_provider_profile_carried(
        provider_summary,
        dispatch_roundtrip,
    )
    dispatch_provider_profile_matches_runtime_session = _dispatch_roundtrip_provider_profile_matches_session(
        provider_summary,
        dispatch_roundtrip,
    )
    dispatch_synthetic_dataset_count = int(
        _dispatch_roundtrip_number(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_synthetic_dataset_count",
            "synthetic_dataset_count",
        )
    )
    dispatch_synthetic_sidecar_count = int(
        _dispatch_roundtrip_number(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_synthetic_sidecar_count",
            "synthetic_sidecar_count",
        )
    )
    dispatch_synthetic_sidecar_proof_required = dispatch_synthetic_dataset_count > 0
    dispatch_synthetic_sidecar_proof_ready = _dispatch_roundtrip_bool(
        provider_summary,
        dispatch_roundtrip,
        "dispatch_roundtrip_synthetic_sidecar_proof_ready",
        "synthetic_sidecar_proof_ready",
    )
    dispatch_synthetic_sidecar_count_matches = (
        dispatch_synthetic_sidecar_count == dispatch_synthetic_dataset_count
    )
    dispatch_route_sidecar_breach_pairs = int(
        _dispatch_roundtrip_number(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
        )
    )
    dispatch_route_sidecar_gate_active = (
        _dispatch_roundtrip_bool(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_route_readiness_provided",
            "route_readiness_provided",
        )
        or _dispatch_roundtrip_bool(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_route_readiness_ops_launch_controls_present",
            "route_readiness_ops_launch_controls_present",
        )
        or dispatch_route_sidecar_breach_pairs > 0
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_capture_commands_carried",
            dispatch_bundle_provider_capture_command_count,
            "==",
            dispatch_provider_capture_command_count,
            dispatch_bundle_provider_capture_commands_carried if dispatch_bundle_provided else True,
            "provider imbalance cutover is missing broker-readiness round-trip provider command proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_capture_commands_match_session",
            dispatch_bundle_provider_capture_command_count,
            "matches",
            dispatch_provider_capture_command_count,
            dispatch_bundle_provider_capture_commands_match_session if dispatch_bundle_provided else True,
            "provider imbalance cutover round-trip command proof no longer matches the session packet",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
            dispatch_provider_capture_commands_match_runtime_session,
            "is",
            True,
            dispatch_provider_capture_commands_match_runtime_session if dispatch_bundle_provided else True,
            "provider imbalance cutover round-trip command proof no longer matches runtime-session proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_adapter_execution_contract_carried",
            _dispatch_roundtrip_adapter_contract_metadata_text(provider_summary, dispatch_roundtrip),
            "is_not",
            "",
            dispatch_adapter_contract_carried if dispatch_bundle_provided else True,
            "provider imbalance cutover is missing broker-readiness round-trip adapter execution contract proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            _dispatch_roundtrip_adapter_contract_metadata_text(provider_summary, dispatch_roundtrip),
            "matches",
            "live evidence",
            _dispatch_roundtrip_bool(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
                "adapter_contract_metadata_matches_evidence",
            )
            if dispatch_bundle_provided
            else True,
            "provider imbalance cutover round-trip adapter execution contract no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            _dispatch_roundtrip_adapter_contract_metadata_text(provider_summary, dispatch_roundtrip),
            "matches",
            _adapter_contract_metadata_text(provider_summary),
            dispatch_adapter_contract_matches_runtime_session if dispatch_bundle_provided else True,
            "provider imbalance cutover round-trip adapter execution contract no longer matches runtime-session proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_profile_carried",
            _dispatch_roundtrip_provider_profile_metadata_text(provider_summary, dispatch_roundtrip),
            "is_not",
            "",
            dispatch_provider_profile_carried if dispatch_bundle_provided else True,
            "provider imbalance cutover is missing broker-readiness round-trip provider-profile proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_profile_matches_session",
            _dispatch_roundtrip_provider_profile_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_sha256",
                "sha256",
                "provider_profile_sha256",
            ),
            "matches",
            "live session",
            _dispatch_roundtrip_bool(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_matches_session",
                "provider_profile_matches_session",
            )
            if dispatch_bundle_provided
            else True,
            "provider imbalance cutover round-trip provider-profile proof no longer matches live session",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_profile_matches_bundle",
            _dispatch_roundtrip_capture_bundle_provider_profile_text(provider_summary, dispatch_roundtrip),
            "matches",
            _dispatch_roundtrip_provider_profile_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_sha256",
                "sha256",
                "provider_profile_sha256",
            ),
            _dispatch_roundtrip_bool(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_matches_bundle",
                "provider_profile_matches_bundle",
            )
            if dispatch_bundle_provided
            else True,
            "provider imbalance cutover round-trip provider-profile proof no longer matches capture bundle",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            _dispatch_roundtrip_adapter_contract_provider_profile_text(provider_summary, dispatch_roundtrip),
            "==",
            _dispatch_roundtrip_provider_profile_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_sha256",
                "sha256",
                "provider_profile_sha256",
            ),
            _dispatch_roundtrip_bool(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
                "adapter_contract_provider_profile_matches_evidence",
            )
            if dispatch_bundle_provided
            else True,
            "provider imbalance cutover round-trip adapter contract provider-profile SHA no longer matches evidence",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_profile_matches_runtime_session",
            _dispatch_roundtrip_provider_profile_metadata_text(provider_summary, dispatch_roundtrip),
            "matches",
            _provider_profile_metadata_text(provider_summary),
            dispatch_provider_profile_matches_runtime_session if dispatch_bundle_provided else True,
            "provider imbalance cutover round-trip provider profile no longer matches runtime-session proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_synthetic_sidecar_proof_carried",
            dispatch_synthetic_sidecar_count,
            "==",
            dispatch_synthetic_dataset_count,
            (
                dispatch_synthetic_sidecar_count_matches
                if dispatch_synthetic_sidecar_proof_required
                else True
            ),
            "provider imbalance cutover is missing broker-readiness round-trip synthetic rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_synthetic_sidecar_proof_ready",
            dispatch_synthetic_sidecar_proof_ready,
            "is",
            True,
            (
                dispatch_synthetic_sidecar_proof_ready
                if dispatch_synthetic_sidecar_proof_required
                else True
            ),
            "provider imbalance cutover round-trip synthetic rehearsal sidecar proof is not ready",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_route_readiness_provider_sidecar_breach_pairs",
            dispatch_route_sidecar_breach_pairs,
            "<=",
            0,
            (
                dispatch_route_sidecar_breach_pairs <= 0
                if dispatch_route_sidecar_gate_active
                else True
            ),
            "provider imbalance cutover carries broker-readiness final round-trip route-readiness sidecar breaches",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    provider_root: Path,
    scaleup_dir: Path | None,
    broker_readiness_dir: Path | None,
    runtime_session_dir: Path | None,
    operator_review_path: Path | None,
    provider_dispatch_roundtrip_dir: Path | None,
    dispatch_roundtrip_dir: Path | None,
    upstream_provider_dispatch_roundtrip_dir: Path | None,
    upstream_dispatch_roundtrip_dir: Path | None,
    cutover: CutoverGateReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    cutover_summary = cutover.summary if cutover is not None else pd.DataFrame()
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_broker_readiness_ready": _first_bool(provider_summary, "ready"),
                "cutover_ready": bool(cutover is not None and cutover.ready),
                "provider_broker_readiness_dir": str(provider_root),
                "scaleup_dir": _path_text(scaleup_dir),
                "broker_readiness_dir": _path_text(broker_readiness_dir),
                "runtime_session_dir": _path_text(runtime_session_dir),
                "operator_review_path": _path_text(operator_review_path),
                "exchange": _first_text(provider_summary, "exchange"),
                "source_session_timezone": _first_text(provider_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(provider_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(provider_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(provider_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(provider_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(provider_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(provider_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(provider_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(provider_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(provider_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(provider_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    provider_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    provider_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    provider_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    provider_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    provider_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    provider_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    provider_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    provider_summary,
                    "capture_bundle_live_fetch_contract_metadata_matches_session",
                ),
                "capture_env_template_path": _first_text(provider_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(provider_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(provider_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(provider_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(provider_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(provider_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(provider_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(provider_summary, "adapter_handoff_sha256"),
                "source_credential_env_template_path": _first_text(
                    provider_summary,
                    "source_credential_env_template_path",
                ),
                "source_credential_env_template_exists": _first_bool(
                    provider_summary,
                    "source_credential_env_template_exists",
                ),
                "source_credential_env_template_sha256": _first_text(
                    provider_summary,
                    "source_credential_env_template_sha256",
                ),
                "source_live_fetch_contract_available": _first_bool(
                    provider_summary,
                    "source_live_fetch_contract_available",
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_next_gate",
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_command_template",
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_exchange",
                ),
                "source_live_fetch_contract_market": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_market",
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_session_timezone",
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_session_open_local",
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_session_close_local",
                ),
                "adapter_contract_provider": _first_text(provider_summary, "adapter_contract_provider"),
                "adapter_contract_transport": _first_text(provider_summary, "adapter_contract_transport"),
                "adapter_contract_market": _first_text(provider_summary, "adapter_contract_market"),
                "adapter_contract_exchange": _first_text(provider_summary, "adapter_contract_exchange"),
                "adapter_contract_values_stored": _first_bool(provider_summary, "adapter_contract_values_stored"),
                "adapter_contract_metadata_matches_evidence": _first_bool(
                    provider_summary,
                    "adapter_contract_metadata_matches_evidence",
                ),
                "provider_profile_sha256": _first_text(provider_summary, "provider_profile_sha256"),
                "provider_profile_adapter": _first_text(provider_summary, "provider_profile_adapter"),
                "provider_profile_auth_required": _first_bool(provider_summary, "provider_profile_auth_required"),
                "provider_profile_transports": _first_text(provider_summary, "provider_profile_transports"),
                "provider_profile_capabilities": _first_text(provider_summary, "provider_profile_capabilities"),
                "capture_bundle_provider_profile_sha256": _first_text(
                    provider_summary,
                    "capture_bundle_provider_profile_sha256",
                ),
                "provider_profile_matches_session": _first_bool(
                    provider_summary,
                    "provider_profile_matches_session",
                ),
                "provider_profile_matches_bundle": _first_bool(
                    provider_summary,
                    "provider_profile_matches_bundle",
                )
                if _first_bool(provider_summary, "capture_bundle_provided")
                else True,
                "adapter_contract_provider_profile_sha256": _first_text(
                    provider_summary,
                    "adapter_contract_provider_profile_sha256",
                ),
                "adapter_contract_provider_profile_matches_evidence": _first_bool(
                    provider_summary,
                    "adapter_contract_provider_profile_matches_evidence",
                ),
                "provider_capture_command_count": int(
                    _first_number(provider_summary, "provider_capture_command_count")
                ),
                "provider_capture_command_providers": _first_text(
                    provider_summary,
                    "provider_capture_command_providers",
                ),
                "provider_capture_command_transports": _first_text(
                    provider_summary,
                    "provider_capture_command_transports",
                ),
                "capture_bundle_provider_capture_command_count": int(
                    _first_number(provider_summary, "capture_bundle_provider_capture_command_count")
                ),
                "capture_bundle_provider_capture_command_missing_count": int(
                    _first_number(provider_summary, "capture_bundle_provider_capture_command_missing_count")
                ),
                "capture_bundle_provider_capture_commands_match_session": _first_bool(
                    provider_summary,
                    "capture_bundle_provider_capture_commands_match_session",
                )
                if _first_bool(provider_summary, "capture_bundle_provided")
                else True,
                "synthetic_dataset_count": int(_first_number(provider_summary, "synthetic_dataset_count")),
                "synthetic_sidecar_proof_ready": _first_bool(
                    provider_summary,
                    "synthetic_sidecar_proof_ready",
                ),
                "synthetic_sidecar_count": int(_first_number(provider_summary, "synthetic_sidecar_count")),
                "synthetic_sidecar_readable_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_readable_count")
                ),
                "synthetic_sidecar_source_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_source_count")
                ),
                "synthetic_sidecar_adapter_command_hash_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_adapter_command_hash_count")
                ),
                "synthetic_sidecar_capture_env_template_match_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_capture_env_template_match_count")
                ),
                "synthetic_sidecar_adapter_handoff_match_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_adapter_handoff_match_count")
                ),
                "synthetic_sidecar_source_env_template_match_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_source_env_template_match_count")
                ),
                "synthetic_sidecar_live_fetch_contract_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_live_fetch_contract_count")
                ),
                "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_adapter_execution_contract_safe_count")
                ),
                "synthetic_sidecar_invariant_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_invariant_count")
                ),
                "route_readiness_provided": _first_bool(provider_summary, "route_readiness_provided"),
                "route_readiness_ops_launch_controls_present": _first_bool(
                    provider_summary,
                    "route_readiness_ops_launch_controls_present",
                ),
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    _first_number(
                        provider_summary,
                        "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                    )
                ),
                "dispatch_roundtrip_route_readiness_provided": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_route_readiness_provided",
                    "route_readiness_provided",
                ),
                "dispatch_roundtrip_route_readiness_ops_launch_controls_present": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_route_readiness_ops_launch_controls_present",
                    "route_readiness_ops_launch_controls_present",
                ),
                "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                        "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                    )
                ),
                "dispatch_roundtrip_synthetic_dataset_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_dataset_count",
                        "synthetic_dataset_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_proof_ready": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_synthetic_sidecar_proof_ready",
                    "synthetic_sidecar_proof_ready",
                ),
                "dispatch_roundtrip_synthetic_sidecar_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_count",
                        "synthetic_sidecar_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_readable_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_readable_count",
                        "synthetic_sidecar_readable_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_source_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_source_count",
                        "synthetic_sidecar_source_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count",
                        "synthetic_sidecar_adapter_command_hash_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count",
                        "synthetic_sidecar_capture_env_template_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count",
                        "synthetic_sidecar_adapter_handoff_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count",
                        "synthetic_sidecar_source_env_template_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count",
                        "synthetic_sidecar_live_fetch_contract_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count",
                        "synthetic_sidecar_adapter_execution_contract_safe_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_invariant_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_synthetic_sidecar_invariant_count",
                        "synthetic_sidecar_invariant_count",
                    )
                ),
                "dispatch_roundtrip_provider_capture_command_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_provider_capture_command_count",
                        "provider_capture_command_count",
                    )
                ),
                "dispatch_roundtrip_provider_capture_command_providers": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_capture_command_providers",
                    "provider_capture_command_providers",
                ),
                "dispatch_roundtrip_provider_capture_command_transports": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_capture_command_transports",
                    "provider_capture_command_transports",
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_command_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
                        "capture_bundle_provider_capture_command_count",
                    )
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": int(
                    _dispatch_roundtrip_number(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
                        "capture_bundle_provider_capture_command_missing_count",
                    )
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": (
                    _dispatch_roundtrip_bool(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
                        "capture_bundle_provider_capture_commands_match_session",
                    )
                )
                if _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                )
                else True,
                "dispatch_roundtrip_provider_capture_commands_match_runtime_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
                    "provider_capture_commands_match_runtime_session",
                ),
                "dispatch_roundtrip_adapter_contract_provider": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_provider",
                    "adapter_contract_provider",
                ),
                "dispatch_roundtrip_adapter_contract_transport": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_transport",
                    "adapter_contract_transport",
                ),
                "dispatch_roundtrip_adapter_contract_market": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_market",
                    "adapter_contract_market",
                ),
                "dispatch_roundtrip_adapter_contract_exchange": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_exchange",
                    "adapter_contract_exchange",
                ),
                "dispatch_roundtrip_adapter_contract_values_stored": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_values_stored",
                    "adapter_contract_values_stored",
                ),
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
                    "adapter_contract_metadata_matches_evidence",
                ),
                "dispatch_roundtrip_adapter_contract_matches_runtime_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_matches_runtime_session",
                    "adapter_contract_matches_runtime_session",
                )
                if _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                )
                else True,
                "dispatch_roundtrip_provider_profile_sha256": _dispatch_roundtrip_provider_profile_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_sha256",
                    "sha256",
                    "provider_profile_sha256",
                ),
                "dispatch_roundtrip_provider_profile_adapter": _dispatch_roundtrip_provider_profile_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_adapter",
                    "adapter",
                    "provider_profile_adapter",
                ),
                "dispatch_roundtrip_provider_profile_auth_required": _dispatch_roundtrip_provider_profile_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_auth_required",
                    "auth_required",
                    "provider_profile_auth_required",
                ),
                "dispatch_roundtrip_provider_profile_transports": _dispatch_roundtrip_provider_profile_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_transports",
                    "transports",
                    "provider_profile_transports",
                ),
                "dispatch_roundtrip_provider_profile_capabilities": _dispatch_roundtrip_provider_profile_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_capabilities",
                    "capabilities",
                    "provider_profile_capabilities",
                ),
                "dispatch_roundtrip_capture_bundle_provider_profile_sha256": (
                    _dispatch_roundtrip_capture_bundle_provider_profile_text(provider_summary, dispatch_roundtrip)
                ),
                "dispatch_roundtrip_provider_profile_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_matches_session",
                    "provider_profile_matches_session",
                )
                if _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                )
                else True,
                "dispatch_roundtrip_provider_profile_matches_bundle": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_provider_profile_matches_bundle",
                    "provider_profile_matches_bundle",
                )
                if _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                )
                else True,
                "dispatch_roundtrip_adapter_contract_provider_profile_sha256": (
                    _dispatch_roundtrip_adapter_contract_provider_profile_text(provider_summary, dispatch_roundtrip)
                ),
                "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
                    "adapter_contract_provider_profile_matches_evidence",
                ),
                "dispatch_roundtrip_provider_profile_matches_runtime_session": (
                    _dispatch_roundtrip_provider_profile_matches_session(provider_summary, dispatch_roundtrip)
                )
                if _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                )
                else True,
                "dispatch_roundtrip_exchange": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_exchange",
                    "exchange",
                ),
                "dispatch_roundtrip_source_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_session_timezone",
                )
                or _nested_text(dispatch_roundtrip, "source_session", "timezone"),
                "dispatch_roundtrip_source_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_session_open_local",
                )
                or _nested_text(dispatch_roundtrip, "source_session", "open_local"),
                "dispatch_roundtrip_source_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_session_close_local",
                )
                or _nested_text(dispatch_roundtrip, "source_session", "close_local"),
                "dispatch_roundtrip_market_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_market_session_timezone",
                )
                or _nested_text(dispatch_roundtrip, "market_session", "timezone"),
                "dispatch_roundtrip_market_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_market_session_open_local",
                )
                or _nested_text(dispatch_roundtrip, "market_session", "open_local"),
                "dispatch_roundtrip_market_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_market_session_close_local",
                )
                or _nested_text(dispatch_roundtrip, "market_session", "close_local"),
                "dispatch_roundtrip_exchange_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_exchange_matches_session",
                    "exchange_matches_session",
                ),
                "dispatch_roundtrip_source_session_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_session_matches_session",
                    "source_session_matches_session",
                ),
                "dispatch_roundtrip_market_session_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_market_session_matches_session",
                    "market_session_matches_session",
                ),
                "dispatch_roundtrip_metadata_consistent": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_metadata_consistent",
                    "metadata_consistent_with_runtime_session",
                ),
                "dispatch_roundtrip_source_credential_env_template_path": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_credential_env_template_path",
                    "source_credential_env_template_path",
                ),
                "dispatch_roundtrip_source_credential_env_template_exists": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_credential_env_template_exists",
                    "source_credential_env_template_exists",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_credential_env_template_sha256",
                    "source_credential_env_template_sha256",
                ),
                "dispatch_roundtrip_source_credential_env_template_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_credential_env_template_matches_session",
                    "source_credential_env_template_matches_session",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_credential_env_template_sha256_matches_session",
                    "source_credential_env_template_sha256_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_available": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_available",
                    "source_live_fetch_contract_available",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate",
                    "source_live_fetch_contract_next_gate",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_command_template",
                    "source_live_fetch_contract_command_template",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_exchange",
                    "source_live_fetch_contract_exchange",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_market": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_market",
                    "source_live_fetch_contract_market",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_timezone",
                )
                or _nested_text(dispatch_roundtrip, "source_live_fetch_contract_session", "timezone"),
                "dispatch_roundtrip_source_live_fetch_contract_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
                )
                or _nested_text(dispatch_roundtrip, "source_live_fetch_contract_session", "open_local"),
                "dispatch_roundtrip_source_live_fetch_contract_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_close_local",
                )
                or _nested_text(dispatch_roundtrip, "source_live_fetch_contract_session", "close_local"),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session",
                    "source_live_fetch_contract_next_gate_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": (
                    _dispatch_roundtrip_bool(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session",
                        "source_live_fetch_contract_command_template_matches_session",
                    )
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
                    "source_live_fetch_contract_exchange_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_market_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_market_matches_session",
                    "source_live_fetch_contract_market_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_live_fetch_contract_session_matches_session",
                    "source_live_fetch_contract_session_matches_session",
                ),
                "dispatch_roundtrip_source_provenance_consistent": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_source_provenance_consistent",
                    "source_provenance_consistent_with_runtime_session",
                ),
                "dispatch_roundtrip_capture_bundle_path": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_path",
                    "capture_bundle_path",
                ),
                "dispatch_roundtrip_capture_bundle_provided": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                ),
                "dispatch_roundtrip_capture_bundle_exists": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_exists",
                    "capture_bundle_exists",
                ),
                "dispatch_roundtrip_capture_bundle_ready": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_ready",
                    "capture_bundle_ready",
                ),
                "dispatch_roundtrip_capture_bundle_exchange": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_exchange",
                    "capture_bundle_exchange",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_timezone",
                )
                or _nested_text(dispatch_roundtrip, "capture_bundle_source_session", "timezone"),
                "dispatch_roundtrip_capture_bundle_source_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_open_local",
                )
                or _nested_text(dispatch_roundtrip, "capture_bundle_source_session", "open_local"),
                "dispatch_roundtrip_capture_bundle_source_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_close_local",
                )
                or _nested_text(dispatch_roundtrip, "capture_bundle_source_session", "close_local"),
                "dispatch_roundtrip_capture_bundle_market_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_timezone",
                )
                or _nested_text(dispatch_roundtrip, "capture_bundle_market_session", "timezone"),
                "dispatch_roundtrip_capture_bundle_market_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_open_local",
                )
                or _nested_text(dispatch_roundtrip, "capture_bundle_market_session", "open_local"),
                "dispatch_roundtrip_capture_bundle_market_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_close_local",
                )
                or _nested_text(dispatch_roundtrip, "capture_bundle_market_session", "close_local"),
                "dispatch_roundtrip_capture_bundle_metadata_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_metadata_matches_session",
                    "capture_bundle_metadata_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session": (
                    _dispatch_roundtrip_bool(
                        provider_summary,
                        dispatch_roundtrip,
                        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
                        "capture_bundle_live_fetch_contract_metadata_matches_session",
                    )
                ),
                "dispatch_roundtrip_capture_bundle_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_matches_session",
                    "capture_bundle_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_exchange_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_exchange_matches_session",
                    "capture_bundle_exchange_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_source_session_matches_session",
                    "capture_bundle_source_session_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_bundle_market_session_matches_session",
                    "capture_bundle_market_session_matches_session",
                ),
                "dispatch_roundtrip_capture_env_template_path": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_env_template_path",
                    "capture_env_template_path",
                ),
                "dispatch_roundtrip_capture_env_template_provided": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_env_template_provided",
                    "capture_env_template_provided",
                ),
                "dispatch_roundtrip_capture_env_template_exists": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_env_template_exists",
                    "capture_env_template_exists",
                ),
                "dispatch_roundtrip_capture_env_template_sha256": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_env_template_sha256",
                    "capture_env_template_sha256",
                ),
                "dispatch_roundtrip_capture_env_template_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_env_template_matches_session",
                    "capture_env_template_matches_session",
                ),
                "dispatch_roundtrip_adapter_handoff_path": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_handoff_path",
                    "adapter_handoff_path",
                ),
                "dispatch_roundtrip_adapter_handoff_provided": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_handoff_provided",
                    "adapter_handoff_provided",
                ),
                "dispatch_roundtrip_adapter_handoff_exists": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_handoff_exists",
                    "adapter_handoff_exists",
                ),
                "dispatch_roundtrip_adapter_handoff_sha256": _dispatch_roundtrip_text(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_handoff_sha256",
                    "adapter_handoff_sha256",
                ),
                "dispatch_roundtrip_adapter_handoff_matches_session": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_adapter_handoff_matches_session",
                    "adapter_handoff_matches_session",
                ),
                "dispatch_roundtrip_capture_provenance_consistent": _dispatch_roundtrip_bool(
                    provider_summary,
                    dispatch_roundtrip,
                    "dispatch_roundtrip_capture_provenance_consistent",
                    "consistent_with_runtime_session",
                ),
                "provider_dispatch_roundtrip_dir": _path_text(provider_dispatch_roundtrip_dir),
                "dispatch_roundtrip_dir": _path_text(dispatch_roundtrip_dir),
                "upstream_provider_dispatch_roundtrip_dir": _path_text(upstream_provider_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_dir": _path_text(upstream_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_provided": bool(upstream_dispatch_roundtrip_dir)
                or _first_bool(provider_summary, "upstream_dispatch_roundtrip_provided"),
                "upstream_dispatch_roundtrip_ready": _first_bool(
                    provider_summary,
                    "upstream_dispatch_roundtrip_ready",
                ),
                "upstream_dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "upstream_dispatch_roundtrip_failed_checks")
                ),
                "dispatch_roundtrip_provided": _first_bool(provider_summary, "dispatch_roundtrip_provided"),
                "dispatch_roundtrip_ready": _first_bool(provider_summary, "dispatch_roundtrip_ready"),
                "dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "dispatch_roundtrip_failed_checks")
                ),
                **_provider_broker_readiness_vendor_market_data_batch_summary_fields(provider_summary),
                "cutover_dir": "" if cutover is None else str(cutover.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(cutover_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(cutover_summary, "strategy")
                or _first_text(provider_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(cutover_summary, "target_mode")
                or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(cutover_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(cutover_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "max_orders": _first_text(cutover_summary, "max_orders"),
                "max_notional": _first_text(cutover_summary, "max_notional"),
                "operator_approved": _first_bool(cutover_summary, "operator_approved"),
                "cutover_recommendation": _first_text(cutover_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "prepare_provider_imbalance_route_enable"
                if ready
                else "repair_provider_imbalance_cutover",
                "next_gate": "review-route-enable" if ready else _blocked_next_gate(checks, cutover),
                "next_gate_help_command": _help_command_for_gate(
                    "review-route-enable" if ready else _blocked_next_gate(checks, cutover)
                ),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _provider_broker_readiness_vendor_market_data_batch_summary_fields(
    provider_summary: pd.DataFrame,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for prefix in (
        *VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES,
        *UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES,
    ):
        for suffix in VENDOR_MARKET_DATA_BATCH_BOOL_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_bool(provider_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_INT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = int(_first_number(provider_summary, f"{prefix}_{suffix}"))
        for suffix in VENDOR_MARKET_DATA_BATCH_FLOAT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_number(provider_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_TEXT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_text(provider_summary, f"{prefix}_{suffix}")
    return fields


def _provider_broker_readiness_vendor_market_data_batch_config(
    provider_config: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    vendor = provider_config.get(key, {})
    return dict(vendor) if isinstance(vendor, dict) else {}


def _dispatch_roundtrip_provenance(provider_config: dict[str, Any]) -> dict[str, Any]:
    value = provider_config.get("dispatch_roundtrip_provenance", {})
    return value if isinstance(value, dict) else {}


def _nested_text(mapping: dict[str, Any], key: str, nested_key: str) -> str:
    value = mapping.get(key, {})
    if not isinstance(value, dict):
        return ""
    return _clean(value.get(nested_key))


def _dispatch_roundtrip_text(
    frame: pd.DataFrame | None,
    provenance: dict[str, Any],
    column: str,
    fallback_key: str,
) -> str:
    if _first_value_present(frame, column):
        return _first_text(frame, column)
    return _clean(provenance.get(fallback_key))


def _dispatch_roundtrip_bool(
    frame: pd.DataFrame | None,
    provenance: dict[str, Any],
    column: str,
    fallback_key: str,
) -> bool:
    if _first_value_present(frame, column):
        return _first_bool(frame, column)
    return _truthy(provenance.get(fallback_key))


def _dispatch_roundtrip_number(
    frame: pd.DataFrame | None,
    provenance: dict[str, Any],
    column: str,
    fallback_key: str,
    fallback: float = 0.0,
) -> float:
    sidecar_fallback = _number_from_value(provenance.get(fallback_key), fallback)
    if _first_value_present(frame, column):
        value = _first_number(frame, column, fallback)
        if value == 0 and sidecar_fallback > 0:
            return sidecar_fallback
        return value
    return sidecar_fallback


def _number_from_value(value: object, fallback: float = 0.0) -> float:
    text = _clean(value)
    if not text:
        return fallback
    try:
        return float(text)
    except (TypeError, ValueError):
        return fallback


def _dispatch_roundtrip_provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return _list(dispatch_roundtrip.get("provider_capture_commands")) or _provider_capture_commands(provider_config)


def _dispatch_roundtrip_bundle_provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return _list(
        dispatch_roundtrip.get("capture_bundle_provider_capture_commands")
    ) or _bundle_provider_capture_commands(provider_config)


def _dispatch_roundtrip_adapter_execution_contract(provider_config: dict[str, Any]) -> dict[str, Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return _mapping(dispatch_roundtrip.get("adapter_execution_contract")) or _adapter_execution_contract(
        provider_config
    )


def _dispatch_roundtrip_provider_profile(provider_config: dict[str, Any]) -> dict[str, Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return _mapping(dispatch_roundtrip.get("provider_profile")) or _mapping(provider_config.get("provider_profile"))


def _dispatch_roundtrip_live_session_provider_profile(provider_config: dict[str, Any]) -> dict[str, Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return _mapping(dispatch_roundtrip.get("live_session_provider_profile")) or _mapping(
        provider_config.get("live_session_provider_profile")
    )


def _dispatch_roundtrip_capture_bundle_provider_profile(provider_config: dict[str, Any]) -> dict[str, Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    bundle = _mapping(provider_config.get("capture_bundle"))
    return (
        _mapping(dispatch_roundtrip.get("capture_bundle_provider_profile"))
        or _mapping(bundle.get("capture_bundle_provider_profile"))
        or _mapping(bundle.get("provider_profile"))
    )


def _dispatch_roundtrip_synthetic_sidecar_proof(provider_config: dict[str, Any]) -> dict[str, Any]:
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return _mapping(dispatch_roundtrip.get("synthetic_sidecar_proof"))


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    if not action_queue.empty:
        out["primary_action_status"] = str(action_queue.iloc[0].get("queue_status", ""))
        out["next_gate"] = str(action_queue.iloc[0].get("next_gate", out.iloc[0].get("next_gate", "")))
        out["next_gate_help_command"] = str(
            action_queue.iloc[0].get("next_gate_help_command", out.iloc[0].get("next_gate_help_command", ""))
        )
    return out


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    cutover: CutoverGateReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_cutover_summary",
                    "component": "cutover",
                    "check": "cutover_ready",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "prepare_provider_imbalance_route_enable",
                    "reason": "provider imbalance cutover is clear for route-enable review",
                    "recommendation": "feed_cutover_into_route_enable",
                    "next_gate": "review-route-enable",
                    "next_gate_help_command": _help_command_for_gate("review-route-enable"),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    failed_rows = sorted(
        failed.to_dict(orient="records"),
        key=lambda row: _action_priority(str(row.get("check", ""))),
    )
    for check in failed_rows:
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, cutover)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_cutover_checks",
                "component": _component_for_check(name),
                "check": name,
                "actual": check.get("value"),
                "operator": check.get("operator"),
                "expected": check.get("threshold"),
                "action": _action_for_check(name),
                "reason": str(check.get("reason", "")) or name.replace("_", " "),
                "recommendation": _recommendation_for_check(name),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_cutover_checks",
                "component": "cutover",
                "check": "provider_cutover_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_cutover",
                "reason": "provider imbalance cutover is not ready",
                "recommendation": "rerun_provider_imbalance_cutover",
                "next_gate": "review-provider-market-data-imbalance-cutover",
                "next_gate_help_command": _help_command_for_gate("review-provider-market-data-imbalance-cutover"),
            }
        )
    return _action_frame(rows)


def _action_priority(check: str) -> int:
    if _is_dispatch_roundtrip_route_sidecar_check(check):
        return 0
    if (
        check.startswith("provider_broker_readiness")
        or check.startswith("nested_broker_readiness")
        or _is_dispatch_roundtrip_adapter_contract_check(check)
        or _is_dispatch_roundtrip_provider_profile_check(check)
        or _is_dispatch_roundtrip_synthetic_sidecar_check(check)
    ):
        return 0
    if check.startswith("nested_scaleup"):
        return 1
    if check.startswith("nested_runtime_session"):
        return 2
    if check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return 3
    if check == "cutover_ready":
        return 4
    if check.startswith("cutover"):
        return 5
    return 6


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    cutover: CutoverGateReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceCutoverConfig,
    cutover_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "cutover_inputs": _jsonable(cutover_inputs),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(provider_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(provider_config.get("live_session_provider_profile")),
        "provider_capture_commands": _provider_capture_commands(provider_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(provider_config),
        "adapter_execution_contract": _adapter_execution_contract(provider_config),
        "synthetic_sidecar_proof": _mapping(provider_config.get("synthetic_sidecar_proof")),
        "capture_bundle": {
            "capture_bundle_path": str(summary["capture_bundle_path"]),
            "capture_bundle_provided": bool(summary["capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary["capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary["capture_bundle_ready"]),
            "exchange": str(summary["capture_bundle_exchange"]),
            "source_session": _capture_bundle_source_session_contract_from_summary(summary),
            "market_session": _capture_bundle_market_session_contract_from_summary(summary),
            "capture_bundle_metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "provider_capture_command_count": int(summary["provider_capture_command_count"]),
            "provider_capture_command_providers": str(summary["provider_capture_command_providers"]),
            "provider_capture_command_transports": str(summary["provider_capture_command_transports"]),
            "capture_bundle_provider_capture_command_count": int(
                summary["capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                summary["capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                summary["capture_bundle_provider_capture_commands_match_session"]
            ),
            "provider_capture_commands": _bundle_provider_capture_commands(provider_config),
            "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(provider_config),
            "metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "live_fetch_contract_metadata_matches_session": bool(
                summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_env_template_path": str(summary["capture_env_template_path"]),
            "capture_env_template_provided": bool(summary["capture_env_template_provided"]),
            "capture_env_template_exists": bool(summary["capture_env_template_exists"]),
            "capture_env_template_sha256": str(summary["capture_env_template_sha256"]),
            "adapter_handoff_path": str(summary["adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
            "adapter_handoff_sha256": str(summary["adapter_handoff_sha256"]),
            "source_credential_env_template_path": str(summary["source_credential_env_template_path"]),
            "source_credential_env_template_exists": bool(summary["source_credential_env_template_exists"]),
            "source_credential_env_template_sha256": str(summary["source_credential_env_template_sha256"]),
            "source_live_fetch_contract_available": bool(summary["source_live_fetch_contract_available"]),
            "source_live_fetch_contract_next_gate": str(summary["source_live_fetch_contract_next_gate"]),
            "source_live_fetch_contract_command_template": str(
                summary["source_live_fetch_contract_command_template"]
            ),
            "source_live_fetch_contract_exchange": str(summary["source_live_fetch_contract_exchange"]),
            "source_live_fetch_contract_market": str(summary["source_live_fetch_contract_market"]),
            "source_live_fetch_contract_session_timezone": str(
                summary["source_live_fetch_contract_session_timezone"]
            ),
            "source_live_fetch_contract_session_open_local": str(
                summary["source_live_fetch_contract_session_open_local"]
            ),
            "source_live_fetch_contract_session_close_local": str(
                summary["source_live_fetch_contract_session_close_local"]
            ),
            "adapter_execution_contract": _adapter_execution_contract(provider_config),
            "adapter_contract_provider": str(summary["adapter_contract_provider"]),
            "adapter_contract_transport": str(summary["adapter_contract_transport"]),
            "adapter_contract_market": str(summary["adapter_contract_market"]),
            "adapter_contract_exchange": str(summary["adapter_contract_exchange"]),
            "adapter_contract_values_stored": bool(summary["adapter_contract_values_stored"]),
            "adapter_contract_metadata_matches_evidence": bool(
                summary["adapter_contract_metadata_matches_evidence"]
            ),
            "provider_profile": _mapping(provider_config.get("provider_profile")),
            "live_session_provider_profile": _mapping(provider_config.get("live_session_provider_profile")),
            "capture_bundle_provider_profile": _mapping(
                _mapping(provider_config.get("capture_bundle")).get("capture_bundle_provider_profile")
            ),
            "provider_profile_sha256": str(summary["provider_profile_sha256"]),
            "provider_profile_matches_session": bool(summary["provider_profile_matches_session"]),
            "provider_profile_matches_bundle": bool(summary["provider_profile_matches_bundle"]),
            "adapter_contract_provider_profile_sha256": str(summary["adapter_contract_provider_profile_sha256"]),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary["adapter_contract_provider_profile_matches_evidence"]
            ),
        },
        "dispatch_roundtrip_provenance": {
            "exchange": str(summary["dispatch_roundtrip_exchange"]),
            "source_session": _dispatch_roundtrip_source_session_contract_from_summary(summary),
            "market_session": _dispatch_roundtrip_market_session_contract_from_summary(summary),
            "exchange_matches_session": bool(summary["dispatch_roundtrip_exchange_matches_session"]),
            "source_session_matches_session": bool(summary["dispatch_roundtrip_source_session_matches_session"]),
            "market_session_matches_session": bool(summary["dispatch_roundtrip_market_session_matches_session"]),
            "metadata_consistent_with_runtime_session": bool(summary["dispatch_roundtrip_metadata_consistent"]),
            "synthetic_sidecar_proof": _dispatch_roundtrip_synthetic_sidecar_proof(provider_config),
            "synthetic_dataset_count": int(summary["dispatch_roundtrip_synthetic_dataset_count"]),
            "synthetic_sidecar_proof_ready": bool(
                summary["dispatch_roundtrip_synthetic_sidecar_proof_ready"]
            ),
            "synthetic_sidecar_count": int(summary["dispatch_roundtrip_synthetic_sidecar_count"]),
            "synthetic_sidecar_readable_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_readable_count"]
            ),
            "route_readiness_provided": bool(summary["dispatch_roundtrip_route_readiness_provided"]),
            "route_readiness_ops_launch_controls_present": bool(
                summary["dispatch_roundtrip_route_readiness_ops_launch_controls_present"]
            ),
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                summary[
                    "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"
                ]
            ),
            "synthetic_sidecar_source_count": int(summary["dispatch_roundtrip_synthetic_sidecar_source_count"]),
            "synthetic_sidecar_adapter_command_hash_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count"]
            ),
            "synthetic_sidecar_capture_env_template_match_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count"]
            ),
            "synthetic_sidecar_adapter_handoff_match_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count"]
            ),
            "synthetic_sidecar_source_env_template_match_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count"]
            ),
            "synthetic_sidecar_live_fetch_contract_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count"]
            ),
            "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count"]
            ),
            "synthetic_sidecar_invariant_count": int(
                summary["dispatch_roundtrip_synthetic_sidecar_invariant_count"]
            ),
            "provider_capture_command_count": int(summary["dispatch_roundtrip_provider_capture_command_count"]),
            "provider_capture_command_providers": str(
                summary["dispatch_roundtrip_provider_capture_command_providers"]
            ),
            "provider_capture_command_transports": str(
                summary["dispatch_roundtrip_provider_capture_command_transports"]
            ),
            "capture_bundle_provider_capture_command_count": int(
                summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
            ),
            "provider_capture_commands": _dispatch_roundtrip_provider_capture_commands(provider_config),
            "capture_bundle_provider_capture_commands": _dispatch_roundtrip_bundle_provider_capture_commands(
                provider_config
            ),
            "provider_capture_commands_match_runtime_session": bool(
                summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
            ),
            "adapter_execution_contract": _dispatch_roundtrip_adapter_execution_contract(provider_config),
            "adapter_contract_provider": str(summary["dispatch_roundtrip_adapter_contract_provider"]),
            "adapter_contract_transport": str(summary["dispatch_roundtrip_adapter_contract_transport"]),
            "adapter_contract_market": str(summary["dispatch_roundtrip_adapter_contract_market"]),
            "adapter_contract_exchange": str(summary["dispatch_roundtrip_adapter_contract_exchange"]),
            "adapter_contract_values_stored": bool(summary["dispatch_roundtrip_adapter_contract_values_stored"]),
            "adapter_contract_metadata_matches_evidence": bool(
                summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"]
            ),
            "adapter_contract_matches_runtime_session": bool(
                summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
            ),
            "provider_profile": _dispatch_roundtrip_provider_profile(provider_config),
            "live_session_provider_profile": _dispatch_roundtrip_live_session_provider_profile(provider_config),
            "capture_bundle_provider_profile": _dispatch_roundtrip_capture_bundle_provider_profile(provider_config),
            "provider_profile_sha256": str(summary["dispatch_roundtrip_provider_profile_sha256"]),
            "provider_profile_matches_session": bool(summary["dispatch_roundtrip_provider_profile_matches_session"]),
            "provider_profile_matches_bundle": bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"]),
            "provider_profile_matches_runtime_session": bool(
                summary["dispatch_roundtrip_provider_profile_matches_runtime_session"]
            ),
            "adapter_contract_provider_profile_sha256": str(
                summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
            ),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
            ),
            "capture_bundle_path": str(summary["dispatch_roundtrip_capture_bundle_path"]),
            "capture_bundle_provided": bool(summary["dispatch_roundtrip_capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary["dispatch_roundtrip_capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary["dispatch_roundtrip_capture_bundle_ready"]),
            "capture_bundle_exchange": str(summary["dispatch_roundtrip_capture_bundle_exchange"]),
            "capture_bundle_source_session": _dispatch_roundtrip_capture_bundle_source_session_contract_from_summary(
                summary
            ),
            "capture_bundle_market_session": _dispatch_roundtrip_capture_bundle_market_session_contract_from_summary(
                summary
            ),
            "capture_bundle_metadata_matches_session": bool(
                summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"]
            ),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_bundle_matches_session": bool(summary["dispatch_roundtrip_capture_bundle_matches_session"]),
            "capture_bundle_exchange_matches_session": bool(
                summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"]
            ),
            "capture_bundle_source_session_matches_session": bool(
                summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"]
            ),
            "capture_bundle_market_session_matches_session": bool(
                summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"]
            ),
            "capture_env_template_path": str(summary["dispatch_roundtrip_capture_env_template_path"]),
            "capture_env_template_provided": bool(summary["dispatch_roundtrip_capture_env_template_provided"]),
            "capture_env_template_exists": bool(summary["dispatch_roundtrip_capture_env_template_exists"]),
            "capture_env_template_sha256": str(summary["dispatch_roundtrip_capture_env_template_sha256"]),
            "capture_env_template_matches_session": bool(
                summary["dispatch_roundtrip_capture_env_template_matches_session"]
            ),
            "adapter_handoff_path": str(summary["dispatch_roundtrip_adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["dispatch_roundtrip_adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["dispatch_roundtrip_adapter_handoff_exists"]),
            "adapter_handoff_sha256": str(summary["dispatch_roundtrip_adapter_handoff_sha256"]),
            "adapter_handoff_matches_session": bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"]),
            "consistent_with_runtime_session": bool(summary["dispatch_roundtrip_capture_provenance_consistent"]),
            "source_credential_env_template_path": str(
                summary["dispatch_roundtrip_source_credential_env_template_path"]
            ),
            "source_credential_env_template_exists": bool(
                summary["dispatch_roundtrip_source_credential_env_template_exists"]
            ),
            "source_credential_env_template_sha256": str(
                summary["dispatch_roundtrip_source_credential_env_template_sha256"]
            ),
            "source_credential_env_template_matches_session": bool(
                summary["dispatch_roundtrip_source_credential_env_template_matches_session"]
            ),
            "source_credential_env_template_sha256_matches_session": bool(
                summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"]
            ),
            "source_live_fetch_contract_available": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_available"]
            ),
            "source_live_fetch_contract_next_gate": str(
                summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"]
            ),
            "source_live_fetch_contract_command_template": str(
                summary["dispatch_roundtrip_source_live_fetch_contract_command_template"]
            ),
            "source_live_fetch_contract_exchange": str(
                summary["dispatch_roundtrip_source_live_fetch_contract_exchange"]
            ),
            "source_live_fetch_contract_market": str(
                summary["dispatch_roundtrip_source_live_fetch_contract_market"]
            ),
            "source_live_fetch_contract_session": (
                _dispatch_roundtrip_source_live_fetch_contract_session_from_summary(summary)
            ),
            "source_live_fetch_contract_next_gate_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"]
            ),
            "source_live_fetch_contract_command_template_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"]
            ),
            "source_live_fetch_contract_exchange_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"]
            ),
            "source_live_fetch_contract_market_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"]
            ),
            "source_live_fetch_contract_session_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"]
            ),
            "source_provenance_consistent_with_runtime_session": bool(
                summary["dispatch_roundtrip_source_provenance_consistent"]
            ),
        },
        "provider_broker_readiness": _first_record(provider_summary),
        "provider_broker_readiness_config": provider_config,
        "upstream_dispatch_roundtrip_vendor_market_data_batch": (
            _provider_broker_readiness_vendor_market_data_batch_config(
                provider_config,
                "upstream_dispatch_roundtrip_vendor_market_data_batch",
            )
        ),
        "upstream_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _provider_broker_readiness_vendor_market_data_batch_config(
                provider_config,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
            )
        ),
        "dispatch_roundtrip_vendor_market_data_batch": _provider_broker_readiness_vendor_market_data_batch_config(
            provider_config,
            "dispatch_roundtrip_vendor_market_data_batch",
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch": (
            _provider_broker_readiness_vendor_market_data_batch_config(
                provider_config,
                "broker_dispatch_roundtrip_vendor_market_data_batch",
            )
        ),
        "cutover": {
            "evaluated": cutover is not None,
            "ready": False if cutover is None else bool(cutover.ready),
            "output_dir": "" if cutover is None else str(cutover.output_dir or ""),
            "summary": _first_record(None if cutover is None else cutover.summary),
            "authorization": _records(None if cutover is None else cutover.authorization),
            "checks": _records(None if cutover is None else cutover.checks),
            "action_queue": _records(None if cutover is None else cutover.action_queue),
            "config": {} if cutover is None or cutover.config is None else cutover.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Cutover",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Dispatch round-trip exchange: {summary['dispatch_roundtrip_exchange'] or 'unspecified'}",
        "- Dispatch round-trip source session: "
        f"{summary['dispatch_roundtrip_source_session_open_local'] or '?'} - "
        f"{summary['dispatch_roundtrip_source_session_close_local'] or '?'} "
        f"{summary['dispatch_roundtrip_source_session_timezone'] or ''}",
        f"- Target mode: {summary['target_mode']}",
        f"- Cutover dir: {summary['cutover_dir']}",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        "- Live fetch contract: "
        f"{'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        "- Adapter execution contract: "
        f"{summary['adapter_contract_provider'] or 'missing'} / "
        f"{summary['adapter_contract_transport'] or 'missing'} "
        f"(evidence match: {'yes' if bool(summary['adapter_contract_metadata_matches_evidence']) else 'no'})",
        f"- Provider profile: {summary['provider_profile_sha256'] or 'missing'} (bundle match: {'yes' if bool(summary['provider_profile_matches_bundle']) else 'no'})",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'} ({summary['synthetic_sidecar_count']}/{summary['synthetic_dataset_count']})",
        f"- Route sidecar breach pairs: {summary['route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs']}",
        "- Dispatch round-trip route sidecar breach pairs: "
        f"{summary['dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs']}",
        "- Dispatch round-trip synthetic sidecar proof: "
        f"{'yes' if bool(summary['dispatch_roundtrip_synthetic_sidecar_proof_ready']) else 'no'} "
        f"({summary['dispatch_roundtrip_synthetic_sidecar_count']}/"
        f"{summary['dispatch_roundtrip_synthetic_dataset_count']})",
        "- Dispatch round-trip live fetch contract: "
        f"{'available' if bool(summary['dispatch_roundtrip_source_live_fetch_contract_available']) else 'missing'}",
        "- Dispatch round-trip provider capture commands: "
        f"{summary['dispatch_roundtrip_provider_capture_command_count']} "
        f"(runtime match: {'yes' if bool(summary['dispatch_roundtrip_provider_capture_commands_match_runtime_session']) else 'no'})",
        "- Dispatch round-trip adapter execution contract: "
        f"{summary['dispatch_roundtrip_adapter_contract_provider'] or 'missing'} / "
        f"{summary['dispatch_roundtrip_adapter_contract_transport'] or 'missing'} "
        f"(runtime match: {'yes' if bool(summary['dispatch_roundtrip_adapter_contract_matches_runtime_session']) else 'no'}, "
        f"evidence match: {'yes' if bool(summary['dispatch_roundtrip_adapter_contract_metadata_matches_evidence']) else 'no'})",
        "- Dispatch round-trip provider profile: "
        f"{summary['dispatch_roundtrip_provider_profile_sha256'] or 'missing'} "
        f"(runtime match: {'yes' if bool(summary['dispatch_roundtrip_provider_profile_matches_runtime_session']) else 'no'}, "
        f"bundle match: {'yes' if bool(summary['dispatch_roundtrip_provider_profile_matches_bundle']) else 'no'})",
        f"- Dispatch round-trip capture bundle: {summary['dispatch_roundtrip_capture_bundle_path'] or 'not provided'}",
        "- Dispatch round-trip capture env template: "
        f"{summary['dispatch_roundtrip_capture_env_template_path'] or 'not provided'}",
        f"- Dispatch round-trip adapter handoff: {summary['dispatch_roundtrip_adapter_handoff_path'] or 'not provided'}",
        "- Dispatch round-trip provenance consistent: "
        f"{'yes' if bool(summary['dispatch_roundtrip_capture_provenance_consistent']) else 'no'}",
        "- Dispatch round-trip source credential env template: "
        f"{summary['dispatch_roundtrip_source_credential_env_template_path'] or 'not provided'}",
        "- Dispatch round-trip source provenance consistent: "
        f"{'yes' if bool(summary['dispatch_roundtrip_source_provenance_consistent']) else 'no'}",
        f"- Dispatch round-trip dir: {summary['dispatch_roundtrip_dir']}",
        "- Dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        f"- Upstream dispatch round-trip dir: {summary['upstream_dispatch_roundtrip_dir']}",
        "- Upstream dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['upstream_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Upstream broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        f"- Primary next gate: `{summary['next_gate']}`",
        f"- Primary next gate help: `{summary['next_gate_help_command']}`",
        "",
        "## Checks",
        "",
        _checks_table(checks),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _thresholds(
    config: ProviderMarketDataImbalanceCutoverConfig,
    provider_summary: pd.DataFrame,
) -> CutoverGateThresholds:
    return CutoverGateThresholds(
        target_mode=config.target_mode or _first_text(provider_summary, "target_mode") or "shadow",
        require_scaleup_ready=config.require_scaleup_ready,
        require_broker_readiness=config.require_broker_readiness,
        require_runtime_session=config.require_runtime_session,
        require_runtime_guard_continue=config.require_runtime_guard_continue,
        require_route_readiness=config.require_route_readiness,
        require_resume_gate=config.require_resume_gate,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        require_operator_approval=config.require_operator_approval,
        require_operator_identity_ack=config.require_operator_identity_ack,
        require_operator_limits_ack=config.require_operator_limits_ack,
        max_failed_scaleup_checks=config.max_failed_scaleup_checks,
    )


def _cutover_failure_reason(cutover: CutoverGateReport | None) -> str:
    if cutover is None or cutover.checks.empty:
        return ""
    failed = cutover.checks.loc[~cutover.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame, cutover: CutoverGateReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "review-provider-market-data-imbalance-cutover"
    return _next_gate_for_check(failed[0], cutover)


def _next_gate_for_check(check: str, cutover: CutoverGateReport | None) -> str:
    if _is_dispatch_roundtrip_route_sidecar_check(check):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("provider_broker_readiness_route_readiness_provider_sidecar"):
        return "review-provider-market-data-imbalance-route-readiness"
    if (
        check.startswith("provider_broker_readiness")
        or check.startswith("nested_broker_readiness")
        or _is_dispatch_roundtrip_adapter_contract_check(check)
        or _is_dispatch_roundtrip_provider_profile_check(check)
        or _is_dispatch_roundtrip_synthetic_sidecar_check(check)
    ):
        return "review-provider-market-data-imbalance-broker-readiness"
    if check.startswith("nested_scaleup"):
        return "plan-provider-market-data-imbalance-scaleup"
    if check.startswith("nested_runtime_session"):
        return "monitor-provider-market-data-imbalance-runtime-session"
    if check == "cutover_ready" and cutover is not None:
        next_gate = _first_action_value(cutover.action_queue, "next_gate")
        return next_gate or "review-cutover-gate"
    if check.startswith("cutover"):
        return "review-cutover-gate"
    if check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "review-provider-market-data-imbalance-broker-readiness"
    return "review-provider-market-data-imbalance-cutover"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-route-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-broker-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-readiness --help"
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "monitor-provider-market-data-imbalance-runtime-session":
        return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-session --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    if next_gate == "review-route-readiness":
        return "python -m hft_cli review-route-readiness --help"
    if next_gate == "review-route-enable":
        return "python -m hft_cli review-route-enable --help"
    return "python -m hft_cli review-provider-market-data-imbalance-cutover --help"


def _component_for_check(check: str) -> str:
    if _is_dispatch_roundtrip_route_sidecar_check(check):
        return "provider_route_readiness"
    if check.startswith("provider_broker_readiness_route_readiness_provider_sidecar"):
        return "provider_route_readiness"
    if (
        check.startswith("provider_broker_readiness")
        or check.startswith("nested_broker_readiness")
        or _is_dispatch_roundtrip_adapter_contract_check(check)
        or _is_dispatch_roundtrip_provider_profile_check(check)
        or _is_dispatch_roundtrip_synthetic_sidecar_check(check)
    ):
        return "provider_broker_readiness"
    if check.startswith("nested_scaleup"):
        return "scaleup"
    if check.startswith("nested_runtime_session"):
        return "runtime_session"
    if check.startswith("cutover"):
        return "cutover"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_cutover"


def _action_for_check(check: str) -> str:
    if _is_dispatch_roundtrip_route_sidecar_check(check):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("provider_broker_readiness_route_readiness_provider_sidecar"):
        return "review_provider_imbalance_route_readiness"
    if (
        check.startswith("provider_broker_readiness")
        or check.startswith("nested_broker_readiness")
        or _is_dispatch_roundtrip_adapter_contract_check(check)
        or _is_dispatch_roundtrip_provider_profile_check(check)
        or _is_dispatch_roundtrip_synthetic_sidecar_check(check)
    ):
        return "repair_provider_imbalance_broker_readiness"
    if check.startswith("nested_scaleup"):
        return "repair_provider_imbalance_scaleup"
    if check.startswith("nested_runtime_session"):
        return "repair_provider_imbalance_runtime_session"
    if check.startswith("cutover"):
        return "repair_cutover_gate_inputs"
    return "repair_provider_imbalance_cutover"


def _recommendation_for_check(check: str) -> str:
    if _is_dispatch_roundtrip_route_sidecar_check(check):
        return "review_provider_roundtrip_route_readiness_sidecar_proof_before_cutover"
    if check.startswith("provider_broker_readiness_route_readiness_provider_sidecar"):
        return "review_provider_route_readiness_sidecar_proof_before_cutover"
    if (
        check.startswith("provider_broker_readiness")
        or check.startswith("nested_broker_readiness")
        or _is_dispatch_roundtrip_adapter_contract_check(check)
        or _is_dispatch_roundtrip_provider_profile_check(check)
        or _is_dispatch_roundtrip_synthetic_sidecar_check(check)
    ):
        return "rerun_provider_broker_readiness_before_cutover"
    if check.startswith("nested_scaleup"):
        return "rerun_provider_scaleup_before_cutover"
    if check.startswith("nested_runtime_session"):
        return "rerun_provider_runtime_session_before_cutover"
    if check.startswith("cutover"):
        return "rerun_generic_cutover_gate_with_required_artifacts"
    return "repair_provider_cutover_inputs"


def _is_dispatch_roundtrip_adapter_contract_check(check: str) -> bool:
    return check.startswith("dispatch_roundtrip_adapter_execution_contract")


def _is_dispatch_roundtrip_provider_profile_check(check: str) -> bool:
    return check.startswith("dispatch_roundtrip_provider_profile") or check.startswith(
        "dispatch_roundtrip_adapter_provider_profile"
    )


def _is_dispatch_roundtrip_synthetic_sidecar_check(check: str) -> bool:
    return check.startswith("dispatch_roundtrip_synthetic_sidecar")


def _is_dispatch_roundtrip_route_sidecar_check(check: str) -> bool:
    return check.startswith("dispatch_roundtrip_route_readiness_provider_sidecar")


def _inferred_scaleup_dir(provider_summary: pd.DataFrame, provider_config: dict[str, Any]) -> Path | None:
    session_record = provider_config.get("provider_runtime_session", {}) or {}
    session_config = provider_config.get("provider_runtime_session_config", {}) or {}
    session_summary = session_config.get("summary", {}) or {}
    return _first_existing_path(
        _path_from_text(_first_text(provider_summary, "scaleup_dir")),
        _path_from_text(session_record.get("scaleup_dir")),
        _path_from_text(session_summary.get("scaleup_dir")),
    )


def _inferred_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    broker_inputs = provider_config.get("broker_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "provider_dispatch_roundtrip_dir")),
        _path_from_text(broker_inputs.get("provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "dispatch_roundtrip_dir")),
        _path_from_text(broker_inputs.get("dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _inferred_upstream_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    broker_inputs = provider_config.get("broker_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upstream_provider_dispatch_roundtrip_dir")),
        _path_from_text(broker_inputs.get("upstream_provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upstream_dispatch_roundtrip_dir")),
        _path_from_text(broker_inputs.get("upstream_dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred: Path | None,
    config: ProviderMarketDataImbalanceCutoverConfig,
) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    if not config.use_provider_broker_readiness_inputs:
        return None
    return inferred


def _first_action_value(action_queue: pd.DataFrame | None, column: str) -> str:
    if action_queue is None or action_queue.empty or column not in action_queue.columns:
        return ""
    for value in action_queue[column].tolist():
        text = _clean(value)
        if text:
            return text
    return ""


def _checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "_None_"
    rows = [
        [
            str(row.get("check", "")),
            "pass" if _truthy(row.get("passed")) else "fail",
            str(row.get("value", "")),
            str(row.get("threshold", "")),
            str(row.get("reason", "")),
        ]
        for row in checks.to_dict(orient="records")
    ]
    return _markdown_table(["Check", "Status", "Value", "Threshold", "Reason"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(row.get("priority", "")),
            str(row.get("queue_status", "")),
            str(row.get("action", "")),
            str(row.get("next_gate", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
    return _markdown_table(["#", "Status", "Action", "Next gate", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _action_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    return Path(text)


def _path_or_empty(path: str | Path | None) -> Path:
    if path is None:
        return Path()
    return Path(path)


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    return _list(provider_config.get("provider_capture_commands"))


def _bundle_provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    bundle = _mapping(provider_config.get("capture_bundle"))
    return (
        _list(provider_config.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("provider_capture_commands"))
    )


def _adapter_execution_contract(provider_config: dict[str, Any]) -> dict[str, Any]:
    bundle = _mapping(provider_config.get("capture_bundle"))
    return _mapping(provider_config.get("adapter_execution_contract")) or _mapping(
        bundle.get("adapter_execution_contract")
    )


def _source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_session_timezone"]),
        "open_local": str(summary["source_session_open_local"]),
        "close_local": str(summary["source_session_close_local"]),
    }


def _market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["market_session_timezone"]),
        "open_local": str(summary["market_session_open_local"]),
        "close_local": str(summary["market_session_close_local"]),
    }


def _capture_bundle_source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_source_session_timezone"]),
        "open_local": str(summary["capture_bundle_source_session_open_local"]),
        "close_local": str(summary["capture_bundle_source_session_close_local"]),
    }


def _capture_bundle_market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_market_session_timezone"]),
        "open_local": str(summary["capture_bundle_market_session_open_local"]),
        "close_local": str(summary["capture_bundle_market_session_close_local"]),
    }


def _source_live_fetch_contract_session_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_live_fetch_contract_session_timezone"]),
        "open_local": str(summary["source_live_fetch_contract_session_open_local"]),
        "close_local": str(summary["source_live_fetch_contract_session_close_local"]),
    }


def _adapter_contract_carried(provider_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(provider_summary, "adapter_contract_provider"))
        and bool(_first_text(provider_summary, "adapter_contract_transport"))
        and bool(_first_text(provider_summary, "adapter_contract_market"))
        and bool(_first_text(provider_summary, "adapter_contract_exchange"))
        and not _first_bool(provider_summary, "adapter_contract_values_stored")
    )


def _provider_profile_carried(provider_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(provider_summary, "provider_profile_sha256"))
        and bool(_first_text(provider_summary, "provider_profile_adapter"))
        and bool(_first_text(provider_summary, "provider_profile_transports"))
    )


def _provider_profile_metadata_text(provider_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(provider_summary, 'provider_profile_sha256')}|"
        f"{_first_text(provider_summary, 'provider_profile_adapter')}|"
        f"{_first_text(provider_summary, 'provider_profile_transports')}"
    )


def _adapter_contract_metadata_text(provider_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(provider_summary, 'adapter_contract_provider')}|"
        f"{_first_text(provider_summary, 'adapter_contract_transport')}|"
        f"{_first_text(provider_summary, 'adapter_contract_market')}|"
        f"{_first_text(provider_summary, 'adapter_contract_exchange')}"
    )


def _dispatch_roundtrip_provider_profile_text(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
    column: str,
    profile_key: str,
    fallback_key: str,
) -> str:
    if _first_value_present(provider_summary, column):
        return _first_text(provider_summary, column)
    direct = _clean(dispatch_roundtrip.get(fallback_key))
    if direct:
        return direct
    return _clean(_mapping(dispatch_roundtrip.get("provider_profile")).get(profile_key))


def _dispatch_roundtrip_provider_profile_bool(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
    column: str,
    profile_key: str,
    fallback_key: str,
) -> bool:
    if _first_value_present(provider_summary, column):
        return _first_bool(provider_summary, column)
    if fallback_key in dispatch_roundtrip:
        return _truthy(dispatch_roundtrip.get(fallback_key))
    return _truthy(_mapping(dispatch_roundtrip.get("provider_profile")).get(profile_key))


def _dispatch_roundtrip_capture_bundle_provider_profile_text(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> str:
    column = "dispatch_roundtrip_capture_bundle_provider_profile_sha256"
    if _first_value_present(provider_summary, column):
        return _first_text(provider_summary, column)
    direct = _clean(dispatch_roundtrip.get("capture_bundle_provider_profile_sha256"))
    if direct:
        return direct
    return _clean(_mapping(dispatch_roundtrip.get("capture_bundle_provider_profile")).get("sha256"))


def _dispatch_roundtrip_adapter_contract_provider_profile_text(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> str:
    column = "dispatch_roundtrip_adapter_contract_provider_profile_sha256"
    if _first_value_present(provider_summary, column):
        return _first_text(provider_summary, column)
    direct = _clean(dispatch_roundtrip.get("adapter_contract_provider_profile_sha256"))
    if direct:
        return direct
    return _clean(_mapping(dispatch_roundtrip.get("adapter_execution_contract")).get("provider_profile_sha256"))


def _dispatch_roundtrip_provider_profile_carried(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> bool:
    return (
        bool(
            _dispatch_roundtrip_provider_profile_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_sha256",
                "sha256",
                "provider_profile_sha256",
            )
        )
        and bool(
            _dispatch_roundtrip_provider_profile_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_adapter",
                "adapter",
                "provider_profile_adapter",
            )
        )
        and bool(
            _dispatch_roundtrip_provider_profile_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_provider_profile_transports",
                "transports",
                "provider_profile_transports",
            )
        )
    )


def _dispatch_roundtrip_provider_profile_metadata_text(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> str:
    return (
        f"{_dispatch_roundtrip_provider_profile_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_provider_profile_sha256', 'sha256', 'provider_profile_sha256')}|"
        f"{_dispatch_roundtrip_provider_profile_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_provider_profile_adapter', 'adapter', 'provider_profile_adapter')}|"
        f"{_dispatch_roundtrip_provider_profile_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_provider_profile_transports', 'transports', 'provider_profile_transports')}"
    )


def _dispatch_roundtrip_provider_profile_matches_session(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> bool:
    explicit_match_flag = _first_value_present(
        provider_summary,
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
    ) or "provider_profile_matches_runtime_session" in dispatch_roundtrip
    if explicit_match_flag:
        return _dispatch_roundtrip_bool(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_provider_profile_matches_runtime_session",
            "provider_profile_matches_runtime_session",
        )
    return (
        _provider_profile_carried(provider_summary)
        and _dispatch_roundtrip_provider_profile_carried(provider_summary, dispatch_roundtrip)
        and _provider_profile_metadata_text(provider_summary)
        == _dispatch_roundtrip_provider_profile_metadata_text(provider_summary, dispatch_roundtrip)
    )


def _dispatch_roundtrip_adapter_contract_carried(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> bool:
    return (
        bool(
            _dispatch_roundtrip_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_adapter_contract_provider",
                "adapter_contract_provider",
            )
        )
        and bool(
            _dispatch_roundtrip_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_adapter_contract_transport",
                "adapter_contract_transport",
            )
        )
        and bool(
            _dispatch_roundtrip_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_adapter_contract_market",
                "adapter_contract_market",
            )
        )
        and bool(
            _dispatch_roundtrip_text(
                provider_summary,
                dispatch_roundtrip,
                "dispatch_roundtrip_adapter_contract_exchange",
                "adapter_contract_exchange",
            )
        )
        and not _dispatch_roundtrip_bool(
            provider_summary,
            dispatch_roundtrip,
            "dispatch_roundtrip_adapter_contract_values_stored",
            "adapter_contract_values_stored",
        )
    )


def _dispatch_roundtrip_adapter_contract_metadata_text(
    provider_summary: pd.DataFrame,
    dispatch_roundtrip: dict[str, Any],
) -> str:
    return (
        f"{_dispatch_roundtrip_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_adapter_contract_provider', 'adapter_contract_provider')}|"
        f"{_dispatch_roundtrip_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_adapter_contract_transport', 'adapter_contract_transport')}|"
        f"{_dispatch_roundtrip_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_adapter_contract_market', 'adapter_contract_market')}|"
        f"{_dispatch_roundtrip_text(provider_summary, dispatch_roundtrip, 'dispatch_roundtrip_adapter_contract_exchange', 'adapter_contract_exchange')}"
    )


def _dispatch_roundtrip_source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["dispatch_roundtrip_source_session_timezone"]),
        "open_local": str(summary["dispatch_roundtrip_source_session_open_local"]),
        "close_local": str(summary["dispatch_roundtrip_source_session_close_local"]),
    }


def _dispatch_roundtrip_market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["dispatch_roundtrip_market_session_timezone"]),
        "open_local": str(summary["dispatch_roundtrip_market_session_open_local"]),
        "close_local": str(summary["dispatch_roundtrip_market_session_close_local"]),
    }


def _dispatch_roundtrip_capture_bundle_source_session_contract_from_summary(
    summary: pd.Series,
) -> dict[str, str]:
    return {
        "timezone": str(summary["dispatch_roundtrip_capture_bundle_source_session_timezone"]),
        "open_local": str(summary["dispatch_roundtrip_capture_bundle_source_session_open_local"]),
        "close_local": str(summary["dispatch_roundtrip_capture_bundle_source_session_close_local"]),
    }


def _dispatch_roundtrip_capture_bundle_market_session_contract_from_summary(
    summary: pd.Series,
) -> dict[str, str]:
    return {
        "timezone": str(summary["dispatch_roundtrip_capture_bundle_market_session_timezone"]),
        "open_local": str(summary["dispatch_roundtrip_capture_bundle_market_session_open_local"]),
        "close_local": str(summary["dispatch_roundtrip_capture_bundle_market_session_close_local"]),
    }


def _dispatch_roundtrip_source_live_fetch_contract_session_from_summary(
    summary: pd.Series,
) -> dict[str, str]:
    return {
        "timezone": str(summary["dispatch_roundtrip_source_live_fetch_contract_session_timezone"]),
        "open_local": str(summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"]),
        "close_local": str(summary["dispatch_roundtrip_source_live_fetch_contract_session_close_local"]),
    }


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _clean(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_value_present(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    value = frame.iloc[0][column]
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _first_number(frame: pd.DataFrame | None, column: str, fallback: float = 0.0) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return fallback
    value = frame.iloc[0][column]
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _identity_key(value: object) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _truthy(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed", "continue"}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [_jsonable(row) for row in frame.to_dict(orient="records")]


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    records = _records(frame)
    return records[0] if records else {}


def _series_record(series: pd.Series) -> dict[str, Any]:
    return _jsonable(series.to_dict())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _records(value)
    if isinstance(value, pd.Series):
        return _series_record(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return str(value)
    return value
