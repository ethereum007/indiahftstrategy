from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from adapters.broker import get_adapter
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES, MARKET_PROFILES
from reports.manifest import file_sha256, write_experiment_manifest


PROVIDER_SPECS: dict[str, dict[str, object]] = {
    "file_replay": {
        "adapter": "normalized",
        "transports": ("file",),
        "auth_required": False,
        "capabilities": ("historical_replay",),
    },
    "arrow_money": {
        "adapter": "arrow_money",
        "transports": ("file", "rest", "websocket"),
        "auth_required": True,
        "capabilities": ("historical_batch", "live_ticks", "option_chain"),
    },
    "irage": {
        "adapter": "irage",
        "transports": ("file", "rest", "websocket"),
        "auth_required": True,
        "capabilities": ("historical_batch", "live_ticks", "option_chain"),
    },
}

SUPPORTED_KINDS = ("ticks", "chain")
SUPPORTED_TRANSPORTS = ("file", "rest", "websocket")
SECRET_QUERY_KEYS = {"api_key", "apikey", "key", "secret", "token", "access_token", "password"}
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
ENV_TEMPLATE_NAME = "market_data_source_env_template.env"
DEFAULT_EXCHANGE = "NFO"


@dataclass(frozen=True)
class MarketDataSourceConfig:
    provider: str = "file_replay"
    adapter: str = ""
    kind: str = "ticks"
    transport: str = "file"
    source_uri: str = ""
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    exchange: str = DEFAULT_EXCHANGE
    session_timezone: str = ""
    session_open: str = ""
    session_close: str = ""
    auth_env_vars: tuple[str, ...] = ()
    label: str = ""


@dataclass(frozen=True)
class MarketDataSourceReport:
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


def evaluate_market_data_source(
    config: MarketDataSourceConfig | None = None,
) -> MarketDataSourceReport:
    config = config or MarketDataSourceConfig()
    normalized = _normalize_config(config)
    checks = pd.DataFrame(_checks(normalized))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    summary = _summary(normalized, checks, ready)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, action_queue)
    plan_config = _config(summary.iloc[0], checks, action_queue, normalized)
    return MarketDataSourceReport(checks, summary, action_queue, plan_config)


def write_market_data_source_plan(
    output_dir: str | Path,
    *,
    config: MarketDataSourceConfig | None = None,
) -> MarketDataSourceReport:
    report = evaluate_market_data_source(config)
    normalized = _normalize_config(config or MarketDataSourceConfig())
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / "market_data_source_checks.csv", index=False)
    report.summary.to_csv(out / "market_data_source_summary.csv", index=False)
    report.action_queue.to_csv(out / "market_data_source_action_queue.csv", index=False)
    (out / "market_data_source_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / ENV_TEMPLATE_NAME).write_text(
        _env_template(normalized.auth_env_vars),
        encoding="utf-8",
    )
    (out / "market_data_source_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.action_queue),
        encoding="utf-8",
    )
    inputs = {}
    source_path = _source_path(normalized)
    if source_path is not None and source_path.exists():
        inputs["source_file"] = source_path
    write_experiment_manifest(
        out,
        run_type="market_data_source_plan",
        parameters={"config": asdict(normalized)},
        inputs=inputs,
        extra={
            "source": report.config["source"],
            "credential_env_template_file": ENV_TEMPLATE_NAME,
            "live_fetch_contract": report.config["live_fetch_contract"],
        },
    )
    return MarketDataSourceReport(report.checks, report.summary, report.action_queue, report.config, out)


def _normalize_config(config: MarketDataSourceConfig) -> MarketDataSourceConfig:
    provider = _identity_key(config.provider) or "file_replay"
    provider_spec = PROVIDER_SPECS.get(provider, {})
    default_adapter = str(provider_spec.get("adapter", provider))
    adapter = _identity_key(config.adapter) or default_adapter
    market = _identity_key(config.market) or INDIA_NSE_INDEX_DERIVATIVES.name
    profile = MARKET_PROFILES.get(market, INDIA_NSE_INDEX_DERIVATIVES)
    return MarketDataSourceConfig(
        provider=provider,
        adapter=adapter,
        kind=_identity_key(config.kind) or "ticks",
        transport=_identity_key(config.transport) or "file",
        source_uri=str(config.source_uri or "").strip(),
        market=market,
        exchange=_exchange_key(config.exchange) or DEFAULT_EXCHANGE,
        session_timezone=str(config.session_timezone or profile.session.timezone).strip(),
        session_open=_session_hhmmss(config.session_open, _seconds_to_hhmmss(profile.session.open_seconds)),
        session_close=_session_hhmmss(config.session_close, _seconds_to_hhmmss(profile.session.close_seconds)),
        auth_env_vars=tuple(_normalize_auth_envs(config.auth_env_vars)),
        label=str(config.label or "").strip(),
    )


def _checks(config: MarketDataSourceConfig) -> list[dict[str, Any]]:
    provider_spec = PROVIDER_SPECS.get(config.provider)
    known_provider = provider_spec is not None
    known_adapter = _adapter_known(config.adapter)
    source_present = bool(config.source_uri)
    source_kind = _source_kind(config)
    file_path = _source_path(config)
    file_exists = bool(file_path is not None and file_path.exists())
    transport_allowed = bool(
        known_provider and config.transport in tuple(provider_spec.get("transports", ()))  # type: ignore[union-attr]
    )
    auth_required = bool(provider_spec.get("auth_required", False)) if provider_spec else False
    auth_envs_valid = all(_auth_env_name_valid(value) for value in config.auth_env_vars)
    query_secret_keys = _secret_query_keys(config.source_uri)
    session_open_valid = _hhmmss_seconds(config.session_open) is not None
    session_close_valid = _hhmmss_seconds(config.session_close) is not None
    return [
        _check(
            "provider_known",
            config.provider,
            "in",
            sorted(PROVIDER_SPECS),
            known_provider,
            "market-data provider is not registered",
        ),
        _check(
            "adapter_known",
            config.adapter,
            "in",
            "adapters.broker.ADAPTERS",
            known_adapter,
            "market-data adapter is not registered",
        ),
        _check(
            "provider_adapter_matches",
            config.adapter,
            "==",
            str(provider_spec.get("adapter", config.adapter)) if provider_spec else config.provider,
            _provider_adapter_matches(config, provider_spec),
            "provider should use its matching adapter unless this is file_replay",
        ),
        _check(
            "kind_supported",
            config.kind,
            "in",
            SUPPORTED_KINDS,
            config.kind in SUPPORTED_KINDS,
            "market-data source kind must be ticks or chain",
        ),
        _check(
            "transport_supported",
            config.transport,
            "in",
            SUPPORTED_TRANSPORTS,
            config.transport in SUPPORTED_TRANSPORTS,
            "market-data transport is unsupported",
        ),
        _check(
            "provider_transport_allowed",
            config.transport,
            "in",
            tuple(provider_spec.get("transports", ())) if provider_spec else (),
            transport_allowed,
            "provider does not support the selected transport",
        ),
        _check(
            "source_uri_present",
            source_present,
            "is",
            True,
            source_present,
            "market-data source URI or file path is required",
        ),
        _check(
            "exchange_present",
            config.exchange,
            "is_not",
            "",
            bool(config.exchange),
            "exchange or segment code is required for provider handoff",
        ),
        _check(
            "session_timezone_known",
            config.session_timezone,
            "known",
            "IANA timezone",
            _timezone_known(config.session_timezone),
            "session timezone must be a valid IANA timezone such as Asia/Kolkata",
        ),
        _check(
            "session_open_shape",
            config.session_open,
            "matches",
            "HH:MM:SS",
            session_open_valid,
            "session open must be HH:MM:SS",
        ),
        _check(
            "session_close_shape",
            config.session_close,
            "matches",
            "HH:MM:SS",
            session_close_valid,
            "session close must be HH:MM:SS",
        ),
        _check(
            "session_window_order",
            f"{config.session_open}..{config.session_close}",
            "<",
            "close after open",
            _session_window_order_valid(config.session_open, config.session_close),
            "session close must be after session open",
        ),
        _check(
            "source_uri_shape",
            source_kind,
            "matches",
            "file path for file transport, URL for rest/websocket",
            _source_shape_valid(config, source_kind),
            "source URI shape does not match the selected transport",
        ),
        _check(
            "source_file_exists",
            file_exists,
            "is",
            True,
            file_exists if config.transport == "file" else True,
            "file transport requires an existing market-data source file",
        ),
        _check(
            "auth_env_vars_present",
            len(config.auth_env_vars),
            ">=",
            1 if auth_required and config.transport != "file" else 0,
            (len(config.auth_env_vars) >= 1) if auth_required and config.transport != "file" else True,
            "live provider transports require credential environment variable names",
        ),
        _check(
            "auth_env_vars_are_names",
            ",".join(config.auth_env_vars),
            "matches",
            "UPPER_SNAKE_CASE names without values",
            auth_envs_valid,
            "credential inputs must be environment variable names, not secret values",
        ),
        _check(
            "source_uri_has_no_secret_query",
            ",".join(query_secret_keys),
            "is",
            "",
            not query_secret_keys,
            "source URI must not embed tokens, keys, passwords, or secrets",
        ),
    ]


def _summary(config: MarketDataSourceConfig, checks: pd.DataFrame, ready: bool) -> pd.DataFrame:
    source_kind = _source_kind(config)
    source_path = _source_path(config)
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider": config.provider,
                "adapter": config.adapter,
                "kind": config.kind,
                "transport": config.transport,
                "market": config.market,
                "exchange": config.exchange,
                "session_timezone": config.session_timezone,
                "session_open_local": config.session_open,
                "session_close_local": config.session_close,
                "label": config.label,
                "source_uri": _sanitize_uri(config.source_uri),
                "source_uri_kind": source_kind,
                "source_file_exists": bool(source_path is not None and source_path.exists()),
                "source_file_sha256": file_sha256(source_path)
                if source_path is not None and source_path.exists() and source_path.is_file()
                else "",
                "auth_env_var_count": int(len(config.auth_env_vars)),
                "auth_env_vars": ";".join(config.auth_env_vars),
                "credential_env_template_file": ENV_TEMPLATE_NAME,
                "live_fetch_contract_available": bool(ready and config.transport in {"rest", "websocket"}),
                "live_fetch_contract_command": _live_fetch_contract_command(config, ready),
                "failed_checks": failed_checks,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                )
                if not checks.empty
                else "",
                "recommendation": "market_data_source_ready" if ready else "fix_market_data_source_plan",
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
                "next_gate": "plan-market-data-source",
                "next_gate_help_command": "python -m hft_cli plan-market-data-source --help",
            }
        )
    if not rows and bool(summary["ready"]):
        next_gate = "pipeline-vendor-market-data" if str(summary["transport"]) == "file" else "provider_fetcher"
        help_command = (
            "python -m hft_cli pipeline-vendor-market-data --help"
            if next_gate == "pipeline-vendor-market-data"
            else "wire provider fetcher with market_data_source_config.json"
        )
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "run_vendor_market_data_pipeline"
                if next_gate == "pipeline-vendor-market-data"
                else "wire_provider_market_data_fetcher",
                "reason": "market-data source plan is ready",
                "provider": str(summary["provider"]),
                "adapter": str(summary["adapter"]),
                "kind": str(summary["kind"]),
                "transport": str(summary["transport"]),
                "next_gate": next_gate,
                "next_gate_help_command": help_command,
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
            "next_gate",
            "next_gate_help_command",
        ],
    )


def _config(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: MarketDataSourceConfig,
) -> dict[str, Any]:
    failed_checks = _failed_checks(checks)
    ready_actions = _queue_records(action_queue, "ready")
    blocked_actions = _queue_records(action_queue, "blocked")
    next_action = _first_record(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
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
        "label": str(summary["label"]),
        "source": {
            "uri": str(summary["source_uri"]),
            "uri_kind": str(summary["source_uri_kind"]),
            "file_exists": bool(summary["source_file_exists"]),
            "file_sha256": str(summary["source_file_sha256"]),
        },
        "credentials": {
            "env_vars": list(config.auth_env_vars),
            "env_template_file": ENV_TEMPLATE_NAME,
            "env_template_entry_count": int(len(config.auth_env_vars)),
            "values_stored": False,
        },
        "capabilities": list(PROVIDER_SPECS.get(config.provider, {}).get("capabilities", ())),
        "normalized_pipeline": _normalized_pipeline(summary),
        "live_fetch_contract": _live_fetch_contract(summary),
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


def _normalized_pipeline(summary: pd.Series) -> dict[str, Any]:
    if str(summary["transport"]) != "file" or not bool(summary["ready"]):
        return {
            "available": False,
            "next_gate": "",
            "command": "",
        }
    output_dir = f"runs/vendor_market_data/{summary['provider']}_{summary['kind']}"
    return {
        "available": True,
        "next_gate": "pipeline-vendor-market-data",
        "command": (
            "python -m hft_cli pipeline-vendor-market-data "
            f"--input {_shell_quote(summary['source_uri'])} "
            f"--out {_shell_quote(output_dir)} "
            f"--adapter {summary['adapter']} "
            f"--kind {summary['kind']} "
            f"--market {summary['market']}"
        ),
    }


def _live_fetch_contract(summary: pd.Series) -> dict[str, Any]:
    available = bool(summary["ready"]) and str(summary["transport"]) in {"rest", "websocket"}
    if not available:
        return {
            "available": False,
            "next_gate": "",
            "command_template": "",
            "required_inputs": [],
            "credential_env_template_file": ENV_TEMPLATE_NAME,
            "exchange": str(summary.get("exchange", "")),
            "market": str(summary.get("market", "")),
            "session": {
                "timezone": str(summary.get("session_timezone", "")),
                "open_local": str(summary.get("session_open_local", "")),
                "close_local": str(summary.get("session_close_local", "")),
            },
        }
    required_inputs = ["symbol"]
    if str(summary["transport"]) == "rest":
        required_inputs.extend(["window_start", "window_end"])
    return {
        "available": True,
        "next_gate": "provider_fetcher",
        "command_template": str(summary["live_fetch_contract_command"]),
        "required_inputs": required_inputs,
        "credential_env_template_file": ENV_TEMPLATE_NAME,
        "exchange": str(summary["exchange"]),
        "market": str(summary["market"]),
        "session": {
            "timezone": str(summary["session_timezone"]),
            "open_local": str(summary["session_open_local"]),
            "close_local": str(summary["session_close_local"]),
        },
    }


def _live_fetch_contract_command(config: MarketDataSourceConfig, ready: bool) -> str:
    if not ready or config.transport not in {"rest", "websocket"}:
        return ""
    output_dir = f"runs/market_data_fetch/{config.provider}_{config.kind}"
    parts = [
        "python -m hft_cli plan-market-data-fetch",
        "--source-plan market_data_source_config.json",
        f"--out {_shell_quote(output_dir)}",
        "--symbol <SYMBOL>",
    ]
    if config.transport == "rest":
        parts.extend(["--window-start <WINDOW_START_ISO>", "--window-end <WINDOW_END_ISO>"])
    parts.extend(
        [
            "--max-latency-ms 150",
            f"--expected-market {config.market}",
            "--fail-on-blocked-actions",
            "--fail-on-breach",
        ]
    )
    return " ".join(parts)


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Market Data Source Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Adapter: {summary['adapter']}",
        f"- Kind: {summary['kind']}",
        f"- Transport: {summary['transport']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange']}",
        f"- Session: {summary['session_open_local']} - {summary['session_close_local']} {summary['session_timezone']}",
        f"- Source: {summary['source_uri']}",
        f"- Credential env vars: {summary['auth_env_vars'] or 'none'}",
    ]
    lines.append(f"- Credential env template: {summary['credential_env_template_file']}")
    if str(summary["live_fetch_contract_command"]):
        lines.append(f"- Live fetch contract command: `{summary['live_fetch_contract_command']}`")
    lines.extend(["", "## Actions"])
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
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _provider_adapter_matches(
    config: MarketDataSourceConfig,
    provider_spec: dict[str, object] | None,
) -> bool:
    if config.provider == "file_replay":
        return True
    if provider_spec is None:
        return False
    return config.adapter == str(provider_spec.get("adapter", config.provider))


def _adapter_known(adapter: str) -> bool:
    try:
        get_adapter(adapter)
    except ValueError:
        return False
    return True


def _source_shape_valid(config: MarketDataSourceConfig, source_kind: str) -> bool:
    if not config.source_uri:
        return False
    if config.transport == "file":
        return source_kind == "file"
    if config.transport == "rest":
        return source_kind in {"http", "https"}
    if config.transport == "websocket":
        return source_kind in {"ws", "wss"}
    return False


def _source_kind(config: MarketDataSourceConfig) -> str:
    if not config.source_uri:
        return ""
    if _is_windows_path(config.source_uri):
        return "file"
    split = urlsplit(config.source_uri)
    if split.scheme:
        return split.scheme.lower()
    return "file"


def _source_path(config: MarketDataSourceConfig) -> Path | None:
    if config.transport != "file" or not config.source_uri:
        return None
    if urlsplit(config.source_uri).scheme and not _is_windows_path(config.source_uri):
        return None
    return Path(config.source_uri)


def _sanitize_uri(value: str) -> str:
    if not value:
        return ""
    if _is_windows_path(value):
        return value
    split = urlsplit(value)
    if not split.scheme or not split.query:
        return value
    pairs = []
    for key, item in parse_qsl(split.query, keep_blank_values=True):
        pairs.append((key, "***" if key.lower() in SECRET_QUERY_KEYS else item))
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(pairs), split.fragment))


def _secret_query_keys(value: str) -> list[str]:
    if not value:
        return []
    if _is_windows_path(value):
        return []
    split = urlsplit(value)
    if not split.query:
        return []
    return sorted({key.lower() for key, _ in parse_qsl(split.query) if key.lower() in SECRET_QUERY_KEYS})


def _is_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value))


def _normalize_auth_envs(values: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def _auth_env_name_valid(value: str) -> bool:
    return bool(ENV_NAME_RE.match(value)) and "=" not in value


def _env_template(env_vars: tuple[str, ...]) -> str:
    return "".join(f"{env_var}=\n" for env_var in env_vars)


def _repair_action(check: str) -> str:
    if check.startswith("source_"):
        return "fix_market_data_source_uri"
    if check.startswith("session_") or check.startswith("exchange_"):
        return "fix_market_session_metadata"
    if check.startswith("auth_"):
        return "provide_credential_environment_variable_names"
    if check.startswith("provider"):
        return "select_supported_provider_adapter_transport"
    if check == "kind_supported":
        return "select_supported_market_data_kind"
    return "repair_market_data_source_plan"


def _shell_quote(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"' if re.search(r"\s", escaped) else escaped


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


def _identity_key(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text.lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _exchange_key(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text.upper().replace("-", "_").replace(" ", "_").replace(".", "_")


def _seconds_to_hhmmss(value: int) -> str:
    hour, remainder = divmod(int(value), 3600)
    minute, second = divmod(remainder, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _session_hhmmss(value: object, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _hhmmss_seconds(value: str) -> int | None:
    parts = str(value or "").split(":")
    if len(parts) != 3:
        return None
    try:
        hour, minute, second = (int(part) for part in parts)
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour * 3600 + minute * 60 + second


def _session_window_order_valid(open_time: str, close_time: str) -> bool:
    open_seconds = _hhmmss_seconds(open_time)
    close_seconds = _hhmmss_seconds(close_time)
    return open_seconds is not None and close_seconds is not None and open_seconds < close_seconds


def _timezone_known(value: str) -> bool:
    if not value:
        return False
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return False
    return True


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, tuple):
        return list(value)
    return value
