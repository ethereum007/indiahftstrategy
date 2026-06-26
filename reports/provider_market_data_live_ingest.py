from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.provider_market_data_batch import (
    ProviderMarketDataBatchConfig,
    ProviderMarketDataBatchReport,
    write_provider_market_data_batch_pipeline,
)


@dataclass(frozen=True)
class ProviderMarketDataLiveIngestConfig:
    capture_bundle_path: str = ""
    batch_output_dir: str = ""
    min_capture_rows: int | None = None
    pipeline_min_rows: int | None = None
    tick_size: float | None = None
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None


@dataclass(frozen=True)
class ProviderMarketDataLiveIngestReport:
    windows: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    batch: ProviderMarketDataBatchReport | None
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_live_session_ingest(
    live_session_packet_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataLiveIngestConfig | None = None,
) -> ProviderMarketDataLiveIngestReport:
    report = evaluate_provider_market_data_live_session_ingest(
        live_session_packet_path,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.windows.to_csv(out / "provider_market_data_live_ingest_windows.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_live_ingest_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_live_ingest_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_live_ingest_action_queue.csv", index=False)
    (out / "provider_market_data_live_ingest_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_ingest_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.windows, report.action_queue),
        encoding="utf-8",
    )
    packet_path = Path(live_session_packet_path)
    inputs: dict[str, Any] = {"live_session_packet": packet_path} if packet_path.exists() else {}
    capture_bundle_path = _path_or_none(str(report.summary.iloc[0]["capture_bundle_path"]))
    if capture_bundle_path is not None and capture_bundle_path.exists():
        inputs["capture_bundle"] = capture_bundle_path
    capture_env_template_path = _path_or_none(str(report.summary.iloc[0]["capture_env_template_path"]))
    if capture_env_template_path is not None and capture_env_template_path.exists():
        inputs["capture_env_template"] = capture_env_template_path
    adapter_handoff_path = _path_or_none(str(report.summary.iloc[0]["adapter_handoff_path"]))
    if adapter_handoff_path is not None and adapter_handoff_path.exists():
        inputs["adapter_handoff"] = adapter_handoff_path
    client_packet = Path(str(report.summary.iloc[0]["client_packet_path"]))
    if client_packet.exists():
        inputs["client_packet"] = client_packet
    capture_paths = [Path(str(path)) for path in report.windows["capture_path"].astype(str).tolist()] if not report.windows.empty else []
    existing_captures = [path for path in capture_paths if path.exists()]
    if existing_captures:
        inputs["captures"] = existing_captures
    batch_manifest = Path(str(report.summary.iloc[0]["batch_output_dir"])) / "manifest.json"
    if batch_manifest.exists():
        inputs["batch_manifest"] = batch_manifest
    write_experiment_manifest(
        out,
        run_type="provider_market_data_live_session_ingest",
        parameters={"config": asdict(config or ProviderMarketDataLiveIngestConfig())},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "batch_ready": bool(report.summary.iloc[0]["batch_ready"]),
            "batch_output_dir": str(report.summary.iloc[0]["batch_output_dir"]),
        },
    )
    return ProviderMarketDataLiveIngestReport(
        report.windows,
        report.checks,
        report.summary,
        report.batch,
        report.action_queue,
        report.config,
        out,
    )


def evaluate_provider_market_data_live_session_ingest(
    live_session_packet_path: str | Path,
    *,
    config: ProviderMarketDataLiveIngestConfig | None = None,
) -> ProviderMarketDataLiveIngestReport:
    config = _normalize_config(config or ProviderMarketDataLiveIngestConfig())
    packet_path = Path(live_session_packet_path)
    packet, packet_error = _read_packet(packet_path)
    bundle_path = Path(config.capture_bundle_path) if config.capture_bundle_path else Path("")
    bundle, bundle_error = _read_optional_json(bundle_path, "capture bundle") if config.capture_bundle_path else ({}, "")
    windows = _windows(packet)
    checks = pd.DataFrame(_checks(packet_path, packet, packet_error, bundle_path, bundle, bundle_error, windows, config))
    preflight_ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    batch = None
    effective = _effective_batch_config(packet, config)
    if preflight_ready:
        batch = write_provider_market_data_batch_pipeline(
            Path(str(packet["client_packet_path"])),
            windows["capture_path"].astype(str).tolist(),
            output_dir=effective["batch_output_dir"],
            labels=windows["pipeline_label"].astype(str).tolist(),
            config=ProviderMarketDataBatchConfig(
                min_capture_rows=int(effective["min_capture_rows"]),
                pipeline_min_rows=int(effective["pipeline_min_rows"]),
                tick_size=effective["tick_size"],
                max_p99_gap_ns=effective["max_p99_gap_ns"],
                max_median_spread_ticks=effective["max_median_spread_ticks"],
            ),
        )
    action_queue = _action_queue(checks, batch)
    summary = _summary(packet_path, packet, bundle_path, bundle, windows, checks, batch, action_queue, config, effective)
    ingest_config = _config(summary.iloc[0], windows, checks, action_queue, batch, config, effective)
    return ProviderMarketDataLiveIngestReport(windows, checks, summary, batch, action_queue, ingest_config)


def _read_packet(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "live session packet does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"live session packet is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"live session packet JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "live session packet JSON must be an object"
    return payload, ""


def _read_optional_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"{label} does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"{label} is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"{label} JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{label} JSON must be an object"
    return payload, ""


def _windows(packet: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for index, item in enumerate(_list(packet.get("capture_windows")), start=1):
        row = _mapping(item)
        capture_path = Path(_text(row.get("capture_path")))
        exists = capture_path.exists()
        size_bytes = capture_path.stat().st_size if exists and capture_path.is_file() else 0
        rows.append(
            {
                "priority": index,
                "label": _text(row.get("label"), f"window_{index}"),
                "pipeline_label": _text(row.get("pipeline_label"), _text(row.get("label"), f"window_{index}")),
                "start_local": _text(row.get("start_local")),
                "end_local": _text(row.get("end_local")),
                "capture_path": str(capture_path),
                "capture_exists": bool(exists),
                "capture_size_bytes": int(size_bytes),
                "capture_nonempty": bool(size_bytes > 0),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "label",
            "pipeline_label",
            "start_local",
            "end_local",
            "capture_path",
            "capture_exists",
            "capture_size_bytes",
            "capture_nonempty",
        ],
    )


def _checks(
    packet_path: Path,
    packet: dict[str, Any],
    packet_error: str,
    bundle_path: Path,
    bundle: dict[str, Any],
    bundle_error: str,
    windows: pd.DataFrame,
    config: ProviderMarketDataLiveIngestConfig,
) -> list[dict[str, Any]]:
    capture_exists = bool(windows["capture_exists"].astype(bool).all()) if not windows.empty else False
    capture_nonempty = bool(windows["capture_nonempty"].astype(bool).all()) if not windows.empty else False
    labels_unique = bool(windows["pipeline_label"].astype(str).nunique() == len(windows)) if not windows.empty else False
    bundle_provided = bool(config.capture_bundle_path)
    env_template_path = _env_template_path(bundle_path, bundle) if bundle_provided and not bundle_error else None
    return [
        _check("live_session_packet_path_exists", str(packet_path), "exists", True, packet_path.exists(), "live session packet is required"),
        _check("live_session_packet_json_readable", packet_error or "ok", "is", "ok", not packet_error, packet_error or "live session packet could not be read"),
        _check("capture_bundle_json_readable", bundle_error or "ok", "is", "ok", not bundle_error if bundle_provided else True, bundle_error or "capture bundle could not be read"),
        _check("capture_bundle_matches_session", _text(bundle.get("live_session_packet_path")), "matches", str(packet_path), _bundle_matches_session(bundle_path, bundle, packet_path) if bundle_provided and not bundle_error else True, "capture bundle must reference the same live session packet"),
        _check("capture_env_template_exists", _path_text(env_template_path), "exists", True, bool(env_template_path is not None and env_template_path.exists()) if bundle_provided and not bundle_error else True, "capture bundle credential env template is required for bundle-linked ingest provenance"),
        _check("live_session_packet_ready", bool(packet.get("ready")), "is", True, bool(packet.get("ready")), "live session plan must be ready before ingest"),
        _check("client_packet_path_exists", _text(packet.get("client_packet_path")), "exists", True, Path(_text(packet.get("client_packet_path"))).exists(), "client packet referenced by live session plan is required"),
        _check("capture_windows_present", len(windows), ">=", 1, len(windows) >= 1, "live session packet must include capture windows"),
        _check("capture_labels_unique", len(windows), "unique", len(windows), labels_unique, "capture window labels must be unique"),
        _check("expected_capture_files_exist", int(windows["capture_exists"].astype(bool).sum()) if not windows.empty else 0, "==", len(windows), capture_exists, "all expected capture files must exist"),
        _check("expected_capture_files_nonempty", int(windows["capture_nonempty"].astype(bool).sum()) if not windows.empty else 0, "==", len(windows), capture_nonempty, "all expected capture files must be non-empty"),
        _check("credential_values_not_stored", bool(_mapping(packet.get("authentication")).get("values_stored", True)), "is", False, bool(_mapping(packet.get("authentication")).get("values_stored", True)) is False, "live session packet must not store credential values"),
    ]


def _effective_batch_config(packet: dict[str, Any], config: ProviderMarketDataLiveIngestConfig) -> dict[str, Any]:
    planned = _mapping(packet.get("post_capture_batch"))
    return {
        "batch_output_dir": config.batch_output_dir or _text(planned.get("output_dir"), "runs/provider_market_data_batches/live_session"),
        "min_capture_rows": config.min_capture_rows
        if config.min_capture_rows is not None
        else int(_number(planned.get("min_capture_rows"), fallback=1)),
        "pipeline_min_rows": config.pipeline_min_rows
        if config.pipeline_min_rows is not None
        else int(_number(planned.get("pipeline_min_rows"), fallback=1)),
        "tick_size": config.tick_size if config.tick_size is not None else _optional_number(planned.get("tick_size")),
        "max_p99_gap_ns": config.max_p99_gap_ns
        if config.max_p99_gap_ns is not None
        else _optional_number(planned.get("max_p99_gap_ns")),
        "max_median_spread_ticks": config.max_median_spread_ticks
        if config.max_median_spread_ticks is not None
        else _optional_number(planned.get("max_median_spread_ticks")),
    }


def _summary(
    packet_path: Path,
    packet: dict[str, Any],
    bundle_path: Path,
    bundle: dict[str, Any],
    windows: pd.DataFrame,
    checks: pd.DataFrame,
    batch: ProviderMarketDataBatchReport | None,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveIngestConfig,
    effective: dict[str, Any],
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    batch_ready = bool(batch.ready) if batch is not None else False
    ready = bool(failed_checks == 0 and batch_ready and blocked_actions == 0)
    capture_bundle_path = bundle_path if config.capture_bundle_path else None
    capture_env_template_path = _env_template_path(bundle_path, bundle) if config.capture_bundle_path else None
    adapter_handoff_path = _adapter_handoff_path(bundle_path, bundle) if config.capture_bundle_path else None
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "live_session_packet_path": str(packet_path),
                "capture_bundle_path": _path_text(capture_bundle_path),
                "capture_bundle_provided": bool(config.capture_bundle_path),
                "capture_bundle_ready": bool(bundle.get("ready")),
                "capture_env_template_path": _path_text(capture_env_template_path),
                "capture_env_template_exists": bool(
                    capture_env_template_path is not None and capture_env_template_path.exists()
                ),
                "adapter_handoff_path": _path_text(adapter_handoff_path),
                "adapter_handoff_provided": bool(adapter_handoff_path),
                "adapter_handoff_exists": bool(adapter_handoff_path is not None and adapter_handoff_path.exists()),
                "client_packet_path": _text(packet.get("client_packet_path")),
                "provider": _text(packet.get("provider")),
                "transport": _text(packet.get("transport")),
                "market": _text(packet.get("market")),
                "kind": _text(packet.get("kind")),
                "expected_capture_count": int(len(windows)),
                "present_capture_count": int(windows["capture_exists"].astype(bool).sum()) if not windows.empty else 0,
                "nonempty_capture_count": int(windows["capture_nonempty"].astype(bool).sum()) if not windows.empty else 0,
                "batch_output_dir": str(effective["batch_output_dir"]),
                "batch_ready": batch_ready,
                "failed_checks": failed_checks,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0,
                "blocked_action_count": blocked_actions,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "feed_walkforward_research" if ready else "fix_provider_market_data_live_ingest",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, batch: ProviderMarketDataBatchReport | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    for _, row in failed.iterrows():
        check = str(row["check"])
        rows.append(_action("blocked", _repair_action(check), str(row["reason"]), _next_gate_for_check(check), _next_gate_help_command(_next_gate_for_check(check))))
    if not rows and batch is not None and batch.action_queue is not None and not batch.action_queue.empty:
        blocked = batch.action_queue.loc[batch.action_queue["queue_status"].astype(str) == "blocked"]
        for _, row in blocked.iterrows():
            next_gate = _provider_next_gate(str(row.get("next_gate", "")))
            rows.append(
                _action(
                    "blocked",
                    str(row.get("recommendation", "fix_provider_market_data_batch")),
                    str(row.get("reason", "")),
                    next_gate,
                    _next_gate_help_command(next_gate),
                )
            )
    if not rows and batch is not None and batch.ready:
        rows.append(
            _action(
                "ready",
                "feed_provider_market_data_batch_to_research",
                "expected live captures were ingested and batch readiness passed",
                "review-data-readiness",
                "batch output contains comparison and nested data-readiness evidence",
            )
        )
    for priority, row in enumerate(rows, start=1):
        row["priority"] = priority
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _action(status: str, action: str, reason: str, next_gate: str, help_command: str) -> dict[str, Any]:
    return {
        "priority": 0,
        "queue_status": status,
        "action": action,
        "reason": reason,
        "next_gate": next_gate,
        "next_gate_help_command": help_command,
    }


def _config(
    summary: pd.Series,
    windows: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    batch: ProviderMarketDataBatchReport | None,
    config: ProviderMarketDataLiveIngestConfig,
    effective: dict[str, Any],
) -> dict[str, Any]:
    records = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "effective_batch_config": effective,
        "capture_bundle": {
            "path": str(summary["capture_bundle_path"]),
            "provided": bool(summary["capture_bundle_provided"]),
            "ready": bool(summary["capture_bundle_ready"]),
            "env_template_path": str(summary["capture_env_template_path"]),
            "env_template_exists": bool(summary["capture_env_template_exists"]),
            "adapter_handoff_path": str(summary["adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
        },
        "windows": _records(windows),
        "checks": _records(checks),
        "batch": {} if batch is None else _batch_config(batch),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": records,
        "ready_actions": [row for row in records if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in records if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": records[0] if records else {},
    }


def _batch_config(batch: ProviderMarketDataBatchReport) -> dict[str, Any]:
    row = batch.summary.iloc[0] if not batch.summary.empty else pd.Series(dtype=object)
    return {
        "ready": bool(batch.ready),
        "output_dir": "" if batch.output_dir is None else str(batch.output_dir),
        "summary": {str(key): _jsonable(value) for key, value in row.to_dict().items()},
        "datasets": _records(batch.datasets),
    }


def _runbook_markdown(summary: pd.Series, windows: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Live Ingest Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Batch ready: {'yes' if bool(summary['batch_ready']) else 'no'}",
        f"- Capture bundle: {summary['capture_bundle_path']}",
        f"- Credential env template: {summary['capture_env_template_path']}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Expected captures: {summary['expected_capture_count']}",
        f"- Present captures: {summary['present_capture_count']}",
        f"- Batch output: {summary['batch_output_dir']}",
        "",
        "## Captures",
        "",
        _windows_table(windows),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _windows_table(windows: pd.DataFrame) -> str:
    if windows.empty:
        return "_None_"
    rows = []
    for row in windows.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("label")),
                _text(row.get("capture_path")),
                "yes" if _truthy(row.get("capture_exists")) else "no",
                str(int(_number(row.get("capture_size_bytes"), fallback=0))),
            ]
        )
    return _markdown_table(["#", "Label", "Capture", "Exists", "Bytes"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = []
    for row in action_queue.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("queue_status")),
                _text(row.get("action")),
                _text(row.get("next_gate")),
                _text(row.get("reason")),
            ]
        )
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


def _next_gate_for_check(check: str) -> str:
    if check.startswith("live_session_packet"):
        return "plan-provider-market-data-live-session"
    if check.startswith("client_packet"):
        return "prepare-provider-market-data-client"
    if check.startswith("capture_bundle") or check.startswith("capture_env_template"):
        return "bundle-provider-market-data-live-capture"
    if check.startswith("expected_capture"):
        return "provider_fetcher_live_run"
    return "pipeline-provider-market-data-batch"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {
        "plan-provider-market-data-live-session",
        "prepare-provider-market-data-client",
        "bundle-provider-market-data-live-capture",
        "pipeline-provider-market-data-batch",
    }:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_fetcher_live_run":
        return "execute the provider adapter for the missing live capture window"
    if next_gate == "review-data-readiness":
        return "batch output contains comparison and nested data-readiness evidence"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("expected_capture"):
        return "produce_expected_provider_capture_file"
    if check.startswith("live_session_packet"):
        return "repair_provider_live_session_packet"
    if check.startswith("client_packet"):
        return "repair_provider_client_packet"
    if check.startswith("capture_bundle") or check.startswith("capture_env_template"):
        return "repair_provider_live_capture_bundle"
    return "repair_provider_live_ingest"


def _provider_next_gate(next_gate: str) -> str:
    if next_gate == "pipeline-provider-market-data-batch":
        return next_gate
    if next_gate == "pipeline-vendor-market-data-batch":
        return "pipeline-provider-market-data-batch"
    return next_gate


def _normalize_config(config: ProviderMarketDataLiveIngestConfig) -> ProviderMarketDataLiveIngestConfig:
    return ProviderMarketDataLiveIngestConfig(
        capture_bundle_path=str(config.capture_bundle_path or "").strip(),
        batch_output_dir=str(config.batch_output_dir or "").strip(),
        min_capture_rows=config.min_capture_rows,
        pipeline_min_rows=config.pipeline_min_rows,
        tick_size=config.tick_size,
        max_p99_gap_ns=config.max_p99_gap_ns,
        max_median_spread_ticks=config.max_median_spread_ticks,
    )


def _bundle_matches_session(bundle_path: Path, bundle: dict[str, Any], packet_path: Path) -> bool:
    raw = _text(bundle.get("live_session_packet_path"))
    if not raw:
        return False
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = bundle_path.parent / candidate
    try:
        return candidate.resolve() == packet_path.resolve()
    except OSError:
        return str(candidate) == str(packet_path)


def _env_template_path(bundle_path: Path, bundle: dict[str, Any]) -> Path | None:
    template = _text(_mapping(bundle.get("authentication")).get("env_template"))
    if not template:
        return None
    path = Path(template)
    if path.is_absolute():
        return path
    return bundle_path.parent / path


def _adapter_handoff_path(bundle_path: Path, bundle: dict[str, Any]) -> Path | None:
    handoff = _text(bundle.get("adapter_handoff")) or "provider_market_data_adapter_handoff.json"
    path = Path(handoff)
    if path.is_absolute():
        return path
    return bundle_path.parent / path


def _path_or_none(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _optional_number(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if value in {"", None}:
        return None
    return _number(value, fallback=0.0)


def _number(value: object, *, fallback: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return float(fallback)
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _text(value: object, fallback: str = "") -> str:
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
    return _text(value).lower() in {"1", "true", "yes", "ready"}


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
