from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.mapped_data import MappedDataConfig, MappedDataReport, write_mapped_data_normalization
from adapters.vendor_intake import VendorCsvIntakeConfig, VendorCsvIntakeReport, write_vendor_csv_intake_report
from data.diagnostics import DiagnosticResult, chain_diagnostics, tick_diagnostics, write_diagnostics
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.data_readiness import DataReadinessReport, DataReadinessThresholds, write_data_readiness_report
from reports.data_readiness_comparison import (
    DataReadinessComparisonReport,
    DataReadinessComparisonThresholds,
    write_data_readiness_comparison,
)
from reports.manifest import write_experiment_manifest


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
class VendorMarketDataPipelineReport:
    components: pd.DataFrame
    summary: pd.DataFrame
    intake: VendorCsvIntakeReport
    mapped_data: MappedDataReport
    diagnostics: DiagnosticResult
    readiness: DataReadinessReport
    output_dir: Path | None = None

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
    config: VendorMarketDataPipelineConfig | None = None,
    readiness_thresholds: DataReadinessThresholds | None = None,
) -> VendorMarketDataPipelineReport:
    config = config or VendorMarketDataPipelineConfig()
    _validate_config(config)
    source_file = Path(input_path)
    if not source_file.exists():
        raise FileNotFoundError(f"vendor market-data input not found: {source_file}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    intake_dir = out / "01_vendor_intake"
    mapped_dir = out / "02_normalized"
    diagnostics_dir = out / "03_diagnostics"
    readiness_dir = out / "04_data_readiness"

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
            require_all_mapped=config.require_all_mapped,
        ),
    )
    diagnostics = _write_diagnostics(mapped.data, diagnostics_dir, config)
    thresholds = readiness_thresholds or _readiness_thresholds(config)
    readiness = write_data_readiness_report(
        output_dir=readiness_dir,
        vendor_intake_dir=intake_dir,
        mapped_data_dir=mapped_dir,
        tick_diagnostics_dir=diagnostics_dir if config.kind == "ticks" else None,
        chain_diagnostics_dir=diagnostics_dir if config.kind == "chain" else None,
        thresholds=thresholds,
    )
    components = _components(intake, mapped, diagnostics, readiness)
    summary = _summary(source_file, mapping_file, components, intake, mapped, diagnostics, readiness, config)
    components.to_csv(out / "vendor_market_data_pipeline_components.csv", index=False)
    summary.to_csv(out / "vendor_market_data_pipeline_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="vendor_market_data_pipeline",
        parameters={
            "config": asdict(config),
            "readiness_thresholds": asdict(thresholds),
            "mapping_source": "provided" if mapping_path is not None else "vendor_intake_draft",
        },
        inputs={
            "input": source_file,
            "mapping": mapping_file,
        },
    )
    return VendorMarketDataPipelineReport(components, summary, intake, mapped, diagnostics, readiness, out)


def write_vendor_market_data_batch_pipeline(
    input_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    mapping_path: str | Path | None = None,
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

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dataset_rows = []
    readiness_dirs = []
    comparison_labels = []
    for idx, path in enumerate(paths):
        label = labels[idx] if labels is not None else path.stem
        dataset_dir = out / "datasets" / _safe_label(label, idx)
        report = write_vendor_market_data_pipeline(
            path,
            output_dir=dataset_dir,
            mapping_path=mapping_path,
            config=config,
            readiness_thresholds=readiness_thresholds,
        )
        readiness_dir = dataset_dir / "04_data_readiness"
        readiness_dirs.append(readiness_dir)
        comparison_labels.append(label)
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
                "recommendation": str(row.get("recommendation", "")),
            }
        )

    thresholds = comparison_thresholds or DataReadinessComparisonThresholds(
        min_datasets=len(paths),
        min_ready_datasets=len(paths),
        min_ready_rate=1.0,
        max_total_failed_checks=0,
    )
    comparison = write_data_readiness_comparison(
        readiness_dirs,
        output_dir=out / "comparison",
        labels=comparison_labels,
        thresholds=thresholds,
    )
    datasets = pd.DataFrame(dataset_rows)
    summary = _batch_summary(datasets, comparison, config)
    datasets.to_csv(out / "vendor_market_data_batch_datasets.csv", index=False)
    summary.to_csv(out / "vendor_market_data_batch_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="vendor_market_data_batch_pipeline",
        parameters={
            "config": asdict(config),
            "readiness_thresholds": asdict(readiness_thresholds)
            if readiness_thresholds is not None
            else asdict(_readiness_thresholds(config)),
            "comparison_thresholds": asdict(thresholds),
            "labels": labels,
            "mapping_source": "provided" if mapping_path is not None else "per_dataset_vendor_intake_draft",
        },
        inputs={"inputs": paths, "mapping": mapping_path},
    )
    return VendorMarketDataBatchReport(datasets, summary, comparison, out)


def _write_diagnostics(data: pd.DataFrame, output_dir: Path, config: VendorMarketDataPipelineConfig) -> DiagnosticResult:
    if config.kind == "ticks":
        return write_diagnostics(tick_diagnostics(data, tick_size=config.tick_size, market=config.market), output_dir)
    if config.kind == "chain":
        return write_diagnostics(chain_diagnostics(data, tick_size=config.tick_size, market=config.market), output_dir)
    raise ValueError("vendor market-data pipeline kind must be ticks or chain")


def _readiness_thresholds(config: VendorMarketDataPipelineConfig) -> DataReadinessThresholds:
    return DataReadinessThresholds(
        require_vendor_intake=True,
        require_mapped_data=True,
        require_tick_diagnostics=config.kind == "ticks",
        require_chain_diagnostics=config.kind == "chain",
        min_tick_rows=config.min_rows,
        min_chain_rows=config.min_rows,
        max_crossed_quote_rows=config.max_crossed_quote_rows,
        max_nonpositive_quote_rows=config.max_nonpositive_quote_rows,
        max_nonpositive_depth_rows=config.max_nonpositive_depth_rows,
        max_out_of_session_rows=config.max_out_of_session_rows,
        max_tick_p99_gap_ns=config.max_p99_gap_ns if config.kind == "ticks" else None,
        max_tick_median_spread_ticks=config.max_median_spread_ticks if config.kind == "ticks" else None,
        max_chain_median_spread_ticks=config.max_median_spread_ticks if config.kind == "chain" else None,
    )


def _components(
    intake: VendorCsvIntakeReport,
    mapped: MappedDataReport,
    diagnostics: DiagnosticResult,
    readiness: DataReadinessReport,
) -> pd.DataFrame:
    rows = [
        _component("vendor_intake", intake.ready, intake.output_dir, _first(intake.summary)),
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
    mapped: MappedDataReport,
    diagnostics: DiagnosticResult,
    readiness: DataReadinessReport,
    config: VendorMarketDataPipelineConfig,
) -> pd.DataFrame:
    failed = int((~components["ready"].astype(bool)).sum()) if not components.empty else 1
    intake_row = _first(intake.summary)
    mapped_row = _first(mapped.summary)
    diagnostic_row = _diagnostic_overall(diagnostics)
    return pd.DataFrame(
        [
            {
                "ready": bool(readiness.ready and failed == 0),
                "adapter": config.adapter,
                "kind": config.kind,
                "input_path": str(source_file),
                "mapping_path": str(mapping_file),
                "normalized_output_file": _output_filename(config),
                "source_columns": int(_number(intake_row, "source_columns", fallback=0.0)),
                "mapping_coverage": _number(intake_row, "mapping_coverage", fallback=0.0),
                "input_rows": int(_number(mapped_row, "input_rows", fallback=0.0)),
                "normalized_rows": int(_number(mapped_row, "output_rows", fallback=0.0)),
                "diagnostic_rows": int(_number(diagnostic_row, "rows", fallback=0.0)),
                "failed_components": failed,
                "data_readiness_ready": bool(readiness.ready),
                "recommendation": "feed_strategy_research" if readiness.ready and failed == 0 else "fix_vendor_market_data_pipeline",
            }
        ]
    )


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
    return pd.DataFrame(
        [
            {
                "ready": bool(accepted and failed_datasets == 0),
                "adapter": config.adapter,
                "kind": config.kind,
                "dataset_count": dataset_count,
                "ready_datasets": ready_datasets,
                "failed_datasets": failed_datasets,
                "ready_rate": float(ready_datasets / dataset_count) if dataset_count else 0.0,
                "comparison_accepted": accepted,
                "comparison_ready_rate": _number(comparison_row, "ready_rate", fallback=0.0),
                "comparison_failed_checks": int(_number(comparison_row, "total_failed_checks", fallback=0.0)),
                "recommendation": "feed_walkforward_research" if accepted and failed_datasets == 0 else "fix_vendor_market_data_batch",
            }
        ]
    )


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
        "max_crossed_quote_rows",
        "max_nonpositive_quote_rows",
        "max_nonpositive_depth_rows",
        "max_out_of_session_rows",
    ):
        if getattr(config, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in ("tick_size", "max_p99_gap_ns", "max_median_spread_ticks"):
        value = getattr(config, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")
