from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.broker_dispatch_send import (
    BrokerDispatchSendReport,
    BrokerDispatchSendThresholds,
    write_broker_dispatch_send_packet,
)
from reports.manifest import write_experiment_manifest


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_broker_dispatch_send"

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchSendConfig:
    require_provider_broker_dispatch_ready: bool = True
    require_broker_dispatch_send_ready: bool = True
    use_provider_broker_dispatch_inputs: bool = True
    target_mode: str = ""
    require_dispatch_ready: bool = True
    require_armed_dispatch: bool = True
    require_dry_run: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    max_requests: int | None = None


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchSendReport:
    broker_dispatch_send: BrokerDispatchSendReport | None
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


def write_provider_market_data_imbalance_broker_dispatch_send(
    provider_broker_dispatch_dir: str | Path,
    output_dir: str | Path,
    *,
    broker_dispatch_dir: str | Path | None = None,
    config: ProviderMarketDataImbalanceBrokerDispatchSendConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerDispatchSendReport:
    config = config or ProviderMarketDataImbalanceBrokerDispatchSendConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    provider_root = Path(provider_broker_dispatch_dir)
    provider_summary, provider_summary_error = _read_csv(
        provider_root / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_root / "provider_market_data_imbalance_broker_dispatch_config.json"
    )
    resolved_broker_dispatch_dir = _explicit_or_inferred(
        broker_dispatch_dir,
        _inferred_broker_dispatch_dir(provider_summary, provider_config),
        config,
    )
    inferred_provider_dispatch_roundtrip_dir, inferred_dispatch_roundtrip_dir = _inferred_dispatch_roundtrip_dirs(
        provider_summary,
        provider_config,
    )

    prechecks = _prechecks(
        provider_root,
        provider_summary,
        provider_summary_error,
        provider_config_error,
        resolved_broker_dispatch_dir,
        config,
    )

    broker_dispatch_send: BrokerDispatchSendReport | None = None
    broker_dispatch_send_error = ""
    broker_dispatch_send_dir = out / "broker_dispatch_send"
    if bool(prechecks["passed"].all()):
        try:
            broker_dispatch_send = write_broker_dispatch_send_packet(
                dispatch_dir=_path_or_empty(resolved_broker_dispatch_dir),
                output_dir=broker_dispatch_send_dir,
                thresholds=_thresholds(config, provider_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError, json.JSONDecodeError) as exc:
            broker_dispatch_send_error = str(exc)
    else:
        broker_dispatch_send_error = "provider imbalance broker-dispatch-send prerequisites are not ready"

    checks = _checks(prechecks, broker_dispatch_send, broker_dispatch_send_error, provider_summary, config)
    summary = _summary(
        provider_root,
        resolved_broker_dispatch_dir,
        inferred_provider_dispatch_roundtrip_dir,
        inferred_dispatch_roundtrip_dir,
        broker_dispatch_send,
        checks,
        out,
        broker_dispatch_send_dir,
        provider_summary,
    )
    action_queue = _action_queue(summary.iloc[0], checks, broker_dispatch_send)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        broker_dispatch_send,
        checks,
        action_queue,
        config,
        {
            "provider_broker_dispatch_dir": provider_root,
            "broker_dispatch_dir": resolved_broker_dispatch_dir,
            "provider_dispatch_roundtrip_dir": inferred_provider_dispatch_roundtrip_dir,
            "dispatch_roundtrip_dir": inferred_dispatch_roundtrip_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_broker_dispatch_send_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_broker_dispatch_send_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_broker_dispatch_send_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_broker_dispatch_send_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_dispatch_send_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_broker_dispatch_dir": provider_root}
    if resolved_broker_dispatch_dir is not None:
        inputs["broker_dispatch"] = Path(resolved_broker_dispatch_dir)
    if inferred_provider_dispatch_roundtrip_dir is not None:
        inputs["provider_dispatch_roundtrip"] = Path(inferred_provider_dispatch_roundtrip_dir)
    if inferred_dispatch_roundtrip_dir is not None:
        inputs["dispatch_roundtrip"] = Path(inferred_dispatch_roundtrip_dir)
    if broker_dispatch_send is not None and broker_dispatch_send.output_dir is not None:
        inputs["broker_dispatch_send"] = broker_dispatch_send.output_dir

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "broker_dispatch_send_inputs": _jsonable(payload["broker_dispatch_send_inputs"]),
        },
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "broker_dispatch_send_ready": bool(summary.iloc[0]["broker_dispatch_send_ready"]),
            "profile": PROFILE,
            "strategy": str(summary.iloc[0]["strategy"]),
            "market": str(summary.iloc[0]["market"]),
        },
    )
    return ProviderMarketDataImbalanceBrokerDispatchSendReport(
        broker_dispatch_send,
        checks,
        summary,
        action_queue,
        payload,
        out,
    )


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"{path.name} does not exist"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} is not readable: {exc}"
    return value if isinstance(value, dict) else {}, ""


def _prechecks(
    provider_root: Path,
    provider_summary: pd.DataFrame,
    provider_summary_error: str,
    provider_config_error: str,
    broker_dispatch_dir: Path | None,
    config: ProviderMarketDataImbalanceBrokerDispatchSendConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_broker_dispatch_dir_exists",
                str(provider_root),
                "exists",
                True,
                provider_root.exists(),
                "provider imbalance broker-dispatch directory is required",
            ),
            _check(
                "provider_broker_dispatch_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance broker-dispatch summary could not be read",
            ),
            _check(
                "provider_broker_dispatch_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider imbalance broker-dispatch config could not be read",
            ),
            _check(
                "provider_broker_dispatch_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_broker_dispatch_ready,
                "provider imbalance broker-dispatch wrapper is not ready",
            ),
            _check(
                "provider_nested_broker_dispatch_ready",
                _first_bool(provider_summary, "broker_dispatch_ready"),
                "is",
                True,
                _first_bool(provider_summary, "broker_dispatch_ready")
                or not config.require_provider_broker_dispatch_ready,
                "nested broker dispatch plan is not ready",
            ),
            _check(
                "generic_broker_dispatch_input_resolved",
                _path_text(broker_dispatch_dir),
                "present",
                True,
                bool(broker_dispatch_dir),
                "nested generic broker dispatch input is required for send packet",
            ),
            _check(
                "nested_broker_dispatch_config_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_config.json").exists()),
                "nested broker_dispatch_config.json is required for send packet",
            ),
            _check(
                "nested_broker_dispatch_summary_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_summary.csv").exists()),
                "nested broker_dispatch_summary.csv is required for send packet",
            ),
            _check(
                "nested_broker_dispatch_orders_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_orders.csv").exists()),
                "nested broker_dispatch_orders.csv is required for send packet",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    broker_dispatch_send: BrokerDispatchSendReport | None,
    broker_dispatch_send_error: str,
    provider_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchSendConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    send_summary = broker_dispatch_send.summary if broker_dispatch_send is not None else pd.DataFrame()
    rows.append(
        _check(
            "broker_dispatch_send_runnable",
            broker_dispatch_send_error or ("ran" if broker_dispatch_send is not None else "not_run"),
            "is",
            "ran",
            broker_dispatch_send is not None and not broker_dispatch_send_error,
            broker_dispatch_send_error or "generic broker dispatch send packet was not run",
        )
    )
    rows.append(
        _check(
            "broker_dispatch_send_ready",
            bool(broker_dispatch_send is not None and broker_dispatch_send.ready),
            "is",
            True,
            bool(
                broker_dispatch_send is not None
                and (broker_dispatch_send.ready or not config.require_broker_dispatch_send_ready)
            ),
            _broker_dispatch_send_failure_reason(broker_dispatch_send) or "broker dispatch send packet is not ready",
        )
    )
    strategy = _first_text(send_summary, "strategy") or _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            bool(broker_dispatch_send is not None) and _identity_key(strategy) == PROFILE,
            "broker dispatch send packet did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    send_market = _first_text(send_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            send_market or expected_market,
            "is",
            expected_market or "present",
            bool(broker_dispatch_send is not None)
            and (not expected_market or _identity_key(send_market) == _identity_key(expected_market)),
            "broker dispatch send market identity does not match provider dispatch",
        )
    )
    expected_adapter = _first_text(provider_summary, "adapter")
    send_adapter = _first_text(send_summary, "adapter")
    rows.append(
        _check(
            "adapter_identity_consistent",
            send_adapter or expected_adapter,
            "is",
            expected_adapter or "present",
            bool(broker_dispatch_send is not None)
            and (not expected_adapter or _identity_key(send_adapter) == _identity_key(expected_adapter)),
            "broker dispatch send adapter identity does not match provider dispatch",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    provider_root: Path,
    broker_dispatch_dir: Path | None,
    provider_dispatch_roundtrip_dir: Path | None,
    dispatch_roundtrip_dir: Path | None,
    broker_dispatch_send: BrokerDispatchSendReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    broker_dispatch_send_dir: Path,
    provider_summary: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    send_summary = broker_dispatch_send.summary if broker_dispatch_send is not None else pd.DataFrame()
    send_dir = (
        broker_dispatch_send_dir
        if broker_dispatch_send is None
        else Path(broker_dispatch_send.output_dir or broker_dispatch_send_dir)
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_broker_dispatch_ready": _first_bool(provider_summary, "ready"),
                "broker_dispatch_send_ready": bool(broker_dispatch_send is not None and broker_dispatch_send.ready),
                "provider_broker_dispatch_dir": str(provider_root),
                "broker_dispatch_dir": _path_text(broker_dispatch_dir),
                "provider_dispatch_roundtrip_dir": _path_text(provider_dispatch_roundtrip_dir),
                "dispatch_roundtrip_dir": _path_text(dispatch_roundtrip_dir),
                "dispatch_roundtrip_provided": _first_bool(provider_summary, "dispatch_roundtrip_provided"),
                "dispatch_roundtrip_ready": _first_bool(provider_summary, "dispatch_roundtrip_ready"),
                "dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "dispatch_roundtrip_failed_checks")
                ),
                "broker_dispatch_send_dir": str(send_dir),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(send_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(send_summary, "strategy")
                or _first_text(provider_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(send_summary, "target_mode")
                or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(send_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(send_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "route_state": _first_text(provider_summary, "route_state") or "disabled",
                "route_enabled": _first_bool(provider_summary, "route_enabled"),
                "dispatch_state": _first_text(provider_summary, "dispatch_state") or "disabled",
                "dispatch_batch_id": _first_text(send_summary, "dispatch_batch_id")
                or _first_text(provider_summary, "dispatch_batch_id"),
                "dispatch_orders": int(
                    _first_number(send_summary, "dispatch_orders")
                    or _first_number(provider_summary, "dispatch_orders")
                ),
                "dispatch_total_notional": float(
                    _first_number(send_summary, "dispatch_total_notional")
                    or _first_number(provider_summary, "dispatch_total_notional")
                ),
                "request_state": _first_text(send_summary, "request_state") or "disabled",
                "requests": int(_first_number(send_summary, "requests")),
                "dry_run_only": _first_bool(send_summary, "dry_run_only"),
                "submission_enabled": _first_bool(send_summary, "submission_enabled"),
                "route_readiness_required": _first_bool(send_summary, "route_readiness_required")
                or _first_bool(provider_summary, "route_readiness_required"),
                "route_readiness_ready": _first_bool(send_summary, "route_readiness_ready")
                or _first_bool(provider_summary, "route_readiness_ready"),
                "route_readiness_gap_pairs": int(
                    _first_number(send_summary, "route_readiness_gap_pairs")
                    or _first_number(provider_summary, "route_readiness_gap_pairs")
                ),
                "provider_broker_dispatch_recommendation": _first_text(
                    provider_summary, "broker_dispatch_recommendation"
                )
                or _first_text(provider_summary, "recommendation"),
                "broker_dispatch_send_recommendation": _first_text(send_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "capture_provider_imbalance_broker_acknowledgements"
                if ready
                else "repair_provider_imbalance_broker_dispatch_send",
                "next_gate": "reconcile-broker-dispatch"
                if ready
                else _blocked_next_gate(checks, broker_dispatch_send),
                "next_gate_help_command": _help_command_for_gate(
                    "reconcile-broker-dispatch" if ready else _blocked_next_gate(checks, broker_dispatch_send)
                ),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    if not action_queue.empty:
        out["primary_action_status"] = str(action_queue.iloc[0].get("queue_status", ""))
        out["next_gate"] = str(action_queue.iloc[0].get("next_gate", out.iloc[0].get("next_gate", "")))
        out["next_gate_help_command"] = str(
            action_queue.iloc[0].get("next_gate_help_command", out.iloc[0].get("next_gate_help_command", ""))
        )
    return out


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    broker_dispatch_send: BrokerDispatchSendReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_broker_dispatch_send_summary",
                    "component": "broker_dispatch_send",
                    "check": "broker_dispatch_send_ready",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "capture_provider_imbalance_broker_acknowledgements",
                    "reason": "provider imbalance non-submitting broker send packet is ready",
                    "recommendation": "capture_dry_run_broker_acks_then_reconcile",
                    "next_gate": "reconcile-broker-dispatch",
                    "next_gate_help_command": _help_command_for_gate("reconcile-broker-dispatch"),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, broker_dispatch_send)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_dispatch_send_checks",
                "component": _component_for_check(name),
                "check": name,
                "actual": check.get("value"),
                "operator": check.get("operator"),
                "expected": check.get("threshold"),
                "action": _action_for_check(name),
                "reason": str(check.get("reason", "")) or name.replace("_", " "),
                "recommendation": _recommendation_for_check(name),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_dispatch_send_checks",
                "component": "broker_dispatch_send",
                "check": "provider_broker_dispatch_send_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_broker_dispatch_send",
                "reason": "provider imbalance broker dispatch send wrapper is not ready",
                "recommendation": "rerun_provider_imbalance_broker_dispatch_send",
                "next_gate": "prepare-provider-market-data-imbalance-broker-dispatch-send",
                "next_gate_help_command": _help_command_for_gate(
                    "prepare-provider-market-data-imbalance-broker-dispatch-send"
                ),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    broker_dispatch_send: BrokerDispatchSendReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchSendConfig,
    broker_dispatch_send_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "broker_dispatch_send_inputs": _jsonable(broker_dispatch_send_inputs),
        "summary": _series_record(summary),
        "provider_broker_dispatch": _first_record(provider_summary),
        "provider_broker_dispatch_config": provider_config,
        "broker_dispatch_send": {
            "evaluated": broker_dispatch_send is not None,
            "ready": False if broker_dispatch_send is None else bool(broker_dispatch_send.ready),
            "output_dir": "" if broker_dispatch_send is None else str(broker_dispatch_send.output_dir or ""),
            "requests": _records(None if broker_dispatch_send is None else broker_dispatch_send.requests),
            "expected_acks": _records(None if broker_dispatch_send is None else broker_dispatch_send.expected_acks),
            "summary": _first_record(None if broker_dispatch_send is None else broker_dispatch_send.summary),
            "checks": _records(None if broker_dispatch_send is None else broker_dispatch_send.checks),
            "action_queue": _records(None if broker_dispatch_send is None else broker_dispatch_send.action_queue),
            "config": {}
            if broker_dispatch_send is None or broker_dispatch_send.config is None
            else broker_dispatch_send.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Broker Dispatch Send",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Target mode: {summary['target_mode']}",
        f"- Request state: {summary['request_state']}",
        f"- Requests: {summary['requests']}",
        f"- Submission enabled: {'yes' if bool(summary['submission_enabled']) else 'no'}",
        f"- Broker dispatch send dir: {summary['broker_dispatch_send_dir']}",
        f"- Dispatch round-trip ready: {'yes' if bool(summary['dispatch_roundtrip_ready']) else 'no'}",
        f"- Dispatch round-trip dir: {summary['dispatch_roundtrip_dir']}",
        f"- Primary next gate: `{summary['next_gate']}`",
        f"- Primary next gate help: `{summary['next_gate_help_command']}`",
        "",
        "## Checks",
        "",
        _checks_table(checks),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _thresholds(
    config: ProviderMarketDataImbalanceBrokerDispatchSendConfig,
    provider_summary: pd.DataFrame,
) -> BrokerDispatchSendThresholds:
    return BrokerDispatchSendThresholds(
        target_mode=config.target_mode or _first_text(provider_summary, "target_mode") or "live_dryrun",
        require_dispatch_ready=config.require_dispatch_ready,
        require_armed_dispatch=config.require_armed_dispatch,
        require_dry_run=config.require_dry_run,
        require_route_readiness=config.require_route_readiness,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        max_requests=config.max_requests,
    )


def _broker_dispatch_send_failure_reason(broker_dispatch_send: BrokerDispatchSendReport | None) -> str:
    if broker_dispatch_send is None or broker_dispatch_send.checks.empty:
        return ""
    failed = broker_dispatch_send.checks.loc[~broker_dispatch_send.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame, broker_dispatch_send: BrokerDispatchSendReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "prepare-provider-market-data-imbalance-broker-dispatch-send"
    return _next_gate_for_check(failed[0], broker_dispatch_send)


def _next_gate_for_check(check: str, broker_dispatch_send: BrokerDispatchSendReport | None) -> str:
    if check.startswith("provider_broker_dispatch") or check.startswith("generic_broker_dispatch"):
        return "plan-provider-market-data-imbalance-broker-dispatch"
    if check.startswith("nested_broker_dispatch"):
        return "plan-provider-market-data-imbalance-broker-dispatch"
    if check == "broker_dispatch_send_ready" and broker_dispatch_send is not None:
        next_gate = _first_action_value(broker_dispatch_send.action_queue, "next_gate")
        return next_gate or "prepare-broker-dispatch-send"
    if check.startswith("broker_dispatch_send"):
        return "prepare-broker-dispatch-send"
    if check in {"strategy_identity_imbalance", "market_identity_consistent", "adapter_identity_consistent"}:
        return "plan-provider-market-data-imbalance-broker-dispatch"
    return "prepare-provider-market-data-imbalance-broker-dispatch-send"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "plan-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "prepare-provider-market-data-imbalance-broker-dispatch-send":
        return "python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send --help"
    if next_gate == "plan-broker-dispatch":
        return "python -m hft_cli plan-broker-dispatch --help"
    if next_gate == "prepare-broker-dispatch-send":
        return "python -m hft_cli prepare-broker-dispatch-send --help"
    if next_gate == "reconcile-broker-dispatch":
        return "python -m hft_cli reconcile-broker-dispatch --help"
    if next_gate == "review-route-readiness":
        return "python -m hft_cli review-route-readiness --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    if next_gate == "review-broker-dispatch-roundtrip":
        return "python -m hft_cli review-broker-dispatch-roundtrip --help"
    if next_gate == "pipeline-vendor-market-data-batch":
        return "python -m hft_cli pipeline-vendor-market-data-batch --help"
    if next_gate == "pipeline-broker-vendor-readiness":
        return "python -m hft_cli pipeline-broker-vendor-readiness --help"
    if next_gate == "review-resume-gate":
        return "python -m hft_cli review-resume-gate --help"
    if next_gate == "review-broker-readiness":
        return "python -m hft_cli review-broker-readiness --help"
    return "python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch"):
        return "provider_broker_dispatch"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "broker_dispatch"
    if check.startswith("broker_dispatch_send"):
        return "broker_dispatch_send"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_broker_dispatch_send"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch"):
        return "repair_provider_imbalance_broker_dispatch"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "repair_provider_imbalance_broker_dispatch_inputs"
    if check.startswith("broker_dispatch_send"):
        return "repair_broker_dispatch_send_packet"
    return "repair_provider_imbalance_broker_dispatch_send"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch"):
        return "rerun_provider_broker_dispatch_before_send_packet"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "rerun_provider_broker_dispatch_to_refresh_nested_dispatch_artifacts"
    if check.startswith("broker_dispatch_send"):
        return "rerun_generic_broker_dispatch_send_with_required_artifacts"
    return "repair_provider_broker_dispatch_send_inputs"


def _inferred_broker_dispatch_dir(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> Path | None:
    dispatch_config = provider_config.get("broker_dispatch", {}) or {}
    return _first_existing_path(
        _path_from_text(_first_text(provider_summary, "broker_dispatch_dir")),
        _path_from_text(dispatch_config.get("output_dir")),
    )


def _inferred_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    broker_dispatch_inputs = provider_config.get("broker_dispatch_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "provider_dispatch_roundtrip_dir")),
        _path_from_text(broker_dispatch_inputs.get("provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "dispatch_roundtrip_dir")),
        _path_from_text(broker_dispatch_inputs.get("dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred: Path | None,
    config: ProviderMarketDataImbalanceBrokerDispatchSendConfig,
) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    if not config.use_provider_broker_dispatch_inputs:
        return None
    return inferred


def _first_action_value(action_queue: pd.DataFrame | None, column: str) -> str:
    if action_queue is None or action_queue.empty or column not in action_queue.columns:
        return ""
    for value in action_queue[column].tolist():
        text = _clean(value)
        if text:
            return text
    return ""


def _checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "_None_"
    rows = [
        [
            str(row.get("check", "")),
            "pass" if _truthy(row.get("passed")) else "fail",
            str(row.get("value", "")),
            str(row.get("threshold", "")),
            str(row.get("reason", "")),
        ]
        for row in checks.to_dict(orient="records")
    ]
    return _markdown_table(["Check", "Status", "Value", "Threshold", "Reason"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(row.get("priority", "")),
            str(row.get("queue_status", "")),
            str(row.get("action", "")),
            str(row.get("next_gate", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
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


def _action_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    return Path(text)


def _path_or_empty(path: str | Path | None) -> Path:
    if path is None:
        return Path()
    return Path(path)


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _clean(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str, fallback: float = 0.0) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return float(fallback)
    value = pd.to_numeric(frame.iloc[0][column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _identity_key(value: object) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _truthy(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed", "continue", "enabled"}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [_jsonable(row) for row in frame.to_dict(orient="records")]


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    records = _records(frame)
    return records[0] if records else {}


def _series_record(series: pd.Series) -> dict[str, Any]:
    return _jsonable(series.to_dict())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _records(value)
    if isinstance(value, pd.Series):
        return _series_record(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return str(value)
    return value
