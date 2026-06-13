from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class SettlementCandidatePromotionThresholds:
    require_walkforward_passed: bool = True
    require_candidate_ready: bool = True
    min_pass_rate: float = 1.0
    min_total_opportunities: int = 1
    min_total_net_edge: float = 0.0
    min_median_best_net_edge: float = 0.0
    min_median_known_fraction: float = 0.0


@dataclass(frozen=True)
class SettlementCandidatePromotionReport:
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


def evaluate_settlement_candidate_promotion(
    walkforward_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    *,
    thresholds: SettlementCandidatePromotionThresholds | None = None,
) -> SettlementCandidatePromotionReport:
    thresholds = thresholds or SettlementCandidatePromotionThresholds()
    _validate_thresholds(thresholds)
    _require(
        walkforward_summary,
        [
            "passed",
            "pass_rate",
            "total_opportunities",
            "total_net_edge",
            "median_best_net_edge",
            "median_known_fraction",
        ],
        "walkforward_summary",
    )
    row = walkforward_summary.iloc[0]
    checks = _checks(row, candidate_config, thresholds)
    candidate = pd.DataFrame([_candidate_row(row, candidate_config)])
    summary = _summary(candidate, checks)
    config = _promotion_candidate_config(candidate.iloc[0], checks, summary.iloc[0], candidate_config, thresholds)
    return SettlementCandidatePromotionReport(candidate, checks, summary, config)


def write_settlement_candidate_promotion(
    walkforward_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: SettlementCandidatePromotionThresholds | None = None,
) -> SettlementCandidatePromotionReport:
    walkforward = Path(walkforward_path)
    summary_path = walkforward / "settlement_convergence_walkforward_summary.csv"
    candidate_path = walkforward / "candidate_config.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"settlement_convergence_walkforward_summary.csv not found: {summary_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")

    thresholds = thresholds or SettlementCandidatePromotionThresholds()
    report = evaluate_settlement_candidate_promotion(
        pd.read_csv(summary_path),
        json.loads(candidate_path.read_text(encoding="utf-8")),
        thresholds=thresholds,
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
    write_experiment_manifest(
        out,
        run_type="promotion_report",
        parameters={
            "strategy": "settlement_convergence",
            "market": INDIA_NSE_INDEX_DERIVATIVES.name,
            "thresholds": asdict(thresholds),
        },
        inputs={"walkforward": walkforward, "summary": summary_path, "candidate_config": candidate_path},
        extra={"promotion_source": "settlement_convergence_walkforward"},
    )
    return SettlementCandidatePromotionReport(
        report.candidate,
        report.checks,
        report.summary,
        report.candidate_config,
        out,
    )


def _checks(
    row: pd.Series,
    candidate_config: dict[str, Any],
    thresholds: SettlementCandidatePromotionThresholds,
) -> pd.DataFrame:
    walkforward_passed = _to_bool(row.get("passed", False))
    candidate_ready = _to_bool(candidate_config.get("ready", False))
    return pd.DataFrame(
        [
            _check(
                "walkforward_passed",
                walkforward_passed,
                "is",
                True,
                walkforward_passed or not thresholds.require_walkforward_passed,
                "settlement convergence walk-forward did not pass",
            ),
            _check(
                "candidate_config_ready",
                candidate_ready,
                "is",
                True,
                candidate_ready or not thresholds.require_candidate_ready,
                "source candidate_config.json is not ready",
            ),
            _threshold_check("pass_rate", _float(row, "pass_rate"), ">=", thresholds.min_pass_rate),
            _threshold_check(
                "total_opportunities",
                _float(row, "total_opportunities"),
                ">=",
                thresholds.min_total_opportunities,
            ),
            _threshold_check("total_net_edge", _float(row, "total_net_edge"), ">=", thresholds.min_total_net_edge),
            _threshold_check(
                "median_best_net_edge",
                _float(row, "median_best_net_edge"),
                ">=",
                thresholds.min_median_best_net_edge,
            ),
            _threshold_check(
                "median_known_fraction",
                _float(row, "median_known_fraction"),
                ">=",
                thresholds.min_median_known_fraction,
            ),
        ]
    )


def _candidate_row(row: pd.Series, candidate_config: dict[str, Any]) -> dict[str, Any]:
    best = candidate_config.get("best_fold", {}) if isinstance(candidate_config.get("best_fold", {}), dict) else {}
    defaults = (
        candidate_config.get("research_defaults", {})
        if isinstance(candidate_config.get("research_defaults", {}), dict)
        else {}
    )
    scenario_key = _scenario_key(best, defaults)
    return {
        "scenario_key": scenario_key,
        "strategy": "settlement_convergence",
        "market": _jsonable(defaults.get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
        "source_run_type": str(candidate_config.get("source_run_type", "")),
        "best_fold": _jsonable(best.get("fold")),
        "best_ts": _jsonable(best.get("ts")),
        "best_expiry": _jsonable(best.get("expiry")),
        "best_strike": _jsonable(best.get("strike")),
        "best_option_type": _jsonable(best.get("option_type")),
        "best_direction": _jsonable(best.get("direction")),
        "best_side": _jsonable(best.get("side")),
        "best_touch_price": _jsonable(best.get("touch_price")),
        "best_trade_qty": _jsonable(best.get("trade_qty")),
        "best_projected_settlement": _jsonable(best.get("projected_settlement")),
        "best_projected_intrinsic": _jsonable(best.get("projected_intrinsic")),
        "best_gross_edge": _jsonable(best.get("gross_edge")),
        "best_gross_edge_ticks": _jsonable(best.get("gross_edge_ticks")),
        "best_cost": _jsonable(best.get("cost")),
        "fold_count": _int(row, "fold_count"),
        "passed_folds": _int(row, "passed_folds"),
        "pass_rate": _float(row, "pass_rate"),
        "total_opportunities": _int(row, "total_opportunities"),
        "total_net_edge": _float(row, "total_net_edge"),
        "median_best_net_edge": _float(row, "median_best_net_edge"),
        "best_net_edge": _float(row, "best_net_edge"),
        "median_known_fraction": _float(row, "median_known_fraction"),
        "min_known_fraction": _jsonable(defaults.get("min_known_fraction")),
        "min_gross_edge_ticks": _jsonable(defaults.get("min_gross_edge_ticks")),
        "min_net_edge": _jsonable(defaults.get("min_net_edge")),
        "qty": _jsonable(defaults.get("qty")),
        "depth_fraction": _jsonable(defaults.get("depth_fraction")),
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
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
            }
        ]
    )


def _promotion_candidate_config(
    candidate: pd.Series,
    checks: pd.DataFrame,
    summary: pd.Series,
    source_config: dict[str, Any],
    thresholds: SettlementCandidatePromotionThresholds,
) -> dict[str, Any]:
    failed_checks = list(source_config.get("failed_checks", []) or [])
    failed_checks.extend(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist())
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "strategy": "settlement_convergence",
        "scenario_key": str(candidate["scenario_key"]),
        "parameters": {
            "best_fold": _jsonable(candidate.get("best_fold")),
            "market": _jsonable(candidate.get("market")),
            "best_ts": _jsonable(candidate.get("best_ts")),
            "best_expiry": _jsonable(candidate.get("best_expiry")),
            "best_strike": _jsonable(candidate.get("best_strike")),
            "best_option_type": _jsonable(candidate.get("best_option_type")),
            "best_direction": _jsonable(candidate.get("best_direction")),
            "best_side": _jsonable(candidate.get("best_side")),
            "best_touch_price": _jsonable(candidate.get("best_touch_price")),
            "best_trade_qty": _jsonable(candidate.get("best_trade_qty")),
            "best_projected_settlement": _jsonable(candidate.get("best_projected_settlement")),
            "best_projected_intrinsic": _jsonable(candidate.get("best_projected_intrinsic")),
            "best_gross_edge": _jsonable(candidate.get("best_gross_edge")),
            "best_gross_edge_ticks": _jsonable(candidate.get("best_gross_edge_ticks")),
            "best_cost": _jsonable(candidate.get("best_cost")),
            "min_known_fraction": _jsonable(candidate.get("min_known_fraction")),
            "min_gross_edge_ticks": _jsonable(candidate.get("min_gross_edge_ticks")),
            "min_net_edge": _jsonable(candidate.get("min_net_edge")),
            "qty": _jsonable(candidate.get("qty")),
            "depth_fraction": _jsonable(candidate.get("depth_fraction")),
        },
        "metrics": {
            "fold_count": _jsonable(candidate.get("fold_count")),
            "passed_folds": _jsonable(candidate.get("passed_folds")),
            "pass_rate": _jsonable(candidate.get("pass_rate")),
            "total_opportunities": _jsonable(candidate.get("total_opportunities")),
            "total_net_edge": _jsonable(candidate.get("total_net_edge")),
            "median_best_net_edge": _jsonable(candidate.get("median_best_net_edge")),
            "best_net_edge": _jsonable(candidate.get("best_net_edge")),
            "median_known_fraction": _jsonable(candidate.get("median_known_fraction")),
        },
        "source_candidate": _jsonable(source_config),
        "failed_checks": list(dict.fromkeys(failed_checks)),
        "thresholds": asdict(thresholds),
        "recommendation": str(summary["recommendation"]),
    }


def _scenario_key(best: dict[str, Any], defaults: dict[str, Any]) -> str:
    pieces = [
        ("strategy", "settlement_convergence"),
        ("market", defaults.get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
        ("direction", best.get("direction")),
        ("option_type", best.get("option_type")),
        ("strike", best.get("strike")),
        ("min_known_fraction", defaults.get("min_known_fraction")),
        ("min_net_edge", defaults.get("min_net_edge")),
    ]
    return "|".join(f"{key}={_format_value(value)}" for key, value in pieces)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
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


def _validate_thresholds(thresholds: SettlementCandidatePromotionThresholds) -> None:
    if not 0 <= thresholds.min_pass_rate <= 1:
        raise ValueError("min_pass_rate must be between 0 and 1")
    if thresholds.min_total_opportunities < 0:
        raise ValueError("min_total_opportunities must be non-negative")
    if not 0 <= thresholds.min_median_known_fraction <= 1:
        raise ValueError("min_median_known_fraction must be between 0 and 1")


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
