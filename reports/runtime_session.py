from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.halt_response import HaltResponseConfig, HaltResponseReport, write_halt_response_plan
from reports.manifest import write_experiment_manifest
from reports.runtime_guard import RuntimeGuardReport, write_runtime_guard_report
from reports.runtime_telemetry import RuntimeTelemetryReport, write_runtime_telemetry_snapshot


@dataclass(frozen=True)
class RuntimeSessionMonitorReport:
    telemetry: RuntimeTelemetryReport
    guard: RuntimeGuardReport
    halt_response: HaltResponseReport | None
    steps: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

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
    steps.to_csv(out / "runtime_session_steps.csv", index=False)
    summary.to_csv(out / "runtime_session_summary.csv", index=False)
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
        inputs={
            "scaleup": scaleup_dir,
            "export": export_dir,
            "upload_pack": upload_pack_dir,
            "reconciliation": reconciliation_dir,
            "instrument_metadata": instrument_metadata_dir,
            "pnl": pnl_path,
            "open_orders": open_orders_path,
            "positions": positions_path,
        },
    )
    return RuntimeSessionMonitorReport(
        telemetry=telemetry,
        guard=guard,
        halt_response=halt_response,
        steps=steps,
        summary=summary,
        output_dir=out,
    )


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
            "status": "ready" if telemetry.ready else "blocked",
            "output_dir": str(telemetry.output_dir or ""),
            "failed_checks": int(telemetry_row.get("failed_checks", 0)),
            "failed_check_names": _text(telemetry_row, "failed_check_names"),
            "first_failed_reason": _text(telemetry_row, "first_failed_reason"),
            "recommendation": str(telemetry_row.get("recommendation", "")),
        },
        {
            "step": "runtime_guard",
            "status": "halt" if guard.halted else "continue",
            "output_dir": str(guard.output_dir or ""),
            "failed_checks": int(guard_row.get("failed_checks", 0)),
            "failed_check_names": _text(guard_row, "failed_check_names"),
            "first_failed_reason": _text(guard_row, "first_failed_reason"),
            "recommendation": str(guard_row.get("recommendation", "")),
        },
    ]
    if guard.halted and halt_response is not None:
        response_row = halt_response.summary.iloc[0]
        rows.append(
            {
                "step": "halt_response",
                "status": "ready" if halt_response.ready else "blocked",
                "output_dir": str(halt_response.output_dir or ""),
                "failed_checks": int(response_row.get("failed_checks", 0)),
                "failed_check_names": _text(response_row, "guard_failed_check_names"),
                "first_failed_reason": _text(response_row, "guard_first_failed_reason"),
                "recommendation": str(response_row.get("recommendation", "")),
            }
        )
    elif guard.halted:
        rows.append(
            {
                "step": "halt_response",
                "status": "skipped",
                "output_dir": "",
                "failed_checks": 0,
                "failed_check_names": _text(guard_row, "failed_check_names"),
                "first_failed_reason": _text(guard_row, "first_failed_reason"),
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
                "scenario_key": str(guard_row.get("scenario_key", telemetry_row.get("scenario_key", ""))),
                "adapter": str(guard_row.get("adapter", telemetry_row.get("adapter", ""))),
                "orders_sent": int(float(guard_row.get("orders_sent", telemetry_row.get("orders_sent", 0)))),
                "session_notional": float(guard_row.get("session_notional", telemetry_row.get("session_notional", 0.0))),
                "realized_pnl": float(guard_row.get("realized_pnl", telemetry_row.get("realized_pnl", 0.0))),
                "guard_failed_check_names": _text(guard_row, "failed_check_names"),
                "guard_first_failed_reason": _text(guard_row, "first_failed_reason"),
                "telemetry_ready": bool(telemetry.ready),
                "halt_response_created": halt_response is not None,
                "halt_response_ready": response_ready,
                "failed_steps": failed_steps,
                "failed_checks": int(steps["failed_checks"].sum()),
                "recommendation": recommendation,
            }
        ]
    )


def _text(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value)
