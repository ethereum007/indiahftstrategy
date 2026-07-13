from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker_readiness import BrokerReadinessReport, BrokerReadinessThresholds, write_broker_readiness_report
from reports.manifest import write_experiment_manifest
from reports.provider_lineage_selection import (
    provider_lineage_selection_contract_from_config,
    provider_lineage_selection_contract_from_manifest,
    provider_lineage_selection_contract_from_summary,
    provider_lineage_selection_contract_valid,
    provider_lineage_selection_contracts_match,
)


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_broker_readiness"

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
class ProviderMarketDataImbalanceBrokerReadinessConfig:
    require_provider_runtime_session_ready: bool = True
    require_broker_readiness_ready: bool = True
    use_provider_runtime_session_inputs: bool = True
    adapter: str = ""
    expected_market: str = ""
    expected_vendor_data_kind: str = "ticks"
    require_reviewed_schema: bool = False
    require_schema_audit: bool = False
    require_order_export: bool = True
    require_mapping_draft: bool = False
    require_mapped_orders: bool = False
    require_upload_pack: bool = True
    require_halt_export: bool = False
    require_reconciliation: bool = False
    require_runtime_session: bool = True
    require_resume_gate: bool = False
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    require_adapter_match: bool = True


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerReadinessReport:
    broker_readiness: BrokerReadinessReport | None
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


def write_provider_market_data_imbalance_broker_readiness(
    provider_runtime_session_dir: str | Path,
    output_dir: str | Path,
    *,
    schema_audit_dir: str | Path | None = None,
    order_export_dir: str | Path | None = None,
    mapping_draft_dir: str | Path | None = None,
    mapped_orders_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    halt_export_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    resume_dir: str | Path | None = None,
    dispatch_roundtrip_dir: str | Path | None = None,
    vendor_market_data_batch_dir: str | Path | None = None,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerReadinessReport:
    config = config or ProviderMarketDataImbalanceBrokerReadinessConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    session_root = Path(provider_runtime_session_dir)
    session_summary, session_summary_error = _read_csv(
        session_root / "provider_market_data_imbalance_runtime_session_summary.csv"
    )
    session_config, session_config_error = _read_json(
        session_root / "provider_market_data_imbalance_runtime_session_config.json"
    )
    session_manifest, session_manifest_error = _read_json(
        session_root / "manifest.json"
    )
    runtime_inputs = _runtime_inputs(session_config)
    generic_runtime_session_dir = _first_existing_path(
        _path_from_text(_first_text(session_summary, "runtime_session_dir")),
        _path_from_text((session_config.get("runtime_session", {}) or {}).get("output_dir")),
    )
    resolved_order_export_dir = _explicit_or_inferred(order_export_dir, runtime_inputs, "export_dir", config)
    resolved_upload_pack_dir = _explicit_or_inferred(upload_pack_dir, runtime_inputs, "upload_pack_dir", config)
    resolved_reconciliation_dir = _explicit_or_inferred(reconciliation_dir, runtime_inputs, "reconciliation_dir", config)
    resolved_schema_audit_dir = Path(schema_audit_dir) if schema_audit_dir is not None else None
    resolved_mapping_draft_dir = Path(mapping_draft_dir) if mapping_draft_dir is not None else None
    resolved_mapped_orders_dir = Path(mapped_orders_dir) if mapped_orders_dir is not None else None
    resolved_halt_export_dir = Path(halt_export_dir) if halt_export_dir is not None else None
    resolved_resume_dir = Path(resume_dir) if resume_dir is not None else None
    provider_dispatch_roundtrip_dir = Path(dispatch_roundtrip_dir) if dispatch_roundtrip_dir is not None else None
    resolved_dispatch_roundtrip_dir = _resolve_dispatch_roundtrip_dir(provider_dispatch_roundtrip_dir)
    (
        provider_roundtrip_summary,
        provider_roundtrip_config,
        provider_roundtrip_manifest,
        provider_roundtrip_wrapper_provided,
        provider_roundtrip_summary_error,
        provider_roundtrip_config_error,
        provider_roundtrip_manifest_error,
    ) = _read_provider_dispatch_roundtrip_artifacts(provider_dispatch_roundtrip_dir)
    upstream_provider_dispatch_roundtrip_dir, upstream_dispatch_roundtrip_dir = (
        _inferred_upstream_dispatch_roundtrip_dirs(provider_roundtrip_summary, provider_roundtrip_config)
    )
    resolved_vendor_market_data_batch_dir = Path(vendor_market_data_batch_dir) if vendor_market_data_batch_dir is not None else None

    prechecks = _prechecks(
        session_root,
        session_summary,
        session_summary_error,
        session_config,
        session_config_error,
        session_manifest,
        session_manifest_error,
        provider_roundtrip_summary,
        provider_roundtrip_summary_error,
        provider_roundtrip_config,
        provider_roundtrip_config_error,
        provider_roundtrip_manifest,
        provider_roundtrip_manifest_error,
        provider_roundtrip_wrapper_provided,
        generic_runtime_session_dir,
        resolved_order_export_dir,
        resolved_upload_pack_dir,
        config,
    )
    broker: BrokerReadinessReport | None = None
    broker_error = ""
    broker_dir = out / "broker_readiness"
    if bool(prechecks["passed"].all()):
        try:
            broker = write_broker_readiness_report(
                output_dir=broker_dir,
                schema_audit_dir=resolved_schema_audit_dir,
                order_export_dir=resolved_order_export_dir,
                mapping_draft_dir=resolved_mapping_draft_dir,
                mapped_orders_dir=resolved_mapped_orders_dir,
                upload_pack_dir=resolved_upload_pack_dir,
                halt_export_dir=resolved_halt_export_dir,
                reconciliation_dir=resolved_reconciliation_dir,
                runtime_session_dir=generic_runtime_session_dir,
                resume_dir=resolved_resume_dir,
                dispatch_roundtrip_dir=resolved_dispatch_roundtrip_dir,
                vendor_market_data_batch_dir=resolved_vendor_market_data_batch_dir,
                thresholds=_thresholds(config, session_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            broker_error = str(exc)
    else:
        broker_error = "provider imbalance broker readiness prerequisites are not ready"

    checks = _checks(
        prechecks,
        broker,
        broker_error,
        session_summary,
        session_config,
        session_manifest,
        provider_roundtrip_summary,
        config,
    )
    summary = _summary(
        session_root,
        generic_runtime_session_dir,
        broker,
        checks,
        out,
        session_summary,
        session_config,
        session_manifest,
        provider_roundtrip_config,
        provider_roundtrip_manifest,
        provider_roundtrip_wrapper_provided,
        resolved_schema_audit_dir,
        resolved_order_export_dir,
        resolved_upload_pack_dir,
        provider_dispatch_roundtrip_dir,
        resolved_dispatch_roundtrip_dir,
        provider_roundtrip_summary,
        upstream_provider_dispatch_roundtrip_dir,
        upstream_dispatch_roundtrip_dir,
    )
    action_queue = _action_queue(summary.iloc[0], checks, broker)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        session_summary,
        session_config,
        session_manifest,
        provider_roundtrip_config,
        provider_roundtrip_manifest,
        provider_roundtrip_wrapper_provided,
        broker,
        checks,
        action_queue,
        config,
        {
            "schema_audit_dir": resolved_schema_audit_dir,
            "order_export_dir": resolved_order_export_dir,
            "mapping_draft_dir": resolved_mapping_draft_dir,
            "mapped_orders_dir": resolved_mapped_orders_dir,
            "upload_pack_dir": resolved_upload_pack_dir,
            "halt_export_dir": resolved_halt_export_dir,
            "reconciliation_dir": resolved_reconciliation_dir,
            "runtime_session_dir": generic_runtime_session_dir,
            "resume_dir": resolved_resume_dir,
            "provider_dispatch_roundtrip_dir": provider_dispatch_roundtrip_dir,
            "dispatch_roundtrip_dir": resolved_dispatch_roundtrip_dir,
            "upstream_provider_dispatch_roundtrip_dir": upstream_provider_dispatch_roundtrip_dir,
            "upstream_dispatch_roundtrip_dir": upstream_dispatch_roundtrip_dir,
            "vendor_market_data_batch_dir": resolved_vendor_market_data_batch_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_broker_readiness_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_broker_readiness_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_broker_readiness_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_broker_readiness_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_readiness_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_runtime_session_dir": session_root}
    for name, value in {
        "runtime_session": generic_runtime_session_dir,
        "schema_audit": resolved_schema_audit_dir,
        "order_export": resolved_order_export_dir,
        "mapping_draft": resolved_mapping_draft_dir,
        "mapped_orders": resolved_mapped_orders_dir,
        "upload_pack": resolved_upload_pack_dir,
        "halt_export": resolved_halt_export_dir,
        "reconciliation": resolved_reconciliation_dir,
        "resume_gate": resolved_resume_dir,
        "dispatch_roundtrip": resolved_dispatch_roundtrip_dir,
        "provider_dispatch_roundtrip": provider_dispatch_roundtrip_dir,
        "upstream_provider_dispatch_roundtrip": upstream_provider_dispatch_roundtrip_dir,
        "upstream_dispatch_roundtrip": upstream_dispatch_roundtrip_dir,
        "vendor_market_data_batch": resolved_vendor_market_data_batch_dir,
    }.items():
        if value is not None:
            inputs[name] = Path(value)
    if broker is not None and broker.output_dir is not None:
        inputs["broker_readiness"] = broker.output_dir
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
    receipt_paths, capture_paths = _adapter_receipt_proof_paths(
        _mapping(session_config.get("adapter_receipt_proof"))
    )
    if receipt_paths:
        inputs["adapter_receipts"] = receipt_paths
    if capture_paths:
        inputs["provider_captures"] = capture_paths
    roundtrip_receipt_paths, roundtrip_capture_paths = _adapter_receipt_proof_paths(
        _mapping(provider_roundtrip_config.get("adapter_receipt_proof"))
    )
    if roundtrip_receipt_paths:
        inputs["dispatch_roundtrip_adapter_receipts"] = roundtrip_receipt_paths
    if roundtrip_capture_paths:
        inputs["dispatch_roundtrip_provider_captures"] = roundtrip_capture_paths

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config), "broker_inputs": _jsonable(payload["broker_inputs"])},
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "broker_readiness_ready": bool(summary_row["broker_readiness_ready"]),
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
            "adapter_execution_contract": _mapping(payload.get("adapter_execution_contract")),
            "adapter_contract_provider_profile_sha256": str(summary_row["adapter_contract_provider_profile_sha256"]),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary_row["adapter_contract_provider_profile_matches_evidence"]
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
                "adapter_execution_contract": _mapping(
                    _mapping(payload.get("capture_bundle")).get("adapter_execution_contract")
                ),
                "adapter_receipt_proof": _mapping(
                    payload.get("adapter_receipt_proof")
                ),
                "metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
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
            "provider_lineage_selection_contract": provider_lineage_selection_contract_from_summary(
                summary_row
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
    return ProviderMarketDataImbalanceBrokerReadinessReport(broker, checks, summary, action_queue, payload, out)


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
    session_root: Path,
    session_summary: pd.DataFrame,
    session_summary_error: str,
    session_config: dict[str, Any],
    session_config_error: str,
    session_manifest: dict[str, Any],
    session_manifest_error: str,
    provider_roundtrip_summary: pd.DataFrame,
    provider_roundtrip_summary_error: str,
    provider_roundtrip_config: dict[str, Any],
    provider_roundtrip_config_error: str,
    provider_roundtrip_manifest: dict[str, Any],
    provider_roundtrip_manifest_error: str,
    provider_roundtrip_wrapper_provided: bool,
    generic_runtime_session_dir: Path | None,
    order_export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
) -> pd.DataFrame:
    bundle_provided = _first_bool(session_summary, "capture_bundle_provided")
    config_receipt_proof = _mapping(session_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(session_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_proofs_match = bool(
        config_receipt_proof
        and manifest_receipt_proof
        and config_receipt_proof == manifest_receipt_proof
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    roundtrip_bundle_provided = _roundtrip_bool(
        provider_roundtrip_summary,
        "capture_bundle_provided",
    )
    roundtrip_config_receipt_proof = _mapping(
        provider_roundtrip_config.get("adapter_receipt_proof")
    )
    roundtrip_manifest_receipt_proof = _mapping(
        _mapping(provider_roundtrip_manifest.get("extra")).get(
            "adapter_receipt_proof"
        )
    )
    roundtrip_receipt_proofs_match = bool(
        roundtrip_config_receipt_proof
        and roundtrip_manifest_receipt_proof
        and roundtrip_config_receipt_proof == roundtrip_manifest_receipt_proof
    )
    roundtrip_receipt_proof_matches_session = bool(
        roundtrip_config_receipt_proof
        and config_receipt_proof
        and roundtrip_config_receipt_proof == config_receipt_proof
    )
    roundtrip_receipt_status = _adapter_receipt_proof_status(
        roundtrip_config_receipt_proof
    )
    roundtrip_receipt_gate_active = bool(
        provider_roundtrip_wrapper_provided and roundtrip_bundle_provided
    )
    return pd.DataFrame(
        [
            _check(
                "provider_runtime_session_dir_exists",
                str(session_root),
                "exists",
                True,
                session_root.exists(),
                "provider imbalance runtime session directory is required",
            ),
            _check(
                "provider_runtime_session_summary_readable",
                session_summary_error or "ok",
                "is",
                "ok",
                not session_summary_error,
                session_summary_error or "provider imbalance runtime session summary could not be read",
            ),
            _check(
                "provider_runtime_session_config_readable",
                session_config_error or "ok",
                "is",
                "ok",
                not session_config_error,
                session_config_error or "provider imbalance runtime session config could not be read",
            ),
            _check(
                "provider_runtime_session_manifest_readable",
                session_manifest_error or "ok",
                "is",
                "ok",
                not session_manifest_error,
                session_manifest_error or "provider imbalance runtime session manifest could not be read",
            ),
            _check(
                "provider_runtime_session_manifest_type",
                _clean(session_manifest.get("run_type")),
                "is",
                "provider_market_data_imbalance_runtime_session",
                _clean(session_manifest.get("run_type"))
                == "provider_market_data_imbalance_runtime_session",
                "provider imbalance runtime session manifest run_type is not expected",
            ),
            _check(
                "provider_runtime_session_ready",
                _first_bool(session_summary, "ready"),
                "is",
                True,
                _first_bool(session_summary, "ready") or not config.require_provider_runtime_session_ready,
                "provider imbalance runtime session is not ready",
            ),
            _check(
                "provider_runtime_session_adapter_receipt_proof_carried",
                bool(config_receipt_proof),
                "is",
                True,
                bool(config_receipt_proof)
                and _truthy(config_receipt_proof.get("ready"))
                if bundle_provided
                else True,
                "provider imbalance runtime session is missing ready adapter receipt proof",
            ),
            _check(
                "provider_runtime_session_adapter_receipt_proof_matches_manifest",
                receipt_proofs_match,
                "is",
                True,
                receipt_proofs_match if bundle_provided else True,
                "adapter receipt proof differs between runtime session config and manifest",
            ),
            _check(
                "provider_runtime_session_adapter_receipts_valid",
                receipt_status["valid_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["valid_count"] == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider imbalance runtime session did not preserve valid required adapter receipts",
            ),
            _check(
                "provider_runtime_session_adapter_receipt_fingerprints_current",
                receipt_status["receipt_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["receipt_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "adapter receipt files changed after provider runtime session monitoring",
            ),
            _check(
                "provider_runtime_session_capture_fingerprints_current",
                receipt_status["capture_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["capture_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider capture files changed after provider runtime session monitoring",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_summary_readable",
                provider_roundtrip_summary_error or "ok",
                "is",
                "ok",
                not provider_roundtrip_summary_error
                if provider_roundtrip_wrapper_provided
                else True,
                provider_roundtrip_summary_error
                or "provider broker-dispatch round-trip summary could not be read",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_config_readable",
                provider_roundtrip_config_error or "ok",
                "is",
                "ok",
                not provider_roundtrip_config_error
                if provider_roundtrip_wrapper_provided
                else True,
                provider_roundtrip_config_error
                or "provider broker-dispatch round-trip config could not be read",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_manifest_readable",
                provider_roundtrip_manifest_error or "ok",
                "is",
                "ok",
                not provider_roundtrip_manifest_error
                if provider_roundtrip_wrapper_provided
                else True,
                provider_roundtrip_manifest_error
                or "provider broker-dispatch round-trip manifest could not be read",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_manifest_type",
                _clean(provider_roundtrip_manifest.get("run_type")),
                "is",
                "provider_market_data_imbalance_broker_dispatch_roundtrip",
                _clean(provider_roundtrip_manifest.get("run_type"))
                == "provider_market_data_imbalance_broker_dispatch_roundtrip"
                if provider_roundtrip_wrapper_provided
                else True,
                "provider broker-dispatch round-trip manifest run_type is not expected",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_adapter_receipt_proof_carried",
                bool(roundtrip_config_receipt_proof),
                "is",
                True,
                bool(roundtrip_config_receipt_proof)
                and _truthy(roundtrip_config_receipt_proof.get("ready"))
                if roundtrip_receipt_gate_active
                else True,
                "provider broker-dispatch round-trip is missing ready adapter receipt proof",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_adapter_receipt_proof_matches_manifest",
                roundtrip_receipt_proofs_match,
                "is",
                True,
                roundtrip_receipt_proofs_match
                if roundtrip_receipt_gate_active
                else True,
                "adapter receipt proof differs between broker-dispatch round-trip config and manifest",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session",
                roundtrip_receipt_proof_matches_session,
                "is",
                True,
                roundtrip_receipt_proof_matches_session
                if roundtrip_receipt_gate_active
                else True,
                "broker-dispatch round-trip adapter receipt proof differs from runtime session proof",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_adapter_receipts_valid",
                roundtrip_receipt_status["valid_count"],
                "==",
                roundtrip_receipt_status["required_count"],
                roundtrip_receipt_status["valid_count"]
                == roundtrip_receipt_status["required_count"]
                if roundtrip_receipt_gate_active
                else True,
                "provider broker-dispatch round-trip did not preserve valid required adapter receipts",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_adapter_receipt_fingerprints_current",
                roundtrip_receipt_status["receipt_fingerprint_match_count"],
                "==",
                roundtrip_receipt_status["required_count"],
                roundtrip_receipt_status["receipt_fingerprint_match_count"]
                == roundtrip_receipt_status["required_count"]
                if roundtrip_receipt_gate_active
                else True,
                "adapter receipt files changed after provider broker-dispatch round-trip review",
            ),
            _check(
                "provider_broker_dispatch_roundtrip_capture_fingerprints_current",
                roundtrip_receipt_status["capture_fingerprint_match_count"],
                "==",
                roundtrip_receipt_status["required_count"],
                roundtrip_receipt_status["capture_fingerprint_match_count"]
                == roundtrip_receipt_status["required_count"]
                if roundtrip_receipt_gate_active
                else True,
                "provider capture files changed after provider broker-dispatch round-trip review",
            ),
            _check(
                "nested_runtime_session_summary_exists",
                _path_text(generic_runtime_session_dir),
                "exists",
                True,
                bool(generic_runtime_session_dir and (generic_runtime_session_dir / "runtime_session_summary.csv").exists()),
                "nested runtime_session_summary.csv is required for broker readiness",
            ),
            _check(
                "order_export_input_resolved",
                _path_text(_path_or_none(order_export_dir)),
                "exists",
                True,
                (not config.require_order_export) or bool(order_export_dir),
                "order export input is required for provider broker readiness",
            ),
            _check(
                "upload_pack_input_resolved",
                _path_text(_path_or_none(upload_pack_dir)),
                "exists",
                True,
                (not config.require_upload_pack) or bool(upload_pack_dir),
                "upload pack input is required for provider broker readiness",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    broker: BrokerReadinessReport | None,
    broker_error: str,
    session_summary: pd.DataFrame,
    session_config: dict[str, Any],
    session_manifest: dict[str, Any],
    provider_roundtrip_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    broker_summary = broker.summary if broker is not None else pd.DataFrame()
    rows.append(
        _check(
            "broker_readiness_runnable",
            broker_error or ("ran" if broker is not None else "not_run"),
            "is",
            "ran",
            broker is not None and not broker_error,
            broker_error or "generic broker readiness was not run",
        )
    )
    rows.extend(_dispatch_roundtrip_provenance_checks(session_summary, provider_roundtrip_summary))
    rows.append(
        _check(
            "broker_readiness_ready",
            bool(broker is not None and broker.ready),
            "is",
            True,
            bool(broker is not None and (broker.ready or not config.require_broker_readiness_ready)),
            _broker_failure_reason(broker) or "broker readiness is not ready",
        )
    )
    strategy = _first_text(session_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            _identity_key(strategy) == PROFILE,
            "provider broker readiness did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(session_summary, "market")
    broker_market = _first_text(broker_summary, "runtime_market")
    rows.append(
        _check(
            "market_identity_consistent",
            broker_market or expected_market,
            "is",
            expected_market or "present",
            bool(broker is not None)
            and bool(expected_market)
            and (not broker_market or _identity_key(broker_market) == _identity_key(expected_market)),
            "broker readiness market identity does not match provider runtime session",
        )
    )
    bundle_provided = _first_bool(session_summary, "capture_bundle_provided")
    provider_capture_command_count = int(_first_number(session_summary, "provider_capture_command_count"))
    bundle_provider_capture_command_count = int(
        _first_number(session_summary, "capture_bundle_provider_capture_command_count")
    )
    bundle_provider_capture_command_missing_count = int(
        _first_number(session_summary, "capture_bundle_provider_capture_command_missing_count")
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and _first_bool(session_summary, "capture_bundle_provider_capture_commands_match_session")
    )
    adapter_contract_carried = _adapter_contract_carried(session_summary)
    provider_profile_carried = _provider_profile_carried(session_summary)
    synthetic_dataset_count = int(_first_number(session_summary, "synthetic_dataset_count"))
    synthetic_sidecar_count = int(_first_number(session_summary, "synthetic_sidecar_count"))
    synthetic_sidecar_proof_required = synthetic_dataset_count > 0
    synthetic_sidecar_proof_ready = _first_bool(session_summary, "synthetic_sidecar_proof_ready")
    synthetic_sidecar_count_matches = synthetic_sidecar_count == synthetic_dataset_count
    route_sidecar_breach_pairs = int(
        _first_number(
            session_summary,
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
        )
    )
    route_sidecar_gate_active = (
        _first_bool(session_summary, "route_readiness_provided")
        or _first_bool(session_summary, "route_readiness_ops_launch_controls_present")
        or route_sidecar_breach_pairs > 0
    )
    route_lineage_contract = provider_lineage_selection_contract_from_summary(
        session_summary
    )
    route_lineage_contract_sha256 = str(route_lineage_contract["sha256"])
    route_lineage_gate_active = bool(
        route_sidecar_gate_active
        or any(bool(value) for value in route_lineage_contract.values())
    )
    route_lineage_contract_ready = provider_lineage_selection_contract_valid(
        route_lineage_contract
    )
    route_lineage_contract_matches_artifacts = provider_lineage_selection_contracts_match(
        route_lineage_contract,
        provider_lineage_selection_contract_from_config(session_config),
        provider_lineage_selection_contract_from_manifest(session_manifest),
    )
    rows.append(
        _check(
            "provider_runtime_session_provider_capture_commands_carried",
            bundle_provider_capture_command_count,
            "==",
            provider_capture_command_count,
            bundle_provider_capture_commands_carried if bundle_provided else True,
            "provider imbalance runtime session is missing capture-bundle provider command proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_provider_capture_commands_match_session",
            bundle_provider_capture_command_count,
            "matches",
            provider_capture_command_count,
            bundle_provider_capture_commands_match_session if bundle_provided else True,
            "provider imbalance runtime session command proof no longer matches the session packet",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_adapter_execution_contract_carried",
            _adapter_contract_metadata_text(session_summary),
            "is_not",
            "",
            adapter_contract_carried if bundle_provided else True,
            "provider imbalance runtime session is missing credential-safe adapter execution contract proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_adapter_execution_contract_matches_evidence",
            _adapter_contract_metadata_text(session_summary),
            "matches",
            "live evidence",
            _first_bool(session_summary, "adapter_contract_metadata_matches_evidence") if bundle_provided else True,
            "provider imbalance runtime session adapter execution contract no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_provider_profile_carried",
            _first_text(session_summary, "provider_profile_sha256"),
            "has",
            "provider profile",
            provider_profile_carried,
            "provider imbalance runtime session is missing provider-profile proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_provider_profile_matches_session",
            _first_text(session_summary, "provider_profile_sha256"),
            "matches",
            "live session",
            _first_bool(session_summary, "provider_profile_matches_session"),
            "provider imbalance runtime session provider-profile proof no longer matches the live session packet",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_provider_profile_matches_bundle",
            _first_text(session_summary, "capture_bundle_provider_profile_sha256"),
            "matches",
            _first_text(session_summary, "provider_profile_sha256"),
            _first_bool(session_summary, "provider_profile_matches_bundle") if bundle_provided else True,
            "provider imbalance runtime session provider-profile proof no longer matches the capture bundle",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_adapter_provider_profile_matches_evidence",
            _first_text(session_summary, "adapter_contract_provider_profile_sha256"),
            "==",
            _first_text(session_summary, "provider_profile_sha256"),
            _first_bool(session_summary, "adapter_contract_provider_profile_matches_evidence")
            if bundle_provided
            else True,
            "provider imbalance runtime session adapter contract provider-profile SHA no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_synthetic_sidecar_proof_carried",
            synthetic_sidecar_count,
            "==",
            synthetic_dataset_count,
            synthetic_sidecar_count_matches if synthetic_sidecar_proof_required else True,
            "provider imbalance runtime session synthetic folds are missing rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_synthetic_sidecar_proof_ready",
            synthetic_sidecar_proof_ready,
            "is",
            True,
            synthetic_sidecar_proof_ready if synthetic_sidecar_proof_required else True,
            "provider imbalance runtime session synthetic folds require ready rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_route_readiness_provider_sidecar_breach_pairs",
            route_sidecar_breach_pairs,
            "<=",
            0,
            route_sidecar_breach_pairs <= 0 if route_sidecar_gate_active else True,
            "provider imbalance runtime session carries breached route-readiness broker round-trip synthetic sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_route_readiness_provider_lineage_selection_contract",
            route_lineage_contract_sha256,
            "is",
            "three_stage_sha256_contract",
            route_lineage_contract_ready if route_lineage_gate_active else True,
            "provider runtime session does not carry a complete active-lineage selection contract",
        )
    )
    rows.append(
        _check(
            "provider_runtime_session_route_readiness_provider_lineage_selection_contract_matches_artifacts",
            "match" if route_lineage_contract_matches_artifacts else "mismatch",
            "is",
            "match",
            route_lineage_contract_matches_artifacts if route_lineage_gate_active else True,
            "provider runtime session lineage selection contract differs across summary, config, and manifest",
        )
    )
    return pd.DataFrame(rows)


def _dispatch_roundtrip_provenance_checks(
    session_summary: pd.DataFrame,
    provider_roundtrip_summary: pd.DataFrame,
) -> list[dict[str, Any]]:
    roundtrip_bundle_provided = _roundtrip_bool(provider_roundtrip_summary, "capture_bundle_provided")
    roundtrip_adapter_contract_carried = _roundtrip_adapter_contract_carried(provider_roundtrip_summary)
    roundtrip_provider_profile_carried = _roundtrip_provider_profile_carried(provider_roundtrip_summary)
    roundtrip_synthetic_dataset_count = int(_roundtrip_number(provider_roundtrip_summary, "synthetic_dataset_count"))
    roundtrip_synthetic_sidecar_count = int(_roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_count"))
    roundtrip_synthetic_sidecar_proof_required = roundtrip_synthetic_dataset_count > 0
    roundtrip_synthetic_sidecar_proof_ready = _roundtrip_bool(
        provider_roundtrip_summary,
        "synthetic_sidecar_proof_ready",
    )
    roundtrip_synthetic_sidecar_count_matches = (
        roundtrip_synthetic_sidecar_count == roundtrip_synthetic_dataset_count
    )
    roundtrip_route_sidecar_breach_pairs = int(
        _roundtrip_number(
            provider_roundtrip_summary,
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
        )
    )
    roundtrip_route_sidecar_gate_active = (
        _roundtrip_bool(provider_roundtrip_summary, "route_readiness_provided")
        or _roundtrip_bool(provider_roundtrip_summary, "route_readiness_ops_launch_controls_present")
        or roundtrip_route_sidecar_breach_pairs > 0
    )
    return [
        _provenance_check(
            "dispatch_roundtrip_capture_bundle_consistent",
            _first_text(session_summary, "capture_bundle_path"),
            _roundtrip_text(provider_roundtrip_summary, "capture_bundle_path"),
            "dispatch round-trip capture bundle does not match provider runtime session",
        ),
        _provenance_check(
            "dispatch_roundtrip_capture_env_template_consistent",
            _first_text(session_summary, "capture_env_template_path"),
            _roundtrip_text(provider_roundtrip_summary, "capture_env_template_path"),
            "dispatch round-trip capture env template does not match provider runtime session",
        ),
        _provenance_check(
            "dispatch_roundtrip_adapter_handoff_consistent",
            _first_text(session_summary, "adapter_handoff_path"),
            _roundtrip_text(provider_roundtrip_summary, "adapter_handoff_path"),
            "dispatch round-trip adapter handoff does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_exchange_consistent",
            _first_text(session_summary, "exchange"),
            _roundtrip_text(provider_roundtrip_summary, "exchange"),
            "dispatch round-trip exchange does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_source_session_consistent",
            _session_contract_text(session_summary, "source_session"),
            _roundtrip_session_contract_text(provider_roundtrip_summary, "source_session"),
            "dispatch round-trip source session does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_market_session_consistent",
            _session_contract_text(session_summary, "market_session"),
            _roundtrip_session_contract_text(provider_roundtrip_summary, "market_session"),
            "dispatch round-trip market session does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_capture_bundle_exchange_consistent",
            _first_text(session_summary, "capture_bundle_exchange"),
            _roundtrip_text(provider_roundtrip_summary, "capture_bundle_exchange"),
            "dispatch round-trip capture bundle exchange does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_capture_bundle_source_session_consistent",
            _session_contract_text(session_summary, "capture_bundle_source_session"),
            _roundtrip_session_contract_text(provider_roundtrip_summary, "capture_bundle_source_session"),
            "dispatch round-trip capture bundle source session does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_capture_bundle_market_session_consistent",
            _session_contract_text(session_summary, "capture_bundle_market_session"),
            _roundtrip_session_contract_text(provider_roundtrip_summary, "capture_bundle_market_session"),
            "dispatch round-trip capture bundle market session does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_provider_capture_commands_consistent",
            _provider_capture_command_proof_text(session_summary),
            _roundtrip_provider_capture_command_proof_text(provider_roundtrip_summary),
            "dispatch round-trip provider capture-command proof does not match provider runtime session",
        ),
        _check(
            "dispatch_roundtrip_adapter_execution_contract_carried",
            _roundtrip_adapter_contract_metadata_text(provider_roundtrip_summary),
            "is_not",
            "",
            roundtrip_adapter_contract_carried if roundtrip_bundle_provided else True,
            "dispatch round-trip is missing credential-safe adapter execution contract proof",
        ),
        _check(
            "dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            _roundtrip_adapter_contract_metadata_text(provider_roundtrip_summary),
            "matches",
            "live evidence",
            _roundtrip_bool(provider_roundtrip_summary, "adapter_contract_metadata_matches_evidence")
            if roundtrip_bundle_provided
            else True,
            "dispatch round-trip adapter execution contract no longer matches live evidence",
        ),
        _check(
            "dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            _roundtrip_adapter_contract_metadata_text(provider_roundtrip_summary),
            "matches",
            _adapter_contract_metadata_text(session_summary),
            _roundtrip_adapter_contract_matches_session(session_summary, provider_roundtrip_summary)
            if roundtrip_bundle_provided
            else True,
            "dispatch round-trip adapter execution contract does not match provider runtime session",
        ),
        _check(
            "dispatch_roundtrip_provider_profile_carried",
            _roundtrip_text(provider_roundtrip_summary, "provider_profile_sha256"),
            "has",
            "provider profile",
            roundtrip_provider_profile_carried if roundtrip_bundle_provided else True,
            "dispatch round-trip is missing provider-profile proof",
        ),
        _check(
            "dispatch_roundtrip_provider_profile_matches_session",
            _roundtrip_text(provider_roundtrip_summary, "provider_profile_sha256"),
            "matches",
            "live session",
            _roundtrip_bool(provider_roundtrip_summary, "provider_profile_matches_session")
            if roundtrip_bundle_provided
            else True,
            "dispatch round-trip provider-profile proof no longer matches the live session packet",
        ),
        _check(
            "dispatch_roundtrip_provider_profile_matches_bundle",
            _roundtrip_text(provider_roundtrip_summary, "capture_bundle_provider_profile_sha256"),
            "matches",
            _roundtrip_text(provider_roundtrip_summary, "provider_profile_sha256"),
            _roundtrip_bool(provider_roundtrip_summary, "provider_profile_matches_bundle")
            if roundtrip_bundle_provided
            else True,
            "dispatch round-trip provider-profile proof no longer matches the capture bundle",
        ),
        _check(
            "dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            _roundtrip_text(provider_roundtrip_summary, "adapter_contract_provider_profile_sha256"),
            "==",
            _roundtrip_text(provider_roundtrip_summary, "provider_profile_sha256"),
            _roundtrip_bool(provider_roundtrip_summary, "adapter_contract_provider_profile_matches_evidence")
            if roundtrip_bundle_provided
            else True,
            "dispatch round-trip adapter contract provider-profile SHA no longer matches live evidence",
        ),
        _check(
            "dispatch_roundtrip_provider_profile_matches_runtime_session",
            _roundtrip_provider_profile_metadata_text(provider_roundtrip_summary),
            "matches",
            _provider_profile_metadata_text(session_summary),
            _roundtrip_provider_profile_matches_session(session_summary, provider_roundtrip_summary)
            if roundtrip_bundle_provided
            else True,
            "dispatch round-trip provider-profile proof does not match provider runtime session",
        ),
        _check(
            "dispatch_roundtrip_synthetic_sidecar_proof_carried",
            roundtrip_synthetic_sidecar_count,
            "==",
            roundtrip_synthetic_dataset_count,
            (
                roundtrip_synthetic_sidecar_count_matches
                if roundtrip_synthetic_sidecar_proof_required
                else True
            ),
            "dispatch round-trip synthetic provider folds require carried rehearsal sidecar proof",
        ),
        _check(
            "dispatch_roundtrip_synthetic_sidecar_proof_ready",
            roundtrip_synthetic_sidecar_proof_ready,
            "is",
            True,
            (
                roundtrip_synthetic_sidecar_proof_ready
                if roundtrip_synthetic_sidecar_proof_required
                else True
            ),
            "dispatch round-trip synthetic provider folds require ready rehearsal sidecar proof",
        ),
        _check(
            "dispatch_roundtrip_route_readiness_provider_sidecar_breach_pairs",
            roundtrip_route_sidecar_breach_pairs,
            "<=",
            0,
            (
                roundtrip_route_sidecar_breach_pairs <= 0
                if roundtrip_route_sidecar_gate_active
                else True
            ),
            "dispatch round-trip carries breached route-readiness broker round-trip synthetic sidecar proof",
        ),
        _provenance_check(
            "dispatch_roundtrip_source_credential_env_template_consistent",
            _first_text(session_summary, "source_credential_env_template_path"),
            _roundtrip_text(provider_roundtrip_summary, "source_credential_env_template_path"),
            "dispatch round-trip source credential env template does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_source_credential_env_template_sha256_consistent",
            _first_text(session_summary, "source_credential_env_template_sha256"),
            _roundtrip_text(provider_roundtrip_summary, "source_credential_env_template_sha256"),
            "dispatch round-trip source credential env template digest does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_live_fetch_contract_next_gate_consistent",
            _first_text(session_summary, "source_live_fetch_contract_next_gate"),
            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_next_gate"),
            "dispatch round-trip live fetch contract next gate does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_live_fetch_contract_command_template_consistent",
            _first_text(session_summary, "source_live_fetch_contract_command_template"),
            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_command_template"),
            "dispatch round-trip live fetch contract command template does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_live_fetch_contract_exchange_consistent",
            _first_text(session_summary, "source_live_fetch_contract_exchange"),
            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_exchange"),
            "dispatch round-trip live fetch contract exchange does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_live_fetch_contract_market_consistent",
            _first_text(session_summary, "source_live_fetch_contract_market"),
            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_market"),
            "dispatch round-trip live fetch contract market does not match provider runtime session",
        ),
        _text_consistency_check(
            "dispatch_roundtrip_live_fetch_contract_session_consistent",
            _session_contract_text(session_summary, "source_live_fetch_contract_session"),
            _roundtrip_session_contract_text(provider_roundtrip_summary, "source_live_fetch_contract_session"),
            "dispatch round-trip live fetch contract session does not match provider runtime session",
        ),
    ]


def _session_contract_text(frame: pd.DataFrame, prefix: str) -> str:
    parts = [
        _first_text(frame, f"{prefix}_timezone"),
        _first_text(frame, f"{prefix}_open_local"),
        _first_text(frame, f"{prefix}_close_local"),
    ]
    return "|".join(parts) if any(parts) else ""


def _roundtrip_text(frame: pd.DataFrame, suffix: str) -> str:
    return _first_text(frame, f"dispatch_roundtrip_{suffix}", fallback_column=suffix)


def _roundtrip_session_contract_text(frame: pd.DataFrame, prefix: str) -> str:
    parts = [
        _first_text(frame, f"dispatch_roundtrip_{prefix}_timezone", fallback_column=f"{prefix}_timezone"),
        _first_text(frame, f"dispatch_roundtrip_{prefix}_open_local", fallback_column=f"{prefix}_open_local"),
        _first_text(frame, f"dispatch_roundtrip_{prefix}_close_local", fallback_column=f"{prefix}_close_local"),
    ]
    return "|".join(parts) if any(parts) else ""


def _provider_capture_command_proof_text(frame: pd.DataFrame) -> str:
    parts = [
        str(int(_first_number(frame, "provider_capture_command_count"))),
        _first_text(frame, "provider_capture_command_providers"),
        _first_text(frame, "provider_capture_command_transports"),
        str(int(_first_number(frame, "capture_bundle_provider_capture_command_count"))),
        str(int(_first_number(frame, "capture_bundle_provider_capture_command_missing_count"))),
        str(_first_bool(frame, "capture_bundle_provider_capture_commands_match_session")),
    ]
    return "|".join(parts) if any(part not in {"", "0", "False"} for part in parts) else ""


def _roundtrip_provider_capture_command_proof_text(frame: pd.DataFrame) -> str:
    parts = [
        str(int(_roundtrip_number(frame, "provider_capture_command_count"))),
        _roundtrip_text(frame, "provider_capture_command_providers"),
        _roundtrip_text(frame, "provider_capture_command_transports"),
        str(int(_roundtrip_number(frame, "capture_bundle_provider_capture_command_count"))),
        str(int(_roundtrip_number(frame, "capture_bundle_provider_capture_command_missing_count"))),
        str(_roundtrip_bool(frame, "capture_bundle_provider_capture_commands_match_session")),
    ]
    return "|".join(parts) if any(part not in {"", "0", "False"} for part in parts) else ""


def _provider_capture_command_proof_matches(
    session_summary: pd.DataFrame,
    provider_roundtrip_summary: pd.DataFrame,
) -> bool:
    return _text_matches(
        _provider_capture_command_proof_text(session_summary),
        _roundtrip_provider_capture_command_proof_text(provider_roundtrip_summary),
    )


def _roundtrip_bool(frame: pd.DataFrame, suffix: str) -> bool:
    return _first_bool(frame, f"dispatch_roundtrip_{suffix}", fallback_column=suffix)


def _roundtrip_number(frame: pd.DataFrame, suffix: str) -> float:
    prefixed = f"dispatch_roundtrip_{suffix}"
    if frame is not None and not frame.empty and prefixed in frame.columns:
        return _first_number(frame, prefixed)
    return _first_number(frame, suffix)


def _provenance_check(check: str, expected: str, actual: str, reason: str) -> dict[str, Any]:
    return _check(
        check,
        actual or "not_provided",
        "matches",
        expected or "runtime_session_provenance_or_empty",
        _provenance_matches(expected, actual),
        reason,
    )


def _text_consistency_check(check: str, expected: str, actual: str, reason: str) -> dict[str, Any]:
    return _check(
        check,
        actual or "not_provided",
        "matches",
        expected or "runtime_session_provenance_or_empty",
        _text_matches(expected, actual),
        reason,
    )


def _summary(
    session_root: Path,
    generic_runtime_session_dir: Path | None,
    broker: BrokerReadinessReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    session_summary: pd.DataFrame,
    session_config: dict[str, Any],
    session_manifest: dict[str, Any],
    provider_roundtrip_config: dict[str, Any],
    provider_roundtrip_manifest: dict[str, Any],
    provider_roundtrip_wrapper_provided: bool,
    schema_audit_dir: Path | None,
    order_export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
    provider_dispatch_roundtrip_dir: Path | None,
    dispatch_roundtrip_dir: Path | None,
    provider_roundtrip_summary: pd.DataFrame,
    upstream_provider_dispatch_roundtrip_dir: Path | None,
    upstream_dispatch_roundtrip_dir: Path | None,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    broker_summary = broker.summary if broker is not None else pd.DataFrame()
    config_receipt_proof = _mapping(session_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(session_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    roundtrip_config_receipt_proof = _mapping(
        provider_roundtrip_config.get("adapter_receipt_proof")
    )
    roundtrip_manifest_receipt_proof = _mapping(
        _mapping(provider_roundtrip_manifest.get("extra")).get(
            "adapter_receipt_proof"
        )
    )
    roundtrip_receipt_status = _adapter_receipt_proof_status(
        roundtrip_config_receipt_proof
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_runtime_session_ready": _first_bool(session_summary, "ready"),
                "broker_readiness_ready": bool(broker is not None and broker.ready),
                "provider_runtime_session_dir": str(session_root),
                "runtime_session_dir": _path_text(generic_runtime_session_dir),
                "broker_readiness_dir": "" if broker is None else str(broker.output_dir or ""),
                "exchange": _first_text(session_summary, "exchange"),
                "source_session_timezone": _first_text(session_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(session_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(session_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(session_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(session_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(session_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(session_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(session_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(session_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(session_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(session_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    session_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    session_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    session_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    session_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    session_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    session_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    session_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    session_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                ),
                "capture_env_template_path": _first_text(session_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(session_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(session_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(session_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(session_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(session_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(session_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(session_summary, "adapter_handoff_sha256"),
                "provider_runtime_session_manifest_run_type": _clean(
                    session_manifest.get("run_type")
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
                    provider_roundtrip_wrapper_provided
                ),
                "provider_broker_dispatch_roundtrip_manifest_run_type": _clean(
                    provider_roundtrip_manifest.get("run_type")
                ),
                "dispatch_roundtrip_adapter_receipt_proof_ready": bool(
                    roundtrip_receipt_status["ready"]
                ),
                "dispatch_roundtrip_adapter_receipt_proof_matches_manifest": bool(
                    roundtrip_config_receipt_proof
                    and roundtrip_manifest_receipt_proof
                    and roundtrip_config_receipt_proof
                    == roundtrip_manifest_receipt_proof
                ),
                "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session": bool(
                    roundtrip_config_receipt_proof
                    and config_receipt_proof
                    and roundtrip_config_receipt_proof == config_receipt_proof
                ),
                "dispatch_roundtrip_adapter_receipts_required": _truthy(
                    roundtrip_config_receipt_proof.get("required")
                ),
                "dispatch_roundtrip_adapter_receipt_required_count": int(
                    roundtrip_receipt_status["required_count"]
                ),
                "dispatch_roundtrip_adapter_receipt_valid_count": int(
                    roundtrip_receipt_status["valid_count"]
                ),
                "dispatch_roundtrip_adapter_receipt_fingerprint_match_count": int(
                    roundtrip_receipt_status["receipt_fingerprint_match_count"]
                ),
                "dispatch_roundtrip_capture_fingerprint_match_count": int(
                    roundtrip_receipt_status["capture_fingerprint_match_count"]
                ),
                "source_credential_env_template_path": _first_text(
                    session_summary,
                    "source_credential_env_template_path",
                ),
                "source_credential_env_template_exists": _first_bool(
                    session_summary,
                    "source_credential_env_template_exists",
                ),
                "source_credential_env_template_sha256": _first_text(
                    session_summary,
                    "source_credential_env_template_sha256",
                ),
                "source_live_fetch_contract_available": _first_bool(
                    session_summary,
                    "source_live_fetch_contract_available",
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    session_summary,
                    "source_live_fetch_contract_next_gate",
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    session_summary,
                    "source_live_fetch_contract_command_template",
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    session_summary,
                    "source_live_fetch_contract_exchange",
                ),
                "source_live_fetch_contract_market": _first_text(
                    session_summary,
                    "source_live_fetch_contract_market",
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    session_summary,
                    "source_live_fetch_contract_session_timezone",
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    session_summary,
                    "source_live_fetch_contract_session_open_local",
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    session_summary,
                    "source_live_fetch_contract_session_close_local",
                ),
                "adapter_contract_provider": _first_text(session_summary, "adapter_contract_provider"),
                "adapter_contract_transport": _first_text(session_summary, "adapter_contract_transport"),
                "adapter_contract_market": _first_text(session_summary, "adapter_contract_market"),
                "adapter_contract_exchange": _first_text(session_summary, "adapter_contract_exchange"),
                "adapter_contract_values_stored": _first_bool(session_summary, "adapter_contract_values_stored"),
                "adapter_contract_metadata_matches_evidence": _first_bool(
                    session_summary,
                    "adapter_contract_metadata_matches_evidence",
                ),
                "provider_profile_sha256": _first_text(session_summary, "provider_profile_sha256"),
                "provider_profile_adapter": _first_text(session_summary, "provider_profile_adapter"),
                "provider_profile_auth_required": _first_bool(session_summary, "provider_profile_auth_required"),
                "provider_profile_transports": _first_text(session_summary, "provider_profile_transports"),
                "provider_profile_capabilities": _first_text(session_summary, "provider_profile_capabilities"),
                "capture_bundle_provider_profile_sha256": _first_text(
                    session_summary,
                    "capture_bundle_provider_profile_sha256",
                ),
                "provider_profile_matches_session": _first_bool(
                    session_summary,
                    "provider_profile_matches_session",
                ),
                "provider_profile_matches_bundle": _first_bool(
                    session_summary,
                    "provider_profile_matches_bundle",
                )
                if _first_bool(session_summary, "capture_bundle_provided")
                else True,
                "adapter_contract_provider_profile_sha256": _first_text(
                    session_summary,
                    "adapter_contract_provider_profile_sha256",
                ),
                "adapter_contract_provider_profile_matches_evidence": _first_bool(
                    session_summary,
                    "adapter_contract_provider_profile_matches_evidence",
                ),
                "provider_capture_command_count": int(
                    _first_number(session_summary, "provider_capture_command_count")
                ),
                "provider_capture_command_providers": _first_text(
                    session_summary,
                    "provider_capture_command_providers",
                ),
                "provider_capture_command_transports": _first_text(
                    session_summary,
                    "provider_capture_command_transports",
                ),
                "capture_bundle_provider_capture_command_count": int(
                    _first_number(session_summary, "capture_bundle_provider_capture_command_count")
                ),
                "capture_bundle_provider_capture_command_missing_count": int(
                    _first_number(session_summary, "capture_bundle_provider_capture_command_missing_count")
                ),
                "capture_bundle_provider_capture_commands_match_session": _first_bool(
                    session_summary,
                    "capture_bundle_provider_capture_commands_match_session",
                )
                if _first_bool(session_summary, "capture_bundle_provided")
                else True,
                "synthetic_dataset_count": int(_first_number(session_summary, "synthetic_dataset_count")),
                "synthetic_sidecar_proof_ready": _first_bool(session_summary, "synthetic_sidecar_proof_ready"),
                "synthetic_sidecar_count": int(_first_number(session_summary, "synthetic_sidecar_count")),
                "synthetic_sidecar_readable_count": int(
                    _first_number(session_summary, "synthetic_sidecar_readable_count")
                ),
                "synthetic_sidecar_source_count": int(
                    _first_number(session_summary, "synthetic_sidecar_source_count")
                ),
                "synthetic_sidecar_adapter_command_hash_count": int(
                    _first_number(session_summary, "synthetic_sidecar_adapter_command_hash_count")
                ),
                "synthetic_sidecar_capture_env_template_match_count": int(
                    _first_number(session_summary, "synthetic_sidecar_capture_env_template_match_count")
                ),
                "synthetic_sidecar_adapter_handoff_match_count": int(
                    _first_number(session_summary, "synthetic_sidecar_adapter_handoff_match_count")
                ),
                "synthetic_sidecar_source_env_template_match_count": int(
                    _first_number(session_summary, "synthetic_sidecar_source_env_template_match_count")
                ),
            "synthetic_sidecar_live_fetch_contract_count": int(
                _first_number(session_summary, "synthetic_sidecar_live_fetch_contract_count")
            ),
            "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                _first_number(session_summary, "synthetic_sidecar_adapter_execution_contract_safe_count")
            ),
            "synthetic_sidecar_invariant_count": int(
                _first_number(session_summary, "synthetic_sidecar_invariant_count")
            ),
            "route_readiness_provided": _first_bool(session_summary, "route_readiness_provided"),
            "route_readiness_ops_launch_controls_present": _first_bool(
                session_summary,
                "route_readiness_ops_launch_controls_present",
            ),
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                _first_number(
                    session_summary,
                    "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                )
            ),
            "route_readiness_ops_provider_lineage_selected_run_count": int(
                _first_number(
                    session_summary,
                    "route_readiness_ops_provider_lineage_selected_run_count",
                )
            ),
            "route_readiness_ops_provider_lineage_selected_pair_count": int(
                _first_number(
                    session_summary,
                    "route_readiness_ops_provider_lineage_selected_pair_count",
                )
            ),
            "route_readiness_ops_provider_lineage_selected_pair_ids": _first_text(
                session_summary,
                "route_readiness_ops_provider_lineage_selected_pair_ids",
            ),
            "route_readiness_ops_provider_lineage_selected_run_dirs": _first_text(
                session_summary,
                "route_readiness_ops_provider_lineage_selected_run_dirs",
            ),
            "route_readiness_ops_provider_lineage_selection_contract_version": _first_text(
                session_summary,
                "route_readiness_ops_provider_lineage_selection_contract_version",
            ),
            "route_readiness_ops_provider_lineage_selection_contract_sha256": _first_text(
                session_summary,
                "route_readiness_ops_provider_lineage_selection_contract_sha256",
            ),
            "route_readiness_ops_provider_lineage_selection_artifact": _first_text(
                session_summary,
                "route_readiness_ops_provider_lineage_selection_artifact",
            ),
            "dispatch_roundtrip_route_readiness_provided": _roundtrip_bool(
                provider_roundtrip_summary,
                "route_readiness_provided",
            ),
            "dispatch_roundtrip_route_readiness_ops_launch_controls_present": _roundtrip_bool(
                provider_roundtrip_summary,
                "route_readiness_ops_launch_controls_present",
            ),
            "dispatch_roundtrip_route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                _roundtrip_number(
                    provider_roundtrip_summary,
                    "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                )
            ),
            "dispatch_roundtrip_synthetic_dataset_count": int(
                _roundtrip_number(provider_roundtrip_summary, "synthetic_dataset_count")
            ),
                "dispatch_roundtrip_synthetic_sidecar_proof_ready": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "synthetic_sidecar_proof_ready",
                ),
                "dispatch_roundtrip_synthetic_sidecar_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_readable_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_readable_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_source_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_source_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_adapter_command_hash_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count": int(
                    _roundtrip_number(
                        provider_roundtrip_summary,
                        "synthetic_sidecar_capture_env_template_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_adapter_handoff_match_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count": int(
                    _roundtrip_number(
                        provider_roundtrip_summary,
                        "synthetic_sidecar_source_env_template_match_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_live_fetch_contract_count")
                ),
                "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _roundtrip_number(
                        provider_roundtrip_summary,
                        "synthetic_sidecar_adapter_execution_contract_safe_count",
                    )
                ),
                "dispatch_roundtrip_synthetic_sidecar_invariant_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "synthetic_sidecar_invariant_count")
                ),
                "dispatch_roundtrip_provider_capture_command_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "provider_capture_command_count")
                ),
                "dispatch_roundtrip_provider_capture_command_providers": _roundtrip_text(
                    provider_roundtrip_summary,
                    "provider_capture_command_providers",
                ),
                "dispatch_roundtrip_provider_capture_command_transports": _roundtrip_text(
                    provider_roundtrip_summary,
                    "provider_capture_command_transports",
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_command_count": int(
                    _roundtrip_number(provider_roundtrip_summary, "capture_bundle_provider_capture_command_count")
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": int(
                    _roundtrip_number(
                        provider_roundtrip_summary,
                        "capture_bundle_provider_capture_command_missing_count",
                    )
                ),
                "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "capture_bundle_provider_capture_commands_match_session",
                )
                if _first_bool(provider_roundtrip_summary, "capture_bundle_provided")
                else True,
                "dispatch_roundtrip_provider_capture_commands_match_runtime_session": (
                    _provider_capture_command_proof_matches(session_summary, provider_roundtrip_summary)
                ),
                "dispatch_roundtrip_adapter_contract_provider": _roundtrip_text(
                    provider_roundtrip_summary,
                    "adapter_contract_provider",
                ),
                "dispatch_roundtrip_adapter_contract_transport": _roundtrip_text(
                    provider_roundtrip_summary,
                    "adapter_contract_transport",
                ),
                "dispatch_roundtrip_adapter_contract_market": _roundtrip_text(
                    provider_roundtrip_summary,
                    "adapter_contract_market",
                ),
                "dispatch_roundtrip_adapter_contract_exchange": _roundtrip_text(
                    provider_roundtrip_summary,
                    "adapter_contract_exchange",
                ),
                "dispatch_roundtrip_adapter_contract_values_stored": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "adapter_contract_values_stored",
                ),
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "adapter_contract_metadata_matches_evidence",
                ),
                "dispatch_roundtrip_adapter_contract_matches_runtime_session": (
                    _roundtrip_adapter_contract_matches_session(session_summary, provider_roundtrip_summary)
                )
                if _roundtrip_bool(provider_roundtrip_summary, "capture_bundle_provided")
                else True,
                "dispatch_roundtrip_provider_profile_sha256": _roundtrip_text(
                    provider_roundtrip_summary,
                    "provider_profile_sha256",
                ),
                "dispatch_roundtrip_provider_profile_adapter": _roundtrip_text(
                    provider_roundtrip_summary,
                    "provider_profile_adapter",
                ),
                "dispatch_roundtrip_provider_profile_auth_required": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "provider_profile_auth_required",
                ),
                "dispatch_roundtrip_provider_profile_transports": _roundtrip_text(
                    provider_roundtrip_summary,
                    "provider_profile_transports",
                ),
                "dispatch_roundtrip_provider_profile_capabilities": _roundtrip_text(
                    provider_roundtrip_summary,
                    "provider_profile_capabilities",
                ),
                "dispatch_roundtrip_capture_bundle_provider_profile_sha256": _roundtrip_text(
                    provider_roundtrip_summary,
                    "capture_bundle_provider_profile_sha256",
                ),
                "dispatch_roundtrip_provider_profile_matches_session": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "provider_profile_matches_session",
                )
                if _roundtrip_bool(provider_roundtrip_summary, "capture_bundle_provided")
                else True,
                "dispatch_roundtrip_provider_profile_matches_bundle": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "provider_profile_matches_bundle",
                )
                if _roundtrip_bool(provider_roundtrip_summary, "capture_bundle_provided")
                else True,
                "dispatch_roundtrip_adapter_contract_provider_profile_sha256": _roundtrip_text(
                    provider_roundtrip_summary,
                    "adapter_contract_provider_profile_sha256",
                ),
                "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence": _roundtrip_bool(
                    provider_roundtrip_summary,
                    "adapter_contract_provider_profile_matches_evidence",
                ),
                "dispatch_roundtrip_provider_profile_matches_runtime_session": (
                    _roundtrip_provider_profile_matches_session(session_summary, provider_roundtrip_summary)
                )
                if _roundtrip_bool(provider_roundtrip_summary, "capture_bundle_provided")
                else True,
                "dispatch_roundtrip_exchange": _roundtrip_text(provider_roundtrip_summary, "exchange"),
                "dispatch_roundtrip_source_session_timezone": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_session_timezone",
                    fallback_column="source_session_timezone",
                ),
                "dispatch_roundtrip_source_session_open_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_session_open_local",
                    fallback_column="source_session_open_local",
                ),
                "dispatch_roundtrip_source_session_close_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_session_close_local",
                    fallback_column="source_session_close_local",
                ),
                "dispatch_roundtrip_market_session_timezone": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_market_session_timezone",
                    fallback_column="market_session_timezone",
                ),
                "dispatch_roundtrip_market_session_open_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_market_session_open_local",
                    fallback_column="market_session_open_local",
                ),
                "dispatch_roundtrip_market_session_close_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_market_session_close_local",
                    fallback_column="market_session_close_local",
                ),
                "dispatch_roundtrip_exchange_matches_session": _text_matches(
                    _first_text(session_summary, "exchange"),
                    _roundtrip_text(provider_roundtrip_summary, "exchange"),
                ),
                "dispatch_roundtrip_source_session_matches_session": _text_matches(
                    _session_contract_text(session_summary, "source_session"),
                    _roundtrip_session_contract_text(provider_roundtrip_summary, "source_session"),
                ),
                "dispatch_roundtrip_market_session_matches_session": _text_matches(
                    _session_contract_text(session_summary, "market_session"),
                    _roundtrip_session_contract_text(provider_roundtrip_summary, "market_session"),
                ),
                "dispatch_roundtrip_source_credential_env_template_path": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_credential_env_template_path",
                    fallback_column="source_credential_env_template_path",
                ),
                "dispatch_roundtrip_source_credential_env_template_exists": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_credential_env_template_exists",
                    fallback_column="source_credential_env_template_exists",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_credential_env_template_sha256",
                    fallback_column="source_credential_env_template_sha256",
                ),
                "dispatch_roundtrip_source_credential_env_template_matches_session": _provenance_matches(
                    _first_text(session_summary, "source_credential_env_template_path"),
                    _roundtrip_text(provider_roundtrip_summary, "source_credential_env_template_path"),
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": _text_matches(
                    _first_text(session_summary, "source_credential_env_template_sha256"),
                    _roundtrip_text(provider_roundtrip_summary, "source_credential_env_template_sha256"),
                ),
                "dispatch_roundtrip_source_live_fetch_contract_available": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_available",
                    fallback_column="source_live_fetch_contract_available",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate",
                    fallback_column="source_live_fetch_contract_next_gate",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_command_template",
                    fallback_column="source_live_fetch_contract_command_template",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_exchange",
                    fallback_column="source_live_fetch_contract_exchange",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_market": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_market",
                    fallback_column="source_live_fetch_contract_market",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_timezone": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_timezone",
                    fallback_column="source_live_fetch_contract_session_timezone",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_open_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
                    fallback_column="source_live_fetch_contract_session_open_local",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_close_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_session_close_local",
                    fallback_column="source_live_fetch_contract_session_close_local",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": _text_matches(
                    _first_text(session_summary, "source_live_fetch_contract_next_gate"),
                    _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_next_gate"),
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": _text_matches(
                    _first_text(session_summary, "source_live_fetch_contract_command_template"),
                    _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_command_template"),
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session": _text_matches(
                    _first_text(session_summary, "source_live_fetch_contract_exchange"),
                    _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_exchange"),
                ),
                "dispatch_roundtrip_source_live_fetch_contract_market_matches_session": _text_matches(
                    _first_text(session_summary, "source_live_fetch_contract_market"),
                    _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_market"),
                ),
                "dispatch_roundtrip_source_live_fetch_contract_session_matches_session": _text_matches(
                    _session_contract_text(session_summary, "source_live_fetch_contract_session"),
                    _roundtrip_session_contract_text(provider_roundtrip_summary, "source_live_fetch_contract_session"),
                ),
                "dispatch_roundtrip_capture_bundle_path": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_path",
                    fallback_column="capture_bundle_path",
                ),
                "dispatch_roundtrip_capture_bundle_provided": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_provided",
                    fallback_column="capture_bundle_provided",
                ),
                "dispatch_roundtrip_capture_bundle_exists": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_exists",
                    fallback_column="capture_bundle_exists",
                ),
                "dispatch_roundtrip_capture_bundle_ready": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_ready",
                    fallback_column="capture_bundle_ready",
                ),
                "dispatch_roundtrip_capture_bundle_exchange": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_exchange",
                    fallback_column="capture_bundle_exchange",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_timezone": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_timezone",
                    fallback_column="capture_bundle_source_session_timezone",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_open_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_open_local",
                    fallback_column="capture_bundle_source_session_open_local",
                ),
                "dispatch_roundtrip_capture_bundle_source_session_close_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_source_session_close_local",
                    fallback_column="capture_bundle_source_session_close_local",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_timezone": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_timezone",
                    fallback_column="capture_bundle_market_session_timezone",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_open_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_open_local",
                    fallback_column="capture_bundle_market_session_open_local",
                ),
                "dispatch_roundtrip_capture_bundle_market_session_close_local": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_market_session_close_local",
                    fallback_column="capture_bundle_market_session_close_local",
                ),
                "dispatch_roundtrip_capture_bundle_metadata_matches_session": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_metadata_matches_session",
                    fallback_column="capture_bundle_metadata_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
                    fallback_column="capture_bundle_live_fetch_contract_metadata_matches_session",
                ),
                "dispatch_roundtrip_capture_bundle_matches_session": _provenance_matches(
                    _first_text(session_summary, "capture_bundle_path"),
                    _roundtrip_text(provider_roundtrip_summary, "capture_bundle_path"),
                ),
                "dispatch_roundtrip_capture_bundle_exchange_matches_session": _text_matches(
                    _first_text(session_summary, "capture_bundle_exchange"),
                    _roundtrip_text(provider_roundtrip_summary, "capture_bundle_exchange"),
                ),
                "dispatch_roundtrip_capture_bundle_source_session_matches_session": _text_matches(
                    _session_contract_text(session_summary, "capture_bundle_source_session"),
                    _roundtrip_session_contract_text(provider_roundtrip_summary, "capture_bundle_source_session"),
                ),
                "dispatch_roundtrip_capture_bundle_market_session_matches_session": _text_matches(
                    _session_contract_text(session_summary, "capture_bundle_market_session"),
                    _roundtrip_session_contract_text(provider_roundtrip_summary, "capture_bundle_market_session"),
                ),
                "dispatch_roundtrip_capture_env_template_path": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_env_template_path",
                    fallback_column="capture_env_template_path",
                ),
                "dispatch_roundtrip_capture_env_template_provided": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_env_template_provided",
                    fallback_column="capture_env_template_provided",
                ),
                "dispatch_roundtrip_capture_env_template_exists": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_env_template_exists",
                    fallback_column="capture_env_template_exists",
                ),
                "dispatch_roundtrip_capture_env_template_sha256": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_capture_env_template_sha256",
                    fallback_column="capture_env_template_sha256",
                ),
                "dispatch_roundtrip_capture_env_template_matches_session": _provenance_matches(
                    _first_text(session_summary, "capture_env_template_path"),
                    _roundtrip_text(provider_roundtrip_summary, "capture_env_template_path"),
                ),
                "dispatch_roundtrip_adapter_handoff_path": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_adapter_handoff_path",
                    fallback_column="adapter_handoff_path",
                ),
                "dispatch_roundtrip_adapter_handoff_provided": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_adapter_handoff_provided",
                    fallback_column="adapter_handoff_provided",
                ),
                "dispatch_roundtrip_adapter_handoff_exists": _first_bool(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_adapter_handoff_exists",
                    fallback_column="adapter_handoff_exists",
                ),
                "dispatch_roundtrip_adapter_handoff_sha256": _first_text(
                    provider_roundtrip_summary,
                    "dispatch_roundtrip_adapter_handoff_sha256",
                    fallback_column="adapter_handoff_sha256",
                ),
                "dispatch_roundtrip_adapter_handoff_matches_session": _provenance_matches(
                    _first_text(session_summary, "adapter_handoff_path"),
                    _roundtrip_text(provider_roundtrip_summary, "adapter_handoff_path"),
                ),
                "dispatch_roundtrip_capture_provenance_consistent": all(
                    [
                        _provenance_matches(
                            _first_text(session_summary, "capture_bundle_path"),
                            _roundtrip_text(provider_roundtrip_summary, "capture_bundle_path"),
                        ),
                        _provenance_matches(
                            _first_text(session_summary, "capture_env_template_path"),
                            _roundtrip_text(provider_roundtrip_summary, "capture_env_template_path"),
                        ),
                        _provenance_matches(
                            _first_text(session_summary, "adapter_handoff_path"),
                            _roundtrip_text(provider_roundtrip_summary, "adapter_handoff_path"),
                        ),
                        _text_matches(
                            _first_text(session_summary, "capture_bundle_exchange"),
                            _roundtrip_text(provider_roundtrip_summary, "capture_bundle_exchange"),
                        ),
                        _text_matches(
                            _session_contract_text(session_summary, "capture_bundle_source_session"),
                            _roundtrip_session_contract_text(
                                provider_roundtrip_summary,
                                "capture_bundle_source_session",
                            ),
                        ),
                        _text_matches(
                            _session_contract_text(session_summary, "capture_bundle_market_session"),
                            _roundtrip_session_contract_text(
                                provider_roundtrip_summary,
                                "capture_bundle_market_session",
                            ),
                        ),
                        _provider_capture_command_proof_matches(session_summary, provider_roundtrip_summary),
                    ]
                ),
                "dispatch_roundtrip_source_provenance_consistent": all(
                    [
                        _provenance_matches(
                            _first_text(session_summary, "source_credential_env_template_path"),
                            _roundtrip_text(provider_roundtrip_summary, "source_credential_env_template_path"),
                        ),
                        _text_matches(
                            _first_text(session_summary, "source_credential_env_template_sha256"),
                            _roundtrip_text(provider_roundtrip_summary, "source_credential_env_template_sha256"),
                        ),
                        _text_matches(
                            _first_text(session_summary, "source_live_fetch_contract_next_gate"),
                            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_next_gate"),
                        ),
                        _text_matches(
                            _first_text(session_summary, "source_live_fetch_contract_command_template"),
                            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_command_template"),
                        ),
                        _text_matches(
                            _first_text(session_summary, "source_live_fetch_contract_exchange"),
                            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_exchange"),
                        ),
                        _text_matches(
                            _first_text(session_summary, "source_live_fetch_contract_market"),
                            _roundtrip_text(provider_roundtrip_summary, "source_live_fetch_contract_market"),
                        ),
                        _text_matches(
                            _session_contract_text(session_summary, "source_live_fetch_contract_session"),
                            _roundtrip_session_contract_text(
                                provider_roundtrip_summary,
                                "source_live_fetch_contract_session",
                            ),
                        ),
                    ]
                ),
                "dispatch_roundtrip_metadata_consistent": all(
                    [
                        _text_matches(
                            _first_text(session_summary, "exchange"),
                            _roundtrip_text(provider_roundtrip_summary, "exchange"),
                        ),
                        _text_matches(
                            _session_contract_text(session_summary, "source_session"),
                            _roundtrip_session_contract_text(provider_roundtrip_summary, "source_session"),
                        ),
                        _text_matches(
                            _session_contract_text(session_summary, "market_session"),
                            _roundtrip_session_contract_text(provider_roundtrip_summary, "market_session"),
                        ),
                    ]
                ),
                "schema_audit_dir": _path_text(schema_audit_dir),
                "order_export_dir": _path_text(_path_or_none(order_export_dir)),
                "upload_pack_dir": _path_text(_path_or_none(upload_pack_dir)),
                "provider_dispatch_roundtrip_dir": _path_text(provider_dispatch_roundtrip_dir),
                "dispatch_roundtrip_dir": _path_text(dispatch_roundtrip_dir),
                "upstream_provider_dispatch_roundtrip_dir": _path_text(upstream_provider_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_dir": _path_text(upstream_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_provided": bool(upstream_dispatch_roundtrip_dir)
                or _first_bool(provider_roundtrip_summary, "upstream_dispatch_roundtrip_provided"),
                "upstream_dispatch_roundtrip_ready": _first_bool(
                    provider_roundtrip_summary,
                    "upstream_dispatch_roundtrip_ready",
                ),
                "upstream_dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_roundtrip_summary, "upstream_dispatch_roundtrip_failed_checks")
                ),
                "dispatch_roundtrip_provided": _first_bool(broker_summary, "dispatch_roundtrip_provided"),
                "dispatch_roundtrip_ready": _first_bool(broker_summary, "dispatch_roundtrip_ready"),
                "dispatch_roundtrip_failed_checks": int(
                    _first_number(broker_summary, "dispatch_roundtrip_failed_checks")
                ),
                **_provider_roundtrip_upstream_vendor_market_data_batch_summary_fields(provider_roundtrip_summary),
                **_broker_readiness_vendor_market_data_batch_summary_fields(broker_summary),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(session_summary, "provider"),
                "transport": _first_text(session_summary, "transport"),
                "market": _first_text(session_summary, "market"),
                "strategy": _first_text(session_summary, "strategy") or PROFILE,
                "target_mode": _first_text(session_summary, "target_mode"),
                "adapter": _first_text(broker_summary, "adapter") or _first_text(session_summary, "adapter"),
                "schema_reviewed": _first_bool(broker_summary, "schema_reviewed"),
                "schema_review_mode": _first_text(broker_summary, "schema_review_mode"),
                "runtime_session_ready": _first_bool(broker_summary, "runtime_session_ready"),
                "runtime_guard_action": _first_text(broker_summary, "runtime_guard_action")
                or _first_text(session_summary, "guard_action"),
                "runtime_guard_halted": _first_bool(broker_summary, "runtime_guard_halted")
                or _first_bool(session_summary, "halted"),
                "broker_recommendation": _first_text(broker_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "prepare_provider_imbalance_cutover_review"
                if ready
                else "repair_provider_imbalance_broker_readiness",
                "next_gate": "review-provider-market-data-imbalance-cutover" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _help_command_for_gate(
                    "review-provider-market-data-imbalance-cutover" if ready else _blocked_next_gate(checks)
                ),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _provider_roundtrip_upstream_vendor_market_data_batch_summary_fields(
    provider_roundtrip_summary: pd.DataFrame,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for prefix in UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES:
        for suffix in VENDOR_MARKET_DATA_BATCH_BOOL_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_bool(provider_roundtrip_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_INT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = int(_first_number(provider_roundtrip_summary, f"{prefix}_{suffix}"))
        for suffix in VENDOR_MARKET_DATA_BATCH_FLOAT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_number(provider_roundtrip_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_TEXT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_text(provider_roundtrip_summary, f"{prefix}_{suffix}")
    return fields


def _broker_readiness_vendor_market_data_batch_summary_fields(broker_summary: pd.DataFrame) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for prefix in VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES:
        for suffix in VENDOR_MARKET_DATA_BATCH_BOOL_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_bool(broker_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_INT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = int(_first_number(broker_summary, f"{prefix}_{suffix}"))
        for suffix in VENDOR_MARKET_DATA_BATCH_FLOAT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_number(broker_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_TEXT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_text(broker_summary, f"{prefix}_{suffix}")
    return fields


def _broker_readiness_vendor_market_data_batch_config(
    broker: BrokerReadinessReport | None,
    key: str,
) -> dict[str, Any]:
    if broker is None or not isinstance(broker.config, dict):
        return {}
    dispatch_roundtrip = broker.config.get("dispatch_roundtrip", {})
    if not isinstance(dispatch_roundtrip, dict):
        return {}
    vendor = dispatch_roundtrip.get(key, {})
    return dict(vendor) if isinstance(vendor, dict) else {}


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
    broker: BrokerReadinessReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_broker_readiness_summary",
                    "component": "broker_readiness",
                    "check": "broker_readiness_ready",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "prepare_provider_imbalance_cutover_review",
                    "reason": "provider imbalance broker readiness is clear for cutover review",
                    "recommendation": "feed_broker_readiness_into_cutover_gate",
                    "next_gate": "review-provider-market-data-imbalance-cutover",
                    "next_gate_help_command": _help_command_for_gate(
                        "review-provider-market-data-imbalance-cutover"
                    ),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, broker)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_readiness_checks",
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
                "source": "provider_market_data_imbalance_broker_readiness_checks",
                "component": "broker_readiness",
                "check": "provider_broker_readiness_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_broker_readiness",
                "reason": "provider imbalance broker readiness is not ready",
                "recommendation": "rerun_provider_imbalance_broker_readiness",
                "next_gate": "review-provider-market-data-imbalance-broker-readiness",
                "next_gate_help_command": _help_command_for_gate(
                    "review-provider-market-data-imbalance-broker-readiness"
                ),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    session_summary: pd.DataFrame,
    session_config: dict[str, Any],
    session_manifest: dict[str, Any],
    provider_roundtrip_config: dict[str, Any],
    provider_roundtrip_manifest: dict[str, Any],
    provider_roundtrip_wrapper_provided: bool,
    broker: BrokerReadinessReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
    broker_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "broker_inputs": _jsonable(broker_inputs),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(session_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(session_config.get("live_session_provider_profile")),
        "provider_capture_commands": _provider_capture_commands(session_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(session_config),
        "adapter_execution_contract": _mapping(session_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            session_config.get("adapter_receipt_proof")
        ),
        "synthetic_sidecar_proof": _mapping(session_config.get("synthetic_sidecar_proof")),
        "provider_lineage_selection_contract": provider_lineage_selection_contract_from_summary(
            summary
        ),
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
            "provider_capture_commands": _bundle_provider_capture_commands(session_config),
            "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(session_config),
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
            "adapter_execution_contract": _mapping(session_config.get("adapter_execution_contract")),
            "adapter_receipt_proof": _mapping(
                session_config.get("adapter_receipt_proof")
            ),
            "adapter_contract_provider": str(summary["adapter_contract_provider"]),
            "adapter_contract_transport": str(summary["adapter_contract_transport"]),
            "adapter_contract_market": str(summary["adapter_contract_market"]),
            "adapter_contract_exchange": str(summary["adapter_contract_exchange"]),
            "adapter_contract_values_stored": bool(summary["adapter_contract_values_stored"]),
            "adapter_contract_metadata_matches_evidence": bool(
                summary["adapter_contract_metadata_matches_evidence"]
            ),
            "provider_profile": _mapping(session_config.get("provider_profile")),
            "live_session_provider_profile": _mapping(session_config.get("live_session_provider_profile")),
            "capture_bundle_provider_profile": _mapping(
                _mapping(session_config.get("capture_bundle")).get("capture_bundle_provider_profile")
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
            "provider_wrapper_provided": bool(provider_roundtrip_wrapper_provided),
            "provider_manifest_run_type": _clean(
                provider_roundtrip_manifest.get("run_type")
            ),
            "adapter_receipt_proof": _mapping(
                provider_roundtrip_config.get("adapter_receipt_proof")
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
            "synthetic_sidecar_proof": _mapping(
                _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance")).get(
                    "synthetic_sidecar_proof"
                )
            )
            or _mapping(provider_roundtrip_config.get("synthetic_sidecar_proof")),
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
            "provider_capture_commands": _roundtrip_provider_capture_commands(provider_roundtrip_config),
            "capture_bundle_provider_capture_commands": _roundtrip_bundle_provider_capture_commands(
                provider_roundtrip_config
            ),
            "provider_capture_commands_match_runtime_session": bool(
                summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
            ),
            "adapter_execution_contract": _roundtrip_adapter_execution_contract(provider_roundtrip_config),
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
            "provider_profile": _roundtrip_provider_profile(provider_roundtrip_config),
            "live_session_provider_profile": _roundtrip_live_session_provider_profile(provider_roundtrip_config),
            "capture_bundle_provider_profile": _roundtrip_capture_bundle_provider_profile(provider_roundtrip_config),
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
        "provider_runtime_session": _first_record(session_summary),
        "provider_runtime_session_config": session_config,
        "provider_runtime_session_manifest_run_type": _clean(
            session_manifest.get("run_type")
        ),
        "upstream_dispatch_roundtrip_vendor_market_data_batch": _provider_roundtrip_vendor_market_data_batch_config(
            provider_roundtrip_config,
            "upstream_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "upstream_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _provider_roundtrip_vendor_market_data_batch_config(
                provider_roundtrip_config,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
            )
        ),
        "dispatch_roundtrip_vendor_market_data_batch": _broker_readiness_vendor_market_data_batch_config(
            broker,
            "vendor_market_data_batch",
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _broker_readiness_vendor_market_data_batch_config(
            broker,
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "broker_readiness": {
            "evaluated": broker is not None,
            "ready": False if broker is None else bool(broker.ready),
            "output_dir": "" if broker is None else str(broker.output_dir or ""),
            "summary": _first_record(None if broker is None else broker.summary),
            "items": _records(None if broker is None else broker.items),
            "checks": _records(None if broker is None else broker.checks),
            "action_queue": _records(None if broker is None else broker.action_queue),
            "config": {} if broker is None or broker.config is None else broker.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _provider_roundtrip_vendor_market_data_batch_config(
    provider_roundtrip_config: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    vendor = provider_roundtrip_config.get(key, {})
    return dict(vendor) if isinstance(vendor, dict) else {}


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    dispatch_roundtrip_receipt_line = (
        "- Dispatch round-trip adapter receipt proof: not applicable "
        "(nested generic input)"
        if not bool(summary["provider_broker_dispatch_roundtrip_wrapper_provided"])
        else (
            "- Dispatch round-trip adapter receipt proof: "
            f"{'ready' if bool(summary['dispatch_roundtrip_adapter_receipt_proof_ready']) else 'blocked'} "
            f"({summary['dispatch_roundtrip_adapter_receipt_fingerprint_match_count']}/"
            f"{summary['dispatch_roundtrip_adapter_receipt_required_count']} sealed; "
            "round-trip manifest match: "
            f"{'yes' if bool(summary['dispatch_roundtrip_adapter_receipt_proof_matches_manifest']) else 'no'}; "
            "runtime match: "
            f"{'yes' if bool(summary['dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session']) else 'no'})"
        )
    )
    lines = [
        "# Provider Market Data Imbalance Broker Readiness",
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
        f"- Broker readiness dir: {summary['broker_readiness_dir']}",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        "- Live fetch contract: "
        f"{'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Adapter execution contract: {summary['adapter_contract_provider'] or 'missing'} / {summary['adapter_contract_transport'] or 'missing'} (evidence match: {'yes' if bool(summary['adapter_contract_metadata_matches_evidence']) else 'no'})",
        f"- Provider profile: {summary['provider_profile_sha256'] or 'missing'} (bundle match: {'yes' if bool(summary['provider_profile_matches_bundle']) else 'no'})",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Adapter receipt proof: {'ready' if bool(summary['adapter_receipt_proof_ready']) else 'blocked'} ({summary['adapter_receipt_fingerprint_match_count']}/{summary['adapter_receipt_required_count']} sealed; session manifest match: {'yes' if bool(summary['adapter_receipt_proof_matches_manifest']) else 'no'})",
        dispatch_roundtrip_receipt_line,
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'} ({summary['synthetic_sidecar_count']}/{summary['synthetic_dataset_count']})",
        f"- Route sidecar breach pairs: {summary['route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs']}",
        f"- Provider lineage contract: `{summary['route_readiness_ops_provider_lineage_selection_contract_sha256']}`",
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
        f"- Dispatch round-trip ready: {'yes' if bool(summary['dispatch_roundtrip_ready']) else 'no'}",
        f"- Dispatch round-trip dir: {summary['dispatch_roundtrip_dir']}",
        "- Dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        f"- Upstream dispatch round-trip ready: {'yes' if bool(summary['upstream_dispatch_roundtrip_ready']) else 'no'}",
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
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
    session_summary: pd.DataFrame,
) -> BrokerReadinessThresholds:
    return BrokerReadinessThresholds(
        adapter=config.adapter or _first_text(session_summary, "adapter") or "arrow_money",
        expected_market=config.expected_market or _first_text(session_summary, "market"),
        expected_vendor_data_kind=config.expected_vendor_data_kind,
        require_reviewed_schema=config.require_reviewed_schema,
        require_schema_audit=config.require_schema_audit,
        require_order_export=config.require_order_export,
        require_mapping_draft=config.require_mapping_draft,
        require_mapped_orders=config.require_mapped_orders,
        require_upload_pack=config.require_upload_pack,
        require_halt_export=config.require_halt_export,
        require_reconciliation=config.require_reconciliation,
        require_runtime_session=config.require_runtime_session,
        require_resume_gate=config.require_resume_gate,
        require_route_readiness=config.require_route_readiness,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        require_adapter_match=config.require_adapter_match,
    )


def _broker_failure_reason(broker: BrokerReadinessReport | None) -> str:
    if broker is None or broker.checks.empty:
        return ""
    failed = broker.checks.loc[~broker.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "review-provider-market-data-imbalance-broker-readiness"
    return _next_gate_for_check(failed[0], None)


def _next_gate_for_check(check: str, broker: BrokerReadinessReport | None) -> str:
    if check.startswith("provider_runtime_session_route_readiness_provider_lineage"):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("provider_runtime_session_route_readiness_provider_sidecar"):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "monitor-provider-market-data-imbalance-runtime-session"
    if check.startswith("order_export") or check.startswith("upload_pack"):
        return "pipeline-provider-market-data-imbalance-launch"
    if check.startswith("provider_broker_dispatch_roundtrip"):
        return "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    if check == "broker_readiness_ready" and broker is not None:
        next_gate = _provider_next_gate(_first_action_value(broker.action_queue, "next_gate"))
        return next_gate or "review-provider-market-data-imbalance-broker-readiness"
    if (
        (check.startswith("dispatch_roundtrip_") and check.endswith("_consistent"))
        or check.startswith("dispatch_roundtrip_adapter_execution_contract")
        or check.startswith("dispatch_roundtrip_provider_profile")
        or check.startswith("dispatch_roundtrip_adapter_provider_profile")
        or check.startswith("dispatch_roundtrip_synthetic_sidecar")
    ):
        return "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    if check.startswith("broker_readiness"):
        return "review-broker-readiness"
    if check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "monitor-provider-market-data-imbalance-runtime-session"
    return "review-provider-market-data-imbalance-broker-readiness"


def _provider_next_gate(next_gate: str) -> str:
    mapping = {
        "review-broker-readiness": "review-provider-market-data-imbalance-broker-readiness",
        "review-route-readiness": "review-provider-market-data-imbalance-route-readiness",
        "review-broker-dispatch-roundtrip": "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
        "plan-broker-dispatch": "plan-provider-market-data-imbalance-broker-dispatch",
        "prepare-broker-dispatch-send": "prepare-provider-market-data-imbalance-broker-dispatch-send",
        "reconcile-broker-dispatch": "reconcile-provider-market-data-imbalance-broker-dispatch",
    }
    return mapping.get(next_gate, next_gate)


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "monitor-provider-market-data-imbalance-runtime-session":
        return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-session --help"
    if next_gate == "pipeline-provider-market-data-imbalance-launch":
        return "python -m hft_cli pipeline-provider-market-data-imbalance-launch --help"
    if next_gate == "review-provider-market-data-imbalance-route-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-broker-dispatch-roundtrip":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-dispatch-roundtrip --help"
    if next_gate == "plan-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "prepare-provider-market-data-imbalance-broker-dispatch-send":
        return "python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send --help"
    if next_gate == "reconcile-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli reconcile-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "review-broker-readiness":
        return "python -m hft_cli review-broker-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-cutover":
        return "python -m hft_cli review-provider-market-data-imbalance-cutover --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    return "python -m hft_cli review-provider-market-data-imbalance-broker-readiness --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_runtime_session_route_readiness_provider_lineage"):
        return "provider_route_readiness"
    if check.startswith("dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "provider_route_readiness"
    if check.startswith("provider_runtime_session_route_readiness_provider_sidecar"):
        return "provider_route_readiness"
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "provider_runtime_session"
    if check.startswith("order_export"):
        return "order_export"
    if check.startswith("upload_pack"):
        return "upload_pack"
    if check.startswith("provider_broker_dispatch_roundtrip"):
        return "provider_broker_dispatch_roundtrip"
    if (
        (check.startswith("dispatch_roundtrip_") and check.endswith("_consistent"))
        or check.startswith("dispatch_roundtrip_adapter_execution_contract")
        or check.startswith("dispatch_roundtrip_provider_profile")
        or check.startswith("dispatch_roundtrip_adapter_provider_profile")
        or check.startswith("dispatch_roundtrip_synthetic_sidecar")
    ):
        return "provider_broker_dispatch_roundtrip"
    if check.startswith("broker_readiness"):
        return "broker_readiness"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_broker_readiness"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_runtime_session_route_readiness_provider_lineage"):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("provider_runtime_session_route_readiness_provider_sidecar"):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "repair_provider_imbalance_runtime_session"
    if check.startswith("order_export") or check.startswith("upload_pack"):
        return "repair_provider_imbalance_launch_broker_artifacts"
    if check.startswith("provider_broker_dispatch_roundtrip"):
        return "repair_provider_imbalance_broker_dispatch_roundtrip"
    if (
        (check.startswith("dispatch_roundtrip_") and check.endswith("_consistent"))
        or check.startswith("dispatch_roundtrip_adapter_execution_contract")
        or check.startswith("dispatch_roundtrip_provider_profile")
        or check.startswith("dispatch_roundtrip_adapter_provider_profile")
        or check.startswith("dispatch_roundtrip_synthetic_sidecar")
    ):
        return "repair_provider_imbalance_broker_dispatch_roundtrip"
    if check.startswith("broker_readiness"):
        return "repair_broker_readiness_inputs"
    return "repair_provider_imbalance_broker_readiness"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_runtime_session_route_readiness_provider_lineage"):
        return "review_provider_lineage_selection_contract_before_broker_readiness"
    if check.startswith("dispatch_roundtrip_route_readiness_provider_sidecar"):
        return "review_provider_roundtrip_route_readiness_sidecar_proof_before_broker_readiness"
    if check.startswith("provider_runtime_session_route_readiness_provider_sidecar"):
        return "review_provider_route_readiness_sidecar_proof_before_broker_readiness"
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "rerun_provider_runtime_session_before_broker_readiness"
    if check.startswith("order_export") or check.startswith("upload_pack"):
        return "rebuild_provider_launch_pipeline_broker_artifacts"
    if check.startswith("provider_broker_dispatch_roundtrip"):
        return "rerun_provider_broker_dispatch_roundtrip_from_same_runtime_and_live_source_provenance"
    if (
        (check.startswith("dispatch_roundtrip_") and check.endswith("_consistent"))
        or check.startswith("dispatch_roundtrip_adapter_execution_contract")
        or check.startswith("dispatch_roundtrip_provider_profile")
        or check.startswith("dispatch_roundtrip_adapter_provider_profile")
        or check.startswith("dispatch_roundtrip_synthetic_sidecar")
    ):
        return "rerun_provider_broker_dispatch_roundtrip_from_same_runtime_and_live_source_provenance"
    if check.startswith("broker_readiness"):
        return "rerun_generic_broker_readiness_with_required_artifacts"
    return "repair_provider_broker_readiness_inputs"


def _runtime_inputs(session_config: dict[str, Any]) -> dict[str, Any]:
    inputs = session_config.get("runtime_inputs", {}) or {}
    return inputs if isinstance(inputs, dict) else {}


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred_inputs: dict[str, Any],
    key: str,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
) -> str | Path | None:
    if explicit is not None:
        return explicit
    if not config.use_provider_runtime_session_inputs:
        return None
    text = _clean(inferred_inputs.get(key))
    return text or None


def _resolve_dispatch_roundtrip_dir(path: Path | None) -> Path | None:
    if path is None:
        return None
    generic_summary = path / "broker_dispatch_roundtrip_summary.csv" if path.is_dir() else path
    if generic_summary.exists():
        return path
    provider_summary, _ = _read_csv(path / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    provider_config, _ = _read_json(path / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json")
    nested = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "broker_dispatch_roundtrip_dir")),
        _path_from_text(((provider_config.get("broker_dispatch_roundtrip", {}) or {}).get("output_dir"))),
        _manifest_input_path(path / "manifest.json", "broker_dispatch_roundtrip"),
    )
    return nested or path


def _read_provider_dispatch_roundtrip_artifacts(
    path: Path | None,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
    dict[str, Any],
    bool,
    str,
    str,
    str,
]:
    if path is None:
        return pd.DataFrame(), {}, {}, False, "", "", ""
    summary_path = (
        path
        / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    config_path = (
        path
        / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    wrapper_provided = summary_path.exists() or config_path.exists()
    if not wrapper_provided:
        return pd.DataFrame(), {}, {}, False, "", "", ""
    summary, summary_error = _read_csv(summary_path)
    config, config_error = _read_json(config_path)
    manifest, manifest_error = _read_json(path / "manifest.json")
    return (
        _with_dispatch_roundtrip_config_fallback(summary, config),
        config,
        manifest,
        True,
        summary_error,
        config_error,
        manifest_error,
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
        fallback_column = column.removeprefix("dispatch_roundtrip_")
        if column not in out.columns:
            out[column] = ""
        if not _first_value_present(out, column) and not _first_value_present(out, fallback_column):
            out[column] = out[column].astype("object")
            out.loc[out.index[0], column] = value
    return out


def _dispatch_roundtrip_config_summary(provider_config: dict[str, Any]) -> pd.DataFrame:
    provenance = _dispatch_roundtrip_provenance(provider_config)
    if not provenance:
        return pd.DataFrame()
    record: dict[str, Any] = {}
    _set_config_text(record, "dispatch_roundtrip_synthetic_dataset_count", provenance, "synthetic_dataset_count")
    _set_config_bool(
        record,
        "dispatch_roundtrip_synthetic_sidecar_proof_ready",
        provenance,
        "synthetic_sidecar_proof_ready",
    )
    for column, key in (
        ("dispatch_roundtrip_synthetic_sidecar_count", "synthetic_sidecar_count"),
        ("dispatch_roundtrip_synthetic_sidecar_readable_count", "synthetic_sidecar_readable_count"),
        ("dispatch_roundtrip_synthetic_sidecar_source_count", "synthetic_sidecar_source_count"),
        (
            "dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count",
            "synthetic_sidecar_adapter_command_hash_count",
        ),
        (
            "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count",
            "synthetic_sidecar_capture_env_template_match_count",
        ),
        (
            "dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count",
            "synthetic_sidecar_adapter_handoff_match_count",
        ),
        (
            "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count",
            "synthetic_sidecar_source_env_template_match_count",
        ),
        ("dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count", "synthetic_sidecar_live_fetch_contract_count"),
        (
            "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count",
            "synthetic_sidecar_adapter_execution_contract_safe_count",
        ),
        ("dispatch_roundtrip_synthetic_sidecar_invariant_count", "synthetic_sidecar_invariant_count"),
    ):
        _set_config_text(record, column, provenance, key)
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
    synthetic_sidecar_proof = _mapping(provenance.get("synthetic_sidecar_proof")) or _mapping(
        provider_config.get("synthetic_sidecar_proof")
    )
    if synthetic_sidecar_proof:
        _set_config_bool(
            record,
            "dispatch_roundtrip_synthetic_sidecar_proof_ready",
            synthetic_sidecar_proof,
            "ready",
        )
        for column, key in (
            ("dispatch_roundtrip_synthetic_sidecar_count", "synthetic_sidecar_count"),
            ("dispatch_roundtrip_synthetic_sidecar_readable_count", "sidecar_readable_count"),
            ("dispatch_roundtrip_synthetic_sidecar_source_count", "sidecar_source_count"),
            ("dispatch_roundtrip_synthetic_sidecar_adapter_command_hash_count", "adapter_command_hash_count"),
            (
                "dispatch_roundtrip_synthetic_sidecar_capture_env_template_match_count",
                "capture_env_template_match_count",
            ),
            ("dispatch_roundtrip_synthetic_sidecar_adapter_handoff_match_count", "adapter_handoff_match_count"),
            (
                "dispatch_roundtrip_synthetic_sidecar_source_env_template_match_count",
                "source_credential_env_template_match_count",
            ),
            ("dispatch_roundtrip_synthetic_sidecar_live_fetch_contract_count", "live_fetch_contract_count"),
            (
                "dispatch_roundtrip_synthetic_sidecar_adapter_execution_contract_safe_count",
                "adapter_execution_contract_safe_count",
            ),
            ("dispatch_roundtrip_synthetic_sidecar_invariant_count", "invariant_count"),
        ):
            _set_config_text(record, column, synthetic_sidecar_proof, key)
    return pd.DataFrame([record]) if record else pd.DataFrame()


def _dispatch_roundtrip_provenance(provider_config: dict[str, Any]) -> dict[str, Any]:
    return _mapping(provider_config.get("dispatch_roundtrip_provenance"))


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


def _inferred_upstream_dispatch_roundtrip_dirs(
    provider_roundtrip_summary: pd.DataFrame,
    provider_roundtrip_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    inputs = provider_roundtrip_config.get("broker_dispatch_roundtrip_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_roundtrip_summary, "upstream_provider_dispatch_roundtrip_dir")),
        _path_from_text(inputs.get("upstream_provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_roundtrip_summary, "upstream_dispatch_roundtrip_dir")),
        _path_from_text(inputs.get("upstream_dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _manifest_input_path(manifest_path: Path, input_name: str) -> Path | None:
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = (manifest.get("inputs", {}) or {}).get(input_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    if not raw_path:
        return None
    candidate = Path(str(raw_path))
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate


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


def _path_or_none(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    return Path(value)


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


def _adapter_contract_carried(session_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(session_summary, "adapter_contract_provider"))
        and bool(_first_text(session_summary, "adapter_contract_transport"))
        and bool(_first_text(session_summary, "adapter_contract_market"))
        and bool(_first_text(session_summary, "adapter_contract_exchange"))
        and not _first_bool(session_summary, "adapter_contract_values_stored")
    )


def _provider_profile_carried(session_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(session_summary, "provider_profile_sha256"))
        and bool(_first_text(session_summary, "provider_profile_adapter"))
        and bool(_first_text(session_summary, "provider_profile_transports"))
    )


def _roundtrip_provider_profile_carried(provider_roundtrip_summary: pd.DataFrame) -> bool:
    return (
        bool(_roundtrip_text(provider_roundtrip_summary, "provider_profile_sha256"))
        and bool(_roundtrip_text(provider_roundtrip_summary, "provider_profile_adapter"))
        and bool(_roundtrip_text(provider_roundtrip_summary, "provider_profile_transports"))
    )


def _provider_profile_metadata_text(session_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(session_summary, 'provider_profile_sha256')}|"
        f"{_first_text(session_summary, 'provider_profile_adapter')}|"
        f"{_first_text(session_summary, 'provider_profile_transports')}"
    )


def _roundtrip_provider_profile_metadata_text(provider_roundtrip_summary: pd.DataFrame) -> str:
    return (
        f"{_roundtrip_text(provider_roundtrip_summary, 'provider_profile_sha256')}|"
        f"{_roundtrip_text(provider_roundtrip_summary, 'provider_profile_adapter')}|"
        f"{_roundtrip_text(provider_roundtrip_summary, 'provider_profile_transports')}"
    )


def _roundtrip_provider_profile_matches_session(
    session_summary: pd.DataFrame,
    provider_roundtrip_summary: pd.DataFrame,
) -> bool:
    return (
        _provider_profile_carried(session_summary)
        and _roundtrip_provider_profile_carried(provider_roundtrip_summary)
        and _provider_profile_metadata_text(session_summary)
        == _roundtrip_provider_profile_metadata_text(provider_roundtrip_summary)
    )


def _adapter_contract_metadata_text(session_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(session_summary, 'adapter_contract_provider')}|"
        f"{_first_text(session_summary, 'adapter_contract_transport')}|"
        f"{_first_text(session_summary, 'adapter_contract_market')}|"
        f"{_first_text(session_summary, 'adapter_contract_exchange')}"
    )


def _roundtrip_adapter_contract_carried(provider_roundtrip_summary: pd.DataFrame) -> bool:
    return (
        bool(_roundtrip_text(provider_roundtrip_summary, "adapter_contract_provider"))
        and bool(_roundtrip_text(provider_roundtrip_summary, "adapter_contract_transport"))
        and bool(_roundtrip_text(provider_roundtrip_summary, "adapter_contract_market"))
        and bool(_roundtrip_text(provider_roundtrip_summary, "adapter_contract_exchange"))
        and not _roundtrip_bool(provider_roundtrip_summary, "adapter_contract_values_stored")
    )


def _roundtrip_adapter_contract_metadata_text(provider_roundtrip_summary: pd.DataFrame) -> str:
    return (
        f"{_roundtrip_text(provider_roundtrip_summary, 'adapter_contract_provider')}|"
        f"{_roundtrip_text(provider_roundtrip_summary, 'adapter_contract_transport')}|"
        f"{_roundtrip_text(provider_roundtrip_summary, 'adapter_contract_market')}|"
        f"{_roundtrip_text(provider_roundtrip_summary, 'adapter_contract_exchange')}"
    )


def _roundtrip_adapter_contract_matches_session(
    session_summary: pd.DataFrame,
    provider_roundtrip_summary: pd.DataFrame,
) -> bool:
    return (
        _adapter_contract_carried(session_summary)
        and _roundtrip_adapter_contract_carried(provider_roundtrip_summary)
        and _adapter_contract_metadata_text(session_summary)
        == _roundtrip_adapter_contract_metadata_text(provider_roundtrip_summary)
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
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _provider_capture_commands(session_config: dict[str, Any]) -> list[Any]:
    return _list(session_config.get("provider_capture_commands"))


def _bundle_provider_capture_commands(session_config: dict[str, Any]) -> list[Any]:
    bundle = _mapping(session_config.get("capture_bundle"))
    return (
        _list(session_config.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("provider_capture_commands"))
    )


def _roundtrip_provider_capture_commands(provider_roundtrip_config: dict[str, Any]) -> list[Any]:
    provenance = _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance"))
    return _list(provenance.get("provider_capture_commands")) or _provider_capture_commands(
        provider_roundtrip_config
    )


def _roundtrip_bundle_provider_capture_commands(provider_roundtrip_config: dict[str, Any]) -> list[Any]:
    provenance = _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance"))
    return _list(provenance.get("capture_bundle_provider_capture_commands")) or _bundle_provider_capture_commands(
        provider_roundtrip_config
    )


def _roundtrip_adapter_execution_contract(provider_roundtrip_config: dict[str, Any]) -> dict[str, Any]:
    provenance = _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance"))
    bundle = _mapping(provider_roundtrip_config.get("capture_bundle"))
    return (
        _mapping(provider_roundtrip_config.get("adapter_execution_contract"))
        or _mapping(bundle.get("adapter_execution_contract"))
        or _mapping(provenance.get("adapter_execution_contract"))
    )


def _roundtrip_provider_profile(provider_roundtrip_config: dict[str, Any]) -> dict[str, Any]:
    provenance = _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance"))
    return _mapping(provenance.get("provider_profile")) or _mapping(
        provider_roundtrip_config.get("provider_profile")
    )


def _roundtrip_live_session_provider_profile(provider_roundtrip_config: dict[str, Any]) -> dict[str, Any]:
    provenance = _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance"))
    return _mapping(provenance.get("live_session_provider_profile")) or _mapping(
        provider_roundtrip_config.get("live_session_provider_profile")
    )


def _roundtrip_capture_bundle_provider_profile(provider_roundtrip_config: dict[str, Any]) -> dict[str, Any]:
    provenance = _mapping(provider_roundtrip_config.get("dispatch_roundtrip_provenance"))
    bundle = _mapping(provider_roundtrip_config.get("capture_bundle"))
    return (
        _mapping(provenance.get("capture_bundle_provider_profile"))
        or _mapping(bundle.get("capture_bundle_provider_profile"))
        or _mapping(bundle.get("provider_profile"))
    )


def _first_text(frame: pd.DataFrame | None, column: str, *, fallback_column: str = "") -> str:
    if frame is None or frame.empty:
        return ""
    if column not in frame.columns:
        return _first_text(frame, fallback_column) if fallback_column else ""
    value = _clean(frame.iloc[0][column])
    if value:
        return value
    if fallback_column:
        return _first_text(frame, fallback_column)
    return value


def _first_bool(frame: pd.DataFrame | None, column: str, *, fallback_column: str = "") -> bool:
    if frame is None or frame.empty:
        return False
    if column not in frame.columns:
        return _first_bool(frame, fallback_column) if fallback_column else False
    value = frame.iloc[0][column]
    passed = _truthy(value)
    if not passed and fallback_column and _first_bool(frame, fallback_column):
        return True
    return passed


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


def _first_value_present(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _value_present(frame.iloc[0][column])


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


def _provenance_matches(expected: object, actual: object) -> bool:
    expected_text = _clean(expected)
    actual_text = _clean(actual)
    if not expected_text or not actual_text:
        return True
    return _path_identity(expected_text) == _path_identity(actual_text)


def _text_matches(expected: object, actual: object) -> bool:
    expected_text = _clean(expected)
    actual_text = _clean(actual)
    if not expected_text or not actual_text:
        return True
    return expected_text == actual_text


def _path_identity(value: str) -> str:
    try:
        return str(Path(value).resolve()).lower()
    except (OSError, RuntimeError, ValueError):
        return value.strip().lower()


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
    if isinstance(value, (list, tuple, set)):
        items = sorted(value) if isinstance(value, set) else value
        parts = [_clean(item) for item in items]
        return ";".join(part for part in parts if part)
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return text
        if isinstance(parsed, (list, tuple, set)):
            return _clean(parsed)
    return text


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
