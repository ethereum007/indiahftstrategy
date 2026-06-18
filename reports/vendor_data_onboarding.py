from __future__ import annotations

import json
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
    inputs: dict[str, Any] = {
        "input": source_file,
        "mapping": mapping_file,
    }
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
    dataset_manifest_paths = []
    dataset_action_rows = []
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
                "source_file_sha256": _text(row, "source_file_sha256"),
                "source_header_sha256": _text(row, "source_header_sha256"),
                "mapping_draft_sha256": _text(row, "mapping_draft_sha256"),
                "mapping_source": _text(row, "mapping_source"),
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
    summary["blocked_action_count"] = int(len(action_queue))
    summary["ready_action_count"] = 0
    summary["next_gate"] = _primary_next_gate(action_queue)
    summary["next_gate_help_command"] = summary["next_gate"].map(_next_gate_help_command)
    datasets.to_csv(out / "vendor_market_data_batch_datasets.csv", index=False)
    summary.to_csv(out / "vendor_market_data_batch_summary.csv", index=False)
    action_queue.to_csv(out / "vendor_market_data_batch_action_queue.csv", index=False)
    (out / "vendor_market_data_batch_runbook.md").write_text(
        _batch_runbook_markdown(summary.iloc[0], datasets, action_queue),
        encoding="utf-8",
    )
    batch_config = _batch_config(summary.iloc[0], datasets, action_queue, thresholds, config)
    (out / "vendor_market_data_batch_config.json").write_text(
        json.dumps(batch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"inputs": paths}
    if mapping_path is not None:
        inputs["mapping"] = mapping_path
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
            "readiness_thresholds": asdict(readiness_thresholds)
            if readiness_thresholds is not None
            else asdict(_readiness_thresholds(config)),
            "comparison_thresholds": asdict(thresholds),
            "labels": labels,
            "mapping_source": "provided" if mapping_path is not None else "per_dataset_vendor_intake_draft",
        },
        inputs=inputs,
    )
    return VendorMarketDataBatchReport(datasets, summary, comparison, out, action_queue)


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
        expected_adapter=config.adapter,
        expected_vendor_data_kind=config.kind,
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
    *,
    mapping_source: str,
    intake_dir: Path,
    mapped_dir: Path,
    readiness_dir: Path,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~components["ready"].astype(bool)).sum()) if not components.empty else 1
    intake_row = _first(intake.summary)
    mapped_row = _first(mapped.summary)
    diagnostic_row = _diagnostic_overall(diagnostics)
    next_gate = _primary_next_gate(action_queue)
    return pd.DataFrame(
        [
            {
                "ready": bool(readiness.ready and failed == 0),
                "adapter": config.adapter,
                "kind": config.kind,
                "market": config.market,
                "input_path": str(source_file),
                "mapping_path": str(mapping_file),
                "mapping_source": mapping_source,
                "normalized_output_file": _output_filename(config),
                "source_columns": int(_number(intake_row, "source_columns", fallback=0.0)),
                "source_file_sha256": _text(intake_row, "source_file_sha256"),
                "source_header_sha256": _text(intake_row, "source_header_sha256"),
                "mapping_draft_sha256": _text(intake_row, "mapping_draft_sha256"),
                "mapping_coverage": _number(intake_row, "mapping_coverage", fallback=0.0),
                "input_rows": int(_number(mapped_row, "input_rows", fallback=0.0)),
                "normalized_rows": int(_number(mapped_row, "output_rows", fallback=0.0)),
                "diagnostic_rows": int(_number(diagnostic_row, "rows", fallback=0.0)),
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
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Dataset count: {int(_number_from_value(summary_row.get('dataset_count', 0)))}",
        f"- Ready datasets: {int(_number_from_value(summary_row.get('ready_datasets', 0)))}",
        f"- Failed datasets: {int(_number_from_value(summary_row.get('failed_datasets', 0)))}",
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
        ["Dataset", "Ready", "Rows", "Failed components", "Recommendation"],
        [
            [
                _value_text(row.get("dataset")),
                "yes" if _truthy(row.get("ready")) else "no",
                str(int(_number_from_value(row.get("normalized_rows", 0)))),
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
    return pd.DataFrame(
        [
            {
                "ready": bool(accepted and failed_datasets == 0),
                "adapter": config.adapter,
                "kind": config.kind,
                "market": config.market,
                "dataset_count": dataset_count,
                "ready_datasets": ready_datasets,
                "failed_datasets": failed_datasets,
                "ready_rate": float(ready_datasets / dataset_count) if dataset_count else 0.0,
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
        },
        "normalized": {
            "output_file": _text(row, "normalized_output_file"),
            "input_rows": int(_number(row, "input_rows", fallback=0.0)),
            "rows": int(_number(row, "normalized_rows", fallback=0.0)),
            "timestamp_unit": config.timestamp_unit,
            "timestamp_tz": config.timestamp_tz,
            "filter_session": bool(config.filter_session),
        },
        "diagnostics": {
            "rows": int(_number(row, "diagnostic_rows", fallback=0.0)),
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
            "source_file_sha256": str(item.get("source_file_sha256", "")),
            "source_header_sha256": str(item.get("source_header_sha256", "")),
            "mapping_draft_sha256": str(item.get("mapping_draft_sha256", "")),
            "mapping_source": str(item.get("mapping_source", "")),
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
        "dataset_count": int(_number(row, "dataset_count", fallback=0.0)),
        "ready_datasets": int(_number(row, "ready_datasets", fallback=0.0)),
        "failed_datasets": int(_number(row, "failed_datasets", fallback=0.0)),
        "ready_rate": _number(row, "ready_rate", fallback=0.0),
        "unique_source_files": int(_number(row, "unique_source_files", fallback=0.0)),
        "source_file_fingerprint_coverage": _number(row, "source_file_fingerprint_coverage", fallback=0.0),
        "min_mapping_coverage": _number(row, "min_mapping_coverage", fallback=0.0),
        "unique_header_fingerprints": int(_number(row, "unique_header_fingerprints", fallback=0.0)),
        "unique_mapping_drafts": int(_number(row, "unique_mapping_drafts", fallback=0.0)),
        "mapping_sources": _text(row, "mapping_sources"),
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
