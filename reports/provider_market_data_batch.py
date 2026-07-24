from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from markets.calendars import market_calendar_summary, resolve_market_calendar
from reports.data_readiness_comparison import (
    DataReadinessComparisonReport,
    DataReadinessComparisonThresholds,
    write_data_readiness_comparison,
)
from reports.manifest import write_experiment_manifest
from reports.provider_market_data_pipeline import (
    ProviderMarketDataPipelineConfig,
    ProviderMarketDataPipelineReport,
    write_provider_market_data_pipeline,
)


@dataclass(frozen=True)
class ProviderMarketDataBatchConfig:
    min_capture_rows: int = 1
    max_missing_required_columns: int = 0
    max_null_required_cells: int = 0
    require_monotonic_ts: bool = True
    expected_market: str = "india_nse_index_derivatives"
    market_calendar_path: str | None = None
    expected_kind: str = "ticks"
    sample_rows: int = 1000
    tick_size: float | None = None
    timestamp_unit: str = "datetime"
    timestamp_tz: str | None = None
    pipeline_min_rows: int = 1
    max_null_rows: int = 0
    max_nonfinite_rows: int = 0
    max_nonintegral_rows: int = 0
    max_duplicate_tick_rows: int = 0
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_non_trading_day_rows: int = 0
    max_out_of_session_rows: int = 0
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None
    min_datasets: int | None = None
    min_ready_datasets: int | None = None
    min_ready_rate: float = 1.0
    max_total_failed_checks: int = 0
    min_unique_source_files: int | None = None
    min_source_file_fingerprint_coverage: float | None = 1.0
    min_mapping_coverage: float | None = 1.0


@dataclass(frozen=True)
class ProviderMarketDataBatchReport:
    datasets: pd.DataFrame
    summary: pd.DataFrame
    comparison: DataReadinessComparisonReport | None
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_batch_pipeline(
    client_packet_path: str | Path,
    capture_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    config: ProviderMarketDataBatchConfig | None = None,
) -> ProviderMarketDataBatchReport:
    config = config or ProviderMarketDataBatchConfig()
    _validate_config(config)
    packet = Path(client_packet_path)
    captures = [Path(path) for path in capture_paths]
    if not captures:
        raise ValueError("at least one provider market-data capture is required")
    if labels is not None and len(labels) != len(captures):
        raise ValueError("labels must match capture paths")
    for capture in captures:
        if not capture.exists():
            raise FileNotFoundError(f"provider market-data capture not found: {capture}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    datasets_rows: list[dict[str, Any]] = []
    dataset_action_rows: list[dict[str, Any]] = []
    dataset_manifest_paths: list[Path] = []
    readiness_dirs: list[Path] = []
    readiness_labels: list[str] = []
    pipeline_config = _pipeline_config(config)

    for idx, capture in enumerate(captures):
        label = labels[idx] if labels is not None else capture.stem
        dataset_dir = out / "captures" / _safe_label(label, idx)
        report = write_provider_market_data_pipeline(
            packet,
            capture,
            output_dir=dataset_dir,
            config=pipeline_config,
        )
        dataset_manifest_path = dataset_dir / "manifest.json"
        if dataset_manifest_path.exists():
            dataset_manifest_paths.append(dataset_manifest_path)
        readiness_dir = dataset_dir / "02_vendor_market_data_pipeline" / "04_data_readiness"
        if (readiness_dir / "data_readiness_summary.csv").exists():
            readiness_dirs.append(readiness_dir)
            readiness_labels.append(label)
        dataset_action_rows.extend(
            _promote_dataset_actions(
                report.action_queue,
                dataset=label,
                pipeline_dir=dataset_dir,
            )
        )
        datasets_rows.append(_dataset_row(label, capture, dataset_dir, readiness_dir, report))

    thresholds = _comparison_thresholds(config, len(captures))
    comparison = None
    comparison_action_rows: list[dict[str, Any]] = []
    if readiness_dirs:
        comparison = write_data_readiness_comparison(
            readiness_dirs,
            output_dir=out / "comparison",
            labels=readiness_labels,
            thresholds=thresholds,
        )
        comparison_action_rows = _promote_comparison_actions(comparison.action_queue)
    else:
        comparison_action_rows = [
            _action(
                "blocked",
                "comparison",
                "",
                "data_readiness_available",
                "pipeline-provider-market-data-batch",
                "python -m hft_cli pipeline-provider-market-data-batch --help",
                "no data-readiness outputs were produced; repair provider capture reviews first",
                "fix_provider_market_data_batch",
                "",
            )
        ]

    datasets = pd.DataFrame(datasets_rows)
    action_queue = _action_queue_frame([*dataset_action_rows, *comparison_action_rows])
    summary = _summary(datasets, comparison, action_queue, config)
    batch_config = _config(summary.iloc[0], datasets, action_queue, comparison, thresholds, config)

    datasets.to_csv(out / "provider_market_data_batch_datasets.csv", index=False)
    summary.to_csv(out / "provider_market_data_batch_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_batch_action_queue.csv", index=False)
    (out / "provider_market_data_batch_config.json").write_text(
        json.dumps(batch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_batch_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], datasets, action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "client_packet": packet,
        "captures": captures,
    }
    if config.market_calendar_path:
        inputs["market_calendar"] = Path(config.market_calendar_path)
    if dataset_manifest_paths:
        inputs["dataset_manifests"] = dataset_manifest_paths
    comparison_manifest = out / "comparison" / "manifest.json"
    if comparison_manifest.exists():
        inputs["comparison_manifest"] = comparison_manifest
    write_experiment_manifest(
        out,
        run_type="provider_market_data_batch_pipeline",
        parameters={
            "config": asdict(config),
            "pipeline_config": asdict(pipeline_config),
            "comparison_thresholds": asdict(thresholds),
            "labels": labels,
        },
        inputs=inputs,
        extra={"ready": bool(summary.iloc[0]["ready"])},
    )
    return ProviderMarketDataBatchReport(datasets, summary, comparison, action_queue, batch_config, out)


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


def _pipeline_config(config: ProviderMarketDataBatchConfig) -> ProviderMarketDataPipelineConfig:
    return ProviderMarketDataPipelineConfig(
        min_capture_rows=config.min_capture_rows,
        max_missing_required_columns=config.max_missing_required_columns,
        max_null_required_cells=config.max_null_required_cells,
        require_monotonic_ts=config.require_monotonic_ts,
        expected_market=config.expected_market,
        market_calendar_path=config.market_calendar_path,
        expected_kind=config.expected_kind,
        sample_rows=config.sample_rows,
        tick_size=config.tick_size,
        timestamp_unit=config.timestamp_unit,
        timestamp_tz=config.timestamp_tz,
        pipeline_min_rows=config.pipeline_min_rows,
        max_null_rows=config.max_null_rows,
        max_nonfinite_rows=config.max_nonfinite_rows,
        max_nonintegral_rows=config.max_nonintegral_rows,
        max_duplicate_tick_rows=config.max_duplicate_tick_rows,
        max_crossed_quote_rows=config.max_crossed_quote_rows,
        max_nonpositive_quote_rows=config.max_nonpositive_quote_rows,
        max_nonpositive_depth_rows=config.max_nonpositive_depth_rows,
        max_non_trading_day_rows=config.max_non_trading_day_rows,
        max_out_of_session_rows=config.max_out_of_session_rows,
        max_p99_gap_ns=config.max_p99_gap_ns,
        max_median_spread_ticks=config.max_median_spread_ticks,
    )


def _comparison_thresholds(config: ProviderMarketDataBatchConfig, capture_count: int) -> DataReadinessComparisonThresholds:
    return DataReadinessComparisonThresholds(
        min_datasets=config.min_datasets if config.min_datasets is not None else capture_count,
        min_ready_datasets=config.min_ready_datasets if config.min_ready_datasets is not None else capture_count,
        min_ready_rate=config.min_ready_rate,
        max_total_failed_checks=config.max_total_failed_checks,
        min_unique_source_files=config.min_unique_source_files
        if config.min_unique_source_files is not None
        else capture_count,
        min_source_file_fingerprint_coverage=config.min_source_file_fingerprint_coverage,
        min_mapping_coverage=config.min_mapping_coverage,
        require_market_calendar=bool(config.market_calendar_path),
        require_consistent_market_calendar=bool(config.market_calendar_path),
    )


def _dataset_row(
    label: str,
    capture: Path,
    dataset_dir: Path,
    readiness_dir: Path,
    report: ProviderMarketDataPipelineReport,
) -> dict[str, Any]:
    root_row = report.summary.iloc[0] if not report.summary.empty else pd.Series(dtype=object)
    vendor_row = (
        report.vendor_pipeline.summary.iloc[0]
        if report.vendor_pipeline is not None and not report.vendor_pipeline.summary.empty
        else pd.Series(dtype=object)
    )
    return {
        "dataset": label,
        "capture_path": str(capture),
        "pipeline_dir": str(dataset_dir),
        "data_readiness_dir": str(readiness_dir),
        "ready": bool(report.ready),
        "capture_ready": _truthy(root_row.get("capture_ready", False)),
        "vendor_pipeline_ready": _truthy(root_row.get("vendor_pipeline_ready", False)),
        "provider": _text(root_row, "provider"),
        "market": _text(root_row, "market"),
        "kind": _text(root_row, "kind"),
        "normalized_rows": int(_number(vendor_row, "normalized_rows", fallback=0.0)),
        "failed_components": int(_number(root_row, "failed_components", fallback=1.0)),
        "source_file_sha256": _text(vendor_row, "source_file_sha256"),
        "source_header_sha256": _text(vendor_row, "source_header_sha256"),
        "mapping_draft_sha256": _text(vendor_row, "mapping_draft_sha256"),
        "mapping_source": _text(vendor_row, "mapping_source"),
        "data_readiness_manifest_path": _text(vendor_row, "data_readiness_manifest_path"),
        "recommendation": _text(root_row, "recommendation"),
    }


def _promote_dataset_actions(action_queue: pd.DataFrame, *, dataset: str, pipeline_dir: Path) -> list[dict[str, Any]]:
    if action_queue is None or action_queue.empty:
        return []
    rows = []
    blocked = action_queue.loc[action_queue["queue_status"].astype(str) == "blocked"]
    for item in blocked.to_dict(orient="records"):
        next_gate = _provider_next_gate(str(item.get("next_gate", "")))
        rows.append(
            _action(
                "blocked",
                "dataset_pipeline",
                dataset,
                str(item.get("component", "")),
                next_gate,
                _next_gate_help_command(next_gate),
                str(item.get("reason", "")),
                str(item.get("action", "fix_provider_market_data_pipeline")),
                str(pipeline_dir),
            )
        )
    return rows


def _promote_comparison_actions(action_queue: pd.DataFrame | None) -> list[dict[str, Any]]:
    if action_queue is None or action_queue.empty:
        return []
    rows = []
    for item in action_queue.to_dict(orient="records"):
        next_gate = _provider_next_gate(str(item.get("next_gate", "")))
        rows.append(
            _action(
                str(item.get("queue_status", "blocked")),
                "comparison",
                "",
                str(item.get("check", "")),
                next_gate,
                _next_gate_help_command(next_gate),
                str(item.get("reason", "")),
                str(item.get("recommendation", "fix_provider_market_data_batch")),
                "",
            )
        )
    return rows


def _action(
    status: str,
    source: str,
    dataset: str,
    check: str,
    next_gate: str,
    help_command: str,
    reason: str,
    recommendation: str,
    pipeline_dir: str,
) -> dict[str, Any]:
    return {
        "priority": 0,
        "queue_status": status,
        "source": source,
        "dataset": dataset,
        "component": check,
        "check": check,
        "next_gate": next_gate,
        "next_gate_help_command": help_command,
        "reason": reason,
        "recommendation": recommendation,
        "pipeline_dir": pipeline_dir,
    }


def _action_queue_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        ordered = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        ordered["priority"] = priority
        if not ordered["queue_status"]:
            ordered["queue_status"] = "blocked"
        ordered_rows.append(ordered)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _summary(
    datasets: pd.DataFrame,
    comparison: DataReadinessComparisonReport | None,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataBatchConfig,
) -> pd.DataFrame:
    dataset_count = int(len(datasets))
    ready_datasets = int(datasets["ready"].astype(bool).sum()) if dataset_count else 0
    failed_datasets = dataset_count - ready_datasets
    comparison_row = comparison.summary.iloc[0] if comparison is not None and not comparison.summary.empty else pd.Series(dtype=object)
    comparison_accepted = bool(comparison.accepted) if comparison is not None else False
    blocked_actions = (
        int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    )
    next_gate = _primary_next_gate(action_queue)
    ready = bool(dataset_count > 0 and failed_datasets == 0 and comparison_accepted and blocked_actions == 0)
    calendar = resolve_market_calendar(
        config.market_calendar_path,
        market=config.expected_market,
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": "normalized",
                "kind": config.expected_kind,
                "market": config.expected_market,
                **market_calendar_summary(calendar),
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
                "comparison_accepted": comparison_accepted,
                "comparison_ready_rate": _number(comparison_row, "ready_rate", fallback=0.0),
                "comparison_failed_checks": int(_number(comparison_row, "total_failed_checks", fallback=0.0)),
                "ready_action_count": 0,
                "blocked_action_count": blocked_actions,
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
                "recommendation": "feed_walkforward_research" if ready else "fix_provider_market_data_batch",
            }
        ]
    )


def _config(
    row: pd.Series,
    datasets: pd.DataFrame,
    action_queue: pd.DataFrame,
    comparison: DataReadinessComparisonReport | None,
    thresholds: DataReadinessComparisonThresholds,
    config: ProviderMarketDataBatchConfig,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    comparison_summary = (
        {}
        if comparison is None or comparison.summary.empty
        else {str(key): _jsonable(value) for key, value in comparison.summary.iloc[0].to_dict().items()}
    )
    return {
        "schema_version": 1,
        "ready": bool(row["ready"]),
        "parameters": asdict(config),
        "market_calendar": {
            "provided": bool(row.get("market_calendar_provided", False)),
            "policy": _text(row, "market_calendar_policy"),
            "id": _text(row, "market_calendar_id"),
            "path": _text(row, "market_calendar_path"),
            "sha256": _text(row, "market_calendar_sha256"),
            "valid_from": _text(row, "market_calendar_valid_from"),
            "valid_to": _text(row, "market_calendar_valid_to"),
        },
        "comparison": {
            "accepted": bool(row["comparison_accepted"]),
            "thresholds": asdict(thresholds),
            "summary": comparison_summary,
        },
        "dataset_count": int(_number(row, "dataset_count", fallback=0.0)),
        "ready_datasets": int(_number(row, "ready_datasets", fallback=0.0)),
        "failed_datasets": int(_number(row, "failed_datasets", fallback=0.0)),
        "ready_rate": _number(row, "ready_rate", fallback=0.0),
        "unique_source_files": int(_number(row, "unique_source_files", fallback=0.0)),
        "source_file_fingerprint_coverage": _number(row, "source_file_fingerprint_coverage", fallback=0.0),
        "min_mapping_coverage": _number(row, "min_mapping_coverage", fallback=0.0),
        "datasets": _records(datasets),
        "ready_action_count": int(_number(row, "ready_action_count", fallback=0.0)),
        "blocked_action_count": int(_number(row, "blocked_action_count", fallback=0.0)),
        "next_gate": _text(row, "next_gate"),
        "next_gate_help_command": _text(row, "next_gate_help_command"),
        "primary_action_status": str(primary_action.get("queue_status", "")),
        "primary_action": primary_action,
        "next_actions": _records(action_queue),
        "ready_actions": _records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _records(_actions_with_status(action_queue, "blocked")),
        "recommendation": _text(row, "recommendation"),
    }


def _runbook_markdown(summary: pd.Series, datasets: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Batch Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Market: {summary['market']}",
        f"- Market calendar: {summary['market_calendar_id'] or 'not provided'}",
        f"- Calendar SHA-256: {summary['market_calendar_sha256']}",
        f"- Kind: {summary['kind']}",
        f"- Dataset count: {int(_number(summary, 'dataset_count', fallback=0.0))}",
        f"- Ready datasets: {int(_number(summary, 'ready_datasets', fallback=0.0))}",
        f"- Failed datasets: {int(_number(summary, 'failed_datasets', fallback=0.0))}",
        f"- Primary next gate: `{summary['next_gate']}`" if str(summary["next_gate"]) else "- Primary next gate: ",
        "",
        "## Blocked Actions",
        "",
        _action_table(action_queue),
        "",
        "## Datasets",
        "",
        _dataset_table(datasets),
        "",
    ]
    return "\n".join(lines)


def _action_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = []
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            [
                str(int(_number_from_value(item.get("priority", 0)))),
                _value_text(item.get("source")),
                _value_text(item.get("dataset")),
                _value_text(item.get("check")),
                _value_text(item.get("next_gate")),
                _value_text(item.get("recommendation")),
            ]
        )
    return _markdown_table(["Priority", "Source", "Dataset", "Check", "Next gate", "Recommendation"], rows)


def _dataset_table(datasets: pd.DataFrame) -> str:
    if datasets.empty:
        return "_None_"
    rows = []
    for item in datasets.to_dict(orient="records"):
        rows.append(
            [
                _value_text(item.get("dataset")),
                "yes" if _truthy(item.get("ready")) else "no",
                str(int(_number_from_value(item.get("normalized_rows", 0)))),
                str(int(_number_from_value(item.get("failed_components", 0)))),
                _value_text(item.get("recommendation")),
            ]
        )
    return _markdown_table(["Dataset", "Ready", "Rows", "Failed components", "Recommendation"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _provider_next_gate(next_gate: str) -> str:
    if next_gate == "pipeline-vendor-market-data-batch":
        return "pipeline-provider-market-data-batch"
    if next_gate == "pipeline-vendor-market-data":
        return "pipeline-provider-market-data"
    return next_gate


def _next_gate_help_command(next_gate: str) -> str:
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _primary_next_gate(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return ""
    return _value_text(action_queue.iloc[0].get("next_gate"))


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        rows.append({str(key): _jsonable(value) for key, value in record.items()})
    return rows


def _first_action_record(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _unique_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    values = frame[column].dropna().astype(str).str.strip()
    return int(values.loc[values != ""].nunique())


def _safe_label(label: str, idx: int) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(label).strip())
    return safe or f"capture_{idx + 1}"


def _validate_config(config: ProviderMarketDataBatchConfig) -> None:
    resolve_market_calendar(
        config.market_calendar_path,
        market=config.expected_market,
    )
    if config.min_capture_rows <= 0:
        raise ValueError("min_capture_rows must be positive")
    if config.pipeline_min_rows <= 0:
        raise ValueError("pipeline_min_rows must be positive")
    if not 0 <= config.min_ready_rate <= 1:
        raise ValueError("min_ready_rate must be between 0 and 1")
    for name in (
        "max_missing_required_columns",
        "max_null_required_cells",
        "max_null_rows",
        "max_nonfinite_rows",
        "max_nonintegral_rows",
        "max_duplicate_tick_rows",
        "max_crossed_quote_rows",
        "max_nonpositive_quote_rows",
        "max_nonpositive_depth_rows",
        "max_non_trading_day_rows",
        "max_out_of_session_rows",
        "max_total_failed_checks",
    ):
        if getattr(config, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in (
        "tick_size",
        "max_p99_gap_ns",
        "max_median_spread_ticks",
        "min_source_file_fingerprint_coverage",
        "min_mapping_coverage",
    ):
        value = getattr(config, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")


def _number(row: pd.Series, column: str, *, fallback: float = 0.0) -> float:
    if row.empty or column not in row:
        return float(fallback)
    return _number_from_value(row.get(column), fallback=fallback)


def _number_from_value(value: object, *, fallback: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return float(fallback)
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _text(row: pd.Series, column: str, *, fallback: str = "") -> str:
    if row.empty or column not in row:
        return fallback
    return _value_text(row.get(column), fallback=fallback)


def _value_text(value: object, *, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    text = _value_text(value).lower()
    return text in {"1", "true", "yes", "y", "ready"}


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
