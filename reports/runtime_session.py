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
