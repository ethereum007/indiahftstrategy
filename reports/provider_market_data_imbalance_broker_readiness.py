from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker_readiness import BrokerReadinessReport, BrokerReadinessThresholds, write_broker_readiness_report
from reports.manifest import write_experiment_manifest


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_broker_readiness"

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
class ProviderMarketDataImbalanceBrokerReadinessConfig:
    require_provider_runtime_session_ready: bool = True
    require_broker_readiness_ready: bool = True
    use_provider_runtime_session_inputs: bool = True
    adapter: str = ""
    expected_market: str = ""
    expected_vendor_data_kind: str = "ticks"
    require_reviewed_schema: bool = False
    require_schema_audit: bool = False
    require_order_export: bool = True
    require_mapping_draft: bool = False
    require_mapped_orders: bool = False
    require_upload_pack: bool = True
    require_halt_export: bool = False
    require_reconciliation: bool = False
    require_runtime_session: bool = True
    require_resume_gate: bool = False
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    require_adapter_match: bool = True


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerReadinessReport:
    broker_readiness: BrokerReadinessReport | None
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


def write_provider_market_data_imbalance_broker_readiness(
    provider_runtime_session_dir: str | Path,
    output_dir: str | Path,
    *,
    schema_audit_dir: str | Path | None = None,
    order_export_dir: str | Path | None = None,
    mapping_draft_dir: str | Path | None = None,
    mapped_orders_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    halt_export_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    resume_dir: str | Path | None = None,
    dispatch_roundtrip_dir: str | Path | None = None,
    vendor_market_data_batch_dir: str | Path | None = None,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerReadinessReport:
    config = config or ProviderMarketDataImbalanceBrokerReadinessConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    session_root = Path(provider_runtime_session_dir)
    session_summary, session_summary_error = _read_csv(
        session_root / "provider_market_data_imbalance_runtime_session_summary.csv"
    )
    session_config, session_config_error = _read_json(
        session_root / "provider_market_data_imbalance_runtime_session_config.json"
    )
    runtime_inputs = _runtime_inputs(session_config)
    generic_runtime_session_dir = _first_existing_path(
        _path_from_text(_first_text(session_summary, "runtime_session_dir")),
        _path_from_text((session_config.get("runtime_session", {}) or {}).get("output_dir")),
    )
    resolved_order_export_dir = _explicit_or_inferred(order_export_dir, runtime_inputs, "export_dir", config)
    resolved_upload_pack_dir = _explicit_or_inferred(upload_pack_dir, runtime_inputs, "upload_pack_dir", config)
    resolved_reconciliation_dir = _explicit_or_inferred(reconciliation_dir, runtime_inputs, "reconciliation_dir", config)
    resolved_schema_audit_dir = Path(schema_audit_dir) if schema_audit_dir is not None else None
    resolved_mapping_draft_dir = Path(mapping_draft_dir) if mapping_draft_dir is not None else None
    resolved_mapped_orders_dir = Path(mapped_orders_dir) if mapped_orders_dir is not None else None
    resolved_halt_export_dir = Path(halt_export_dir) if halt_export_dir is not None else None
    resolved_resume_dir = Path(resume_dir) if resume_dir is not None else None
    provider_dispatch_roundtrip_dir = Path(dispatch_roundtrip_dir) if dispatch_roundtrip_dir is not None else None
    resolved_dispatch_roundtrip_dir = _resolve_dispatch_roundtrip_dir(provider_dispatch_roundtrip_dir)
    provider_roundtrip_summary, provider_roundtrip_config = _read_provider_dispatch_roundtrip_artifacts(
        provider_dispatch_roundtrip_dir
    )
    upstream_provider_dispatch_roundtrip_dir, upstream_dispatch_roundtrip_dir = (
        _inferred_upstream_dispatch_roundtrip_dirs(provider_roundtrip_summary, provider_roundtrip_config)
    )
    resolved_vendor_market_data_batch_dir = Path(vendor_market_data_batch_dir) if vendor_market_data_batch_dir is not None else None

    prechecks = _prechecks(
        session_root,
        session_summary,
        session_summary_error,
        session_config_error,
        generic_runtime_session_dir,
        resolved_order_export_dir,
        resolved_upload_pack_dir,
        config,
    )
    broker: BrokerReadinessReport | None = None
    broker_error = ""
    broker_dir = out / "broker_readiness"
    if bool(prechecks["passed"].all()):
        try:
            broker = write_broker_readiness_report(
                output_dir=broker_dir,
                schema_audit_dir=resolved_schema_audit_dir,
                order_export_dir=resolved_order_export_dir,
                mapping_draft_dir=resolved_mapping_draft_dir,
                mapped_orders_dir=resolved_mapped_orders_dir,
                upload_pack_dir=resolved_upload_pack_dir,
                halt_export_dir=resolved_halt_export_dir,
                reconciliation_dir=resolved_reconciliation_dir,
                runtime_session_dir=generic_runtime_session_dir,
                resume_dir=resolved_resume_dir,
                dispatch_roundtrip_dir=resolved_dispatch_roundtrip_dir,
                vendor_market_data_batch_dir=resolved_vendor_market_data_batch_dir,
                thresholds=_thresholds(config, session_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            broker_error = str(exc)
    else:
        broker_error = "provider imbalance broker readiness prerequisites are not ready"

    checks = _checks(prechecks, broker, broker_error, session_summary, config)
    summary = _summary(
        session_root,
        generic_runtime_session_dir,
        broker,
        checks,
        out,
        session_summary,
        resolved_schema_audit_dir,
        resolved_order_export_dir,
        resolved_upload_pack_dir,
        provider_dispatch_roundtrip_dir,
        resolved_dispatch_roundtrip_dir,
        provider_roundtrip_summary,
        upstream_provider_dispatch_roundtrip_dir,
        upstream_dispatch_roundtrip_dir,
    )
    action_queue = _action_queue(summary.iloc[0], checks, broker)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        session_summary,
        session_config,
        broker,
        checks,
        action_queue,
        config,
        {
            "schema_audit_dir": resolved_schema_audit_dir,
            "order_export_dir": resolved_order_export_dir,
            "mapping_draft_dir": resolved_mapping_draft_dir,
            "mapped_orders_dir": resolved_mapped_orders_dir,
            "upload_pack_dir": resolved_upload_pack_dir,
            "halt_export_dir": resolved_halt_export_dir,
            "reconciliation_dir": resolved_reconciliation_dir,
            "runtime_session_dir": generic_runtime_session_dir,
            "resume_dir": resolved_resume_dir,
            "provider_dispatch_roundtrip_dir": provider_dispatch_roundtrip_dir,
            "dispatch_roundtrip_dir": resolved_dispatch_roundtrip_dir,
            "upstream_provider_dispatch_roundtrip_dir": upstream_provider_dispatch_roundtrip_dir,
            "upstream_dispatch_roundtrip_dir": upstream_dispatch_roundtrip_dir,
            "vendor_market_data_batch_dir": resolved_vendor_market_data_batch_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_broker_readiness_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_broker_readiness_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_broker_readiness_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_broker_readiness_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_readiness_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_runtime_session_dir": session_root}
    for name, value in {
        "runtime_session": generic_runtime_session_dir,
        "schema_audit": resolved_schema_audit_dir,
        "order_export": resolved_order_export_dir,
        "mapping_draft": resolved_mapping_draft_dir,
        "mapped_orders": resolved_mapped_orders_dir,
        "upload_pack": resolved_upload_pack_dir,
        "halt_export": resolved_halt_export_dir,
        "reconciliation": resolved_reconciliation_dir,
        "resume_gate": resolved_resume_dir,
        "dispatch_roundtrip": resolved_dispatch_roundtrip_dir,
        "provider_dispatch_roundtrip": provider_dispatch_roundtrip_dir,
        "upstream_provider_dispatch_roundtrip": upstream_provider_dispatch_roundtrip_dir,
        "upstream_dispatch_roundtrip": upstream_dispatch_roundtrip_dir,
        "vendor_market_data_batch": resolved_vendor_market_data_batch_dir,
    }.items():
        if value is not None:
            inputs[name] = Path(value)
    if broker is not None and broker.output_dir is not None:
        inputs["broker_readiness"] = broker.output_dir

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config), "broker_inputs": _jsonable(payload["broker_inputs"])},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "broker_readiness_ready": bool(summary.iloc[0]["broker_readiness_ready"]),
            "profile": PROFILE,
            "strategy": str(summary.iloc[0]["strategy"]),
            "market": str(summary.iloc[0]["market"]),
        },
    )
    return ProviderMarketDataImbalanceBrokerReadinessReport(broker, checks, summary, action_queue, payload, out)


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
    session_root: Path,
    session_summary: pd.DataFrame,
    session_summary_error: str,
    session_config_error: str,
    generic_runtime_session_dir: Path | None,
    order_export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_runtime_session_dir_exists",
                str(session_root),
                "exists",
                True,
                session_root.exists(),
                "provider imbalance runtime session directory is required",
            ),
            _check(
                "provider_runtime_session_summary_readable",
                session_summary_error or "ok",
                "is",
                "ok",
                not session_summary_error,
                session_summary_error or "provider imbalance runtime session summary could not be read",
            ),
            _check(
                "provider_runtime_session_config_readable",
                session_config_error or "ok",
                "is",
                "ok",
                not session_config_error,
                session_config_error or "provider imbalance runtime session config could not be read",
            ),
            _check(
                "provider_runtime_session_ready",
                _first_bool(session_summary, "ready"),
                "is",
                True,
                _first_bool(session_summary, "ready") or not config.require_provider_runtime_session_ready,
                "provider imbalance runtime session is not ready",
            ),
            _check(
                "nested_runtime_session_summary_exists",
                _path_text(generic_runtime_session_dir),
                "exists",
                True,
                bool(generic_runtime_session_dir and (generic_runtime_session_dir / "runtime_session_summary.csv").exists()),
                "nested runtime_session_summary.csv is required for broker readiness",
            ),
            _check(
                "order_export_input_resolved",
                _path_text(_path_or_none(order_export_dir)),
                "exists",
                True,
                (not config.require_order_export) or bool(order_export_dir),
                "order export input is required for provider broker readiness",
            ),
            _check(
                "upload_pack_input_resolved",
                _path_text(_path_or_none(upload_pack_dir)),
                "exists",
                True,
                (not config.require_upload_pack) or bool(upload_pack_dir),
                "upload pack input is required for provider broker readiness",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    broker: BrokerReadinessReport | None,
    broker_error: str,
    session_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    broker_summary = broker.summary if broker is not None else pd.DataFrame()
    rows.append(
        _check(
            "broker_readiness_runnable",
            broker_error or ("ran" if broker is not None else "not_run"),
            "is",
            "ran",
            broker is not None and not broker_error,
            broker_error or "generic broker readiness was not run",
        )
    )
    rows.append(
        _check(
            "broker_readiness_ready",
            bool(broker is not None and broker.ready),
            "is",
            True,
            bool(broker is not None and (broker.ready or not config.require_broker_readiness_ready)),
            _broker_failure_reason(broker) or "broker readiness is not ready",
        )
    )
    strategy = _first_text(session_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            _identity_key(strategy) == PROFILE,
            "provider broker readiness did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(session_summary, "market")
    broker_market = _first_text(broker_summary, "runtime_market")
    rows.append(
        _check(
            "market_identity_consistent",
            broker_market or expected_market,
            "is",
            expected_market or "present",
            bool(broker is not None)
            and bool(expected_market)
            and (not broker_market or _identity_key(broker_market) == _identity_key(expected_market)),
            "broker readiness market identity does not match provider runtime session",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    session_root: Path,
    generic_runtime_session_dir: Path | None,
    broker: BrokerReadinessReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    session_summary: pd.DataFrame,
    schema_audit_dir: Path | None,
    order_export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
    provider_dispatch_roundtrip_dir: Path | None,
    dispatch_roundtrip_dir: Path | None,
    provider_roundtrip_summary: pd.DataFrame,
    upstream_provider_dispatch_roundtrip_dir: Path | None,
    upstream_dispatch_roundtrip_dir: Path | None,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    broker_summary = broker.summary if broker is not None else pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_runtime_session_ready": _first_bool(session_summary, "ready"),
                "broker_readiness_ready": bool(broker is not None and broker.ready),
                "provider_runtime_session_dir": str(session_root),
                "runtime_session_dir": _path_text(generic_runtime_session_dir),
                "broker_readiness_dir": "" if broker is None else str(broker.output_dir or ""),
                "schema_audit_dir": _path_text(schema_audit_dir),
                "order_export_dir": _path_text(_path_or_none(order_export_dir)),
                "upload_pack_dir": _path_text(_path_or_none(upload_pack_dir)),
                "provider_dispatch_roundtrip_dir": _path_text(provider_dispatch_roundtrip_dir),
                "dispatch_roundtrip_dir": _path_text(dispatch_roundtrip_dir),
                "upstream_provider_dispatch_roundtrip_dir": _path_text(upstream_provider_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_dir": _path_text(upstream_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_provided": bool(upstream_dispatch_roundtrip_dir)
                or _first_bool(provider_roundtrip_summary, "upstream_dispatch_roundtrip_provided"),
                "upstream_dispatch_roundtrip_ready": _first_bool(
                    provider_roundtrip_summary,
                    "upstream_dispatch_roundtrip_ready",
                ),
                "upstream_dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_roundtrip_summary, "upstream_dispatch_roundtrip_failed_checks")
                ),
                "dispatch_roundtrip_provided": _first_bool(broker_summary, "dispatch_roundtrip_provided"),
                "dispatch_roundtrip_ready": _first_bool(broker_summary, "dispatch_roundtrip_ready"),
                "dispatch_roundtrip_failed_checks": int(
                    _first_number(broker_summary, "dispatch_roundtrip_failed_checks")
                ),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(session_summary, "provider"),
                "transport": _first_text(session_summary, "transport"),
                "market": _first_text(session_summary, "market"),
                "strategy": _first_text(session_summary, "strategy") or PROFILE,
                "target_mode": _first_text(session_summary, "target_mode"),
                "adapter": _first_text(broker_summary, "adapter") or _first_text(session_summary, "adapter"),
                "schema_reviewed": _first_bool(broker_summary, "schema_reviewed"),
                "schema_review_mode": _first_text(broker_summary, "schema_review_mode"),
                "runtime_session_ready": _first_bool(broker_summary, "runtime_session_ready"),
                "runtime_guard_action": _first_text(broker_summary, "runtime_guard_action")
                or _first_text(session_summary, "guard_action"),
                "runtime_guard_halted": _first_bool(broker_summary, "runtime_guard_halted")
                or _first_bool(session_summary, "halted"),
                "broker_recommendation": _first_text(broker_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "prepare_provider_imbalance_cutover_review"
                if ready
                else "repair_provider_imbalance_broker_readiness",
                "next_gate": "review-provider-market-data-imbalance-cutover" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _help_command_for_gate(
                    "review-provider-market-data-imbalance-cutover" if ready else _blocked_next_gate(checks)
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
    broker: BrokerReadinessReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_broker_readiness_summary",
                    "component": "broker_readiness",
                    "check": "broker_readiness_ready",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "prepare_provider_imbalance_cutover_review",
                    "reason": "provider imbalance broker readiness is clear for cutover review",
                    "recommendation": "feed_broker_readiness_into_cutover_gate",
                    "next_gate": "review-provider-market-data-imbalance-cutover",
                    "next_gate_help_command": _help_command_for_gate(
                        "review-provider-market-data-imbalance-cutover"
                    ),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, broker)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_readiness_checks",
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
                "source": "provider_market_data_imbalance_broker_readiness_checks",
                "component": "broker_readiness",
                "check": "provider_broker_readiness_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_broker_readiness",
                "reason": "provider imbalance broker readiness is not ready",
                "recommendation": "rerun_provider_imbalance_broker_readiness",
                "next_gate": "review-provider-market-data-imbalance-broker-readiness",
                "next_gate_help_command": _help_command_for_gate(
                    "review-provider-market-data-imbalance-broker-readiness"
                ),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    session_summary: pd.DataFrame,
    session_config: dict[str, Any],
    broker: BrokerReadinessReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
    broker_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "broker_inputs": _jsonable(broker_inputs),
        "summary": _series_record(summary),
        "provider_runtime_session": _first_record(session_summary),
        "provider_runtime_session_config": session_config,
        "broker_readiness": {
            "evaluated": broker is not None,
            "ready": False if broker is None else bool(broker.ready),
            "output_dir": "" if broker is None else str(broker.output_dir or ""),
            "summary": _first_record(None if broker is None else broker.summary),
            "items": _records(None if broker is None else broker.items),
            "checks": _records(None if broker is None else broker.checks),
            "action_queue": _records(None if broker is None else broker.action_queue),
            "config": {} if broker is None or broker.config is None else broker.config,
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
        "# Provider Market Data Imbalance Broker Readiness",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Target mode: {summary['target_mode']}",
        f"- Broker readiness dir: {summary['broker_readiness_dir']}",
        f"- Dispatch round-trip ready: {'yes' if bool(summary['dispatch_roundtrip_ready']) else 'no'}",
        f"- Dispatch round-trip dir: {summary['dispatch_roundtrip_dir']}",
        f"- Upstream dispatch round-trip ready: {'yes' if bool(summary['upstream_dispatch_roundtrip_ready']) else 'no'}",
        f"- Upstream dispatch round-trip dir: {summary['upstream_dispatch_roundtrip_dir']}",
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
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
    session_summary: pd.DataFrame,
) -> BrokerReadinessThresholds:
    return BrokerReadinessThresholds(
        adapter=config.adapter or _first_text(session_summary, "adapter") or "arrow_money",
        expected_market=config.expected_market or _first_text(session_summary, "market"),
        expected_vendor_data_kind=config.expected_vendor_data_kind,
        require_reviewed_schema=config.require_reviewed_schema,
        require_schema_audit=config.require_schema_audit,
        require_order_export=config.require_order_export,
        require_mapping_draft=config.require_mapping_draft,
        require_mapped_orders=config.require_mapped_orders,
        require_upload_pack=config.require_upload_pack,
        require_halt_export=config.require_halt_export,
        require_reconciliation=config.require_reconciliation,
        require_runtime_session=config.require_runtime_session,
        require_resume_gate=config.require_resume_gate,
        require_route_readiness=config.require_route_readiness,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        require_adapter_match=config.require_adapter_match,
    )


def _broker_failure_reason(broker: BrokerReadinessReport | None) -> str:
    if broker is None or broker.checks.empty:
        return ""
    failed = broker.checks.loc[~broker.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "review-provider-market-data-imbalance-broker-readiness"
    return _next_gate_for_check(failed[0], None)


def _next_gate_for_check(check: str, broker: BrokerReadinessReport | None) -> str:
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "monitor-provider-market-data-imbalance-runtime-session"
    if check.startswith("order_export") or check.startswith("upload_pack"):
        return "pipeline-provider-market-data-imbalance-launch"
    if check == "broker_readiness_ready" and broker is not None:
        next_gate = _provider_next_gate(_first_action_value(broker.action_queue, "next_gate"))
        return next_gate or "review-provider-market-data-imbalance-broker-readiness"
    if check.startswith("broker_readiness"):
        return "review-broker-readiness"
    if check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "monitor-provider-market-data-imbalance-runtime-session"
    return "review-provider-market-data-imbalance-broker-readiness"


def _provider_next_gate(next_gate: str) -> str:
    mapping = {
        "review-broker-readiness": "review-provider-market-data-imbalance-broker-readiness",
        "review-route-readiness": "review-provider-market-data-imbalance-route-readiness",
        "review-broker-dispatch-roundtrip": "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
        "plan-broker-dispatch": "plan-provider-market-data-imbalance-broker-dispatch",
        "prepare-broker-dispatch-send": "prepare-provider-market-data-imbalance-broker-dispatch-send",
        "reconcile-broker-dispatch": "reconcile-provider-market-data-imbalance-broker-dispatch",
    }
    return mapping.get(next_gate, next_gate)


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "monitor-provider-market-data-imbalance-runtime-session":
        return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-session --help"
    if next_gate == "pipeline-provider-market-data-imbalance-launch":
        return "python -m hft_cli pipeline-provider-market-data-imbalance-launch --help"
    if next_gate == "review-provider-market-data-imbalance-route-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-broker-dispatch-roundtrip":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-dispatch-roundtrip --help"
    if next_gate == "plan-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "prepare-provider-market-data-imbalance-broker-dispatch-send":
        return "python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send --help"
    if next_gate == "reconcile-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli reconcile-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "review-broker-readiness":
        return "python -m hft_cli review-broker-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-cutover":
        return "python -m hft_cli review-provider-market-data-imbalance-cutover --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    return "python -m hft_cli review-provider-market-data-imbalance-broker-readiness --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "provider_runtime_session"
    if check.startswith("order_export"):
        return "order_export"
    if check.startswith("upload_pack"):
        return "upload_pack"
    if check.startswith("broker_readiness"):
        return "broker_readiness"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_broker_readiness"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "repair_provider_imbalance_runtime_session"
    if check.startswith("order_export") or check.startswith("upload_pack"):
        return "repair_provider_imbalance_launch_broker_artifacts"
    if check.startswith("broker_readiness"):
        return "repair_broker_readiness_inputs"
    return "repair_provider_imbalance_broker_readiness"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_runtime_session") or check.startswith("nested_runtime_session"):
        return "rerun_provider_runtime_session_before_broker_readiness"
    if check.startswith("order_export") or check.startswith("upload_pack"):
        return "rebuild_provider_launch_pipeline_broker_artifacts"
    if check.startswith("broker_readiness"):
        return "rerun_generic_broker_readiness_with_required_artifacts"
    return "repair_provider_broker_readiness_inputs"


def _runtime_inputs(session_config: dict[str, Any]) -> dict[str, Any]:
    inputs = session_config.get("runtime_inputs", {}) or {}
    return inputs if isinstance(inputs, dict) else {}


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred_inputs: dict[str, Any],
    key: str,
    config: ProviderMarketDataImbalanceBrokerReadinessConfig,
) -> str | Path | None:
    if explicit is not None:
        return explicit
    if not config.use_provider_runtime_session_inputs:
        return None
    text = _clean(inferred_inputs.get(key))
    return text or None


def _resolve_dispatch_roundtrip_dir(path: Path | None) -> Path | None:
    if path is None:
        return None
    generic_summary = path / "broker_dispatch_roundtrip_summary.csv" if path.is_dir() else path
    if generic_summary.exists():
        return path
    provider_summary, _ = _read_csv(path / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    provider_config, _ = _read_json(path / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json")
    nested = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "broker_dispatch_roundtrip_dir")),
        _path_from_text(((provider_config.get("broker_dispatch_roundtrip", {}) or {}).get("output_dir"))),
        _manifest_input_path(path / "manifest.json", "broker_dispatch_roundtrip"),
    )
    return nested or path


def _read_provider_dispatch_roundtrip_artifacts(path: Path | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if path is None:
        return pd.DataFrame(), {}
    summary, _ = _read_csv(path / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    config, _ = _read_json(path / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json")
    return summary, config


def _inferred_upstream_dispatch_roundtrip_dirs(
    provider_roundtrip_summary: pd.DataFrame,
    provider_roundtrip_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    inputs = provider_roundtrip_config.get("broker_dispatch_roundtrip_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_roundtrip_summary, "upstream_provider_dispatch_roundtrip_dir")),
        _path_from_text(inputs.get("upstream_provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_roundtrip_summary, "upstream_dispatch_roundtrip_dir")),
        _path_from_text(inputs.get("upstream_dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _manifest_input_path(manifest_path: Path, input_name: str) -> Path | None:
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = (manifest.get("inputs", {}) or {}).get(input_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    if not raw_path:
        return None
    candidate = Path(str(raw_path))
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate


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


def _path_or_none(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    return Path(value)


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
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed", "continue"}


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
