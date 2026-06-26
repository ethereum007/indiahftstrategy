from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.runtime_guard import RuntimeGuardReport, write_runtime_guard_report


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_runtime_guard"

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
class ProviderMarketDataImbalanceRuntimeGuardConfig:
    require_provider_runtime_telemetry_ready: bool = True
    require_runtime_guard_continue: bool = False


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRuntimeGuardReport:
    guard: RuntimeGuardReport | None
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

    @property
    def halted(self) -> bool:
        if self.summary.empty:
            return True
        return bool(self.summary.iloc[0]["halted"])


def write_provider_market_data_imbalance_runtime_guard(
    provider_runtime_telemetry_dir: str | Path,
    output_dir: str | Path,
    *,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
    config: ProviderMarketDataImbalanceRuntimeGuardConfig | None = None,
) -> ProviderMarketDataImbalanceRuntimeGuardReport:
    config = config or ProviderMarketDataImbalanceRuntimeGuardConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    telemetry_root = Path(provider_runtime_telemetry_dir)
    provider_summary, provider_summary_error = _read_csv(
        telemetry_root / "provider_market_data_imbalance_runtime_telemetry_summary.csv"
    )
    scaleup_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "scaleup_dir")),
        telemetry_root.parent / "provider_imbalance_scaleup" / "scaleup",
        telemetry_root / "scaleup",
    )
    runtime_telemetry_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "runtime_telemetry_dir")),
        telemetry_root / "runtime_telemetry",
    )
    prechecks = _prechecks(
        telemetry_root,
        provider_summary,
        provider_summary_error,
        scaleup_dir,
        runtime_telemetry_dir,
        config,
    )

    guard: RuntimeGuardReport | None = None
    guard_error = ""
    guard_dir = out / "runtime_guard"
    if bool(prechecks["passed"].all()):
        try:
            guard = write_runtime_guard_report(
                scaleup_dir=_path_or_empty(scaleup_dir),
                telemetry_path=_path_or_empty(runtime_telemetry_dir),
                output_dir=guard_dir,
                as_of_ts_ns=as_of_ts_ns,
                max_telemetry_age_ns=max_telemetry_age_ns,
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            guard_error = str(exc)
    else:
        guard_error = "provider imbalance runtime guard prerequisites are not ready"

    checks = _checks(prechecks, guard, guard_error, provider_summary, config)
    summary = _summary(
        telemetry_root,
        scaleup_dir,
        runtime_telemetry_dir,
        guard,
        checks,
        out,
        provider_summary,
    )
    action_queue = _action_queue(summary.iloc[0], checks, guard)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        guard,
        checks,
        action_queue,
        config,
        as_of_ts_ns,
        max_telemetry_age_ns,
    )

    checks.to_csv(out / "provider_market_data_imbalance_runtime_guard_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_runtime_guard_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_runtime_guard_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_runtime_guard_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_runtime_guard_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_runtime_telemetry_dir": telemetry_root}
    if scaleup_dir is not None:
        inputs["scaleup"] = scaleup_dir
    if runtime_telemetry_dir is not None:
        inputs["runtime_telemetry"] = runtime_telemetry_dir
    if guard is not None and guard.output_dir is not None:
        inputs["runtime_guard"] = guard.output_dir
    summary_row = summary.iloc[0]
    capture_bundle = _path_from_text(summary_row["capture_bundle_path"])
    if capture_bundle is not None and capture_bundle.exists():
        inputs["capture_bundle"] = capture_bundle
    capture_env_template = _path_from_text(summary_row["capture_env_template_path"])
    if capture_env_template is not None and capture_env_template.exists():
        inputs["capture_env_template"] = capture_env_template
    adapter_handoff = _path_from_text(summary_row["adapter_handoff_path"])
    if adapter_handoff is not None and adapter_handoff.exists():
        inputs["adapter_handoff"] = adapter_handoff

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "as_of_ts_ns": as_of_ts_ns,
            "max_telemetry_age_ns": max_telemetry_age_ns,
        },
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "halted": bool(summary_row["halted"]),
            "guard_action": str(summary_row["guard_action"]),
            "profile": PROFILE,
            "capture_bundle_provided": bool(summary_row["capture_bundle_provided"]),
            "capture_env_template_exists": bool(summary_row["capture_env_template_exists"]),
            "adapter_handoff_exists": bool(summary_row["adapter_handoff_exists"]),
        },
    )
    return ProviderMarketDataImbalanceRuntimeGuardReport(guard, checks, summary, action_queue, payload, out)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _prechecks(
    telemetry_root: Path,
    provider_summary: pd.DataFrame,
    provider_summary_error: str,
    scaleup_dir: Path | None,
    runtime_telemetry_dir: Path | None,
    config: ProviderMarketDataImbalanceRuntimeGuardConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_runtime_telemetry_dir_exists",
                str(telemetry_root),
                "exists",
                True,
                telemetry_root.exists(),
                "provider imbalance runtime telemetry directory is required",
            ),
            _check(
                "provider_runtime_telemetry_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance runtime telemetry summary could not be read",
            ),
            _check(
                "provider_runtime_telemetry_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_runtime_telemetry_ready,
                "provider imbalance runtime telemetry is not ready",
            ),
            _check(
                "nested_scaleup_config_exists",
                _path_text(scaleup_dir),
                "exists",
                True,
                bool(scaleup_dir and (scaleup_dir / "scaleup_config.json").exists()),
                "nested scaleup_config.json is required for runtime guard",
            ),
            _check(
                "runtime_telemetry_csv_exists",
                _path_text(None if runtime_telemetry_dir is None else runtime_telemetry_dir / "runtime_telemetry.csv"),
                "exists",
                True,
                bool(runtime_telemetry_dir and (runtime_telemetry_dir / "runtime_telemetry.csv").exists()),
                "nested runtime_telemetry.csv is required for runtime guard",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    guard: RuntimeGuardReport | None,
    guard_error: str,
    provider_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceRuntimeGuardConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    guard_summary = guard.summary if guard is not None else pd.DataFrame()
    guard_continue = guard is not None and not guard.halted
    rows.append(
        _check(
            "runtime_guard_runnable",
            guard_error or ("ran" if guard is not None else "not_run"),
            "is",
            "ran",
            guard is not None and not guard_error,
            guard_error or "generic runtime guard was not run",
        )
    )
    rows.append(
        _check(
            "runtime_guard_evaluated",
            bool(guard is not None and not guard_summary.empty),
            "is",
            True,
            bool(guard is not None and not guard_summary.empty),
            "generic runtime guard did not write an evaluation summary",
        )
    )
    rows.append(
        _check(
            "runtime_guard_continue",
            guard_continue,
            "is",
            True,
            bool(guard is not None and (guard_continue or not config.require_runtime_guard_continue)),
            "runtime guard halted routing",
        )
    )
    strategy = _first_text(guard_summary, "strategy") or _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            _identity_key(strategy) == PROFILE,
            "runtime guard did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    guard_market = _first_text(guard_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            guard_market or expected_market,
            "is",
            expected_market or "present",
            bool(guard_market)
            and (not expected_market or _identity_key(guard_market) == _identity_key(expected_market)),
            "runtime guard market identity does not match provider telemetry",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    telemetry_root: Path,
    scaleup_dir: Path | None,
    runtime_telemetry_dir: Path | None,
    guard: RuntimeGuardReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    provider_summary: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    guard_summary = guard.summary if guard is not None else pd.DataFrame()
    halted = True if guard is None else bool(guard.halted)
    guard_action = _first_text(guard_summary, "guard_action") or ("halt" if halted else "continue")
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_runtime_telemetry_ready": _first_bool(provider_summary, "ready"),
                "runtime_guard_evaluated": guard is not None and not guard_summary.empty,
                "runtime_guard_continue": bool(guard is not None and not guard.halted),
                "halted": halted,
                "guard_action": guard_action,
                "provider_runtime_telemetry_dir": str(telemetry_root),
                "scaleup_dir": _path_text(scaleup_dir),
                "runtime_telemetry_dir": _path_text(runtime_telemetry_dir),
                "capture_bundle_path": _first_text(provider_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(provider_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(provider_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(provider_summary, "capture_bundle_ready"),
                "capture_env_template_path": _first_text(provider_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(provider_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(provider_summary, "capture_env_template_exists"),
                "adapter_handoff_path": _first_text(provider_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(provider_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(provider_summary, "adapter_handoff_exists"),
                "runtime_guard_dir": "" if guard is None else str(guard.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(guard_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(guard_summary, "strategy") or _first_text(provider_summary, "strategy") or PROFILE,
                "target_mode": _first_text(guard_summary, "target_mode") or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(guard_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(guard_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "orders_sent": _first_number(guard_summary, "orders_sent"),
                "session_notional": _first_number(guard_summary, "session_notional"),
                "runtime_guard_failed_checks": _first_number(guard_summary, "failed_check_count"),
                "runtime_guard_failed_check_names": _first_text(guard_summary, "failed_check_names"),
                "runtime_guard_primary_blocker": _first_text(guard_summary, "primary_blocker_check"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": _recommendation(ready, halted, guard is not None),
                "next_gate": _ready_next_gate(guard) if ready else _blocked_next_gate(checks, guard),
                "next_gate_help_command": _help_command_for_gate(
                    _ready_next_gate(guard) if ready else _blocked_next_gate(checks, guard)
                ),
                "primary_action_status": "ready" if ready else _primary_blocked_status(checks, guard),
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
    guard: RuntimeGuardReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty and guard is not None and not guard.halted:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_runtime_guard_summary",
                    "component": "runtime_guard",
                    "check": "runtime_guard_continue",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "monitor_provider_imbalance_runtime_session",
                    "reason": "provider imbalance runtime guard is clear to continue monitoring",
                    "recommendation": "continue_provider_imbalance_shadow_monitoring",
                    "next_gate": "monitor-provider-market-data-imbalance-runtime-session",
                    "next_gate_help_command": _help_command_for_gate(
                        "monitor-provider-market-data-imbalance-runtime-session"
                    ),
                }
            ]
        )
    if failed.empty and guard is not None and guard.halted:
        return _halt_actions_from_guard(guard)

    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        halted_check = name == "runtime_guard_continue" and guard is not None and guard.halted
        next_gate = _next_gate_for_check(name, guard)
        rows.append(
            {
                "queue_status": "ready" if halted_check else "blocked",
                "source": "provider_market_data_imbalance_runtime_guard_checks",
                "component": _component_for_check(name),
                "check": name,
                "actual": check.get("value"),
                "operator": check.get("operator"),
                "expected": check.get("threshold"),
                "action": _action_for_check(name, guard),
                "reason": str(check.get("reason", "")) or name.replace("_", " "),
                "recommendation": _recommendation_for_check(name, guard),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_runtime_guard_checks",
                "component": "runtime_guard",
                "check": "provider_runtime_guard_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_runtime_guard",
                "reason": "provider imbalance runtime guard is not ready",
                "recommendation": "rebuild_provider_imbalance_runtime_guard",
                "next_gate": "monitor-provider-market-data-imbalance-runtime-guard",
                "next_gate_help_command": _help_command_for_gate(
                    "monitor-provider-market-data-imbalance-runtime-guard"
                ),
            }
        )
    return _action_frame(rows)


def _halt_actions_from_guard(guard: RuntimeGuardReport) -> pd.DataFrame:
    guard_queue = guard.action_queue if guard.action_queue is not None else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    if guard_queue.empty:
        rows.append(
            {
                "queue_status": "ready",
                "source": "runtime_guard_summary",
                "component": "runtime_guard",
                "check": "guard_action",
                "actual": "halt",
                "operator": "is",
                "expected": "continue",
                "action": "execute_provider_imbalance_halt_response",
                "reason": "runtime guard halted routing",
                "recommendation": "stop_routing_and_prepare_halt_response",
                "next_gate": "plan-halt-response",
                "next_gate_help_command": _help_command_for_gate("plan-halt-response"),
            }
        )
    for item in guard_queue.to_dict(orient="records"):
        next_gate = str(item.get("next_gate") or "plan-halt-response")
        rows.append(
            {
                "queue_status": str(item.get("queue_status") or "ready"),
                "source": "runtime_guard_action_queue",
                "component": str(item.get("component") or "runtime_guard"),
                "check": str(item.get("check") or "guard_action"),
                "actual": item.get("actual"),
                "operator": item.get("operator"),
                "expected": item.get("expected"),
                "action": "execute_provider_imbalance_halt_response",
                "reason": str(item.get("reason") or "runtime guard halted routing"),
                "recommendation": str(item.get("recommendation") or "stop_routing_and_prepare_halt_response"),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    guard: RuntimeGuardReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceRuntimeGuardConfig,
    as_of_ts_ns: int | float | None,
    max_telemetry_age_ns: int | float | None,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "halted": bool(summary["halted"]),
        "guard_action": str(summary["guard_action"]),
        "parameters": {
            **asdict(config),
            "as_of_ts_ns": as_of_ts_ns,
            "max_telemetry_age_ns": max_telemetry_age_ns,
        },
        "summary": _series_record(summary),
        "capture_bundle": {
            "capture_bundle_path": str(summary["capture_bundle_path"]),
            "capture_bundle_provided": bool(summary["capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary["capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary["capture_bundle_ready"]),
            "capture_env_template_path": str(summary["capture_env_template_path"]),
            "capture_env_template_provided": bool(summary["capture_env_template_provided"]),
            "capture_env_template_exists": bool(summary["capture_env_template_exists"]),
            "adapter_handoff_path": str(summary["adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
        },
        "provider_runtime_telemetry": _first_record(provider_summary),
        "runtime_guard": {
            "evaluated": guard is not None,
            "halted": True if guard is None else bool(guard.halted),
            "output_dir": "" if guard is None else str(guard.output_dir or ""),
            "summary": _first_record(None if guard is None else guard.summary),
            "checks": _records(None if guard is None else guard.checks),
            "action_queue": _records(None if guard is None else guard.action_queue),
            "config": {} if guard is None or guard.config is None else guard.config,
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
        "# Provider Market Data Imbalance Runtime Guard",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Halted: {'yes' if bool(summary['halted']) else 'no'}",
        f"- Guard action: {summary['guard_action']}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Target mode: {summary['target_mode']}",
        f"- Runtime guard dir: {summary['runtime_guard_dir']}",
        f"- Primary next gate: `{summary['next_gate']}`",
        f"- Primary next gate help: `{summary['next_gate_help_command']}`",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
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


def _recommendation(ready: bool, halted: bool, guard_present: bool) -> str:
    if guard_present and halted:
        return "execute_provider_imbalance_halt_response"
    if ready:
        return "monitor_provider_imbalance_runtime_session"
    return "repair_provider_imbalance_runtime_guard"


def _ready_next_gate(guard: RuntimeGuardReport | None) -> str:
    if guard is None:
        return "monitor-provider-market-data-imbalance-runtime-guard"
    if guard.halted:
        return _first_action_value(guard.action_queue, "next_gate") or "plan-halt-response"
    return "monitor-provider-market-data-imbalance-runtime-session"


def _blocked_next_gate(checks: pd.DataFrame, guard: RuntimeGuardReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return _ready_next_gate(guard)
    return _next_gate_for_check(failed[0], guard)


def _primary_blocked_status(checks: pd.DataFrame, guard: RuntimeGuardReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if failed and failed[0] == "runtime_guard_continue" and guard is not None and guard.halted:
        return "ready"
    return "blocked"


def _next_gate_for_check(check: str, guard: RuntimeGuardReport | None) -> str:
    if check in {"provider_runtime_telemetry_dir_exists", "provider_runtime_telemetry_summary_readable"}:
        return "build-provider-market-data-imbalance-runtime-telemetry"
    if check == "provider_runtime_telemetry_ready":
        return "build-provider-market-data-imbalance-runtime-telemetry"
    if check == "nested_scaleup_config_exists":
        return "plan-provider-market-data-imbalance-scaleup"
    if check == "runtime_telemetry_csv_exists":
        return "build-provider-market-data-imbalance-runtime-telemetry"
    if check in {"runtime_guard_runnable", "runtime_guard_evaluated"}:
        return "monitor-scaleup-guard"
    if check == "runtime_guard_continue" and guard is not None and guard.halted:
        return _first_action_value(guard.action_queue, "next_gate") or "plan-halt-response"
    if check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "build-provider-market-data-imbalance-runtime-telemetry"
    return "monitor-provider-market-data-imbalance-runtime-guard"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "build-provider-market-data-imbalance-runtime-telemetry":
        return "python -m hft_cli build-provider-market-data-imbalance-runtime-telemetry --help"
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "monitor-scaleup-guard":
        return "python -m hft_cli monitor-scaleup-guard --help"
    if next_gate == "plan-halt-response":
        return "python -m hft_cli plan-halt-response --help"
    if next_gate == "monitor-runtime-session":
        return "python -m hft_cli monitor-runtime-session --help"
    if next_gate == "monitor-provider-market-data-imbalance-runtime-session":
        return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-session --help"
    return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-guard --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_runtime_telemetry"):
        return "provider_runtime_telemetry"
    if check.startswith("nested_scaleup"):
        return "scaleup_plan"
    if check.startswith("runtime_telemetry"):
        return "runtime_telemetry"
    if check.startswith("runtime_guard"):
        return "runtime_guard"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_runtime_guard"


def _action_for_check(check: str, guard: RuntimeGuardReport | None) -> str:
    if check == "runtime_guard_continue" and guard is not None and guard.halted:
        return "execute_provider_imbalance_halt_response"
    if check.startswith("provider_runtime_telemetry"):
        return "repair_provider_imbalance_runtime_telemetry"
    if check.startswith("nested_scaleup"):
        return "rebuild_provider_imbalance_scaleup"
    if check.startswith("runtime_telemetry"):
        return "rebuild_provider_imbalance_runtime_telemetry"
    if check.startswith("runtime_guard"):
        return "repair_runtime_guard_monitor"
    return "repair_provider_imbalance_runtime_guard"


def _recommendation_for_check(check: str, guard: RuntimeGuardReport | None) -> str:
    if check == "runtime_guard_continue" and guard is not None and guard.halted:
        return "stop_routing_and_prepare_halt_response"
    if check.startswith("provider_runtime_telemetry"):
        return "rebuild_provider_runtime_telemetry_before_guard"
    if check.startswith("nested_scaleup"):
        return "rebuild_provider_scaleup_before_guard"
    if check.startswith("runtime_telemetry"):
        return "rebuild_runtime_telemetry_before_guard"
    if check.startswith("runtime_guard"):
        return "rerun_runtime_guard_with_valid_inputs"
    return "repair_provider_runtime_guard_inputs"


def _first_action_value(action_queue: pd.DataFrame | None, column: str) -> str:
    if action_queue is None or action_queue.empty or column not in action_queue.columns:
        return ""
    for value in action_queue[column].tolist():
        text = _clean(value)
        if text:
            return text
    return ""


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


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _path_or_empty(path: Path | None) -> Path:
    return Path("") if path is None else path


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _clean(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    try:
        value = frame.iloc[0][column]
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed"}


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
