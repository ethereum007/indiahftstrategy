from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from adapters.broker_readiness import BrokerReadinessReport, BrokerReadinessThresholds, write_broker_readiness_report
from reports.data_readiness import DataReadinessThresholds
from reports.data_readiness_comparison import DataReadinessComparisonThresholds
from reports.manifest import write_experiment_manifest
from reports.vendor_data_onboarding import (
    VendorMarketDataBatchReport,
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
)


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
    tick_size: float | None = None
    require_all_mapped: bool = True
    min_rows: int = 1
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_out_of_session_rows: int = 0
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None


@dataclass(frozen=True)
class BrokerVendorDataReadinessReport:
    vendor_batch: VendorMarketDataBatchReport
    broker_readiness: BrokerReadinessReport
    components: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

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
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    vendor_batch_dir = out / "01_vendor_market_data_batch"
    broker_readiness_dir = out / "02_broker_readiness"

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
        tick_size=config.tick_size,
        require_all_mapped=config.require_all_mapped,
        min_rows=config.min_rows,
        max_crossed_quote_rows=config.max_crossed_quote_rows,
        max_nonpositive_quote_rows=config.max_nonpositive_quote_rows,
        max_nonpositive_depth_rows=config.max_nonpositive_depth_rows,
        max_out_of_session_rows=config.max_out_of_session_rows,
        max_p99_gap_ns=config.max_p99_gap_ns,
        max_median_spread_ticks=config.max_median_spread_ticks,
    )
    vendor_batch = write_vendor_market_data_batch_pipeline(
        input_paths,
        output_dir=vendor_batch_dir,
        labels=labels,
        mapping_path=mapping_path,
        config=vendor_config,
        readiness_thresholds=readiness_thresholds,
        comparison_thresholds=comparison_thresholds,
    )
    broker_thresholds = broker_thresholds or BrokerReadinessThresholds(
        adapter=config.adapter,
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
    summary = _summary(components, vendor_batch, broker_readiness, config)
    components.to_csv(out / "broker_vendor_data_readiness_components.csv", index=False)
    summary.to_csv(out / "broker_vendor_data_readiness_summary.csv", index=False)
    (out / "broker_vendor_data_readiness_config.json").write_text(
        json.dumps(_config(summary.iloc[0], components, config, broker_thresholds), indent=2, sort_keys=True) + "\n",
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
        },
        inputs={
            "inputs": [Path(path) for path in input_paths],
            "mapping": Path(mapping_path) if mapping_path is not None else None,
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
            "vendor_market_data_batch": vendor_batch_dir,
            "broker_readiness": broker_readiness_dir,
        },
    )
    return BrokerVendorDataReadinessReport(vendor_batch, broker_readiness, components, summary, out)


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
        "dataset_count": _int(row.get("dataset_count", 0)),
        "failed_checks": _int(row.get("failed_checks", row.get("comparison_failed_checks", 0))),
        "recommendation": str(row.get("recommendation", "")),
    }


def _summary(
    components: pd.DataFrame,
    vendor_batch: VendorMarketDataBatchReport,
    broker_readiness: BrokerReadinessReport,
    config: BrokerVendorDataReadinessConfig,
) -> pd.DataFrame:
    vendor_row = vendor_batch.summary.iloc[0] if not vendor_batch.summary.empty else pd.Series(dtype=object)
    broker_row = broker_readiness.summary.iloc[0] if not broker_readiness.summary.empty else pd.Series(dtype=object)
    ready = bool(vendor_batch.ready and broker_readiness.ready)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "kind": config.kind,
                "market": config.market,
                "vendor_batch_ready": bool(vendor_batch.ready),
                "broker_readiness_ready": bool(broker_readiness.ready),
                "dataset_count": _int(vendor_row.get("dataset_count", 0)),
                "ready_datasets": _int(vendor_row.get("ready_datasets", 0)),
                "failed_datasets": _int(vendor_row.get("failed_datasets", 0)),
                "unique_source_files": _int(vendor_row.get("unique_source_files", 0)),
                "broker_vendor_data_ready": bool(
                    broker_row.get("broker_dispatch_roundtrip_vendor_market_data_batch_ready", False)
                ),
                "failed_components": int((~components["ready"].astype(bool)).sum()) if not components.empty else 0,
                "recommendation": "broker_data_proof_ready" if ready else "fix_vendor_or_broker_readiness_proof",
            }
        ]
    )


def _config(
    row: pd.Series,
    components: pd.DataFrame,
    config: BrokerVendorDataReadinessConfig,
    broker_thresholds: BrokerReadinessThresholds,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ready": bool(row.get("ready", False)),
        "adapter": config.adapter,
        "kind": config.kind,
        "market": config.market,
        "broker_thresholds": asdict(broker_thresholds),
        "components": [
            {
                "component": str(component.get("component", "")),
                "ready": bool(component.get("ready", False)),
                "status": str(component.get("status", "")),
                "artifact_dir": str(component.get("artifact_dir", "")),
            }
            for component in components.to_dict(orient="records")
        ],
        "recommendation": str(row.get("recommendation", "")),
    }


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0
