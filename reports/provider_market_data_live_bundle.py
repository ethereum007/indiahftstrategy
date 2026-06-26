from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


DEFAULT_ADAPTER_TEMPLATE = (
    "provider-adapter capture "
    "--provider {provider} --transport {transport} --endpoint {endpoint} "
    "--market {market} --kind {kind} --start {start_local} --end {end_local} "
    "--output {capture_path}"
)
ENV_TEMPLATE_NAME = "provider_market_data_live_capture_env_template.env"
ADAPTER_HANDOFF_NAME = "provider_market_data_adapter_handoff.json"


@dataclass(frozen=True)
class ProviderMarketDataLiveCaptureBundleConfig:
    preflight_config_path: str = ""
    adapter_command_template: str = ""
    ingest_output_dir: str = ""
    require_preflight_ready: bool = True
    require_env_present: bool = False
    allow_existing_captures: bool = False


@dataclass(frozen=True)
class ProviderMarketDataLiveCaptureBundleReport:
    commands: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    bundle: dict[str, Any]
    adapter_handoff: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_live_capture_bundle(
    live_session_packet_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataLiveCaptureBundleConfig | None = None,
) -> ProviderMarketDataLiveCaptureBundleReport:
    report = evaluate_provider_market_data_live_capture_bundle(
        live_session_packet_path,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.commands.to_csv(out / "provider_market_data_live_capture_commands.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_live_capture_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_live_capture_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_live_capture_action_queue.csv", index=False)
    (out / "provider_market_data_live_capture_bundle.json").write_text(
        json.dumps(report.bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / ENV_TEMPLATE_NAME).write_text(
        _env_template(_string_list(report.bundle.get("authentication", {}).get("env_vars"))),
        encoding="utf-8",
    )
    (out / ADAPTER_HANDOFF_NAME).write_text(
        json.dumps(report.adapter_handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_capture_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.commands, report.action_queue),
        encoding="utf-8",
    )
    packet_path = Path(live_session_packet_path)
    inputs: dict[str, Any] = {"live_session_packet": packet_path} if packet_path.exists() else {}
    preflight_path = Path((config or ProviderMarketDataLiveCaptureBundleConfig()).preflight_config_path)
    if str(preflight_path) and preflight_path.exists():
        inputs["preflight_config"] = preflight_path
    write_experiment_manifest(
        out,
        run_type="provider_market_data_live_capture_bundle",
        parameters={"config": asdict(config or ProviderMarketDataLiveCaptureBundleConfig())},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "command_count": int(report.summary.iloc[0]["command_count"]),
            "failed_checks": int(report.summary.iloc[0]["failed_checks"]),
            "blocked_action_count": int(report.summary.iloc[0]["blocked_action_count"]),
            "adapter_handoff_file": ADAPTER_HANDOFF_NAME,
        },
    )
    return ProviderMarketDataLiveCaptureBundleReport(
        report.commands,
        report.checks,
        report.summary,
        report.action_queue,
        report.bundle,
        report.adapter_handoff,
        out,
    )


def evaluate_provider_market_data_live_capture_bundle(
    live_session_packet_path: str | Path,
    *,
    config: ProviderMarketDataLiveCaptureBundleConfig | None = None,
) -> ProviderMarketDataLiveCaptureBundleReport:
    config = _normalize_config(config or ProviderMarketDataLiveCaptureBundleConfig())
    packet_path = Path(live_session_packet_path)
    packet, packet_error = _read_json(packet_path, "live session packet")
    preflight_path = Path(config.preflight_config_path) if config.preflight_config_path else Path("")
    preflight, preflight_error = _read_json(preflight_path, "preflight config") if config.preflight_config_path else ({}, "")
    env_presence = _env_presence(packet)
    commands = _commands(packet_path, packet, config)
    checks = pd.DataFrame(_checks(packet_path, packet, packet_error, preflight_path, preflight, preflight_error, env_presence, commands, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    action_queue = _action_queue(checks, ready)
    summary = _summary(packet_path, packet, preflight_path, preflight, env_presence, commands, checks, action_queue, config, ready)
    bundle = _bundle(summary.iloc[0], packet_path, packet, preflight_path, preflight, env_presence, commands, checks, action_queue, config)
    adapter_handoff = _adapter_handoff(summary.iloc[0], packet_path, packet, preflight_path, env_presence, commands, config)
    return ProviderMarketDataLiveCaptureBundleReport(commands, checks, summary, action_queue, bundle, adapter_handoff)


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    if not str(path) or str(path) == ".":
        return {}, f"{label} path is missing"
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


def _commands(
    packet_path: Path,
    packet: dict[str, Any],
    config: ProviderMarketDataLiveCaptureBundleConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    template = config.adapter_command_template or DEFAULT_ADAPTER_TEMPLATE
    env_vars = _string_list(_mapping(packet.get("authentication")).get("env_vars"))
    ingest_command = _ingest_command(packet_path, packet, config)
    for index, item in enumerate(_list(packet.get("capture_windows")), start=1):
        window = _mapping(item)
        capture_path = _text(window.get("capture_path"))
        context = {
            "provider": _shell_quote(_text(packet.get("provider"))),
            "transport": _shell_quote(_text(packet.get("transport"))),
            "endpoint": _shell_quote(_text(packet.get("endpoint"))),
            "market": _shell_quote(_text(packet.get("market"))),
            "kind": _shell_quote(_text(packet.get("kind"))),
            "label": _shell_quote(_text(window.get("label"), f"window_{index}")),
            "pipeline_label": _shell_quote(_text(window.get("pipeline_label"), _text(window.get("label"), f"window_{index}"))),
            "start_local": _shell_quote(_text(window.get("start_local"))),
            "end_local": _shell_quote(_text(window.get("end_local"))),
            "capture_path": _shell_quote(capture_path),
            "env_vars": _shell_quote(";".join(env_vars)),
        }
        command, render_error = _render_template(template, context)
        capture_exists = bool(capture_path and Path(capture_path).exists() and Path(capture_path).is_file())
        rows.append(
            {
                "priority": index,
                "queue_status": "pending_validation",
                "label": _text(window.get("label"), f"window_{index}"),
                "pipeline_label": _text(window.get("pipeline_label"), _text(window.get("label"), f"window_{index}")),
                "provider": _text(packet.get("provider")),
                "transport": _text(packet.get("transport")),
                "market": _text(packet.get("market")),
                "kind": _text(packet.get("kind")),
                "endpoint": _text(packet.get("endpoint")),
                "start_local": _text(window.get("start_local")),
                "end_local": _text(window.get("end_local")),
                "capture_path": capture_path,
                "capture_exists": capture_exists,
                "credential_env_vars": ";".join(env_vars),
                "adapter_command": command,
                "render_ok": not render_error,
                "render_error": render_error,
                "post_capture_ingest_command": ingest_command,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "label",
            "pipeline_label",
            "provider",
            "transport",
            "market",
            "kind",
            "endpoint",
            "start_local",
            "end_local",
            "capture_path",
            "capture_exists",
            "credential_env_vars",
            "adapter_command",
            "render_ok",
            "render_error",
            "post_capture_ingest_command",
        ],
    )


def _checks(
    packet_path: Path,
    packet: dict[str, Any],
    packet_error: str,
    preflight_path: Path,
    preflight: dict[str, Any],
    preflight_error: str,
    env_presence: dict[str, bool],
    commands: pd.DataFrame,
    config: ProviderMarketDataLiveCaptureBundleConfig,
) -> list[dict[str, Any]]:
    require_env = config.require_env_present or bool(_mapping(preflight.get("parameters")).get("require_env_present", False))
    command_count = int(len(commands))
    render_ok = bool(commands["render_ok"].astype(bool).all()) if not commands.empty else False
    capture_paths_unique = bool(commands["capture_path"].astype(str).nunique() == len(commands)) if not commands.empty else False
    existing_capture_count = int(commands["capture_exists"].astype(bool).sum()) if not commands.empty else 0
    preflight_provided = bool(config.preflight_config_path)
    preflight_packet_match = _preflight_packet_matches(packet_path, packet, preflight) if preflight_provided and not preflight_error else False
    return [
        _check("live_session_packet_path_exists", str(packet_path), "exists", True, packet_path.exists(), "live session packet is required"),
        _check("live_session_packet_json_readable", packet_error or "ok", "is", "ok", not packet_error, packet_error or "live session packet could not be read"),
        _check("live_session_packet_ready", bool(packet.get("ready")), "is", True, bool(packet.get("ready")), "live session plan must be ready before capture bundling"),
        _check("preflight_config_path_provided", bool(config.preflight_config_path), "is", True, bool(config.preflight_config_path) or not config.require_preflight_ready, "ready preflight config is required before capture bundling"),
        _check("preflight_config_json_readable", preflight_error or "ok", "is", "ok", not preflight_error if preflight_provided else not config.require_preflight_ready, preflight_error or "preflight config could not be read"),
        _check("preflight_config_ready", bool(preflight.get("ready")), "is", True, bool(preflight.get("ready")) if preflight_provided else not config.require_preflight_ready, "preflight must be ready before capture bundling"),
        _check("preflight_packet_matches_session", preflight_packet_match, "is", True, preflight_packet_match if preflight_provided else not config.require_preflight_ready, "preflight config must reference the same live session packet"),
        _check("credential_values_not_stored", bool(_mapping(packet.get("authentication")).get("values_stored", True)), "is", False, bool(_mapping(packet.get("authentication")).get("values_stored", True)) is False, "live session packet must not store credential values"),
        _check("credential_env_vars_present", len(env_presence), ">=", 1, len(env_presence) >= 1, "credential env-var names are required"),
        _check("credential_env_vars_present_in_runtime", sum(env_presence.values()), "==", len(env_presence), all(env_presence.values()) if require_env else True, "required credential environment variables are missing from runtime"),
        _check("capture_windows_present", command_count, ">=", 1, command_count >= 1, "capture bundle requires at least one planned window"),
        _check("capture_paths_unique", command_count, "unique", command_count, capture_paths_unique, "capture output paths must be unique"),
        _check("capture_files_do_not_already_exist", existing_capture_count, "==", 0 if not config.allow_existing_captures else "allowed", config.allow_existing_captures or existing_capture_count == 0, "capture files already exist; choose fresh paths or explicitly allow existing captures"),
        _check("adapter_commands_rendered", int(commands["render_ok"].astype(bool).sum()) if not commands.empty else 0, "==", command_count, render_ok, "all adapter command templates must render"),
        _check("post_capture_ingest_command_present", _ingest_command(packet_path, packet, config), "is_not", "", bool(_ingest_command(packet_path, packet, config)), "post-capture ingest command is required"),
    ]


def _summary(
    packet_path: Path,
    packet: dict[str, Any],
    preflight_path: Path,
    preflight: dict[str, Any],
    env_presence: dict[str, bool],
    commands: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveCaptureBundleConfig,
    ready: bool,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    blocked = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "live_session_packet_path": str(packet_path),
                "preflight_config_path": config.preflight_config_path,
                "preflight_ready": bool(preflight.get("ready")) if config.preflight_config_path else False,
                "provider": _text(packet.get("provider")),
                "transport": _text(packet.get("transport")),
                "market": _text(packet.get("market")),
                "kind": _text(packet.get("kind")),
                "command_count": int(len(commands)),
                "capture_file_collision_count": int(commands["capture_exists"].astype(bool).sum()) if not commands.empty else 0,
                "credential_env_var_count": int(len(env_presence)),
                "credential_env_vars": ";".join(env_presence.keys()),
                "credential_env_vars_present": int(sum(env_presence.values())),
                "require_env_present": bool(config.require_env_present or bool(_mapping(preflight.get("parameters")).get("require_env_present", False))),
                "adapter_template_default": not bool(config.adapter_command_template),
                "ingest_output_dir": _ingest_output_dir(packet, config),
                "post_capture_ingest_command": _ingest_command(packet_path, packet, config),
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0,
                "blocked_action_count": blocked,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "start_provider_market_data_live_capture" if ready else "fix_provider_market_data_live_capture_bundle",
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
                "action": "start_provider_market_data_live_capture",
                "reason": "capture bundle is ready for the provider adapter without persisted credential values",
                "next_gate": "ingest-provider-market-data-live-session",
                "next_gate_help_command": "run the generated post_capture_ingest_command after all capture windows finish",
            }
        )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _bundle(
    summary: pd.Series,
    packet_path: Path,
    packet: dict[str, Any],
    preflight_path: Path,
    preflight: dict[str, Any],
    env_presence: dict[str, bool],
    commands: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveCaptureBundleConfig,
) -> dict[str, Any]:
    command_records = _records(_commands_with_status(commands, "ready" if bool(summary["ready"]) else "blocked"))
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "live_session_packet_path": str(packet_path),
        "preflight_config_path": str(preflight_path) if config.preflight_config_path else "",
        "provider": _text(packet.get("provider")),
        "transport": _text(packet.get("transport")),
        "market": _text(packet.get("market")),
        "kind": _text(packet.get("kind")),
        "authentication": {
            "env_vars": list(env_presence.keys()),
            "env_presence": env_presence,
            "env_template": ENV_TEMPLATE_NAME,
            "values_stored": False,
        },
        "preflight": {
            "ready": bool(preflight.get("ready")) if config.preflight_config_path else False,
            "next_gate": _text(preflight.get("next_gate")),
            "primary_action_status": _text(preflight.get("primary_action_status")),
        },
        "adapter_handoff": ADAPTER_HANDOFF_NAME,
        "commands": command_records,
        "post_capture_ingest_command": str(summary["post_capture_ingest_command"]),
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": actions[0] if actions else {},
    }


def _adapter_handoff(
    summary: pd.Series,
    packet_path: Path,
    packet: dict[str, Any],
    preflight_path: Path,
    env_presence: dict[str, bool],
    commands: pd.DataFrame,
    config: ProviderMarketDataLiveCaptureBundleConfig,
) -> dict[str, Any]:
    output = _mapping(packet.get("output"))
    auth = _mapping(packet.get("authentication"))
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "live_session_packet_path": str(packet_path),
        "preflight_config_path": str(preflight_path) if config.preflight_config_path else "",
        "provider": _text(packet.get("provider")),
        "transport": _text(packet.get("transport")),
        "template_kind": _text(packet.get("template_kind")),
        "market": _text(packet.get("market")),
        "kind": _text(packet.get("kind")),
        "endpoint": _text(packet.get("endpoint")),
        "request": _mapping(packet.get("request")),
        "runtime": _mapping(packet.get("runtime")),
        "authentication": {
            "env_vars": list(env_presence.keys()),
            "env_presence": env_presence,
            "env_template": ENV_TEMPLATE_NAME,
            "values_stored": False,
            "injection": _text(auth.get("injection")),
        },
        "output": {
            "format": _text(output.get("format")),
            "filename": _text(output.get("filename")),
            "schema_columns": _string_list(output.get("schema_columns")),
        },
        "adapter_command_template": config.adapter_command_template or DEFAULT_ADAPTER_TEMPLATE,
        "adapter_template_default": not bool(config.adapter_command_template),
        "capture_windows": _records(
            _commands_with_status(commands, "ready" if bool(summary["ready"]) else "blocked")
        ),
        "post_capture_ingest_command": str(summary["post_capture_ingest_command"]),
        "handoff_invariants": {
            "credential_values_must_not_be_persisted": True,
            "credential_values_must_be_loaded_from_env": True,
            "adapter_must_write_exact_capture_paths": True,
            "capture_output_must_match_schema_columns": _string_list(output.get("schema_columns")),
            "run_post_capture_ingest_after_all_windows": True,
        },
    }


def _commands_with_status(commands: pd.DataFrame, status: str) -> pd.DataFrame:
    if commands.empty:
        return commands.copy()
    out = commands.copy()
    out["queue_status"] = status
    return out


def _preflight_packet_matches(packet_path: Path, packet: dict[str, Any], preflight: dict[str, Any]) -> bool:
    raw_path = _text(preflight.get("live_session_packet_path"))
    if raw_path:
        try:
            if Path(raw_path).resolve() == packet_path.resolve():
                return True
        except OSError:
            if raw_path == str(packet_path):
                return True
    session_packet = _mapping(preflight.get("session_packet"))
    return _text(session_packet.get("client_packet_path")) == _text(packet.get("client_packet_path"))


def _ingest_command(packet_path: Path, packet: dict[str, Any], config: ProviderMarketDataLiveCaptureBundleConfig) -> str:
    out_dir = _ingest_output_dir(packet, config)
    if not out_dir:
        return ""
    return " ".join(
        [
            "python",
            "-m",
            "hft_cli",
            "ingest-provider-market-data-live-session",
            "--live-session-packet",
            _shell_quote(str(packet_path)),
            "--out",
            _shell_quote(out_dir),
            "--fail-on-blocked-actions",
            "--fail-on-breach",
        ]
    )


def _ingest_output_dir(
    packet: dict[str, Any],
    config: ProviderMarketDataLiveCaptureBundleConfig,
) -> str:
    if config.ingest_output_dir:
        return config.ingest_output_dir
    provider = _safe_label(_text(packet.get("provider"), "provider"))
    market = _safe_label(_text(packet.get("market"), "market"))
    day = "session"
    windows = _list(packet.get("capture_windows"))
    if windows:
        first_start = _text(_mapping(windows[0]).get("start_local"))
        if len(first_start) >= 10:
            day = first_start[:10].replace("-", "_")
    return f"runs/provider_market_data_live_ingest/{provider}_{market}_{day}"


def _next_gate_for_check(check: str) -> str:
    if check.startswith("live_session_packet"):
        return "plan-provider-market-data-live-session"
    if check.startswith("preflight"):
        return "preflight-provider-market-data-live-session"
    if check.startswith("credential"):
        return "provider_credentials_runtime"
    if check.startswith("capture"):
        return "plan-provider-market-data-live-session"
    if check.startswith("adapter"):
        return "bundle-provider-market-data-live-capture"
    return "ingest-provider-market-data-live-session"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {
        "plan-provider-market-data-live-session",
        "preflight-provider-market-data-live-session",
        "bundle-provider-market-data-live-capture",
        "ingest-provider-market-data-live-session",
    }:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_credentials_runtime":
        return "set required provider credential environment variables without writing values to artifacts"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("live_session_packet"):
        return "repair_provider_live_session_packet"
    if check.startswith("preflight"):
        return "rerun_provider_market_data_live_preflight"
    if check.startswith("credential"):
        return "load_provider_credentials_into_runtime"
    if check == "capture_files_do_not_already_exist":
        return "choose_fresh_provider_capture_paths"
    if check.startswith("capture"):
        return "repair_provider_capture_windows"
    if check.startswith("adapter"):
        return "repair_provider_adapter_command_template"
    return "repair_provider_market_data_live_capture_bundle"


def _runbook_markdown(summary: pd.Series, commands: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Live Capture Bundle",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Commands: {summary['command_count']}",
        f"- Credential env template: `{ENV_TEMPLATE_NAME}`",
        f"- Adapter handoff: `{ADAPTER_HANDOFF_NAME}`",
        f"- Post-capture ingest: `{summary['post_capture_ingest_command']}`",
        "",
        "## Capture Commands",
        "",
        _commands_table(commands),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _env_template(env_vars: list[str]) -> str:
    lines = [
        "# Provider market-data live capture credentials",
        "# Fill values only in the runtime shell. Do not commit populated copies.",
        "",
    ]
    for name in env_vars:
        lines.append(f"{name}=")
    if not env_vars:
        lines.append("# No credential environment variables were declared in the bundle.")
    return "\n".join(lines) + "\n"


def _commands_table(commands: pd.DataFrame) -> str:
    if commands.empty:
        return "_None_"
    rows = []
    for row in commands.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("label")),
                _text(row.get("start_local")),
                _text(row.get("end_local")),
                _text(row.get("capture_path")),
                _text(row.get("adapter_command")),
            ]
        )
    return _markdown_table(["#", "Label", "Start", "End", "Capture", "Command"], rows)


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


class _FormatMap(dict):
    def __missing__(self, key):
        return ""


def _render_template(template: str, context: dict[str, str]) -> tuple[str, str]:
    try:
        return template.format_map(_FormatMap(context)), ""
    except (KeyError, ValueError) as exc:
        return "", str(exc)


def _env_presence(packet: dict[str, Any]) -> dict[str, bool]:
    env_vars = _string_list(_mapping(packet.get("authentication")).get("env_vars"))
    return {name: name in os.environ for name in env_vars}


def _normalize_config(config: ProviderMarketDataLiveCaptureBundleConfig) -> ProviderMarketDataLiveCaptureBundleConfig:
    return ProviderMarketDataLiveCaptureBundleConfig(
        preflight_config_path=str(config.preflight_config_path or "").strip(),
        adapter_command_template=str(config.adapter_command_template or "").strip(),
        ingest_output_dir=str(config.ingest_output_dir or "").strip(),
        require_preflight_ready=bool(config.require_preflight_ready),
        require_env_present=bool(config.require_env_present),
        allow_existing_captures=bool(config.allow_existing_captures),
    )


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


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _text(value: object, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _safe_label(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return safe.strip("._-") or "session"


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
