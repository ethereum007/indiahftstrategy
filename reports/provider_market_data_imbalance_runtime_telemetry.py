from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.runtime_telemetry import RuntimeTelemetryReport, write_runtime_telemetry_snapshot


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_runtime_telemetry_snapshot"


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRuntimeTelemetryConfig:
    require_provider_scaleup_ready: bool = True
    require_runtime_telemetry_ready: bool = True
    use_launch_pipeline_broker_inputs: bool = True


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRuntimeTelemetryReport:
    telemetry: RuntimeTelemetryReport | None
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


def write_provider_market_data_imbalance_runtime_telemetry_snapshot(
    provider_scaleup_dir: str | Path,
    output_dir: str | Path,
    *,
    export_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    pnl_path: str | Path | None = None,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    snapshot_ts_ns: int | float | None = None,
    config: ProviderMarketDataImbalanceRuntimeTelemetryConfig | None = None,
) -> ProviderMarketDataImbalanceRuntimeTelemetryReport:
    config = config or ProviderMarketDataImbalanceRuntimeTelemetryConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    scaleup_root = Path(provider_scaleup_dir)
    provider_summary, provider_summary_error = _read_csv(
        scaleup_root / "provider_market_data_imbalance_scaleup_summary.csv"
    )
    scaleup_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "scaleup_dir")),
        scaleup_root / "scaleup",
    )
    launch_pipeline_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "launch_pipeline_dir")),
        None,
    )
    resolved_export_dir = export_dir
    resolved_upload_pack_dir = upload_pack_dir
    if config.use_launch_pipeline_broker_inputs and launch_pipeline_dir is not None:
        if resolved_export_dir is None:
            resolved_export_dir = launch_pipeline_dir
        if resolved_upload_pack_dir is None:
            resolved_upload_pack_dir = launch_pipeline_dir

    telemetry: RuntimeTelemetryReport | None = None
    telemetry_error = ""
    telemetry_dir = out / "runtime_telemetry"
    prechecks = _prechecks(
        scaleup_root,
        provider_summary,
        provider_summary_error,
        scaleup_dir,
        launch_pipeline_dir,
        config,
    )
    if bool(prechecks["passed"].all()):
        try:
            telemetry = write_runtime_telemetry_snapshot(
                scaleup_dir=_path_or_empty(scaleup_dir),
                output_dir=telemetry_dir,
                export_dir=resolved_export_dir,
                upload_pack_dir=resolved_upload_pack_dir,
                reconciliation_dir=reconciliation_dir,
                instrument_metadata_dir=instrument_metadata_dir,
                pnl_path=pnl_path,
                open_orders_path=open_orders_path,
                positions_path=positions_path,
                snapshot_ts_ns=snapshot_ts_ns,
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            telemetry_error = str(exc)
    else:
        telemetry_error = "provider imbalance runtime telemetry prerequisites are not ready"

    checks = _checks(prechecks, telemetry, telemetry_error, provider_summary, config)
    summary = _summary(
        scaleup_root,
        scaleup_dir,
        launch_pipeline_dir,
        telemetry,
        checks,
        out,
        provider_summary,
        resolved_export_dir,
        resolved_upload_pack_dir,
    )
    action_queue = _action_queue(summary.iloc[0], checks, telemetry)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        telemetry,
        checks,
        action_queue,
        config,
        resolved_export_dir,
        resolved_upload_pack_dir,
        reconciliation_dir,
        instrument_metadata_dir,
        pnl_path,
        open_orders_path,
        positions_path,
        snapshot_ts_ns,
    )

    checks.to_csv(out / "provider_market_data_imbalance_runtime_telemetry_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_runtime_telemetry_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_runtime_telemetry_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_runtime_telemetry_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_runtime_telemetry_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_scaleup_dir": scaleup_root}
    if scaleup_dir is not None:
        inputs["scaleup"] = scaleup_dir
    if launch_pipeline_dir is not None:
        inputs["launch_pipeline"] = launch_pipeline_dir
    for name, value in {
        "export": resolved_export_dir,
        "upload_pack": resolved_upload_pack_dir,
        "reconciliation": reconciliation_dir,
        "instrument_metadata": instrument_metadata_dir,
        "pnl": pnl_path,
        "open_orders": open_orders_path,
        "positions": positions_path,
    }.items():
        if value is not None:
            inputs[name] = Path(value)
    if telemetry is not None and telemetry.output_dir is not None:
        inputs["runtime_telemetry"] = telemetry.output_dir

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config), "snapshot_ts_ns": snapshot_ts_ns},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "provider_scaleup_ready": bool(summary.iloc[0]["provider_scaleup_ready"]),
            "runtime_telemetry_ready": bool(summary.iloc[0]["runtime_telemetry_ready"]),
            "profile": PROFILE,
        },
    )
    return ProviderMarketDataImbalanceRuntimeTelemetryReport(
        telemetry,
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


def _prechecks(
    scaleup_root: Path,
    provider_summary: pd.DataFrame,
    provider_summary_error: str,
    scaleup_dir: Path | None,
    launch_pipeline_dir: Path | None,
    config: ProviderMarketDataImbalanceRuntimeTelemetryConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_scaleup_dir_exists",
                str(scaleup_root),
                "exists",
                True,
                scaleup_root.exists(),
                "provider imbalance scale-up directory is required",
            ),
            _check(
                "provider_scaleup_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance scale-up summary could not be read",
            ),
            _check(
                "provider_imbalance_scaleup_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_scaleup_ready,
                "provider imbalance scale-up plan is not ready",
            ),
            _check(
                "nested_scaleup_config_exists",
                _path_text(scaleup_dir),
                "exists",
                True,
                bool(scaleup_dir and (scaleup_dir / "scaleup_config.json").exists()),
                "nested scaleup_config.json is required for runtime telemetry",
            ),
            _check(
                "launch_pipeline_dir_resolved",
                _path_text(launch_pipeline_dir),
                "exists",
                True,
                (not config.use_launch_pipeline_broker_inputs) or bool(launch_pipeline_dir and launch_pipeline_dir.exists()),
                "provider launch pipeline directory is required for inferred export/upload telemetry inputs",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    telemetry: RuntimeTelemetryReport | None,
    telemetry_error: str,
    provider_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceRuntimeTelemetryConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    telemetry_ready = bool(telemetry.ready) if telemetry is not None else False
    telemetry_summary = telemetry.summary if telemetry is not None else pd.DataFrame()
    rows.append(
        _check(
            "runtime_telemetry_runnable",
            telemetry_error or ("ran" if telemetry is not None else "not_run"),
            "is",
            "ran",
            telemetry is not None and not telemetry_error,
            telemetry_error or "generic runtime telemetry builder was not run",
        )
    )
    rows.append(
        _check(
            "runtime_telemetry_ready",
            telemetry_ready,
            "is",
            True,
            telemetry_ready or not config.require_runtime_telemetry_ready,
            _telemetry_failure_reason(telemetry) or "runtime telemetry is not ready",
        )
    )
    rows.append(
        _check(
            "strategy_identity_imbalance",
            _first_text(telemetry_summary, "strategy") or _first_text(provider_summary, "strategy"),
            "is",
            PROFILE,
            (_first_text(telemetry_summary, "strategy") or _first_text(provider_summary, "strategy")) == PROFILE,
            "runtime telemetry did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    telemetry_market = _first_text(telemetry_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            telemetry_market or expected_market,
            "is",
            expected_market or "present",
            bool(telemetry_market)
            and (not expected_market or _identity_key(telemetry_market) == _identity_key(expected_market)),
            "runtime telemetry market identity does not match provider scale-up",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    scaleup_root: Path,
    scaleup_dir: Path | None,
    launch_pipeline_dir: Path | None,
    telemetry: RuntimeTelemetryReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    provider_summary: pd.DataFrame,
    export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    telemetry_summary = telemetry.summary if telemetry is not None else pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_scaleup_ready": _first_bool(provider_summary, "ready"),
                "runtime_telemetry_ready": bool(telemetry.ready) if telemetry is not None else False,
                "provider_scaleup_dir": str(scaleup_root),
                "scaleup_dir": _path_text(scaleup_dir),
                "launch_pipeline_dir": _path_text(launch_pipeline_dir),
                "runtime_telemetry_dir": "" if telemetry is None else str(telemetry.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(telemetry_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(telemetry_summary, "strategy") or _first_text(provider_summary, "strategy") or PROFILE,
                "target_mode": _first_text(telemetry_summary, "target_mode") or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(telemetry_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(telemetry_summary, "scenario_key") or _first_text(provider_summary, "scenario_key"),
                "orders_sent": int(_first_number(telemetry_summary, "orders_sent")),
                "session_notional": _first_number(telemetry_summary, "session_notional"),
                "total_failed_component_checks": _first_number(telemetry_summary, "failed_checks"),
                "export_dir": "" if export_dir is None else str(Path(export_dir)),
                "upload_pack_dir": "" if upload_pack_dir is None else str(Path(upload_pack_dir)),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "monitor_provider_imbalance_runtime_guard"
                if ready
                else "repair_provider_imbalance_runtime_telemetry",
                "next_gate": "monitor-scaleup-guard" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _help_command_for_gate("monitor-scaleup-guard")
                if ready
                else _blocked_help_command(checks),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    telemetry: RuntimeTelemetryReport | None,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "monitor_provider_imbalance_runtime_guard",
                    "reason": "provider imbalance runtime telemetry is ready for scale-up guard monitoring",
                    "next_gate": "monitor-scaleup-guard",
                    "next_gate_help_command": _help_command_for_gate("monitor-scaleup-guard"),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    for check in failed:
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": _reason_for_check(check, telemetry),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_runtime_telemetry",
                "reason": "provider imbalance runtime telemetry is not ready",
                "next_gate": "build-provider-market-data-imbalance-runtime-telemetry",
                "next_gate_help_command": _help_command_for_gate(
                    "build-provider-market-data-imbalance-runtime-telemetry"
                ),
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    telemetry: RuntimeTelemetryReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceRuntimeTelemetryConfig,
    export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
    reconciliation_dir: str | Path | None,
    instrument_metadata_dir: str | Path | None,
    pnl_path: str | Path | None,
    open_orders_path: str | Path | None,
    positions_path: str | Path | None,
    snapshot_ts_ns: int | float | None,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "runtime_inputs": {
            "export_dir": _path_text(Path(export_dir) if export_dir is not None else None),
            "upload_pack_dir": _path_text(Path(upload_pack_dir) if upload_pack_dir is not None else None),
            "reconciliation_dir": _path_text(Path(reconciliation_dir) if reconciliation_dir is not None else None),
            "instrument_metadata_dir": _path_text(
                Path(instrument_metadata_dir) if instrument_metadata_dir is not None else None
            ),
            "pnl_path": _path_text(Path(pnl_path) if pnl_path is not None else None),
            "open_orders_path": _path_text(Path(open_orders_path) if open_orders_path is not None else None),
            "positions_path": _path_text(Path(positions_path) if positions_path is not None else None),
            "snapshot_ts_ns": snapshot_ts_ns,
        },
        "summary": _series_record(summary),
        "provider_scaleup": _first_record(provider_summary),
        "runtime_telemetry": {
            "ready": False if telemetry is None else bool(telemetry.ready),
            "output_dir": "" if telemetry is None else str(telemetry.output_dir or ""),
            "summary": _first_record(None if telemetry is None else telemetry.summary),
            "sources": _records(None if telemetry is None else telemetry.sources),
            "checks": _records(None if telemetry is None else telemetry.checks),
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _telemetry_failure_reason(telemetry: RuntimeTelemetryReport | None) -> str:
    if telemetry is None or telemetry.checks.empty:
        return ""
    failed = telemetry.checks.loc[~telemetry.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "build-provider-market-data-imbalance-runtime-telemetry"
    return _next_gate_for_check(failed[0])


def _blocked_help_command(checks: pd.DataFrame) -> str:
    return _help_command_for_gate(_blocked_next_gate(checks))


def _next_gate_for_check(check: str) -> str:
    if check.startswith("provider_scaleup") or check.startswith("provider_imbalance_scaleup"):
        return "plan-provider-market-data-imbalance-scaleup"
    if check.startswith("nested_scaleup") or check.startswith("launch_pipeline"):
        return "plan-provider-market-data-imbalance-scaleup"
    if check.startswith("runtime_telemetry") or check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "build-runtime-telemetry"
    return "build-provider-market-data-imbalance-runtime-telemetry"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "build-runtime-telemetry":
        return "python -m hft_cli build-runtime-telemetry --help"
    if next_gate == "monitor-scaleup-guard":
        return "python -m hft_cli monitor-scaleup-guard --help"
    return "python -m hft_cli build-provider-market-data-imbalance-runtime-telemetry --help"


def _repair_action(check: str) -> str:
    if check.startswith("provider_scaleup") or check.startswith("provider_imbalance_scaleup"):
        return "repair_provider_imbalance_scaleup"
    if check.startswith("nested_scaleup") or check.startswith("launch_pipeline"):
        return "rebuild_provider_imbalance_scaleup"
    if check.startswith("runtime_telemetry"):
        return "repair_runtime_telemetry_snapshot"
    return "repair_provider_imbalance_runtime_telemetry"


def _reason_for_check(check: str, telemetry: RuntimeTelemetryReport | None) -> str:
    if check == "runtime_telemetry_ready":
        return _telemetry_failure_reason(telemetry) or "runtime telemetry is not ready"
    return check.replace("_", " ")


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Runtime Telemetry",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Target mode: {summary['target_mode']}",
        f"- Runtime telemetry dir: {summary['runtime_telemetry_dir']}",
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


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: str) -> Path | None:
    return Path(value) if value else None


def _path_or_empty(path: Path | None) -> Path:
    return path if path is not None else Path("__missing__")


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _identity_key(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _series_record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return _number(frame.iloc[0][column])


def _text(value: object, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "ready", "pass"}


def _number(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
