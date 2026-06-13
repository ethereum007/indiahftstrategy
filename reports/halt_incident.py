from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from reports.manifest import write_experiment_manifest


PROOF_REFRESH_COLUMNS = [
    "proof_refresh_required",
    "proof_refresh_provided",
    "proof_refresh_ready",
    "proof_refresh_strategy",
    "proof_refresh_market",
    "proof_refresh_mixed_identity",
    "proof_source",
]
PROOF_REFRESH_BOOL_COLUMNS = {
    "proof_refresh_required",
    "proof_refresh_provided",
    "proof_refresh_ready",
    "proof_refresh_mixed_identity",
}


@dataclass(frozen=True)
class HaltIncidentThresholds:
    require_guard_halt: bool = True
    require_response_ready: bool = True
    require_export_ready: bool = False
    require_execution_passed: bool = True


@dataclass(frozen=True)
class HaltIncidentReport:
    timeline: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_halt_incident(
    *,
    guard_summary: pd.DataFrame,
    guard_checks: pd.DataFrame | None = None,
    halt_response_summary: pd.DataFrame,
    halt_response_checks: pd.DataFrame | None = None,
    halt_export_summary: pd.DataFrame | None = None,
    halt_export_checks: pd.DataFrame | None = None,
    halt_execution_summary: pd.DataFrame,
    halt_execution_checks: pd.DataFrame | None = None,
    thresholds: HaltIncidentThresholds | None = None,
) -> HaltIncidentReport:
    thresholds = thresholds or HaltIncidentThresholds()
    guard_summary = _require_nonempty(guard_summary, "guard_summary")
    halt_response_summary = _require_nonempty(halt_response_summary, "halt_response_summary")
    halt_execution_summary = _require_nonempty(halt_execution_summary, "halt_execution_summary")
    guard_checks = _optional_frame(guard_checks)
    halt_response_checks = _optional_frame(halt_response_checks)
    halt_export_summary = _optional_frame(halt_export_summary)
    halt_export_checks = _optional_frame(halt_export_checks)
    halt_execution_checks = _optional_frame(halt_execution_checks)

    timeline = _timeline(
        guard_summary,
        guard_checks,
        halt_response_summary,
        halt_response_checks,
        halt_export_summary,
        halt_export_checks,
        halt_execution_summary,
        halt_execution_checks,
    )
    checks = _checks(
        guard_summary.iloc[0],
        halt_response_summary.iloc[0],
        halt_export_summary.iloc[0] if not halt_export_summary.empty else pd.Series(dtype=object),
        halt_execution_summary.iloc[0],
        export_provided=not halt_export_summary.empty,
        thresholds=thresholds,
    )
    summary = _summary(
        guard_summary.iloc[0],
        halt_response_summary.iloc[0],
        halt_export_summary.iloc[0] if not halt_export_summary.empty else pd.Series(dtype=object),
        halt_execution_summary.iloc[0],
        checks,
    )
    return HaltIncidentReport(timeline=timeline, checks=checks, summary=summary)


def write_halt_incident_report(
    *,
    guard_dir: str | Path,
    halt_response_dir: str | Path,
    halt_execution_dir: str | Path,
    output_dir: str | Path,
    halt_export_dir: str | Path | None = None,
    thresholds: HaltIncidentThresholds | None = None,
) -> HaltIncidentReport:
    guard = Path(guard_dir)
    response = Path(halt_response_dir)
    execution = Path(halt_execution_dir)
    export = Path(halt_export_dir) if halt_export_dir is not None else None
    thresholds = thresholds or HaltIncidentThresholds()
    report = evaluate_halt_incident(
        guard_summary=_read_required(guard / "runtime_guard_summary.csv"),
        guard_checks=_read_optional(guard / "runtime_guard_checks.csv"),
        halt_response_summary=_read_required(response / "halt_response_summary.csv"),
        halt_response_checks=_read_optional(response / "halt_response_checks.csv"),
        halt_export_summary=_read_optional(export / "halt_response_export_summary.csv") if export else None,
        halt_export_checks=_read_optional(export / "halt_response_export_checks.csv") if export else None,
        halt_execution_summary=_read_required(execution / "halt_execution_summary.csv"),
        halt_execution_checks=_read_optional(execution / "halt_execution_checks.csv"),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.timeline.to_csv(out / "halt_incident_timeline.csv", index=False)
    report.checks.to_csv(out / "halt_incident_checks.csv", index=False)
    report.summary.to_csv(out / "halt_incident_summary.csv", index=False)
    inputs = {
        "guard": guard,
        "halt_response": response,
        "halt_execution": execution,
    }
    if export is not None:
        inputs["halt_export"] = export
    write_experiment_manifest(
        out,
        run_type="halt_incident_review",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
    )
    return HaltIncidentReport(report.timeline, report.checks, report.summary, out)


def _timeline(
    guard_summary: pd.DataFrame,
    guard_checks: pd.DataFrame,
    response_summary: pd.DataFrame,
    response_checks: pd.DataFrame,
    export_summary: pd.DataFrame,
    export_checks: pd.DataFrame,
    execution_summary: pd.DataFrame,
    execution_checks: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        _timeline_row(
            1,
            "runtime_guard",
            "halt" if _guard_halted(guard_summary.iloc[0]) else "continue",
            _guard_halted(guard_summary.iloc[0]),
            guard_summary.iloc[0],
            guard_checks,
        ),
        _timeline_row(
            2,
            "halt_response",
            "ready" if _to_bool(response_summary.iloc[0].get("ready", False)) else "not_ready",
            _to_bool(response_summary.iloc[0].get("ready", False)),
            response_summary.iloc[0],
            response_checks,
        ),
    ]
    if not export_summary.empty:
        rows.append(
            _timeline_row(
                3,
                "halt_export",
                "ready" if _to_bool(export_summary.iloc[0].get("ready", False)) else "not_ready",
                _to_bool(export_summary.iloc[0].get("ready", False)),
                export_summary.iloc[0],
                export_checks,
            )
        )
    rows.append(
        _timeline_row(
            4,
            "halt_execution",
            "passed" if _to_bool(execution_summary.iloc[0].get("passed", False)) else "failed",
            _to_bool(execution_summary.iloc[0].get("passed", False)),
            execution_summary.iloc[0],
            execution_checks,
        )
    )
    return pd.DataFrame(rows)


def _timeline_row(
    sequence: int,
    component: str,
    status: str,
    passed: bool,
    summary: pd.Series,
    checks: pd.DataFrame,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "component": component,
        "status": status,
        "passed": bool(passed),
        "failed_checks": _component_failed_checks(summary, checks),
        "failed_check_names": _component_failed_check_names(summary, checks),
        "first_failed_reason": _component_first_failed_reason(summary, checks),
        "guard_failed_check_names": _summary_text(summary, "guard_failed_check_names")
        or _summary_text(summary, "failed_check_names"),
        "guard_first_failed_reason": _summary_text(summary, "guard_first_failed_reason")
        or _summary_text(summary, "first_failed_reason"),
        "strategy": str(summary.get("strategy", "")),
        "market": str(summary.get("market", "")),
        **_proof_refresh_context(summary),
        "scenario_key": str(summary.get("scenario_key", "")),
        "adapter": str(summary.get("adapter", "")),
        "recommendation": str(summary.get("recommendation", "")),
    }


def _checks(
    guard: pd.Series,
    response: pd.Series,
    export: pd.Series,
    execution: pd.Series,
    *,
    export_provided: bool,
    thresholds: HaltIncidentThresholds,
) -> pd.DataFrame:
    guard_halted = _guard_halted(guard)
    response_ready = _to_bool(response.get("ready", False))
    export_ready = export_provided and _to_bool(export.get("ready", False))
    execution_passed = _to_bool(execution.get("passed", False))
    return pd.DataFrame(
        [
            _check(
                "guard_halted",
                guard_halted,
                "is",
                True,
                guard_halted or not thresholds.require_guard_halt,
                "runtime guard did not request a halt",
            ),
            _check(
                "halt_response_ready",
                response_ready,
                "is",
                True,
                response_ready or not thresholds.require_response_ready,
                "halt response plan is not ready",
            ),
            _check(
                "halt_export_ready",
                "missing" if not export_provided else export_ready,
                "is",
                True,
                (not export_provided and not thresholds.require_export_ready) or export_ready,
                "halt response export is missing or not ready",
            ),
            _check(
                "halt_execution_passed",
                execution_passed,
                "is",
                True,
                execution_passed or not thresholds.require_execution_passed,
                "halt execution reconciliation did not pass",
            ),
        ]
    )


def _summary(
    guard: pd.Series,
    response: pd.Series,
    export: pd.Series,
    execution: pd.Series,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    guard_halted = _guard_halted(guard)
    status = "halt_completed" if passed and guard_halted else "halt_incomplete"
    if not guard_halted:
        status = "no_halt_review"
    guard_failed_names = _summary_text(guard, "failed_check_names") or _summary_text(
        response,
        "guard_failed_check_names",
    )
    guard_first_reason = _summary_text(guard, "first_failed_reason") or _summary_text(
        response,
        "guard_first_failed_reason",
    )
    proof_refresh = _proof_refresh_context(guard, fallback=response)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "incident_status": status,
                "strategy": str(guard.get("strategy", response.get("strategy", ""))),
                "market": str(guard.get("market", response.get("market", ""))),
                **proof_refresh,
                "scenario_key": str(guard.get("scenario_key", response.get("scenario_key", ""))),
                "adapter": str(guard.get("adapter", response.get("adapter", ""))),
                "guard_action": str(guard.get("guard_action", "")),
                "guard_failed_check_names": guard_failed_names,
                "guard_first_failed_reason": guard_first_reason,
                "response_ready": _to_bool(response.get("ready", False)),
                "export_ready": _to_bool(export.get("ready", False)) if not export.empty else False,
                "execution_passed": _to_bool(execution.get("passed", False)),
                "cancel_actions": int(_number(response, "cancel_orders", fallback=_number(execution, "cancel_actions", 0.0))),
                "flatten_actions": int(_number(response, "flatten_orders", fallback=_number(execution, "flatten_actions", 0.0))),
                "failed_checks": failed,
                "recommendation": "resume_only_after_new_scaleup_review" if passed else "keep_trading_disabled_and_investigate",
            }
        ]
    )


def _component_failed_checks(summary: pd.Series, checks: pd.DataFrame) -> int:
    if "failed_checks" in summary.index and not pd.isna(summary["failed_checks"]):
        return int(float(summary["failed_checks"]))
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _component_failed_check_names(summary: pd.Series, checks: pd.DataFrame) -> str:
    names = _summary_text(summary, "failed_check_names")
    if names:
        return names
    if checks.empty or "passed" not in checks.columns or "check" not in checks.columns:
        return ""
    failed = checks.loc[~checks["passed"].map(_to_bool), "check"]
    return ";".join(str(value) for value in failed.tolist())


def _component_first_failed_reason(summary: pd.Series, checks: pd.DataFrame) -> str:
    reason = _summary_text(summary, "first_failed_reason")
    if reason:
        return reason
    if checks.empty or "passed" not in checks.columns or "reason" not in checks.columns:
        return ""
    failed = checks.loc[~checks["passed"].map(_to_bool), "reason"]
    reasons = [_clean(value) for value in failed.tolist()]
    return next((value for value in reasons if value), "")


def _guard_halted(row: pd.Series) -> bool:
    return _to_bool(row.get("halted", False)) or str(row.get("guard_action", "")).strip().lower() == "halt"


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required halt incident input not found: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"required halt incident input is empty: {path}")
    return frame


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else float(fallback)


def _summary_text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row[column])


def _proof_refresh_context(summary: pd.Series, fallback: pd.Series | None = None) -> dict[str, object]:
    fallback = pd.Series(dtype=object) if fallback is None else fallback
    fields = {}
    for column in PROOF_REFRESH_COLUMNS:
        if column in PROOF_REFRESH_BOOL_COLUMNS:
            fields[column] = _summary_bool(summary, fallback, column)
        else:
            fields[column] = _summary_value(summary, fallback, column)
    return fields


def _summary_bool(row: pd.Series, fallback: pd.Series, column: str) -> bool:
    value = _raw_summary_value(row, column)
    if value is None:
        value = _raw_summary_value(fallback, column)
    return _to_bool(value) if value is not None else False


def _summary_value(row: pd.Series, fallback: pd.Series, column: str) -> str:
    value = _raw_summary_value(row, column)
    if value is None:
        value = _raw_summary_value(fallback, column)
    return _clean(value) if value is not None else ""


def _raw_summary_value(row: pd.Series, column: str) -> object | None:
    if row.empty or column not in row.index or pd.isna(row[column]):
        return None
    return row[column]


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "halt", "passed", "ready"}
    return bool(value)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }
