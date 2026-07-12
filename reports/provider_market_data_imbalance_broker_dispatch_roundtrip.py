from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.broker_dispatch_roundtrip import (
    BrokerDispatchRoundTripReport,
    BrokerDispatchRoundTripThresholds,
    write_broker_dispatch_roundtrip,
)
from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    broker_dispatch_ack_lineage_fields,
    empty_broker_dispatch_ack_lineage,
)


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_broker_dispatch_roundtrip"
READY_NEXT_GATE = "review-provider-market-data-imbalance-broker-readiness"
BROKER_DISPATCH_ACK_LINEAGE_COLUMNS = tuple(
    broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage()
    ).keys()
)

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
    "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
    "broker_dispatch_roundtrip_vendor_market_data_batch",
)

UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES = (
    (
        "dispatch_roundtrip_vendor_market_data_batch",
        "upstream_dispatch_roundtrip_vendor_market_data_batch",
    ),
    (
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
    ),
)

VENDOR_MARKET_DATA_BATCH_SUMMARY_SUFFIXES = (
    "provided",
    "ready",
    "adapter",
    "kind",
    "manifest_run_type",
    "market",
    "dataset_count",
    "ready_datasets",
    "failed_datasets",
    "ready_rate",
    "unique_source_files",
    "unique_header_fingerprints",
    "source_file_fingerprint_coverage",
    "min_mapping_coverage",
    "unique_mapping_drafts",
    "mapping_sources",
    "comparison_accepted",
    "comparison_failed_checks",
    "datasets_json",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig:
    require_provider_broker_dispatch_ack_passed: bool = True
    require_broker_dispatch_roundtrip_passed: bool = True
    use_provider_broker_dispatch_ack_inputs: bool = True
    target_mode: str = ""
    require_dispatch_ready: bool = True
    require_send_ready: bool = True
    require_ack_passed: bool = True
    require_identity_match: bool = True
    require_submission_disabled: bool = True
    require_all_requests_acked: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    require_ack_lineage: bool = False
    allow_rejections: bool = False
    max_duplicate_ack_orders: int = 0
    max_unmatched_acks: int = 0
    max_missing_request_acks: int = 0
    max_total_failed_component_checks: int = 0


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchRoundTripReport:
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])

    @property
    def ready(self) -> bool:
        return self.passed


def write_provider_market_data_imbalance_broker_dispatch_roundtrip(
    provider_broker_dispatch_ack_dir: str | Path,
    output_dir: str | Path,
    *,
    broker_dispatch_dir: str | Path | None = None,
    broker_dispatch_send_dir: str | Path | None = None,
    broker_dispatch_ack_dir: str | Path | None = None,
    config: ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerDispatchRoundTripReport:
    config = config or ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    provider_root = Path(provider_broker_dispatch_ack_dir)
    provider_summary, provider_summary_error = _read_csv(
        provider_root / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_root / "provider_market_data_imbalance_broker_dispatch_ack_config.json"
    )
    provider_manifest, provider_manifest_error = _read_json(
        provider_root / "manifest.json"
    )

    inferred = _inferred_generic_inputs(provider_root, provider_summary, provider_config)
    upstream_provider_dispatch_roundtrip_dir, upstream_dispatch_roundtrip_dir = (
        _inferred_upstream_dispatch_roundtrip_dirs(provider_summary, provider_config)
    )
    resolved_broker_dispatch_dir = _explicit_or_inferred(
        broker_dispatch_dir,
        inferred["broker_dispatch_dir"],
        config.use_provider_broker_dispatch_ack_inputs,
    )
    resolved_broker_dispatch_send_dir = _explicit_or_inferred(
        broker_dispatch_send_dir,
        inferred["broker_dispatch_send_dir"],
        config.use_provider_broker_dispatch_ack_inputs,
    )
    resolved_broker_dispatch_ack_dir = _explicit_or_inferred(
        broker_dispatch_ack_dir,
        inferred["broker_dispatch_ack_dir"],
        config.use_provider_broker_dispatch_ack_inputs,
    )

    prechecks = _prechecks(
        provider_root,
        provider_summary,
        provider_summary_error,
        provider_config,
        provider_config_error,
        provider_manifest,
        provider_manifest_error,
        resolved_broker_dispatch_dir,
        resolved_broker_dispatch_send_dir,
        resolved_broker_dispatch_ack_dir,
        config,
    )

    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None = None
    broker_dispatch_roundtrip_error = ""
    broker_dispatch_roundtrip_dir = out / "broker_dispatch_roundtrip"
    if bool(prechecks["passed"].all()):
        try:
            broker_dispatch_roundtrip = write_broker_dispatch_roundtrip(
                dispatch_dir=_path_or_empty(resolved_broker_dispatch_dir),
                send_dir=_path_or_empty(resolved_broker_dispatch_send_dir),
                ack_dir=_path_or_empty(resolved_broker_dispatch_ack_dir),
                output_dir=broker_dispatch_roundtrip_dir,
                thresholds=_thresholds(config, provider_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError, json.JSONDecodeError) as exc:
            broker_dispatch_roundtrip_error = str(exc)
    else:
        broker_dispatch_roundtrip_error = "provider imbalance broker-dispatch-roundtrip prerequisites are not ready"

    checks = _checks(
        prechecks,
        broker_dispatch_roundtrip,
        broker_dispatch_roundtrip_error,
        provider_summary,
        provider_config,
        config,
    )
    summary = _summary(
        provider_root,
        resolved_broker_dispatch_dir,
        resolved_broker_dispatch_send_dir,
        resolved_broker_dispatch_ack_dir,
        broker_dispatch_roundtrip,
        checks,
        out,
        broker_dispatch_roundtrip_dir,
        provider_summary,
        provider_config,
        provider_manifest,
        upstream_provider_dispatch_roundtrip_dir,
        upstream_dispatch_roundtrip_dir,
    )
    action_queue = _action_queue(summary.iloc[0], checks, broker_dispatch_roundtrip)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        provider_manifest,
        broker_dispatch_roundtrip,
        checks,
        action_queue,
        config,
        {
            "provider_broker_dispatch_ack_dir": provider_root,
            "broker_dispatch_dir": resolved_broker_dispatch_dir,
            "broker_dispatch_send_dir": resolved_broker_dispatch_send_dir,
            "broker_dispatch_ack_dir": resolved_broker_dispatch_ack_dir,
            "upstream_provider_dispatch_roundtrip_dir": upstream_provider_dispatch_roundtrip_dir,
            "upstream_dispatch_roundtrip_dir": upstream_dispatch_roundtrip_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_broker_dispatch_roundtrip_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv", index=False)
    action_queue.to_csv(
        out / "provider_market_data_imbalance_broker_dispatch_roundtrip_action_queue.csv",
        index=False,
    )
    (out / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_broker_dispatch_ack_dir": provider_root}
    if resolved_broker_dispatch_dir is not None:
        inputs["broker_dispatch"] = Path(resolved_broker_dispatch_dir)
    if resolved_broker_dispatch_send_dir is not None:
        inputs["broker_dispatch_send"] = Path(resolved_broker_dispatch_send_dir)
    if resolved_broker_dispatch_ack_dir is not None:
        inputs["broker_dispatch_ack"] = Path(resolved_broker_dispatch_ack_dir)
    if upstream_provider_dispatch_roundtrip_dir is not None:
        inputs["upstream_provider_dispatch_roundtrip"] = Path(upstream_provider_dispatch_roundtrip_dir)
    if upstream_dispatch_roundtrip_dir is not None:
        inputs["upstream_dispatch_roundtrip"] = Path(upstream_dispatch_roundtrip_dir)
    if broker_dispatch_roundtrip is not None and broker_dispatch_roundtrip.output_dir is not None:
        inputs["broker_dispatch_roundtrip"] = broker_dispatch_roundtrip.output_dir
    summary_row = summary.iloc[0]
    for name, value in {
        "capture_bundle": _path_from_text(summary_row["capture_bundle_path"]),
        "capture_env_template": _path_from_text(summary_row["capture_env_template_path"]),
        "adapter_handoff": _path_from_text(summary_row["adapter_handoff_path"]),
        "source_credential_env_template": _path_from_text(summary_row["source_credential_env_template_path"]),
        "dispatch_roundtrip_capture_bundle": _path_from_text(
            summary_row["dispatch_roundtrip_capture_bundle_path"]
        ),
        "dispatch_roundtrip_capture_env_template": _path_from_text(
            summary_row["dispatch_roundtrip_capture_env_template_path"]
        ),
        "dispatch_roundtrip_adapter_handoff": _path_from_text(
            summary_row["dispatch_roundtrip_adapter_handoff_path"]
        ),
        "dispatch_roundtrip_source_credential_env_template": _path_from_text(
            summary_row["dispatch_roundtrip_source_credential_env_template_path"]
        ),
    }.items():
        if value is not None:
            inputs[name] = value
    receipt_paths, capture_paths = _adapter_receipt_proof_paths(
        _mapping(provider_config.get("adapter_receipt_proof"))
    )
    if receipt_paths:
        inputs["adapter_receipts"] = receipt_paths
    if capture_paths:
        inputs["provider_captures"] = capture_paths
    dispatch_roundtrip_receipt_paths, dispatch_roundtrip_capture_paths = (
        _adapter_receipt_proof_paths(
            _mapping(
                _dispatch_roundtrip_provenance(provider_config).get(
                    "adapter_receipt_proof"
                )
            )
        )
    )
    if dispatch_roundtrip_receipt_paths:
        inputs["dispatch_roundtrip_adapter_receipts"] = (
            dispatch_roundtrip_receipt_paths
        )
    if dispatch_roundtrip_capture_paths:
        inputs["dispatch_roundtrip_provider_captures"] = (
            dispatch_roundtrip_capture_paths
        )

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "broker_dispatch_roundtrip_inputs": _jsonable(payload["broker_dispatch_roundtrip_inputs"]),
        },
        inputs=inputs,
        extra={
            "authorizes_submission": False,
            "passed": bool(summary_row["passed"]),
            "broker_dispatch_roundtrip_passed": bool(summary_row["broker_dispatch_roundtrip_passed"]),
            "broker_dispatch_ack_lineage": _broker_dispatch_ack_lineage_config(
                summary_row
            ),
            "profile": PROFILE,
            "strategy": str(summary_row["strategy"]),
            "market": str(summary_row["market"]),
            "exchange": str(summary_row["exchange"]),
            "source_session": _source_session_contract_from_summary(summary_row),
            "market_session": _market_session_contract_from_summary(summary_row),
            "provider_profile": _mapping(payload.get("provider_profile")),
            "adapter_receipt_proof": _mapping(payload.get("adapter_receipt_proof")),
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
                "adapter_receipt_proof": _mapping(
                    payload.get("adapter_receipt_proof")
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
            "provider_broker_dispatch_roundtrip_wrapper_provided": bool(
                summary_row["provider_broker_dispatch_roundtrip_wrapper_provided"]
            ),
            "provider_broker_dispatch_roundtrip_manifest_run_type": str(
                summary_row["provider_broker_dispatch_roundtrip_manifest_run_type"]
            ),
            "dispatch_roundtrip_adapter_receipt_proof": _mapping(
                _mapping(payload.get("dispatch_roundtrip_provenance")).get(
                    "adapter_receipt_proof"
                )
            ),
            "dispatch_roundtrip_adapter_receipt_proof_ready": bool(
                summary_row["dispatch_roundtrip_adapter_receipt_proof_ready"]
            ),
            "dispatch_roundtrip_adapter_receipt_proof_matches_manifest": bool(
                summary_row[
                    "dispatch_roundtrip_adapter_receipt_proof_matches_manifest"
                ]
            ),
            "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session": bool(
                summary_row[
                    "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session"
                ]
            ),
            "dispatch_roundtrip_adapter_receipt_required_count": int(
                summary_row["dispatch_roundtrip_adapter_receipt_required_count"]
            ),
            "dispatch_roundtrip_adapter_receipt_valid_count": int(
                summary_row["dispatch_roundtrip_adapter_receipt_valid_count"]
            ),
            "dispatch_roundtrip_adapter_receipt_fingerprint_match_count": int(
                summary_row[
                    "dispatch_roundtrip_adapter_receipt_fingerprint_match_count"
                ]
            ),
            "dispatch_roundtrip_capture_fingerprint_match_count": int(
                summary_row["dispatch_roundtrip_capture_fingerprint_match_count"]
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
                "adapter_receipt_proof": _mapping(
                    _mapping(payload.get("dispatch_roundtrip_provenance")).get(
                        "adapter_receipt_proof"
                    )
                ),
                "adapter_receipt_proof_ready": bool(
                    summary_row["dispatch_roundtrip_adapter_receipt_proof_ready"]
                ),
                "adapter_receipt_proof_matches_manifest": bool(
                    summary_row[
                        "dispatch_roundtrip_adapter_receipt_proof_matches_manifest"
                    ]
                ),
                "adapter_receipt_proof_matches_runtime_session": bool(
                    summary_row[
                        "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session"
                    ]
                ),
                "exchange": str(summary_row["dispatch_roundtrip_exchange"]),
                "source_session": _dispatch_roundtrip_source_session_contract_from_summary(summary_row),
                "market_session": _dispatch_roundtrip_market_session_contract_from_summary(summary_row),
                "metadata_consistent": bool(summary_row["dispatch_roundtrip_metadata_consistent"]),
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
                "live_fetch_contract": {
                    "exchange": str(summary_row["dispatch_roundtrip_source_live_fetch_contract_exchange"]),
                    "market": str(summary_row["dispatch_roundtrip_source_live_fetch_contract_market"]),
                    "session": _dispatch_roundtrip_source_live_fetch_contract_session_from_summary(summary_row),
                },
            },
            "upstream_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
        },
    )
    return ProviderMarketDataImbalanceBrokerDispatchRoundTripReport(
        broker_dispatch_roundtrip,
        checks,
        summary,
        action_queue,
        payload,
        out,
    )


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
    provider_config: dict[str, Any],
    provider_config_error: str,
    provider_manifest: dict[str, Any],
    provider_manifest_error: str,
    broker_dispatch_dir: Path | None,
    broker_dispatch_send_dir: Path | None,
    broker_dispatch_ack_dir: Path | None,
    config: ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig,
) -> pd.DataFrame:
    bundle_provided = _first_bool(provider_summary, "capture_bundle_provided")
    config_receipt_proof = _mapping(provider_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(provider_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_proofs_match = bool(
        config_receipt_proof
        and manifest_receipt_proof
        and config_receipt_proof == manifest_receipt_proof
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    dispatch_roundtrip_config_receipt_proof = _mapping(
        dispatch_roundtrip.get("adapter_receipt_proof")
    )
    manifest_extra = _mapping(provider_manifest.get("extra"))
    dispatch_roundtrip_manifest_receipt_proof = _mapping(
        manifest_extra.get("dispatch_roundtrip_adapter_receipt_proof")
    )
    dispatch_roundtrip_wrapper_provided = bool(
        _truthy(dispatch_roundtrip.get("provider_wrapper_provided"))
        or _first_bool(
            provider_summary,
            "provider_broker_dispatch_roundtrip_wrapper_provided",
        )
        or _truthy(
            manifest_extra.get(
                "provider_broker_dispatch_roundtrip_wrapper_provided"
            )
        )
    )
    dispatch_roundtrip_receipts_required = bool(
        _truthy(dispatch_roundtrip_config_receipt_proof.get("required"))
        or _truthy(dispatch_roundtrip_manifest_receipt_proof.get("required"))
        or _first_bool(
            provider_summary,
            "dispatch_roundtrip_adapter_receipts_required",
        )
        or _number(
            manifest_extra.get(
                "dispatch_roundtrip_adapter_receipt_required_count"
            )
        )
        > 0
    )
    dispatch_roundtrip_receipt_gate_active = bool(
        dispatch_roundtrip_wrapper_provided
        and (
            dispatch_roundtrip_receipts_required
            or dispatch_roundtrip_config_receipt_proof
            or dispatch_roundtrip_manifest_receipt_proof
        )
    )
    dispatch_roundtrip_receipt_proofs_match = bool(
        dispatch_roundtrip_config_receipt_proof
        and dispatch_roundtrip_manifest_receipt_proof
        and dispatch_roundtrip_config_receipt_proof
        == dispatch_roundtrip_manifest_receipt_proof
    )
    dispatch_roundtrip_receipt_proof_matches_runtime = bool(
        dispatch_roundtrip_config_receipt_proof
        and config_receipt_proof
        and dispatch_roundtrip_config_receipt_proof == config_receipt_proof
    )
    dispatch_roundtrip_receipt_status = _adapter_receipt_proof_status(
        dispatch_roundtrip_config_receipt_proof
    )
    return pd.DataFrame(
        [
            _check(
                "provider_broker_dispatch_ack_dir_exists",
                str(provider_root),
                "exists",
                True,
                provider_root.exists(),
                "provider imbalance broker-dispatch-ack directory is required",
            ),
            _check(
                "provider_broker_dispatch_ack_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider broker-dispatch-ack summary could not be read",
            ),
            _check(
                "provider_broker_dispatch_ack_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider broker-dispatch-ack config could not be read",
            ),
            _check(
                "provider_broker_dispatch_ack_manifest_readable",
                provider_manifest_error or "ok",
                "is",
                "ok",
                not provider_manifest_error,
                provider_manifest_error or "provider broker-dispatch-ack manifest could not be read",
            ),
            _check(
                "provider_broker_dispatch_ack_manifest_type",
                _clean(provider_manifest.get("run_type")),
                "is",
                "provider_market_data_imbalance_broker_dispatch_ack",
                _clean(provider_manifest.get("run_type"))
                == "provider_market_data_imbalance_broker_dispatch_ack",
                "provider broker-dispatch-ack manifest run_type is not expected",
            ),
            _check(
                "provider_broker_dispatch_ack_passed",
                _first_bool(provider_summary, "passed"),
                "is",
                True,
                _first_bool(provider_summary, "passed")
                or not config.require_provider_broker_dispatch_ack_passed,
                "provider broker-dispatch acknowledgement wrapper has not passed",
            ),
            _check(
                "provider_broker_dispatch_ack_adapter_receipt_proof_carried",
                bool(config_receipt_proof),
                "is",
                True,
                bool(config_receipt_proof)
                and _truthy(config_receipt_proof.get("ready"))
                if bundle_provided
                else True,
                "provider broker-dispatch acknowledgement is missing ready adapter receipt proof",
            ),
            _check(
                "provider_broker_dispatch_ack_adapter_receipt_proof_matches_manifest",
                receipt_proofs_match,
                "is",
                True,
                receipt_proofs_match if bundle_provided else True,
                "adapter receipt proof differs between broker-dispatch-ack config and manifest",
            ),
            _check(
                "provider_broker_dispatch_ack_adapter_receipts_valid",
                receipt_status["valid_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["valid_count"] == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider broker-dispatch acknowledgement did not preserve valid required adapter receipts",
            ),
            _check(
                "provider_broker_dispatch_ack_adapter_receipt_fingerprints_current",
                receipt_status["receipt_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["receipt_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "adapter receipt files changed after provider broker-dispatch acknowledgement",
            ),
            _check(
                "provider_broker_dispatch_ack_capture_fingerprints_current",
                receipt_status["capture_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["capture_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider capture files changed after provider broker-dispatch acknowledgement",
            ),
            _check(
                "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_receipt_proof_carried",
                bool(dispatch_roundtrip_config_receipt_proof),
                "is",
                True,
                bool(dispatch_roundtrip_config_receipt_proof)
                and _truthy(dispatch_roundtrip_config_receipt_proof.get("ready"))
                if dispatch_roundtrip_receipt_gate_active
                else True,
                "provider broker-dispatch acknowledgement is missing final round-trip adapter receipt proof",
            ),
            _check(
                "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_receipt_proof_matches_manifest",
                dispatch_roundtrip_receipt_proofs_match,
                "is",
                True,
                dispatch_roundtrip_receipt_proofs_match
                if dispatch_roundtrip_receipt_gate_active
                else True,
                "final round-trip adapter receipt proof differs between ack config and manifest",
            ),
            _check(
                "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_receipt_proof_matches_runtime",
                dispatch_roundtrip_receipt_proof_matches_runtime,
                "is",
                True,
                dispatch_roundtrip_receipt_proof_matches_runtime
                if dispatch_roundtrip_receipt_gate_active
                else True,
                "final round-trip adapter receipt proof differs from ack runtime proof",
            ),
            _check(
                "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_receipts_valid",
                dispatch_roundtrip_receipt_status["valid_count"],
                "==",
                dispatch_roundtrip_receipt_status["required_count"],
                dispatch_roundtrip_receipt_status["valid_count"]
                == dispatch_roundtrip_receipt_status["required_count"]
                if dispatch_roundtrip_receipt_gate_active
                else True,
                "provider broker-dispatch acknowledgement did not preserve valid final round-trip adapter receipts",
            ),
            _check(
                "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_receipt_fingerprints_current",
                dispatch_roundtrip_receipt_status[
                    "receipt_fingerprint_match_count"
                ],
                "==",
                dispatch_roundtrip_receipt_status["required_count"],
                dispatch_roundtrip_receipt_status[
                    "receipt_fingerprint_match_count"
                ]
                == dispatch_roundtrip_receipt_status["required_count"]
                if dispatch_roundtrip_receipt_gate_active
                else True,
                "final round-trip adapter receipt files changed after provider broker-dispatch acknowledgement",
            ),
            _check(
                "provider_broker_dispatch_ack_dispatch_roundtrip_capture_fingerprints_current",
                dispatch_roundtrip_receipt_status[
                    "capture_fingerprint_match_count"
                ],
                "==",
                dispatch_roundtrip_receipt_status["required_count"],
                dispatch_roundtrip_receipt_status[
                    "capture_fingerprint_match_count"
                ]
                == dispatch_roundtrip_receipt_status["required_count"]
                if dispatch_roundtrip_receipt_gate_active
                else True,
                "final round-trip provider capture files changed after provider broker-dispatch acknowledgement",
            ),
            _check(
                "provider_nested_broker_dispatch_ack_passed",
                _first_bool(provider_summary, "broker_dispatch_ack_passed"),
                "is",
                True,
                _first_bool(provider_summary, "broker_dispatch_ack_passed")
                or not config.require_provider_broker_dispatch_ack_passed,
                "nested broker dispatch acknowledgement proof has not passed",
            ),
            _check(
                "generic_broker_dispatch_input_resolved",
                _path_text(broker_dispatch_dir),
                "present",
                True,
                bool(broker_dispatch_dir),
                "nested generic broker dispatch input is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_summary_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_summary.csv").exists()),
                "nested broker_dispatch_summary.csv is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_orders_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_orders.csv").exists()),
                "nested broker_dispatch_orders.csv is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_config_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_config.json").exists()),
                "nested broker_dispatch_config.json is required for round-trip proof",
            ),
            _check(
                "generic_broker_dispatch_send_input_resolved",
                _path_text(broker_dispatch_send_dir),
                "present",
                True,
                bool(broker_dispatch_send_dir),
                "nested generic broker dispatch send input is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_send_summary_exists",
                _path_text(broker_dispatch_send_dir),
                "exists",
                True,
                bool(
                    broker_dispatch_send_dir
                    and (broker_dispatch_send_dir / "broker_dispatch_send_summary.csv").exists()
                ),
                "nested broker_dispatch_send_summary.csv is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_send_requests_exists",
                _path_text(broker_dispatch_send_dir),
                "exists",
                True,
                bool(
                    broker_dispatch_send_dir
                    and (broker_dispatch_send_dir / "broker_dispatch_send_requests.csv").exists()
                ),
                "nested broker_dispatch_send_requests.csv is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_send_config_exists",
                _path_text(broker_dispatch_send_dir),
                "exists",
                True,
                bool(
                    broker_dispatch_send_dir
                    and (broker_dispatch_send_dir / "broker_dispatch_send_config.json").exists()
                ),
                "nested broker_dispatch_send_config.json is required for round-trip proof",
            ),
            _check(
                "generic_broker_dispatch_ack_input_resolved",
                _path_text(broker_dispatch_ack_dir),
                "present",
                True,
                bool(broker_dispatch_ack_dir),
                "nested generic broker dispatch ack input is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_ack_summary_exists",
                _path_text(broker_dispatch_ack_dir),
                "exists",
                True,
                bool(broker_dispatch_ack_dir and (broker_dispatch_ack_dir / "broker_dispatch_ack_summary.csv").exists()),
                "nested broker_dispatch_ack_summary.csv is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_acknowledgements_exists",
                _path_text(broker_dispatch_ack_dir),
                "exists",
                True,
                bool(
                    broker_dispatch_ack_dir
                    and (broker_dispatch_ack_dir / "broker_dispatch_acknowledgements.csv").exists()
                ),
                "nested broker_dispatch_acknowledgements.csv is required for round-trip proof",
            ),
            _check(
                "nested_broker_dispatch_ack_config_exists",
                _path_text(broker_dispatch_ack_dir),
                "exists",
                True,
                bool(broker_dispatch_ack_dir and (broker_dispatch_ack_dir / "broker_dispatch_ack_config.json").exists()),
                "nested broker_dispatch_ack_config.json is required for round-trip proof",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
    broker_dispatch_roundtrip_error: str,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    config: ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    roundtrip_summary = broker_dispatch_roundtrip.summary if broker_dispatch_roundtrip is not None else pd.DataFrame()
    rows.append(
        _check(
            "broker_dispatch_roundtrip_runnable",
            broker_dispatch_roundtrip_error or ("ran" if broker_dispatch_roundtrip is not None else "not_run"),
            "is",
            "ran",
            broker_dispatch_roundtrip is not None and not broker_dispatch_roundtrip_error,
            broker_dispatch_roundtrip_error or "generic broker dispatch round-trip proof was not run",
        )
    )
    rows.append(
        _check(
            "broker_dispatch_roundtrip_passed",
            bool(broker_dispatch_roundtrip is not None and broker_dispatch_roundtrip.passed),
            "is",
            True,
            bool(
                broker_dispatch_roundtrip is not None
                and (broker_dispatch_roundtrip.passed or not config.require_broker_dispatch_roundtrip_passed)
            ),
            _broker_dispatch_roundtrip_failure_reason(broker_dispatch_roundtrip)
            or "broker dispatch round-trip proof did not pass",
        )
    )
    strategy = _first_text(roundtrip_summary, "strategy") or _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            bool(broker_dispatch_roundtrip is not None) and _identity_key(strategy) == PROFILE,
            "broker dispatch round-trip proof did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    roundtrip_market = _first_text(roundtrip_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            roundtrip_market or expected_market,
            "is",
            expected_market or "present",
            bool(broker_dispatch_roundtrip is not None)
            and (not expected_market or _identity_key(roundtrip_market) == _identity_key(expected_market)),
            "broker dispatch round-trip market identity does not match provider ack",
        )
    )
    expected_adapter = _first_text(provider_summary, "adapter")
    roundtrip_adapter = _first_text(roundtrip_summary, "adapter")
    rows.append(
        _check(
            "adapter_identity_consistent",
            roundtrip_adapter or expected_adapter,
            "is",
            expected_adapter or "present",
            bool(broker_dispatch_roundtrip is not None)
            and (not expected_adapter or _identity_key(roundtrip_adapter) == _identity_key(expected_adapter)),
            "broker dispatch round-trip adapter identity does not match provider ack",
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
            "provider_broker_dispatch_ack_provider_capture_commands_carried",
            bundle_provider_capture_command_count,
            "==",
            provider_capture_command_count,
            bundle_provider_capture_commands_carried if bundle_provided else True,
            "provider imbalance broker-dispatch-ack is missing capture-bundle provider command proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_provider_capture_commands_match_session",
            bundle_provider_capture_command_count,
            "matches",
            provider_capture_command_count,
            bundle_provider_capture_commands_match_session if bundle_provided else True,
            "provider imbalance broker-dispatch-ack command proof no longer matches the session packet",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_adapter_execution_contract_carried",
            _adapter_contract_metadata_text(provider_summary),
            "is_not",
            "",
            adapter_contract_carried if bundle_provided else True,
            "provider imbalance broker-dispatch-ack is missing credential-safe adapter execution contract metadata",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_adapter_execution_contract_matches_evidence",
            _adapter_contract_metadata_text(provider_summary),
            "matches",
            "live evidence",
            _first_bool(provider_summary, "adapter_contract_metadata_matches_evidence")
            if bundle_provided
            else True,
            "provider imbalance broker-dispatch-ack adapter execution contract no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_provider_profile_carried",
            _first_text(provider_summary, "provider_profile_sha256"),
            "has",
            "provider profile",
            provider_profile_carried,
            "provider imbalance broker-dispatch-ack is missing provider-profile proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_provider_profile_matches_session",
            _first_text(provider_summary, "provider_profile_sha256"),
            "matches",
            "live session",
            _first_bool(provider_summary, "provider_profile_matches_session"),
            "provider imbalance broker-dispatch-ack provider-profile proof no longer matches the live session packet",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_provider_profile_matches_bundle",
            _first_text(provider_summary, "capture_bundle_provider_profile_sha256"),
            "matches",
            _first_text(provider_summary, "provider_profile_sha256"),
            _first_bool(provider_summary, "provider_profile_matches_bundle") if bundle_provided else True,
            "provider imbalance broker-dispatch-ack provider-profile proof no longer matches the capture bundle",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_adapter_provider_profile_matches_evidence",
            _first_text(provider_summary, "adapter_contract_provider_profile_sha256"),
            "==",
            _first_text(provider_summary, "provider_profile_sha256"),
            _first_bool(provider_summary, "adapter_contract_provider_profile_matches_evidence")
            if bundle_provided
            else True,
            "provider imbalance broker-dispatch-ack adapter contract provider-profile SHA no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_synthetic_sidecar_proof_carried",
            synthetic_sidecar_count,
            "==",
            synthetic_dataset_count,
            synthetic_sidecar_count_matches if synthetic_sidecar_proof_required else True,
            "provider imbalance broker-dispatch-ack is missing synthetic rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_synthetic_sidecar_proof_ready",
            synthetic_sidecar_proof_ready,
            "is",
            True,
            synthetic_sidecar_proof_ready if synthetic_sidecar_proof_required else True,
            "provider imbalance broker-dispatch-ack synthetic rehearsal sidecar proof is not ready",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_route_readiness_provider_sidecar_breach_pairs",
            route_sidecar_breach_pairs,
            "<=",
            0,
            route_sidecar_breach_pairs <= 0 if route_sidecar_gate_active else True,
            (
                "provider imbalance broker-dispatch-ack carries breached route-readiness "
                "broker round-trip synthetic sidecar proof"
            ),
        )
    )
    dispatch_summary = _with_dispatch_roundtrip_config_fallback(provider_summary, provider_config)
    dispatch_bundle_provided = _first_bool_with_fallback(
        dispatch_summary,
        "dispatch_roundtrip_capture_bundle_provided",
        "capture_bundle_provided",
    )
    dispatch_provider_capture_command_count = int(
        _first_number_with_fallback(
            dispatch_summary,
            "dispatch_roundtrip_provider_capture_command_count",
            "provider_capture_command_count",
        )
    )
    dispatch_bundle_provider_capture_command_count = int(
        _first_number_with_fallback(
            dispatch_summary,
            "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
            "capture_bundle_provider_capture_command_count",
        )
    )
    dispatch_bundle_provider_capture_command_missing_count = int(
        _first_number_with_fallback(
            dispatch_summary,
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
        and _first_bool_with_fallback(
            dispatch_summary,
            "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
            "capture_bundle_provider_capture_commands_match_session",
        )
    )
    dispatch_provider_capture_commands_match_runtime_session = _first_bool(
        dispatch_summary,
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
    ) if _first_value_present(
        dispatch_summary,
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
    ) else dispatch_bundle_provider_capture_commands_match_session
    dispatch_adapter_contract_carried = _dispatch_roundtrip_adapter_contract_carried(dispatch_summary)
    dispatch_adapter_contract_metadata = _dispatch_roundtrip_adapter_contract_metadata_text(dispatch_summary)
    dispatch_adapter_contract_matches_runtime_session = _first_bool(
        dispatch_summary,
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
    )
    dispatch_provider_profile_carried = _dispatch_roundtrip_provider_profile_carried(dispatch_summary)
    dispatch_provider_profile_metadata = _dispatch_roundtrip_provider_profile_metadata_text(dispatch_summary)
    dispatch_provider_profile_matches_runtime_session = _dispatch_roundtrip_provider_profile_matches_session(
        provider_summary,
        dispatch_summary,
    )
    dispatch_synthetic_dataset_count = int(
        _first_number(dispatch_summary, "dispatch_roundtrip_synthetic_dataset_count")
    )
    dispatch_synthetic_sidecar_count = int(
        _first_number(dispatch_summary, "dispatch_roundtrip_synthetic_sidecar_count")
    )
    dispatch_synthetic_sidecar_proof_required = dispatch_synthetic_dataset_count > 0
    dispatch_synthetic_sidecar_proof_ready = _first_bool(
        dispatch_summary,
        "dispatch_roundtrip_synthetic_sidecar_proof_ready",
    )
    dispatch_synthetic_sidecar_count_matches = (
        dispatch_synthetic_sidecar_count == dispatch_synthetic_dataset_count
    )
    dispatch_route_sidecar_breach_pairs = int(
        _first_number(
            dispatch_summary,
            "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
        )
    )
    dispatch_route_sidecar_gate_active = (
        _first_bool(dispatch_summary, "dispatch_roundtrip_route_readiness_provided")
        or _first_bool(dispatch_summary, "dispatch_roundtrip_route_readiness_ops_launch_controls_present")
        or dispatch_route_sidecar_breach_pairs > 0
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_capture_commands_carried",
            dispatch_bundle_provider_capture_command_count,
            "==",
            dispatch_provider_capture_command_count,
            dispatch_bundle_provider_capture_commands_carried if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip is missing ack-retained round-trip provider command proof",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_capture_commands_match_session",
            dispatch_bundle_provider_capture_command_count,
            "matches",
            dispatch_provider_capture_command_count,
            dispatch_bundle_provider_capture_commands_match_session if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip command proof no longer matches the session packet",
        )
    )
    rows.append(
        _check(
            "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
            dispatch_provider_capture_commands_match_runtime_session,
            "is",
            True,
            dispatch_provider_capture_commands_match_runtime_session if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip command proof no longer matches runtime-session proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_carried",
            dispatch_adapter_contract_metadata,
            "is_not",
            "",
            dispatch_adapter_contract_carried if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip is missing ack-retained round-trip adapter execution contract proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            dispatch_adapter_contract_metadata,
            "matches",
            "live evidence",
            _first_bool(
                dispatch_summary,
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
            )
            if dispatch_bundle_provided
            else True,
            "provider imbalance broker-dispatch-roundtrip round-trip adapter execution contract no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            dispatch_adapter_contract_metadata,
            "matches",
            _adapter_contract_metadata_text(provider_summary),
            dispatch_adapter_contract_matches_runtime_session if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip round-trip adapter execution contract no longer matches runtime-session proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_carried",
            dispatch_provider_profile_metadata,
            "is_not",
            "",
            dispatch_provider_profile_carried if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip is missing ack-retained round-trip provider-profile proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_session",
            _first_text(dispatch_summary, "dispatch_roundtrip_provider_profile_sha256"),
            "matches",
            "live session",
            _first_bool(dispatch_summary, "dispatch_roundtrip_provider_profile_matches_session")
            if dispatch_bundle_provided
            else True,
            "provider imbalance broker-dispatch-roundtrip round-trip provider-profile proof no longer matches live session",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_bundle",
            _first_text(dispatch_summary, "dispatch_roundtrip_capture_bundle_provider_profile_sha256"),
            "matches",
            _first_text(dispatch_summary, "dispatch_roundtrip_provider_profile_sha256"),
            _first_bool(dispatch_summary, "dispatch_roundtrip_provider_profile_matches_bundle")
            if dispatch_bundle_provided
            else True,
            "provider imbalance broker-dispatch-roundtrip round-trip provider-profile proof no longer matches capture bundle",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            _first_text(dispatch_summary, "dispatch_roundtrip_adapter_contract_provider_profile_sha256"),
            "==",
            _first_text(dispatch_summary, "dispatch_roundtrip_provider_profile_sha256"),
            _first_bool(dispatch_summary, "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence")
            if dispatch_bundle_provided
            else True,
            "provider imbalance broker-dispatch-roundtrip round-trip adapter contract provider-profile SHA no longer matches evidence",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_runtime_session",
            dispatch_provider_profile_metadata,
            "matches",
            _provider_profile_metadata_text(provider_summary),
            dispatch_provider_profile_matches_runtime_session if dispatch_bundle_provided else True,
            "provider imbalance broker-dispatch-roundtrip round-trip provider profile no longer matches runtime-session proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_synthetic_sidecar_proof_carried",
            dispatch_synthetic_sidecar_count,
            "==",
            dispatch_synthetic_dataset_count,
            (
                dispatch_synthetic_sidecar_count_matches
                if dispatch_synthetic_sidecar_proof_required
                else True
            ),
            "provider imbalance broker-dispatch-roundtrip is missing ack-retained round-trip synthetic rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_synthetic_sidecar_proof_ready",
            dispatch_synthetic_sidecar_proof_ready,
            "is",
            True,
            (
                dispatch_synthetic_sidecar_proof_ready
                if dispatch_synthetic_sidecar_proof_required
                else True
            ),
            "provider imbalance broker-dispatch-roundtrip ack-retained round-trip synthetic rehearsal sidecar proof is not ready",
        )
    )
    rows.append(
        _check(
            "provider_broker_dispatch_ack_dispatch_roundtrip_route_readiness_provider_sidecar_breach_pairs",
            dispatch_route_sidecar_breach_pairs,
            "<=",
            0,
            dispatch_route_sidecar_breach_pairs <= 0 if dispatch_route_sidecar_gate_active else True,
            (
                "provider imbalance broker-dispatch-roundtrip carries breached "
                "ack-retained round-trip route-readiness sidecar proof"
            ),
        )
    )
    return pd.DataFrame(rows)


def _broker_dispatch_ack_lineage_summary_fields(
    roundtrip_summary: pd.DataFrame,
) -> dict[str, Any]:
    defaults = broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage()
    )
    if roundtrip_summary.empty:
        return defaults
    row = roundtrip_summary.iloc[0]
    fields: dict[str, Any] = {}
    for column, default in defaults.items():
        value = row.get(column, default)
        if isinstance(default, bool):
            fields[column] = _truthy(value)
        elif isinstance(default, int):
            try:
                fields[column] = int(float(value))
            except (TypeError, ValueError):
                fields[column] = default
        else:
            fields[column] = _clean(value)
    return fields


def _broker_dispatch_ack_lineage_config(summary: pd.Series) -> dict[str, Any]:
    return {
        column: _jsonable(summary.get(column))
        for column in BROKER_DISPATCH_ACK_LINEAGE_COLUMNS
    }


def _summary(
    provider_root: Path,
    broker_dispatch_dir: Path | None,
    broker_dispatch_send_dir: Path | None,
    broker_dispatch_ack_dir: Path | None,
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    broker_dispatch_roundtrip_dir: Path,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    provider_manifest: dict[str, Any],
    upstream_provider_dispatch_roundtrip_dir: Path | None,
    upstream_dispatch_roundtrip_dir: Path | None,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    passed = failed == 0
    roundtrip_summary = broker_dispatch_roundtrip.summary if broker_dispatch_roundtrip is not None else pd.DataFrame()
    nested_roundtrip_dir = (
        broker_dispatch_roundtrip_dir
        if broker_dispatch_roundtrip is None
        else Path(broker_dispatch_roundtrip.output_dir or broker_dispatch_roundtrip_dir)
    )
    config_receipt_proof = _mapping(provider_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(provider_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    provider_summary = _with_dispatch_roundtrip_config_fallback(provider_summary, provider_config)
    dispatch_roundtrip = _dispatch_roundtrip_provenance(provider_config)
    dispatch_roundtrip_config_receipt_proof = _mapping(
        dispatch_roundtrip.get("adapter_receipt_proof")
    )
    dispatch_roundtrip_manifest_receipt_proof = _mapping(
        _mapping(provider_manifest.get("extra")).get(
            "dispatch_roundtrip_adapter_receipt_proof"
        )
    )
    dispatch_roundtrip_receipt_status = _adapter_receipt_proof_status(
        dispatch_roundtrip_config_receipt_proof
    )
    nested_route_readiness_provided = _first_bool(roundtrip_summary, "route_readiness_provided")
    nested_route_readiness_ops_launch_controls_present = _first_bool(
        roundtrip_summary,
        "route_readiness_ops_launch_controls_present",
    )
    return pd.DataFrame(
        [
            {
                "authorizes_submission": False,
                "passed": passed,
                "ready": passed,
                "provider_broker_dispatch_ack_passed": _first_bool(provider_summary, "passed"),
                "broker_dispatch_roundtrip_passed": bool(
                    broker_dispatch_roundtrip is not None and broker_dispatch_roundtrip.passed
                ),
                "provider_broker_dispatch_ack_dir": str(provider_root),
                "broker_dispatch_dir": _path_text(broker_dispatch_dir),
                "broker_dispatch_send_dir": _path_text(broker_dispatch_send_dir),
                "broker_dispatch_ack_dir": _path_text(broker_dispatch_ack_dir),
                **_broker_dispatch_ack_lineage_summary_fields(
                    roundtrip_summary
                ),
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
                "provider_broker_dispatch_ack_manifest_run_type": _clean(
                    provider_manifest.get("run_type")
                ),
                "adapter_receipt_proof_ready": bool(receipt_status["ready"]),
                "adapter_receipt_proof_matches_manifest": bool(
                    config_receipt_proof
                    and manifest_receipt_proof
                    and config_receipt_proof == manifest_receipt_proof
                ),
                "adapter_receipts_required": _truthy(
                    config_receipt_proof.get("required")
                ),
                "adapter_receipt_required_count": int(
                    receipt_status["required_count"]
                ),
                "adapter_receipt_valid_count": int(receipt_status["valid_count"]),
                "adapter_receipt_fingerprint_match_count": int(
                    receipt_status["receipt_fingerprint_match_count"]
                ),
                "capture_fingerprint_match_count": int(
                    receipt_status["capture_fingerprint_match_count"]
                ),
                "provider_broker_dispatch_roundtrip_wrapper_provided": bool(
                    _truthy(dispatch_roundtrip.get("provider_wrapper_provided"))
                    or _first_bool(
                        provider_summary,
                        "provider_broker_dispatch_roundtrip_wrapper_provided",
                    )
                    or _truthy(
                        _mapping(provider_manifest.get("extra")).get(
                            "provider_broker_dispatch_roundtrip_wrapper_provided"
                        )
                    )
                ),
                "provider_broker_dispatch_roundtrip_manifest_run_type": _clean(
                    dispatch_roundtrip.get("provider_manifest_run_type")
                )
                or _first_text(
                    provider_summary,
                    "provider_broker_dispatch_roundtrip_manifest_run_type",
                )
                or _clean(
                    _mapping(provider_manifest.get("extra")).get(
                        "provider_broker_dispatch_roundtrip_manifest_run_type"
                    )
                ),
                "dispatch_roundtrip_adapter_receipt_proof_ready": bool(
                    dispatch_roundtrip_receipt_status["ready"]
                ),
                "dispatch_roundtrip_adapter_receipt_proof_matches_manifest": bool(
                    dispatch_roundtrip_config_receipt_proof
                    and dispatch_roundtrip_manifest_receipt_proof
                    and dispatch_roundtrip_config_receipt_proof
                    == dispatch_roundtrip_manifest_receipt_proof
                ),
                "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session": bool(
                    dispatch_roundtrip_config_receipt_proof
                    and config_receipt_proof
                    and dispatch_roundtrip_config_receipt_proof
                    == config_receipt_proof
                ),
                "dispatch_roundtrip_adapter_receipts_required": bool(
                    _truthy(
                        dispatch_roundtrip_config_receipt_proof.get("required")
                    )
                    or _truthy(
                        dispatch_roundtrip_manifest_receipt_proof.get("required")
                    )
                    or _first_bool(
                        provider_summary,
                        "dispatch_roundtrip_adapter_receipts_required",
                    )
                    or _number(
                        _mapping(provider_manifest.get("extra")).get(
                            "dispatch_roundtrip_adapter_receipt_required_count"
                        )
                    )
                    > 0
                ),
                "dispatch_roundtrip_adapter_receipt_required_count": int(
                    dispatch_roundtrip_receipt_status["required_count"]
                ),
                "dispatch_roundtrip_adapter_receipt_valid_count": int(
                    dispatch_roundtrip_receipt_status["valid_count"]
                ),
                "dispatch_roundtrip_adapter_receipt_fingerprint_match_count": int(
                    dispatch_roundtrip_receipt_status[
                        "receipt_fingerprint_match_count"
                    ]
                ),
                "dispatch_roundtrip_capture_fingerprint_match_count": int(
                    dispatch_roundtrip_receipt_status[
                        "capture_fingerprint_match_count"
                    ]
                ),
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
                "route_readiness_provided": _first_bool(provider_summary, "route_readiness_provided")
                or nested_route_readiness_provided,
                "route_readiness_ops_launch_controls_present": _first_bool(
                    provider_summary,
                    "route_readiness_ops_launch_controls_present",
                )
                or nested_route_readiness_ops_launch_controls_present,
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    _first_number(
                        provider_summary,
                        "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                    )
                ),
                "dispatch_roundtrip_synthetic_dataset_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_dataset_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_proof_ready": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_synthetic_sidecar_proof_ready",
                ),
                "dispatch_roundtrip_synthetic_sidecar_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_readable_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_readable_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_source_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_source_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count": int(
                    _first_number(
                        provider_summary,
                        "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count": int(
                    _first_number(
                        provider_summary,
                        "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _first_number(
                        provider_summary,
                        "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_invariant_count": int(
                    _first_number(provider_summary, "dispatch_roundtrip_synthetic_sidecar_invariant_count")
                ),
                "dispatch_roundtrip_route_readiness_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_route_readiness_provided",
                )
                or nested_route_readiness_provided,
                "dispatch_roundtrip_route_readiness_ops_launch_controls_present": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_route_readiness_ops_launch_controls_present",
                )
                or nested_route_readiness_ops_launch_controls_present,
                "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    _first_number(
                        provider_summary,
                        "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                    )
                ),
                "dispatch_roundtrip_provider_capture_command_count": int(
                    _first_number_with_unprovided_roundtrip_fallback(
                        provider_summary,
                        "dispatch_roundtrip_provider_capture_command_count",
                        "provider_capture_command_count",
                        "dispatch_roundtrip_capture_bundle_provided",
                    )
                ),
                "dispatch_roundtrip_provider_capture_command_providers": _first_text_with_fallback(
                    provider_summary,
                    "dispatch_roundtrip_provider_capture_command_providers",
                    "provider_capture_command_providers",
                ),
                "dispatch_roundtrip_provider_capture_command_transports": _first_text_with_fallback(
                    provider_summary,
                    "dispatch_roundtrip_provider_capture_command_transports",
                    "provider_capture_command_transports",
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_command_count": int(
                    _first_number_with_unprovided_roundtrip_fallback(
                        provider_summary,
                        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
                        "capture_bundle_provider_capture_command_count",
                        "dispatch_roundtrip_capture_bundle_provided",
                    )
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": int(
                    _first_number_with_fallback(
                        provider_summary,
                        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
                        "capture_bundle_provider_capture_command_missing_count",
                    )
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": _first_bool_with_fallback(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
                    "capture_bundle_provider_capture_commands_match_session",
                )
                if _first_bool_with_fallback(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_provided",
                    "capture_bundle_provided",
                )
                else True,
                "dispatch_roundtrip_provider_capture_commands_match_runtime_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
                )
                if _first_value_present(
                    provider_summary,
                    "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
                )
                else _first_bool_with_fallback(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
                    "capture_bundle_provider_capture_commands_match_session",
                ),
                "dispatch_roundtrip_adapter_contract_provider": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_provider",
                ),
                "dispatch_roundtrip_adapter_contract_transport": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_transport",
                ),
                "dispatch_roundtrip_adapter_contract_market": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_market",
                ),
                "dispatch_roundtrip_adapter_contract_exchange": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_exchange",
                ),
                "dispatch_roundtrip_adapter_contract_values_stored": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_values_stored",
                ),
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
                ),
                "dispatch_roundtrip_adapter_contract_matches_runtime_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_matches_runtime_session",
                )
                if _first_bool(provider_summary, "dispatch_roundtrip_capture_bundle_provided")
                else True,
                "dispatch_roundtrip_provider_profile_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_sha256",
                ),
                "dispatch_roundtrip_provider_profile_adapter": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_adapter",
                ),
                "dispatch_roundtrip_provider_profile_auth_required": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_auth_required",
                ),
                "dispatch_roundtrip_provider_profile_transports": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_transports",
                ),
                "dispatch_roundtrip_provider_profile_capabilities": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_capabilities",
                ),
                "dispatch_roundtrip_capture_bundle_provider_profile_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
                ),
                "dispatch_roundtrip_provider_profile_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_matches_session",
                )
                if _first_bool(provider_summary, "dispatch_roundtrip_capture_bundle_provided")
                else True,
                "dispatch_roundtrip_provider_profile_matches_bundle": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_provider_profile_matches_bundle",
                )
                if _first_bool(provider_summary, "dispatch_roundtrip_capture_bundle_provided")
                else True,
                "dispatch_roundtrip_adapter_contract_provider_profile_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
                ),
                "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
                ),
                "dispatch_roundtrip_provider_profile_matches_runtime_session": (
                    _dispatch_roundtrip_provider_profile_matches_session(provider_summary, provider_summary)
                )
                if _first_bool(provider_summary, "dispatch_roundtrip_capture_bundle_provided")
                else True,
                "dispatch_roundtrip_exchange": _first_text(provider_summary, "dispatch_roundtrip_exchange"),
                "dispatch_roundtrip_source_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_session_timezone",
                ),
                "dispatch_roundtrip_source_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_session_open_local",
                ),
                "dispatch_roundtrip_source_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_session_close_local",
                ),
                "dispatch_roundtrip_market_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_market_session_timezone",
                ),
                "dispatch_roundtrip_market_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_market_session_open_local",
                ),
                "dispatch_roundtrip_market_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_market_session_close_local",
                ),
                "dispatch_roundtrip_exchange_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_exchange_matches_session",
                ),
                "dispatch_roundtrip_source_session_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_session_matches_session",
                ),
                "dispatch_roundtrip_market_session_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_market_session_matches_session",
                ),
                "dispatch_roundtrip_metadata_consistent": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_metadata_consistent",
                ),
                "dispatch_roundtrip_source_credential_env_template_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_path",
                ),
                "dispatch_roundtrip_source_credential_env_template_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_exists",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_sha256",
                ),
                "dispatch_roundtrip_source_credential_env_template_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_matches_session",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_sha256_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_available": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_available",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_command_template",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_exchange",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_market": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_market",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_timezone",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_close_local",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_market_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_market_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_matches_session",
                ),
                "dispatch_roundtrip_source_provenance_consistent": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_provenance_consistent",
                ),
                "dispatch_roundtrip_capture_bundle_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_path",
                ),
                "dispatch_roundtrip_capture_bundle_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_provided",
                ),
                "dispatch_roundtrip_capture_bundle_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_exists",
                ),
                "dispatch_roundtrip_capture_bundle_ready": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_ready",
                ),
                "dispatch_roundtrip_capture_bundle_exchange": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_exchange",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_timezone",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_open_local",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_close_local",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_timezone": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_timezone",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_open_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_open_local",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_close_local": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_close_local",
                ),
                "dispatch_roundtrip_capture_bundle_metadata_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_metadata_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_exchange_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_exchange_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_matches_session",
                ),
                "dispatch_roundtrip_capture_env_template_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_path",
                ),
                "dispatch_roundtrip_capture_env_template_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_provided",
                ),
                "dispatch_roundtrip_capture_env_template_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_exists",
                ),
                "dispatch_roundtrip_capture_env_template_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_sha256",
                ),
                "dispatch_roundtrip_capture_env_template_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_matches_session",
                ),
                "dispatch_roundtrip_adapter_handoff_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_path",
                ),
                "dispatch_roundtrip_adapter_handoff_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_provided",
                ),
                "dispatch_roundtrip_adapter_handoff_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_exists",
                ),
                "dispatch_roundtrip_adapter_handoff_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_sha256",
                ),
                "dispatch_roundtrip_adapter_handoff_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_matches_session",
                ),
                "dispatch_roundtrip_capture_provenance_consistent": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_provenance_consistent",
                ),
                "upstream_provider_dispatch_roundtrip_dir": _path_text(upstream_provider_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_dir": _path_text(upstream_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_provided": bool(upstream_dispatch_roundtrip_dir)
                or _first_bool(provider_summary, "dispatch_roundtrip_provided"),
                "upstream_dispatch_roundtrip_ready": _first_bool(provider_summary, "dispatch_roundtrip_ready"),
                "upstream_dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "dispatch_roundtrip_failed_checks")
                ),
                "broker_dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(roundtrip_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(roundtrip_summary, "strategy")
                or _first_text(provider_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(roundtrip_summary, "target_mode")
                or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(roundtrip_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(roundtrip_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "dispatch_orders": int(
                    _first_number(roundtrip_summary, "dispatch_orders")
                    or _first_number(provider_summary, "dispatch_orders")
                ),
                "send_requests": int(_first_number(roundtrip_summary, "send_requests")),
                "acked_orders": int(_first_number(roundtrip_summary, "acked_orders")),
                "missing_request_acks": int(_first_number(roundtrip_summary, "missing_request_acks")),
                "rejected_orders": int(_first_number(roundtrip_summary, "rejected_orders")),
                "duplicate_ack_orders": int(_first_number(roundtrip_summary, "duplicate_ack_orders")),
                "unmatched_acks": int(_first_number(roundtrip_summary, "unmatched_acks")),
                "dispatch_total_notional": float(
                    _first_number(roundtrip_summary, "dispatch_total_notional")
                    or _first_number(provider_summary, "dispatch_total_notional")
                ),
                "route_readiness_required": _first_bool(roundtrip_summary, "route_readiness_required")
                or _first_bool(provider_summary, "route_readiness_required"),
                "route_readiness_ready": _first_bool(roundtrip_summary, "route_readiness_ready")
                or _first_bool(provider_summary, "route_readiness_ready"),
                "route_readiness_gap_pairs": int(
                    _first_number(roundtrip_summary, "route_readiness_gap_pairs")
                    or _first_number(provider_summary, "route_readiness_gap_pairs")
                ),
                "roundtrip_recommendation": _first_text(roundtrip_summary, "recommendation"),
                **_upstream_vendor_market_data_batch_summary_fields(provider_summary),
                **_nested_vendor_market_data_batch_summary_fields(broker_dispatch_roundtrip),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "feed_provider_imbalance_broker_roundtrip_into_broker_readiness"
                if passed
                else "repair_provider_imbalance_broker_dispatch_roundtrip",
                "next_gate": READY_NEXT_GATE if passed else _blocked_next_gate(checks, broker_dispatch_roundtrip),
                "next_gate_help_command": _help_command_for_gate(
                    READY_NEXT_GATE if passed else _blocked_next_gate(checks, broker_dispatch_roundtrip)
                ),
                "primary_action_status": "ready" if passed else "blocked",
            }
        ]
    )


DISPATCH_ROUNDTRIP_CONFIG_TEXT_FIELDS = (
    ("dispatch_roundtrip_exchange", "exchange"),
    ("dispatch_roundtrip_provider_capture_command_count", "provider_capture_command_count"),
    ("dispatch_roundtrip_provider_capture_command_providers", "provider_capture_command_providers"),
    ("dispatch_roundtrip_provider_capture_command_transports", "provider_capture_command_transports"),
    (
        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
        "capture_bundle_provider_capture_command_count",
    ),
    (
        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
        "capture_bundle_provider_capture_command_missing_count",
    ),
    (
        "dispatch_roundtrip_source_credential_env_template_path",
        "source_credential_env_template_path",
    ),
    (
        "dispatch_roundtrip_source_credential_env_template_sha256",
        "source_credential_env_template_sha256",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_next_gate",
        "source_live_fetch_contract_next_gate",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_command_template",
        "source_live_fetch_contract_command_template",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_exchange",
        "source_live_fetch_contract_exchange",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_market",
        "source_live_fetch_contract_market",
    ),
    ("dispatch_roundtrip_capture_bundle_path", "capture_bundle_path"),
    ("dispatch_roundtrip_capture_bundle_exchange", "capture_bundle_exchange"),
    ("dispatch_roundtrip_adapter_contract_provider", "adapter_contract_provider"),
    ("dispatch_roundtrip_adapter_contract_transport", "adapter_contract_transport"),
    ("dispatch_roundtrip_adapter_contract_market", "adapter_contract_market"),
    ("dispatch_roundtrip_adapter_contract_exchange", "adapter_contract_exchange"),
    ("dispatch_roundtrip_provider_profile_sha256", "provider_profile_sha256"),
    ("dispatch_roundtrip_provider_profile_adapter", "provider_profile_adapter"),
    ("dispatch_roundtrip_provider_profile_transports", "provider_profile_transports"),
    ("dispatch_roundtrip_provider_profile_capabilities", "provider_profile_capabilities"),
    (
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "capture_bundle_provider_profile_sha256",
    ),
    (
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ),
    ("dispatch_roundtrip_capture_env_template_path", "capture_env_template_path"),
    ("dispatch_roundtrip_capture_env_template_sha256", "capture_env_template_sha256"),
    ("dispatch_roundtrip_adapter_handoff_path", "adapter_handoff_path"),
    ("dispatch_roundtrip_adapter_handoff_sha256", "adapter_handoff_sha256"),
)

DISPATCH_ROUNDTRIP_CONFIG_BOOL_FIELDS = (
    ("dispatch_roundtrip_exchange_matches_session", "exchange_matches_session"),
    ("dispatch_roundtrip_source_session_matches_session", "source_session_matches_session"),
    ("dispatch_roundtrip_market_session_matches_session", "market_session_matches_session"),
    (
        "dispatch_roundtrip_metadata_consistent",
        "metadata_consistent_with_runtime_session",
    ),
    (
        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
        "capture_bundle_provider_capture_commands_match_session",
    ),
    (
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "provider_capture_commands_match_runtime_session",
    ),
    ("dispatch_roundtrip_adapter_contract_values_stored", "adapter_contract_values_stored"),
    (
        "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
        "adapter_contract_metadata_matches_evidence",
    ),
    (
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "adapter_contract_matches_runtime_session",
    ),
    ("dispatch_roundtrip_provider_profile_auth_required", "provider_profile_auth_required"),
    (
        "dispatch_roundtrip_provider_profile_matches_session",
        "provider_profile_matches_session",
    ),
    (
        "dispatch_roundtrip_provider_profile_matches_bundle",
        "provider_profile_matches_bundle",
    ),
    (
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        "provider_profile_matches_runtime_session",
    ),
    (
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        "adapter_contract_provider_profile_matches_evidence",
    ),
    (
        "dispatch_roundtrip_source_credential_env_template_exists",
        "source_credential_env_template_exists",
    ),
    (
        "dispatch_roundtrip_source_credential_env_template_matches_session",
        "source_credential_env_template_matches_session",
    ),
    (
        "dispatch_roundtrip_source_credential_env_template_sha256_matches_session",
        "source_credential_env_template_sha256_matches_session",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_available",
        "source_live_fetch_contract_available",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session",
        "source_live_fetch_contract_next_gate_matches_session",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session",
        "source_live_fetch_contract_command_template_matches_session",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
        "source_live_fetch_contract_exchange_matches_session",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_market_matches_session",
        "source_live_fetch_contract_market_matches_session",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_session_matches_session",
        "source_live_fetch_contract_session_matches_session",
    ),
    (
        "dispatch_roundtrip_source_provenance_consistent",
        "source_provenance_consistent_with_runtime_session",
    ),
    ("dispatch_roundtrip_capture_bundle_provided", "capture_bundle_provided"),
    ("dispatch_roundtrip_capture_bundle_exists", "capture_bundle_exists"),
    ("dispatch_roundtrip_capture_bundle_ready", "capture_bundle_ready"),
    (
        "dispatch_roundtrip_capture_bundle_metadata_matches_session",
        "capture_bundle_metadata_matches_session",
    ),
    (
        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
        "capture_bundle_live_fetch_contract_metadata_matches_session",
    ),
    ("dispatch_roundtrip_capture_bundle_matches_session", "capture_bundle_matches_session"),
    (
        "dispatch_roundtrip_capture_bundle_exchange_matches_session",
        "capture_bundle_exchange_matches_session",
    ),
    (
        "dispatch_roundtrip_capture_bundle_source_session_matches_session",
        "capture_bundle_source_session_matches_session",
    ),
    (
        "dispatch_roundtrip_capture_bundle_market_session_matches_session",
        "capture_bundle_market_session_matches_session",
    ),
    ("dispatch_roundtrip_capture_env_template_provided", "capture_env_template_provided"),
    ("dispatch_roundtrip_capture_env_template_exists", "capture_env_template_exists"),
    (
        "dispatch_roundtrip_capture_env_template_matches_session",
        "capture_env_template_matches_session",
    ),
    ("dispatch_roundtrip_adapter_handoff_provided", "adapter_handoff_provided"),
    ("dispatch_roundtrip_adapter_handoff_exists", "adapter_handoff_exists"),
    ("dispatch_roundtrip_adapter_handoff_matches_session", "adapter_handoff_matches_session"),
    (
        "dispatch_roundtrip_capture_provenance_consistent",
        "consistent_with_runtime_session",
    ),
)

DISPATCH_ROUNDTRIP_CONFIG_NESTED_TEXT_FIELDS = (
    ("dispatch_roundtrip_source_session_timezone", "source_session", "timezone"),
    ("dispatch_roundtrip_source_session_open_local", "source_session", "open_local"),
    ("dispatch_roundtrip_source_session_close_local", "source_session", "close_local"),
    ("dispatch_roundtrip_market_session_timezone", "market_session", "timezone"),
    ("dispatch_roundtrip_market_session_open_local", "market_session", "open_local"),
    ("dispatch_roundtrip_market_session_close_local", "market_session", "close_local"),
    (
        "dispatch_roundtrip_source_live_fetch_contract_session_timezone",
        "source_live_fetch_contract_session",
        "timezone",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
        "source_live_fetch_contract_session",
        "open_local",
    ),
    (
        "dispatch_roundtrip_source_live_fetch_contract_session_close_local",
        "source_live_fetch_contract_session",
        "close_local",
    ),
    (
        "dispatch_roundtrip_capture_bundle_source_session_timezone",
        "capture_bundle_source_session",
        "timezone",
    ),
    (
        "dispatch_roundtrip_capture_bundle_source_session_open_local",
        "capture_bundle_source_session",
        "open_local",
    ),
    (
        "dispatch_roundtrip_capture_bundle_source_session_close_local",
        "capture_bundle_source_session",
        "close_local",
    ),
    (
        "dispatch_roundtrip_capture_bundle_market_session_timezone",
        "capture_bundle_market_session",
        "timezone",
    ),
    (
        "dispatch_roundtrip_capture_bundle_market_session_open_local",
        "capture_bundle_market_session",
        "open_local",
    ),
    (
        "dispatch_roundtrip_capture_bundle_market_session_close_local",
        "capture_bundle_market_session",
        "close_local",
    ),
)


def _with_dispatch_roundtrip_config_fallback(
    frame: pd.DataFrame,
    provider_config: dict[str, Any],
) -> pd.DataFrame:
    fallback = _dispatch_roundtrip_config_summary(provider_config)
    if fallback.empty:
        return frame
    if frame is None or frame.empty:
        return fallback
    out = frame.copy()
    fallback_row = fallback.iloc[0]
    for column in fallback.columns:
        value = fallback_row[column]
        if not _value_present(value):
            continue
        if column not in out.columns:
            out[column] = ""
        if not _first_value_present(out, column):
            out[column] = out[column].astype("object")
            out.loc[out.index[0], column] = value
    return out


def _dispatch_roundtrip_config_summary(provider_config: dict[str, Any]) -> pd.DataFrame:
    provenance = _dispatch_roundtrip_provenance(provider_config)
    if not provenance:
        return pd.DataFrame()
    record: dict[str, Any] = {}
    for column, key in DISPATCH_ROUNDTRIP_CONFIG_TEXT_FIELDS:
        _set_config_text(record, column, provenance, key)
    for column, key in DISPATCH_ROUNDTRIP_CONFIG_BOOL_FIELDS:
        _set_config_bool(record, column, provenance, key)
    for column, key, nested_key in DISPATCH_ROUNDTRIP_CONFIG_NESTED_TEXT_FIELDS:
        _set_nested_config_text(record, column, provenance, key, nested_key)
    synthetic_sidecar_proof = _mapping(provenance.get("synthetic_sidecar_proof"))
    _set_config_text(record, "dispatch_roundtrip_synthetic_dataset_count", provenance, "synthetic_dataset_count")
    _set_config_bool(
        record,
        "dispatch_roundtrip_synthetic_sidecar_proof_ready",
        provenance,
        "synthetic_sidecar_proof_ready",
    )
    _set_config_text(record, "dispatch_roundtrip_synthetic_sidecar_count", provenance, "synthetic_sidecar_count")
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_readable_count",
        provenance,
        "synthetic_sidecar_readable_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_source_count",
        provenance,
        "synthetic_sidecar_source_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count",
        provenance,
        "synthetic_sidecar_adapter_command_hash_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count",
        provenance,
        "synthetic_sidecar_capture_env_template_match_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count",
        provenance,
        "synthetic_sidecar_adapter_handoff_match_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count",
        provenance,
        "synthetic_sidecar_source_env_template_match_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count",
        provenance,
        "synthetic_sidecar_live_fetch_contract_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count",
        provenance,
        "synthetic_sidecar_adapter_execution_contract_safe_count",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_synthetic_sidecar_invariant_count",
        provenance,
        "synthetic_sidecar_invariant_count",
    )
    _set_config_bool(record, "dispatch_roundtrip_route_readiness_provided", provenance, "route_readiness_provided")
    _set_config_bool(
        record,
        "dispatch_roundtrip_route_readiness_ops_launch_controls_present",
        provenance,
        "route_readiness_ops_launch_controls_present",
    )
    _set_config_text(
        record,
        "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
        provenance,
        "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
    )
    if synthetic_sidecar_proof:
        _set_config_bool(
            record,
            "dispatch_roundtrip_synthetic_sidecar_proof_ready",
            synthetic_sidecar_proof,
            "ready",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_count",
            synthetic_sidecar_proof,
            "synthetic_sidecar_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_readable_count",
            synthetic_sidecar_proof,
            "sidecar_readable_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_source_count",
            synthetic_sidecar_proof,
            "sidecar_source_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count",
            synthetic_sidecar_proof,
            "adapter_command_hash_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count",
            synthetic_sidecar_proof,
            "capture_env_template_match_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count",
            synthetic_sidecar_proof,
            "adapter_handoff_match_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count",
            synthetic_sidecar_proof,
            "source_credential_env_template_match_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count",
            synthetic_sidecar_proof,
            "live_fetch_contract_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count",
            synthetic_sidecar_proof,
            "adapter_execution_contract_safe_count",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_synthetic_sidecar_invariant_count",
            synthetic_sidecar_proof,
            "invariant_count",
        )
    contract = _mapping(provenance.get("adapter_execution_contract"))
    if contract:
        _set_config_text(record, "dispatch_roundtrip_adapter_contract_provider", contract, "provider")
        _set_config_text(record, "dispatch_roundtrip_adapter_contract_transport", contract, "transport")
        _set_config_text(record, "dispatch_roundtrip_adapter_contract_market", contract, "market")
        _set_config_text(record, "dispatch_roundtrip_adapter_contract_exchange", contract, "exchange")
        _set_config_bool(record, "dispatch_roundtrip_adapter_contract_values_stored", contract, "values_stored")
        _set_config_text(
            record,
            "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
            contract,
            "provider_profile_sha256",
        )
        _set_config_bool(
            record,
            "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
            contract,
            "metadata_matches_evidence",
        )
    provider_profile = _mapping(provenance.get("provider_profile"))
    if provider_profile:
        _set_config_text(record, "dispatch_roundtrip_provider_profile_sha256", provider_profile, "sha256")
        _set_config_text(record, "dispatch_roundtrip_provider_profile_adapter", provider_profile, "adapter")
        _set_config_bool(
            record,
            "dispatch_roundtrip_provider_profile_auth_required",
            provider_profile,
            "auth_required",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_provider_profile_transports",
            provider_profile,
            "transports",
        )
        _set_config_text(
            record,
            "dispatch_roundtrip_provider_profile_capabilities",
            provider_profile,
            "capabilities",
        )
    capture_bundle_provider_profile = _mapping(provenance.get("capture_bundle_provider_profile"))
    if capture_bundle_provider_profile:
        _set_config_text(
            record,
            "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
            capture_bundle_provider_profile,
            "sha256",
        )
    _set_config_bool(
        record,
        "dispatch_roundtrip_provider_profile_matches_session",
        provenance,
        "provider_profile_matches_session",
    )
    _set_config_bool(
        record,
        "dispatch_roundtrip_provider_profile_matches_bundle",
        provenance,
        "provider_profile_matches_bundle",
    )
    _set_config_bool(
        record,
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        provenance,
        "provider_profile_matches_runtime_session",
    )
    _set_config_bool(
        record,
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        provenance,
        "adapter_contract_provider_profile_matches_evidence",
    )
    return pd.DataFrame([record]) if record else pd.DataFrame()


def _dispatch_roundtrip_provenance(provider_config: dict[str, Any]) -> dict[str, Any]:
    value = provider_config.get("dispatch_roundtrip_provenance", {})
    return value if isinstance(value, dict) else {}


def _dispatch_roundtrip_synthetic_sidecar_proof(provider_config: dict[str, Any]) -> dict[str, Any]:
    return _mapping(_dispatch_roundtrip_provenance(provider_config).get("synthetic_sidecar_proof"))


def _dispatch_roundtrip_provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    return _list(_dispatch_roundtrip_provenance(provider_config).get("provider_capture_commands")) or (
        _provider_capture_commands(provider_config)
    )


def _dispatch_roundtrip_capture_bundle_provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    return _list(
        _dispatch_roundtrip_provenance(provider_config).get("capture_bundle_provider_capture_commands")
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


def _set_config_text(record: dict[str, Any], column: str, mapping: dict[str, Any], key: str) -> None:
    if _value_present(record.get(column)) or key not in mapping:
        return
    value = _clean(mapping.get(key))
    if value:
        record[column] = value


def _set_config_bool(record: dict[str, Any], column: str, mapping: dict[str, Any], key: str) -> None:
    if _value_present(record.get(column)) or key not in mapping:
        return
    record[column] = _truthy(mapping.get(key))


def _set_nested_config_text(
    record: dict[str, Any],
    column: str,
    mapping: dict[str, Any],
    key: str,
    nested_key: str,
) -> None:
    if _value_present(record.get(column)):
        return
    nested = mapping.get(key, {})
    if not isinstance(nested, dict) or nested_key not in nested:
        return
    value = _clean(nested.get(nested_key))
    if value:
        record[column] = value


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
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_broker_dispatch_roundtrip_summary",
                    "component": "broker_dispatch_roundtrip",
                    "check": "broker_dispatch_roundtrip_passed",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "feed_provider_imbalance_broker_dispatch_roundtrip_into_broker_readiness",
                    "reason": "provider imbalance broker dispatch dry-run round-trip proof passed",
                    "recommendation": "supply_nested_roundtrip_to_provider_broker_readiness_before_cutover",
                    "next_gate": READY_NEXT_GATE,
                    "next_gate_help_command": _help_command_for_gate(READY_NEXT_GATE),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, broker_dispatch_roundtrip)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_dispatch_roundtrip_checks",
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
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    provider_manifest: dict[str, Any],
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig,
    broker_dispatch_roundtrip_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    dispatch_roundtrip_provider_capture_commands = _dispatch_roundtrip_provider_capture_commands(provider_config)
    dispatch_roundtrip_capture_bundle_provider_capture_commands = (
        _dispatch_roundtrip_capture_bundle_provider_capture_commands(provider_config)
    )
    dispatch_roundtrip_adapter_execution_contract = _dispatch_roundtrip_adapter_execution_contract(provider_config)
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "passed": bool(summary["passed"]),
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "broker_dispatch_roundtrip_inputs": _jsonable(broker_dispatch_roundtrip_inputs),
        "broker_dispatch_ack_lineage": _broker_dispatch_ack_lineage_config(
            summary
        ),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(provider_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(provider_config.get("live_session_provider_profile")),
        "provider_capture_commands": _provider_capture_commands(provider_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(provider_config),
        "adapter_execution_contract": _adapter_execution_contract(provider_config),
        "adapter_receipt_proof": _mapping(
            provider_config.get("adapter_receipt_proof")
        ),
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
            "metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "live_fetch_contract_metadata_matches_session": bool(
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
            "adapter_receipt_proof": _mapping(
                provider_config.get("adapter_receipt_proof")
            ),
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
            "provider_wrapper_provided": bool(
                summary["provider_broker_dispatch_roundtrip_wrapper_provided"]
            ),
            "provider_manifest_run_type": str(
                summary["provider_broker_dispatch_roundtrip_manifest_run_type"]
            ),
            "adapter_receipt_proof": _mapping(
                _dispatch_roundtrip_provenance(provider_config).get(
                    "adapter_receipt_proof"
                )
            ),
            "adapter_receipt_proof_ready": bool(
                summary["dispatch_roundtrip_adapter_receipt_proof_ready"]
            ),
            "adapter_receipt_proof_matches_manifest": bool(
                summary[
                    "dispatch_roundtrip_adapter_receipt_proof_matches_manifest"
                ]
            ),
            "adapter_receipt_proof_matches_runtime_session": bool(
                summary[
                    "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session"
                ]
            ),
            "adapter_receipt_required_count": int(
                summary["dispatch_roundtrip_adapter_receipt_required_count"]
            ),
            "adapter_receipt_valid_count": int(
                summary["dispatch_roundtrip_adapter_receipt_valid_count"]
            ),
            "adapter_receipt_fingerprint_match_count": int(
                summary[
                    "dispatch_roundtrip_adapter_receipt_fingerprint_match_count"
                ]
            ),
            "capture_fingerprint_match_count": int(
                summary["dispatch_roundtrip_capture_fingerprint_match_count"]
            ),
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
            "route_readiness_provided": bool(summary["dispatch_roundtrip_route_readiness_provided"]),
            "route_readiness_ops_launch_controls_present": bool(
                summary["dispatch_roundtrip_route_readiness_ops_launch_controls_present"]
            ),
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                summary[
                    "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"
                ]
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
            "provider_capture_commands": dispatch_roundtrip_provider_capture_commands,
            "capture_bundle_provider_capture_commands": dispatch_roundtrip_capture_bundle_provider_capture_commands,
            "provider_capture_commands_match_runtime_session": bool(
                summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
            ),
            "adapter_execution_contract": dispatch_roundtrip_adapter_execution_contract,
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
        "provider_broker_dispatch_ack": _first_record(provider_summary),
        "provider_broker_dispatch_ack_config": provider_config,
        "provider_broker_dispatch_ack_manifest_run_type": _clean(
            provider_manifest.get("run_type")
        ),
        **_upstream_vendor_market_data_batch_config_fields(provider_config),
        **_nested_vendor_market_data_batch_config_fields(broker_dispatch_roundtrip),
        "broker_dispatch_roundtrip": {
            "evaluated": broker_dispatch_roundtrip is not None,
            "passed": False if broker_dispatch_roundtrip is None else bool(broker_dispatch_roundtrip.passed),
            "output_dir": "" if broker_dispatch_roundtrip is None else str(broker_dispatch_roundtrip.output_dir or ""),
            "orders": _records(None if broker_dispatch_roundtrip is None else broker_dispatch_roundtrip.orders),
            "summary": _first_record(None if broker_dispatch_roundtrip is None else broker_dispatch_roundtrip.summary),
            "checks": _records(None if broker_dispatch_roundtrip is None else broker_dispatch_roundtrip.checks),
            "action_queue": _records(
                None if broker_dispatch_roundtrip is None else broker_dispatch_roundtrip.action_queue
            ),
            "config": {}
            if broker_dispatch_roundtrip is None or broker_dispatch_roundtrip.config is None
            else broker_dispatch_roundtrip.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _upstream_vendor_market_data_batch_summary_fields(provider_summary: pd.DataFrame) -> dict[str, object]:
    fields: dict[str, object] = {}
    for source_prefix, target_prefix in UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES:
        for suffix in VENDOR_MARKET_DATA_BATCH_SUMMARY_SUFFIXES:
            source_key = f"{source_prefix}_{suffix}"
            key = f"{target_prefix}_{suffix}"
            if suffix in {"provided", "ready", "comparison_accepted"}:
                fields[key] = _first_bool(provider_summary, source_key)
            elif suffix in {
                "dataset_count",
                "ready_datasets",
                "failed_datasets",
                "unique_source_files",
                "unique_header_fingerprints",
                "unique_mapping_drafts",
                "comparison_failed_checks",
            }:
                fields[key] = int(_first_number(provider_summary, source_key))
            elif suffix in {"ready_rate", "source_file_fingerprint_coverage", "min_mapping_coverage"}:
                fields[key] = float(_first_number(provider_summary, source_key))
            else:
                fields[key] = _first_text(provider_summary, source_key)
    return fields


def _nested_vendor_market_data_batch_summary_fields(
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
) -> dict[str, object]:
    summary = broker_dispatch_roundtrip.summary if broker_dispatch_roundtrip is not None else pd.DataFrame()
    fields: dict[str, object] = {}
    for prefix in VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES:
        for suffix in VENDOR_MARKET_DATA_BATCH_SUMMARY_SUFFIXES:
            key = f"{prefix}_{suffix}"
            source_key = _vendor_market_data_batch_summary_key(summary, prefix, suffix)
            if suffix in {"provided", "ready", "comparison_accepted"}:
                fields[key] = _first_bool(summary, source_key)
            elif suffix in {
                "dataset_count",
                "ready_datasets",
                "failed_datasets",
                "unique_source_files",
                "unique_header_fingerprints",
                "unique_mapping_drafts",
                "comparison_failed_checks",
            }:
                fields[key] = int(_first_number(summary, source_key))
            elif suffix in {"ready_rate", "source_file_fingerprint_coverage", "min_mapping_coverage"}:
                fields[key] = float(_first_number(summary, source_key))
            else:
                fields[key] = _first_text(summary, source_key)
    return fields


def _vendor_market_data_batch_summary_key(summary: pd.DataFrame, prefix: str, suffix: str) -> str:
    key = f"{prefix}_{suffix}"
    if (
        prefix == "broker_dispatch_roundtrip_vendor_market_data_batch"
        and key not in summary.columns
    ):
        return f"roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_{suffix}"
    return key


def _upstream_vendor_market_data_batch_config_fields(provider_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "upstream_dispatch_roundtrip_vendor_market_data_batch": _provider_vendor_market_data_batch_config(
            provider_config,
            "dispatch_roundtrip_vendor_market_data_batch",
        ),
        "upstream_broker_dispatch_roundtrip_vendor_market_data_batch": _provider_vendor_market_data_batch_config(
            provider_config,
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
    }


def _provider_vendor_market_data_batch_config(provider_config: dict[str, Any], key: str) -> dict[str, Any]:
    vendor = _mapping(provider_config.get(key))
    if vendor:
        return vendor
    provider_send_config = provider_config.get("provider_broker_dispatch_send_config", {})
    if isinstance(provider_send_config, dict):
        return _mapping(provider_send_config.get(key))
    return {}


def _nested_vendor_market_data_batch_config_fields(
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
) -> dict[str, Any]:
    config = broker_dispatch_roundtrip.config if broker_dispatch_roundtrip is not None else {}
    config = config if isinstance(config, dict) else {}
    broker_dispatch_vendor = _mapping(config.get("broker_dispatch_roundtrip_vendor_market_data_batch"))
    roundtrip_broker_dispatch_vendor = _mapping(
        config.get("roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch")
    )
    return {
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch": roundtrip_broker_dispatch_vendor,
        "broker_dispatch_roundtrip_vendor_market_data_batch": (
            broker_dispatch_vendor or roundtrip_broker_dispatch_vendor
        ),
        "roundtrip_vendor_market_data_batch": _mapping(config.get("roundtrip_vendor_market_data_batch")),
    }


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    dispatch_roundtrip_receipt_line = (
        "- Dispatch round-trip adapter receipt proof: not applicable "
        "(no provider wrapper proof)"
        if not bool(summary["provider_broker_dispatch_roundtrip_wrapper_provided"])
        else (
            "- Dispatch round-trip adapter receipt proof: not applicable "
            "(provider wrapper has no required adapter receipts)"
            if not bool(summary["dispatch_roundtrip_adapter_receipts_required"])
            else (
                "- Dispatch round-trip adapter receipt proof: "
                f"{'ready' if bool(summary['dispatch_roundtrip_adapter_receipt_proof_ready']) else 'blocked'} "
                f"({summary['dispatch_roundtrip_adapter_receipt_fingerprint_match_count']}/"
                f"{summary['dispatch_roundtrip_adapter_receipt_required_count']} sealed; "
                "ack manifest match: "
                f"{'yes' if bool(summary['dispatch_roundtrip_adapter_receipt_proof_matches_manifest']) else 'no'}; "
                "runtime match: "
                f"{'yes' if bool(summary['dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session']) else 'no'})"
            )
        )
    )
    lines = [
        "# Provider Market Data Imbalance Broker Dispatch Round-Trip",
        "",
        f"- Passed: {'yes' if bool(summary['passed']) else 'no'}",
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
        f"- Dispatch orders: {summary['dispatch_orders']}",
        f"- Send requests: {summary['send_requests']}",
        f"- Acked orders: {summary['acked_orders']}",
        f"- Missing request acks: {summary['missing_request_acks']}",
        f"- Rejected orders: {summary['rejected_orders']}",
        "- Acknowledgement lineage: "
        f"{'current' if bool(summary['broker_dispatch_ack_lineage_gate_passed']) else 'blocked'}",
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
        f"- Adapter receipt proof: {'ready' if bool(summary['adapter_receipt_proof_ready']) else 'blocked'} ({summary['adapter_receipt_fingerprint_match_count']}/{summary['adapter_receipt_required_count']} sealed; ack manifest match: {'yes' if bool(summary['adapter_receipt_proof_matches_manifest']) else 'no'})",
        dispatch_roundtrip_receipt_line,
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'} ({summary['synthetic_sidecar_count']}/{summary['synthetic_dataset_count']})",
        "- Route sidecar breach pairs: "
        f"{summary['route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs']}",
        "- Dispatch round-trip synthetic sidecar proof: "
        f"{'yes' if bool(summary['dispatch_roundtrip_synthetic_sidecar_proof_ready']) else 'no'} "
        f"({summary['dispatch_roundtrip_synthetic_sidecar_count']}/"
        f"{summary['dispatch_roundtrip_synthetic_dataset_count']})",
        "- Dispatch round-trip route sidecar breach pairs: "
        f"{summary['dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs']}",
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
        f"- Upstream dispatch round-trip ready: {'yes' if bool(summary['upstream_dispatch_roundtrip_ready']) else 'no'}",
        f"- Upstream dispatch round-trip dir: {summary['upstream_dispatch_roundtrip_dir']}",
        "- Upstream dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['upstream_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Upstream broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Fresh broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        f"- Broker dispatch round-trip dir: {summary['broker_dispatch_roundtrip_dir']}",
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
    config: ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig,
    provider_summary: pd.DataFrame,
) -> BrokerDispatchRoundTripThresholds:
    return BrokerDispatchRoundTripThresholds(
        target_mode=config.target_mode or _first_text(provider_summary, "target_mode") or "live_dryrun",
        require_dispatch_ready=config.require_dispatch_ready,
        require_send_ready=config.require_send_ready,
        require_ack_passed=config.require_ack_passed,
        require_identity_match=config.require_identity_match,
        require_submission_disabled=config.require_submission_disabled,
        require_all_requests_acked=config.require_all_requests_acked,
        require_route_readiness=config.require_route_readiness,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        require_ack_lineage=config.require_ack_lineage,
        allow_rejections=config.allow_rejections,
        max_duplicate_ack_orders=config.max_duplicate_ack_orders,
        max_unmatched_acks=config.max_unmatched_acks,
        max_missing_request_acks=config.max_missing_request_acks,
        max_total_failed_component_checks=config.max_total_failed_component_checks,
    )


def _broker_dispatch_roundtrip_failure_reason(
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
) -> str:
    if broker_dispatch_roundtrip is None or broker_dispatch_roundtrip.checks.empty:
        return ""
    failed = broker_dispatch_roundtrip.checks.loc[~broker_dispatch_roundtrip.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(
    checks: pd.DataFrame,
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    return _next_gate_for_check(failed[0], broker_dispatch_roundtrip)


def _next_gate_for_check(
    check: str,
    broker_dispatch_roundtrip: BrokerDispatchRoundTripReport | None,
) -> str:
    if check.startswith("provider_broker_dispatch_ack_dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("provider_broker_dispatch_ack_route_readiness_provider_sidecar"):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("provider_broker_dispatch_ack") or check.startswith("provider_nested_broker_dispatch_ack"):
        return "reconcile-provider-market-data-imbalance-broker-dispatch"
    if check.startswith("generic_broker_dispatch_send") or check.startswith("nested_broker_dispatch_send"):
        return "prepare-provider-market-data-imbalance-broker-dispatch-send"
    if check.startswith("generic_broker_dispatch_ack") or check.startswith("nested_broker_dispatch_ack"):
        return "reconcile-provider-market-data-imbalance-broker-dispatch"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "plan-provider-market-data-imbalance-broker-dispatch"
    if check == "broker_dispatch_roundtrip_passed" and broker_dispatch_roundtrip is not None:
        next_gate = _provider_gate(_first_action_value(broker_dispatch_roundtrip.action_queue, "next_gate"))
        return next_gate or "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    if check.startswith("broker_dispatch_roundtrip"):
        return "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    if check in {"strategy_identity_imbalance", "market_identity_consistent", "adapter_identity_consistent"}:
        return "reconcile-provider-market-data-imbalance-broker-dispatch"
    return "review-provider-market-data-imbalance-broker-dispatch-roundtrip"


def _provider_gate(next_gate: str) -> str:
    mapping = {
        "plan-broker-dispatch": "plan-provider-market-data-imbalance-broker-dispatch",
        "prepare-broker-dispatch-send": "prepare-provider-market-data-imbalance-broker-dispatch-send",
        "reconcile-broker-dispatch": "reconcile-provider-market-data-imbalance-broker-dispatch",
        "review-broker-dispatch-roundtrip": "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
        "review-broker-readiness": "review-provider-market-data-imbalance-broker-readiness",
        "review-route-readiness": "review-provider-market-data-imbalance-route-readiness",
    }
    return mapping.get(next_gate, next_gate)


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-broker-dispatch-roundtrip":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-dispatch-roundtrip --help"
    if next_gate == "reconcile-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli reconcile-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "prepare-provider-market-data-imbalance-broker-dispatch-send":
        return "python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send --help"
    if next_gate == "plan-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == READY_NEXT_GATE:
        return "python -m hft_cli review-provider-market-data-imbalance-broker-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-route-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    if next_gate == "reconcile-broker-dispatch":
        return "python -m hft_cli reconcile-broker-dispatch --help"
    if next_gate == "prepare-broker-dispatch-send":
        return "python -m hft_cli prepare-broker-dispatch-send --help"
    if next_gate == "plan-broker-dispatch":
        return "python -m hft_cli plan-broker-dispatch --help"
    if next_gate == "review-broker-dispatch-roundtrip":
        return "python -m hft_cli review-broker-dispatch-roundtrip --help"
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _component_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch_ack_dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "provider_route_readiness"
    if check.startswith("provider_broker_dispatch_ack_route_readiness_provider_sidecar"):
        return "provider_route_readiness"
    if check.startswith("provider_broker_dispatch_ack") or check.startswith("provider_nested_broker_dispatch_ack"):
        return "provider_broker_dispatch_ack"
    if check.startswith("generic_broker_dispatch_send") or check.startswith("nested_broker_dispatch_send"):
        return "broker_dispatch_send"
    if check.startswith("generic_broker_dispatch_ack") or check.startswith("nested_broker_dispatch_ack"):
        return "broker_dispatch_ack"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "broker_dispatch"
    if check.startswith("broker_dispatch_roundtrip"):
        return "broker_dispatch_roundtrip"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_broker_dispatch_roundtrip"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch_ack_dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("provider_broker_dispatch_ack_route_readiness_provider_sidecar"):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("provider_broker_dispatch_ack") or check.startswith("provider_nested_broker_dispatch_ack"):
        return "repair_provider_imbalance_broker_dispatch_ack"
    if check.startswith("generic_broker_dispatch_send") or check.startswith("nested_broker_dispatch_send"):
        return "repair_provider_imbalance_broker_dispatch_send"
    if check.startswith("generic_broker_dispatch_ack") or check.startswith("nested_broker_dispatch_ack"):
        return "repair_provider_imbalance_broker_dispatch_ack_inputs"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "repair_provider_imbalance_broker_dispatch_inputs"
    if check.startswith("broker_dispatch_roundtrip"):
        return "repair_broker_dispatch_roundtrip"
    return "repair_provider_imbalance_broker_dispatch_roundtrip"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch_ack_dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "review_provider_roundtrip_route_readiness_sidecar_proof_before_broker_dispatch_roundtrip"
    if check.startswith("provider_broker_dispatch_ack_route_readiness_provider_sidecar"):
        return "review_provider_route_readiness_sidecar_proof_before_broker_dispatch_roundtrip"
    if check.startswith("provider_broker_dispatch_ack") or check.startswith("provider_nested_broker_dispatch_ack"):
        return "rerun_provider_broker_dispatch_ack_before_roundtrip_review"
    if check.startswith("generic_broker_dispatch_send") or check.startswith("nested_broker_dispatch_send"):
        return "rerun_provider_broker_dispatch_send_to_refresh_nested_sender_packet"
    if check.startswith("generic_broker_dispatch_ack") or check.startswith("nested_broker_dispatch_ack"):
        return "rerun_provider_broker_dispatch_ack_to_refresh_nested_ack_proof"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "rerun_provider_broker_dispatch_to_refresh_nested_dispatch_plan"
    if check.startswith("broker_dispatch_roundtrip"):
        return "review_nested_roundtrip_failures_and_rebuild_failed_component"
    return "repair_provider_broker_dispatch_roundtrip_inputs"


def _inferred_generic_inputs(
    provider_root: Path,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> dict[str, Path | None]:
    provider_send_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "provider_broker_dispatch_send_dir")),
        _path_from_text((provider_config.get("broker_dispatch_ack_inputs", {}) or {}).get("provider_broker_dispatch_send_dir")),
    )
    provider_send_config = provider_config.get("provider_broker_dispatch_send_config", {}) or {}
    provider_send_summary = provider_config.get("provider_broker_dispatch_send", {}) or {}
    nested_send = provider_send_config.get("broker_dispatch_send", {}) or {}
    ack_inputs = provider_config.get("broker_dispatch_ack_inputs", {}) or {}
    nested_ack = provider_config.get("broker_dispatch_ack", {}) or {}
    nested_ack_config = nested_ack.get("config", {}) if isinstance(nested_ack, dict) else {}
    nested_ack_inputs = nested_ack_config.get("inputs", {}) if isinstance(nested_ack_config, dict) else {}
    return {
        "broker_dispatch_dir": _first_existing_path(
            _path_from_text(_first_text(provider_summary, "broker_dispatch_dir")),
            _path_from_text(ack_inputs.get("broker_dispatch_dir")),
            _path_from_text(nested_ack_inputs.get("dispatch_dir")),
        ),
        "broker_dispatch_send_dir": _first_existing_path(
            _path_from_text(_first_text(provider_summary, "broker_dispatch_send_dir")),
            _path_from_text(provider_send_summary.get("broker_dispatch_send_dir")),
            _path_from_text(nested_send.get("output_dir") if isinstance(nested_send, dict) else ""),
            _child_path(provider_send_dir, "broker_dispatch_send"),
        ),
        "broker_dispatch_ack_dir": _first_existing_path(
            _path_from_text(_first_text(provider_summary, "broker_dispatch_ack_dir")),
            _path_from_text(nested_ack.get("output_dir") if isinstance(nested_ack, dict) else ""),
        ),
    }


def _inferred_upstream_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    ack_inputs = provider_config.get("broker_dispatch_ack_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "provider_dispatch_roundtrip_dir")),
        _path_from_text(ack_inputs.get("provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "dispatch_roundtrip_dir")),
        _path_from_text(ack_inputs.get("dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _explicit_or_inferred(explicit: str | Path | None, inferred: Path | None, use_inputs: bool) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    if not use_inputs:
        return None
    return inferred


def _child_path(parent: Path | None, child: str) -> Path | None:
    if parent is None:
        return None
    return parent / child


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


def _adapter_receipt_proof_status(proof: dict[str, Any]) -> dict[str, Any]:
    records = [
        _mapping(item)
        for item in _list(proof.get("receipts"))
        if _truthy(_mapping(item).get("adapter_receipt_required"))
    ]
    required_count = int(_number(proof.get("required_count")))
    valid_count = int(_number(proof.get("valid_count")))
    receipt_fingerprint_match_count = sum(
        _proof_file_matches(
            _clean(record.get("adapter_receipt_path")),
            _clean(record.get("adapter_receipt_current_sha256"))
            or _clean(record.get("adapter_receipt_ingest_sha256")),
        )
        for record in records
    )
    capture_fingerprint_match_count = sum(
        _proof_file_matches(
            _clean(record.get("capture_path")),
            _clean(record.get("capture_sha256")),
        )
        for record in records
    )
    ready = bool(
        _truthy(proof.get("ready"))
        and required_count > 0
        and len(records) == required_count
        and valid_count == required_count
        and receipt_fingerprint_match_count == required_count
        and capture_fingerprint_match_count == required_count
    )
    return {
        "ready": ready,
        "required_count": required_count,
        "valid_count": valid_count,
        "receipt_fingerprint_match_count": int(receipt_fingerprint_match_count),
        "capture_fingerprint_match_count": int(capture_fingerprint_match_count),
    }


def _adapter_receipt_proof_paths(
    proof: dict[str, Any],
) -> tuple[list[Path], list[Path]]:
    receipt_paths: list[Path] = []
    capture_paths: list[Path] = []
    for item in _list(proof.get("receipts")):
        record = _mapping(item)
        if not _truthy(record.get("adapter_receipt_required")):
            continue
        receipt_path = _path_from_text(_clean(record.get("adapter_receipt_path")))
        if (
            receipt_path is not None
            and receipt_path.exists()
            and receipt_path.is_file()
            and receipt_path not in receipt_paths
        ):
            receipt_paths.append(receipt_path)
        capture_path = _path_from_text(_clean(record.get("capture_path")))
        if (
            capture_path is not None
            and capture_path.exists()
            and capture_path.is_file()
            and capture_path not in capture_paths
        ):
            capture_paths.append(capture_path)
    return receipt_paths, capture_paths


def _proof_file_matches(path_text: str, expected_sha256: str) -> bool:
    path = _path_from_text(path_text)
    return bool(
        path is not None
        and path.exists()
        and path.is_file()
        and expected_sha256
        and _file_sha256(path) == expected_sha256
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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


def _adapter_execution_contract(*configs: dict[str, Any]) -> dict[str, Any]:
    for config in configs:
        bundle = _mapping(config.get("capture_bundle"))
        contract = _mapping(config.get("adapter_execution_contract")) or _mapping(
            bundle.get("adapter_execution_contract")
        )
        if contract:
            return contract
    return {}


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


def _dispatch_roundtrip_adapter_contract_carried(dispatch_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(dispatch_summary, "dispatch_roundtrip_adapter_contract_provider"))
        and bool(_first_text(dispatch_summary, "dispatch_roundtrip_adapter_contract_transport"))
        and bool(_first_text(dispatch_summary, "dispatch_roundtrip_adapter_contract_market"))
        and bool(_first_text(dispatch_summary, "dispatch_roundtrip_adapter_contract_exchange"))
        and not _first_bool(dispatch_summary, "dispatch_roundtrip_adapter_contract_values_stored")
    )


def _dispatch_roundtrip_adapter_contract_metadata_text(dispatch_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_adapter_contract_provider')}|"
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_adapter_contract_transport')}|"
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_adapter_contract_market')}|"
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_adapter_contract_exchange')}"
    )


def _dispatch_roundtrip_provider_profile_carried(dispatch_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(dispatch_summary, "dispatch_roundtrip_provider_profile_sha256"))
        and bool(_first_text(dispatch_summary, "dispatch_roundtrip_provider_profile_adapter"))
        and bool(_first_text(dispatch_summary, "dispatch_roundtrip_provider_profile_transports"))
    )


def _dispatch_roundtrip_provider_profile_metadata_text(dispatch_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_provider_profile_sha256')}|"
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_provider_profile_adapter')}|"
        f"{_first_text(dispatch_summary, 'dispatch_roundtrip_provider_profile_transports')}"
    )


def _dispatch_roundtrip_provider_profile_matches_session(
    provider_summary: pd.DataFrame,
    dispatch_summary: pd.DataFrame,
) -> bool:
    if _first_value_present(dispatch_summary, "dispatch_roundtrip_provider_profile_matches_runtime_session"):
        return _first_bool(dispatch_summary, "dispatch_roundtrip_provider_profile_matches_runtime_session")
    return (
        _provider_profile_carried(provider_summary)
        and _dispatch_roundtrip_provider_profile_carried(dispatch_summary)
        and _provider_profile_metadata_text(provider_summary)
        == _dispatch_roundtrip_provider_profile_metadata_text(dispatch_summary)
    )


def _first_text_with_fallback(frame: pd.DataFrame | None, column: str, fallback_column: str) -> str:
    if _first_value_present(frame, column):
        return _first_text(frame, column)
    return _first_text(frame, fallback_column)


def _first_bool_with_fallback(frame: pd.DataFrame | None, column: str, fallback_column: str) -> bool:
    if _first_value_present(frame, column):
        return _first_bool(frame, column)
    return _first_bool(frame, fallback_column)


def _first_number_with_fallback(frame: pd.DataFrame | None, column: str, fallback_column: str) -> float:
    fallback = _first_number(frame, fallback_column)
    if not _first_value_present(frame, column):
        return fallback
    return _first_number(frame, column)


def _first_number_with_unprovided_roundtrip_fallback(
    frame: pd.DataFrame | None,
    column: str,
    fallback_column: str,
    provided_column: str,
) -> float:
    fallback = _first_number(frame, fallback_column)
    if fallback and not _first_bool(frame, provided_column):
        return fallback
    return _first_number_with_fallback(frame, column, fallback_column)


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
    return _value_present(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str, fallback: float = 0.0) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return float(fallback)
    value = pd.to_numeric(frame.iloc[0][column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _identity_key(value: object) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _value_present(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return bool(value.strip())
    return True


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
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed", "continue", "enabled"}


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
