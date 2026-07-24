from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.applied_mapped_data import (
    AppliedMappedDataConfig,
    AppliedMappedDataReport,
    write_applied_mapped_data_normalization,
)
from adapters.mapped_data import MappedDataConfig, MappedDataReport, write_mapped_data_normalization
from adapters.reviewed_mapped_data import (
    ApprovedMappingReviewInputs,
    ReviewedMappedDataConfig,
    ReviewedMappedDataReport,
    approved_mapping_review_inputs,
    write_reviewed_mapped_data_normalization,
)
from adapters.vendor_intake import VendorCsvIntakeConfig, VendorCsvIntakeReport, write_vendor_csv_intake_report
from adapters.vendor_mapping_application import (
    ApprovedVendorMappingApplicationInputs,
    RECEIPT_FILE as MAPPING_APPLICATION_RECEIPT_FILE,
    approved_vendor_mapping_application_inputs,
)
from data.diagnostics import DiagnosticResult, chain_diagnostics, tick_diagnostics, write_diagnostics
from markets.calendars import market_calendar_summary, resolve_market_calendar
from markets.expiries import load_nse_fo_expiry_rule
from markets.lot_sizes import load_nse_index_lot_rule
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.data_readiness import DataReadinessReport, DataReadinessThresholds, write_data_readiness_report
from reports.data_readiness_comparison import (
    DataReadinessComparisonReport,
    DataReadinessComparisonThresholds,
    write_data_readiness_comparison,
)
from reports.manifest import MANIFEST_NAME, write_experiment_manifest
from reports.market_calendar import write_market_calendar_report


@dataclass(frozen=True)
class VendorMarketDataPipelineConfig:
    adapter: str = "arrow_money"
    kind: str = "ticks"
    sample_rows: int = 1000
    min_mapping_coverage: float = 1.0
    output_filename: str | None = None
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    filter_session: bool = True
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    market_calendar_path: str | None = None
    expiry_cycle: str | None = None
    underlying: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None
    require_all_mapped: bool = True
    min_rows: int = 1
    min_chain_expiry_snapshots: int = 1
    min_chain_snapshots_per_expiry: int = 1
    min_chain_snapshot_strikes: int = 1
    max_null_rows: int = 0
    max_nonfinite_rows: int = 0
    max_nonintegral_rows: int = 0
    max_duplicate_tick_rows: int = 0
    max_integer_overflow_rows: int = 0
    max_nonmonotonic_rows: int = 0
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_invalid_trade_rows: int = 0
    max_off_tick_price_rows: int | None = None
    max_non_trading_day_rows: int = 0
    max_out_of_session_rows: int = 0
    max_unparseable_contract_expiry_rows: int = 0
    max_expired_contract_rows: int = 0
    max_duplicate_contract_key_rows: int = 0
    max_conflicting_contract_key_rows: int = 0
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None
    max_chain_snapshot_p99_gap_ns: float | None = None


@dataclass(frozen=True)
class VendorMarketDataPipelineReport:
    components: pd.DataFrame
    summary: pd.DataFrame
    intake: VendorCsvIntakeReport
    mapped_data: MappedDataReport | ReviewedMappedDataReport | AppliedMappedDataReport
    diagnostics: DiagnosticResult
    readiness: DataReadinessReport
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


@dataclass(frozen=True)
class VendorMarketDataBatchReport:
    datasets: pd.DataFrame
    summary: pd.DataFrame
    comparison: DataReadinessComparisonReport
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_vendor_market_data_pipeline(
    input_path: str | Path,
    *,
    output_dir: str | Path,
    mapping_path: str | Path | None = None,
    mapping_review_dir: str | Path | None = None,
    mapping_application_dir: str | Path | None = None,
    config: VendorMarketDataPipelineConfig | None = None,
    readiness_thresholds: DataReadinessThresholds | None = None,
) -> VendorMarketDataPipelineReport:
    config = config or VendorMarketDataPipelineConfig()
    _validate_config(config)
    mapping_modes = (mapping_path, mapping_review_dir, mapping_application_dir)
    if sum(value is not None for value in mapping_modes) > 1:
        raise ValueError(
            "mapping_path, mapping_review_dir, and mapping_application_dir are mutually exclusive"
        )
    source_file = Path(input_path).resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"vendor market-data input not found: {source_file}")
    approved_review = (
        approved_mapping_review_inputs(mapping_review_dir)
        if mapping_review_dir is not None
        else None
    )
    approved_application = (
        approved_vendor_mapping_application_inputs(mapping_application_dir)
        if mapping_application_dir is not None
        else None
    )
    if approved_review is not None:
        _validate_review_binding(source_file, Path(output_dir), config, approved_review)
    if approved_application is not None:
        _validate_application_binding(
            source_file,
            Path(output_dir),
            config,
            approved_application,
        )
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    intake_dir = out / "01_vendor_intake"
    mapped_dir = out / "02_normalized"
    diagnostics_dir = out / "03_diagnostics"
    readiness_dir = out / "04_data_readiness"
    calendar_dir = out / "00_market_calendar"

    if config.market_calendar_path:
        write_market_calendar_report(
            config.market_calendar_path,
            calendar_dir,
            expected_market=config.market,
        )

    intake = write_vendor_csv_intake_report(
        source_file,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(
            adapter=config.adapter,
            kind=config.kind,
            sample_rows=config.sample_rows,
            min_mapping_coverage=config.min_mapping_coverage,
            output_mapping_file="vendor_mapping_draft.csv",
        ),
    )
    if approved_application is not None:
        mapping_source = "verified_target_application"
        mapping_file = approved_application.applied_mapping_path
        mapped = write_applied_mapped_data_normalization(
            approved_application.application_dir,
            output_dir=mapped_dir,
            config=AppliedMappedDataConfig(
                output_filename=_output_filename(config),
                timestamp_unit=config.timestamp_unit,
                timestamp_tz=config.timestamp_tz,
                filter_session=config.filter_session,
                market=config.market,
                market_calendar_path=config.market_calendar_path,
                require_all_mapped=config.require_all_mapped,
            ),
        )
    elif approved_review is not None:
        mapping_source = "verified_approved_review"
        mapping_file = approved_review.reviewed_mapping_path
        mapped = write_reviewed_mapped_data_normalization(
            approved_review.mapping_review_dir,
            output_dir=mapped_dir,
            config=ReviewedMappedDataConfig(
                output_filename=_output_filename(config),
                timestamp_unit=config.timestamp_unit,
                timestamp_tz=config.timestamp_tz,
                filter_session=config.filter_session,
                market=config.market,
                market_calendar_path=config.market_calendar_path,
                require_all_mapped=config.require_all_mapped,
            ),
        )
    else:
        mapping_source = "provided" if mapping_path is not None else "vendor_intake_draft"
        mapping_file = Path(mapping_path) if mapping_path is not None else intake_dir / "vendor_mapping_draft.csv"
        mapped = write_mapped_data_normalization(
            source_file,
            mapping_file,
            output_dir=mapped_dir,
            config=MappedDataConfig(
                adapter=config.adapter,
                kind=config.kind,
                output_filename=_output_filename(config),
                timestamp_unit=config.timestamp_unit,
                timestamp_tz=config.timestamp_tz,
                filter_session=config.filter_session,
                market=config.market,
                market_calendar_path=config.market_calendar_path,
                require_all_mapped=config.require_all_mapped,
            ),
        )
    diagnostics = _write_diagnostics(mapped.data, diagnostics_dir, config)
    thresholds = readiness_thresholds or _readiness_thresholds(config)
    if config.market_calendar_path:
        thresholds = replace(thresholds, require_market_calendar=True)
    if approved_application is not None:
        thresholds = replace(
            thresholds,
            require_mapped_data=True,
            require_reviewed_mapping_normalization=False,
            require_target_application_normalization=True,
        )
    elif approved_review is not None:
        thresholds = replace(
            thresholds,
            require_mapped_data=True,
            require_reviewed_mapping_normalization=True,
            require_target_application_normalization=False,
        )
    readiness = write_data_readiness_report(
        output_dir=readiness_dir,
        market_calendar_dir=calendar_dir if config.market_calendar_path else None,
        vendor_intake_dir=intake_dir,
        mapped_data_dir=mapped_dir,
        tick_diagnostics_dir=diagnostics_dir if config.kind == "ticks" else None,
        chain_diagnostics_dir=diagnostics_dir if config.kind == "chain" else None,
        thresholds=thresholds,
    )
    components = _components(
        intake,
        mapped,
        diagnostics,
        readiness,
        intake_accepted_by_review=approved_review is not None,
        intake_accepted_by_application=approved_application is not None,
    )
    action_queue = _pipeline_action_queue(components, readiness.action_queue)
    summary = _summary(
        source_file,
        mapping_file,
        components,
        intake,
        mapped,
        diagnostics,
        readiness,
        config,
        mapping_source=mapping_source,
        intake_dir=intake_dir,
        mapped_dir=mapped_dir,
        readiness_dir=readiness_dir,
        action_queue=action_queue,
        approved_review=approved_review,
        approved_application=approved_application,
    )
    components.to_csv(out / "vendor_market_data_pipeline_components.csv", index=False)
    summary.to_csv(out / "vendor_market_data_pipeline_summary.csv", index=False)
    action_queue.to_csv(out / "vendor_market_data_pipeline_action_queue.csv", index=False)
    (out / "vendor_market_data_pipeline_runbook.md").write_text(
        _pipeline_runbook_markdown(summary.iloc[0], components, action_queue),
        encoding="utf-8",
    )
    pipeline_config = _pipeline_config(summary.iloc[0], components, action_queue, thresholds, config)
    (out / "vendor_market_data_pipeline_config.json").write_text(
        json.dumps(pipeline_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if approved_application is not None:
        final_application = approved_vendor_mapping_application_inputs(
            approved_application.application_dir
        )
        if final_application != approved_application:
            raise RuntimeError(
                "mapping application graph changed during vendor market-data pipeline"
            )
    inputs: dict[str, Any] = {
        "input": source_file,
        "mapping": mapping_file,
    }
    if config.market_calendar_path:
        inputs["market_calendar"] = Path(config.market_calendar_path)
    inputs.update(_contract_expiry_inputs(config))
    if approved_review is not None:
        inputs.update(
            {
                "mapping_review": approved_review.mapping_review_dir,
                "mapping_review_manifest": approved_review.mapping_review_dir / "manifest.json",
                "mapping_review_receipt": (
                    approved_review.mapping_review_dir
                    / "vendor_mapping_review_receipt.json"
                ),
            }
        )
    if approved_application is not None:
        inputs.update(
            {
                "mapping_application": approved_application.application_dir,
                "mapping_application_manifest": (
                    approved_application.application_dir / MANIFEST_NAME
                ),
                "mapping_application_receipt": (
                    approved_application.application_dir
                    / MAPPING_APPLICATION_RECEIPT_FILE
                ),
                "mapping_scope_review": approved_application.scope_review_dir,
                "target_intake": approved_application.target_intake_dir,
                "target_source": approved_application.target_source_path,
                "applied_mapping": approved_application.applied_mapping_path,
            }
        )
    inputs.update(
        _existing_paths(
            vendor_intake_manifest=intake_dir / "manifest.json",
            vendor_intake_source_profile=intake_dir / "vendor_intake_source_profile.json",
            mapped_data_manifest=mapped_dir / "manifest.json",
            data_readiness_manifest=readiness_dir / "manifest.json",
        )
    )
    write_experiment_manifest(
        out,
        run_type="vendor_market_data_pipeline",
        parameters={
            "config": asdict(config),
            "readiness_thresholds": asdict(thresholds),
            "mapping_source": mapping_source,
        },
        inputs=inputs,
    )
    return VendorMarketDataPipelineReport(components, summary, intake, mapped, diagnostics, readiness, out, action_queue)


def write_vendor_market_data_batch_pipeline(
    input_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    mapping_path: str | Path | None = None,
    mapping_application_dirs: list[str | Path] | None = None,
    config: VendorMarketDataPipelineConfig | None = None,
    readiness_thresholds: DataReadinessThresholds | None = None,
    comparison_thresholds: DataReadinessComparisonThresholds | None = None,
) -> VendorMarketDataBatchReport:
    config = config or VendorMarketDataPipelineConfig()
    _validate_config(config)
    paths = [Path(path) for path in input_paths]
    if not paths:
        raise ValueError("at least one vendor market-data input is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match input paths")
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"vendor market-data input not found: {path}")
    if mapping_path is not None and mapping_application_dirs is not None:
        raise ValueError(
            "mapping_path and mapping_application_dirs are mutually exclusive"
        )
    if (
        mapping_application_dirs is not None
        and len(mapping_application_dirs) != len(paths)
    ):
        raise ValueError("mapping applications must match input paths one for one")

    resolved_labels = [
        labels[idx] if labels is not None else path.stem
        for idx, path in enumerate(paths)
    ]
    safe_labels = [_safe_label(label, idx) for idx, label in enumerate(resolved_labels)]
    if len(set(safe_labels)) != len(safe_labels):
        raise ValueError("labels must resolve to unique dataset directories")

    out = Path(output_dir).resolve()
    application_roots = (
        [Path(application_dir).resolve() for application_dir in mapping_application_dirs]
        if mapping_application_dirs is not None
        else []
    )
    if len(set(application_roots)) != len(application_roots):
        raise ValueError("mapping applications must be distinct per dataset")
    approved_applications = (
        [
            approved_vendor_mapping_application_inputs(application_dir)
            for application_dir in application_roots
        ]
        if application_roots
        else []
    )
    if approved_applications:
        for path, application in zip(paths, approved_applications, strict=True):
            _validate_application_binding(path.resolve(), out, config, application)

    effective_readiness_thresholds = readiness_thresholds or _readiness_thresholds(config)
    if approved_applications:
        effective_readiness_thresholds = replace(
            effective_readiness_thresholds,
            require_mapped_data=True,
            require_reviewed_mapping_normalization=False,
            require_target_application_normalization=True,
        )
    batch_mapping_source = (
        "per_dataset_verified_target_application"
        if approved_applications
        else "provided"
        if mapping_path is not None
        else "per_dataset_vendor_intake_draft"
    )

    out.mkdir(parents=True, exist_ok=True)
    dataset_rows = []
    dataset_manifest_paths = []
    dataset_action_rows = []
    readiness_dirs = []
    comparison_labels = []
    for idx, path in enumerate(paths):
        label = resolved_labels[idx]
        dataset_dir = out / "datasets" / safe_labels[idx]
        approved_application = (
            approved_applications[idx]
            if approved_applications
            else None
        )
        report = write_vendor_market_data_pipeline(
            path,
            output_dir=dataset_dir,
            mapping_path=mapping_path,
            mapping_application_dir=(
                approved_application.application_dir
                if approved_application is not None
                else None
            ),
            config=config,
            readiness_thresholds=effective_readiness_thresholds,
        )
        dataset_action_rows.extend(
            _promote_action_rows(
                report.action_queue,
                source="dataset_pipeline",
                dataset=label,
                pipeline_dir=dataset_dir,
            )
        )
        readiness_dir = dataset_dir / "04_data_readiness"
        readiness_dirs.append(readiness_dir)
        comparison_labels.append(label)
        dataset_manifest_path = dataset_dir / "manifest.json"
        if dataset_manifest_path.exists():
            dataset_manifest_paths.append(dataset_manifest_path)
        row = report.summary.iloc[0] if not report.summary.empty else pd.Series(dtype=object)
        dataset_rows.append(
            {
                "dataset": label,
                "input_path": str(path),
                "pipeline_dir": str(dataset_dir),
                "data_readiness_dir": str(readiness_dir),
                "ready": bool(report.ready),
                "normalized_rows": int(_number(row, "normalized_rows", fallback=0.0)),
                "failed_components": int(_number(row, "failed_components", fallback=1.0)),
                "dropped_null_rows": int(
                    _number(row, "dropped_null_rows", fallback=0.0)
                ),
                "dropped_nonfinite_rows": int(
                    _number(row, "dropped_nonfinite_rows", fallback=0.0)
                ),
                "dropped_nonintegral_rows": int(
                    _number(row, "dropped_nonintegral_rows", fallback=0.0)
                ),
                "dropped_duplicate_rows": int(
                    _number(row, "dropped_duplicate_rows", fallback=0.0)
                ),
                "dropped_integer_overflow_rows": int(
                    _number(
                        row,
                        "dropped_integer_overflow_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_nonmonotonic_rows": int(
                    _number(row, "dropped_nonmonotonic_rows", fallback=0.0)
                ),
                "dropped_negative_depth_rows": int(
                    _number(row, "dropped_negative_depth_rows", fallback=0.0)
                ),
                "dropped_invalid_trade_rows": int(
                    _number(row, "dropped_invalid_trade_rows", fallback=0.0)
                ),
                "price_grid_validation_enabled": _truthy(
                    row.get("price_grid_validation_enabled", False)
                ),
                "price_grid_tick_size": _number(
                    row,
                    "price_grid_tick_size",
                    fallback=float("nan"),
                ),
                "off_tick_price_rows": int(
                    _number(row, "off_tick_price_rows", fallback=0.0)
                ),
                "dropped_calendar_closed_rows": int(
                    _number(row, "dropped_calendar_closed_rows", fallback=0.0)
                ),
                "dropped_calendar_out_of_range_rows": int(
                    _number(
                        row,
                        "dropped_calendar_out_of_range_rows",
                        fallback=0.0,
                    )
                ),
                "source_file_sha256": _text(row, "source_file_sha256"),
                "source_header_sha256": _text(row, "source_header_sha256"),
                "mapping_draft_sha256": _text(row, "mapping_draft_sha256"),
                "market_calendar_id": _text(row, "market_calendar_id"),
                "market_calendar_sha256": _text(
                    row,
                    "market_calendar_sha256",
                ),
                "market_calendar_valid_from": _text(
                    row,
                    "market_calendar_valid_from",
                ),
                "market_calendar_valid_to": _text(
                    row,
                    "market_calendar_valid_to",
                ),
                "mapping_source": _text(row, "mapping_source"),
                "mapping_application_path": _text(row, "mapping_application_path"),
                "mapping_application_id": _text(row, "mapping_application_id"),
                "mapping_application_sha256": _text(
                    row,
                    "mapping_application_sha256",
                ),
                "mapping_scope_review_id": _text(row, "mapping_scope_review_id"),
                "mapping_scope_review_sha256": _text(
                    row,
                    "mapping_scope_review_sha256",
                ),
                "target_intake_receipt_id": _text(row, "target_intake_receipt_id"),
                "applied_mapping_sha256": _text(row, "applied_mapping_sha256"),
                "data_readiness_manifest_path": _text(row, "data_readiness_manifest_path"),
                "recommendation": str(row.get("recommendation", "")),
            }
        )

    thresholds = comparison_thresholds or DataReadinessComparisonThresholds(
        min_datasets=len(paths),
        min_ready_datasets=len(paths),
        min_ready_rate=1.0,
        max_total_failed_checks=0,
        min_unique_source_files=len(paths),
        min_source_file_fingerprint_coverage=1.0,
        min_mapping_coverage=config.min_mapping_coverage,
        require_market_calendar=bool(config.market_calendar_path),
        require_consistent_market_calendar=bool(config.market_calendar_path),
    )
    if config.market_calendar_path:
        thresholds = replace(
            thresholds,
            require_market_calendar=True,
            require_consistent_market_calendar=True,
        )
    comparison = write_data_readiness_comparison(
        readiness_dirs,
        output_dir=out / "comparison",
        labels=comparison_labels,
        thresholds=thresholds,
    )
    datasets = pd.DataFrame(dataset_rows)
    action_queue = _batch_action_queue(dataset_action_rows, comparison.action_queue)
    summary = _batch_summary(datasets, comparison, config)
    summary["mapping_source_mode"] = batch_mapping_source
    summary["blocked_action_count"] = int(len(action_queue))
    summary["ready_action_count"] = 0
    summary["next_gate"] = _primary_next_gate(action_queue)
    summary["next_gate_help_command"] = summary["next_gate"].map(_next_gate_help_command)
    if approved_applications:
        final_applications = [
            approved_vendor_mapping_application_inputs(application.application_dir)
            for application in approved_applications
        ]
        if final_applications != approved_applications:
            raise RuntimeError(
                "mapping application graph changed during vendor market-data batch"
            )
    datasets.to_csv(out / "vendor_market_data_batch_datasets.csv", index=False)
    summary.to_csv(out / "vendor_market_data_batch_summary.csv", index=False)
    action_queue.to_csv(out / "vendor_market_data_batch_action_queue.csv", index=False)
    (out / "vendor_market_data_batch_runbook.md").write_text(
        _batch_runbook_markdown(summary.iloc[0], datasets, action_queue),
        encoding="utf-8",
    )
    batch_config = _batch_config(
        summary.iloc[0],
        datasets,
        action_queue,
        thresholds,
        effective_readiness_thresholds,
        config,
    )
    (out / "vendor_market_data_batch_config.json").write_text(
        json.dumps(batch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"inputs": paths}
    if config.market_calendar_path:
        inputs["market_calendar"] = Path(config.market_calendar_path)
    inputs.update(_contract_expiry_inputs(config))
    if mapping_path is not None:
        inputs["mapping"] = mapping_path
    if approved_applications:
        inputs.update(
            {
                "mapping_applications": [
                    application.application_dir
                    for application in approved_applications
                ],
                "mapping_application_manifests": [
                    application.application_dir / MANIFEST_NAME
                    for application in approved_applications
                ],
                "mapping_application_receipts": [
                    application.application_dir / MAPPING_APPLICATION_RECEIPT_FILE
                    for application in approved_applications
                ],
                "mapping_scope_reviews": [
                    application.scope_review_dir
                    for application in approved_applications
                ],
                "target_intakes": [
                    application.target_intake_dir
                    for application in approved_applications
                ],
                "target_sources": [
                    application.target_source_path
                    for application in approved_applications
                ],
                "applied_mappings": [
                    application.applied_mapping_path
                    for application in approved_applications
                ],
            }
        )
    inputs.update(
        _existing_paths(
            comparison_manifest=out / "comparison" / "manifest.json",
        )
    )
    if dataset_manifest_paths:
        inputs["dataset_manifests"] = dataset_manifest_paths
    write_experiment_manifest(
        out,
        run_type="vendor_market_data_batch_pipeline",
        parameters={
            "config": asdict(config),
            "readiness_thresholds": asdict(effective_readiness_thresholds),
            "comparison_thresholds": asdict(thresholds),
            "labels": labels,
            "mapping_source": batch_mapping_source,
        },
        inputs=inputs,
    )
    return VendorMarketDataBatchReport(datasets, summary, comparison, out, action_queue)


def _write_diagnostics(data: pd.DataFrame, output_dir: Path, config: VendorMarketDataPipelineConfig) -> DiagnosticResult:
    if config.kind == "ticks":
        return write_diagnostics(
            tick_diagnostics(
                data,
                tick_size=config.tick_size,
                market=config.market,
                market_calendar=config.market_calendar_path,
            ),
            output_dir,
        )
    if config.kind == "chain":
        return write_diagnostics(
            chain_diagnostics(
                data,
                tick_size=config.tick_size,
                market=config.market,
                market_calendar=config.market_calendar_path,
                expiry_cycle=config.expiry_cycle,
                underlying=config.underlying,
                lot_size=config.lot_size,
            ),
            output_dir,
        )
    raise ValueError("vendor market-data pipeline kind must be ticks or chain")


def _contract_expiry_inputs(
    config: VendorMarketDataPipelineConfig,
) -> dict[str, Path]:
    inputs: dict[str, Path] = {}
    if config.expiry_cycle:
        expiry_rule = load_nse_fo_expiry_rule()
        inputs.update(
            {
                "contract_expiry_rule": expiry_rule.config_path,
                "contract_expiry_authority_source": (
                    expiry_rule.authority_source_path
                ),
            }
        )
    if config.underlying is not None or config.lot_size is not None:
        lot_rule = load_nse_index_lot_rule()
        inputs.update(
            {
                "contract_lot_rule": lot_rule.config_path,
                "contract_lot_authority_source": (
                    lot_rule.authority_source_path
                ),
                "contract_lot_snapshot": lot_rule.snapshot_path,
            }
        )
    return inputs


def _readiness_thresholds(config: VendorMarketDataPipelineConfig) -> DataReadinessThresholds:
    return DataReadinessThresholds(
        require_market_calendar=bool(config.market_calendar_path),
        require_vendor_intake=True,
        require_mapped_data=True,
        require_tick_diagnostics=config.kind == "ticks",
        require_chain_diagnostics=config.kind == "chain",
        require_contract_expiry_validation=bool(config.expiry_cycle),
        require_contract_lot_validation=bool(
            config.underlying is not None and config.lot_size is not None
        ),
        expected_adapter=config.adapter,
        expected_vendor_data_kind=config.kind,
        min_tick_rows=config.min_rows,
        min_chain_rows=config.min_rows,
        min_chain_expiry_snapshots=config.min_chain_expiry_snapshots,
        min_chain_snapshots_per_expiry=(
            config.min_chain_snapshots_per_expiry
        ),
        min_chain_snapshot_strikes=config.min_chain_snapshot_strikes,
        max_null_rows=config.max_null_rows,
        max_nonfinite_rows=config.max_nonfinite_rows,
        max_nonintegral_rows=config.max_nonintegral_rows,
        max_duplicate_tick_rows=config.max_duplicate_tick_rows,
        max_integer_overflow_rows=config.max_integer_overflow_rows,
        max_nonmonotonic_rows=config.max_nonmonotonic_rows,
        max_crossed_quote_rows=config.max_crossed_quote_rows,
        max_nonpositive_quote_rows=config.max_nonpositive_quote_rows,
        max_nonpositive_depth_rows=config.max_nonpositive_depth_rows,
        max_invalid_trade_rows=config.max_invalid_trade_rows,
        max_off_tick_price_rows=config.max_off_tick_price_rows,
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
        max_tick_p99_gap_ns=config.max_p99_gap_ns if config.kind == "ticks" else None,
        max_tick_median_spread_ticks=config.max_median_spread_ticks if config.kind == "ticks" else None,
        max_chain_median_spread_ticks=config.max_median_spread_ticks if config.kind == "chain" else None,
        max_chain_snapshot_p99_gap_ns=(
            config.max_chain_snapshot_p99_gap_ns
            if config.kind == "chain"
            else None
        ),
    )


def _components(
    intake: VendorCsvIntakeReport,
    mapped: MappedDataReport | ReviewedMappedDataReport | AppliedMappedDataReport,
    diagnostics: DiagnosticResult,
    readiness: DataReadinessReport,
    *,
    intake_accepted_by_review: bool = False,
    intake_accepted_by_application: bool = False,
) -> pd.DataFrame:
    intake_ready = bool(
        intake.ready
        or intake_accepted_by_review
        or intake_accepted_by_application
    )
    intake_row = _first(intake.summary).copy()
    if intake_accepted_by_application and not intake.ready:
        intake_row["recommendation"] = "accepted_by_verified_target_application"
    elif intake_accepted_by_review and not intake.ready:
        intake_row["recommendation"] = "accepted_by_verified_mapping_review"
    rows = [
        _component("vendor_intake", intake_ready, intake.output_dir, intake_row),
        _component("mapped_data", mapped.ready, mapped.output_dir, _first(mapped.summary)),
        _component("diagnostics", _diagnostics_ready(diagnostics), diagnostics.output_dir, _diagnostic_overall(diagnostics)),
        _component("data_readiness", readiness.ready, readiness.output_dir, _first(readiness.summary)),
    ]
    return pd.DataFrame(rows)


def _component(name: str, ready: bool, output_dir: Path | None, row: pd.Series) -> dict[str, Any]:
    row_count = _number(
        row,
        "rows",
        fallback=_number(row, "output_rows", fallback=_number(row, "sampled_rows", fallback=0.0)),
    )
    failed_checks = _number(
        row,
        "failed_checks",
        fallback=_number(row, "failed_mappings", fallback=_number(row, "unmapped_required_columns", fallback=0.0)),
    )
    return {
        "component": name,
        "status": "ready" if ready else "not_ready",
        "ready": bool(ready),
        "output_dir": str(output_dir or ""),
        "rows": int(row_count),
        "failed_checks": int(failed_checks),
        "recommendation": str(row.get("recommendation", "")),
    }


def _summary(
    source_file: Path,
    mapping_file: Path,
    components: pd.DataFrame,
    intake: VendorCsvIntakeReport,
    mapped: MappedDataReport | ReviewedMappedDataReport | AppliedMappedDataReport,
    diagnostics: DiagnosticResult,
    readiness: DataReadinessReport,
    config: VendorMarketDataPipelineConfig,
    *,
    mapping_source: str,
    intake_dir: Path,
    mapped_dir: Path,
    readiness_dir: Path,
    action_queue: pd.DataFrame,
    approved_review: ApprovedMappingReviewInputs | None,
    approved_application: ApprovedVendorMappingApplicationInputs | None,
) -> pd.DataFrame:
    failed = int((~components["ready"].astype(bool)).sum()) if not components.empty else 1
    intake_row = _first(intake.summary)
    mapped_row = _first(mapped.summary)
    diagnostic_row = _diagnostic_overall(diagnostics)
    next_gate = _primary_next_gate(action_queue)
    calendar = resolve_market_calendar(
        config.market_calendar_path,
        market=config.market,
    )
    return pd.DataFrame(
        [
            {
                "ready": bool(readiness.ready and failed == 0),
                "adapter": config.adapter,
                "kind": config.kind,
                "market": config.market,
                **market_calendar_summary(calendar),
                "input_path": str(source_file),
                "mapping_path": str(mapping_file),
                "mapping_source": mapping_source,
                "mapping_review_path": str(
                    approved_review.mapping_review_dir if approved_review is not None else ""
                ),
                "mapping_review_id": (
                    approved_review.mapping_review_id if approved_review is not None else ""
                ),
                "mapping_review_sha256": (
                    approved_review.mapping_review_sha256 if approved_review is not None else ""
                ),
                "mapping_application_path": str(
                    approved_application.application_dir
                    if approved_application is not None
                    else ""
                ),
                "mapping_application_id": (
                    approved_application.mapping_application_id
                    if approved_application is not None
                    else ""
                ),
                "mapping_application_sha256": (
                    approved_application.mapping_application_sha256
                    if approved_application is not None
                    else ""
                ),
                "mapping_scope_review_path": str(
                    approved_application.scope_review_dir
                    if approved_application is not None
                    else ""
                ),
                "mapping_scope_review_id": (
                    approved_application.mapping_scope_review_id
                    if approved_application is not None
                    else ""
                ),
                "mapping_scope_review_sha256": (
                    approved_application.mapping_scope_review_sha256
                    if approved_application is not None
                    else ""
                ),
                "target_intake_path": str(
                    approved_application.target_intake_dir
                    if approved_application is not None
                    else ""
                ),
                "target_intake_receipt_id": (
                    approved_application.target_intake_receipt_id
                    if approved_application is not None
                    else ""
                ),
                "applied_mapping_sha256": (
                    approved_application.reviewed_mapping_sha256
                    if approved_application is not None
                    else ""
                ),
                "normalized_output_file": _output_filename(config),
                "source_columns": int(_number(intake_row, "source_columns", fallback=0.0)),
                "source_file_sha256": _text(intake_row, "source_file_sha256"),
                "source_header_sha256": _text(intake_row, "source_header_sha256"),
                "mapping_draft_sha256": _text(intake_row, "mapping_draft_sha256"),
                "mapping_coverage": _number(intake_row, "mapping_coverage", fallback=0.0),
                "input_rows": int(_number(mapped_row, "input_rows", fallback=0.0)),
                "normalized_rows": int(_number(mapped_row, "output_rows", fallback=0.0)),
                "dropped_null_rows": int(
                    _number(
                        mapped_row,
                        "dropped_null_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_nonfinite_rows": int(
                    _number(
                        mapped_row,
                        "dropped_nonfinite_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_nonintegral_rows": int(
                    _number(
                        mapped_row,
                        "dropped_nonintegral_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_duplicate_rows": int(
                    _number(
                        mapped_row,
                        "dropped_duplicate_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_integer_overflow_rows": int(
                    _number(
                        mapped_row,
                        "dropped_integer_overflow_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_nonmonotonic_rows": int(
                    _number(mapped_row, "dropped_nonmonotonic_rows", fallback=0.0)
                ),
                "dropped_negative_depth_rows": int(
                    _number(mapped_row, "dropped_negative_depth_rows", fallback=0.0)
                ),
                "dropped_invalid_trade_rows": int(
                    _number(mapped_row, "dropped_invalid_trade_rows", fallback=0.0)
                ),
                "dropped_non_trading_day_rows": int(
                    _number(
                        mapped_row,
                        "dropped_non_trading_day_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_calendar_closed_rows": int(
                    _number(
                        mapped_row,
                        "dropped_calendar_closed_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_calendar_out_of_range_rows": int(
                    _number(
                        mapped_row,
                        "dropped_calendar_out_of_range_rows",
                        fallback=0.0,
                    )
                ),
                "dropped_out_of_session_rows": int(
                    _number(
                        mapped_row,
                        "dropped_out_of_session_rows",
                        fallback=0.0,
                    )
                ),
                "diagnostic_rows": int(_number(diagnostic_row, "rows", fallback=0.0)),
                "price_grid_validation_enabled": _truthy(
                    diagnostic_row.get(
                        "price_grid_validation_enabled",
                        False,
                    )
                ),
                "price_grid_tick_size": _number(
                    diagnostic_row,
                    "price_grid_tick_size",
                    fallback=float("nan"),
                ),
                "off_tick_price_rows": int(
                    _number(
                        diagnostic_row,
                        "off_tick_price_rows",
                        fallback=0.0,
                    )
                ),
                "contract_horizon_validation_enabled": _truthy(
                    diagnostic_row.get(
                        "contract_horizon_validation_enabled",
                        False,
                    )
                ),
                "contract_horizon_market_timezone": _text(
                    diagnostic_row,
                    "contract_horizon_market_timezone",
                ),
                "unparseable_contract_expiry_rows": int(
                    _number(
                        diagnostic_row,
                        "unparseable_contract_expiry_rows",
                        fallback=0.0,
                    )
                ),
                "expired_contract_rows": int(
                    _number(
                        diagnostic_row,
                        "expired_contract_rows",
                        fallback=0.0,
                    )
                ),
                "zero_dte_rows": int(
                    _number(
                        diagnostic_row,
                        "zero_dte_rows",
                        fallback=0.0,
                    )
                ),
                "min_calendar_dte_days": _number(
                    diagnostic_row,
                    "min_calendar_dte_days",
                    fallback=float("nan"),
                ),
                "median_calendar_dte_days": _number(
                    diagnostic_row,
                    "median_calendar_dte_days",
                    fallback=float("nan"),
                ),
                "max_calendar_dte_days": _number(
                    diagnostic_row,
                    "max_calendar_dte_days",
                    fallback=float("nan"),
                ),
                "contract_key_validation_enabled": _truthy(
                    diagnostic_row.get(
                        "contract_key_validation_enabled",
                        False,
                    )
                ),
                "duplicate_contract_key_rows": int(
                    _number(
                        diagnostic_row,
                        "duplicate_contract_key_rows",
                        fallback=0.0,
                    )
                ),
                "duplicate_contract_key_excess_rows": int(
                    _number(
                        diagnostic_row,
                        "duplicate_contract_key_excess_rows",
                        fallback=0.0,
                    )
                ),
                "duplicate_contract_key_groups": int(
                    _number(
                        diagnostic_row,
                        "duplicate_contract_key_groups",
                        fallback=0.0,
                    )
                ),
                "exact_duplicate_contract_key_rows": int(
                    _number(
                        diagnostic_row,
                        "exact_duplicate_contract_key_rows",
                        fallback=0.0,
                    )
                ),
                "conflicting_contract_key_rows": int(
                    _number(
                        diagnostic_row,
                        "conflicting_contract_key_rows",
                        fallback=0.0,
                    )
                ),
                "conflicting_contract_key_groups": int(
                    _number(
                        diagnostic_row,
                        "conflicting_contract_key_groups",
                        fallback=0.0,
                    )
                ),
                "chain_snapshot_validation_enabled": _truthy(
                    diagnostic_row.get(
                        "chain_snapshot_validation_enabled",
                        False,
                    )
                ),
                "observation_timestamps": int(
                    _number(
                        diagnostic_row,
                        "observation_timestamps",
                        fallback=0.0,
                    )
                ),
                "expiry_snapshots": int(
                    _number(
                        diagnostic_row,
                        "expiry_snapshots",
                        fallback=0.0,
                    )
                ),
                "min_snapshots_per_expiry": int(
                    _number(
                        diagnostic_row,
                        "min_snapshots_per_expiry",
                        fallback=0.0,
                    )
                ),
                "min_snapshot_strikes": int(
                    _number(
                        diagnostic_row,
                        "min_snapshot_strikes",
                        fallback=0.0,
                    )
                ),
                "median_snapshot_strikes": _number(
                    diagnostic_row,
                    "median_snapshot_strikes",
                    fallback=0.0,
                ),
                "max_snapshot_strikes": int(
                    _number(
                        diagnostic_row,
                        "max_snapshot_strikes",
                        fallback=0.0,
                    )
                ),
                "snapshot_gap_observations": int(
                    _number(
                        diagnostic_row,
                        "snapshot_gap_observations",
                        fallback=0.0,
                    )
                ),
                "median_snapshot_gap_ns": _number(
                    diagnostic_row,
                    "median_snapshot_gap_ns",
                    fallback=0.0,
                ),
                "p99_snapshot_gap_ns": _number(
                    diagnostic_row,
                    "p99_snapshot_gap_ns",
                    fallback=0.0,
                ),
                "max_snapshot_gap_ns": _number(
                    diagnostic_row,
                    "max_snapshot_gap_ns",
                    fallback=0.0,
                ),
                "contract_expiry_validation_enabled": _truthy(
                    diagnostic_row.get(
                        "contract_expiry_validation_enabled",
                        False,
                    )
                ),
                "contract_expiry_cycle": _text(
                    diagnostic_row,
                    "contract_expiry_cycle",
                ),
                "contract_expiry_rule_id": _text(
                    diagnostic_row,
                    "contract_expiry_rule_id",
                ),
                "contract_expiry_rule_sha256": _text(
                    diagnostic_row,
                    "contract_expiry_rule_sha256",
                ),
                "contract_expiry_authority_source_sha256": _text(
                    diagnostic_row,
                    "contract_expiry_authority_source_sha256",
                ),
                "invalid_contract_expiry_rows": int(
                    _number(
                        diagnostic_row,
                        "invalid_contract_expiry_rows",
                        fallback=0.0,
                    )
                ),
                "uncovered_contract_expiry_rows": int(
                    _number(
                        diagnostic_row,
                        "uncovered_contract_expiry_rows",
                        fallback=0.0,
                    )
                ),
                "contract_lot_validation_enabled": _truthy(
                    diagnostic_row.get(
                        "contract_lot_validation_enabled",
                        False,
                    )
                ),
                "contract_lot_underlying": _text(
                    diagnostic_row,
                    "contract_lot_underlying",
                ),
                "contract_lot_size": int(
                    _number(
                        diagnostic_row,
                        "contract_lot_size",
                        fallback=0.0,
                    )
                ),
                "contract_lot_rule_id": _text(
                    diagnostic_row,
                    "contract_lot_rule_id",
                ),
                "contract_lot_rule_sha256": _text(
                    diagnostic_row,
                    "contract_lot_rule_sha256",
                ),
                "contract_lot_authority_source_sha256": _text(
                    diagnostic_row,
                    "contract_lot_authority_source_sha256",
                ),
                "contract_lot_snapshot_sha256": _text(
                    diagnostic_row,
                    "contract_lot_snapshot_sha256",
                ),
                "invalid_contract_lot_rows": int(
                    _number(
                        diagnostic_row,
                        "invalid_contract_lot_rows",
                        fallback=0.0,
                    )
                ),
                "uncovered_contract_lot_rows": int(
                    _number(
                        diagnostic_row,
                        "uncovered_contract_lot_rows",
                        fallback=0.0,
                    )
                ),
                "failed_components": failed,
                "data_readiness_ready": bool(readiness.ready),
                "vendor_intake_manifest_path": _manifest_path(intake_dir),
                "mapped_data_manifest_path": _manifest_path(mapped_dir),
                "data_readiness_manifest_path": _manifest_path(readiness_dir),
                "ready_action_count": 0,
                "blocked_action_count": int(len(action_queue)),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
                "recommendation": "feed_strategy_research" if readiness.ready and failed == 0 else "fix_vendor_market_data_pipeline",
            }
        ]
    )


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "dataset",
    "component",
    "check",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
    "pipeline_dir",
]


def _pipeline_action_queue(components: pd.DataFrame, readiness_queue: pd.DataFrame | None) -> pd.DataFrame:
    rows = _promote_action_rows(readiness_queue, source="data_readiness", dataset="", pipeline_dir="")
    if not rows and not components.empty:
        for item in components.loc[~components["ready"].astype(bool)].to_dict(orient="records"):
            rows.append(
                {
                    "queue_status": "blocked",
                    "source": "component",
                    "dataset": "",
                    "component": _value_text(item.get("component")),
                    "check": f"{_value_text(item.get('component'))}_ready",
                    "next_gate": "pipeline-vendor-market-data",
                    "next_gate_help_command": _next_gate_help_command("pipeline-vendor-market-data"),
                    "reason": _value_text(item.get("status")),
                    "recommendation": _value_text(item.get("recommendation"))
                    or "fix_vendor_market_data_pipeline",
                    "pipeline_dir": "",
                }
            )
    return _action_queue_frame(rows)


def _batch_action_queue(
    dataset_action_rows: list[dict[str, object]],
    comparison_queue: pd.DataFrame | None,
) -> pd.DataFrame:
    rows = list(dataset_action_rows)
    rows.extend(_promote_action_rows(comparison_queue, source="comparison", dataset="", pipeline_dir="comparison"))
    return _action_queue_frame(rows)


def _promote_action_rows(
    action_queue: pd.DataFrame | None,
    *,
    source: str,
    dataset: str,
    pipeline_dir: Path | str,
) -> list[dict[str, object]]:
    if action_queue is None or action_queue.empty:
        return []
    rows: list[dict[str, object]] = []
    for item in action_queue.to_dict(orient="records"):
        next_gate = _value_text(item.get("next_gate"))
        help_command = _value_text(item.get("next_gate_help_command")) or _next_gate_help_command(next_gate)
        rows.append(
            {
                "queue_status": _value_text(item.get("queue_status")) or "blocked",
                "source": source,
                "dataset": dataset,
                "component": _value_text(item.get("component")),
                "check": _value_text(item.get("check")),
                "next_gate": next_gate,
                "next_gate_help_command": help_command,
                "reason": _value_text(item.get("reason")),
                "recommendation": _value_text(item.get("recommendation")),
                "pipeline_dir": str(pipeline_dir),
            }
        )
    return rows


def _action_queue_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        ordered = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        ordered["priority"] = priority
        if not ordered["queue_status"]:
            ordered["queue_status"] = "blocked"
        ordered_rows.append(ordered)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _primary_next_gate(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return ""
    return _value_text(action_queue.iloc[0].get("next_gate"))


def _next_gate_help_command(next_gate: str) -> str:
    gate = _value_text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _nonmonotonic_label(row: pd.Series) -> str:
    if _value_text(row.get("kind")).lower() == "chain":
        return "Nonmonotonic chain rows"
    return "Nonmonotonic tick packets"


def _pipeline_runbook_markdown(
    summary_row: pd.Series,
    components: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    ready_label = "yes" if _truthy(summary_row.get("ready", False)) else "no"
    lines = [
        "# Vendor Market Data Pipeline Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_value_text(summary_row.get('adapter'))}",
        f"- Kind: {_value_text(summary_row.get('kind'))}",
        f"- Market: {_value_text(summary_row.get('market'))}",
        f"- Market calendar: {_value_text(summary_row.get('market_calendar_id')) or 'not provided'}",
        f"- Calendar coverage: {_value_text(summary_row.get('market_calendar_valid_from')) or 'n/a'} to {_value_text(summary_row.get('market_calendar_valid_to')) or 'n/a'}",
        f"- Calendar SHA-256: {_value_text(summary_row.get('market_calendar_sha256'))}",
        f"- Null required-field rows: {int(_number_from_value(summary_row.get('dropped_null_rows', 0)))}",
        f"- Non-finite numeric rows: {int(_number_from_value(summary_row.get('dropped_nonfinite_rows', 0)))}",
        f"- Non-integral integer-field rows: {int(_number_from_value(summary_row.get('dropped_nonintegral_rows', 0)))}",
        f"- Duplicate tick packets: {int(_number_from_value(summary_row.get('dropped_duplicate_rows', 0)))}",
        f"- Integer-overflow rows: {int(_number_from_value(summary_row.get('dropped_integer_overflow_rows', 0)))}",
        f"- {_nonmonotonic_label(summary_row)}: {int(_number_from_value(summary_row.get('dropped_nonmonotonic_rows', 0)))}",
        f"- Nonpositive depth rows: {int(_number_from_value(summary_row.get('dropped_negative_depth_rows', 0)))}",
        f"- Invalid trade rows: {int(_number_from_value(summary_row.get('dropped_invalid_trade_rows', 0)))}",
        f"- Price-grid validation: {'yes' if _truthy(summary_row.get('price_grid_validation_enabled', False)) else 'no'}",
        f"- Price-grid tick size: {_value_text(summary_row.get('price_grid_tick_size')) or 'n/a'}",
        f"- Off-tick price rows: {int(_number_from_value(summary_row.get('off_tick_price_rows', 0)))}",
        f"- Calendar-closed rows: {int(_number_from_value(summary_row.get('dropped_calendar_closed_rows', 0)))}",
        f"- Calendar out-of-range rows: {int(_number_from_value(summary_row.get('dropped_calendar_out_of_range_rows', 0)))}",
        f"- Contract horizon timezone: {_value_text(summary_row.get('contract_horizon_market_timezone')) or 'n/a'}",
        f"- Unparseable contract-expiry rows: {int(_number_from_value(summary_row.get('unparseable_contract_expiry_rows', 0)))}",
        f"- Post-expiry observation rows: {int(_number_from_value(summary_row.get('expired_contract_rows', 0)))}",
        f"- Zero-DTE rows: {int(_number_from_value(summary_row.get('zero_dte_rows', 0)))}",
        f"- Duplicate contract-key rows: {int(_number_from_value(summary_row.get('duplicate_contract_key_rows', 0)))}",
        f"- Duplicate contract-key groups: {int(_number_from_value(summary_row.get('duplicate_contract_key_groups', 0)))}",
        f"- Conflicting contract-key rows: {int(_number_from_value(summary_row.get('conflicting_contract_key_rows', 0)))}",
        f"- Conflicting contract-key groups: {int(_number_from_value(summary_row.get('conflicting_contract_key_groups', 0)))}",
        f"- Expiry snapshots: {int(_number_from_value(summary_row.get('expiry_snapshots', 0)))}",
        f"- Minimum snapshots per expiry: {int(_number_from_value(summary_row.get('min_snapshots_per_expiry', 0)))}",
        f"- Minimum strikes per snapshot: {int(_number_from_value(summary_row.get('min_snapshot_strikes', 0)))}",
        f"- Snapshot p99 gap (ns): {_number_from_value(summary_row.get('p99_snapshot_gap_ns', 0))}",
        f"- Contract expiry validation: {'yes' if _truthy(summary_row.get('contract_expiry_validation_enabled', False)) else 'no'}",
        f"- Contract expiry cycle: {_value_text(summary_row.get('contract_expiry_cycle')) or 'n/a'}",
        f"- Contract expiry rule: {_value_text(summary_row.get('contract_expiry_rule_id')) or 'n/a'}",
        f"- Invalid contract-expiry rows: {int(_number_from_value(summary_row.get('invalid_contract_expiry_rows', 0)))}",
        f"- Uncovered contract-expiry rows: {int(_number_from_value(summary_row.get('uncovered_contract_expiry_rows', 0)))}",
        f"- Contract lot-size validation: {'yes' if _truthy(summary_row.get('contract_lot_validation_enabled', False)) else 'no'}",
        f"- Contract lot-size underlying: {_value_text(summary_row.get('contract_lot_underlying')) or 'n/a'}",
        f"- Declared contract lot size: {_value_text(summary_row.get('contract_lot_size')) or 'n/a'}",
        f"- Contract lot-size rule: {_value_text(summary_row.get('contract_lot_rule_id')) or 'n/a'}",
        f"- Invalid contract-lot rows: {int(_number_from_value(summary_row.get('invalid_contract_lot_rows', 0)))}",
        f"- Uncovered contract-lot rows: {int(_number_from_value(summary_row.get('uncovered_contract_lot_rows', 0)))}",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Failed components: {int(_number_from_value(summary_row.get('failed_components', 0)))}",
        f"- Blocked actions: {int(_number_from_value(summary_row.get('blocked_action_count', 0)))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
        "## Components",
        "",
        _components_table(components),
        "",
    ]
    return "\n".join(lines)


def _batch_runbook_markdown(
    summary_row: pd.Series,
    datasets: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    ready_label = "yes" if _truthy(summary_row.get("ready", False)) else "no"
    lines = [
        "# Vendor Market Data Batch Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_value_text(summary_row.get('adapter'))}",
        f"- Kind: {_value_text(summary_row.get('kind'))}",
        f"- Market: {_value_text(summary_row.get('market'))}",
        f"- Market calendar: {_value_text(summary_row.get('market_calendar_id')) or 'not provided'}",
        f"- Calendar coverage: {_value_text(summary_row.get('market_calendar_valid_from')) or 'n/a'} to {_value_text(summary_row.get('market_calendar_valid_to')) or 'n/a'}",
        f"- Calendar SHA-256: {_value_text(summary_row.get('market_calendar_sha256'))}",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Dataset count: {int(_number_from_value(summary_row.get('dataset_count', 0)))}",
        f"- Ready datasets: {int(_number_from_value(summary_row.get('ready_datasets', 0)))}",
        f"- Failed datasets: {int(_number_from_value(summary_row.get('failed_datasets', 0)))}",
        f"- Mapping source mode: {_value_text(summary_row.get('mapping_source_mode'))}",
        f"- Mapping applications: {int(_number_from_value(summary_row.get('mapping_application_count', 0)))}",
        f"- Target-application coverage: {_number_from_value(summary_row.get('target_application_coverage', 0.0)):.3f}",
        f"- Null required-field rows: {int(_number_from_value(summary_row.get('dropped_null_rows', 0)))}",
        f"- Non-finite numeric rows: {int(_number_from_value(summary_row.get('dropped_nonfinite_rows', 0)))}",
        f"- Non-integral integer-field rows: {int(_number_from_value(summary_row.get('dropped_nonintegral_rows', 0)))}",
        f"- Duplicate tick packets: {int(_number_from_value(summary_row.get('dropped_duplicate_rows', 0)))}",
        f"- Integer-overflow rows: {int(_number_from_value(summary_row.get('dropped_integer_overflow_rows', 0)))}",
        f"- {_nonmonotonic_label(summary_row)}: {int(_number_from_value(summary_row.get('dropped_nonmonotonic_rows', 0)))}",
        f"- Nonpositive depth rows: {int(_number_from_value(summary_row.get('dropped_negative_depth_rows', 0)))}",
        f"- Invalid trade rows: {int(_number_from_value(summary_row.get('dropped_invalid_trade_rows', 0)))}",
        f"- Price-grid validation: {'yes' if _truthy(summary_row.get('price_grid_validation_enabled', False)) else 'no'}",
        f"- Price-grid tick size: {_value_text(summary_row.get('price_grid_tick_size')) or 'n/a'}",
        f"- Off-tick price rows: {int(_number_from_value(summary_row.get('off_tick_price_rows', 0)))}",
        f"- Calendar-closed rows: {int(_number_from_value(summary_row.get('dropped_calendar_closed_rows', 0)))}",
        f"- Calendar out-of-range rows: {int(_number_from_value(summary_row.get('dropped_calendar_out_of_range_rows', 0)))}",
        f"- Blocked actions: {int(_number_from_value(summary_row.get('blocked_action_count', 0)))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
        "## Datasets",
        "",
        _datasets_table(datasets),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Source", "Dataset", "Check", "Next gate", "Help", "Recommendation"],
        [
            [
                str(int(_number_from_value(row.get("priority", 0)))),
                _value_text(row.get("source")),
                _value_text(row.get("dataset")),
                _value_text(row.get("check")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _value_text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _components_table(components: pd.DataFrame) -> str:
    if components.empty:
        return "_None_"
    return _markdown_table(
        ["Component", "Ready", "Rows", "Failed checks", "Recommendation"],
        [
            [
                _value_text(row.get("component")),
                "yes" if _truthy(row.get("ready")) else "no",
                str(int(_number_from_value(row.get("rows", 0)))),
                str(int(_number_from_value(row.get("failed_checks", 0)))),
                _value_text(row.get("recommendation")),
            ]
            for row in components.to_dict(orient="records")
        ],
    )


def _datasets_table(datasets: pd.DataFrame) -> str:
    if datasets.empty:
        return "_None_"
    return _markdown_table(
        [
            "Dataset",
            "Ready",
            "Rows",
            "Mapping source",
            "Application ID",
            "Failed components",
            "Recommendation",
        ],
        [
            [
                _value_text(row.get("dataset")),
                "yes" if _truthy(row.get("ready")) else "no",
                str(int(_number_from_value(row.get("normalized_rows", 0)))),
                _value_text(row.get("mapping_source")),
                _value_text(row.get("mapping_application_id")),
                str(int(_number_from_value(row.get("failed_components", 0)))),
                _value_text(row.get("recommendation")),
            ]
            for row in datasets.to_dict(orient="records")
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _code(value: object) -> str:
    text = _value_text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: object) -> str:
    return _value_text(value).replace("|", "\\|").replace("\n", " ")


def _batch_summary(
    datasets: pd.DataFrame,
    comparison: DataReadinessComparisonReport,
    config: VendorMarketDataPipelineConfig,
) -> pd.DataFrame:
    comparison_row = comparison.summary.iloc[0] if not comparison.summary.empty else pd.Series(dtype=object)
    dataset_count = int(len(datasets))
    ready_datasets = int(datasets["ready"].astype(bool).sum()) if dataset_count else 0
    failed_datasets = dataset_count - ready_datasets
    accepted = bool(comparison.accepted)
    calendar = resolve_market_calendar(
        config.market_calendar_path,
        market=config.market,
    )
    return pd.DataFrame(
        [
            {
                "ready": bool(accepted and failed_datasets == 0),
                "adapter": config.adapter,
                "kind": config.kind,
                "market": config.market,
                **market_calendar_summary(calendar),
                "dataset_count": dataset_count,
                "ready_datasets": ready_datasets,
                "failed_datasets": failed_datasets,
                "ready_rate": float(ready_datasets / dataset_count) if dataset_count else 0.0,
                "dropped_null_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_null_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_nonfinite_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_nonfinite_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_nonintegral_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_nonintegral_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_duplicate_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_duplicate_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_integer_overflow_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_integer_overflow_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_nonmonotonic_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_nonmonotonic_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_negative_depth_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_negative_depth_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_invalid_trade_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_invalid_trade_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "price_grid_validation_enabled": bool(
                    dataset_count
                    and datasets.get(
                        "price_grid_validation_enabled",
                        pd.Series(False, index=datasets.index, dtype=bool),
                    ).fillna(False).astype(bool).all()
                ),
                "price_grid_tick_size": (
                    float(config.tick_size)
                    if config.tick_size is not None
                    else float("nan")
                ),
                "off_tick_price_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "off_tick_price_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_calendar_closed_rows": int(
                    pd.to_numeric(
                        datasets.get("dropped_calendar_closed_rows", pd.Series(dtype=float)),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "dropped_calendar_out_of_range_rows": int(
                    pd.to_numeric(
                        datasets.get(
                            "dropped_calendar_out_of_range_rows",
                            pd.Series(dtype=float),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "unique_source_files": _unique_count(datasets, "source_file_sha256"),
                "source_file_fingerprint_coverage": _number(
                    comparison_row,
                    "source_file_fingerprint_coverage",
                    fallback=0.0,
                ),
                "min_mapping_coverage": _number(comparison_row, "min_mapping_coverage", fallback=0.0),
                "unique_header_fingerprints": _unique_count(datasets, "source_header_sha256"),
                "unique_mapping_drafts": int(_number(comparison_row, "unique_mapping_drafts", fallback=0.0)),
                "mapping_sources": _joined_values(datasets, "mapping_source"),
                "mapping_application_count": _present_count(
                    datasets,
                    "mapping_application_id",
                ),
                "unique_mapping_applications": _unique_count(
                    datasets,
                    "mapping_application_id",
                ),
                "target_application_coverage": (
                    _present_count(datasets, "mapping_application_id") / dataset_count
                    if dataset_count
                    else 0.0
                ),
                "comparison_accepted": accepted,
                "comparison_ready_rate": _number(comparison_row, "ready_rate", fallback=0.0),
                "comparison_failed_checks": int(_number(comparison_row, "total_failed_checks", fallback=0.0)),
                "recommendation": "feed_walkforward_research" if accepted and failed_datasets == 0 else "fix_vendor_market_data_batch",
            }
        ]
    )


def _pipeline_config(
    row: pd.Series,
    components: pd.DataFrame,
    action_queue: pd.DataFrame,
    thresholds: DataReadinessThresholds,
    config: VendorMarketDataPipelineConfig,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    component_rows = [
        {
            "component": str(item.get("component", "")),
            "ready": _truthy(item.get("ready", False)),
            "status": str(item.get("status", "")),
            "output_dir": str(item.get("output_dir", "")),
            "rows": int(_number_from_value(item.get("rows", 0))),
            "failed_checks": int(_number_from_value(item.get("failed_checks", 0))),
            "recommendation": str(item.get("recommendation", "")),
        }
        for item in components.to_dict(orient="records")
    ]
    return {
        "schema_version": 1,
        "ready": _truthy(row.get("ready", False)),
        "adapter": _text(row, "adapter"),
        "kind": _text(row, "kind"),
        "market": config.market,
        "market_calendar": _market_calendar_config(row),
        "source": {
            "path": _text(row, "input_path"),
            "file_sha256": _text(row, "source_file_sha256"),
            "header_sha256": _text(row, "source_header_sha256"),
            "columns": int(_number(row, "source_columns", fallback=0.0)),
        },
        "mapping": {
            "path": _text(row, "mapping_path"),
            "source": _text(row, "mapping_source"),
            "draft_sha256": _text(row, "mapping_draft_sha256"),
            "coverage": _number(row, "mapping_coverage", fallback=0.0),
            "min_coverage": float(config.min_mapping_coverage),
            "review_path": _text(row, "mapping_review_path"),
            "review_id": _text(row, "mapping_review_id"),
            "review_sha256": _text(row, "mapping_review_sha256"),
            "application": {
                "path": _text(row, "mapping_application_path"),
                "id": _text(row, "mapping_application_id"),
                "sha256": _text(row, "mapping_application_sha256"),
                "scope_review_path": _text(row, "mapping_scope_review_path"),
                "scope_review_id": _text(row, "mapping_scope_review_id"),
                "scope_review_sha256": _text(
                    row,
                    "mapping_scope_review_sha256",
                ),
                "target_intake_path": _text(row, "target_intake_path"),
                "target_intake_receipt_id": _text(
                    row,
                    "target_intake_receipt_id",
                ),
                "applied_mapping_sha256": _text(
                    row,
                    "applied_mapping_sha256",
                ),
            },
        },
        "normalized": {
            "output_file": _text(row, "normalized_output_file"),
            "input_rows": int(_number(row, "input_rows", fallback=0.0)),
            "rows": int(_number(row, "normalized_rows", fallback=0.0)),
            "dropped_null_rows": int(
                _number(row, "dropped_null_rows", fallback=0.0)
            ),
            "dropped_nonfinite_rows": int(
                _number(row, "dropped_nonfinite_rows", fallback=0.0)
            ),
            "dropped_nonintegral_rows": int(
                _number(row, "dropped_nonintegral_rows", fallback=0.0)
            ),
            "dropped_duplicate_rows": int(
                _number(row, "dropped_duplicate_rows", fallback=0.0)
            ),
            "dropped_integer_overflow_rows": int(
                _number(row, "dropped_integer_overflow_rows", fallback=0.0)
            ),
            "dropped_nonmonotonic_rows": int(
                _number(row, "dropped_nonmonotonic_rows", fallback=0.0)
            ),
            "dropped_negative_depth_rows": int(
                _number(row, "dropped_negative_depth_rows", fallback=0.0)
            ),
            "dropped_invalid_trade_rows": int(
                _number(row, "dropped_invalid_trade_rows", fallback=0.0)
            ),
            "dropped_non_trading_day_rows": int(
                _number(row, "dropped_non_trading_day_rows", fallback=0.0)
            ),
            "dropped_calendar_closed_rows": int(
                _number(row, "dropped_calendar_closed_rows", fallback=0.0)
            ),
            "dropped_calendar_out_of_range_rows": int(
                _number(
                    row,
                    "dropped_calendar_out_of_range_rows",
                    fallback=0.0,
                )
            ),
            "dropped_out_of_session_rows": int(
                _number(row, "dropped_out_of_session_rows", fallback=0.0)
            ),
            "timestamp_unit": config.timestamp_unit,
            "timestamp_tz": config.timestamp_tz,
            "filter_session": bool(config.filter_session),
        },
        "diagnostics": {
            "rows": int(_number(row, "diagnostic_rows", fallback=0.0)),
            "price_grid_validation_enabled": _truthy(
                row.get("price_grid_validation_enabled", False)
            ),
            "price_grid_tick_size": _number(
                row,
                "price_grid_tick_size",
                fallback=0.0,
            ),
            "off_tick_price_rows": int(
                _number(row, "off_tick_price_rows", fallback=0.0)
            ),
        },
        "data_readiness": {
            "ready": _truthy(row.get("data_readiness_ready", False)),
            "manifest_path": _text(row, "data_readiness_manifest_path"),
            "thresholds": asdict(thresholds),
        },
        "component_manifests": {
            "vendor_intake": _text(row, "vendor_intake_manifest_path"),
            "mapped_data": _text(row, "mapped_data_manifest_path"),
            "data_readiness": _text(row, "data_readiness_manifest_path"),
        },
        "components": component_rows,
        "failed_components": int(_number(row, "failed_components", fallback=0.0)),
        "ready_action_count": int(_number(row, "ready_action_count", fallback=0.0)),
        "blocked_action_count": int(_number(row, "blocked_action_count", fallback=0.0)),
        "next_gate": _text(row, "next_gate"),
        "next_gate_help_command": _text(row, "next_gate_help_command"),
        "primary_action_status": _value_text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "recommendation": _text(row, "recommendation"),
    }


def _batch_config(
    row: pd.Series,
    datasets: pd.DataFrame,
    action_queue: pd.DataFrame,
    thresholds: DataReadinessComparisonThresholds,
    readiness_thresholds: DataReadinessThresholds,
    config: VendorMarketDataPipelineConfig,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    dataset_rows = [
        {
            "dataset": str(item.get("dataset", "")),
            "ready": _truthy(item.get("ready", False)),
            "input_path": str(item.get("input_path", "")),
            "pipeline_dir": str(item.get("pipeline_dir", "")),
            "data_readiness_dir": str(item.get("data_readiness_dir", "")),
            "normalized_rows": int(_number_from_value(item.get("normalized_rows", 0))),
            "failed_components": int(_number_from_value(item.get("failed_components", 0))),
            "dropped_null_rows": int(
                _number_from_value(item.get("dropped_null_rows", 0))
            ),
            "dropped_nonfinite_rows": int(
                _number_from_value(item.get("dropped_nonfinite_rows", 0))
            ),
            "dropped_nonintegral_rows": int(
                _number_from_value(item.get("dropped_nonintegral_rows", 0))
            ),
            "dropped_duplicate_rows": int(
                _number_from_value(item.get("dropped_duplicate_rows", 0))
            ),
            "dropped_integer_overflow_rows": int(
                _number_from_value(item.get("dropped_integer_overflow_rows", 0))
            ),
            "dropped_nonmonotonic_rows": int(
                _number_from_value(item.get("dropped_nonmonotonic_rows", 0))
            ),
            "dropped_negative_depth_rows": int(
                _number_from_value(item.get("dropped_negative_depth_rows", 0))
            ),
            "dropped_invalid_trade_rows": int(
                _number_from_value(item.get("dropped_invalid_trade_rows", 0))
            ),
            "price_grid_validation_enabled": _truthy(
                item.get("price_grid_validation_enabled", False)
            ),
            "price_grid_tick_size": _number_from_value(
                item.get("price_grid_tick_size", 0.0),
                fallback=0.0,
            ),
            "off_tick_price_rows": int(
                _number_from_value(item.get("off_tick_price_rows", 0))
            ),
            "dropped_calendar_closed_rows": int(
                _number_from_value(item.get("dropped_calendar_closed_rows", 0))
            ),
            "dropped_calendar_out_of_range_rows": int(
                _number_from_value(
                    item.get("dropped_calendar_out_of_range_rows", 0)
                )
            ),
            "source_file_sha256": str(item.get("source_file_sha256", "")),
            "source_header_sha256": str(item.get("source_header_sha256", "")),
            "mapping_draft_sha256": str(item.get("mapping_draft_sha256", "")),
            "market_calendar_id": str(item.get("market_calendar_id", "")),
            "market_calendar_sha256": str(
                item.get("market_calendar_sha256", "")
            ),
            "market_calendar_valid_from": str(
                item.get("market_calendar_valid_from", "")
            ),
            "market_calendar_valid_to": str(
                item.get("market_calendar_valid_to", "")
            ),
            "mapping_source": str(item.get("mapping_source", "")),
            "mapping_application_path": str(
                item.get("mapping_application_path", "")
            ),
            "mapping_application_id": str(item.get("mapping_application_id", "")),
            "mapping_application_sha256": str(
                item.get("mapping_application_sha256", "")
            ),
            "mapping_scope_review_id": str(item.get("mapping_scope_review_id", "")),
            "mapping_scope_review_sha256": str(
                item.get("mapping_scope_review_sha256", "")
            ),
            "target_intake_receipt_id": str(
                item.get("target_intake_receipt_id", "")
            ),
            "applied_mapping_sha256": str(item.get("applied_mapping_sha256", "")),
            "data_readiness_manifest_path": str(item.get("data_readiness_manifest_path", "")),
            "recommendation": str(item.get("recommendation", "")),
        }
        for item in datasets.to_dict(orient="records")
    ]
    return {
        "schema_version": 1,
        "ready": _truthy(row.get("ready", False)),
        "adapter": config.adapter,
        "kind": config.kind,
        "market": config.market,
        "market_calendar": _market_calendar_config(row),
        "dataset_count": int(_number(row, "dataset_count", fallback=0.0)),
        "ready_datasets": int(_number(row, "ready_datasets", fallback=0.0)),
        "failed_datasets": int(_number(row, "failed_datasets", fallback=0.0)),
        "dropped_null_rows": int(
            _number(row, "dropped_null_rows", fallback=0.0)
        ),
        "dropped_nonfinite_rows": int(
            _number(row, "dropped_nonfinite_rows", fallback=0.0)
        ),
        "dropped_nonintegral_rows": int(
            _number(row, "dropped_nonintegral_rows", fallback=0.0)
        ),
        "dropped_duplicate_rows": int(
            _number(row, "dropped_duplicate_rows", fallback=0.0)
        ),
        "dropped_integer_overflow_rows": int(
            _number(row, "dropped_integer_overflow_rows", fallback=0.0)
        ),
        "dropped_nonmonotonic_rows": int(
            _number(row, "dropped_nonmonotonic_rows", fallback=0.0)
        ),
        "dropped_negative_depth_rows": int(
            _number(row, "dropped_negative_depth_rows", fallback=0.0)
        ),
        "dropped_invalid_trade_rows": int(
            _number(row, "dropped_invalid_trade_rows", fallback=0.0)
        ),
        "price_grid_validation_enabled": _truthy(
            row.get("price_grid_validation_enabled", False)
        ),
        "price_grid_tick_size": _number(
            row,
            "price_grid_tick_size",
            fallback=0.0,
        ),
        "off_tick_price_rows": int(
            _number(row, "off_tick_price_rows", fallback=0.0)
        ),
        "dropped_calendar_closed_rows": int(
            _number(row, "dropped_calendar_closed_rows", fallback=0.0)
        ),
        "dropped_calendar_out_of_range_rows": int(
            _number(row, "dropped_calendar_out_of_range_rows", fallback=0.0)
        ),
        "ready_rate": _number(row, "ready_rate", fallback=0.0),
        "unique_source_files": int(_number(row, "unique_source_files", fallback=0.0)),
        "source_file_fingerprint_coverage": _number(row, "source_file_fingerprint_coverage", fallback=0.0),
        "min_mapping_coverage": _number(row, "min_mapping_coverage", fallback=0.0),
        "unique_header_fingerprints": int(_number(row, "unique_header_fingerprints", fallback=0.0)),
        "unique_mapping_drafts": int(_number(row, "unique_mapping_drafts", fallback=0.0)),
        "mapping_sources": _text(row, "mapping_sources"),
        "mapping_source_mode": _text(row, "mapping_source_mode"),
        "mapping_application_count": int(
            _number(row, "mapping_application_count", fallback=0.0)
        ),
        "unique_mapping_applications": int(
            _number(row, "unique_mapping_applications", fallback=0.0)
        ),
        "target_application_coverage": _number(
            row,
            "target_application_coverage",
            fallback=0.0,
        ),
        "data_readiness_thresholds": asdict(readiness_thresholds),
        "comparison": {
            "accepted": _truthy(row.get("comparison_accepted", False)),
            "ready_rate": _number(row, "comparison_ready_rate", fallback=0.0),
            "failed_checks": int(_number(row, "comparison_failed_checks", fallback=0.0)),
            "thresholds": asdict(thresholds),
        },
        "datasets": dataset_rows,
        "ready_action_count": int(_number(row, "ready_action_count", fallback=0.0)),
        "blocked_action_count": int(_number(row, "blocked_action_count", fallback=0.0)),
        "next_gate": _text(row, "next_gate"),
        "next_gate_help_command": _text(row, "next_gate_help_command"),
        "primary_action_status": _value_text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "recommendation": _text(row, "recommendation"),
    }


def _first_action_record(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return _jsonable_record(frame.iloc[0].to_dict())


def _market_calendar_config(row: pd.Series) -> dict[str, object]:
    return {
        "provided": _truthy(row.get("market_calendar_provided", False)),
        "policy": _text(row, "market_calendar_policy"),
        "id": _text(row, "market_calendar_id"),
        "path": _text(row, "market_calendar_path"),
        "sha256": _text(row, "market_calendar_sha256"),
        "valid_from": _text(row, "market_calendar_valid_from"),
        "valid_to": _text(row, "market_calendar_valid_to"),
        "publisher": _text(row, "market_calendar_publisher"),
        "source_url": _text(row, "market_calendar_source_url"),
        "published_date": _text(row, "market_calendar_published_date"),
        "closed_dates": int(
            _number(row, "market_calendar_closed_dates", fallback=0.0)
        ),
        "special_open_dates": int(
            _number(row, "market_calendar_special_open_dates", fallback=0.0)
        ),
    }


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


def _diagnostics_ready(diagnostics: DiagnosticResult) -> bool:
    row = _diagnostic_overall(diagnostics)
    return int(_number(row, "rows", fallback=0.0)) > 0


def _diagnostic_overall(diagnostics: DiagnosticResult) -> pd.Series:
    if diagnostics.summary.empty:
        return pd.Series(dtype=object)
    if "scope" in diagnostics.summary.columns:
        overall = diagnostics.summary.loc[diagnostics.summary["scope"].astype(str) == "overall"]
        if not overall.empty:
            return overall.iloc[0]
    return diagnostics.summary.iloc[0]


def _first(frame: pd.DataFrame) -> pd.Series:
    return frame.iloc[0] if not frame.empty else pd.Series(dtype=object)


def _output_filename(config: VendorMarketDataPipelineConfig) -> str:
    if config.output_filename:
        return config.output_filename
    return "normalized_ticks.csv" if config.kind == "ticks" else "normalized_chain.csv"


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _text(row: pd.Series, column: str, fallback: str = "") -> str:
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return str(value).strip()


def _value_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _number_from_value(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _truthy(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed", "accepted"}
    return bool(value)


def _manifest_path(directory: Path) -> str:
    manifest = directory / "manifest.json"
    return str(manifest) if manifest.exists() else ""


def _existing_paths(**paths: Path) -> dict[str, Path]:
    return {name: path for name, path in paths.items() if path.exists()}


def _present_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    values = frame[column].dropna().astype(str).str.strip()
    return int((values != "").sum())


def _unique_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    values = frame[column].dropna().astype(str).str.strip()
    return int(values.loc[values != ""].nunique())


def _joined_values(frame: pd.DataFrame, column: str) -> str:
    if column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    return ";".join(sorted(set(values.loc[values != ""])))


def _safe_label(label: str, idx: int) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(label).strip())
    return safe or f"dataset_{idx + 1}"


def _validate_config(config: VendorMarketDataPipelineConfig) -> None:
    if config.kind not in {"ticks", "chain"}:
        raise ValueError("vendor market-data pipeline kind must be ticks or chain")
    if config.sample_rows <= 0:
        raise ValueError("sample_rows must be positive")
    if not 0 <= config.min_mapping_coverage <= 1:
        raise ValueError("min_mapping_coverage must be between 0 and 1")
    if config.min_rows <= 0:
        raise ValueError("min_rows must be positive")
    for name in (
        "min_chain_expiry_snapshots",
        "min_chain_snapshots_per_expiry",
        "min_chain_snapshot_strikes",
    ):
        if getattr(config, name) <= 0:
            raise ValueError(f"{name} must be positive")
    resolve_market_calendar(config.market_calendar_path, market=config.market)
    if config.expiry_cycle is not None:
        expiry_cycle = str(config.expiry_cycle).strip().lower()
        if expiry_cycle not in {"weekly", "monthly"}:
            raise ValueError("expiry_cycle must be weekly or monthly")
        if config.kind != "chain":
            raise ValueError("expiry_cycle is only valid for chain data")
        if not config.market_calendar_path:
            raise ValueError(
                "market_calendar_path is required when expiry_cycle is set"
            )
    lot_validation_requested = (
        config.underlying is not None or config.lot_size is not None
    )
    if config.max_off_tick_price_rows is not None and config.tick_size is None:
        raise ValueError(
            "tick_size is required when max_off_tick_price_rows is set"
        )
    if lot_validation_requested:
        if config.kind != "chain":
            raise ValueError(
                "underlying and lot_size are only valid for chain data"
            )
        if config.underlying is None or not str(config.underlying).strip():
            raise ValueError(
                "underlying is required when lot_size is provided"
            )
        if (
            isinstance(config.lot_size, bool)
            or not isinstance(config.lot_size, int)
            or config.lot_size <= 0
        ):
            raise ValueError(
                "lot_size must be a positive integer when underlying is provided"
            )
        if config.expiry_cycle is None:
            raise ValueError(
                "expiry_cycle is required when contract lot-size validation is enabled"
            )
    for name in (
        "max_null_rows",
        "max_nonfinite_rows",
        "max_nonintegral_rows",
        "max_duplicate_tick_rows",
        "max_integer_overflow_rows",
        "max_nonmonotonic_rows",
        "max_crossed_quote_rows",
        "max_nonpositive_quote_rows",
        "max_nonpositive_depth_rows",
        "max_invalid_trade_rows",
        "max_non_trading_day_rows",
        "max_out_of_session_rows",
        "max_unparseable_contract_expiry_rows",
        "max_expired_contract_rows",
        "max_duplicate_contract_key_rows",
        "max_conflicting_contract_key_rows",
    ):
        if getattr(config, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    if (
        config.max_off_tick_price_rows is not None
        and config.max_off_tick_price_rows < 0
    ):
        raise ValueError("max_off_tick_price_rows must be non-negative")
    for name in (
        "tick_size",
        "max_p99_gap_ns",
        "max_median_spread_ticks",
        "max_chain_snapshot_p99_gap_ns",
    ):
        value = getattr(config, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")


def _validate_review_binding(
    source_file: Path,
    output_dir: Path,
    config: VendorMarketDataPipelineConfig,
    review: ApprovedMappingReviewInputs,
) -> None:
    if source_file.resolve() != review.source_path.resolve():
        raise ValueError("pipeline input does not match the exact source bound by mapping review")
    if _identity(config.adapter) != review.adapter:
        raise ValueError("pipeline adapter does not match the approved mapping review")
    if _identity(config.kind) != review.kind:
        raise ValueError("pipeline kind does not match the approved mapping review")
    if _is_relative_to(output_dir.resolve(), review.mapping_review_dir.resolve()):
        raise ValueError("pipeline output cannot modify mapping-review evidence")
    if _is_relative_to(review.mapping_review_dir.resolve(), output_dir.resolve()):
        raise ValueError("pipeline output cannot contain mapping-review evidence")


def _validate_application_binding(
    source_file: Path,
    output_dir: Path,
    config: VendorMarketDataPipelineConfig,
    application: ApprovedVendorMappingApplicationInputs,
) -> None:
    if source_file.resolve() != application.target_source_path.resolve():
        raise ValueError(
            "pipeline input does not match the exact target source bound by mapping application"
        )
    if _identity(config.adapter) != application.adapter:
        raise ValueError("pipeline adapter does not match the verified mapping application")
    if _identity(config.kind) != application.kind:
        raise ValueError("pipeline kind does not match the verified mapping application")

    out = output_dir.resolve()
    evidence_paths = (
        ("mapping-application", application.application_dir.resolve()),
        ("mapping-scope-review", application.scope_review_dir.resolve()),
        ("target-intake", application.target_intake_dir.resolve()),
        ("target-source", application.target_source_path.resolve()),
    )
    for label, evidence_path in evidence_paths:
        if _is_relative_to(out, evidence_path):
            raise ValueError(f"pipeline output cannot modify {label} evidence")
        if _is_relative_to(evidence_path, out):
            raise ValueError(f"pipeline output cannot contain {label} evidence")


def _identity(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
