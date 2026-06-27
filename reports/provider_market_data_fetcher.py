from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


LIVE_TRANSPORTS = {"rest", "websocket"}
SUPPORTED_PROVIDERS = {"arrow_money", "irage"}
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True)
class ProviderMarketDataFetcherConfig:
    require_env_present: bool = False
    connect_timeout_ms: int = 5000
    read_timeout_ms: int = 1000
    heartbeat_timeout_ms: int = 30000
    max_reconnects: int = 3
    batch_size: int = 5000
    dry_run: bool = True


@dataclass(frozen=True)
class ProviderMarketDataFetcherReport:
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    request_template: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_provider_market_data_fetcher(
    fetch_plan_path: str | Path,
    *,
    config: ProviderMarketDataFetcherConfig | None = None,
) -> ProviderMarketDataFetcherReport:
    config = _normalize_config(config or ProviderMarketDataFetcherConfig())
    plan_path = Path(fetch_plan_path)
    fetch_config, load_error = _read_fetch_config(plan_path)
    checks = pd.DataFrame(_checks(plan_path, fetch_config, load_error, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    request_template = _request_template(fetch_config, config, ready)
    summary = _summary(plan_path, fetch_config, config, checks, ready, request_template)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, action_queue)
    provider_config = _config(summary.iloc[0], checks, action_queue, fetch_config, config, request_template)
    return ProviderMarketDataFetcherReport(checks, summary, action_queue, provider_config, request_template)


def write_provider_market_data_fetcher_plan(
    fetch_plan_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataFetcherConfig | None = None,
) -> ProviderMarketDataFetcherReport:
    report = evaluate_provider_market_data_fetcher(fetch_plan_path, config=config)
    normalized = _normalize_config(config or ProviderMarketDataFetcherConfig())
    plan_path = Path(fetch_plan_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / "provider_market_data_fetcher_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_fetcher_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_fetcher_action_queue.csv", index=False)
    (out / "provider_market_data_fetcher_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_request_template.json").write_text(
        json.dumps(report.request_template, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_fetcher_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {}
    if plan_path.exists():
        inputs["fetch_plan"] = plan_path
    credential_env_template = _credential_env_template_from_fetch_config(report.config)
    if credential_env_template["path"]:
        credential_env_template_path = Path(credential_env_template["path"])
        if credential_env_template_path.exists():
            inputs["credential_env_template"] = credential_env_template_path
    write_experiment_manifest(
        out,
        run_type="provider_market_data_fetcher_plan",
        parameters={
            "fetch_plan_path": str(plan_path),
            "config": asdict(normalized),
        },
        inputs=inputs,
        extra={
            "provider_fetcher": report.config["provider_fetcher"],
            "request_template": report.request_template,
            "credential_env_template": credential_env_template,
        },
    )
    return ProviderMarketDataFetcherReport(
        report.checks,
        report.summary,
        report.action_queue,
        report.config,
        report.request_template,
        out,
    )


def _normalize_config(config: ProviderMarketDataFetcherConfig) -> ProviderMarketDataFetcherConfig:
    return ProviderMarketDataFetcherConfig(
        require_env_present=bool(config.require_env_present),
        connect_timeout_ms=int(config.connect_timeout_ms),
        read_timeout_ms=int(config.read_timeout_ms),
        heartbeat_timeout_ms=int(config.heartbeat_timeout_ms),
        max_reconnects=int(config.max_reconnects),
        batch_size=int(config.batch_size),
        dry_run=bool(config.dry_run),
    )


def _read_fetch_config(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "fetch plan file does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"fetch plan file is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"fetch plan JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "fetch plan JSON must be an object"
    return payload, ""


def _checks(
    fetch_plan_path: Path,
    fetch_config: dict[str, Any],
    load_error: str,
    config: ProviderMarketDataFetcherConfig,
) -> list[dict[str, Any]]:
    source_plan = _mapping(fetch_config.get("source_plan"))
    fetch = _mapping(fetch_config.get("fetch"))
    credentials = _mapping(fetch_config.get("credentials"))
    credential_env_template = _mapping(credentials.get("env_template"))
    env_vars = _string_list(credentials.get("env_vars"))
    provider = _text(source_plan.get("provider"))
    transport = _text(source_plan.get("transport"))
    mode = _text(fetch.get("mode"))
    source = _mapping(source_plan.get("source"))
    live_fetch_contract = _mapping(source_plan.get("live_fetch_contract"))
    source_uri = _text(source.get("uri"))
    symbols = _string_list(fetch.get("symbols"))
    env_presence = _env_presence(env_vars)
    return [
        _check(
            "fetch_plan_path_exists",
            str(fetch_plan_path),
            "exists",
            True,
            fetch_plan_path.exists(),
            "market-data fetch plan config is required",
        ),
        _check(
            "fetch_plan_json_readable",
            load_error or "ok",
            "is",
            "ok",
            not load_error,
            load_error or "market-data fetch plan JSON could not be read",
        ),
        _check(
            "fetch_plan_ready",
            bool(fetch_config.get("ready")),
            "is",
            True,
            bool(fetch_config.get("ready")),
            "fetch plan must pass before provider fetcher preparation can proceed",
        ),
        _check(
            "provider_supported_for_live_fetch",
            provider,
            "in",
            sorted(SUPPORTED_PROVIDERS),
            provider in SUPPORTED_PROVIDERS,
            "provider fetcher supports Arrow.money and iRage live plans only",
        ),
        _check(
            "transport_is_live",
            transport,
            "in",
            sorted(LIVE_TRANSPORTS),
            transport in LIVE_TRANSPORTS,
            "provider fetcher requires a REST or websocket fetch plan, not file replay",
        ),
        _check(
            "mode_matches_transport",
            mode,
            "matches",
            "provider_rest_backfill/provider_websocket_capture",
            _mode_matches_transport(mode, transport),
            "fetch mode must match the source transport",
        ),
        _check(
            "source_uri_present",
            source_uri,
            "is_not",
            "",
            bool(source_uri),
            "provider fetcher needs a live source URI",
        ),
        _check(
            "source_uri_not_censored",
            source_uri,
            "does_not_contain",
            "***",
            "***" not in source_uri,
            "source URI is censored because the source plan contained a secret-bearing URI",
        ),
        _check(
            "credential_values_not_stored",
            bool(credentials.get("values_stored", True)),
            "is",
            False,
            bool(credentials.get("values_stored", True)) is False,
            "fetch plan must not store credential values",
        ),
        _check(
            "credential_env_vars_present",
            len(env_vars),
            ">=",
            1,
            len(env_vars) >= 1,
            "provider fetcher requires credential environment variable names",
        ),
        _check(
            "credential_env_vars_are_names",
            ";".join(env_vars),
            "matches",
            "UPPER_SNAKE_CASE names without values",
            all(_auth_env_name_valid(value) for value in env_vars),
            "credential references must be environment variable names",
        ),
        _check(
            "credential_env_vars_present_in_runtime",
            ";".join(name for name, present in env_presence.items() if present),
            "contains",
            "all env vars" if config.require_env_present else "optional",
            all(env_presence.values()) if config.require_env_present else True,
            "required credential environment variables are missing from runtime",
        ),
        _check(
            "credential_env_template_carried",
            _text(credential_env_template.get("path")),
            "exists",
            True,
            bool(credential_env_template.get("exists")) and bool(_text(credential_env_template.get("sha256"))),
            "fetch plan must carry the source-plan credential env-template proof",
        ),
        _check(
            "source_live_fetch_contract_carried",
            bool(live_fetch_contract.get("available")),
            "is",
            True,
            bool(live_fetch_contract.get("available")) and _text(live_fetch_contract.get("next_gate")) == "provider_fetcher",
            "fetch plan must carry the upstream live fetch-contract handoff",
        ),
        _check(
            "symbols_present",
            len(symbols),
            ">=",
            1,
            len(symbols) >= 1,
            "provider fetcher requires one or more symbols",
        ),
        _check(
            "connect_timeout_ms_positive",
            config.connect_timeout_ms,
            ">",
            0,
            config.connect_timeout_ms > 0,
            "connect timeout must be positive",
        ),
        _check(
            "read_timeout_ms_positive",
            config.read_timeout_ms,
            ">",
            0,
            config.read_timeout_ms > 0,
            "read timeout must be positive",
        ),
        _check(
            "heartbeat_timeout_ms_positive",
            config.heartbeat_timeout_ms,
            ">",
            0,
            config.heartbeat_timeout_ms > 0,
            "heartbeat timeout must be positive",
        ),
        _check(
            "max_reconnects_nonnegative",
            config.max_reconnects,
            ">=",
            0,
            config.max_reconnects >= 0,
            "max reconnect count cannot be negative",
        ),
        _check(
            "batch_size_positive",
            config.batch_size,
            ">",
            0,
            config.batch_size > 0,
            "batch size must be positive",
        ),
        _check(
            "dry_run_only",
            config.dry_run,
            "is",
            True,
            config.dry_run,
            "provider fetcher preparation is dry-run only until API contracts are approved",
        ),
    ]


def _summary(
    fetch_plan_path: Path,
    fetch_config: dict[str, Any],
    config: ProviderMarketDataFetcherConfig,
    checks: pd.DataFrame,
    ready: bool,
    request_template: dict[str, Any],
) -> pd.DataFrame:
    source_plan = _mapping(fetch_config.get("source_plan"))
    fetch = _mapping(fetch_config.get("fetch"))
    credentials = _mapping(fetch_config.get("credentials"))
    credential_env_template = _mapping(credentials.get("env_template"))
    live_fetch_contract = _mapping(source_plan.get("live_fetch_contract"))
    session = _mapping(source_plan.get("session"))
    env_vars = _string_list(credentials.get("env_vars"))
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "fetch_plan_path": str(fetch_plan_path),
                "provider": _text(source_plan.get("provider")),
                "adapter": _text(source_plan.get("adapter")),
                "kind": _text(source_plan.get("kind")),
                "transport": _text(source_plan.get("transport")),
                "mode": _text(fetch.get("mode")),
                "market": _text(source_plan.get("market")),
                "exchange": _text(source_plan.get("exchange")),
                "session_timezone": _text(session.get("timezone")),
                "session_open_local": _text(session.get("open_local")),
                "session_close_local": _text(session.get("close_local")),
                "source_uri": _text(_mapping(source_plan.get("source")).get("uri")),
                "symbols": ";".join(_string_list(fetch.get("symbols"))),
                "symbol_count": int(len(_string_list(fetch.get("symbols")))),
                "window_start": _text(_mapping(fetch.get("window")).get("start")),
                "window_end": _text(_mapping(fetch.get("window")).get("end")),
                "credential_env_var_count": int(len(env_vars)),
                "credential_env_vars": ";".join(env_vars),
                "credential_env_vars_present": int(sum(_env_presence(env_vars).values())),
                "credential_env_template_path": _text(credential_env_template.get("path")),
                "credential_env_template_exists": bool(credential_env_template.get("exists")),
                "credential_env_template_sha256": _text(credential_env_template.get("sha256")),
                "source_live_fetch_contract_available": bool(live_fetch_contract.get("available")),
                "source_live_fetch_contract_next_gate": _text(live_fetch_contract.get("next_gate")),
                "source_live_fetch_contract_command_template": _text(
                    live_fetch_contract.get("command_template")
                ),
                "require_env_present": bool(config.require_env_present),
                "connect_timeout_ms": int(config.connect_timeout_ms),
                "read_timeout_ms": int(config.read_timeout_ms),
                "heartbeat_timeout_ms": int(config.heartbeat_timeout_ms),
                "max_reconnects": int(config.max_reconnects),
                "batch_size": int(config.batch_size),
                "dry_run": bool(config.dry_run),
                "template_kind": _text(request_template.get("template_kind")),
                "failed_checks": failed_checks,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                )
                if not checks.empty
                else "",
                "recommendation": "provider_market_data_fetcher_ready"
                if ready
                else "fix_provider_market_data_fetcher_plan",
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    ready_actions = int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0
    blocked_actions = (
        int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    )
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
        next_gate = _blocked_next_gate(str(row["check"]))
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(str(row["check"])),
                "reason": str(row["reason"]),
                "provider": str(summary["provider"]),
                "transport": str(summary["transport"]),
                "mode": str(summary["mode"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
            }
        )
    if not rows and bool(summary["ready"]):
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "review_provider_fetcher_request_template",
                "reason": "provider fetcher preparation is ready",
                "provider": str(summary["provider"]),
                "transport": str(summary["transport"]),
                "mode": str(summary["mode"]),
                "next_gate": "provider_fetcher_client",
                "next_gate_help_command": "python -m hft_cli prepare-provider-market-data-client --help",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "action",
            "reason",
            "provider",
            "transport",
            "mode",
            "next_gate",
            "next_gate_help_command",
        ],
    )


def _config(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    fetch_config: dict[str, Any],
    config: ProviderMarketDataFetcherConfig,
    request_template: dict[str, Any],
) -> dict[str, Any]:
    failed_checks = _failed_checks(checks)
    ready_actions = _queue_records(action_queue, "ready")
    blocked_actions = _queue_records(action_queue, "blocked")
    next_action = _first_record(action_queue)
    env_vars = _string_list(_mapping(fetch_config.get("credentials")).get("env_vars"))
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "fetch_plan": {
            "path": str(summary["fetch_plan_path"]),
            "ready": bool(fetch_config.get("ready")),
            "source_plan": _mapping(fetch_config.get("source_plan")),
            "fetch": _mapping(fetch_config.get("fetch")),
            "credential_env_template": _credential_env_template_contract(summary),
            "live_fetch_contract": _mapping(_mapping(fetch_config.get("source_plan")).get("live_fetch_contract")),
        },
        "provider_fetcher": {
            "dry_run": bool(config.dry_run),
            "require_env_present": bool(config.require_env_present),
            "connect_timeout_ms": int(config.connect_timeout_ms),
            "read_timeout_ms": int(config.read_timeout_ms),
            "heartbeat_timeout_ms": int(config.heartbeat_timeout_ms),
            "max_reconnects": int(config.max_reconnects),
            "batch_size": int(config.batch_size),
            "request_template_file": "provider_market_data_request_template.json",
        },
        "credentials": {
            "env_vars": env_vars,
            "env_presence": _env_presence(env_vars),
            "env_template": _credential_env_template_contract(summary),
            "values_stored": False,
        },
        "request_template": request_template,
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
        "ready_action_count": len(ready_actions),
        "blocked_action_count": len(blocked_actions),
        "next_gate": "" if next_action is None else str(next_action["next_gate"]),
        "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
        "next_actions": _records(action_queue),
        "ready_actions": ready_actions,
        "blocked_actions": blocked_actions,
        "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
        "primary_action": {} if next_action is None else next_action,
    }


def _request_template(
    fetch_config: dict[str, Any],
    config: ProviderMarketDataFetcherConfig,
    ready: bool,
) -> dict[str, Any]:
    source_plan = _mapping(fetch_config.get("source_plan"))
    fetch = _mapping(fetch_config.get("fetch"))
    credentials = _mapping(fetch_config.get("credentials"))
    transport = _text(source_plan.get("transport"))
    symbols = _string_list(fetch.get("symbols"))
    window = _mapping(fetch.get("window"))
    base: dict[str, Any] = {
        "schema_version": 1,
        "ready": bool(ready),
        "dry_run": bool(config.dry_run),
        "provider": _text(source_plan.get("provider")),
        "adapter": _text(source_plan.get("adapter")),
        "kind": _text(source_plan.get("kind")),
        "market": _text(source_plan.get("market")),
        "exchange": _text(source_plan.get("exchange")),
        "session": _mapping(source_plan.get("session")),
        "transport": transport,
        "mode": _text(fetch.get("mode")),
        "endpoint": _text(_mapping(source_plan.get("source")).get("uri")),
        "authentication": {
            "env_vars": _string_list(credentials.get("env_vars")),
            "env_template": _mapping(credentials.get("env_template")),
            "values_stored": False,
            "injection": "provider_adapter_specific",
        },
        "output": {
            "filename": _text(fetch.get("output_filename")),
            "format": "normalized_csv",
        },
        "runtime": {
            "connect_timeout_ms": int(config.connect_timeout_ms),
            "read_timeout_ms": int(config.read_timeout_ms),
            "heartbeat_timeout_ms": int(config.heartbeat_timeout_ms),
            "max_reconnects": int(config.max_reconnects),
            "batch_size": int(config.batch_size),
        },
    }
    if transport == "rest":
        base.update(
            {
                "template_kind": "rest_backfill_request",
                "method": "GET",
                "query": {
                    "symbols": symbols,
                    "window_start": _text(window.get("start")),
                    "window_end": _text(window.get("end")),
                    "kind": _text(source_plan.get("kind")),
                    "market": _text(source_plan.get("market")),
                    "exchange": _text(source_plan.get("exchange")),
                },
            }
        )
    elif transport == "websocket":
        base.update(
            {
                "template_kind": "websocket_subscription",
                "subscriptions": [
                    {
                        "symbol": symbol,
                        "kind": _text(source_plan.get("kind")),
                        "market": _text(source_plan.get("market")),
                        "exchange": _text(source_plan.get("exchange")),
                    }
                    for symbol in symbols
                ],
            }
        )
    else:
        base.update({"template_kind": "unsupported_transport"})
    return base


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Fetcher Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Adapter: {summary['adapter']}",
        f"- Transport: {summary['transport']}",
        f"- Mode: {summary['mode']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Session: {summary['session_open_local'] or '?'} - {summary['session_close_local'] or '?'} {summary['session_timezone'] or ''}",
        f"- Symbols: {summary['symbols'] or 'none'}",
        f"- Credential env vars: {summary['credential_env_vars'] or 'none'}",
        f"- Credential env vars present: {summary['credential_env_vars_present']}",
        f"- Credential env template: {summary['credential_env_template_path'] or 'missing'}",
        f"- Template: provider_market_data_request_template.json ({summary['template_kind']})",
        "",
        "## Actions",
    ]
    if action_queue.empty:
        lines.append("- None")
    else:
        for _, row in action_queue.iterrows():
            lines.append(
                f"- [{row['queue_status']}] {row['action']}: {row['reason']} "
                f"(`{row['next_gate_help_command']}`)"
            )
    return "\n".join(lines) + "\n"


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": _jsonable(value),
        "operator": operator,
        "threshold": _jsonable(threshold),
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _mode_matches_transport(mode: str, transport: str) -> bool:
    if transport == "rest":
        return mode == "provider_rest_backfill"
    if transport == "websocket":
        return mode == "provider_websocket_capture"
    return False


def _env_presence(env_vars: list[str]) -> dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in env_vars}


def _auth_env_name_valid(value: str) -> bool:
    return bool(ENV_NAME_RE.match(value)) and "=" not in value


def _credential_env_template_contract(summary: pd.Series) -> dict[str, Any]:
    return {
        "path": str(summary["credential_env_template_path"]),
        "exists": bool(summary["credential_env_template_exists"]),
        "sha256": str(summary["credential_env_template_sha256"]),
    }


def _credential_env_template_from_fetch_config(fetch_config: dict[str, Any]) -> dict[str, Any]:
    credentials = _mapping(fetch_config.get("credentials"))
    env_template = _mapping(credentials.get("env_template"))
    return {
        "path": _text(env_template.get("path")),
        "exists": bool(env_template.get("exists")),
        "sha256": _text(env_template.get("sha256")),
    }


def _blocked_next_gate(check: str) -> str:
    if check.startswith("fetch_plan") or check in {
        "provider_supported_for_live_fetch",
        "transport_is_live",
        "mode_matches_transport",
        "source_uri_present",
        "source_uri_not_censored",
        "credential_values_not_stored",
        "credential_env_vars_present",
        "credential_env_vars_are_names",
        "credential_env_template_carried",
        "source_live_fetch_contract_carried",
        "symbols_present",
    }:
        return "plan-market-data-fetch"
    return "plan-provider-market-data-fetcher"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate == "plan-market-data-fetch":
        return "python -m hft_cli plan-market-data-fetch --help"
    if next_gate == "plan-provider-market-data-fetcher":
        return "python -m hft_cli plan-provider-market-data-fetcher --help"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("fetch_plan"):
        return "repair_or_regenerate_market_data_fetch_plan"
    if check in {"provider_supported_for_live_fetch", "transport_is_live", "mode_matches_transport"}:
        return "select_live_provider_fetch_plan"
    if check.startswith("source_uri"):
        return "repair_live_source_uri_contract"
    if check == "credential_env_template_carried":
        return "regenerate_fetch_plan_with_credential_env_template"
    if check.startswith("credential"):
        return "provide_runtime_credential_environment_variables"
    if check == "source_live_fetch_contract_carried":
        return "regenerate_fetch_plan_with_source_live_fetch_contract"
    if check == "symbols_present":
        return "select_provider_fetch_symbols"
    if check.endswith("_positive") or check == "max_reconnects_nonnegative":
        return "set_valid_provider_fetcher_runtime_budget"
    if check == "dry_run_only":
        return "keep_provider_fetcher_preparation_in_dry_run"
    return "repair_provider_market_data_fetcher_plan"


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def _failed_checks(checks: pd.DataFrame) -> list[dict[str, Any]]:
    if checks.empty:
        return []
    return _records(checks.loc[~checks["passed"].astype(bool)])


def _queue_records(action_queue: pd.DataFrame, status: str) -> list[dict[str, Any]]:
    if action_queue.empty:
        return []
    return _records(action_queue.loc[action_queue["queue_status"].astype(str) == status])


def _first_record(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame.empty:
        return None
    return _records(frame.iloc[[0]])[0]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        rows.append({str(key): _jsonable(value) for key, value in record.items()})
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
