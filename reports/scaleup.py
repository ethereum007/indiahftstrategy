from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ScaleUpThresholds:
    target_mode: str = "shadow"
    max_scale_multiplier: float = 1.0
    min_shadow_sessions: int = 1
    min_shadow_acceptance_rate: float = 1.0
    min_median_order_fill_rate: float = 0.0
    min_worst_order_fill_rate: float | None = None
    max_worst_adverse_slippage: float | None = None
    max_total_failed_component_checks: int = 0
    max_total_unmatched_fills: int = 0
    max_total_mismatched_orders: int = 0
    max_total_overfilled_orders: int = 0
    max_orders_per_session: int | None = None
    max_session_notional: float | None = None
    max_gross_notional: float | None = None
    max_abs_net_delta: float | None = None
    max_abs_net_vega: float | None = None
    stop_loss: float | None = None
    allowed_adapters: tuple[str, ...] = ()
    require_proof_refresh: bool = False


@dataclass(frozen=True)
class ScaleUpPlanReport:
    plan: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_scaleup_plan(
    *,
    evidence_summary: pd.DataFrame,
    shadow_comparison_summary: pd.DataFrame,
    launch_summary: pd.DataFrame,
    order_exposure_summary: pd.DataFrame | None = None,
    proof_refresh_summary: pd.DataFrame | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ScaleUpPlanReport:
    thresholds = thresholds or ScaleUpThresholds()
    _validate_thresholds(thresholds)
    _require(evidence_summary, ["ready"], "strategy_evidence_summary")
    _require(shadow_comparison_summary, ["accepted", "session_count", "acceptance_rate"], "shadow_comparison_summary")
    _require(launch_summary, ["ready", "mode", "adapter", "scenario_key", "accepted_orders"], "launch_summary")
    exposure = order_exposure_summary if order_exposure_summary is not None else pd.DataFrame()
    proof_refresh = proof_refresh_summary if proof_refresh_summary is not None else pd.DataFrame()

    rows = {
        "evidence": evidence_summary.iloc[0],
        "shadow": shadow_comparison_summary.iloc[0],
        "launch": launch_summary.iloc[0],
        "exposure": exposure.iloc[0] if not exposure.empty else pd.Series(dtype=object),
        "proof_refresh": proof_refresh.iloc[0] if not proof_refresh.empty else pd.Series(dtype=object),
    }
    checks = _checks(rows, thresholds)
    ready = bool(checks["passed"].all()) if not checks.empty else False
    plan = _plan(rows, thresholds, ready)
    summary = _summary(plan.iloc[0], checks)
    config = _config(plan.iloc[0], checks, thresholds)
    return ScaleUpPlanReport(plan=plan, checks=checks, summary=summary, config=config)


def write_scaleup_plan(
    *,
    evidence_dir: str | Path,
    shadow_comparison_dir: str | Path,
    launch_dir: str | Path,
    output_dir: str | Path,
    order_exposure_dir: str | Path | None = None,
    proof_refresh_dir: str | Path | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ScaleUpPlanReport:
    evidence = _read_summary(evidence_dir, "strategy_evidence_summary.csv")
    shadow = _read_summary(shadow_comparison_dir, "shadow_session_comparison_summary.csv")
    launch = _read_summary(launch_dir, "launch_summary.csv")
    exposure = _read_optional_summary(order_exposure_dir, "order_exposure_summary.csv") if order_exposure_dir else None
    proof_refresh = (
        _read_optional_summary(proof_refresh_dir, "proof_refresh_summary.csv") if proof_refresh_dir else None
    )
    thresholds = thresholds or ScaleUpThresholds()
    report = evaluate_scaleup_plan(
        evidence_summary=evidence,
        shadow_comparison_summary=shadow,
        launch_summary=launch,
        order_exposure_summary=exposure,
        proof_refresh_summary=proof_refresh,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.plan.to_csv(out / "scaleup_plan.csv", index=False)
    report.checks.to_csv(out / "scaleup_checks.csv", index=False)
    report.summary.to_csv(out / "scaleup_summary.csv", index=False)
    (out / "scaleup_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs: dict[str, Any] = {
        "evidence": Path(evidence_dir),
        "shadow_comparison": Path(shadow_comparison_dir),
        "launch": Path(launch_dir),
    }
    if order_exposure_dir is not None:
        inputs["order_exposure"] = Path(order_exposure_dir)
    if proof_refresh_dir is not None:
        inputs["proof_refresh"] = Path(proof_refresh_dir)
    write_experiment_manifest(
        out,
        run_type="scaleup_plan",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
    )
    return ScaleUpPlanReport(report.plan, report.checks, report.summary, report.config, out)


def _checks(rows: dict[str, pd.Series], thresholds: ScaleUpThresholds) -> pd.DataFrame:
    evidence = rows["evidence"]
    shadow = rows["shadow"]
    launch = rows["launch"]
    exposure = rows["exposure"]
    proof_refresh = rows["proof_refresh"]
    adapter = str(launch.get("adapter", ""))
    scenario_match = str(launch.get("scenario_key", "")) == str(shadow.get("scenario_key", launch.get("scenario_key", "")))
    checks = [
        _check("evidence_ready", _to_bool(evidence.get("ready", False)), "is", True, _to_bool(evidence.get("ready", False)), "strategy evidence review is not ready"),
        _check("shadow_comparison_accepted", _to_bool(shadow.get("accepted", False)), "is", True, _to_bool(shadow.get("accepted", False)), "shadow comparison is not accepted"),
        _check("launch_ready", _to_bool(launch.get("ready", False)), "is", True, _to_bool(launch.get("ready", False)), "launch bundle is not ready"),
        _check("scenario_match", scenario_match, "is", True, scenario_match, "launch and shadow scenario keys differ"),
        _threshold_check("session_count", _number(shadow, "session_count"), ">=", thresholds.min_shadow_sessions),
        _threshold_check("acceptance_rate", _number(shadow, "acceptance_rate"), ">=", thresholds.min_shadow_acceptance_rate),
        _threshold_check("median_order_fill_rate", _number(shadow, "median_order_fill_rate"), ">=", thresholds.min_median_order_fill_rate),
        _threshold_check("total_failed_component_checks", _number(shadow, "total_failed_component_checks"), "<=", thresholds.max_total_failed_component_checks),
        _threshold_check("total_unmatched_fills", _number(shadow, "total_unmatched_fills"), "<=", thresholds.max_total_unmatched_fills),
        _threshold_check("total_mismatched_orders", _number(shadow, "total_mismatched_orders"), "<=", thresholds.max_total_mismatched_orders),
        _threshold_check("total_overfilled_orders", _number(shadow, "total_overfilled_orders"), "<=", thresholds.max_total_overfilled_orders),
    ]
    if thresholds.allowed_adapters:
        checks.append(
            _check(
                "adapter_allowed",
                adapter,
                "in",
                ";".join(thresholds.allowed_adapters),
                adapter in thresholds.allowed_adapters,
                "launch adapter is not in allowed adapter list",
            )
        )
    if thresholds.min_worst_order_fill_rate is not None:
        checks.append(_threshold_check("worst_order_fill_rate", _number(shadow, "worst_order_fill_rate"), ">=", thresholds.min_worst_order_fill_rate))
    if thresholds.max_worst_adverse_slippage is not None:
        checks.append(_threshold_check("worst_adverse_slippage", _number(shadow, "worst_adverse_slippage"), "<=", thresholds.max_worst_adverse_slippage))
    if thresholds.max_orders_per_session is not None:
        checks.append(_threshold_check("accepted_orders", _number(launch, "accepted_orders"), "<=", thresholds.max_orders_per_session))
    if thresholds.max_session_notional is not None:
        checks.append(_threshold_check("launch_total_notional", _number(launch, "total_notional"), "<=", thresholds.max_session_notional))
    if not exposure.empty:
        checks.append(_check("order_exposure_passed", _to_bool(exposure.get("passed", False)), "is", True, _to_bool(exposure.get("passed", False)), "order exposure report did not pass"))
        if thresholds.max_gross_notional is not None:
            checks.append(_threshold_check("gross_notional", _number(exposure, "gross_notional"), "<=", thresholds.max_gross_notional))
        if thresholds.max_abs_net_delta is not None:
            checks.append(_threshold_check("abs_net_delta", abs(_number(exposure, "net_delta")), "<=", thresholds.max_abs_net_delta))
        if thresholds.max_abs_net_vega is not None:
            checks.append(_threshold_check("abs_net_vega", abs(_number(exposure, "net_vega")), "<=", thresholds.max_abs_net_vega))
    if thresholds.require_proof_refresh:
        checks.append(
            _check(
                "proof_refresh_available",
                not proof_refresh.empty,
                "is",
                True,
                not proof_refresh.empty,
                "proof refresh gate is required but no proof refresh summary was supplied",
            )
        )
    if not proof_refresh.empty:
        proof_refresh_ready = _to_bool(proof_refresh.get("ready", False))
        checks.append(
            _check(
                "proof_refresh_ready",
                proof_refresh_ready,
                "is",
                True,
                proof_refresh_ready,
                "proof refresh gate is not ready",
            )
        )
    return pd.DataFrame(checks)


def _plan(rows: dict[str, pd.Series], thresholds: ScaleUpThresholds, ready: bool) -> pd.DataFrame:
    launch = rows["launch"]
    shadow = rows["shadow"]
    proof_refresh = rows["proof_refresh"]
    accepted_orders = int(_number(launch, "accepted_orders", fallback=0.0))
    launch_notional = _number(launch, "total_notional", fallback=0.0)
    scaled_orders = int(np.floor(accepted_orders * thresholds.max_scale_multiplier))
    scaled_notional = float(launch_notional * thresholds.max_scale_multiplier)
    if thresholds.max_orders_per_session is not None:
        scaled_orders = min(scaled_orders, int(thresholds.max_orders_per_session))
    if thresholds.max_session_notional is not None:
        scaled_notional = min(scaled_notional, float(thresholds.max_session_notional))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": thresholds.target_mode,
                "scenario_key": str(launch.get("scenario_key", "")),
                "adapter": str(launch.get("adapter", "")),
                "source_launch_mode": str(launch.get("mode", "")),
                "max_scale_multiplier": float(thresholds.max_scale_multiplier),
                "max_orders_per_session": scaled_orders,
                "max_notional_per_session": scaled_notional,
                "stop_loss": _jsonable(thresholds.stop_loss),
                "min_required_shadow_sessions": int(thresholds.min_shadow_sessions),
                "observed_shadow_sessions": int(_number(shadow, "session_count", fallback=0.0)),
                "observed_acceptance_rate": _number(shadow, "acceptance_rate"),
                "observed_median_fill_rate": _number(shadow, "median_order_fill_rate"),
                "observed_worst_fill_rate": _number(shadow, "worst_order_fill_rate"),
                "observed_worst_adverse_slippage": _number(shadow, "worst_adverse_slippage"),
                "proof_refresh_provided": not proof_refresh.empty,
                "proof_refresh_ready": _to_bool(proof_refresh.get("ready", False)) if not proof_refresh.empty else False,
                "proof_source": str(proof_refresh.get("proof_source", "")) if not proof_refresh.empty else "",
                "fresh_proof_required": _to_bool(proof_refresh.get("fresh_proof_required", False))
                if not proof_refresh.empty
                else False,
                "proof_refresh_recommendation": str(proof_refresh.get("recommendation", ""))
                if not proof_refresh.empty
                else "",
            }
        ]
    )


def _summary(plan_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(plan_row["ready"])
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(plan_row["target_mode"]),
                "scenario_key": str(plan_row["scenario_key"]),
                "adapter": str(plan_row["adapter"]),
                "max_orders_per_session": int(plan_row["max_orders_per_session"]),
                "max_notional_per_session": float(plan_row["max_notional_per_session"]),
                "proof_refresh_ready": _to_bool(plan_row["proof_refresh_ready"]),
                "proof_source": str(plan_row["proof_source"]),
                "failed_checks": failed,
                "recommendation": "scale_up_with_controls" if ready else "do_not_scale",
            }
        ]
    )


def _config(plan_row: pd.Series, checks: pd.DataFrame, thresholds: ScaleUpThresholds) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": bool(plan_row["ready"]),
        "target_mode": str(plan_row["target_mode"]),
        "scenario_key": str(plan_row["scenario_key"]),
        "adapter": str(plan_row["adapter"]),
        "limits": {
            "max_orders_per_session": int(plan_row["max_orders_per_session"]),
            "max_notional_per_session": float(plan_row["max_notional_per_session"]),
            "max_scale_multiplier": float(plan_row["max_scale_multiplier"]),
            "stop_loss": _jsonable(plan_row["stop_loss"]),
        },
        "kill_switches": {
            "max_total_failed_component_checks": thresholds.max_total_failed_component_checks,
            "max_total_unmatched_fills": thresholds.max_total_unmatched_fills,
            "max_total_mismatched_orders": thresholds.max_total_mismatched_orders,
            "max_total_overfilled_orders": thresholds.max_total_overfilled_orders,
            "max_worst_adverse_slippage": _jsonable(thresholds.max_worst_adverse_slippage),
        },
        "proof_freshness": {
            "required": bool(thresholds.require_proof_refresh),
            "provided": _to_bool(plan_row["proof_refresh_provided"]),
            "ready": _to_bool(plan_row["proof_refresh_ready"]),
            "proof_source": str(plan_row["proof_source"]),
            "fresh_proof_required": _to_bool(plan_row["fresh_proof_required"]),
            "recommendation": str(plan_row["proof_refresh_recommendation"]),
        },
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
        "thresholds": asdict(thresholds),
    }


def _read_summary(path: str | Path, filename: str) -> pd.DataFrame:
    file_path = _summary_path(path, filename)
    if not file_path.exists():
        raise FileNotFoundError(f"required scale-up input missing: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required scale-up input is empty: {file_path}")
    return frame


def _read_optional_summary(path: str | Path, filename: str) -> pd.DataFrame:
    file_path = _summary_path(path, filename)
    if not file_path.exists():
        return pd.DataFrame()
    return _read_summary(file_path, filename)


def _summary_path(path: str | Path, filename: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        return candidate / filename
    return candidate


def _validate_thresholds(thresholds: ScaleUpThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_scale_multiplier <= 0:
        raise ValueError("max_scale_multiplier must be positive")
    if thresholds.min_shadow_sessions <= 0:
        raise ValueError("min_shadow_sessions must be positive")
    for name in ("min_shadow_acceptance_rate", "min_median_order_fill_rate"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if thresholds.min_worst_order_fill_rate is not None and not 0 <= thresholds.min_worst_order_fill_rate <= 1:
        raise ValueError("min_worst_order_fill_rate must be between 0 and 1")
    for name in (
        "max_total_failed_component_checks",
        "max_total_unmatched_fills",
        "max_total_mismatched_orders",
        "max_total_overfilled_orders",
    ):
        if getattr(thresholds, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in ("max_orders_per_session", "max_session_notional", "max_gross_notional", "max_abs_net_delta", "max_abs_net_vega", "stop_loss"):
        value = getattr(thresholds, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


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


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _to_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
