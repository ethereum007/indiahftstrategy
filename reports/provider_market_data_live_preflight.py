from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from reports.manifest import write_experiment_manifest


BATCH_SUMMARY_NAME = "provider_market_data_batch_summary.csv"
WRITE_TEST_PREFIX = ".provider_live_preflight_write_test"


@dataclass(frozen=True)
class ProviderMarketDataLivePreflightConfig:
    require_env_present: bool = False
    now_iso: str = ""
    allow_existing_captures: bool = False
    allow_existing_batch: bool = False
    require_before_last_window: bool = True


@dataclass(frozen=True)
class ProviderMarketDataLivePreflightReport:
    windows: pd.DataFrame
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


def write_provider_market_data_live_session_preflight(
    live_session_packet_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataLivePreflightConfig | None = None,
) -> ProviderMarketDataLivePreflightReport:
    report = evaluate_provider_market_data_live_session_preflight(
        live_session_packet_path,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.windows.to_csv(out / "provider_market_data_live_preflight_windows.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_live_preflight_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_live_preflight_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_live_preflight_action_queue.csv", index=False)
    (out / "provider_market_data_live_preflight_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_preflight_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.windows, report.action_queue),
        encoding="utf-8",
    )
    packet_path = Path(live_session_packet_path)
    inputs: dict[str, Any] = {"live_session_packet": packet_path} if packet_path.exists() else {}
    client_packet = Path(str(report.summary.iloc[0]["client_packet_path"]))
    if client_packet.exists() and client_packet.is_file():
        inputs["client_packet"] = client_packet
    existing_captures = [Path(str(path)) for path in report.windows.loc[report.windows["capture_exists"].astype(bool), "capture_path"].tolist()] if not report.windows.empty else []
    if existing_captures:
        inputs["existing_captures"] = existing_captures
    batch_summary_path = Path(str(report.summary.iloc[0]["batch_output_dir"])) / BATCH_SUMMARY_NAME
    if batch_summary_path.exists():
        inputs["existing_batch_summary"] = batch_summary_path
    credential_env_template = _mapping(report.config.get("credential_env_template"))
    if credential_env_template.get("path"):
        credential_env_template_path = Path(str(credential_env_template["path"]))
        if credential_env_template_path.exists():
            inputs["credential_env_template"] = credential_env_template_path
    write_experiment_manifest(
        out,
        run_type="provider_market_data_live_preflight",
        parameters={"config": asdict(config or ProviderMarketDataLivePreflightConfig())},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "timing_status": str(report.summary.iloc[0]["timing_status"]),
            "failed_checks": int(report.summary.iloc[0]["failed_checks"]),
            "blocked_action_count": int(report.summary.iloc[0]["blocked_action_count"]),
            "exchange": str(report.summary.iloc[0]["exchange"]),
            "source_session": _mapping(report.config.get("source_session")),
            "market_session": _mapping(report.config.get("market_session")),
            "credential_env_template": credential_env_template,
            "live_fetch_contract": _mapping(report.config.get("live_fetch_contract")),
            "provider_capture_commands": _provider_capture_commands(report.windows),
        },
    )
    return ProviderMarketDataLivePreflightReport(
        report.windows,
        report.checks,
        report.summary,
        report.action_queue,
        report.config,
        out,
    )


def evaluate_provider_market_data_live_session_preflight(
    live_session_packet_path: str | Path,
    *,
    config: ProviderMarketDataLivePreflightConfig | None = None,
) -> ProviderMarketDataLivePreflightReport:
    config = config or ProviderMarketDataLivePreflightConfig()
    packet_path = Path(live_session_packet_path)
    packet, packet_error = _read_packet(packet_path)
    env_presence = _env_presence(packet)
    windows = _windows(packet, config)
    batch = _batch_status(packet, config)
    clock = _clock_status(windows, config)
    checks = pd.DataFrame(_checks(packet_path, packet, packet_error, env_presence, windows, batch, clock, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    action_queue = _action_queue(checks, ready)
    summary = _summary(packet_path, packet, env_presence, windows, batch, clock, checks, action_queue, config, ready)
    preflight_config = _config(summary.iloc[0], packet_path, packet, env_presence, windows, batch, clock, checks, action_queue, config)
    return ProviderMarketDataLivePreflightReport(windows, checks, summary, action_queue, preflight_config)


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


def _windows(packet: dict[str, Any], config: ProviderMarketDataLivePreflightConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(_list(packet.get("capture_windows")), start=1):
        row = _mapping(item)
        capture_path_text = _text(row.get("capture_path"))
        capture_path = Path(capture_path_text) if capture_path_text else Path("")
        capture_exists = bool(capture_path_text and capture_path.exists() and capture_path.is_file())
        capture_size = capture_path.stat().st_size if capture_exists else 0
        parent_writable, write_error = _write_test(capture_path.parent if capture_path_text else None)
        rows.append(
            {
                "priority": index,
                "label": _text(row.get("label"), f"window_{index}"),
                "pipeline_label": _text(row.get("pipeline_label"), _text(row.get("label"), f"window_{index}")),
                "start_local": _text(row.get("start_local")),
                "end_local": _text(row.get("end_local")),
                "capture_path": capture_path_text,
                "capture_parent": str(capture_path.parent) if capture_path_text else "",
                "capture_command_provider": _text(row.get("capture_command_provider")),
                "capture_command_transport": _text(row.get("capture_command_transport")),
                "capture_command_endpoint": _text(row.get("capture_command_endpoint")),
                "capture_command_kind": _text(row.get("capture_command_kind")),
                "capture_command_exchange": _text(row.get("capture_command_exchange")),
                "capture_command_env_vars": _text(row.get("capture_command_env_vars")),
                "capture_command_base": _text(row.get("capture_command_base")),
                "capture_command_template": _text(row.get("capture_command_template") or row.get("capture_command_hint")),
                "capture_exists": capture_exists,
                "capture_size_bytes": int(capture_size),
                "capture_parent_writable": bool(parent_writable),
                "write_test_error": write_error,
                "collision_blocked": bool(capture_exists and not config.allow_existing_captures),
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
            "capture_parent",
            "capture_command_provider",
            "capture_command_transport",
            "capture_command_endpoint",
            "capture_command_kind",
            "capture_command_exchange",
            "capture_command_env_vars",
            "capture_command_base",
            "capture_command_template",
            "capture_exists",
            "capture_size_bytes",
            "capture_parent_writable",
            "write_test_error",
            "collision_blocked",
        ],
    )


def _batch_status(packet: dict[str, Any], config: ProviderMarketDataLivePreflightConfig) -> dict[str, Any]:
    planned = _mapping(packet.get("post_capture_batch"))
    output_dir = Path(_text(planned.get("output_dir"), "runs/provider_market_data_batches/live_session"))
    writable, write_error = _write_test(output_dir)
    summary_path = output_dir / BATCH_SUMMARY_NAME
    manifest_path = output_dir / "manifest.json"
    summary_exists = summary_path.exists() and summary_path.is_file()
    return {
        "output_dir": str(output_dir),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "summary_exists": bool(summary_exists),
        "manifest_exists": bool(manifest_path.exists() and manifest_path.is_file()),
        "output_dir_writable": bool(writable),
        "write_test_error": write_error,
        "collision_blocked": bool(summary_exists and not config.allow_existing_batch),
    }


def _write_test(directory: Path | None) -> tuple[bool, str]:
    if directory is None:
        return False, "path is missing"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f"{WRITE_TEST_PREFIX}_{os.getpid()}"
        probe.write_text("ok\n", encoding="utf-8")
        try:
            probe.unlink()
        except OSError:
            pass
        return True, ""
    except OSError as exc:
        return False, str(exc)


def _env_presence(packet: dict[str, Any]) -> dict[str, bool]:
    env_vars = _string_list(_mapping(packet.get("authentication")).get("env_vars"))
    return {name: name in os.environ for name in env_vars}


def _clock_status(windows: pd.DataFrame, config: ProviderMarketDataLivePreflightConfig) -> dict[str, Any]:
    parsed: list[tuple[str, datetime, datetime]] = []
    errors: list[str] = []
    for row in windows.to_dict(orient="records") if not windows.empty else []:
        label = _text(row.get("label"), "window")
        start, start_error = _parse_datetime(_text(row.get("start_local")))
        end, end_error = _parse_datetime(_text(row.get("end_local")))
        if start_error or end_error or start is None or end is None:
            errors.append(f"{label}:{start_error or end_error}")
            continue
        if end <= start:
            errors.append(f"{label}:end_not_after_start")
            continue
        parsed.append((label, start, end))
    tz = _first_tz(parsed)
    now, now_error = _now(config.now_iso, tz)
    if now_error:
        return _clock_payload(now, "invalid_clock", "", "", "", errors + [now_error])
    if not parsed:
        return _clock_payload(now, "no_windows", "", "", "", errors)
    converted = [(label, start.astimezone(tz), end.astimezone(tz)) for label, start, end in parsed]
    current = [item for item in converted if item[1] <= now <= item[2]]
    future = [item for item in converted if now < item[1]]
    last_end = max(end for _, _, end in converted)
    first_start = min(start for _, start, _ in converted)
    if current:
        label, _, end = current[0]
        return _clock_payload(now, "inside_window", label, "", "", errors, current_window_end=end.isoformat())
    if now < first_start:
        label, start, _ = sorted(converted, key=lambda item: item[1])[0]
        return _clock_payload(now, "before_first_window", "", label, start.isoformat(), errors)
    if future:
        label, start, _ = sorted(future, key=lambda item: item[1])[0]
        return _clock_payload(now, "between_windows", "", label, start.isoformat(), errors)
    if now > last_end:
        return _clock_payload(now, "after_last_window", "", "", "", errors)
    return _clock_payload(now, "between_windows", "", "", "", errors)


def _parse_datetime(value: str) -> tuple[datetime | None, str]:
    if not value:
        return None, "missing_datetime"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, "invalid_datetime"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    return parsed, ""


def _first_tz(parsed: list[tuple[str, datetime, datetime]]) -> Any:
    for _, start, _ in parsed:
        if start.tzinfo is not None:
            return start.tzinfo
    return ZoneInfo("Asia/Kolkata")


def _now(now_iso: str, tz: Any) -> tuple[datetime | None, str]:
    if _text(now_iso):
        try:
            now = datetime.fromisoformat(_text(now_iso))
        except ValueError:
            return None, "now_iso_invalid"
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        return now.astimezone(tz), ""
    return datetime.now(tz), ""


def _clock_payload(
    now: datetime | None,
    timing_status: str,
    current_window_label: str,
    next_window_label: str,
    next_window_start_local: str,
    errors: list[str],
    *,
    current_window_end: str = "",
) -> dict[str, Any]:
    return {
        "now_local": "" if now is None else now.isoformat(),
        "timing_status": timing_status,
        "current_window_label": current_window_label,
        "current_window_end_local": current_window_end,
        "next_window_label": next_window_label,
        "next_window_start_local": next_window_start_local,
        "time_parse_error_count": int(len(errors)),
        "time_parse_errors": ";".join(errors),
    }


def _checks(
    packet_path: Path,
    packet: dict[str, Any],
    packet_error: str,
    env_presence: dict[str, bool],
    windows: pd.DataFrame,
    batch: dict[str, Any],
    clock: dict[str, Any],
    config: ProviderMarketDataLivePreflightConfig,
) -> list[dict[str, Any]]:
    capture_count = int(len(windows))
    writable_count = int(windows["capture_parent_writable"].astype(bool).sum()) if not windows.empty else 0
    existing_capture_count = int(windows["capture_exists"].astype(bool).sum()) if not windows.empty else 0
    capture_command_count = _nonempty_count(windows, "capture_command_template")
    client_packet_text = _text(packet.get("client_packet_path"))
    client_packet_exists = bool(client_packet_text and Path(client_packet_text).exists() and Path(client_packet_text).is_file())
    authentication = _mapping(packet.get("authentication"))
    credential_env_template = _mapping(authentication.get("env_template"))
    live_fetch_contract = _mapping(packet.get("live_fetch_contract"))
    source_session = _mapping(packet.get("source_session"))
    market_session = _mapping(packet.get("market_session"))
    credential_runtime_ok = all(env_presence.values()) if config.require_env_present else True
    collision_ok = config.allow_existing_captures or existing_capture_count == 0
    batch_collision_ok = config.allow_existing_batch or not bool(batch["summary_exists"])
    clock_ok = (
        not config.require_before_last_window
        or str(clock["timing_status"]) in {"before_first_window", "inside_window", "between_windows"}
    )
    return [
        _check("live_session_packet_path_exists", str(packet_path), "exists", True, packet_path.exists(), "live session packet is required"),
        _check("live_session_packet_json_readable", packet_error or "ok", "is", "ok", not packet_error, packet_error or "live session packet could not be read"),
        _check("live_session_packet_ready", bool(packet.get("ready")), "is", True, bool(packet.get("ready")), "live session plan must be ready before preflight"),
        _check("client_packet_path_exists", client_packet_text, "exists", True, client_packet_exists, "client packet referenced by live session plan is required"),
        _check("credential_values_not_stored", bool(authentication.get("values_stored", True)), "is", False, bool(authentication.get("values_stored", True)) is False, "live session packet must not store credential values"),
        _check("credential_env_vars_present", len(env_presence), ">=", 1, len(env_presence) >= 1, "credential env-var names are required"),
        _check("credential_env_vars_present_in_runtime", sum(env_presence.values()), "==", len(env_presence), credential_runtime_ok, "required credential environment variables are missing from runtime"),
        _check("credential_env_template_carried", _text(credential_env_template.get("path")), "exists", True, bool(credential_env_template.get("exists")) and bool(_text(credential_env_template.get("sha256"))), "live session packet must carry blank credential env-template proof"),
        _check("source_live_fetch_contract_carried", bool(live_fetch_contract.get("available")), "is", True, bool(live_fetch_contract.get("available")) and _text(live_fetch_contract.get("next_gate")) == "provider_fetcher", "live session packet must carry the upstream live fetch-contract handoff"),
        _check("source_exchange_carried", _text(packet.get("exchange")), "is_not", "", bool(_text(packet.get("exchange"))), "live session packet must carry source exchange/segment metadata"),
        _check("source_session_contract_carried", _session_contract_text(source_session), "has", "timezone/open/close", _session_contract_carried(source_session), "live session packet must carry source session metadata"),
        _check("market_session_contract_carried", _session_contract_text(market_session), "has", "timezone/open/close", _session_contract_carried(market_session), "live session packet must carry market session metadata"),
        _check("source_session_matches_market_session", _session_contract_text(source_session), "==", _session_contract_text(market_session), _source_session_matches_market_session(source_session, market_session), "source session metadata must match the market session used for capture windows"),
        _check("source_live_fetch_contract_metadata_matches_packet", _live_contract_metadata_text(live_fetch_contract), "==", "live session source metadata", _live_contract_metadata_matches_packet(packet, live_fetch_contract), "live fetch contract exchange/session metadata must match the live session packet"),
        _check("capture_windows_present", capture_count, ">=", 1, capture_count >= 1, "live session packet must include capture windows"),
        _check("capture_command_templates_present", capture_command_count, "==", capture_count, capture_count >= 1 and capture_command_count == capture_count, "each live capture window must carry a provider capture command template"),
        _check("capture_window_times_parseable", int(clock["time_parse_error_count"]), "==", 0, int(clock["time_parse_error_count"]) == 0, str(clock["time_parse_errors"]) or "capture window times must parse"),
        _check("capture_output_dirs_writable", writable_count, "==", capture_count, capture_count >= 1 and writable_count == capture_count, "capture output directories must be creatable and writable"),
        _check("capture_files_do_not_already_exist", existing_capture_count, "==", 0 if not config.allow_existing_captures else "allowed", collision_ok, "expected capture files already exist; choose fresh capture paths or allow existing captures"),
        _check("batch_output_dir_writable", bool(batch["output_dir_writable"]), "is", True, bool(batch["output_dir_writable"]), str(batch["write_test_error"]) or "batch output directory must be writable"),
        _check("batch_output_not_already_ingested", bool(batch["summary_exists"]), "is", False if not config.allow_existing_batch else "allowed", batch_collision_ok, "provider batch summary already exists; choose a fresh batch output dir or allow existing batch output"),
        _check("clock_before_last_window", str(clock["timing_status"]), "in", "before_or_inside_session", clock_ok, "local clock is after all planned capture windows"),
    ]


def _summary(
    packet_path: Path,
    packet: dict[str, Any],
    env_presence: dict[str, bool],
    windows: pd.DataFrame,
    batch: dict[str, Any],
    clock: dict[str, Any],
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLivePreflightConfig,
    ready: bool,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    capture_command_count = _nonempty_count(windows, "capture_command_template")
    authentication = _mapping(packet.get("authentication"))
    credential_env_template = _mapping(authentication.get("env_template"))
    live_fetch_contract = _mapping(packet.get("live_fetch_contract"))
    source_session = _mapping(packet.get("source_session"))
    market_session = _mapping(packet.get("market_session"))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "live_session_packet_path": str(packet_path),
                "client_packet_path": _text(packet.get("client_packet_path")),
                "provider": _text(packet.get("provider")),
                "transport": _text(packet.get("transport")),
                "market": _text(packet.get("market")),
                "exchange": _text(packet.get("exchange")),
                "kind": _text(packet.get("kind")),
                "source_session_timezone": _text(source_session.get("timezone")),
                "source_session_open_local": _text(source_session.get("open_local")),
                "source_session_close_local": _text(source_session.get("close_local")),
                "market_session_timezone": _text(market_session.get("timezone")),
                "market_session_open_local": _text(market_session.get("open_local")),
                "market_session_close_local": _text(market_session.get("close_local")),
                "source_session_matches_market_session": _source_session_matches_market_session(source_session, market_session),
                "expected_capture_count": int(len(windows)),
                "capture_command_count": capture_command_count,
                "capture_command_missing_count": max(int(len(windows)) - capture_command_count, 0),
                "capture_command_providers": _unique_join(windows, "capture_command_provider"),
                "capture_command_transports": _unique_join(windows, "capture_command_transport"),
                "writable_capture_dir_count": int(windows["capture_parent_writable"].astype(bool).sum()) if not windows.empty else 0,
                "existing_capture_count": int(windows["capture_exists"].astype(bool).sum()) if not windows.empty else 0,
                "batch_output_dir": str(batch["output_dir"]),
                "batch_summary_exists": bool(batch["summary_exists"]),
                "credential_env_var_count": int(len(env_presence)),
                "credential_env_vars": ";".join(env_presence.keys()),
                "credential_env_vars_present": int(sum(env_presence.values())),
                "credential_env_template_path": _text(credential_env_template.get("path")),
                "credential_env_template_exists": bool(credential_env_template.get("exists")),
                "credential_env_template_sha256": _text(credential_env_template.get("sha256")),
                "source_live_fetch_contract_available": bool(live_fetch_contract.get("available")),
                "source_live_fetch_contract_next_gate": _text(live_fetch_contract.get("next_gate")),
                "source_live_fetch_contract_command_template": _text(live_fetch_contract.get("command_template")),
                "require_env_present": bool(config.require_env_present),
                "now_local": str(clock["now_local"]),
                "timing_status": str(clock["timing_status"]),
                "current_window_label": str(clock["current_window_label"]),
                "next_window_label": str(clock["next_window_label"]),
                "next_window_start_local": str(clock["next_window_start_local"]),
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0,
                "blocked_action_count": int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "run_provider_live_capture_windows" if ready else "fix_provider_market_data_live_preflight",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, ready: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    for _, row in failed.iterrows():
        check = str(row["check"])
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": str(row["reason"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
            }
        )
    if not rows and ready:
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "run_provider_live_capture_windows",
                "reason": "live session packet, credential env-var contract, capture paths, and timing preflight passed",
                "next_gate": "provider_fetcher_live_run",
                "next_gate_help_command": "execute provider adapter capture commands for each planned window, then run ingest-provider-market-data-live-session",
            }
        )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _config(
    summary: pd.Series,
    packet_path: Path,
    packet: dict[str, Any],
    env_presence: dict[str, bool],
    windows: pd.DataFrame,
    batch: dict[str, Any],
    clock: dict[str, Any],
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLivePreflightConfig,
) -> dict[str, Any]:
    records = _records(action_queue)
    failed_checks = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist() if not checks.empty else []
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "live_session_packet_path": str(packet_path),
        "session_packet": _safe_packet_view(packet, env_presence),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "credential_env_template": _credential_env_template_contract(summary),
        "live_fetch_contract": _mapping(packet.get("live_fetch_contract")),
        "provider_capture_commands": _provider_capture_commands(windows),
        "clock": clock,
        "environment": {
            "env_vars": [{"name": name, "present": bool(present)} for name, present in env_presence.items()],
            "values_stored": False,
        },
        "windows": _records(windows),
        "batch": batch,
        "checks": _records(checks),
        "failed_check_count": int(len(failed_checks)),
        "failed_checks": failed_checks,
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": records,
        "ready_actions": [row for row in records if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in records if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": records[0] if records else {},
    }


def _safe_packet_view(packet: dict[str, Any], env_presence: dict[str, bool]) -> dict[str, Any]:
    auth = _mapping(packet.get("authentication"))
    return {
        "schema_version": packet.get("schema_version"),
        "ready": bool(packet.get("ready")),
        "client_packet_path": _text(packet.get("client_packet_path")),
        "provider": _text(packet.get("provider")),
        "transport": _text(packet.get("transport")),
        "template_kind": _text(packet.get("template_kind")),
        "market": _text(packet.get("market")),
        "exchange": _text(packet.get("exchange")),
        "source_session": _mapping(packet.get("source_session")),
        "market_session": _mapping(packet.get("market_session")),
        "kind": _text(packet.get("kind")),
        "endpoint": _text(packet.get("endpoint")),
        "authentication": {
            "env_vars": list(env_presence.keys()),
            "env_presence": env_presence,
            "env_template": _mapping(auth.get("env_template")),
            "values_stored": bool(auth.get("values_stored", True)),
            "injection": _text(auth.get("injection")),
        },
        "live_fetch_contract": _mapping(packet.get("live_fetch_contract")),
        "capture_windows": [
            {
                "label": _text(row.get("label")),
                "pipeline_label": _text(row.get("pipeline_label")),
                "start_local": _text(row.get("start_local")),
                "end_local": _text(row.get("end_local")),
                "capture_path": _text(row.get("capture_path")),
                "capture_command_provider": _text(row.get("capture_command_provider")),
                "capture_command_transport": _text(row.get("capture_command_transport")),
                "capture_command_endpoint": _text(row.get("capture_command_endpoint")),
                "capture_command_kind": _text(row.get("capture_command_kind")),
                "capture_command_exchange": _text(row.get("capture_command_exchange")),
                "capture_command_env_vars": _text(row.get("capture_command_env_vars")),
                "capture_command_base": _text(row.get("capture_command_base")),
                "capture_command_template": _text(row.get("capture_command_template") or row.get("capture_command_hint")),
            }
            for row in _list(packet.get("capture_windows"))
            if isinstance(row, dict)
        ],
        "post_capture_batch": _mapping(packet.get("post_capture_batch")),
        "post_capture_batch_command": _text(packet.get("post_capture_batch_command")),
        "live_execution_gate": _mapping(packet.get("live_execution_gate")),
    }


def _next_gate_for_check(check: str) -> str:
    if check.startswith("live_session_packet"):
        return "plan-provider-market-data-live-session"
    if check.startswith("client_packet"):
        return "prepare-provider-market-data-client"
    if check in {
        "credential_env_template_carried",
        "source_live_fetch_contract_carried",
        "source_exchange_carried",
        "source_session_contract_carried",
        "market_session_contract_carried",
        "source_session_matches_market_session",
        "source_live_fetch_contract_metadata_matches_packet",
    }:
        return "plan-provider-market-data-live-session"
    if check.startswith("credential"):
        return "provider_credentials_runtime"
    if check.startswith("batch_output"):
        return "ingest-provider-market-data-live-session"
    if check.startswith("clock"):
        return "plan-provider-market-data-live-session"
    if check.startswith("capture"):
        return "preflight-provider-market-data-live-session"
    return "provider_fetcher_live_run"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {
        "plan-provider-market-data-live-session",
        "prepare-provider-market-data-client",
        "preflight-provider-market-data-live-session",
        "ingest-provider-market-data-live-session",
    }:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_credentials_runtime":
        return "set required provider credential environment variables without writing values to artifacts"
    if next_gate == "provider_fetcher_live_run":
        return "execute provider adapter capture commands for each planned window"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("live_session_packet"):
        return "repair_provider_live_session_packet"
    if check.startswith("client_packet"):
        return "repair_provider_client_packet"
    if check == "credential_env_template_carried":
        return "regenerate_live_session_with_credential_env_template"
    if check == "source_live_fetch_contract_carried":
        return "regenerate_live_session_with_source_live_fetch_contract"
    if check in {
        "source_exchange_carried",
        "source_session_contract_carried",
        "market_session_contract_carried",
        "source_session_matches_market_session",
        "source_live_fetch_contract_metadata_matches_packet",
    }:
        return "regenerate_live_session_with_market_session_contract"
    if check.startswith("credential"):
        return "load_provider_credentials_into_runtime"
    if check == "capture_files_do_not_already_exist":
        return "choose_fresh_provider_capture_paths"
    if check.startswith("capture_output"):
        return "repair_provider_capture_output_dirs"
    if check.startswith("capture_window"):
        return "repair_provider_capture_window_times"
    if check == "batch_output_not_already_ingested":
        return "choose_fresh_provider_batch_output_dir"
    if check.startswith("batch_output"):
        return "repair_provider_batch_output_dir"
    if check.startswith("clock"):
        return "replan_provider_live_session_window"
    return "repair_provider_market_data_live_preflight"


def _runbook_markdown(summary: pd.Series, windows: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Live Preflight Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Timing: {summary['timing_status']} at {summary['now_local']}",
        f"- Credential env template: {summary['credential_env_template_path'] or 'missing'}",
        f"- Expected captures: {summary['expected_capture_count']}",
        f"- Existing captures: {summary['existing_capture_count']}",
        f"- Batch output: {summary['batch_output_dir']}",
        "",
        "## Windows",
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
                _text(row.get("start_local")),
                _text(row.get("end_local")),
                _text(row.get("capture_path")),
                "yes" if _truthy(row.get("capture_parent_writable")) else "no",
                "yes" if _truthy(row.get("capture_exists")) else "no",
            ]
        )
    return _markdown_table(["#", "Label", "Start", "End", "Capture", "Writable", "Exists"], rows)


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


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _provider_capture_commands(windows: Any) -> list[dict[str, str]]:
    rows = _records(windows) if isinstance(windows, pd.DataFrame) else _list(windows)
    commands: list[dict[str, str]] = []
    for row in rows:
        item = _mapping(row)
        command_template = _text(item.get("capture_command_template") or item.get("capture_command_hint"))
        if not command_template:
            continue
        commands.append(
            {
                "label": _text(item.get("label")),
                "provider": _text(item.get("capture_command_provider")),
                "transport": _text(item.get("capture_command_transport")),
                "endpoint": _text(item.get("capture_command_endpoint")),
                "kind": _text(item.get("capture_command_kind")),
                "exchange": _text(item.get("capture_command_exchange")),
                "start_local": _text(item.get("start_local")),
                "end_local": _text(item.get("end_local")),
                "output": _text(item.get("capture_path")),
                "required_env_vars": _text(item.get("capture_command_env_vars")),
                "command_base": _text(item.get("capture_command_base")),
                "command_template": command_template,
            }
        )
    return commands


def _nonempty_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(sum(1 for value in frame[column].tolist() if _text(value)))


def _unique_join(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = sorted({_text(value) for value in frame[column].tolist() if _text(value)})
    return ";".join(values)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(";") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


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


def _credential_env_template_contract(summary: pd.Series) -> dict[str, Any]:
    return {
        "path": str(summary["credential_env_template_path"]),
        "exists": bool(summary["credential_env_template_exists"]),
        "sha256": str(summary["credential_env_template_sha256"]),
    }


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


def _session_contract_carried(session: dict[str, Any]) -> bool:
    return all(_text(session.get(key)) for key in ("timezone", "open_local", "close_local"))


def _source_session_matches_market_session(
    source_session: dict[str, Any],
    market_session: dict[str, Any],
) -> bool:
    if not (_session_contract_carried(source_session) and _session_contract_carried(market_session)):
        return False
    return (
        _text(source_session.get("timezone")) == _text(market_session.get("timezone"))
        and _wall_clock_seconds(source_session.get("open_local")) == _wall_clock_seconds(market_session.get("open_local"))
        and _wall_clock_seconds(source_session.get("close_local")) == _wall_clock_seconds(market_session.get("close_local"))
    )


def _live_contract_metadata_matches_packet(packet: dict[str, Any], live_fetch_contract: dict[str, Any]) -> bool:
    if not bool(live_fetch_contract.get("available")):
        return True
    source_session = _mapping(packet.get("source_session"))
    contract_session = _mapping(live_fetch_contract.get("session"))
    return (
        _text(live_fetch_contract.get("exchange")) == _text(packet.get("exchange"))
        and _text(live_fetch_contract.get("market")) == _text(packet.get("market"))
        and _text(contract_session.get("timezone")) == _text(source_session.get("timezone"))
        and _wall_clock_seconds(contract_session.get("open_local")) == _wall_clock_seconds(source_session.get("open_local"))
        and _wall_clock_seconds(contract_session.get("close_local")) == _wall_clock_seconds(source_session.get("close_local"))
    )


def _session_contract_text(session: dict[str, Any]) -> str:
    return (
        f"{_text(session.get('timezone'))}|"
        f"{_text(session.get('open_local'))}|"
        f"{_text(session.get('close_local'))}"
    )


def _live_contract_metadata_text(live_fetch_contract: dict[str, Any]) -> str:
    session = _mapping(live_fetch_contract.get("session"))
    return (
        f"{_text(live_fetch_contract.get('market'))}|"
        f"{_text(live_fetch_contract.get('exchange'))}|"
        f"{_session_contract_text(session)}"
    )


def _wall_clock_seconds(value: object) -> int | None:
    parts = _text(value).split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour * 3600 + minute * 60 + second
