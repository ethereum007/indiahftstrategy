from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.cutover import CutoverGateReport, CutoverGateThresholds, write_cutover_gate_report
from reports.manifest import write_experiment_manifest


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_cutover"

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
class ProviderMarketDataImbalanceCutoverConfig:
    require_provider_broker_readiness_ready: bool = True
    require_cutover_ready: bool = True
    use_provider_broker_readiness_inputs: bool = True
    target_mode: str = ""
    require_scaleup_ready: bool = True
    require_broker_readiness: bool = True
    require_runtime_session: bool = True
    require_runtime_guard_continue: bool = True
    require_route_readiness: bool = False
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
    require_operator_approval: bool = False
    require_operator_identity_ack: bool = False
    require_operator_limits_ack: bool = False
    max_failed_scaleup_checks: int = 0


@dataclass(frozen=True)
class ProviderMarketDataImbalanceCutoverReport:
    cutover: CutoverGateReport | None
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


def write_provider_market_data_imbalance_cutover(
    provider_broker_readiness_dir: str | Path,
    output_dir: str | Path,
    *,
    scaleup_dir: str | Path | None = None,
    broker_readiness_dir: str | Path | None = None,
    runtime_session_dir: str | Path | None = None,
    operator_review_path: str | Path | None = None,
    config: ProviderMarketDataImbalanceCutoverConfig | None = None,
) -> ProviderMarketDataImbalanceCutoverReport:
    config = config or ProviderMarketDataImbalanceCutoverConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    provider_root = Path(provider_broker_readiness_dir)
    provider_summary, provider_summary_error = _read_csv(
        provider_root / "provider_market_data_imbalance_broker_readiness_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_root / "provider_market_data_imbalance_broker_readiness_config.json"
    )
    inferred_scaleup_dir = _inferred_scaleup_dir(provider_summary, provider_config)
    inferred_broker_readiness_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "broker_readiness_dir")),
        _path_from_text((provider_config.get("broker_readiness", {}) or {}).get("output_dir")),
    )
    inferred_runtime_session_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "runtime_session_dir")),
        _path_from_text((provider_config.get("broker_inputs", {}) or {}).get("runtime_session_dir")),
    )
    resolved_scaleup_dir = _explicit_or_inferred(scaleup_dir, inferred_scaleup_dir, config)
    resolved_broker_readiness_dir = _explicit_or_inferred(
        broker_readiness_dir,
        inferred_broker_readiness_dir,
        config,
    )
    resolved_runtime_session_dir = _explicit_or_inferred(
        runtime_session_dir,
        inferred_runtime_session_dir,
        config,
    )
    resolved_operator_review_path = Path(operator_review_path) if operator_review_path is not None else None

    prechecks = _prechecks(
        provider_root,
        provider_summary,
        provider_summary_error,
        provider_config_error,
        resolved_scaleup_dir,
        resolved_broker_readiness_dir,
        resolved_runtime_session_dir,
        config,
    )
    cutover: CutoverGateReport | None = None
    cutover_error = ""
    cutover_dir = out / "cutover"
    if bool(prechecks["passed"].all()):
        try:
            cutover = write_cutover_gate_report(
                scaleup_dir=_path_or_empty(resolved_scaleup_dir),
                broker_readiness_dir=_path_or_empty(resolved_broker_readiness_dir),
                runtime_session_dir=resolved_runtime_session_dir,
                operator_review_path=resolved_operator_review_path,
                output_dir=cutover_dir,
                thresholds=_thresholds(config, provider_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            cutover_error = str(exc)
    else:
        cutover_error = "provider imbalance cutover prerequisites are not ready"

    checks = _checks(prechecks, cutover, cutover_error, provider_summary, config)
    summary = _summary(
        provider_root,
        resolved_scaleup_dir,
        resolved_broker_readiness_dir,
        resolved_runtime_session_dir,
        resolved_operator_review_path,
        cutover,
        checks,
        out,
        provider_summary,
    )
    action_queue = _action_queue(summary.iloc[0], checks, cutover)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        cutover,
        checks,
        action_queue,
        config,
        {
            "scaleup_dir": resolved_scaleup_dir,
            "broker_readiness_dir": resolved_broker_readiness_dir,
            "runtime_session_dir": resolved_runtime_session_dir,
            "operator_review_path": resolved_operator_review_path,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_cutover_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_cutover_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_cutover_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_cutover_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_cutover_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_broker_readiness_dir": provider_root}
    for name, value in {
        "scaleup": resolved_scaleup_dir,
        "broker_readiness": resolved_broker_readiness_dir,
        "runtime_session": resolved_runtime_session_dir,
        "operator_review": resolved_operator_review_path,
    }.items():
        if value is not None:
            inputs[name] = Path(value)
    if cutover is not None and cutover.output_dir is not None:
        inputs["cutover"] = cutover.output_dir

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config), "cutover_inputs": _jsonable(payload["cutover_inputs"])},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "cutover_ready": bool(summary.iloc[0]["cutover_ready"]),
            "profile": PROFILE,
            "strategy": str(summary.iloc[0]["strategy"]),
            "market": str(summary.iloc[0]["market"]),
        },
    )
    return ProviderMarketDataImbalanceCutoverReport(cutover, checks, summary, action_queue, payload, out)


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
    scaleup_dir: Path | None,
    broker_readiness_dir: Path | None,
    runtime_session_dir: Path | None,
    config: ProviderMarketDataImbalanceCutoverConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_broker_readiness_dir_exists",
                str(provider_root),
                "exists",
                True,
                provider_root.exists(),
                "provider imbalance broker-readiness directory is required",
            ),
            _check(
                "provider_broker_readiness_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance broker-readiness summary could not be read",
            ),
            _check(
                "provider_broker_readiness_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider imbalance broker-readiness config could not be read",
            ),
            _check(
                "provider_broker_readiness_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_broker_readiness_ready,
                "provider imbalance broker-readiness is not ready",
            ),
            _check(
                "nested_scaleup_config_exists",
                _path_text(scaleup_dir),
                "exists",
                True,
                bool(scaleup_dir and (scaleup_dir / "scaleup_config.json").exists()),
                "nested scaleup_config.json is required for cutover",
            ),
            _check(
                "nested_broker_readiness_summary_exists",
                _path_text(broker_readiness_dir),
                "exists",
                True,
                bool(broker_readiness_dir and (broker_readiness_dir / "broker_readiness_summary.csv").exists()),
                "nested broker_readiness_summary.csv is required for cutover",
            ),
            _check(
                "nested_runtime_session_summary_exists",
                _path_text(runtime_session_dir),
                "exists",
                True,
                bool(runtime_session_dir and (runtime_session_dir / "runtime_session_summary.csv").exists()),
                "nested runtime_session_summary.csv is required for cutover",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    cutover: CutoverGateReport | None,
    cutover_error: str,
    provider_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceCutoverConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    cutover_summary = cutover.summary if cutover is not None else pd.DataFrame()
    rows.append(
        _check(
            "cutover_runnable",
            cutover_error or ("ran" if cutover is not None else "not_run"),
            "is",
            "ran",
            cutover is not None and not cutover_error,
            cutover_error or "generic cutover gate was not run",
        )
    )
    rows.append(
        _check(
            "cutover_ready",
            bool(cutover is not None and cutover.ready),
            "is",
            True,
            bool(cutover is not None and (cutover.ready or not config.require_cutover_ready)),
            _cutover_failure_reason(cutover) or "cutover gate is not ready",
        )
    )
    strategy = _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            _identity_key(strategy) == PROFILE,
            "provider cutover did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    cutover_market = _first_text(cutover_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            cutover_market or expected_market,
            "is",
            expected_market or "present",
            bool(cutover is not None)
            and bool(expected_market)
            and (not cutover_market or _identity_key(cutover_market) == _identity_key(expected_market)),
            "cutover market identity does not match provider broker-readiness",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    provider_root: Path,
    scaleup_dir: Path | None,
    broker_readiness_dir: Path | None,
    runtime_session_dir: Path | None,
    operator_review_path: Path | None,
    cutover: CutoverGateReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    provider_summary: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    cutover_summary = cutover.summary if cutover is not None else pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_broker_readiness_ready": _first_bool(provider_summary, "ready"),
                "cutover_ready": bool(cutover is not None and cutover.ready),
                "provider_broker_readiness_dir": str(provider_root),
                "scaleup_dir": _path_text(scaleup_dir),
                "broker_readiness_dir": _path_text(broker_readiness_dir),
                "runtime_session_dir": _path_text(runtime_session_dir),
                "operator_review_path": _path_text(operator_review_path),
                "cutover_dir": "" if cutover is None else str(cutover.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(cutover_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(cutover_summary, "strategy")
                or _first_text(provider_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(cutover_summary, "target_mode")
                or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(cutover_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(cutover_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "max_orders": _first_text(cutover_summary, "max_orders"),
                "max_notional": _first_text(cutover_summary, "max_notional"),
                "operator_approved": _first_bool(cutover_summary, "operator_approved"),
                "cutover_recommendation": _first_text(cutover_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "prepare_provider_imbalance_route_enable"
                if ready
                else "repair_provider_imbalance_cutover",
                "next_gate": "review-route-enable" if ready else _blocked_next_gate(checks, cutover),
                "next_gate_help_command": _help_command_for_gate(
                    "review-route-enable" if ready else _blocked_next_gate(checks, cutover)
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
    cutover: CutoverGateReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_cutover_summary",
                    "component": "cutover",
                    "check": "cutover_ready",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "prepare_provider_imbalance_route_enable",
                    "reason": "provider imbalance cutover is clear for route-enable review",
                    "recommendation": "feed_cutover_into_route_enable",
                    "next_gate": "review-route-enable",
                    "next_gate_help_command": _help_command_for_gate("review-route-enable"),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, cutover)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_cutover_checks",
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
                "source": "provider_market_data_imbalance_cutover_checks",
                "component": "cutover",
                "check": "provider_cutover_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_cutover",
                "reason": "provider imbalance cutover is not ready",
                "recommendation": "rerun_provider_imbalance_cutover",
                "next_gate": "review-provider-market-data-imbalance-cutover",
                "next_gate_help_command": _help_command_for_gate("review-provider-market-data-imbalance-cutover"),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    cutover: CutoverGateReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceCutoverConfig,
    cutover_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "cutover_inputs": _jsonable(cutover_inputs),
        "summary": _series_record(summary),
        "provider_broker_readiness": _first_record(provider_summary),
        "provider_broker_readiness_config": provider_config,
        "cutover": {
            "evaluated": cutover is not None,
            "ready": False if cutover is None else bool(cutover.ready),
            "output_dir": "" if cutover is None else str(cutover.output_dir or ""),
            "summary": _first_record(None if cutover is None else cutover.summary),
            "authorization": _records(None if cutover is None else cutover.authorization),
            "checks": _records(None if cutover is None else cutover.checks),
            "action_queue": _records(None if cutover is None else cutover.action_queue),
            "config": {} if cutover is None or cutover.config is None else cutover.config,
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
        "# Provider Market Data Imbalance Cutover",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Target mode: {summary['target_mode']}",
        f"- Cutover dir: {summary['cutover_dir']}",
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
    config: ProviderMarketDataImbalanceCutoverConfig,
    provider_summary: pd.DataFrame,
) -> CutoverGateThresholds:
    return CutoverGateThresholds(
        target_mode=config.target_mode or _first_text(provider_summary, "target_mode") or "shadow",
        require_scaleup_ready=config.require_scaleup_ready,
        require_broker_readiness=config.require_broker_readiness,
        require_runtime_session=config.require_runtime_session,
        require_runtime_guard_continue=config.require_runtime_guard_continue,
        require_route_readiness=config.require_route_readiness,
        require_resume_gate=config.require_resume_gate,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        require_operator_approval=config.require_operator_approval,
        require_operator_identity_ack=config.require_operator_identity_ack,
        require_operator_limits_ack=config.require_operator_limits_ack,
        max_failed_scaleup_checks=config.max_failed_scaleup_checks,
    )


def _cutover_failure_reason(cutover: CutoverGateReport | None) -> str:
    if cutover is None or cutover.checks.empty:
        return ""
    failed = cutover.checks.loc[~cutover.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame, cutover: CutoverGateReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "review-provider-market-data-imbalance-cutover"
    return _next_gate_for_check(failed[0], cutover)


def _next_gate_for_check(check: str, cutover: CutoverGateReport | None) -> str:
    if check.startswith("provider_broker_readiness") or check.startswith("nested_broker_readiness"):
        return "review-provider-market-data-imbalance-broker-readiness"
    if check.startswith("nested_scaleup"):
        return "plan-provider-market-data-imbalance-scaleup"
    if check.startswith("nested_runtime_session"):
        return "monitor-provider-market-data-imbalance-runtime-session"
    if check == "cutover_ready" and cutover is not None:
        next_gate = _first_action_value(cutover.action_queue, "next_gate")
        return next_gate or "review-cutover-gate"
    if check.startswith("cutover"):
        return "review-cutover-gate"
    if check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "review-provider-market-data-imbalance-broker-readiness"
    return "review-provider-market-data-imbalance-cutover"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-broker-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-readiness --help"
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "monitor-provider-market-data-imbalance-runtime-session":
        return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-session --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    if next_gate == "review-route-readiness":
        return "python -m hft_cli review-route-readiness --help"
    if next_gate == "review-route-enable":
        return "python -m hft_cli review-route-enable --help"
    return "python -m hft_cli review-provider-market-data-imbalance-cutover --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_broker_readiness") or check.startswith("nested_broker_readiness"):
        return "provider_broker_readiness"
    if check.startswith("nested_scaleup"):
        return "scaleup"
    if check.startswith("nested_runtime_session"):
        return "runtime_session"
    if check.startswith("cutover"):
        return "cutover"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_cutover"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_broker_readiness") or check.startswith("nested_broker_readiness"):
        return "repair_provider_imbalance_broker_readiness"
    if check.startswith("nested_scaleup"):
        return "repair_provider_imbalance_scaleup"
    if check.startswith("nested_runtime_session"):
        return "repair_provider_imbalance_runtime_session"
    if check.startswith("cutover"):
        return "repair_cutover_gate_inputs"
    return "repair_provider_imbalance_cutover"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_broker_readiness") or check.startswith("nested_broker_readiness"):
        return "rerun_provider_broker_readiness_before_cutover"
    if check.startswith("nested_scaleup"):
        return "rerun_provider_scaleup_before_cutover"
    if check.startswith("nested_runtime_session"):
        return "rerun_provider_runtime_session_before_cutover"
    if check.startswith("cutover"):
        return "rerun_generic_cutover_gate_with_required_artifacts"
    return "repair_provider_cutover_inputs"


def _inferred_scaleup_dir(provider_summary: pd.DataFrame, provider_config: dict[str, Any]) -> Path | None:
    session_record = provider_config.get("provider_runtime_session", {}) or {}
    session_config = provider_config.get("provider_runtime_session_config", {}) or {}
    session_summary = session_config.get("summary", {}) or {}
    return _first_existing_path(
        _path_from_text(_first_text(provider_summary, "scaleup_dir")),
        _path_from_text(session_record.get("scaleup_dir")),
        _path_from_text(session_summary.get("scaleup_dir")),
    )


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred: Path | None,
    config: ProviderMarketDataImbalanceCutoverConfig,
) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    if not config.use_provider_broker_readiness_inputs:
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
