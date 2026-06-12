from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ResumeGateThresholds:
    require_incident_passed: bool = True
    require_scaleup_ready: bool = True
    require_same_scenario: bool = True
    require_same_adapter: bool = True
    require_operator_approval: bool = False
    max_failed_scaleup_checks: int = 0


@dataclass(frozen=True)
class ResumeGateReport:
    authorization: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_resume_gate(
    *,
    incident_summary: pd.DataFrame,
    scaleup_summary: pd.DataFrame,
    scaleup_checks: pd.DataFrame | None = None,
    scaleup_config: dict[str, Any] | None = None,
    operator_review: pd.DataFrame | None = None,
    thresholds: ResumeGateThresholds | None = None,
) -> ResumeGateReport:
    thresholds = thresholds or ResumeGateThresholds()
    _validate_thresholds(thresholds)
    incident_summary = _require_nonempty(incident_summary, "incident_summary")
    scaleup_summary = _require_nonempty(scaleup_summary, "scaleup_summary")
    scaleup_checks = pd.DataFrame() if scaleup_checks is None else scaleup_checks.copy().reset_index(drop=True)
    scaleup_config = scaleup_config or {}
    operator_review = pd.DataFrame() if operator_review is None else operator_review.copy().reset_index(drop=True)

    checks = _checks(
        incident_summary.iloc[0],
        scaleup_summary.iloc[0],
        scaleup_checks,
        operator_review,
        thresholds,
    )
    authorization = _authorization(incident_summary.iloc[0], scaleup_summary.iloc[0], scaleup_config, checks)
    summary = _summary(authorization.iloc[0], checks)
    config = _config(authorization.iloc[0], scaleup_config, thresholds, checks)
    return ResumeGateReport(authorization=authorization, checks=checks, summary=summary, config=config)


def write_resume_gate_report(
    *,
    incident_dir: str | Path,
    scaleup_dir: str | Path,
    output_dir: str | Path,
    operator_review_path: str | Path | None = None,
    thresholds: ResumeGateThresholds | None = None,
) -> ResumeGateReport:
    incident = Path(incident_dir)
    scaleup = Path(scaleup_dir)
    thresholds = thresholds or ResumeGateThresholds()
    scaleup_config_path = scaleup / "scaleup_config.json" if scaleup.is_dir() else Path(scaleup_dir)
    if not scaleup_config_path.exists():
        raise FileNotFoundError(f"scale-up config not found: {scaleup_config_path}")
    scaleup_summary_path = scaleup / "scaleup_summary.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_summary.csv")
    scaleup_checks_path = scaleup / "scaleup_checks.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_checks.csv")
    report = evaluate_resume_gate(
        incident_summary=_read_required(incident / "halt_incident_summary.csv"),
        scaleup_summary=_read_required(scaleup_summary_path),
        scaleup_checks=_read_optional(scaleup_checks_path),
        scaleup_config=json.loads(scaleup_config_path.read_text(encoding="utf-8")),
        operator_review=_read_optional(operator_review_path),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.authorization.to_csv(out / "resume_authorization.csv", index=False)
    report.checks.to_csv(out / "resume_checks.csv", index=False)
    report.summary.to_csv(out / "resume_summary.csv", index=False)
    (out / "resume_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs: dict[str, Any] = {"incident": incident, "scaleup": scaleup_config_path}
    if operator_review_path is not None:
        inputs["operator_review"] = Path(operator_review_path)
    write_experiment_manifest(
        out,
        run_type="resume_gate",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
    )
    return ResumeGateReport(report.authorization, report.checks, report.summary, report.config, out)


def _checks(
    incident: pd.Series,
    scaleup: pd.Series,
    scaleup_checks: pd.DataFrame,
    operator_review: pd.DataFrame,
    thresholds: ResumeGateThresholds,
) -> pd.DataFrame:
    incident_passed = _to_bool(incident.get("passed", False))
    scaleup_ready = _to_bool(scaleup.get("ready", False))
    incident_scenario = str(incident.get("scenario_key", ""))
    scaleup_scenario = str(scaleup.get("scenario_key", ""))
    incident_adapter = str(incident.get("adapter", ""))
    scaleup_adapter = str(scaleup.get("adapter", ""))
    scaleup_failed = _failed_scaleup_checks(scaleup, scaleup_checks)
    operator_approved = _operator_approved(operator_review)
    return pd.DataFrame(
        [
            _check(
                "incident_passed",
                incident_passed,
                "is",
                True,
                incident_passed or not thresholds.require_incident_passed,
                "halt incident is not closed",
            ),
            _check(
                "scaleup_ready",
                scaleup_ready,
                "is",
                True,
                scaleup_ready or not thresholds.require_scaleup_ready,
                "scale-up plan is not ready",
            ),
            _check(
                "scenario_match",
                scaleup_scenario,
                "==",
                incident_scenario,
                scaleup_scenario == incident_scenario or not thresholds.require_same_scenario,
                "incident and scale-up scenario keys differ",
            ),
            _check(
                "adapter_match",
                scaleup_adapter,
                "==",
                incident_adapter,
                scaleup_adapter == incident_adapter or not thresholds.require_same_adapter,
                "incident and scale-up adapters differ",
            ),
            _check(
                "scaleup_failed_checks",
                scaleup_failed,
                "<=",
                thresholds.max_failed_scaleup_checks,
                scaleup_failed <= thresholds.max_failed_scaleup_checks,
                "scale-up checks still have failures",
            ),
            _check(
                "operator_approved",
                operator_approved if not operator_review.empty else "missing",
                "is",
                True,
                operator_approved or not thresholds.require_operator_approval,
                "operator approval is missing or false",
            ),
        ]
    )


def _authorization(
    incident: pd.Series,
    scaleup: pd.Series,
    scaleup_config: dict[str, Any],
    checks: pd.DataFrame,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    limits = scaleup_config.get("limits", {}) or {}
    kill_switches = scaleup_config.get("kill_switches", {}) or {}
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(scaleup.get("target_mode", scaleup_config.get("target_mode", ""))),
                "scenario_key": str(scaleup.get("scenario_key", scaleup_config.get("scenario_key", ""))),
                "adapter": str(scaleup.get("adapter", scaleup_config.get("adapter", ""))),
                "incident_status": str(incident.get("incident_status", "")),
                "max_orders_per_session": int(_number_from(limits, "max_orders_per_session", _number(scaleup, "max_orders_per_session", 0.0))),
                "max_notional_per_session": float(_number_from(limits, "max_notional_per_session", _number(scaleup, "max_notional_per_session", 0.0))),
                "stop_loss": _nullable_number(limits.get("stop_loss")),
                "max_total_failed_component_checks": _nullable_number(kill_switches.get("max_total_failed_component_checks")),
                "max_total_unmatched_fills": _nullable_number(kill_switches.get("max_total_unmatched_fills")),
                "max_total_mismatched_orders": _nullable_number(kill_switches.get("max_total_mismatched_orders")),
                "max_total_overfilled_orders": _nullable_number(kill_switches.get("max_total_overfilled_orders")),
                "max_lifecycle_orders": _nullable_number(kill_switches.get("max_lifecycle_orders")),
                "max_replace_orders": _nullable_number(kill_switches.get("max_replace_orders")),
                "max_abs_net_delta": _nullable_number(kill_switches.get("max_abs_net_delta")),
                "max_abs_net_vega": _nullable_number(kill_switches.get("max_abs_net_vega")),
            }
        ]
    )


def _summary(authorization: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(authorization.get("target_mode", "")),
                "scenario_key": str(authorization.get("scenario_key", "")),
                "adapter": str(authorization.get("adapter", "")),
                "failed_checks": failed,
                "recommendation": "resume_with_scaleup_controls" if ready else "keep_trading_disabled",
            }
        ]
    )


def _config(
    authorization: pd.Series,
    scaleup_config: dict[str, Any],
    thresholds: ResumeGateThresholds,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": bool(authorization["ready"]),
        "target_mode": str(authorization["target_mode"]),
        "scenario_key": str(authorization["scenario_key"]),
        "adapter": str(authorization["adapter"]),
        "limits": scaleup_config.get("limits", {}),
        "kill_switches": scaleup_config.get("kill_switches", {}),
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _read_required(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required resume gate input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required resume gate input is empty: {file_path}")
    return frame


def _read_optional(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_csv(file_path)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _failed_scaleup_checks(scaleup: pd.Series, checks: pd.DataFrame) -> int:
    if "failed_checks" in scaleup.index and not pd.isna(scaleup["failed_checks"]):
        return int(float(scaleup["failed_checks"]))
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _operator_approved(operator_review: pd.DataFrame) -> bool:
    if operator_review.empty:
        return False
    row = operator_review.iloc[-1]
    for column in ("approved", "resume_approved", "allow_resume"):
        if column in row.index:
            return _to_bool(row[column])
    return False


def _validate_thresholds(thresholds: ResumeGateThresholds) -> None:
    if thresholds.max_failed_scaleup_checks < 0:
        raise ValueError("max_failed_scaleup_checks must be non-negative")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return fallback
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else fallback


def _number_from(mapping: dict[str, Any], key: str, fallback: float) -> float:
    value = mapping.get(key, fallback)
    return fallback if value is None or pd.isna(value) else float(value)


def _nullable_number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed"}
    return bool(value)


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
