from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from markets.calendars import market_calendar_summary, resolve_market_calendar
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.provider_market_data_capture import (
    ProviderMarketDataCaptureConfig,
    ProviderMarketDataCaptureReport,
    write_provider_market_data_capture_review,
)
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    VendorMarketDataPipelineReport,
    write_vendor_market_data_pipeline,
)


@dataclass(frozen=True)
class ProviderMarketDataPipelineConfig:
    min_capture_rows: int = 1
    max_missing_required_columns: int = 0
    max_null_required_cells: int = 0
    require_monotonic_ts: bool = True
    expected_market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    market_calendar_path: str | None = None
    expected_kind: str = "ticks"
    sample_rows: int = 1000
    tick_size: float | None = None
    strike_step: float | None = None
    timestamp_unit: str = "datetime"
    timestamp_tz: str | None = None
    pipeline_min_rows: int = 1
    max_null_rows: int = 0
    max_nonfinite_rows: int = 0
    max_nonintegral_rows: int = 0
    max_duplicate_tick_rows: int = 0
    max_integer_overflow_rows: int = 0
    max_nonmonotonic_rows: int = 0
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_strike_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_invalid_trade_rows: int = 0
    max_off_tick_price_rows: int | None = None
    max_off_grid_strike_rows: int | None = None
    max_non_trading_day_rows: int = 0
    max_out_of_session_rows: int = 0
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None


@dataclass(frozen=True)
class ProviderMarketDataPipelineReport:
    components: pd.DataFrame
    summary: pd.DataFrame
    capture_review: ProviderMarketDataCaptureReport
    vendor_pipeline: VendorMarketDataPipelineReport | None
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_pipeline(
    client_packet_path: str | Path,
    capture_path: str | Path,
    *,
    output_dir: str | Path,
    config: ProviderMarketDataPipelineConfig | None = None,
) -> ProviderMarketDataPipelineReport:
    config = config or ProviderMarketDataPipelineConfig()
    resolve_market_calendar(
        config.market_calendar_path,
        market=config.expected_market,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    capture_dir = out / "01_capture_review"
    vendor_dir = out / "02_vendor_market_data_pipeline"
    capture = write_provider_market_data_capture_review(
        client_packet_path,
        capture_path,
        capture_dir,
        config=ProviderMarketDataCaptureConfig(
            min_rows=config.min_capture_rows,
            max_missing_required_columns=config.max_missing_required_columns,
            max_null_required_cells=config.max_null_required_cells,
            require_monotonic_ts=config.require_monotonic_ts,
            expected_market=config.expected_market,
            expected_kind=config.expected_kind,
            pipeline_output_dir=str(vendor_dir),
        ),
    )
    vendor = None
    if capture.ready:
        capture_summary = capture.summary.iloc[0]
        vendor = write_vendor_market_data_pipeline(
            capture_path,
            output_dir=vendor_dir,
            config=VendorMarketDataPipelineConfig(
                adapter="normalized",
                kind=str(capture_summary["kind"]),
                sample_rows=config.sample_rows,
                min_mapping_coverage=1.0,
                output_filename=None,
                timestamp_unit=config.timestamp_unit,
                timestamp_tz=config.timestamp_tz,
                filter_session=True,
                market=str(capture_summary["market"]),
                market_calendar_path=config.market_calendar_path,
                tick_size=config.tick_size,
                strike_step=config.strike_step,
                require_all_mapped=True,
                min_rows=config.pipeline_min_rows,
                max_null_rows=config.max_null_rows,
                max_nonfinite_rows=config.max_nonfinite_rows,
                max_nonintegral_rows=config.max_nonintegral_rows,
                max_duplicate_tick_rows=config.max_duplicate_tick_rows,
                max_integer_overflow_rows=config.max_integer_overflow_rows,
                max_nonmonotonic_rows=config.max_nonmonotonic_rows,
                max_crossed_quote_rows=config.max_crossed_quote_rows,
                max_nonpositive_quote_rows=config.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=config.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=config.max_nonpositive_depth_rows,
                max_invalid_trade_rows=config.max_invalid_trade_rows,
                max_off_tick_price_rows=config.max_off_tick_price_rows,
                max_off_grid_strike_rows=config.max_off_grid_strike_rows,
                max_non_trading_day_rows=config.max_non_trading_day_rows,
                max_out_of_session_rows=config.max_out_of_session_rows,
                max_p99_gap_ns=config.max_p99_gap_ns,
                max_median_spread_ticks=config.max_median_spread_ticks,
            ),
        )

    components = _components(capture, vendor)
    action_queue = _action_queue(capture, vendor)
    summary = _summary(
        client_packet_path,
        capture_path,
        components,
        capture,
        vendor,
        action_queue,
        config,
    )
    pipeline_config = _config(summary.iloc[0], components, action_queue, capture, vendor, config)

    components.to_csv(out / "provider_market_data_pipeline_components.csv", index=False)
    summary.to_csv(out / "provider_market_data_pipeline_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_pipeline_action_queue.csv", index=False)
    (out / "provider_market_data_pipeline_config.json").write_text(
        json.dumps(pipeline_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_pipeline_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], components, action_queue),
        encoding="utf-8",
    )
    inputs = {
        "client_packet": Path(client_packet_path),
        "capture": Path(capture_path),
        "capture_review_manifest": capture_dir / "manifest.json",
    }
    if vendor is not None:
        inputs["vendor_pipeline_manifest"] = vendor_dir / "manifest.json"
    if config.market_calendar_path:
        inputs["market_calendar"] = Path(config.market_calendar_path)
    write_experiment_manifest(
        out,
        run_type="provider_market_data_pipeline",
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "capture_review": capture.config,
            "vendor_pipeline": {} if vendor is None else _vendor_config(vendor),
        },
    )
    return ProviderMarketDataPipelineReport(components, summary, capture, vendor, action_queue, pipeline_config, out)


def _components(
    capture: ProviderMarketDataCaptureReport,
    vendor: VendorMarketDataPipelineReport | None,
) -> pd.DataFrame:
    rows = [
        {
            "component": "capture_review",
            "ready": bool(capture.ready),
            "output_dir": "" if capture.output_dir is None else str(capture.output_dir),
            "summary_file": "provider_market_data_capture_summary.csv",
            "manifest_file": "manifest.json",
        }
    ]
    rows.append(
        {
            "component": "vendor_market_data_pipeline",
            "ready": bool(vendor.ready) if vendor is not None else False,
            "output_dir": "" if vendor is None or vendor.output_dir is None else str(vendor.output_dir),
            "summary_file": "vendor_market_data_pipeline_summary.csv",
            "manifest_file": "manifest.json",
        }
    )
    return pd.DataFrame(rows)


def _summary(
    client_packet_path: str | Path,
    capture_path: str | Path,
    components: pd.DataFrame,
    capture: ProviderMarketDataCaptureReport,
    vendor: VendorMarketDataPipelineReport | None,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataPipelineConfig,
) -> pd.DataFrame:
    capture_summary = capture.summary.iloc[0]
    vendor_ready = bool(vendor.ready) if vendor is not None else False
    failed_components = int((~components["ready"].astype(bool)).sum()) if not components.empty else 0
    blocked_actions = (
        int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    )
    ready = bool(capture.ready and vendor_ready and blocked_actions == 0)
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    calendar = resolve_market_calendar(
        config.market_calendar_path,
        market=config.expected_market,
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "client_packet_path": str(client_packet_path),
                "capture_path": str(capture_path),
                "provider": str(capture_summary["provider"]),
                "adapter": "normalized",
                "market": str(capture_summary["market"]),
                **market_calendar_summary(calendar),
                "kind": str(capture_summary["kind"]),
                "capture_ready": bool(capture.ready),
                "vendor_pipeline_ready": vendor_ready,
                "failed_components": failed_components,
                "blocked_action_count": blocked_actions,
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum())
                if not action_queue.empty
                else 0,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "provider_market_data_pipeline_ready"
                if ready
                else "fix_provider_market_data_pipeline",
            }
        ]
    )


def _action_queue(
    capture: ProviderMarketDataCaptureReport,
    vendor: VendorMarketDataPipelineReport | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not capture.ready:
        rows.extend(_prefixed_actions(capture.action_queue, "capture_review"))
    elif vendor is None:
        rows.append(
            _action(
                "blocked",
                "run_provider_capture_market_data_pipeline",
                "capture review is ready but vendor pipeline did not run",
                "pipeline-vendor-market-data",
                "python -m hft_cli pipeline-vendor-market-data --help",
            )
        )
    elif not vendor.ready:
        rows.extend(_prefixed_actions(vendor.action_queue, "vendor_market_data_pipeline"))
    else:
        rows.append(
            _action(
                "ready",
                "feed_provider_market_data_to_research",
                "provider capture and normalized market-data pipeline are ready",
                "review-data-readiness",
                "pipeline output contains 04_data_readiness/data_readiness_summary.csv",
            )
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "action",
            "reason",
            "component",
            "next_gate",
            "next_gate_help_command",
        ],
    )


def _prefixed_actions(action_queue: pd.DataFrame | None, component: str) -> list[dict[str, Any]]:
    if action_queue is None or action_queue.empty:
        return [
            _action(
                "blocked",
                f"repair_{component}",
                f"{component} is not ready",
                component,
                "",
            )
        ]
    rows = []
    for _, row in action_queue.iterrows():
        rows.append(
            _action(
                str(row.get("queue_status", "blocked")),
                str(row.get("action", f"repair_{component}")),
                str(row.get("reason", f"{component} is not ready")),
                str(row.get("next_gate", component)),
                str(row.get("next_gate_help_command", "")),
                component=component,
            )
        )
    return rows


def _action(
    status: str,
    action: str,
    reason: str,
    next_gate: str,
    help_command: str,
    *,
    component: str = "provider_market_data_pipeline",
) -> dict[str, Any]:
    return {
        "priority": 0,
        "queue_status": status,
        "action": action,
        "reason": reason,
        "component": component,
        "next_gate": next_gate,
        "next_gate_help_command": help_command,
    }


def _config(
    summary: pd.Series,
    components: pd.DataFrame,
    action_queue: pd.DataFrame,
    capture: ProviderMarketDataCaptureReport,
    vendor: VendorMarketDataPipelineReport | None,
    config: ProviderMarketDataPipelineConfig,
) -> dict[str, Any]:
    next_action = _first_record(action_queue)
    records = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "components": _records(components),
        "capture_review": capture.config,
        "vendor_pipeline": {} if vendor is None else _vendor_config(vendor),
        "next_gate": "" if next_action is None else str(next_action["next_gate"]),
        "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
        "next_actions": records,
        "ready_actions": [row for row in records if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in records if row.get("queue_status") == "blocked"],
        "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
        "primary_action": {} if next_action is None else next_action,
    }


def _vendor_config(vendor: VendorMarketDataPipelineReport) -> dict[str, Any]:
    summary = vendor.summary.iloc[0]
    return {
        "ready": bool(vendor.ready),
        "output_dir": "" if vendor.output_dir is None else str(vendor.output_dir),
        "summary": {str(key): _jsonable(value) for key, value in summary.to_dict().items()},
        "action_queue": _records(vendor.action_queue) if vendor.action_queue is not None else [],
    }


def _runbook_markdown(summary: pd.Series, components: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Pipeline Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Market calendar: {summary['market_calendar_id'] or 'not provided'}",
        f"- Calendar SHA-256: {summary['market_calendar_sha256']}",
        f"- Kind: {summary['kind']}",
        "",
        "## Components",
    ]
    for _, row in components.iterrows():
        lines.append(f"- {row['component']}: {'ready' if bool(row['ready']) else 'blocked'} ({row['output_dir']})")
    lines.extend(["", "## Actions"])
    if action_queue.empty:
        lines.append("- None")
    else:
        for _, row in action_queue.iterrows():
            lines.append(
                f"- [{row['queue_status']}] {row['component']}: {row['action']} "
                f"(`{row['next_gate_help_command']}`)"
            )
    return "\n".join(lines) + "\n"


def _first_record(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame.empty:
        return None
    return _records(frame.iloc[[0]])[0]


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(frame.to_dict(orient="records"), start=1):
        out = {str(key): _jsonable(value) for key, value in record.items()}
        if "priority" in out:
            out["priority"] = int(index)
        rows.append(out)
    return rows


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, tuple):
        return list(value)
    return value
