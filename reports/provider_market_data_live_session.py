from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from markets.profiles import get_market_profile
from reports.manifest import write_experiment_manifest


DEFAULT_WINDOWS = ("open=09:15-10:00", "close=14:45-15:30")
WINDOW_RE = re.compile(r"^([A-Za-z0-9_.-]+)=([0-2][0-9]:[0-5][0-9])(?:-)([0-2][0-9]:[0-5][0-9])$")


@dataclass(frozen=True)
class ProviderMarketDataLiveSessionConfig:
    trade_date: str
    windows: tuple[str, ...] = field(default_factory=lambda: DEFAULT_WINDOWS)
    capture_dir: str = "captures/provider_market_data"
    batch_output_dir: str = ""
    min_capture_rows: int = 1
    pipeline_min_rows: int = 1
    tick_size: float | None = None
    max_p99_gap_ns: float | None = None
    max_median_spread_ticks: float | None = None
    require_env_present: bool = False
    allow_weekend: bool = False


@dataclass(frozen=True)
class ProviderMarketDataLiveSessionReport:
    windows: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    packet: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_live_session_plan(
    client_packet_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataLiveSessionConfig,
) -> ProviderMarketDataLiveSessionReport:
    report = evaluate_provider_market_data_live_session_plan(client_packet_path, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.windows.to_csv(out / "provider_market_data_live_session_windows.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_live_session_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_live_session_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_live_session_action_queue.csv", index=False)
    (out / "provider_market_data_live_session_packet.json").write_text(
        json.dumps(report.packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_session_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_session_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.windows, report.action_queue),
        encoding="utf-8",
    )
    packet_path = Path(client_packet_path)
    inputs = {"client_packet": packet_path} if packet_path.exists() else {}
    credential_env_template = _credential_env_template_from_packet(report.packet)
    if credential_env_template["path"]:
        credential_env_template_path = Path(credential_env_template["path"])
        if credential_env_template_path.exists():
            inputs["credential_env_template"] = credential_env_template_path
    write_experiment_manifest(
        out,
        run_type="provider_market_data_live_session_plan",
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "provider": str(report.summary.iloc[0]["provider"]),
            "credential_env_template": credential_env_template,
            "live_fetch_contract": report.packet["live_fetch_contract"],
            "provider_capture_commands": _provider_capture_commands(report.packet.get("capture_windows")),
            "post_capture_batch_command": str(report.summary.iloc[0]["post_capture_batch_command"]),
        },
    )
    return ProviderMarketDataLiveSessionReport(
        report.windows,
        report.checks,
        report.summary,
        report.action_queue,
        report.packet,
        report.config,
        out,
    )


def evaluate_provider_market_data_live_session_plan(
    client_packet_path: str | Path,
    *,
    config: ProviderMarketDataLiveSessionConfig,
) -> ProviderMarketDataLiveSessionReport:
    _validate_config(config)
    packet_path = Path(client_packet_path)
    packet, packet_error = _read_packet(packet_path)
    market = _text(packet.get("market"), "india_nse_index_derivatives")
    profile = get_market_profile(market)
    trade_day = _parse_trade_date(config.trade_date)
    windows, window_errors = _windows(config, packet, profile, trade_day)
    env_vars = _string_list(_mapping(packet.get("authentication")).get("env_vars"))
    env_presence = {name: name in os.environ for name in env_vars}
    checks = pd.DataFrame(_checks(packet_path, packet, packet_error, profile, trade_day, windows, window_errors, env_presence, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    summary = _summary(packet_path, packet, profile, trade_day, windows, checks, env_presence, config, ready)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, action_queue)
    session_packet = _session_packet(packet_path, packet, profile, windows, summary.iloc[0], env_presence, config)
    live_config = _config(summary.iloc[0], checks, action_queue, session_packet, config)
    return ProviderMarketDataLiveSessionReport(windows, checks, summary, action_queue, session_packet, live_config)


def _read_packet(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "provider client packet does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"provider client packet is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"provider client packet JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "provider client packet JSON must be an object"
    return payload, ""


def _windows(
    config: ProviderMarketDataLiveSessionConfig,
    packet: dict[str, Any],
    profile,
    trade_day: date,
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    capture_dir = Path(config.capture_dir)
    provider = _safe_label(_text(packet.get("provider"), "provider"))
    for index, spec in enumerate(config.windows, start=1):
        parsed = _parse_window_spec(spec)
        if parsed is None:
            errors.append(f"invalid_window_spec:{spec}")
            continue
        label, start_time, end_time = parsed
        start_local = datetime.combine(trade_day, start_time, tzinfo=ZoneInfo(profile.session.timezone))
        end_local = datetime.combine(trade_day, end_time, tzinfo=ZoneInfo(profile.session.timezone))
        if end_local <= start_local:
            errors.append(f"nonpositive_window:{label}")
        start_seconds = start_time.hour * 3600 + start_time.minute * 60
        end_seconds = end_time.hour * 3600 + end_time.minute * 60
        within_session = start_seconds >= profile.session.open_seconds and end_seconds <= profile.session.close_seconds
        if not within_session:
            errors.append(f"outside_market_session:{label}")
        capture_path = capture_dir / f"{provider}_{_safe_label(label)}_{trade_day.strftime('%Y_%m_%d')}.csv"
        rows.append(
            {
                "priority": index,
                "label": label,
                "trade_date": trade_day.isoformat(),
                "timezone": profile.session.timezone,
                "start_local": start_local.isoformat(),
                "end_local": end_local.isoformat(),
                "duration_seconds": int((end_local - start_local).total_seconds()),
                "within_market_session": bool(within_session),
                "capture_path": str(capture_path),
                "pipeline_label": label,
                **_capture_command_fields(packet, capture_path, start_local, end_local),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "label",
            "trade_date",
            "timezone",
            "start_local",
            "end_local",
            "duration_seconds",
            "within_market_session",
            "capture_path",
            "pipeline_label",
            "capture_command_provider",
            "capture_command_transport",
            "capture_command_endpoint",
            "capture_command_kind",
            "capture_command_exchange",
            "capture_command_env_vars",
            "capture_command_base",
            "capture_command_template",
            "capture_command_hint",
        ],
    ), errors


def _checks(
    packet_path: Path,
    packet: dict[str, Any],
    packet_error: str,
    profile,
    trade_day: date,
    windows: pd.DataFrame,
    window_errors: list[str],
    env_presence: dict[str, bool],
    config: ProviderMarketDataLiveSessionConfig,
) -> list[dict[str, Any]]:
    transport = _text(packet.get("transport"))
    endpoint = _text(packet.get("endpoint"))
    authentication = _mapping(packet.get("authentication"))
    credential_env_template = _mapping(authentication.get("env_template"))
    live_fetch_contract = _mapping(packet.get("live_fetch_contract"))
    source_session = _mapping(packet.get("session"))
    return [
        _check("client_packet_path_exists", str(packet_path), "exists", True, packet_path.exists(), "provider client packet is required"),
        _check("client_packet_json_readable", packet_error or "ok", "is", "ok", not packet_error, packet_error or "provider client packet JSON could not be read"),
        _check("client_packet_ready", bool(packet.get("ready")), "is", True, bool(packet.get("ready")), "provider client packet must be ready"),
        _check("client_packet_dry_run", _text(packet.get("execution_mode")), "is", "dry_run", _text(packet.get("execution_mode")) == "dry_run", "planner expects dry-run packet as the approved contract"),
        _check("transport_live_supported", transport, "in", "rest/websocket", transport in {"rest", "websocket"}, "live planner supports REST or websocket provider captures"),
        _check("endpoint_present", endpoint, "is_not", "", bool(endpoint), "provider endpoint is required"),
        _check("credential_values_not_stored", bool(authentication.get("values_stored", True)), "is", False, bool(authentication.get("values_stored", True)) is False, "provider packet must not contain credential values"),
        _check("credential_env_vars_present", len(env_presence), ">=", 1, len(env_presence) >= 1, "credential env-var names are required"),
        _check("credential_env_vars_present_in_runtime", sum(env_presence.values()), "==", len(env_presence), all(env_presence.values()) if config.require_env_present else True, "required credential environment variables are missing from runtime"),
        _check("credential_env_template_carried", _text(credential_env_template.get("path")), "exists", True, bool(credential_env_template.get("exists")) and bool(_text(credential_env_template.get("sha256"))), "provider client packet must carry blank credential env-template proof"),
        _check("source_live_fetch_contract_carried", bool(live_fetch_contract.get("available")), "is", True, bool(live_fetch_contract.get("available")) and _text(live_fetch_contract.get("next_gate")) == "provider_fetcher", "provider client packet must carry the upstream live fetch-contract handoff"),
        _check("source_exchange_carried", _text(packet.get("exchange")), "is_not", "", bool(_text(packet.get("exchange"))), "provider client packet must carry source exchange/segment metadata"),
        _check("source_session_contract_carried", _session_contract_text(source_session), "has", "timezone/open/close", _source_session_carried(source_session), "provider client packet must carry source session timezone and open/close metadata"),
        _check("source_session_matches_market_profile", _session_contract_text(source_session), "==", _profile_session_text(profile), _source_session_matches_profile(source_session, profile), "source session metadata must match the selected market profile"),
        _check("source_live_fetch_contract_metadata_matches_packet", _live_contract_metadata_text(live_fetch_contract), "==", "client packet source metadata", _live_contract_metadata_matches_packet(packet, live_fetch_contract), "live fetch contract exchange/session metadata must match the provider client packet"),
        _check("trade_date_weekday", trade_day.isoformat(), "weekday", "Mon-Fri", trade_day.weekday() < 5 or config.allow_weekend, "trade date is a weekend; pass allow_weekend only for test captures"),
        _check("market_session_known", profile.name, "known", True, bool(profile.name), "market profile must be known"),
        _check("windows_present", len(windows), ">=", 1, len(windows) >= 1, "at least one capture window is required"),
        _check("windows_within_session", ";".join(window_errors), "is", "", not window_errors, "capture windows must be valid and inside the market session"),
    ]


def _summary(
    packet_path: Path,
    packet: dict[str, Any],
    profile,
    trade_day: date,
    windows: pd.DataFrame,
    checks: pd.DataFrame,
    env_presence: dict[str, bool],
    config: ProviderMarketDataLiveSessionConfig,
    ready: bool,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    batch_command = _batch_command(packet_path, windows, packet, config)
    authentication = _mapping(packet.get("authentication"))
    credential_env_template = _mapping(authentication.get("env_template"))
    live_fetch_contract = _mapping(packet.get("live_fetch_contract"))
    source_session = _mapping(packet.get("session"))
    capture_command_count = _nonempty_count(windows, "capture_command_template")
    capture_command_missing_count = max(int(len(windows)) - capture_command_count, 0)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "client_packet_path": str(packet_path),
                "provider": _text(packet.get("provider")),
                "transport": _text(packet.get("transport")),
                "template_kind": _text(packet.get("template_kind")),
                "market": profile.name,
                "exchange": _text(packet.get("exchange")),
                "kind": _text(packet.get("kind")),
                "trade_date": trade_day.isoformat(),
                "timezone": profile.session.timezone,
                "session_open_local": _seconds_to_hhmm(profile.session.open_seconds),
                "session_close_local": _seconds_to_hhmm(profile.session.close_seconds),
                "source_session_timezone": _text(source_session.get("timezone")),
                "source_session_open_local": _text(source_session.get("open_local")),
                "source_session_close_local": _text(source_session.get("close_local")),
                "source_session_matches_market_profile": _source_session_matches_profile(source_session, profile),
                "window_count": int(len(windows)),
                "total_capture_seconds": int(pd.to_numeric(windows["duration_seconds"], errors="coerce").sum()) if not windows.empty else 0,
                "credential_env_var_count": int(len(env_presence)),
                "credential_env_vars": ";".join(env_presence.keys()),
                "credential_env_vars_present": int(sum(env_presence.values())),
                "credential_env_template_path": _text(credential_env_template.get("path")),
                "credential_env_template_exists": bool(credential_env_template.get("exists")),
                "credential_env_template_sha256": _text(credential_env_template.get("sha256")),
                "source_live_fetch_contract_available": bool(live_fetch_contract.get("available")),
                "source_live_fetch_contract_next_gate": _text(live_fetch_contract.get("next_gate")),
                "source_live_fetch_contract_command_template": _text(
                    live_fetch_contract.get("command_template")
                ),
                "capture_command_count": capture_command_count,
                "capture_command_missing_count": capture_command_missing_count,
                "capture_command_providers": _unique_join(windows, "capture_command_provider"),
                "capture_command_transports": _unique_join(windows, "capture_command_transport"),
                "require_env_present": bool(config.require_env_present),
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "post_capture_batch_command": batch_command,
                "recommendation": "provider_market_data_live_session_ready" if ready else "fix_provider_market_data_live_session_plan",
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    ready_actions = int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0
    blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    out["ready_action_count"] = ready_actions
    out["blocked_action_count"] = blocked_actions
    out["next_gate"] = "" if next_action is None else str(next_action["next_gate"])
    out["next_gate_help_command"] = "" if next_action is None else str(next_action["next_gate_help_command"])
    out["primary_action_status"] = "" if next_action is None else str(next_action["queue_status"])
    return out


def _action_queue(summary: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    for _, row in failed.iterrows():
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(str(row["check"])),
                "reason": str(row["reason"]),
                "next_gate": _next_gate_for_check(str(row["check"])),
                "next_gate_help_command": _next_gate_help_command(_next_gate_for_check(str(row["check"]))),
            }
        )
    if not rows and bool(summary["ready"]):
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "run_provider_live_capture_windows",
                "reason": "live capture windows and credential-safe packet are ready",
                "next_gate": "provider_fetcher_live_run",
                "next_gate_help_command": "execute provider adapter for each window, then run post_capture_batch_command",
            }
        )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _session_packet(
    packet_path: Path,
    packet: dict[str, Any],
    profile,
    windows: pd.DataFrame,
    summary: pd.Series,
    env_presence: dict[str, bool],
    config: ProviderMarketDataLiveSessionConfig,
) -> dict[str, Any]:
    auth = _mapping(packet.get("authentication"))
    batch_output_dir = config.batch_output_dir.strip() or _default_batch_output(packet, config.trade_date)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "client_packet_path": str(packet_path),
        "provider": _text(packet.get("provider")),
        "transport": _text(packet.get("transport")),
        "template_kind": _text(packet.get("template_kind")),
        "market": profile.name,
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": {
            "timezone": str(summary["timezone"]),
            "open_local": str(summary["session_open_local"]),
            "close_local": str(summary["session_close_local"]),
        },
        "kind": _text(packet.get("kind")),
        "endpoint": _text(packet.get("endpoint")),
        "request": _mapping(packet.get("request")),
        "authentication": {
            "env_vars": list(env_presence.keys()),
            "env_presence": env_presence,
            "env_template": _mapping(auth.get("env_template")),
            "values_stored": False,
            "injection": _text(auth.get("injection")),
        },
        "live_fetch_contract": _mapping(packet.get("live_fetch_contract")),
        "runtime": _mapping(packet.get("runtime")),
        "output": _mapping(packet.get("output")),
        "capture_windows": _records(windows),
        "post_capture_batch": {
            "output_dir": batch_output_dir,
            "min_capture_rows": int(config.min_capture_rows),
            "pipeline_min_rows": int(config.pipeline_min_rows),
            "tick_size": config.tick_size,
            "max_p99_gap_ns": config.max_p99_gap_ns,
            "max_median_spread_ticks": config.max_median_spread_ticks,
        },
        "post_capture_batch_command": str(summary["post_capture_batch_command"]),
        "live_execution_gate": {
            "requires_provider_api_contract": True,
            "requires_credentials_in_runtime": bool(config.require_env_present),
            "requires_no_secret_persistence": True,
            "requires_capture_review_after_run": True,
        },
    }


def _config(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    packet: dict[str, Any],
    config: ProviderMarketDataLiveSessionConfig,
) -> dict[str, Any]:
    failed_checks = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist() if not checks.empty else []
    next_action = _first_record(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "session": {
            "trade_date": str(summary["trade_date"]),
            "timezone": str(summary["timezone"]),
            "session_open_local": str(summary["session_open_local"]),
            "session_close_local": str(summary["session_close_local"]),
            "window_count": int(summary["window_count"]),
        },
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "credential_env_template": _credential_env_template_contract(summary),
        "live_fetch_contract": _mapping(packet.get("live_fetch_contract")),
        "provider_capture_commands": _provider_capture_commands(packet.get("capture_windows")),
        "packet": packet,
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
        "ready_action_count": int(summary["ready_action_count"]),
        "blocked_action_count": int(summary["blocked_action_count"]),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": _records(action_queue),
        "ready_actions": _records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _records(_actions_with_status(action_queue, "blocked")),
        "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
        "primary_action": {} if next_action is None else next_action,
        "post_capture_batch_command": str(summary["post_capture_batch_command"]),
    }


def _batch_command(
    packet_path: Path,
    windows: pd.DataFrame,
    packet: dict[str, Any],
    config: ProviderMarketDataLiveSessionConfig,
) -> str:
    batch_out = config.batch_output_dir.strip() or _default_batch_output(packet, config.trade_date)
    parts = [
        "python",
        "-m",
        "hft_cli",
        "pipeline-provider-market-data-batch",
        "--client-packet",
        str(packet_path),
        "--capture",
    ]
    captures = windows["capture_path"].astype(str).tolist() if not windows.empty else []
    parts.extend(captures)
    for label in windows["pipeline_label"].astype(str).tolist() if not windows.empty else []:
        parts.extend(["--label", label])
    parts.extend(
        [
            "--out",
            batch_out,
            "--min-capture-rows",
            str(config.min_capture_rows),
            "--pipeline-min-rows",
            str(config.pipeline_min_rows),
        ]
    )
    if config.tick_size is not None:
        parts.extend(["--tick-size", str(config.tick_size)])
    if config.max_p99_gap_ns is not None:
        parts.extend(["--max-p99-gap-ns", str(config.max_p99_gap_ns)])
    if config.max_median_spread_ticks is not None:
        parts.extend(["--max-median-spread-ticks", str(config.max_median_spread_ticks)])
    parts.extend(
        [
            "--min-datasets",
            str(len(captures)),
            "--min-ready-datasets",
            str(len(captures)),
            "--min-unique-source-files",
            str(len(captures)),
            "--fail-on-blocked-actions",
            "--fail-on-breach",
        ]
    )
    return " ".join(_shell_quote(part) for part in parts)


def _capture_command_fields(
    packet: dict[str, Any],
    capture_path: Path,
    start_local: datetime,
    end_local: datetime,
) -> dict[str, str]:
    provider = _text(packet.get("provider"), "provider")
    transport = _text(packet.get("transport"))
    endpoint = _text(packet.get("endpoint"))
    kind = _text(packet.get("kind"))
    exchange = _text(packet.get("exchange"))
    env_vars = _string_list(_mapping(packet.get("authentication")).get("env_vars"))
    base = "provider-adapter capture"
    args = [
        "--provider",
        provider,
        "--transport",
        transport,
        "--endpoint",
        endpoint,
        "--kind",
        kind,
        "--exchange",
        exchange,
        "--start",
        start_local.isoformat(),
        "--end",
        end_local.isoformat(),
        "--output",
        str(capture_path),
    ]
    for env_var in env_vars:
        args.extend(["--require-env", env_var])
    command_template = " ".join([base, *(_shell_quote(part) for part in args)])
    return {
        "capture_command_provider": provider,
        "capture_command_transport": transport,
        "capture_command_endpoint": endpoint,
        "capture_command_kind": kind,
        "capture_command_exchange": exchange,
        "capture_command_env_vars": ";".join(env_vars),
        "capture_command_base": base,
        "capture_command_template": command_template,
        "capture_command_hint": command_template,
    }


def _provider_capture_commands(windows: Any) -> list[dict[str, str]]:
    rows = _records(windows) if isinstance(windows, pd.DataFrame) else _list(windows)
    commands: list[dict[str, str]] = []
    for row in rows:
        item = _mapping(row)
        command_template = _text(item.get("capture_command_template"))
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


def _default_batch_output(packet: dict[str, Any], trade_date: str) -> str:
    provider = _safe_label(_text(packet.get("provider"), "provider"))
    market = _safe_label(_text(packet.get("market"), "market"))
    day = trade_date.replace("-", "_")
    return f"runs/provider_market_data_batches/{provider}_{market}_{day}"


def _parse_window_spec(spec: str) -> tuple[str, time, time] | None:
    match = WINDOW_RE.match(str(spec).strip())
    if not match:
        return None
    label, start_raw, end_raw = match.groups()
    return label, _parse_hhmm(start_raw), _parse_hhmm(end_raw)


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    if hour > 23:
        raise ValueError(f"invalid hour in window time {value!r}")
    return time(hour=hour, minute=minute)


def _parse_trade_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError("trade_date must use YYYY-MM-DD") from exc


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
    if check.startswith("client_packet"):
        return "prepare-provider-market-data-client"
    if check in {
        "credential_env_template_carried",
        "source_live_fetch_contract_carried",
        "source_exchange_carried",
        "source_session_contract_carried",
        "source_session_matches_market_profile",
        "source_live_fetch_contract_metadata_matches_packet",
    }:
        return "prepare-provider-market-data-client"
    if check.startswith("credential"):
        return "provider_credentials_runtime"
    if check.startswith("window") or check.startswith("trade_date"):
        return "plan-provider-market-data-live-session"
    return "provider_fetcher_live_run"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate == "plan-provider-market-data-live-session":
        return "python -m hft_cli plan-provider-market-data-live-session --help"
    if next_gate == "prepare-provider-market-data-client":
        return "python -m hft_cli prepare-provider-market-data-client --help"
    if next_gate == "provider_credentials_runtime":
        return "set required provider credential environment variables without writing values to artifacts"
    if next_gate == "provider_fetcher_live_run":
        return "execute provider adapter for each window, then run post_capture_batch_command"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("client_packet"):
        return "repair_provider_client_packet"
    if check == "credential_env_template_carried":
        return "regenerate_provider_client_with_credential_env_template"
    if check == "source_live_fetch_contract_carried":
        return "regenerate_provider_client_with_source_live_fetch_contract"
    if check in {
        "source_exchange_carried",
        "source_session_contract_carried",
        "source_session_matches_market_profile",
        "source_live_fetch_contract_metadata_matches_packet",
    }:
        return "regenerate_provider_client_with_market_session_contract"
    if check.startswith("credential"):
        return "load_provider_credentials_into_runtime"
    if check.startswith("window") or check.startswith("trade_date"):
        return "repair_live_capture_window_plan"
    return "repair_provider_live_session_plan"


def _runbook_markdown(summary: pd.Series, windows: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Live Session Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Trade date: {summary['trade_date']}",
        f"- Session: {summary['session_open_local']} - {summary['session_close_local']} {summary['timezone']}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Credential env template: {summary['credential_env_template_path'] or 'missing'}",
        f"- Post-capture batch command: `{summary['post_capture_batch_command']}`",
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
                _value_text(row.get("label")),
                _value_text(row.get("start_local")),
                _value_text(row.get("end_local")),
                _value_text(row.get("capture_path")),
            ]
        )
    return _markdown_table(["#", "Label", "Start", "End", "Capture"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = []
    for row in action_queue.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _value_text(row.get("queue_status")),
                _value_text(row.get("action")),
                _value_text(row.get("next_gate")),
                _value_text(row.get("reason")),
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


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _nonempty_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(sum(1 for value in frame[column].tolist() if _text(value)))


def _unique_join(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = sorted({_text(value) for value in frame[column].tolist() if _text(value)})
    return ";".join(values)


def _credential_env_template_contract(summary: pd.Series) -> dict[str, Any]:
    return {
        "path": str(summary["credential_env_template_path"]),
        "exists": bool(summary["credential_env_template_exists"]),
        "sha256": str(summary["credential_env_template_sha256"]),
    }


def _credential_env_template_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    auth = _mapping(packet.get("authentication"))
    env_template = _mapping(auth.get("env_template"))
    return {
        "path": _text(env_template.get("path")),
        "exists": bool(env_template.get("exists")),
        "sha256": _text(env_template.get("sha256")),
    }


def _source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_session_timezone"]),
        "open_local": str(summary["source_session_open_local"]),
        "close_local": str(summary["source_session_close_local"]),
    }


def _source_session_carried(session: dict[str, Any]) -> bool:
    return all(_text(session.get(key)) for key in ("timezone", "open_local", "close_local"))


def _source_session_matches_profile(session: dict[str, Any], profile) -> bool:
    if not _source_session_carried(session):
        return False
    return (
        _text(session.get("timezone")) == profile.session.timezone
        and _wall_clock_seconds(session.get("open_local")) == profile.session.open_seconds
        and _wall_clock_seconds(session.get("close_local")) == profile.session.close_seconds
    )


def _live_contract_metadata_matches_packet(packet: dict[str, Any], live_fetch_contract: dict[str, Any]) -> bool:
    if not bool(live_fetch_contract.get("available")):
        return True
    packet_session = _mapping(packet.get("session"))
    contract_session = _mapping(live_fetch_contract.get("session"))
    return (
        _text(live_fetch_contract.get("exchange")) == _text(packet.get("exchange"))
        and _text(live_fetch_contract.get("market")) == _text(packet.get("market"))
        and _text(contract_session.get("timezone")) == _text(packet_session.get("timezone"))
        and _wall_clock_seconds(contract_session.get("open_local")) == _wall_clock_seconds(packet_session.get("open_local"))
        and _wall_clock_seconds(contract_session.get("close_local")) == _wall_clock_seconds(packet_session.get("close_local"))
    )


def _session_contract_text(session: dict[str, Any]) -> str:
    return (
        f"{_text(session.get('timezone'))}|"
        f"{_text(session.get('open_local'))}|"
        f"{_text(session.get('close_local'))}"
    )


def _profile_session_text(profile) -> str:
    return (
        f"{profile.session.timezone}|"
        f"{_seconds_to_hhmm(profile.session.open_seconds)}|"
        f"{_seconds_to_hhmm(profile.session.close_seconds)}"
    )


def _live_contract_metadata_text(live_fetch_contract: dict[str, Any]) -> str:
    session = _mapping(live_fetch_contract.get("session"))
    return (
        f"{_text(live_fetch_contract.get('market'))}|"
        f"{_text(live_fetch_contract.get('exchange'))}|"
        f"{_session_contract_text(session)}"
    )


def _validate_config(config: ProviderMarketDataLiveSessionConfig) -> None:
    if not str(config.trade_date).strip():
        raise ValueError("trade_date is required")
    if config.min_capture_rows <= 0:
        raise ValueError("min_capture_rows must be positive")
    if config.pipeline_min_rows <= 0:
        raise ValueError("pipeline_min_rows must be positive")
    for name in ("tick_size", "max_p99_gap_ns", "max_median_spread_ticks"):
        value = getattr(config, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")


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


def _value_text(value: object, fallback: str = "") -> str:
    return _text(value, fallback)


def _safe_label(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return safe.strip("._-") or "session"


def _seconds_to_hhmm(seconds: int) -> str:
    hour = seconds // 3600
    minute = (seconds % 3600) // 60
    return f"{hour:02d}:{minute:02d}"


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


def _shell_quote(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if re.search(r"[\s'\"`]", text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
