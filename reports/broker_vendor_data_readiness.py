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

_VENDOR_BATCH_PREFIXES = (
    "",
    "broker_dispatch_roundtrip_vendor_market_data_batch",
    "dispatch_roundtrip_vendor_market_data_batch",
)
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
    checks: pd.DataFrame
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
    summary = _summary(components, vendor_batch, broker_readiness, config)
    checks = _checks(summary.iloc[0], components, config)
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    summary.loc[summary.index[0], "failed_checks"] = failed_checks
    summary.loc[summary.index[0], "ready"] = failed_checks == 0
    summary.loc[summary.index[0], "recommendation"] = (
        "broker_data_proof_ready" if failed_checks == 0 else "fix_vendor_or_broker_readiness_proof"
    )
    components.to_csv(out / "broker_vendor_data_readiness_components.csv", index=False)
    summary.to_csv(out / "broker_vendor_data_readiness_summary.csv", index=False)
    checks.to_csv(out / "broker_vendor_data_readiness_checks.csv", index=False)
    action_queue = _action_queue(checks)
    action_queue.to_csv(out / "broker_vendor_data_readiness_action_queue.csv", index=False)
    (out / "broker_vendor_data_readiness_config.json").write_text(
        json.dumps(_config(summary.iloc[0], components, checks, config, broker_thresholds), indent=2, sort_keys=True)
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
    return BrokerVendorDataReadinessReport(vendor_batch, broker_readiness, components, summary, checks, out)


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
                "unique_header_fingerprints": _int(vendor_row.get("unique_header_fingerprints", 0)),
                "source_file_fingerprint_coverage": _float(
                    vendor_row.get("source_file_fingerprint_coverage", 0.0)
                ),
                "min_mapping_coverage": _float(vendor_row.get("min_mapping_coverage", 0.0)),
                "unique_mapping_drafts": _int(vendor_row.get("unique_mapping_drafts", 0)),
                "mapping_sources": str(vendor_row.get("mapping_sources", "")),
                "comparison_accepted": bool(vendor_row.get("comparison_accepted", False)),
                "comparison_failed_checks": _int(vendor_row.get("comparison_failed_checks", 0)),
                "broker_vendor_data_ready": bool(
                    broker_row.get("broker_dispatch_roundtrip_vendor_market_data_batch_ready", False)
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
        failed = checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)
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


def _action_component(check_name: str) -> str:
    if check_name in {"broker_readiness_ready", "broker_vendor_data_ready"}:
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
        f"- Recommendation: {str(row.get('recommendation', ''))}",
        f"- Failed checks: {_int(row.get('failed_checks', 0))}",
        f"- Dataset count: {_int(row.get('dataset_count', 0))}",
        f"- Ready datasets: {_int(row.get('ready_datasets', 0))}",
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
    config: BrokerVendorDataReadinessConfig,
    broker_thresholds: BrokerReadinessThresholds,
) -> dict[str, object]:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    return {
        "schema_version": 1,
        "ready": bool(row.get("ready", False)),
        "adapter": config.adapter,
        "kind": config.kind,
        "market": config.market,
        "vendor_market_data_batch": {
            "ready": bool(row.get("vendor_batch_ready", False)),
            "dataset_count": _int(row.get("dataset_count", 0)),
            "ready_datasets": _int(row.get("ready_datasets", 0)),
            "failed_datasets": _int(row.get("failed_datasets", 0)),
            "unique_source_files": _int(row.get("unique_source_files", 0)),
            "unique_header_fingerprints": _int(row.get("unique_header_fingerprints", 0)),
            "source_file_fingerprint_coverage": _float(row.get("source_file_fingerprint_coverage", 0.0)),
            "min_mapping_coverage": _float(row.get("min_mapping_coverage", 0.0)),
            "unique_mapping_drafts": _int(row.get("unique_mapping_drafts", 0)),
            "mapping_sources": str(row.get("mapping_sources", "")),
            "comparison": {
                "accepted": bool(row.get("comparison_accepted", False)),
                "failed_checks": _int(row.get("comparison_failed_checks", 0)),
            },
        },
        "broker_readiness": {
            "ready": bool(row.get("broker_readiness_ready", False)),
            "broker_vendor_data_ready": bool(row.get("broker_vendor_data_ready", False)),
        },
        "broker_thresholds": asdict(broker_thresholds),
        "failed_check_count": _int(row.get("failed_checks", len(failed))),
        "failed_checks": failed,
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


def _vendor_value(row: pd.Series, suffix: str, fallback: object) -> object:
    for prefix in _VENDOR_BATCH_PREFIXES:
        column = suffix if not prefix else f"{prefix}_{suffix}"
        if column in row.index:
            value = row.get(column, fallback)
            if not pd.isna(value):
                return value
    return fallback
