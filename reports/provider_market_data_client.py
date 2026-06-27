from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import NORMALIZED_CHAIN_COLUMNS, NORMALIZED_TICK_COLUMNS
from reports.manifest import write_experiment_manifest


SUPPORTED_PROVIDERS = {"arrow_money", "irage"}
LIVE_TRANSPORTS = {"rest", "websocket"}
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SAFE_OUTPUT_RE = re.compile(r"^[A-Za-z0-9_.-]+\.csv$")


@dataclass(frozen=True)
class ProviderMarketDataClientConfig:
    require_env_present: bool = False
    session_label: str = ""
    max_clock_skew_ms: int = 250
    max_local_buffer_rows: int = 100000
    dry_run: bool = True


@dataclass(frozen=True)
class ProviderMarketDataClientReport:
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    packet: dict[str, Any]
    output_schema: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_provider_market_data_client(
    fetcher_plan_path: str | Path,
    *,
    config: ProviderMarketDataClientConfig | None = None,
) -> ProviderMarketDataClientReport:
    config = _normalize_config(config or ProviderMarketDataClientConfig())
    plan_path = Path(fetcher_plan_path)
    fetcher_config, load_error = _read_fetcher_config(plan_path)
    output_schema = _output_schema(_request_template(fetcher_config))
    checks = pd.DataFrame(_checks(plan_path, fetcher_config, load_error, config, output_schema))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    packet = _client_packet(fetcher_config, config, output_schema, ready)
    summary = _summary(plan_path, fetcher_config, config, checks, ready, packet, output_schema)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, action_queue)
    client_config = _config(summary.iloc[0], checks, action_queue, fetcher_config, config, packet, output_schema)
    return ProviderMarketDataClientReport(checks, summary, action_queue, client_config, packet, output_schema)


def write_provider_market_data_client_plan(
    fetcher_plan_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataClientConfig | None = None,
) -> ProviderMarketDataClientReport:
    report = evaluate_provider_market_data_client(fetcher_plan_path, config=config)
    normalized = _normalize_config(config or ProviderMarketDataClientConfig())
    plan_path = Path(fetcher_plan_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / "provider_market_data_client_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_client_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_client_action_queue.csv", index=False)
    report.output_schema.to_csv(out / "provider_market_data_output_schema.csv", index=False)
    (out / "provider_market_data_client_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_client_packet.json").write_text(
        json.dumps(report.packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_client_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {}
    if plan_path.exists():
        inputs["fetcher_plan"] = plan_path
    credential_env_template = _credential_env_template_from_client_config(report.config)
    if credential_env_template["path"]:
        credential_env_template_path = Path(credential_env_template["path"])
        if credential_env_template_path.exists():
            inputs["credential_env_template"] = credential_env_template_path
    write_experiment_manifest(
        out,
        run_type="provider_market_data_client_dry_run",
        parameters={
            "fetcher_plan_path": str(plan_path),
            "config": asdict(normalized),
        },
        inputs=inputs,
        extra={
            "client": report.config["client"],
            "packet": report.packet,
            "credential_env_template": credential_env_template,
            "output_schema_columns": report.output_schema["column"].astype(str).tolist(),
        },
    )
    return ProviderMarketDataClientReport(
        report.checks,
        report.summary,
        report.action_queue,
        report.config,
        report.packet,
        report.output_schema,
        out,
    )


def _normalize_config(config: ProviderMarketDataClientConfig) -> ProviderMarketDataClientConfig:
    return ProviderMarketDataClientConfig(
        require_env_present=bool(config.require_env_present),
        session_label=str(config.session_label or "").strip(),
        max_clock_skew_ms=int(config.max_clock_skew_ms),
        max_local_buffer_rows=int(config.max_local_buffer_rows),
        dry_run=bool(config.dry_run),
    )


def _read_fetcher_config(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "provider fetcher plan file does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"provider fetcher plan file is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"provider fetcher plan JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "provider fetcher plan JSON must be an object"
    return payload, ""


def _checks(
    fetcher_plan_path: Path,
    fetcher_config: dict[str, Any],
    load_error: str,
    config: ProviderMarketDataClientConfig,
    output_schema: pd.DataFrame,
) -> list[dict[str, Any]]:
    template = _request_template(fetcher_config)
    fetch_plan = _mapping(fetcher_config.get("fetch_plan"))
    authentication = _mapping(template.get("authentication"))
    credential_env_template = _mapping(authentication.get("env_template"))
    live_fetch_contract = _mapping(fetch_plan.get("live_fetch_contract"))
    output = _mapping(template.get("output"))
    runtime = _mapping(template.get("runtime"))
    env_vars = _string_list(authentication.get("env_vars"))
    env_presence = _env_presence(env_vars)
    transport = _text(template.get("transport"))
    kind = _text(template.get("kind"))
    output_filename = _text(output.get("filename"))
    return [
        _check(
            "fetcher_plan_path_exists",
            str(fetcher_plan_path),
            "exists",
            True,
            fetcher_plan_path.exists(),
            "provider fetcher plan config is required",
        ),
        _check(
            "fetcher_plan_json_readable",
            load_error or "ok",
            "is",
            "ok",
            not load_error,
            load_error or "provider fetcher plan JSON could not be read",
        ),
        _check(
            "fetcher_plan_ready",
            bool(fetcher_config.get("ready")),
            "is",
            True,
            bool(fetcher_config.get("ready")),
            "provider fetcher preparation must pass before client dry-run packet generation",
        ),
        _check(
            "request_template_ready",
            bool(template.get("ready")),
            "is",
            True,
            bool(template.get("ready")),
            "request template must be ready",
        ),
        _check(
            "provider_supported",
            _text(template.get("provider")),
            "in",
            sorted(SUPPORTED_PROVIDERS),
            _text(template.get("provider")) in SUPPORTED_PROVIDERS,
            "provider client dry-run supports Arrow.money and iRage plans only",
        ),
        _check(
            "transport_is_live",
            transport,
            "in",
            sorted(LIVE_TRANSPORTS),
            transport in LIVE_TRANSPORTS,
            "provider client requires REST or websocket transport",
        ),
        _check(
            "template_kind_matches_transport",
            _text(template.get("template_kind")),
            "matches",
            "rest_backfill_request/websocket_subscription",
            _template_kind_matches_transport(_text(template.get("template_kind")), transport),
            "request template kind does not match the transport",
        ),
        _check(
            "endpoint_present",
            _text(template.get("endpoint")),
            "is_not",
            "",
            bool(_text(template.get("endpoint"))),
            "provider endpoint is required",
        ),
        _check(
            "endpoint_not_censored",
            _text(template.get("endpoint")),
            "does_not_contain",
            "***",
            "***" not in _text(template.get("endpoint")),
            "provider endpoint is censored because an upstream URI contained a secret",
        ),
        _check(
            "credential_values_not_stored",
            bool(authentication.get("values_stored", True)),
            "is",
            False,
            bool(authentication.get("values_stored", True)) is False,
            "request template must not store credential values",
        ),
        _check(
            "credential_env_vars_present",
            len(env_vars),
            ">=",
            1,
            len(env_vars) >= 1,
            "provider client requires credential environment variable names",
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
            "request template must carry the blank credential env-template proof",
        ),
        _check(
            "source_live_fetch_contract_carried",
            bool(live_fetch_contract.get("available")),
            "is",
            True,
            bool(live_fetch_contract.get("available")) and _text(live_fetch_contract.get("next_gate")) == "provider_fetcher",
            "fetcher plan must carry the upstream live fetch-contract handoff",
        ),
        _check(
            "output_format_normalized_csv",
            _text(output.get("format")),
            "==",
            "normalized_csv",
            _text(output.get("format")) == "normalized_csv",
            "provider client output must be normalized CSV",
        ),
        _check(
            "output_filename_safe",
            output_filename,
            "matches",
            "safe CSV filename",
            bool(SAFE_OUTPUT_RE.match(output_filename)),
            "output filename must be a plain CSV filename without path separators",
        ),
        _check(
            "output_schema_known",
            kind,
            "in",
            ("ticks", "chain"),
            not output_schema.empty,
            "provider client output schema is unknown for this data kind",
        ),
        _check(
            "rest_template_has_query",
            len(_string_list(_mapping(template.get("query")).get("symbols"))),
            ">=",
            1 if transport == "rest" else 0,
            len(_string_list(_mapping(template.get("query")).get("symbols"))) >= 1 if transport == "rest" else True,
            "REST request template requires query symbols",
        ),
        _check(
            "websocket_template_has_subscriptions",
            len(_list(template.get("subscriptions"))),
            ">=",
            1 if transport == "websocket" else 0,
            len(_list(template.get("subscriptions"))) >= 1 if transport == "websocket" else True,
            "websocket request template requires subscriptions",
        ),
        _check(
            "runtime_connect_timeout_positive",
            _int(runtime.get("connect_timeout_ms")),
            ">",
            0,
            _int(runtime.get("connect_timeout_ms")) > 0,
            "connect timeout must be positive",
        ),
        _check(
            "runtime_read_timeout_positive",
            _int(runtime.get("read_timeout_ms")),
            ">",
            0,
            _int(runtime.get("read_timeout_ms")) > 0,
            "read timeout must be positive",
        ),
        _check(
            "runtime_batch_size_positive",
            _int(runtime.get("batch_size")),
            ">",
            0,
            _int(runtime.get("batch_size")) > 0,
            "batch size must be positive",
        ),
        _check(
            "client_clock_skew_budget_positive",
            config.max_clock_skew_ms,
            ">",
            0,
            config.max_clock_skew_ms > 0,
            "client clock skew budget must be positive",
        ),
        _check(
            "client_buffer_rows_positive",
            config.max_local_buffer_rows,
            ">",
            0,
            config.max_local_buffer_rows > 0,
            "client local buffer row budget must be positive",
        ),
        _check(
            "dry_run_only",
            config.dry_run,
            "is",
            True,
            config.dry_run,
            "provider client packet is dry-run only until provider API and credentials are approved",
        ),
    ]


def _summary(
    fetcher_plan_path: Path,
    fetcher_config: dict[str, Any],
    config: ProviderMarketDataClientConfig,
    checks: pd.DataFrame,
    ready: bool,
    packet: dict[str, Any],
    output_schema: pd.DataFrame,
) -> pd.DataFrame:
    template = _request_template(fetcher_config)
    fetch_plan = _mapping(fetcher_config.get("fetch_plan"))
    authentication = _mapping(template.get("authentication"))
    credential_env_template = _mapping(authentication.get("env_template"))
    live_fetch_contract = _mapping(fetch_plan.get("live_fetch_contract"))
    output = _mapping(template.get("output"))
    env_vars = _string_list(authentication.get("env_vars"))
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "fetcher_plan_path": str(fetcher_plan_path),
                "provider": _text(template.get("provider")),
                "adapter": _text(template.get("adapter")),
                "kind": _text(template.get("kind")),
                "transport": _text(template.get("transport")),
                "template_kind": _text(template.get("template_kind")),
                "mode": _text(template.get("mode")),
                "market": _text(template.get("market")),
                "endpoint": _text(template.get("endpoint")),
                "output_filename": _text(output.get("filename")),
                "output_schema_columns": ";".join(output_schema["column"].astype(str).tolist())
                if not output_schema.empty
                else "",
                "output_schema_column_count": int(len(output_schema)),
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
                "session_label": config.session_label,
                "max_clock_skew_ms": int(config.max_clock_skew_ms),
                "max_local_buffer_rows": int(config.max_local_buffer_rows),
                "dry_run": bool(config.dry_run),
                "packet_execution_mode": _text(packet.get("execution_mode")),
                "failed_checks": failed_checks,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                )
                if not checks.empty
                else "",
                "recommendation": "provider_market_data_client_packet_ready"
                if ready
                else "fix_provider_market_data_client_packet",
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
                "template_kind": str(summary["template_kind"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
            }
        )
    if not rows and bool(summary["ready"]):
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "approve_provider_market_data_live_run",
                "reason": "provider client dry-run packet is ready for credentialed execution review",
                "provider": str(summary["provider"]),
                "transport": str(summary["transport"]),
                "template_kind": str(summary["template_kind"]),
                "next_gate": "provider_fetcher_live_run",
                "next_gate_help_command": "run provider client only after provider API and credential approval",
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
            "template_kind",
            "next_gate",
            "next_gate_help_command",
        ],
    )


def _config(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    fetcher_config: dict[str, Any],
    config: ProviderMarketDataClientConfig,
    packet: dict[str, Any],
    output_schema: pd.DataFrame,
) -> dict[str, Any]:
    failed_checks = _failed_checks(checks)
    ready_actions = _queue_records(action_queue, "ready")
    blocked_actions = _queue_records(action_queue, "blocked")
    next_action = _first_record(action_queue)
    template = _request_template(fetcher_config)
    env_vars = _string_list(_mapping(template.get("authentication")).get("env_vars"))
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "fetcher_plan": {
            "path": str(summary["fetcher_plan_path"]),
            "ready": bool(fetcher_config.get("ready")),
            "request_template": template,
            "credential_env_template": _credential_env_template_contract(summary),
            "live_fetch_contract": _mapping(_mapping(fetcher_config.get("fetch_plan")).get("live_fetch_contract")),
        },
        "client": {
            "dry_run": bool(config.dry_run),
            "require_env_present": bool(config.require_env_present),
            "session_label": config.session_label,
            "max_clock_skew_ms": int(config.max_clock_skew_ms),
            "max_local_buffer_rows": int(config.max_local_buffer_rows),
            "packet_file": "provider_market_data_client_packet.json",
            "output_schema_file": "provider_market_data_output_schema.csv",
        },
        "credentials": {
            "env_vars": env_vars,
            "env_presence": _env_presence(env_vars),
            "env_template": _credential_env_template_contract(summary),
            "values_stored": False,
        },
        "output_schema": _records(output_schema),
        "packet": packet,
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


def _client_packet(
    fetcher_config: dict[str, Any],
    config: ProviderMarketDataClientConfig,
    output_schema: pd.DataFrame,
    ready: bool,
) -> dict[str, Any]:
    template = _request_template(fetcher_config)
    authentication = _mapping(template.get("authentication"))
    output = _mapping(template.get("output"))
    runtime = _mapping(template.get("runtime"))
    env_vars = _string_list(authentication.get("env_vars"))
    return {
        "schema_version": 1,
        "ready": bool(ready),
        "execution_mode": "dry_run",
        "session_label": config.session_label,
        "provider": _text(template.get("provider")),
        "adapter": _text(template.get("adapter")),
        "market": _text(template.get("market")),
        "kind": _text(template.get("kind")),
        "transport": _text(template.get("transport")),
        "template_kind": _text(template.get("template_kind")),
        "endpoint": _text(template.get("endpoint")),
        "request": _request_payload(template),
        "authentication": {
            "env_vars": env_vars,
            "env_presence": _env_presence(env_vars),
            "env_template": _mapping(authentication.get("env_template")),
            "values_stored": False,
            "injection": _text(authentication.get("injection")),
        },
        "runtime": {
            "connect_timeout_ms": _int(runtime.get("connect_timeout_ms")),
            "read_timeout_ms": _int(runtime.get("read_timeout_ms")),
            "heartbeat_timeout_ms": _int(runtime.get("heartbeat_timeout_ms")),
            "max_reconnects": _int(runtime.get("max_reconnects")),
            "batch_size": _int(runtime.get("batch_size")),
            "max_clock_skew_ms": int(config.max_clock_skew_ms),
            "max_local_buffer_rows": int(config.max_local_buffer_rows),
        },
        "output": {
            "filename": _text(output.get("filename")),
            "format": _text(output.get("format")),
            "schema_columns": output_schema["column"].astype(str).tolist() if not output_schema.empty else [],
        },
        "live_execution_gate": {
            "requires_api_contract_approval": True,
            "requires_credentials": True,
            "requires_provider_session": True,
        },
    }


def _request_payload(template: dict[str, Any]) -> dict[str, Any]:
    transport = _text(template.get("transport"))
    if transport == "rest":
        return {
            "method": _text(template.get("method")),
            "query": _mapping(template.get("query")),
        }
    if transport == "websocket":
        return {
            "subscriptions": _list(template.get("subscriptions")),
        }
    return {}


def _output_schema(template: dict[str, Any]) -> pd.DataFrame:
    kind = _text(template.get("kind"))
    if kind == "ticks":
        columns = list(NORMALIZED_TICK_COLUMNS)
    elif kind == "chain":
        columns = list(NORMALIZED_CHAIN_COLUMNS)
    else:
        columns = []
    return pd.DataFrame(
        [
            {
                "position": index + 1,
                "column": column,
                "required": True,
                "source": "normalized_adapter_schema",
            }
            for index, column in enumerate(columns)
        ],
        columns=["position", "column", "required", "source"],
    )


def _request_template(fetcher_config: dict[str, Any]) -> dict[str, Any]:
    return _mapping(fetcher_config.get("request_template"))


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Client Dry-Run Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Transport: {summary['transport']}",
        f"- Template: {summary['template_kind']}",
        f"- Kind: {summary['kind']}",
        f"- Market: {summary['market']}",
        f"- Output: {summary['output_filename']}",
        f"- Output schema columns: {summary['output_schema_columns']}",
        f"- Credential env vars: {summary['credential_env_vars'] or 'none'}",
        f"- Credential env vars present: {summary['credential_env_vars_present']}",
        f"- Credential env template: {summary['credential_env_template_path'] or 'missing'}",
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


def _template_kind_matches_transport(template_kind: str, transport: str) -> bool:
    if transport == "rest":
        return template_kind == "rest_backfill_request"
    if transport == "websocket":
        return template_kind == "websocket_subscription"
    return False


def _blocked_next_gate(check: str) -> str:
    if check.startswith("fetcher_plan") or check in {
        "request_template_ready",
        "provider_supported",
        "transport_is_live",
        "template_kind_matches_transport",
        "endpoint_present",
        "endpoint_not_censored",
        "credential_values_not_stored",
        "credential_env_vars_present",
        "credential_env_vars_are_names",
        "credential_env_template_carried",
        "source_live_fetch_contract_carried",
        "output_format_normalized_csv",
        "output_filename_safe",
        "output_schema_known",
        "rest_template_has_query",
        "websocket_template_has_subscriptions",
    }:
        return "plan-provider-market-data-fetcher"
    return "prepare-provider-market-data-client"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate == "plan-provider-market-data-fetcher":
        return "python -m hft_cli plan-provider-market-data-fetcher --help"
    if next_gate == "prepare-provider-market-data-client":
        return "python -m hft_cli prepare-provider-market-data-client --help"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("fetcher_plan") or check.startswith("request_template"):
        return "repair_or_regenerate_provider_fetcher_plan"
    if check in {"provider_supported", "transport_is_live", "template_kind_matches_transport"}:
        return "select_supported_live_provider_fetcher_plan"
    if check.startswith("endpoint"):
        return "repair_provider_endpoint_contract"
    if check == "credential_env_template_carried":
        return "regenerate_provider_fetcher_with_credential_env_template"
    if check.startswith("credential"):
        return "provide_runtime_credential_environment_variables"
    if check == "source_live_fetch_contract_carried":
        return "regenerate_provider_fetcher_with_source_live_fetch_contract"
    if check.startswith("output"):
        return "repair_provider_output_contract"
    if check.startswith("rest") or check.startswith("websocket"):
        return "repair_provider_request_template"
    if check.startswith("runtime") or check.startswith("client"):
        return "set_valid_provider_client_runtime_budget"
    if check == "dry_run_only":
        return "keep_provider_client_packet_in_dry_run"
    return "repair_provider_market_data_client_packet"


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


def _credential_env_template_from_client_config(client_config: dict[str, Any]) -> dict[str, Any]:
    credentials = _mapping(client_config.get("credentials"))
    env_template = _mapping(credentials.get("env_template"))
    return {
        "path": _text(env_template.get("path")),
        "exists": bool(env_template.get("exists")),
        "sha256": _text(env_template.get("sha256")),
    }


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


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


def _int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(fallback)


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
