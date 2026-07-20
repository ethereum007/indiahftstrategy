from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.leadlag_candidate_contract import (
    candidate_replay_latency_ns,
    edge_audit,
    edge_audit_bound,
    edge_latency_budget_ns,
    edge_metrics,
    latency_budget_respected,
    latency_headroom_ns,
    number,
)
from reports.manifest import (
    ManifestIntegrity,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from strategies.run_leadlag_replay import LEAD_LAG_STRATEGY


WALKFORWARD_RUN_TYPE = "leadlag_replay_walkforward"
WALKFORWARD_REQUIRED_ARTIFACTS = (
    "leadlag_replay_walkforward_folds.csv",
    "leadlag_replay_walkforward_checks.csv",
    "leadlag_replay_walkforward_summary.csv",
    "candidate_config.json",
)


@dataclass(frozen=True)
class LeadLagCandidatePromotionThresholds:
    require_walkforward_passed: bool = True
    require_candidate_ready: bool = True
    require_edge_audit_bound: bool = True
    min_proof_pass_rate: float = 1.0
    min_total_fills: int = 1
    min_total_net_pnl: float = 0.0
    max_worst_drawdown: float | None = None
    min_median_markout_mean: float | None = None


@dataclass(frozen=True)
class LeadLagCandidatePromotionReport:
    candidate: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_leadlag_candidate_promotion(
    walkforward_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    *,
    thresholds: LeadLagCandidatePromotionThresholds | None = None,
) -> LeadLagCandidatePromotionReport:
    thresholds = thresholds or LeadLagCandidatePromotionThresholds()
    _validate_thresholds(thresholds)
    _require(walkforward_summary, ["passed", "proof_pass_rate", "total_fills", "total_net_pnl"], "walkforward_summary")
    row = walkforward_summary.iloc[0]
    checks = _checks(row, candidate_config, thresholds)
    candidate = pd.DataFrame([_candidate_row(row, candidate_config)])
    summary = _summary(candidate, checks)
    config = _promotion_candidate_config(candidate.iloc[0], checks, summary.iloc[0], candidate_config, thresholds)
    return LeadLagCandidatePromotionReport(candidate, checks, summary, config)


def write_leadlag_candidate_promotion(
    walkforward_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: LeadLagCandidatePromotionThresholds | None = None,
) -> LeadLagCandidatePromotionReport:
    walkforward = Path(walkforward_path)
    summary_path = walkforward / "leadlag_replay_walkforward_summary.csv"
    candidate_path = walkforward / "candidate_config.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"leadlag_replay_walkforward_summary.csv not found: {summary_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")

    thresholds = thresholds or LeadLagCandidatePromotionThresholds()
    integrity = verify_experiment_manifest(
        walkforward / "manifest.json",
        expected_run_type=WALKFORWARD_RUN_TYPE,
        required_artifacts=WALKFORWARD_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    source_config = json.loads(candidate_path.read_text(encoding="utf-8"))
    base_report = evaluate_leadlag_candidate_promotion(
        pd.read_csv(summary_path),
        source_config,
        thresholds=thresholds,
    )
    checks = pd.concat(
        [_walkforward_manifest_check(integrity), base_report.checks],
        ignore_index=True,
    )
    summary = _summary(base_report.candidate, checks)
    summary["walkforward_manifest_current"] = bool(integrity.passed)
    summary["walkforward_manifest_error"] = str(integrity.error)
    candidate_config = _promotion_candidate_config(
        base_report.candidate.iloc[0],
        checks,
        summary.iloc[0],
        source_config,
        thresholds,
    )
    report = LeadLagCandidatePromotionReport(
        base_report.candidate,
        checks,
        summary,
        candidate_config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.candidate.to_csv(out / "promotion_candidate.csv", index=False)
    report.checks.to_csv(out / "promotion_checks.csv", index=False)
    report.summary.to_csv(out / "promotion_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(report.candidate_config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dependencies = manifest_dependency_paths(walkforward / "manifest.json")
    write_experiment_manifest(
        out,
        run_type="promotion_report",
        parameters={
            "strategy": LEAD_LAG_STRATEGY,
            "market": str(report.summary.iloc[0].get("market", "")) if not report.summary.empty else "",
            "thresholds": asdict(thresholds),
        },
        inputs={
            "walkforward": walkforward,
            "walkforward_manifest": walkforward / "manifest.json",
            "walkforward_dependencies": dependencies,
            "summary": summary_path,
            "candidate_config": candidate_path,
        },
        extra={
            "promotion_source": WALKFORWARD_RUN_TYPE,
            "walkforward_manifest_current": bool(integrity.passed),
        },
    )
    return LeadLagCandidatePromotionReport(
        report.candidate,
        report.checks,
        report.summary,
        report.candidate_config,
        out,
    )


def _walkforward_manifest_check(
    integrity: ManifestIntegrity,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "check": "walkforward_manifest_current",
                "value": float(bool(integrity.passed)),
                "operator": "is",
                "threshold": 1.0,
                "passed": bool(integrity.passed),
                "reason": (
                    ""
                    if integrity.passed
                    else "lead-lag replay walk-forward manifest failed: "
                    f"{integrity.error or 'verification_failed'}"
                ),
            }
        ]
    )


def _checks(
    row: pd.Series,
    candidate_config: dict[str, Any],
    thresholds: LeadLagCandidatePromotionThresholds,
) -> pd.DataFrame:
    walkforward_passed = _to_bool(row.get("passed", False))
    candidate_ready = _to_bool(candidate_config.get("ready", False))
    audit_bound = edge_audit_bound(candidate_config)
    budget_respected = latency_budget_respected(candidate_config)
    checks = [
        _check(
            "walkforward_passed",
            walkforward_passed,
            "is",
            True,
            walkforward_passed or not thresholds.require_walkforward_passed,
            "lead-lag replay walk-forward did not pass",
        ),
        _check(
            "candidate_config_ready",
            candidate_ready,
            "is",
            True,
            candidate_ready or not thresholds.require_candidate_ready,
            "source candidate_config.json is not ready",
        ),
        _check(
            "edge_audit_bound",
            audit_bound,
            "is",
            True,
            audit_bound or not thresholds.require_edge_audit_bound,
            "candidate is not bound to a passed, current lead-lag edge audit",
        ),
        _check(
            "edge_latency_budget_respected",
            budget_respected,
            "is",
            True,
            budget_respected or not thresholds.require_edge_audit_bound,
            "walk-forward replay latency exceeds or omits the measured edge budget",
        ),
        _threshold_check("proof_pass_rate", _float(row, "proof_pass_rate"), ">=", thresholds.min_proof_pass_rate),
        _threshold_check("total_fills", _float(row, "total_fills"), ">=", thresholds.min_total_fills),
        _threshold_check("total_net_pnl", _float(row, "total_net_pnl"), ">=", thresholds.min_total_net_pnl),
    ]
    if thresholds.max_worst_drawdown is not None:
        checks.append(_threshold_check("worst_drawdown", _float(row, "worst_drawdown"), "<=", thresholds.max_worst_drawdown))
    if thresholds.min_median_markout_mean is not None:
        checks.append(
            _threshold_check(
                "median_markout_mean",
                _float(row, "median_markout_mean"),
                ">=",
                thresholds.min_median_markout_mean,
            )
        )
    return pd.DataFrame(checks)


def _candidate_row(row: pd.Series, candidate_config: dict[str, Any]) -> dict[str, Any]:
    replay_defaults = candidate_config.get("replay_defaults", {}) or {}
    if not isinstance(replay_defaults, dict):
        replay_defaults = {}
    scenario_key = _scenario_key(replay_defaults)
    audit_metrics = edge_metrics(candidate_config)
    return {
        "scenario_key": scenario_key,
        "strategy": LEAD_LAG_STRATEGY,
        "source_run_type": str(candidate_config.get("source_run_type", "")),
        "market": _jsonable(replay_defaults.get("market")),
        "leader_tick": _jsonable(replay_defaults.get("leader_tick")),
        "laggard_tick": _jsonable(replay_defaults.get("laggard_tick")),
        "delta": _jsonable(replay_defaults.get("delta")),
        "trigger_ticks": _jsonable(replay_defaults.get("trigger_ticks")),
        "qty": _jsonable(replay_defaults.get("qty")),
        "flat_after_ns": _jsonable(replay_defaults.get("flat_after_ns")),
        "cooloff_ns": _jsonable(replay_defaults.get("cooloff_ns")),
        "proof_pass_rate": _float(row, "proof_pass_rate"),
        "fold_count": _int(row, "fold_count"),
        "proof_passed_folds": _int(row, "proof_passed_folds"),
        "total_net_pnl": _float(row, "total_net_pnl"),
        "median_net_pnl": _float(row, "median_net_pnl"),
        "min_net_pnl": _float(row, "min_net_pnl"),
        "total_fills": _int(row, "total_fills"),
        "median_fills": _float(row, "median_fills"),
        "worst_drawdown": _float(row, "worst_drawdown"),
        "median_markout_mean": _float(row, "median_markout_mean"),
        "median_robust_score": _float(row, "median_robust_score"),
        "edge_audit_bound": edge_audit_bound(candidate_config),
        "edge_latency_budget_ns": edge_latency_budget_ns(candidate_config),
        "total_replay_latency_ns": candidate_replay_latency_ns(candidate_config),
        "edge_latency_headroom_ns": latency_headroom_ns(candidate_config),
        "edge_best_latency_avg_net_edge": number(
            audit_metrics.get("best_latency_avg_net_edge")
        ),
        "edge_best_latency_cost_drag_ratio": number(
            audit_metrics.get("best_latency_cost_drag_ratio")
        ),
        "edge_best_latency_net_edge_bps": number(
            audit_metrics.get("best_latency_net_edge_bps")
        ),
    }


def _summary(candidate: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    row = candidate.iloc[0] if not candidate.empty else pd.Series(dtype=object)
    key = str(row.get("scenario_key", ""))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": key,
                "strategy": str(row.get("strategy", "")),
                "market": str(row.get("market", "")),
                "checks": int(len(checks)),
                "failed_checks": failed,
                "edge_audit_bound": _to_bool(
                    row.get("edge_audit_bound", False)
                ),
                "edge_latency_budget_ns": row.get(
                    "edge_latency_budget_ns", np.nan
                ),
                "total_replay_latency_ns": row.get(
                    "total_replay_latency_ns", np.nan
                ),
                "edge_latency_headroom_ns": row.get(
                    "edge_latency_headroom_ns", np.nan
                ),
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
            }
        ]
    )


def _promotion_candidate_config(
    candidate: pd.Series,
    checks: pd.DataFrame,
    summary: pd.Series,
    source_config: dict[str, Any],
    thresholds: LeadLagCandidatePromotionThresholds,
) -> dict[str, Any]:
    replay_defaults = source_config.get("replay_defaults", {}) if isinstance(source_config.get("replay_defaults", {}), dict) else {}
    failed_checks = list(source_config.get("failed_checks", []) or [])
    failed_checks.extend(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist())
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "strategy": LEAD_LAG_STRATEGY,
        "scenario_key": str(candidate["scenario_key"]),
        "parameters": {
            "market": _jsonable(candidate.get("market")),
            "leader_tick": _jsonable(candidate.get("leader_tick")),
            "laggard_tick": _jsonable(candidate.get("laggard_tick")),
            "delta": _jsonable(candidate.get("delta")),
            "trigger_ticks": _jsonable(candidate.get("trigger_ticks")),
            "qty": _jsonable(candidate.get("qty")),
            "flat_after_ns": _jsonable(candidate.get("flat_after_ns")),
            "cooloff_ns": _jsonable(candidate.get("cooloff_ns")),
        },
        "replay_defaults": _jsonable(replay_defaults),
        "metrics": {
            "proof_pass_rate": _jsonable(candidate.get("proof_pass_rate")),
            "fold_count": _jsonable(candidate.get("fold_count")),
            "proof_passed_folds": _jsonable(candidate.get("proof_passed_folds")),
            "total_net_pnl": _jsonable(candidate.get("total_net_pnl")),
            "median_net_pnl": _jsonable(candidate.get("median_net_pnl")),
            "min_net_pnl": _jsonable(candidate.get("min_net_pnl")),
            "total_fills": _jsonable(candidate.get("total_fills")),
            "median_fills": _jsonable(candidate.get("median_fills")),
            "worst_drawdown": _jsonable(candidate.get("worst_drawdown")),
            "median_markout_mean": _jsonable(candidate.get("median_markout_mean")),
            "median_robust_score": _jsonable(candidate.get("median_robust_score")),
            "edge_latency_budget_ns": _jsonable(
                candidate.get("edge_latency_budget_ns")
            ),
            "total_replay_latency_ns": _jsonable(
                candidate.get("total_replay_latency_ns")
            ),
            "edge_latency_headroom_ns": _jsonable(
                candidate.get("edge_latency_headroom_ns")
            ),
            "edge_best_latency_avg_net_edge": _jsonable(
                candidate.get("edge_best_latency_avg_net_edge")
            ),
            "edge_best_latency_cost_drag_ratio": _jsonable(
                candidate.get("edge_best_latency_cost_drag_ratio")
            ),
            "edge_best_latency_net_edge_bps": _jsonable(
                candidate.get("edge_best_latency_net_edge_bps")
            ),
        },
        "edge_audit": _jsonable(edge_audit(source_config)),
        "source_candidate": _jsonable(source_config),
        "failed_checks": list(dict.fromkeys(failed_checks)),
        "thresholds": asdict(thresholds),
        "recommendation": str(summary["recommendation"]),
    }


def _scenario_key(replay_defaults: dict[str, Any]) -> str:
    pieces = [
        ("strategy", LEAD_LAG_STRATEGY),
        ("market", replay_defaults.get("market")),
        ("trigger_ticks", replay_defaults.get("trigger_ticks")),
        ("delta", replay_defaults.get("delta")),
        ("leader_tick", replay_defaults.get("leader_tick")),
        ("laggard_tick", replay_defaults.get("laggard_tick")),
    ]
    return "|".join(f"{key}={_format_value(value)}" for key, value in pieces)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float
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
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_thresholds(thresholds: LeadLagCandidatePromotionThresholds) -> None:
    if not 0 <= thresholds.min_proof_pass_rate <= 1:
        raise ValueError("min_proof_pass_rate must be between 0 and 1")
    if thresholds.min_total_fills < 0:
        raise ValueError("min_total_fills must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
    if frame.empty:
        raise ValueError(f"{name} must not be empty")


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _int(row: pd.Series, column: str) -> int:
    value = _float(row, column)
    return int(value) if not pd.isna(value) else 0


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _format_value(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)) and value.is_integer():
        return str(int(value))
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
