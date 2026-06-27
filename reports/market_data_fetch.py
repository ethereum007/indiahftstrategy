from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import file_sha256, write_experiment_manifest
from reports.market_data_source import PROVIDER_SPECS, SUPPORTED_KINDS, SUPPORTED_TRANSPORTS


ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SAFE_OUTPUT_RE = re.compile(r"^[A-Za-z0-9_.-]+\.csv$")


@dataclass(frozen=True)
class MarketDataFetchConfig:
    symbols: tuple[str, ...] = ()
    window_start: str = ""
    window_end: str = ""
    poll_interval_ms: int = 1000
    max_latency_ms: int = 250
    expected_market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    output_filename: str = "provider_market_data.csv"
    dry_run: bool = True


@dataclass(frozen=True)
class MarketDataFetchReport:
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


def evaluate_market_data_fetch(
    source_plan_path: str | Path,
    *,
    config: MarketDataFetchConfig | None = None,
) -> MarketDataFetchReport:
    config = _normalize_config(config or MarketDataFetchConfig())
    plan_path = Path(source_plan_path)
    source_config, load_error = _read_source_config(plan_path)
    checks = pd.DataFrame(_checks(plan_path, source_config, load_error, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    summary = _summary(plan_path, source_config, config, checks, ready)
    action_queue = _action_queue(summary.iloc[0], checks, source_config)
    summary = _summary_with_actions(summary, action_queue)
    fetch_config = _config(summary.iloc[0], checks, action_queue, source_config, config)
    return MarketDataFetchReport(checks, summary, action_queue, fetch_config)


def write_market_data_fetch_plan(
    source_plan_path: str | Path,
    output_dir: str | Path,
    *,
    config: MarketDataFetchConfig | None = None,
) -> MarketDataFetchReport:
    report = evaluate_market_data_fetch(source_plan_path, config=config)
    normalized = _normalize_config(config or MarketDataFetchConfig())
    plan_path = Path(source_plan_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / "market_data_fetch_checks.csv", index=False)
    report.summary.to_csv(out / "market_data_fetch_summary.csv", index=False)
    report.action_queue.to_csv(out / "market_data_fetch_action_queue.csv", index=False)
    (out / "market_data_fetch_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "market_data_fetch_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {}
    if plan_path.exists():
        inputs["source_plan"] = plan_path
    credential_env_template_path = _credential_env_template_path(plan_path, report.config)
    if credential_env_template_path is not None and credential_env_template_path.exists():
        inputs["credential_env_template"] = credential_env_template_path
    write_experiment_manifest(
        out,
        run_type="market_data_fetch_plan",
        parameters={
            "source_plan_path": str(plan_path),
            "config": asdict(normalized),
        },
        inputs=inputs,
        extra={
            "fetch": report.config["fetch"],
            "source_plan": report.config["source_plan"],
            "credential_env_template": report.config["credentials"]["env_template"],
        },
    )
    return MarketDataFetchReport(report.checks, report.summary, report.action_queue, report.config, out)


def _normalize_config(config: MarketDataFetchConfig) -> MarketDataFetchConfig:
    return MarketDataFetchConfig(
        symbols=tuple(_normalize_symbols(config.symbols)),
        window_start=str(config.window_start or "").strip(),
        window_end=str(config.window_end or "").strip(),
        poll_interval_ms=int(config.poll_interval_ms),
        max_latency_ms=int(config.max_latency_ms),
        expected_market=_identity_key(config.expected_market) or INDIA_NSE_INDEX_DERIVATIVES.name,
        output_filename=str(config.output_filename or "provider_market_data.csv").strip(),
        dry_run=bool(config.dry_run),
    )


def _read_source_config(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "source plan file does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"source plan file is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"source plan JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "source plan JSON must be an object"
    return payload, ""


def _checks(
    source_plan_path: Path,
    source_config: dict[str, Any],
    load_error: str,
    config: MarketDataFetchConfig,
) -> list[dict[str, Any]]:
    provider = _text(source_config.get("provider"))
    adapter = _text(source_config.get("adapter"))
    kind = _text(source_config.get("kind"))
    transport = _text(source_config.get("transport"))
    market = _text(source_config.get("market"))
    source = _mapping(source_config.get("source"))
    credentials = _mapping(source_config.get("credentials"))
    normalized_pipeline = _mapping(source_config.get("normalized_pipeline"))
    live_fetch_contract = _mapping(source_config.get("live_fetch_contract"))
    credential_env_template_path = _credential_env_template_path(source_plan_path, source_config)
    provider_spec = PROVIDER_SPECS.get(provider)
    auth_required = bool(provider_spec.get("auth_required", False)) if provider_spec else False
    env_vars = _string_list(credentials.get("env_vars"))
    source_ready = bool(source_config.get("ready"))
    live_transport = transport in {"rest", "websocket"}
    rest_transport = transport == "rest"
    file_transport = transport == "file"
    source_uri = _text(source.get("uri"))
    start_valid = _timestamp_valid(config.window_start)
    end_valid = _timestamp_valid(config.window_end)
    has_window = bool(config.window_start and config.window_end)
    return [
        _check(
            "source_plan_path_exists",
            str(source_plan_path),
            "exists",
            True,
            source_plan_path.exists(),
            "market-data source plan config is required",
        ),
        _check(
            "source_plan_json_readable",
            load_error or "ok",
            "is",
            "ok",
            not load_error,
            load_error or "market-data source plan JSON could not be read",
        ),
        _check(
            "source_plan_ready",
            source_ready,
            "is",
            True,
            source_ready,
            "source plan must pass before fetch planning can proceed",
        ),
        _check(
            "provider_known",
            provider,
            "in",
            sorted(PROVIDER_SPECS),
            provider in PROVIDER_SPECS,
            "source plan provider is not registered",
        ),
        _check(
            "kind_supported",
            kind,
            "in",
            SUPPORTED_KINDS,
            kind in SUPPORTED_KINDS,
            "source plan kind must be ticks or chain",
        ),
        _check(
            "transport_supported",
            transport,
            "in",
            SUPPORTED_TRANSPORTS,
            transport in SUPPORTED_TRANSPORTS,
            "source plan transport is unsupported",
        ),
        _check(
            "credentials_values_not_stored",
            bool(credentials.get("values_stored", True)),
            "is",
            False,
            bool(credentials.get("values_stored", True)) is False,
            "source plan must not store credential values",
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
            "live_credentials_present",
            len(env_vars),
            ">=",
            1 if live_transport and auth_required else 0,
            len(env_vars) >= 1 if live_transport and auth_required else True,
            "live provider fetches require credential environment variable names",
        ),
        _check(
            "credential_env_template_available",
            _text(credentials.get("env_template_file")),
            "exists",
            True if live_transport and auth_required else "optional",
            bool(credential_env_template_path and credential_env_template_path.exists())
            if live_transport and auth_required
            else True,
            "live provider fetches require the source-plan credential env template sidecar",
        ),
        _check(
            "source_uri_not_censored",
            source_uri,
            "does_not_contain",
            "***",
            "***" not in source_uri,
            "source URI is censored because the source plan contains a secret-bearing URI",
        ),
        _check(
            "market_matches_expected",
            market,
            "==",
            config.expected_market,
            (not config.expected_market) or market == config.expected_market,
            "source plan market does not match the requested fetch market",
        ),
        _check(
            "live_symbols_present",
            len(config.symbols),
            ">=",
            1 if live_transport else 0,
            len(config.symbols) >= 1 if live_transport else True,
            "live provider fetch planning requires at least one symbol",
        ),
        _check(
            "window_start_valid",
            config.window_start,
            "is",
            "ISO-like timestamp or empty",
            start_valid,
            "window start must be parseable when supplied",
        ),
        _check(
            "window_end_valid",
            config.window_end,
            "is",
            "ISO-like timestamp or empty",
            end_valid,
            "window end must be parseable when supplied",
        ),
        _check(
            "rest_window_present",
            has_window,
            "is",
            True if rest_transport else "optional",
            has_window if rest_transport else True,
            "REST backfill fetches require a bounded start and end window",
        ),
        _check(
            "window_order",
            f"{config.window_start}..{config.window_end}",
            "<",
            "end after start",
            _window_order_valid(config.window_start, config.window_end, require_both=rest_transport),
            "fetch window end must be after start",
        ),
        _check(
            "poll_interval_ms_positive",
            config.poll_interval_ms,
            ">",
            0,
            config.poll_interval_ms > 0,
            "poll interval must be positive",
        ),
        _check(
            "max_latency_ms_positive",
            config.max_latency_ms,
            ">",
            0,
            config.max_latency_ms > 0,
            "max latency budget must be positive",
        ),
        _check(
            "output_filename_safe",
            config.output_filename,
            "matches",
            "safe CSV filename",
            bool(SAFE_OUTPUT_RE.match(config.output_filename)),
            "output filename must be a plain CSV filename without path separators",
        ),
        _check(
            "file_pipeline_available",
            bool(normalized_pipeline.get("available")),
            "is",
            True if file_transport else "not_applicable",
            bool(normalized_pipeline.get("available")) if file_transport else True,
            "file source plans must provide a normalized market-data pipeline command",
        ),
        _check(
            "live_source_next_gate",
            _text(source_config.get("next_gate")),
            "==",
            "provider_fetcher" if live_transport else "not_applicable",
            _text(source_config.get("next_gate")) == "provider_fetcher" if live_transport else True,
            "live source plans must hand off to the provider fetcher gate",
        ),
        _check(
            "live_fetch_contract_available",
            bool(live_fetch_contract.get("available")),
            "is",
            True if live_transport else "not_applicable",
            bool(live_fetch_contract.get("available")) if live_transport else True,
            "live source plans must provide a fetch-contract handoff template",
        ),
        _check(
            "dry_run_only",
            config.dry_run,
            "is",
            True,
            config.dry_run,
            "fetch planning is dry-run only until provider credentials and API contracts are approved",
        ),
    ]


def _summary(
    source_plan_path: Path,
    source_config: dict[str, Any],
    config: MarketDataFetchConfig,
    checks: pd.DataFrame,
    ready: bool,
) -> pd.DataFrame:
    source = _mapping(source_config.get("source"))
    session = _mapping(source_config.get("session"))
    credentials = _mapping(source_config.get("credentials"))
    live_fetch_contract = _mapping(source_config.get("live_fetch_contract"))
    credential_env_template_path = _credential_env_template_path(source_plan_path, source_config)
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    transport = _text(source_config.get("transport"))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "source_plan_path": str(source_plan_path),
                "provider": _text(source_config.get("provider")),
                "adapter": _text(source_config.get("adapter")),
                "kind": _text(source_config.get("kind")),
                "transport": transport,
                "mode": _fetch_mode(transport),
                "market": _text(source_config.get("market")),
                "exchange": _text(source_config.get("exchange")),
                "session_timezone": _text(session.get("timezone")),
                "session_open_local": _text(session.get("open_local")),
                "session_close_local": _text(session.get("close_local")),
                "source_uri": _text(source.get("uri")),
                "source_uri_kind": _text(source.get("uri_kind")),
                "symbols": ";".join(config.symbols),
                "symbol_count": int(len(config.symbols)),
                "window_start": config.window_start,
                "window_end": config.window_end,
                "poll_interval_ms": int(config.poll_interval_ms),
                "max_latency_ms": int(config.max_latency_ms),
                "expected_market": config.expected_market,
                "output_filename": config.output_filename,
                "dry_run": bool(config.dry_run),
                "credential_env_var_count": int(len(_string_list(credentials.get("env_vars")))),
                "credential_env_vars": ";".join(_string_list(credentials.get("env_vars"))),
                "credential_env_template_file": _text(credentials.get("env_template_file")),
                "credential_env_template_path": str(credential_env_template_path or ""),
                "credential_env_template_exists": bool(
                    credential_env_template_path is not None and credential_env_template_path.exists()
                ),
                "credential_env_template_sha256": file_sha256(credential_env_template_path)
                if credential_env_template_path is not None
                and credential_env_template_path.exists()
                and credential_env_template_path.is_file()
                else "",
                "source_live_fetch_contract_available": bool(live_fetch_contract.get("available")),
                "source_live_fetch_contract_next_gate": _text(live_fetch_contract.get("next_gate")),
                "source_live_fetch_contract_command_template": _text(
                    live_fetch_contract.get("command_template")
                ),
                "failed_checks": failed_checks,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                )
                if not checks.empty
                else "",
                "recommendation": "market_data_fetch_plan_ready" if ready else "fix_market_data_fetch_plan",
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


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    source_config: dict[str, Any],
) -> pd.DataFrame:
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
                "adapter": str(summary["adapter"]),
                "kind": str(summary["kind"]),
                "transport": str(summary["transport"]),
                "mode": str(summary["mode"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate, source_config),
            }
        )
    if not rows and bool(summary["ready"]):
        next_gate = "pipeline-vendor-market-data" if str(summary["transport"]) == "file" else "provider_fetcher"
        action = (
            "run_vendor_market_data_pipeline"
            if next_gate == "pipeline-vendor-market-data"
            else f"execute_{summary['mode']}"
        )
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": action,
                "reason": "market-data fetch plan is ready",
                "provider": str(summary["provider"]),
                "adapter": str(summary["adapter"]),
                "kind": str(summary["kind"]),
                "transport": str(summary["transport"]),
                "mode": str(summary["mode"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate, source_config),
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
            "adapter",
            "kind",
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
    source_config: dict[str, Any],
    config: MarketDataFetchConfig,
) -> dict[str, Any]:
    failed_checks = _failed_checks(checks)
    ready_actions = _queue_records(action_queue, "ready")
    blocked_actions = _queue_records(action_queue, "blocked")
    next_action = _first_record(action_queue)
    credentials = _mapping(source_config.get("credentials"))
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "source_plan": _source_plan_contract(summary, source_config),
        "fetch": {
            "mode": str(summary["mode"]),
            "dry_run": bool(config.dry_run),
            "symbols": list(config.symbols),
            "window": {
                "start": config.window_start,
                "end": config.window_end,
            },
            "poll_interval_ms": int(config.poll_interval_ms),
            "max_latency_ms": int(config.max_latency_ms),
            "output_filename": config.output_filename,
            "expected_market": config.expected_market,
        },
        "credentials": {
            "env_vars": _string_list(credentials.get("env_vars")),
            "env_template": _credential_env_template_contract(summary),
            "values_stored": False,
        },
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


def _source_plan_contract(summary: pd.Series, source_config: dict[str, Any]) -> dict[str, Any]:
    source = _mapping(source_config.get("source"))
    return {
        "path": str(summary["source_plan_path"]),
        "ready": bool(source_config.get("ready")),
        "provider": str(summary["provider"]),
        "adapter": str(summary["adapter"]),
        "kind": str(summary["kind"]),
        "transport": str(summary["transport"]),
        "market": str(summary["market"]),
        "exchange": str(summary["exchange"]),
        "session": {
            "timezone": str(summary["session_timezone"]),
            "open_local": str(summary["session_open_local"]),
            "close_local": str(summary["session_close_local"]),
        },
        "source": {
            "uri": str(summary["source_uri"]),
            "uri_kind": str(summary["source_uri_kind"]),
            "file_exists": bool(source.get("file_exists", False)),
            "file_sha256": _text(source.get("file_sha256")),
        },
        "credential_env_template": _credential_env_template_contract(summary),
        "normalized_pipeline": _mapping(source_config.get("normalized_pipeline")),
        "live_fetch_contract": _mapping(source_config.get("live_fetch_contract")),
        "source_next_gate": _text(source_config.get("next_gate")),
    }


def _credential_env_template_contract(summary: pd.Series) -> dict[str, Any]:
    return {
        "file": str(summary["credential_env_template_file"]),
        "path": str(summary["credential_env_template_path"]),
        "exists": bool(summary["credential_env_template_exists"]),
        "sha256": str(summary["credential_env_template_sha256"]),
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Market Data Fetch Plan Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Adapter: {summary['adapter']}",
        f"- Kind: {summary['kind']}",
        f"- Transport: {summary['transport']}",
        f"- Mode: {summary['mode']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Session: {summary['session_open_local'] or '?'} - {summary['session_close_local'] or '?'} {summary['session_timezone'] or ''}",
        f"- Symbols: {summary['symbols'] or 'none'}",
        f"- Window: {summary['window_start'] or 'open'} to {summary['window_end'] or 'open'}",
        f"- Credential env vars: {summary['credential_env_vars'] or 'none'}",
        f"- Credential env template: {summary['credential_env_template_path'] or 'missing'}",
        f"- Output filename: {summary['output_filename']}",
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


def _fetch_mode(transport: str) -> str:
    if transport == "file":
        return "file_pipeline_replay"
    if transport == "rest":
        return "provider_rest_backfill"
    if transport == "websocket":
        return "provider_websocket_capture"
    return "unknown"


def _blocked_next_gate(check: str) -> str:
    if check.startswith("source_plan") or check in {
        "provider_known",
        "kind_supported",
        "transport_supported",
        "credentials_values_not_stored",
        "credential_env_vars_are_names",
        "credential_env_template_available",
        "live_credentials_present",
        "source_uri_not_censored",
        "market_matches_expected",
        "file_pipeline_available",
        "live_source_next_gate",
        "live_fetch_contract_available",
    }:
        return "plan-market-data-source"
    return "plan-market-data-fetch"


def _next_gate_help_command(next_gate: str, source_config: dict[str, Any]) -> str:
    if next_gate == "pipeline-vendor-market-data":
        command = _text(_mapping(source_config.get("normalized_pipeline")).get("command"))
        return command or "python -m hft_cli pipeline-vendor-market-data --help"
    if next_gate == "provider_fetcher":
        return "python -m hft_cli plan-provider-market-data-fetcher --help"
    if next_gate == "plan-market-data-source":
        return "python -m hft_cli plan-market-data-source --help"
    if next_gate == "plan-market-data-fetch":
        return "python -m hft_cli plan-market-data-fetch --help"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("source_plan"):
        return "repair_or_regenerate_market_data_source_plan"
    if check in {"provider_known", "kind_supported", "transport_supported", "market_matches_expected"}:
        return "select_matching_market_data_source_plan"
    if check == "credential_env_template_available":
        return "regenerate_source_plan_with_credential_env_template"
    if check.startswith("credential") or check == "live_credentials_present":
        return "provide_credential_environment_variable_names"
    if check == "source_uri_not_censored":
        return "remove_embedded_secrets_from_source_uri"
    if check == "live_symbols_present":
        return "select_provider_fetch_symbols"
    if check.startswith("window") or check == "rest_window_present":
        return "select_valid_fetch_window"
    if check.startswith("poll") or check.startswith("max_latency"):
        return "set_positive_fetch_timing_budget"
    if check == "output_filename_safe":
        return "set_plain_csv_output_filename"
    if check == "file_pipeline_available":
        return "regenerate_file_source_plan_with_pipeline_command"
    if check == "live_source_next_gate":
        return "regenerate_live_source_plan_for_provider_fetcher"
    if check == "live_fetch_contract_available":
        return "regenerate_live_source_plan_with_fetch_contract"
    if check == "dry_run_only":
        return "keep_provider_fetch_plan_in_dry_run"
    return "repair_market_data_fetch_plan"


def _normalize_symbols(values: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip().upper()
        if text and text not in out:
            out.append(text)
    return out


def _timestamp_valid(value: str) -> bool:
    if not value:
        return True
    return _timestamp(value) is not None


def _window_order_valid(start: str, end: str, *, require_both: bool) -> bool:
    if not start or not end:
        return not require_both
    start_ts = _timestamp(start)
    end_ts = _timestamp(end)
    if start_ts is None or end_ts is None:
        return False
    return bool(start_ts < end_ts)


def _timestamp(value: str) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        return pd.Timestamp(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _auth_env_name_valid(value: str) -> bool:
    return bool(ENV_NAME_RE.match(value)) and "=" not in value


def _credential_env_template_path(source_plan_path: Path, payload: dict[str, Any]) -> Path | None:
    credentials = _mapping(payload.get("credentials"))
    env_template = _mapping(credentials.get("env_template"))
    direct_path = _text(env_template.get("path"))
    if direct_path:
        return Path(direct_path)
    template_file = _text(credentials.get("env_template_file"))
    if not template_file:
        return None
    path = Path(template_file)
    if path.is_absolute():
        return path
    return source_plan_path.parent / path


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _identity_key(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text.lower().replace("-", "_").replace(" ", "_").replace(".", "_")


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
