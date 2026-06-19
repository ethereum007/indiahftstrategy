from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.halt_response import HaltResponseConfig, HaltResponseReport, write_halt_response_plan
from reports.manifest import write_experiment_manifest
from reports.runtime_guard import RuntimeGuardReport, write_runtime_guard_report
from reports.runtime_telemetry import RuntimeTelemetryReport, write_runtime_telemetry_snapshot


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


@dataclass(frozen=True)
class RuntimeSessionMonitorReport:
    telemetry: RuntimeTelemetryReport
    guard: RuntimeGuardReport
    halt_response: HaltResponseReport | None
    steps: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    config: dict[str, Any] | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def write_runtime_session_monitor(
    *,
    scaleup_dir: str | Path,
    output_dir: str | Path,
    export_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    pnl_path: str | Path | None = None,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    snapshot_ts_ns: int | float | None = None,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
    plan_halt_response: bool = True,
    halt_response_config: HaltResponseConfig | None = None,
) -> RuntimeSessionMonitorReport:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    telemetry_dir = out / "01_telemetry"
    guard_dir = out / "02_guard"
    halt_response_dir = out / "03_halt_response"

    telemetry = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        output_dir=telemetry_dir,
        export_dir=export_dir,
        upload_pack_dir=upload_pack_dir,
        reconciliation_dir=reconciliation_dir,
        instrument_metadata_dir=instrument_metadata_dir,
        pnl_path=pnl_path,
        open_orders_path=open_orders_path,
        positions_path=positions_path,
        snapshot_ts_ns=snapshot_ts_ns,
    )
    guard = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry_dir,
        output_dir=guard_dir,
        as_of_ts_ns=as_of_ts_ns,
        max_telemetry_age_ns=max_telemetry_age_ns,
    )
    halt_response = None
    if guard.halted and plan_halt_response:
        halt_response = write_halt_response_plan(
            guard_dir=guard_dir,
            output_dir=halt_response_dir,
            open_orders_path=open_orders_path,
            positions_path=positions_path,
            config=halt_response_config,
        )

    steps = _steps(telemetry, guard, halt_response, plan_halt_response)
    summary = _summary(telemetry, guard, halt_response, steps, plan_halt_response)
    action_queue = _action_queue(telemetry, guard, halt_response, summary.iloc[0], plan_halt_response)
    summary = _summary_with_actions(summary, steps, action_queue)
    session_config = _config(summary.iloc[0], action_queue, plan_halt_response)
    steps.to_csv(out / "runtime_session_steps.csv", index=False)
    summary.to_csv(out / "runtime_session_summary.csv", index=False)
    action_queue.to_csv(out / "runtime_session_action_queue.csv", index=False)
    (out / "runtime_session_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    (out / "runtime_session_config.json").write_text(
        json.dumps(session_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="runtime_session_monitor",
        parameters={
            "snapshot_ts_ns": snapshot_ts_ns,
            "as_of_ts_ns": as_of_ts_ns,
            "max_telemetry_age_ns": max_telemetry_age_ns,
            "plan_halt_response": plan_halt_response,
            "halt_response_config": asdict(halt_response_config or HaltResponseConfig()),
        },
        inputs=_session_manifest_inputs(
            scaleup_dir=scaleup_dir,
            telemetry_dir=telemetry_dir,
            guard_dir=guard_dir,
            halt_response_dir=halt_response_dir if halt_response is not None else None,
            export_dir=export_dir,
            upload_pack_dir=upload_pack_dir,
            reconciliation_dir=reconciliation_dir,
            instrument_metadata_dir=instrument_metadata_dir,
            pnl_path=pnl_path,
            open_orders_path=open_orders_path,
            positions_path=positions_path,
        ),
    )
    return RuntimeSessionMonitorReport(
        telemetry=telemetry,
        guard=guard,
        halt_response=halt_response,
        steps=steps,
        summary=summary,
        output_dir=out,
        config=session_config,
        action_queue=action_queue,
    )


def _session_manifest_inputs(
    *,
    scaleup_dir: str | Path,
    telemetry_dir: Path,
    guard_dir: Path,
    halt_response_dir: Path | None,
    export_dir: str | Path | None,
    upload_pack_dir: str | Path | None,
    reconciliation_dir: str | Path | None,
    instrument_metadata_dir: str | Path | None,
    pnl_path: str | Path | None,
    open_orders_path: str | Path | None,
    positions_path: str | Path | None,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "scaleup": _scaleup_config_path(scaleup_dir),
    }
    for name, path in {
        "export": _optional_summary_path(
            export_dir,
            "broker_order_summary.csv",
            fallback_dirs=("04_export", "03_export"),
        ),
        "upload_pack": _optional_summary_path(
            upload_pack_dir,
            "broker_upload_summary.csv",
            fallback_dirs=("05_upload_pack", "04_upload_pack"),
        ),
        "reconciliation_summary": _optional_summary_path(reconciliation_dir, "reconciliation_summary.csv"),
        "reconciliation_checks": _optional_summary_path(reconciliation_dir, "reconciliation_checks.csv"),
        "instrument_metadata": _optional_summary_path(
            instrument_metadata_dir,
            "instrument_metadata_summary.csv",
        ),
        "pnl": _optional_file_path(pnl_path),
        "open_orders": _optional_file_path(open_orders_path),
        "positions": _optional_file_path(positions_path),
        "telemetry": telemetry_dir / "runtime_telemetry.csv",
        "telemetry_sources": telemetry_dir / "runtime_telemetry_sources.csv",
        "telemetry_checks": telemetry_dir / "runtime_telemetry_checks.csv",
        "telemetry_summary": telemetry_dir / "runtime_telemetry_summary.csv",
        "telemetry_manifest": telemetry_dir / "manifest.json",
        "guard_metrics": guard_dir / "runtime_guard_metrics.csv",
        "guard_checks": guard_dir / "runtime_guard_checks.csv",
        "guard_summary": guard_dir / "runtime_guard_summary.csv",
        "guard_manifest": guard_dir / "manifest.json",
    }.items():
        _add_existing_input(inputs, name, path)

    if halt_response_dir is not None:
        for name, path in {
            "halt_cancel_orders": halt_response_dir / "halt_cancel_orders.csv",
            "halt_flatten_orders": halt_response_dir / "halt_flatten_orders.csv",
            "halt_response_checks": halt_response_dir / "halt_response_checks.csv",
            "halt_response_summary": halt_response_dir / "halt_response_summary.csv",
            "halt_response_action_queue": halt_response_dir / "halt_response_action_queue.csv",
            "halt_response_runbook": halt_response_dir / "halt_response_runbook.md",
            "halt_response_config": halt_response_dir / "halt_response_config.json",
            "halt_response_manifest": halt_response_dir / "manifest.json",
        }.items():
            _add_existing_input(inputs, name, path)
    return inputs


def _scaleup_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "scaleup_config.json"
    return candidate


def _optional_summary_path(
    path: str | Path | None,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / filename
    if direct.exists():
        return direct
    return next(
        (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
        direct,
    )


def _optional_file_path(path: str | Path | None) -> Path | None:
    return Path(path) if path is not None else None


def _add_existing_input(inputs: dict[str, Any], name: str, path: Path | None) -> None:
    if path is not None and path.exists():
        inputs[name] = path


def _steps(
    telemetry: RuntimeTelemetryReport,
    guard: RuntimeGuardReport,
    halt_response: HaltResponseReport | None,
    plan_halt_response: bool,
) -> pd.DataFrame:
    telemetry_row = telemetry.summary.iloc[0]
    guard_row = guard.summary.iloc[0]
    rows: list[dict[str, Any]] = [
        {
            "step": "telemetry",
            "target_mode": _text(telemetry_row, "target_mode"),
            "strategy": _text(telemetry_row, "strategy"),
            "market": _text(telemetry_row, "market"),
            "status": "ready" if telemetry.ready else "blocked",
            "output_dir": str(telemetry.output_dir or ""),
            "failed_checks": int(telemetry_row.get("failed_checks", 0)),
            "failed_check_names": _text(telemetry_row, "failed_check_names"),
            "first_failed_reason": _text(telemetry_row, "first_failed_reason"),
            "proof_refresh_required": _bool_text(telemetry_row, "proof_refresh_required"),
            "proof_refresh_provided": _bool_text(telemetry_row, "proof_refresh_provided"),
            "proof_refresh_ready": _bool_text(telemetry_row, "proof_refresh_ready"),
            "proof_refresh_strategy": _text(telemetry_row, "proof_refresh_strategy"),
            "proof_refresh_market": _text(telemetry_row, "proof_refresh_market"),
            "proof_refresh_mixed_identity": _bool_text(telemetry_row, "proof_refresh_mixed_identity"),
            "proof_source": _text(telemetry_row, "proof_source"),
            "broker_resume_gate_required": _bool_text(telemetry_row, "broker_resume_gate_required"),
            "broker_resume_gate_provided": _bool_text(telemetry_row, "broker_resume_gate_provided"),
            "broker_resume_gate_ready": _bool_text(telemetry_row, "broker_resume_gate_ready"),
            "broker_resume_strategy": _text(telemetry_row, "broker_resume_strategy"),
            "broker_resume_market": _text(telemetry_row, "broker_resume_market"),
            "broker_resume_proof_refresh_ready": _bool_text(
                telemetry_row,
                "broker_resume_proof_refresh_ready",
            ),
            "broker_resume_proof_refresh_strategy": _text(telemetry_row, "broker_resume_proof_refresh_strategy"),
            "broker_resume_proof_refresh_market": _text(telemetry_row, "broker_resume_proof_refresh_market"),
            **_portfolio_fields(telemetry_row),
            "recommendation": str(telemetry_row.get("recommendation", "")),
        },
        {
            "step": "runtime_guard",
            "target_mode": _identity_text(guard_row, telemetry_row, "target_mode"),
            "strategy": _identity_text(guard_row, telemetry_row, "strategy"),
            "market": _identity_text(guard_row, telemetry_row, "market"),
            "status": "halt" if guard.halted else "continue",
            "output_dir": str(guard.output_dir or ""),
            "failed_checks": int(guard_row.get("failed_checks", 0)),
            "failed_check_names": _text(guard_row, "failed_check_names"),
            "first_failed_reason": _text(guard_row, "first_failed_reason"),
            "proof_refresh_required": _identity_bool(guard_row, telemetry_row, "proof_refresh_required"),
            "proof_refresh_provided": _identity_bool(guard_row, telemetry_row, "proof_refresh_provided"),
            "proof_refresh_ready": _identity_bool(guard_row, telemetry_row, "proof_refresh_ready"),
            "proof_refresh_strategy": _identity_text(guard_row, telemetry_row, "proof_refresh_strategy"),
            "proof_refresh_market": _identity_text(guard_row, telemetry_row, "proof_refresh_market"),
            "proof_refresh_mixed_identity": _identity_bool(
                guard_row,
                telemetry_row,
                "proof_refresh_mixed_identity",
            ),
            "proof_source": _identity_text(guard_row, telemetry_row, "proof_source"),
            "broker_resume_gate_required": _identity_bool(
                guard_row,
                telemetry_row,
                "broker_resume_gate_required",
            ),
            "broker_resume_gate_provided": _identity_bool(
                guard_row,
                telemetry_row,
                "broker_resume_gate_provided",
            ),
            "broker_resume_gate_ready": _identity_bool(guard_row, telemetry_row, "broker_resume_gate_ready"),
            "broker_resume_strategy": _identity_text(guard_row, telemetry_row, "broker_resume_strategy"),
            "broker_resume_market": _identity_text(guard_row, telemetry_row, "broker_resume_market"),
            "broker_resume_proof_refresh_ready": _identity_bool(
                guard_row,
                telemetry_row,
                "broker_resume_proof_refresh_ready",
            ),
            "broker_resume_proof_refresh_strategy": _identity_text(
                guard_row,
                telemetry_row,
                "broker_resume_proof_refresh_strategy",
            ),
            "broker_resume_proof_refresh_market": _identity_text(
                guard_row,
                telemetry_row,
                "broker_resume_proof_refresh_market",
            ),
            **_portfolio_fields(guard_row, telemetry_row),
            "recommendation": str(guard_row.get("recommendation", "")),
        },
    ]
    if guard.halted and halt_response is not None:
        response_row = halt_response.summary.iloc[0]
        rows.append(
            {
                "step": "halt_response",
                "target_mode": _identity_text(response_row, guard_row, "target_mode"),
                "strategy": _identity_text(response_row, guard_row, "strategy"),
                "market": _identity_text(response_row, guard_row, "market"),
                "status": "ready" if halt_response.ready else "blocked",
                "output_dir": str(halt_response.output_dir or ""),
                "failed_checks": int(response_row.get("failed_checks", 0)),
                "failed_check_names": _text(response_row, "guard_failed_check_names"),
                "first_failed_reason": _text(response_row, "guard_first_failed_reason"),
                "proof_refresh_required": _identity_bool(guard_row, telemetry_row, "proof_refresh_required"),
                "proof_refresh_provided": _identity_bool(guard_row, telemetry_row, "proof_refresh_provided"),
                "proof_refresh_ready": _identity_bool(guard_row, telemetry_row, "proof_refresh_ready"),
                "proof_refresh_strategy": _identity_text(guard_row, telemetry_row, "proof_refresh_strategy"),
                "proof_refresh_market": _identity_text(guard_row, telemetry_row, "proof_refresh_market"),
                "proof_refresh_mixed_identity": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "proof_refresh_mixed_identity",
                ),
                "proof_source": _identity_text(guard_row, telemetry_row, "proof_source"),
                "broker_resume_gate_required": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_gate_required",
                ),
                "broker_resume_gate_provided": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_gate_provided",
                ),
                "broker_resume_gate_ready": _identity_bool(guard_row, telemetry_row, "broker_resume_gate_ready"),
                "broker_resume_strategy": _identity_text(guard_row, telemetry_row, "broker_resume_strategy"),
                "broker_resume_market": _identity_text(guard_row, telemetry_row, "broker_resume_market"),
                "broker_resume_proof_refresh_ready": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_ready",
                ),
                "broker_resume_proof_refresh_strategy": _identity_text(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_strategy",
                ),
                "broker_resume_proof_refresh_market": _identity_text(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_market",
                ),
                **_portfolio_fields(guard_row, telemetry_row),
                "recommendation": str(response_row.get("recommendation", "")),
            }
        )
    elif guard.halted:
        rows.append(
            {
                "step": "halt_response",
                "target_mode": _identity_text(guard_row, telemetry_row, "target_mode"),
                "strategy": _identity_text(guard_row, telemetry_row, "strategy"),
                "market": _identity_text(guard_row, telemetry_row, "market"),
                "status": "skipped",
                "output_dir": "",
                "failed_checks": 0,
                "failed_check_names": _text(guard_row, "failed_check_names"),
                "first_failed_reason": _text(guard_row, "first_failed_reason"),
                "proof_refresh_required": _identity_bool(guard_row, telemetry_row, "proof_refresh_required"),
                "proof_refresh_provided": _identity_bool(guard_row, telemetry_row, "proof_refresh_provided"),
                "proof_refresh_ready": _identity_bool(guard_row, telemetry_row, "proof_refresh_ready"),
                "proof_refresh_strategy": _identity_text(guard_row, telemetry_row, "proof_refresh_strategy"),
                "proof_refresh_market": _identity_text(guard_row, telemetry_row, "proof_refresh_market"),
                "proof_refresh_mixed_identity": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "proof_refresh_mixed_identity",
                ),
                "proof_source": _identity_text(guard_row, telemetry_row, "proof_source"),
                "broker_resume_gate_required": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_gate_required",
                ),
                "broker_resume_gate_provided": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_gate_provided",
                ),
                "broker_resume_gate_ready": _identity_bool(guard_row, telemetry_row, "broker_resume_gate_ready"),
                "broker_resume_strategy": _identity_text(guard_row, telemetry_row, "broker_resume_strategy"),
                "broker_resume_market": _identity_text(guard_row, telemetry_row, "broker_resume_market"),
                "broker_resume_proof_refresh_ready": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_ready",
                ),
                "broker_resume_proof_refresh_strategy": _identity_text(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_strategy",
                ),
                "broker_resume_proof_refresh_market": _identity_text(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_market",
                ),
                **_portfolio_fields(guard_row, telemetry_row),
                "recommendation": "manual_halt_response_required" if not plan_halt_response else "not_created",
            }
        )
    return pd.DataFrame(rows)


def _summary(
    telemetry: RuntimeTelemetryReport,
    guard: RuntimeGuardReport,
    halt_response: HaltResponseReport | None,
    steps: pd.DataFrame,
    plan_halt_response: bool,
) -> pd.DataFrame:
    telemetry_row = telemetry.summary.iloc[0]
    guard_row = guard.summary.iloc[0]
    response_ready = bool(halt_response.ready) if halt_response is not None else False
    ready = bool(telemetry.ready and not guard.halted)
    failed_steps = int((steps["status"].isin(["blocked", "halt", "skipped"])).sum())
    recommendation = "continue_with_controls"
    if not telemetry.ready:
        recommendation = "fix_telemetry_before_routing"
    elif guard.halted and response_ready:
        recommendation = "stop_routing_and_execute_halt_response"
    elif guard.halted and plan_halt_response:
        recommendation = "stop_routing_and_fix_halt_response_inputs"
    elif guard.halted:
        recommendation = "stop_routing_and_prepare_manual_halt_response"

    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": str(guard_row.get("guard_action", "")),
                "halted": bool(guard.halted),
                "target_mode": _identity_text(guard_row, telemetry_row, "target_mode"),
                "strategy": _identity_text(guard_row, telemetry_row, "strategy"),
                "market": _identity_text(guard_row, telemetry_row, "market"),
                "scenario_key": str(guard_row.get("scenario_key", telemetry_row.get("scenario_key", ""))),
                "adapter": str(guard_row.get("adapter", telemetry_row.get("adapter", ""))),
                "orders_sent": int(float(guard_row.get("orders_sent", telemetry_row.get("orders_sent", 0)))),
                "session_notional": float(guard_row.get("session_notional", telemetry_row.get("session_notional", 0.0))),
                "realized_pnl": float(guard_row.get("realized_pnl", telemetry_row.get("realized_pnl", 0.0))),
                "guard_failed_check_names": _text(guard_row, "failed_check_names"),
                "guard_first_failed_reason": _text(guard_row, "first_failed_reason"),
                "proof_refresh_required": _identity_bool(guard_row, telemetry_row, "proof_refresh_required"),
                "proof_refresh_provided": _identity_bool(guard_row, telemetry_row, "proof_refresh_provided"),
                "proof_refresh_ready": _identity_bool(guard_row, telemetry_row, "proof_refresh_ready"),
                "proof_refresh_strategy": _identity_text(guard_row, telemetry_row, "proof_refresh_strategy"),
                "proof_refresh_market": _identity_text(guard_row, telemetry_row, "proof_refresh_market"),
                "proof_refresh_mixed_identity": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "proof_refresh_mixed_identity",
                ),
                "proof_source": _identity_text(guard_row, telemetry_row, "proof_source"),
                "broker_resume_gate_required": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_gate_required",
                ),
                "broker_resume_gate_provided": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_gate_provided",
                ),
                "broker_resume_gate_ready": _identity_bool(guard_row, telemetry_row, "broker_resume_gate_ready"),
                "broker_resume_strategy": _identity_text(guard_row, telemetry_row, "broker_resume_strategy"),
                "broker_resume_market": _identity_text(guard_row, telemetry_row, "broker_resume_market"),
                "broker_resume_proof_refresh_ready": _identity_bool(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_ready",
                ),
                "broker_resume_proof_refresh_strategy": _identity_text(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_strategy",
                ),
                "broker_resume_proof_refresh_market": _identity_text(
                    guard_row,
                    telemetry_row,
                    "broker_resume_proof_refresh_market",
                ),
                **_portfolio_fields(guard_row, telemetry_row),
                "telemetry_ready": bool(telemetry.ready),
                "halt_response_created": halt_response is not None,
                "halt_response_ready": response_ready,
                "failed_steps": failed_steps,
                "failed_checks": int(steps["failed_checks"].sum()),
                "recommendation": recommendation,
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, steps: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    failed_names = _failed_check_names(steps, out.iloc[0])
    primary_action = _first_action_record(action_queue)
    out["failed_check_count"] = int(out.iloc[0].get("failed_checks", 0))
    out["failed_check_names"] = failed_names
    out["first_failed_reason"] = _first_failed_reason(steps, out.iloc[0])
    out["primary_blocker_check"] = str(primary_action.get("check", ""))
    out["primary_blocker_value"] = str(primary_action.get("actual", ""))
    out["primary_blocker_operator"] = str(primary_action.get("operator", ""))
    out["primary_blocker_threshold"] = str(primary_action.get("expected", ""))
    out["primary_blocker_reason"] = str(primary_action.get("reason", ""))
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(
    telemetry: RuntimeTelemetryReport,
    guard: RuntimeGuardReport,
    halt_response: HaltResponseReport | None,
    summary_row: pd.Series,
    plan_halt_response: bool,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not telemetry.ready:
        telemetry_row = telemetry.summary.iloc[0]
        rows.append(
            {
                "queue_status": "blocked",
                "source": "runtime_session_summary",
                "component": "runtime_telemetry",
                "check": _text(telemetry_row, "failed_check_names") or "telemetry_ready",
                "actual": False,
                "operator": "is",
                "expected": True,
                "next_gate": "monitor-runtime-session",
                "reason": _text(telemetry_row, "first_failed_reason") or "runtime telemetry is not ready",
                "recommendation": "fix_runtime_telemetry_inputs_before_routing",
            }
        )
    elif guard.halted and halt_response is not None and halt_response.ready:
        rows.append(
            {
                "queue_status": "ready",
                "source": "runtime_session_summary",
                "component": "halt_response",
                "check": "guard_halted",
                "actual": _text(summary_row, "guard_action"),
                "operator": "is",
                "expected": "halt",
                "next_gate": "export-halt-response",
                "reason": _text(summary_row, "guard_first_failed_reason"),
                "recommendation": "export_and_execute_halt_response_packet",
            }
        )
    elif guard.halted and halt_response is not None:
        response_row = halt_response.summary.iloc[0]
        rows.append(
            {
                "queue_status": "blocked",
                "source": "runtime_session_summary",
                "component": "halt_response",
                "check": _text(response_row, "primary_blocker_check") or "halt_response_ready",
                "actual": _text(response_row, "primary_blocker_value") or False,
                "operator": _text(response_row, "primary_blocker_operator") or "is",
                "expected": _text(response_row, "primary_blocker_threshold") or True,
                "next_gate": "plan-halt-response",
                "reason": _text(response_row, "primary_blocker_reason") or "halt response plan is not ready",
                "recommendation": "repair_or_rerun_halt_response_plan",
            }
        )
    elif guard.halted and not plan_halt_response:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "runtime_session_summary",
                "component": "halt_response",
                "check": "halt_response_skipped",
                "actual": "skipped",
                "operator": "is",
                "expected": "created",
                "next_gate": "plan-halt-response",
                "reason": _text(summary_row, "guard_first_failed_reason") or "halt response planning was skipped",
                "recommendation": "rerun_with_halt_response_planning_or_prepare_manual_packet",
            }
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        item["next_gate_help_command"] = _help_command(str(item.get("next_gate", "")))
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _config(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    plan_halt_response: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready")),
        "halted": _to_bool(summary_row.get("halted")),
        "guard_action": _clean(summary_row.get("guard_action")),
        "strategy": _clean(summary_row.get("strategy")),
        "market": _clean(summary_row.get("market")),
        "scenario_key": _clean(summary_row.get("scenario_key")),
        "adapter": _clean(summary_row.get("adapter")),
        "plan_halt_response": bool(plan_halt_response),
        "halt_response_created": _to_bool(summary_row.get("halt_response_created")),
        "halt_response_ready": _to_bool(summary_row.get("halt_response_ready")),
        "failed_check_count": _int_value(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _clean(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _clean(summary_row.get("primary_blocker_check")),
            "value": _clean(summary_row.get("primary_blocker_value")),
            "operator": _clean(summary_row.get("primary_blocker_operator")),
            "threshold": _clean(summary_row.get("primary_blocker_threshold")),
            "reason": _clean(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _int_value(summary_row.get("action_queue_count")),
        "ready_action_count": _int_value(summary_row.get("ready_action_count")),
        "blocked_action_count": _int_value(summary_row.get("blocked_action_count")),
        "review_action_count": _int_value(summary_row.get("review_action_count")),
        "next_gate": _clean(summary_row.get("next_gate")),
        "next_gate_help_command": _clean(summary_row.get("next_gate_help_command")),
        "primary_action_status": _clean(summary_row.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary.get("ready")) else "no"
    halted_label = "yes" if _to_bool(summary.get("halted")) else "no"
    lines = [
        "# Runtime Session Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Halted: {halted_label}",
        f"- Strategy: {_clean(summary.get('strategy'))}",
        f"- Market: {_clean(summary.get('market'))}",
        f"- Scenario: {_clean(summary.get('scenario_key'))}",
        f"- Adapter: {_clean(summary.get('adapter'))}",
        f"- Guard action: {_clean(summary.get('guard_action'))}",
        f"- Guard failed checks: {_clean(summary.get('guard_failed_check_names'))}",
        f"- Halt response created: {_clean(summary.get('halt_response_created'))}",
        f"- Halt response ready: {_clean(summary.get('halt_response_ready'))}",
        f"- Failed checks: {_int_value(summary.get('failed_check_count'))}",
        f"- Ready actions: {_int_value(summary.get('ready_action_count'))}",
        f"- Blocked actions: {_int_value(summary.get('blocked_action_count'))}",
        f"- Recommendation: {_clean(summary.get('recommendation'))}",
        f"- Primary next gate: {_code(summary.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No runtime-session actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _clean(item.get("priority")),
                    _clean(item.get("queue_status")),
                    _clean(item.get("component")),
                    _clean(item.get("check")),
                    _clean(item.get("actual")),
                    _clean(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _clean(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failed_check_names(steps: pd.DataFrame, summary_row: pd.Series) -> str:
    names: list[str] = []
    if not steps.empty and "failed_check_names" in steps.columns:
        for value in steps["failed_check_names"].tolist():
            names.extend(_split_items(value))
    if not names:
        names.extend(_split_items(summary_row.get("guard_failed_check_names")))
    return ";".join(dict.fromkeys(item for item in names if item))


def _first_failed_reason(steps: pd.DataFrame, summary_row: pd.Series) -> str:
    if not steps.empty and "first_failed_reason" in steps.columns:
        for value in steps["first_failed_reason"].tolist():
            text = _clean(value)
            if text:
                return text
    return _clean(summary_row.get("guard_first_failed_reason"))


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _clean(action_queue.iloc[0].get(column))


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_value(value) for key, value in row.items()}


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _split_items(value: object) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _clean(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _clean(value)
    return f"`{text}`" if text else ""


def _int_value(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _text(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value)


def _identity_text(primary: pd.Series, fallback: pd.Series, column: str) -> str:
    value = _text(primary, column).strip()
    return value if value else _text(fallback, column)


def _identity_bool(primary: pd.Series, fallback: pd.Series, column: str) -> bool:
    if column in primary and not pd.isna(primary.get(column)):
        return _to_bool(primary.get(column))
    return _bool_text(fallback, column)


def _portfolio_fields(primary: pd.Series, fallback: pd.Series | None = None) -> dict[str, object]:
    fallback = primary if fallback is None else fallback
    return {
        "strategy_portfolio_required": _identity_bool(primary, fallback, "strategy_portfolio_required"),
        "strategy_portfolio_provided": _identity_bool(primary, fallback, "strategy_portfolio_provided"),
        "strategy_portfolio_ready": _identity_bool(primary, fallback, "strategy_portfolio_ready"),
        "strategy_portfolio_deployment_mode": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_deployment_mode",
        ),
        "strategy_portfolio_allocation_mode": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_allocation_mode",
        ),
        "strategy_portfolio_capital_currency": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_capital_currency",
        ),
        "strategy_portfolio_selected_profile": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_selected_profile",
        ),
        "strategy_portfolio_selected_strategy": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_selected_strategy",
        ),
        "strategy_portfolio_selected_market": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_selected_market",
        ),
        "strategy_portfolio_selected_eligible": _identity_bool(
            primary,
            fallback,
            "strategy_portfolio_selected_eligible",
        ),
        "strategy_portfolio_selected_allocation_weight": _identity_float(
            primary,
            fallback,
            "strategy_portfolio_selected_allocation_weight",
        ),
        "strategy_portfolio_selected_allocation_notional": _identity_float(
            primary,
            fallback,
            "strategy_portfolio_selected_allocation_notional",
        ),
        "strategy_portfolio_notional_cap_applied": _identity_bool(
            primary,
            fallback,
            "strategy_portfolio_notional_cap_applied",
        ),
        "strategy_portfolio_min_strategy_count": int(
            _identity_float(primary, fallback, "strategy_portfolio_min_strategy_count")
        ),
        "strategy_portfolio_min_market_count": int(
            _identity_float(primary, fallback, "strategy_portfolio_min_market_count")
        ),
        "strategy_portfolio_max_strategy_weight": _identity_float(
            primary,
            fallback,
            "strategy_portfolio_max_strategy_weight",
        ),
        "strategy_portfolio_max_market_weight": _identity_float(
            primary,
            fallback,
            "strategy_portfolio_max_market_weight",
        ),
        "strategy_portfolio_allocated_strategy_count": int(
            _identity_float(primary, fallback, "strategy_portfolio_allocated_strategy_count")
        ),
        "strategy_portfolio_allocated_market_count": int(
            _identity_float(primary, fallback, "strategy_portfolio_allocated_market_count")
        ),
        "strategy_portfolio_top_strategy_by_weight": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_top_strategy_by_weight",
        ),
        "strategy_portfolio_top_market_by_weight": _identity_text(
            primary,
            fallback,
            "strategy_portfolio_top_market_by_weight",
        ),
        "strategy_portfolio_max_strategy_allocation_weight": _identity_float(
            primary,
            fallback,
            "strategy_portfolio_max_strategy_allocation_weight",
        ),
        "strategy_portfolio_max_market_allocation_weight": _identity_float(
            primary,
            fallback,
            "strategy_portfolio_max_market_allocation_weight",
        ),
        "pre_portfolio_max_notional_per_session": _identity_float(
            primary,
            fallback,
            "pre_portfolio_max_notional_per_session",
        ),
    }


def _identity_float(primary: pd.Series, fallback: pd.Series, column: str) -> float:
    if column in primary and not pd.isna(primary.get(column)):
        return _to_float(primary.get(column))
    return _to_float(fallback.get(column, 0.0))


def _to_float(value: object) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _bool_text(row: pd.Series, column: str) -> bool:
    return _to_bool(row.get(column, False))


def _to_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready", "continue"}
    return bool(value)
