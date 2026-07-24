from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from adapters.broker_readiness import BrokerReadinessReport, BrokerReadinessThresholds, write_broker_readiness_report
from adapters.vendor_mapping_application import RECEIPT_FILE as MAPPING_APPLICATION_RECEIPT_FILE
from markets.calendars import market_calendar_summary, resolve_market_calendar
from reports.data_readiness import DataReadinessThresholds
from reports.data_readiness_comparison import DataReadinessComparisonThresholds
from reports.manifest import MANIFEST_NAME, write_experiment_manifest
from reports.vendor_data_onboarding import (
    VendorMarketDataBatchReport,
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
)

_VENDOR_BATCH_PREFIXES = (
    "",
    "broker_dispatch_roundtrip_vendor_market_data_batch",
    "dispatch_roundtrip_vendor_market_data_batch",
)
PLACEHOLDER_SCHEMA_STATUS = "placeholder_normalized_pending_vendor_schema"
TARGET_APPLICATION_BATCH_MODE = "per_dataset_verified_target_application"
BROKER_VENDOR_NEXT_GATES = {
    "vendor_market_data_batch": "pipeline-vendor-market-data-batch",
    "broker_readiness": "review-broker-readiness",
    "broker_vendor_data": "pipeline-broker-vendor-readiness",
}


@dataclass(frozen=True)
class BrokerVendorDataReadinessConfig:
    adapter: str = "arrow_money"
    kind: str = "ticks"
    sample_rows: int = 1000
    min_mapping_coverage: float = 1.0
    output_filename: str | None = None
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    filter_session: bool = True
    market: str = "india_nse_index_derivatives"
    market_calendar_path: str | None = None
    expiry_cycle: str | None = None
    underlying: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None
    require_all_mapped: bool = True
    min_rows: int = 1
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_non_trading_day_rows: int = 0
    max_out_of_session_rows: int = 0
    max_unparseable_contract_expiry_rows: int = 0
    max_expired_contract_rows: int = 0
    max_duplicate_contract_key_rows: int = 0
    max_conflicting_contract_key_rows: int = 0
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None


@dataclass(frozen=True)
class BrokerVendorDataReadinessReport:
    vendor_batch: VendorMarketDataBatchReport
    broker_readiness: BrokerReadinessReport
    components: pd.DataFrame
    summary: pd.DataFrame
    checks: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    config: dict[str, object] | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_broker_vendor_data_readiness_pipeline(
    input_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    mapping_path: str | Path | None = None,
    mapping_application_dirs: list[str | Path] | None = None,
    schema_audit_dir: str | Path | None = None,
    order_export_dir: str | Path | None = None,
    mapping_draft_dir: str | Path | None = None,
    mapped_orders_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    halt_export_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    runtime_session_dir: str | Path | None = None,
    resume_dir: str | Path | None = None,
    dispatch_roundtrip_dir: str | Path | None = None,
    config: BrokerVendorDataReadinessConfig | None = None,
    readiness_thresholds: DataReadinessThresholds | None = None,
    comparison_thresholds: DataReadinessComparisonThresholds | None = None,
    broker_thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerVendorDataReadinessReport:
    config = config or BrokerVendorDataReadinessConfig()
    out = Path(output_dir).resolve()
    vendor_batch_dir = out / "01_vendor_market_data_batch"
    broker_readiness_dir = out / "02_broker_readiness"
    mapping_application_roots = (
        [Path(path).resolve() for path in mapping_application_dirs]
        if mapping_application_dirs is not None
        else []
    )

    vendor_config = VendorMarketDataPipelineConfig(
        adapter=config.adapter,
        kind=config.kind,
        sample_rows=config.sample_rows,
        min_mapping_coverage=config.min_mapping_coverage,
        output_filename=config.output_filename,
        timestamp_unit=config.timestamp_unit,
        timestamp_tz=config.timestamp_tz,
        filter_session=config.filter_session,
        market=config.market,
        market_calendar_path=config.market_calendar_path,
        expiry_cycle=config.expiry_cycle,
        underlying=config.underlying,
        lot_size=config.lot_size,
        tick_size=config.tick_size,
        require_all_mapped=config.require_all_mapped,
        min_rows=config.min_rows,
        max_crossed_quote_rows=config.max_crossed_quote_rows,
        max_nonpositive_quote_rows=config.max_nonpositive_quote_rows,
        max_nonpositive_depth_rows=config.max_nonpositive_depth_rows,
        max_non_trading_day_rows=config.max_non_trading_day_rows,
        max_out_of_session_rows=config.max_out_of_session_rows,
        max_unparseable_contract_expiry_rows=(
            config.max_unparseable_contract_expiry_rows
        ),
        max_expired_contract_rows=config.max_expired_contract_rows,
        max_duplicate_contract_key_rows=(
            config.max_duplicate_contract_key_rows
        ),
        max_conflicting_contract_key_rows=(
            config.max_conflicting_contract_key_rows
        ),
        max_p99_gap_ns=config.max_p99_gap_ns,
        max_median_spread_ticks=config.max_median_spread_ticks,
    )
    vendor_batch = write_vendor_market_data_batch_pipeline(
        input_paths,
        output_dir=vendor_batch_dir,
        labels=labels,
        mapping_path=mapping_path,
        mapping_application_dirs=(
            mapping_application_roots
            if mapping_application_dirs is not None
            else None
        ),
        config=vendor_config,
        readiness_thresholds=readiness_thresholds,
        comparison_thresholds=comparison_thresholds,
    )
    broker_thresholds = broker_thresholds or BrokerReadinessThresholds(
        adapter=config.adapter,
        expected_market=config.market,
        expected_vendor_data_kind=config.kind,
        require_reviewed_schema=False,
        require_dispatch_roundtrip=True,
    )
    broker_readiness = write_broker_readiness_report(
        output_dir=broker_readiness_dir,
        schema_audit_dir=schema_audit_dir,
        order_export_dir=order_export_dir,
        mapping_draft_dir=mapping_draft_dir,
        mapped_orders_dir=mapped_orders_dir,
        upload_pack_dir=upload_pack_dir,
        halt_export_dir=halt_export_dir,
        reconciliation_dir=reconciliation_dir,
        runtime_session_dir=runtime_session_dir,
        resume_dir=resume_dir,
        dispatch_roundtrip_dir=dispatch_roundtrip_dir,
        vendor_market_data_batch_dir=vendor_batch_dir,
        thresholds=broker_thresholds,
    )
    components = _components(vendor_batch, vendor_batch_dir, broker_readiness, broker_readiness_dir)
    summary = _summary(components, vendor_batch, broker_readiness, config, broker_thresholds)
    checks = _checks(summary.iloc[0], components, config)
    failed_rows = _failed_check_rows(checks)
    failed_checks = int(len(failed_rows)) if not checks.empty else 1
    primary_blocker = _first_failed_check(failed_rows)
    summary.loc[summary.index[0], "failed_checks"] = failed_checks
    summary.loc[summary.index[0], "failed_check_count"] = failed_checks
    summary.loc[summary.index[0], "failed_check_names"] = _failed_check_names(failed_rows)
    summary.loc[summary.index[0], "first_failed_reason"] = _check_reason(primary_blocker)
    summary.loc[summary.index[0], "primary_blocker_check"] = _check_name(primary_blocker)
    summary.loc[summary.index[0], "primary_blocker_value"] = _check_value(primary_blocker, "observed")
    summary.loc[summary.index[0], "primary_blocker_operator"] = _check_value(primary_blocker, "operator")
    summary.loc[summary.index[0], "primary_blocker_threshold"] = _check_value(primary_blocker, "expected")
    summary.loc[summary.index[0], "primary_blocker_reason"] = _check_reason(primary_blocker)
    summary.loc[summary.index[0], "ready"] = failed_checks == 0
    summary.loc[summary.index[0], "recommendation"] = (
        "broker_data_proof_ready" if failed_checks == 0 else "fix_vendor_or_broker_readiness_proof"
    )
    components.to_csv(out / "broker_vendor_data_readiness_components.csv", index=False)
    summary.to_csv(out / "broker_vendor_data_readiness_summary.csv", index=False)
    checks.to_csv(out / "broker_vendor_data_readiness_checks.csv", index=False)
    action_queue = _action_queue(checks)
    action_queue.to_csv(out / "broker_vendor_data_readiness_action_queue.csv", index=False)
    config_payload = _config(summary.iloc[0], components, checks, action_queue, config, broker_thresholds)
    (out / "broker_vendor_data_readiness_config.json").write_text(
        json.dumps(
            config_payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "broker_vendor_data_readiness_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], components, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_vendor_data_readiness_pipeline",
        parameters={
            "config": asdict(config),
            "broker_thresholds": asdict(broker_thresholds),
            "comparison_thresholds": asdict(comparison_thresholds)
            if comparison_thresholds is not None
            else None,
            "labels": labels,
            "mapping_source": str(summary.iloc[0].get("mapping_source_mode", "")),
            "mapping_application_count": _int(
                summary.iloc[0].get("mapping_application_count", 0)
            ),
        },
        inputs={
            "inputs": [Path(path) for path in input_paths],
            "mapping": Path(mapping_path) if mapping_path is not None else None,
            "mapping_applications": (
                mapping_application_roots
                if mapping_application_dirs is not None
                else None
            ),
            "mapping_application_manifests": (
                [path / MANIFEST_NAME for path in mapping_application_roots]
                if mapping_application_dirs is not None
                else None
            ),
            "mapping_application_receipts": (
                [path / MAPPING_APPLICATION_RECEIPT_FILE for path in mapping_application_roots]
                if mapping_application_dirs is not None
                else None
            ),
            "schema_audit": schema_audit_dir,
            "order_export": order_export_dir,
            "mapping_draft": mapping_draft_dir,
            "mapped_orders": mapped_orders_dir,
            "upload_pack": upload_pack_dir,
            "halt_export": halt_export_dir,
            "reconciliation": reconciliation_dir,
            "runtime_session": runtime_session_dir,
            "resume_gate": resume_dir,
            "dispatch_roundtrip": dispatch_roundtrip_dir,
            "market_calendar": (
                Path(config.market_calendar_path)
                if config.market_calendar_path
                else None
            ),
            "vendor_market_data_batch": vendor_batch_dir,
            "vendor_market_data_batch_manifest": vendor_batch_dir / MANIFEST_NAME,
            "vendor_market_data_batch_config": (
                vendor_batch_dir / "vendor_market_data_batch_config.json"
            ),
            "broker_readiness": broker_readiness_dir,
        },
    )
    return BrokerVendorDataReadinessReport(
        vendor_batch,
        broker_readiness,
        components,
        summary,
        checks,
        out,
        action_queue,
        config_payload,
    )


def _components(
    vendor_batch: VendorMarketDataBatchReport,
    vendor_batch_dir: Path,
    broker_readiness: BrokerReadinessReport,
    broker_readiness_dir: Path,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _component("vendor_market_data_batch", vendor_batch.ready, vendor_batch_dir, vendor_batch.summary),
            _component("broker_readiness", broker_readiness.ready, broker_readiness_dir, broker_readiness.summary),
        ]
    )


def _component(name: str, ready: bool, artifact_dir: Path, summary: pd.DataFrame) -> dict[str, object]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "component": name,
        "status": "ready" if ready else "not_ready",
        "ready": bool(ready),
        "artifact_dir": str(artifact_dir),
        "adapter": str(row.get("adapter", "")),
        "dataset_count": _int(_vendor_value(row, "dataset_count", 0)),
        "ready_datasets": _int(_vendor_value(row, "ready_datasets", 0)),
        "failed_datasets": _int(_vendor_value(row, "failed_datasets", 0)),
        "unique_source_files": _int(_vendor_value(row, "unique_source_files", 0)),
        "unique_header_fingerprints": _int(_vendor_value(row, "unique_header_fingerprints", 0)),
        "source_file_fingerprint_coverage": _float(_vendor_value(row, "source_file_fingerprint_coverage", 0.0)),
        "min_mapping_coverage": _float(_vendor_value(row, "min_mapping_coverage", 0.0)),
        "unique_mapping_drafts": _int(_vendor_value(row, "unique_mapping_drafts", 0)),
        "mapping_sources": str(_vendor_value(row, "mapping_sources", "")),
        "mapping_source_mode": str(_vendor_value(row, "mapping_source_mode", "")),
        "mapping_application_count": _int(
            _vendor_value(row, "mapping_application_count", 0)
        ),
        "unique_mapping_applications": _int(
            _vendor_value(row, "unique_mapping_applications", 0)
        ),
        "target_application_coverage": _float(
            _vendor_value(row, "target_application_coverage", 0.0)
        ),
        "adapter_schema_status": str(row.get("adapter_schema_status", "")),
        "schema_reviewed": _bool(row.get("schema_reviewed", False)),
        "schema_review_mode": str(row.get("schema_review_mode", "")),
        "placeholder_schema_active": _is_placeholder_schema(row.get("adapter_schema_status", "")),
        "failed_checks": _int(row.get("failed_checks", row.get("comparison_failed_checks", 0))),
        "recommendation": str(row.get("recommendation", "")),
    }


def _summary(
    components: pd.DataFrame,
    vendor_batch: VendorMarketDataBatchReport,
    broker_readiness: BrokerReadinessReport,
    config: BrokerVendorDataReadinessConfig,
    broker_thresholds: BrokerReadinessThresholds,
) -> pd.DataFrame:
    vendor_row = vendor_batch.summary.iloc[0] if not vendor_batch.summary.empty else pd.Series(dtype=object)
    broker_row = broker_readiness.summary.iloc[0] if not broker_readiness.summary.empty else pd.Series(dtype=object)
    ready = bool(vendor_batch.ready and broker_readiness.ready)
    schema_status = str(broker_row.get("adapter_schema_status", ""))
    schema_reviewed = _bool(broker_row.get("schema_reviewed", False))
    placeholder_schema_active = _is_placeholder_schema(schema_status)
    placeholder_schema_allowed = placeholder_schema_active and not bool(broker_thresholds.require_reviewed_schema)
    calendar = resolve_market_calendar(
        config.market_calendar_path,
        market=config.market,
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "kind": config.kind,
                "market": config.market,
                **market_calendar_summary(calendar),
                "adapter_schema_status": schema_status,
                "schema_review_required": bool(broker_thresholds.require_reviewed_schema),
                "schema_reviewed": schema_reviewed,
                "schema_review_mode": str(broker_row.get("schema_review_mode", "")),
                "placeholder_schema_active": placeholder_schema_active,
                "placeholder_schema_allowed": placeholder_schema_allowed,
                "placeholder_schema_warning": _placeholder_schema_warning(
                    schema_status,
                    schema_reviewed=schema_reviewed,
                    placeholder_allowed=placeholder_schema_allowed,
                ),
                "vendor_batch_ready": bool(vendor_batch.ready),
                "broker_readiness_ready": bool(broker_readiness.ready),
                "dataset_count": _int(vendor_row.get("dataset_count", 0)),
                "ready_datasets": _int(vendor_row.get("ready_datasets", 0)),
                "failed_datasets": _int(vendor_row.get("failed_datasets", 0)),
                "dropped_calendar_closed_rows": _int(
                    vendor_row.get("dropped_calendar_closed_rows", 0)
                ),
                "dropped_calendar_out_of_range_rows": _int(
                    vendor_row.get("dropped_calendar_out_of_range_rows", 0)
                ),
                "unique_source_files": _int(vendor_row.get("unique_source_files", 0)),
                "unique_header_fingerprints": _int(vendor_row.get("unique_header_fingerprints", 0)),
                "source_file_fingerprint_coverage": _float(
                    vendor_row.get("source_file_fingerprint_coverage", 0.0)
                ),
                "min_mapping_coverage": _float(vendor_row.get("min_mapping_coverage", 0.0)),
                "unique_mapping_drafts": _int(vendor_row.get("unique_mapping_drafts", 0)),
                "mapping_sources": str(vendor_row.get("mapping_sources", "")),
                "mapping_source_mode": str(vendor_row.get("mapping_source_mode", "")),
                "mapping_application_count": _int(
                    vendor_row.get("mapping_application_count", 0)
                ),
                "unique_mapping_applications": _int(
                    vendor_row.get("unique_mapping_applications", 0)
                ),
                "target_application_coverage": _float(
                    vendor_row.get("target_application_coverage", 0.0)
                ),
                "comparison_accepted": bool(vendor_row.get("comparison_accepted", False)),
                "comparison_failed_checks": _int(vendor_row.get("comparison_failed_checks", 0)),
                "broker_vendor_data_ready": bool(
                    broker_row.get("broker_dispatch_roundtrip_vendor_market_data_batch_ready", False)
                ),
                "broker_vendor_mapping_source_mode": str(
                    broker_row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
                        "",
                    )
                ),
                "broker_vendor_mapping_application_count": _int(
                    broker_row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
                        0,
                    )
                ),
                "broker_vendor_unique_mapping_applications": _int(
                    broker_row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
                        0,
                    )
                ),
                "broker_vendor_target_application_coverage": _float(
                    broker_row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
                        0.0,
                    )
                ),
                "broker_vendor_application_lineage_consistency_required": _bool(
                    broker_row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistency_required",
                        False,
                    )
                ),
                "broker_vendor_application_lineage_consistent": _bool(
                    broker_row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
                        False,
                    )
                ),
                "broker_vendor_lineage_match_required": _bool(
                    broker_row.get(
                        "broker_vendor_market_data_batch_lineage_match_required",
                        False,
                    )
                ),
                "broker_vendor_lineage_matches": _bool(
                    broker_row.get(
                        "broker_vendor_market_data_batch_lineage_matches",
                        False,
                    )
                ),
                "vendor_application_lineage_sha256": str(
                    broker_row.get(
                        "vendor_market_data_batch_application_lineage_sha256",
                        "",
                    )
                ),
                "broker_vendor_application_lineage_sha256": str(
                    broker_row.get(
                        "broker_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    )
                ),
                "broker_readiness_route_readiness_ready": _bool(
                    broker_row.get("route_readiness_ready", False)
                ),
                "broker_readiness_route_readiness_strategy": str(
                    broker_row.get("route_readiness_strategy", "")
                ),
                "broker_readiness_route_readiness_market": str(
                    broker_row.get("route_readiness_market", "")
                ),
                "broker_readiness_route_readiness_gap_pairs": _int(
                    broker_row.get("route_readiness_gap_pairs", 0)
                ),
                "broker_readiness_route_readiness_ops_launch_controls_present": _bool(
                    broker_row.get("route_readiness_ops_launch_controls_present", False)
                ),
                "broker_readiness_route_readiness_ops_launch_controls_blocked_pairs": _int(
                    broker_row.get("route_readiness_ops_launch_controls_blocked_pairs", 0)
                ),
                "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": _int(
                    broker_row.get("route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0)
                ),
                "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": _int(
                    broker_row.get(
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                        0,
                    )
                ),
                "broker_readiness_route_broker_route_readiness_provided": _bool(
                    broker_row.get("route_broker_route_readiness_provided", False)
                ),
                "broker_readiness_route_broker_route_readiness_ready": _bool(
                    broker_row.get("route_broker_route_readiness_ready", False)
                ),
                "broker_readiness_route_broker_route_readiness_strategy": str(
                    broker_row.get("route_broker_route_readiness_strategy", "")
                ),
                "broker_readiness_route_broker_route_readiness_market": str(
                    broker_row.get("route_broker_route_readiness_market", "")
                ),
                "broker_readiness_route_broker_route_readiness_gap_pairs": _int(
                    broker_row.get("route_broker_route_readiness_gap_pairs", 0)
                ),
                "broker_readiness_route_broker_route_readiness_ops_launch_controls_ready": _bool(
                    broker_row.get("route_broker_route_readiness_ops_launch_controls_ready", False)
                ),
                "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _int(
                    broker_row.get("route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0)
                ),
                "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _int(
                    broker_row.get("route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0)
                ),
                "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    _int(
                        broker_row.get(
                            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    _int(
                        broker_row.get(
                            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_resume_broker_route_readiness_provided": _bool(
                    broker_row.get("resume_broker_route_readiness_provided", False)
                ),
                "broker_readiness_resume_broker_route_readiness_ready": _bool(
                    broker_row.get("resume_broker_route_readiness_ready", False)
                ),
                "broker_readiness_resume_broker_route_readiness_strategy": str(
                    broker_row.get("resume_broker_route_readiness_strategy", "")
                ),
                "broker_readiness_resume_broker_route_readiness_market": str(
                    broker_row.get("resume_broker_route_readiness_market", "")
                ),
                "broker_readiness_resume_broker_route_readiness_gap_pairs": _int(
                    broker_row.get("resume_broker_route_readiness_gap_pairs", 0)
                ),
                "broker_readiness_resume_broker_route_readiness_ops_launch_controls_ready": _bool(
                    broker_row.get("resume_broker_route_readiness_ops_launch_controls_ready", False)
                ),
                "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _int(
                    broker_row.get("resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0)
                ),
                "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _int(
                    broker_row.get("resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0)
                ),
                "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    _int(
                        broker_row.get(
                            "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    _int(
                        broker_row.get(
                            "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_resume_incident_broker_route_readiness_provided": _bool(
                    broker_row.get("resume_incident_broker_route_readiness_provided", False)
                ),
                "broker_readiness_resume_incident_broker_route_readiness_ready": _bool(
                    broker_row.get("resume_incident_broker_route_readiness_ready", False)
                ),
                "broker_readiness_resume_incident_broker_route_readiness_strategy": str(
                    broker_row.get("resume_incident_broker_route_readiness_strategy", "")
                ),
                "broker_readiness_resume_incident_broker_route_readiness_market": str(
                    broker_row.get("resume_incident_broker_route_readiness_market", "")
                ),
                "broker_readiness_resume_incident_broker_route_readiness_gap_pairs": _int(
                    broker_row.get("resume_incident_broker_route_readiness_gap_pairs", 0)
                ),
                "broker_readiness_resume_incident_broker_route_readiness_ops_launch_controls_ready": _bool(
                    broker_row.get("resume_incident_broker_route_readiness_ops_launch_controls_ready", False)
                ),
                "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    _int(
                        broker_row.get(
                            "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    _int(
                        broker_row.get(
                            "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    _int(
                        broker_row.get(
                            "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                            0,
                        )
                    )
                ),
                "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    _int(
                        broker_row.get(
                            (
                                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                                "concentration_breach_runs"
                            ),
                            0,
                        )
                    )
                ),
                "failed_components": int((~components["ready"].astype(bool)).sum()) if not components.empty else 0,
                "recommendation": "broker_data_proof_ready" if ready else "fix_vendor_or_broker_readiness_proof",
            }
        ]
    )


def _checks(
    row: pd.Series,
    components: pd.DataFrame,
    config: BrokerVendorDataReadinessConfig,
) -> pd.DataFrame:
    dataset_count = _int(row.get("dataset_count", 0))
    min_mapping_coverage = float(config.min_mapping_coverage)
    mapping_source_mode = str(row.get("mapping_source_mode", "")).strip()
    target_application_mode = mapping_source_mode == TARGET_APPLICATION_BATCH_MODE
    expected_application_count = dataset_count if target_application_mode else 0
    expected_application_coverage = 1.0 if target_application_mode else 0.0
    checks = [
        _check(
            "vendor_batch_ready",
            bool(row.get("vendor_batch_ready", False)),
            "is",
            True,
            bool(row.get("vendor_batch_ready", False)),
            "vendor market-data batch is not ready",
        ),
        _check(
            "broker_readiness_ready",
            bool(row.get("broker_readiness_ready", False)),
            "is",
            True,
            bool(row.get("broker_readiness_ready", False)),
            "broker readiness review is not ready",
        ),
        _check(
            "broker_vendor_data_ready",
            bool(row.get("broker_vendor_data_ready", False)),
            "is",
            True,
            bool(row.get("broker_vendor_data_ready", False)),
            "broker readiness did not accept the broker vendor-data proof",
        ),
        _check(
            "failed_components",
            int((~components["ready"].astype(bool)).sum()) if not components.empty else 1,
            "<=",
            0,
            (int((~components["ready"].astype(bool)).sum()) if not components.empty else 1) <= 0,
            "one or more broker-vendor readiness components are not ready",
        ),
        _check(
            "dataset_count",
            dataset_count,
            ">",
            0,
            dataset_count > 0,
            "vendor market-data batch has no datasets",
        ),
        _check(
            "ready_datasets",
            _int(row.get("ready_datasets", 0)),
            ">=",
            dataset_count,
            _int(row.get("ready_datasets", 0)) >= dataset_count and dataset_count > 0,
            "not all vendor market-data datasets are ready",
        ),
        _check(
            "failed_datasets",
            _int(row.get("failed_datasets", 0)),
            "<=",
            0,
            _int(row.get("failed_datasets", 0)) <= 0,
            "vendor market-data batch has failed datasets",
        ),
        _check(
            "unique_source_files",
            _int(row.get("unique_source_files", 0)),
            ">=",
            dataset_count,
            _int(row.get("unique_source_files", 0)) >= dataset_count and dataset_count > 0,
            "vendor market-data batch does not prove distinct source files per dataset",
        ),
        _check(
            "source_file_fingerprint_coverage",
            _float(row.get("source_file_fingerprint_coverage", 0.0)),
            ">=",
            1.0,
            _float(row.get("source_file_fingerprint_coverage", 0.0)) >= 1.0,
            "vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            "min_mapping_coverage",
            _float(row.get("min_mapping_coverage", 0.0)),
            ">=",
            min_mapping_coverage,
            _float(row.get("min_mapping_coverage", 0.0)) >= min_mapping_coverage,
            "vendor market-data batch has incomplete mapping coverage",
        ),
        _check(
            "unique_mapping_drafts",
            _int(row.get("unique_mapping_drafts", 0)),
            ">",
            0,
            _int(row.get("unique_mapping_drafts", 0)) > 0,
            "vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            "mapping_sources",
            str(row.get("mapping_sources", "")).strip(),
            "!=",
            "",
            bool(str(row.get("mapping_sources", "")).strip()),
            "vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            "mapping_source_mode",
            mapping_source_mode,
            "!=",
            "",
            bool(mapping_source_mode),
            "vendor market-data batch is missing its mapping-source mode",
        ),
        _check(
            "mapping_application_count",
            _int(row.get("mapping_application_count", 0)),
            "==",
            expected_application_count,
            _int(row.get("mapping_application_count", 0)) == expected_application_count,
            "vendor market-data batch target applications are not aligned one for one",
        ),
        _check(
            "unique_mapping_applications",
            _int(row.get("unique_mapping_applications", 0)),
            "==",
            expected_application_count,
            _int(row.get("unique_mapping_applications", 0)) == expected_application_count,
            "vendor market-data batch target applications are not distinct per dataset",
        ),
        _check(
            "target_application_coverage",
            _float(row.get("target_application_coverage", 0.0)),
            "==",
            expected_application_coverage,
            _float(row.get("target_application_coverage", 0.0))
            == expected_application_coverage,
            "vendor market-data batch target-application coverage is incomplete",
        ),
        _check(
            "broker_vendor_mapping_source_mode",
            str(row.get("broker_vendor_mapping_source_mode", "")).strip(),
            "==",
            mapping_source_mode,
            bool(mapping_source_mode)
            and str(row.get("broker_vendor_mapping_source_mode", "")).strip()
            == mapping_source_mode,
            "broker readiness did not preserve the vendor batch mapping-source mode",
        ),
        _check(
            "broker_vendor_mapping_application_count",
            _int(row.get("broker_vendor_mapping_application_count", 0)),
            "==",
            expected_application_count,
            _int(row.get("broker_vendor_mapping_application_count", 0))
            == expected_application_count,
            "broker readiness did not preserve the target-application count",
        ),
        _check(
            "broker_vendor_unique_mapping_applications",
            _int(row.get("broker_vendor_unique_mapping_applications", 0)),
            "==",
            expected_application_count,
            _int(row.get("broker_vendor_unique_mapping_applications", 0))
            == expected_application_count,
            "broker readiness did not preserve distinct target-application lineage",
        ),
        _check(
            "broker_vendor_target_application_coverage",
            _float(row.get("broker_vendor_target_application_coverage", 0.0)),
            "==",
            expected_application_coverage,
            _float(row.get("broker_vendor_target_application_coverage", 0.0))
            == expected_application_coverage,
            "broker readiness did not preserve target-application coverage",
        ),
        _check(
            "comparison_accepted",
            bool(row.get("comparison_accepted", False)),
            "is",
            True,
            bool(row.get("comparison_accepted", False)),
            "vendor market-data batch comparison was not accepted",
        ),
        _check(
            "comparison_failed_checks",
            _int(row.get("comparison_failed_checks", 0)),
            "<=",
            0,
            _int(row.get("comparison_failed_checks", 0)) <= 0,
            "vendor market-data batch comparison has failed checks",
        ),
    ]
    if _bool(row.get("broker_vendor_application_lineage_consistency_required", False)):
        checks.append(
            _check(
                "broker_vendor_application_lineage_consistent",
                _bool(row.get("broker_vendor_application_lineage_consistent", False)),
                "is",
                True,
                _bool(row.get("broker_vendor_application_lineage_consistent", False)),
                "broker readiness did not preserve a successful final dispatch/send/ack target-lineage reconciliation",
            )
        )
    if _bool(row.get("broker_vendor_lineage_match_required", False)):
        checks.append(
            _check(
                "broker_vendor_lineage_matches_current_batch",
                _bool(row.get("broker_vendor_lineage_matches", False)),
                "is",
                True,
                _bool(row.get("broker_vendor_lineage_matches", False)),
                "broker-readiness target lineage does not match the current vendor market-data batch",
            )
        )
    return pd.DataFrame(checks)


def _check(
    check: str,
    observed: object,
    operator: str,
    expected: object,
    passed: bool,
    message: str,
) -> dict[str, object]:
    return {
        "check": check,
        "observed": observed,
        "operator": operator,
        "expected": expected,
        "passed": bool(passed),
        "message": "" if passed else message,
    }


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not checks.empty and "passed" in checks.columns:
        failed = _failed_check_rows(checks)
        for priority, row in enumerate(failed.to_dict(orient="records"), start=1):
            check_name = str(row.get("check", ""))
            component = _action_component(check_name)
            next_gate = BROKER_VENDOR_NEXT_GATES.get(component, "pipeline-broker-vendor-readiness")
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "blocked",
                    "check": check_name,
                    "component": component,
                    "next_gate": next_gate,
                    "next_gate_help_command": _help_command(next_gate),
                    "actual": _action_value(row.get("observed")),
                    "operator": _action_value(row.get("operator")),
                    "expected": _action_value(row.get("expected")),
                    "reason": str(row.get("message", "")),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "check",
            "component",
            "next_gate",
            "next_gate_help_command",
            "actual",
            "operator",
            "expected",
            "reason",
        ],
    )


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)


def _failed_check_list(failed_rows: pd.DataFrame) -> list[str]:
    if failed_rows.empty or "check" not in failed_rows.columns:
        return []
    return [_action_value(value) for value in failed_rows["check"].tolist() if _action_value(value)]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    return ";".join(_failed_check_list(failed_rows))


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _first_failed_check_record(failed_rows: pd.DataFrame) -> dict[str, object]:
    if failed_rows.empty:
        return {}
    return _jsonable_record(failed_rows.iloc[0].to_dict())


def _check_name(row: pd.Series) -> str:
    return _check_value(row, "check")


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "message")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty:
        return ""
    return _action_value(row.get(column, ""))


def _first_action_record(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return _jsonable_record(frame.iloc[0].to_dict())


def _action_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [_jsonable_record(row) for row in frame.to_dict(orient="records")]


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Path):
            record[str(key)] = str(value)
            continue
        try:
            if pd.isna(value):
                record[str(key)] = None
                continue
        except (TypeError, ValueError):
            pass
        record[str(key)] = value
    return record


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _action_value(action_queue.iloc[0].get(column))


def _action_component(check_name: str) -> str:
    if check_name in {"broker_readiness_ready", "broker_vendor_data_ready"} or check_name.startswith(
        "broker_vendor_"
    ):
        return "broker_readiness"
    if check_name == "failed_components":
        return "broker_vendor_data"
    return "vendor_market_data_batch"


def _help_command(next_gate: str) -> str:
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _action_value(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _runbook_markdown(row: pd.Series, components: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Broker Vendor Data Readiness Runbook",
        "",
        f"- Ready: {_yes_no(_bool(row.get('ready', False)))}",
        f"- Adapter: {str(row.get('adapter', ''))}",
        f"- Kind: {str(row.get('kind', ''))}",
        f"- Market: {str(row.get('market', ''))}",
        f"- Market calendar: {str(row.get('market_calendar_id', '')) or 'not provided'}",
        f"- Calendar coverage: {str(row.get('market_calendar_valid_from', '')) or 'n/a'} to {str(row.get('market_calendar_valid_to', '')) or 'n/a'}",
        f"- Calendar SHA-256: {str(row.get('market_calendar_sha256', ''))}",
        f"- Adapter schema status: {str(row.get('adapter_schema_status', ''))}",
        f"- Schema review mode: {str(row.get('schema_review_mode', ''))}",
        f"- Placeholder schema active: {_yes_no(_bool(row.get('placeholder_schema_active', False)))}",
        f"- Placeholder schema allowed: {_yes_no(_bool(row.get('placeholder_schema_allowed', False)))}",
        f"- Placeholder schema warning: {str(row.get('placeholder_schema_warning', ''))}",
        f"- Recommendation: {str(row.get('recommendation', ''))}",
        f"- Failed checks: {_int(row.get('failed_checks', 0))}",
        f"- Dataset count: {_int(row.get('dataset_count', 0))}",
        f"- Ready datasets: {_int(row.get('ready_datasets', 0))}",
        f"- Calendar-closed rows: {_int(row.get('dropped_calendar_closed_rows', 0))}",
        f"- Calendar out-of-range rows: {_int(row.get('dropped_calendar_out_of_range_rows', 0))}",
        f"- Mapping source mode: {str(row.get('mapping_source_mode', ''))}",
        f"- Mapping applications: {_int(row.get('mapping_application_count', 0))}",
        f"- Unique mapping applications: {_int(row.get('unique_mapping_applications', 0))}",
        f"- Target-application coverage: {_float(row.get('target_application_coverage', 0.0)):.3f}",
        f"- Broker target-application coverage: {_float(row.get('broker_vendor_target_application_coverage', 0.0)):.3f}",
        f"- Final target-lineage consistency required: {_yes_no(_bool(row.get('broker_vendor_application_lineage_consistency_required', False)))}",
        f"- Final target-lineage consistent: {_yes_no(_bool(row.get('broker_vendor_application_lineage_consistent', False)))}",
        f"- Current/final target lineage match required: {_yes_no(_bool(row.get('broker_vendor_lineage_match_required', False)))}",
        f"- Current/final target lineage matches: {_yes_no(_bool(row.get('broker_vendor_lineage_matches', False)))}",
        f"- Broker readiness ready: {_yes_no(_bool(row.get('broker_readiness_ready', False)))}",
        f"- Broker vendor-data accepted: {_yes_no(_bool(row.get('broker_vendor_data_ready', False)))}",
        "",
        "## Components",
        "",
        _components_table(components),
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _components_table(components: pd.DataFrame) -> str:
    if components.empty:
        return "_None_"
    rows = [
        [
            str(row.get("component", "")),
            _yes_no(_bool(row.get("ready", False))),
            str(row.get("status", "")),
            str(row.get("artifact_dir", "")),
            str(row.get("recommendation", "")),
        ]
        for row in components.to_dict(orient="records")
    ]
    return _markdown_table(["Component", "Ready", "Status", "Artifact dir", "Recommendation"], rows)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(_int(row.get("priority", 0))),
            str(row.get("check", "")),
            str(row.get("component", "")),
            str(row.get("next_gate", "")),
            str(row.get("next_gate_help_command", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
    return _markdown_table(["Priority", "Check", "Component", "Next gate", "Help", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _config(
    row: pd.Series,
    components: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: BrokerVendorDataReadinessConfig,
    broker_thresholds: BrokerReadinessThresholds,
) -> dict[str, object]:
    failed_rows = _failed_check_rows(checks)
    failed = _failed_check_list(failed_rows)
    primary_blocker = _first_failed_check_record(failed_rows)
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(row.get("ready", False)),
        "adapter": config.adapter,
        "kind": config.kind,
        "market": config.market,
        "market_calendar": {
            "provided": _bool(row.get("market_calendar_provided", False)),
            "policy": str(row.get("market_calendar_policy", "")),
            "id": str(row.get("market_calendar_id", "")),
            "path": str(row.get("market_calendar_path", "")),
            "sha256": str(row.get("market_calendar_sha256", "")),
            "valid_from": str(row.get("market_calendar_valid_from", "")),
            "valid_to": str(row.get("market_calendar_valid_to", "")),
            "publisher": str(row.get("market_calendar_publisher", "")),
            "source_url": str(row.get("market_calendar_source_url", "")),
            "published_date": str(
                row.get("market_calendar_published_date", "")
            ),
            "closed_dates": _int(
                row.get("market_calendar_closed_dates", 0)
            ),
            "special_open_dates": _int(
                row.get("market_calendar_special_open_dates", 0)
            ),
        },
        "adapter_schema_status": str(row.get("adapter_schema_status", "")),
        "schema_review_required": _bool(row.get("schema_review_required", False)),
        "schema_reviewed": _bool(row.get("schema_reviewed", False)),
        "schema_review_mode": str(row.get("schema_review_mode", "")),
        "placeholder_schema_active": _bool(row.get("placeholder_schema_active", False)),
        "placeholder_schema_allowed": _bool(row.get("placeholder_schema_allowed", False)),
        "placeholder_schema_warning": str(row.get("placeholder_schema_warning", "")),
        "vendor_market_data_batch": {
            "ready": bool(row.get("vendor_batch_ready", False)),
            "dataset_count": _int(row.get("dataset_count", 0)),
            "ready_datasets": _int(row.get("ready_datasets", 0)),
            "failed_datasets": _int(row.get("failed_datasets", 0)),
            "dropped_calendar_closed_rows": _int(
                row.get("dropped_calendar_closed_rows", 0)
            ),
            "dropped_calendar_out_of_range_rows": _int(
                row.get("dropped_calendar_out_of_range_rows", 0)
            ),
            "unique_source_files": _int(row.get("unique_source_files", 0)),
            "unique_header_fingerprints": _int(row.get("unique_header_fingerprints", 0)),
            "source_file_fingerprint_coverage": _float(row.get("source_file_fingerprint_coverage", 0.0)),
            "min_mapping_coverage": _float(row.get("min_mapping_coverage", 0.0)),
            "unique_mapping_drafts": _int(row.get("unique_mapping_drafts", 0)),
            "mapping_sources": str(row.get("mapping_sources", "")),
            "mapping_source_mode": str(row.get("mapping_source_mode", "")),
            "mapping_application_count": _int(row.get("mapping_application_count", 0)),
            "unique_mapping_applications": _int(
                row.get("unique_mapping_applications", 0)
            ),
            "target_application_coverage": _float(
                row.get("target_application_coverage", 0.0)
            ),
            "application_lineage_sha256": str(
                row.get("vendor_application_lineage_sha256", "")
            ),
            "comparison": {
                "accepted": bool(row.get("comparison_accepted", False)),
                "failed_checks": _int(row.get("comparison_failed_checks", 0)),
            },
        },
        "broker_readiness": {
            "ready": bool(row.get("broker_readiness_ready", False)),
            "broker_vendor_data_ready": bool(row.get("broker_vendor_data_ready", False)),
            "adapter_schema_status": str(row.get("adapter_schema_status", "")),
            "schema_review_required": _bool(row.get("schema_review_required", False)),
            "schema_reviewed": _bool(row.get("schema_reviewed", False)),
            "schema_review_mode": str(row.get("schema_review_mode", "")),
            "placeholder_schema_active": _bool(row.get("placeholder_schema_active", False)),
            "placeholder_schema_allowed": _bool(row.get("placeholder_schema_allowed", False)),
            "vendor_market_data_batch": {
                "mapping_source_mode": str(
                    row.get("broker_vendor_mapping_source_mode", "")
                ),
                "mapping_application_count": _int(
                    row.get("broker_vendor_mapping_application_count", 0)
                ),
                "unique_mapping_applications": _int(
                    row.get("broker_vendor_unique_mapping_applications", 0)
                ),
                "target_application_coverage": _float(
                    row.get("broker_vendor_target_application_coverage", 0.0)
                ),
                "application_lineage_consistency_required": _bool(
                    row.get(
                        "broker_vendor_application_lineage_consistency_required",
                        False,
                    )
                ),
                "application_lineage_consistent": _bool(
                    row.get("broker_vendor_application_lineage_consistent", False)
                ),
                "current_vendor_lineage_match_required": _bool(
                    row.get("broker_vendor_lineage_match_required", False)
                ),
                "matches_current_vendor_lineage": _bool(
                    row.get("broker_vendor_lineage_matches", False)
                ),
                "application_lineage_sha256": str(
                    row.get("broker_vendor_application_lineage_sha256", "")
                ),
            },
            "resume_gate": _broker_readiness_resume_gate_config(row),
            "dispatch_roundtrip": _broker_readiness_dispatch_roundtrip_config(row),
        },
        "broker_thresholds": asdict(broker_thresholds),
        "failed_check_count": _int(row.get("failed_check_count", row.get("failed_checks", len(failed)))),
        "failed_checks": failed,
        "first_failed_reason": str(row.get("first_failed_reason", "")),
        "primary_blocker": primary_blocker,
        "ready_action_count": int(len(ready_actions)),
        "blocked_action_count": int(len(blocked_actions)),
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _action_value(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(ready_actions),
        "blocked_actions": _action_records(blocked_actions),
        "components": [
            {
                "component": str(component.get("component", "")),
                "ready": bool(component.get("ready", False)),
                "status": str(component.get("status", "")),
                "artifact_dir": str(component.get("artifact_dir", "")),
                "dataset_count": _int(component.get("dataset_count", 0)),
                "unique_source_files": _int(component.get("unique_source_files", 0)),
                "source_file_fingerprint_coverage": _float(
                    component.get("source_file_fingerprint_coverage", 0.0)
                ),
                "min_mapping_coverage": _float(component.get("min_mapping_coverage", 0.0)),
                "unique_mapping_drafts": _int(component.get("unique_mapping_drafts", 0)),
                "mapping_source_mode": str(component.get("mapping_source_mode", "")),
                "mapping_application_count": _int(
                    component.get("mapping_application_count", 0)
                ),
                "unique_mapping_applications": _int(
                    component.get("unique_mapping_applications", 0)
                ),
                "target_application_coverage": _float(
                    component.get("target_application_coverage", 0.0)
                ),
                "adapter_schema_status": str(component.get("adapter_schema_status", "")),
                "schema_reviewed": _bool(component.get("schema_reviewed", False)),
                "schema_review_mode": str(component.get("schema_review_mode", "")),
                "placeholder_schema_active": _bool(component.get("placeholder_schema_active", False)),
            }
            for component in components.to_dict(orient="records")
        ],
        "recommendation": str(row.get("recommendation", "")),
    }


def _broker_readiness_dispatch_roundtrip_config(row: pd.Series) -> dict[str, object]:
    return {
        "route_readiness": {
            "ready": _bool(row.get("broker_readiness_route_readiness_ready", False)),
            "strategy": str(row.get("broker_readiness_route_readiness_strategy", "")),
            "market": str(row.get("broker_readiness_route_readiness_market", "")),
            "gap_pairs": _int(row.get("broker_readiness_route_readiness_gap_pairs", 0)),
            "ops_launch_controls_present": _bool(
                row.get("broker_readiness_route_readiness_ops_launch_controls_present", False)
            ),
            "ops_launch_controls_blocked_pairs": _int(
                row.get("broker_readiness_route_readiness_ops_launch_controls_blocked_pairs", 0)
            ),
            "ops_broker_roundtrip_portfolio_breach_pairs": _int(
                row.get("broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0)
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": _int(
                row.get(
                    "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    0,
                )
            ),
        },
        "route_broker_route_readiness": {
            "provided": _bool(row.get("broker_readiness_route_broker_route_readiness_provided", False)),
            "ready": _bool(row.get("broker_readiness_route_broker_route_readiness_ready", False)),
            "strategy": str(row.get("broker_readiness_route_broker_route_readiness_strategy", "")),
            "market": str(row.get("broker_readiness_route_broker_route_readiness_market", "")),
            "gap_pairs": _int(row.get("broker_readiness_route_broker_route_readiness_gap_pairs", 0)),
            "ops_launch_controls_ready": _bool(
                row.get("broker_readiness_route_broker_route_readiness_ops_launch_controls_ready", False)
            ),
            "ops_broker_roundtrip_portfolio_safe_runs": _int(
                row.get(
                    "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": _int(
                row.get(
                    "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": _int(
                row.get(
                    "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": _int(
                row.get(
                    (
                        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "concentration_breach_runs"
                    ),
                    0,
                )
            ),
        },
    }


def _broker_readiness_resume_gate_config(row: pd.Series) -> dict[str, object]:
    return {
        "broker_route_readiness": {
            "provided": _bool(row.get("broker_readiness_resume_broker_route_readiness_provided", False)),
            "ready": _bool(row.get("broker_readiness_resume_broker_route_readiness_ready", False)),
            "strategy": str(row.get("broker_readiness_resume_broker_route_readiness_strategy", "")),
            "market": str(row.get("broker_readiness_resume_broker_route_readiness_market", "")),
            "gap_pairs": _int(row.get("broker_readiness_resume_broker_route_readiness_gap_pairs", 0)),
            "ops_launch_controls_ready": _bool(
                row.get("broker_readiness_resume_broker_route_readiness_ops_launch_controls_ready", False)
            ),
            "ops_broker_roundtrip_portfolio_safe_runs": _int(
                row.get(
                    "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": _int(
                row.get(
                    "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": _int(
                row.get(
                    (
                        "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "concentration_ok_runs"
                    ),
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": _int(
                row.get(
                    (
                        "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "concentration_breach_runs"
                    ),
                    0,
                )
            ),
        },
        "incident_broker_route_readiness": {
            "provided": _bool(row.get("broker_readiness_resume_incident_broker_route_readiness_provided", False)),
            "ready": _bool(row.get("broker_readiness_resume_incident_broker_route_readiness_ready", False)),
            "strategy": str(row.get("broker_readiness_resume_incident_broker_route_readiness_strategy", "")),
            "market": str(row.get("broker_readiness_resume_incident_broker_route_readiness_market", "")),
            "gap_pairs": _int(row.get("broker_readiness_resume_incident_broker_route_readiness_gap_pairs", 0)),
            "ops_launch_controls_ready": _bool(
                row.get("broker_readiness_resume_incident_broker_route_readiness_ops_launch_controls_ready", False)
            ),
            "ops_broker_roundtrip_portfolio_safe_runs": _int(
                row.get(
                    (
                        "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "safe_runs"
                    ),
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": _int(
                row.get(
                    (
                        "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "breach_runs"
                    ),
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": _int(
                row.get(
                    (
                        "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "concentration_ok_runs"
                    ),
                    0,
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": _int(
                row.get(
                    (
                        "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                        "concentration_breach_runs"
                    ),
                    0,
                )
            ),
        },
    }


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _is_placeholder_schema(value: object) -> bool:
    return str(value).strip() == PLACEHOLDER_SCHEMA_STATUS


def _placeholder_schema_warning(
    schema_status: object,
    *,
    schema_reviewed: bool,
    placeholder_allowed: bool,
) -> str:
    if not _is_placeholder_schema(schema_status):
        return ""
    if schema_reviewed:
        return "placeholder adapter schema backed by reviewed vendor mapping"
    if placeholder_allowed:
        return "placeholder adapter schema allowed for dry-run review only"
    return "placeholder adapter schema requires reviewed vendor mapping before broker readiness"


def _vendor_value(row: pd.Series, suffix: str, fallback: object) -> object:
    for prefix in _VENDOR_BATCH_PREFIXES:
        column = suffix if not prefix else f"{prefix}_{suffix}"
        if column in row.index:
            value = row.get(column, fallback)
            if not pd.isna(value):
                return value
    return fallback
