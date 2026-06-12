from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ImbalanceCandidatePromotionThresholds:
    require_walkforward_passed: bool = True
    require_candidate_ready: bool = True
    min_proof_pass_rate: float = 1.0
    min_total_fills: int = 1
    min_total_net_pnl: float = 0.0
    max_worst_drawdown: float | None = None
    min_median_markout_mean: float | None = None


@dataclass(frozen=True)
class ImbalanceCandidatePromotionReport:
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


def evaluate_imbalance_candidate_promotion(
    walkforward_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    *,
    thresholds: ImbalanceCandidatePromotionThresholds | None = None,
) -> ImbalanceCandidatePromotionReport:
    thresholds = thresholds or ImbalanceCandidatePromotionThresholds()
    _validate_thresholds(thresholds)
    _require(walkforward_summary, ["passed", "proof_pass_rate", "total_fills", "total_net_pnl"], "walkforward_summary")
    row = walkforward_summary.iloc[0]
    checks = _checks(row, candidate_config, thresholds)
    candidate = pd.DataFrame([_candidate_row(row, candidate_config)])
    summary = _summary(candidate, checks)
    config = _promotion_candidate_config(candidate.iloc[0], checks, summary.iloc[0], candidate_config, thresholds)
    return ImbalanceCandidatePromotionReport(candidate, checks, summary, config)


def write_imbalance_candidate_promotion(
    walkforward_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: ImbalanceCandidatePromotionThresholds | None = None,
) -> ImbalanceCandidatePromotionReport:
    walkforward = Path(walkforward_path)
    summary_path = walkforward / "imbalance_replay_walkforward_summary.csv"
    candidate_path = walkforward / "candidate_config.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"imbalance_replay_walkforward_summary.csv not found: {summary_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")

    thresholds = thresholds or ImbalanceCandidatePromotionThresholds()
    report = evaluate_imbalance_candidate_promotion(
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
        parameters={"strategy": "imbalance", "thresholds": asdict(thresholds)},
        inputs={"walkforward": walkforward, "summary": summary_path, "candidate_config": candidate_path},
        extra={"promotion_source": "imbalance_replay_walkforward"},
    )
    return ImbalanceCandidatePromotionReport(
        report.candidate,
        report.checks,
        report.summary,
        report.candidate_config,
        out,
    )


def _checks(
    row: pd.Series,
    candidate_config: dict[str, Any],
    thresholds: ImbalanceCandidatePromotionThresholds,
) -> pd.DataFrame:
    walkforward_passed = _to_bool(row.get("passed", False))
    candidate_ready = _to_bool(candidate_config.get("ready", False))
    checks = [
        _check(
            "walkforward_passed",
            walkforward_passed,
            "is",
            True,
            walkforward_passed or not thresholds.require_walkforward_passed,
            "imbalance replay walk-forward did not pass",
        ),
        _check(
            "candidate_config_ready",
            candidate_ready,
            "is",
            True,
            candidate_ready or not thresholds.require_candidate_ready,
            "source candidate_config.json is not ready",
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
    return {
        "scenario_key": scenario_key,
        "strategy": "imbalance",
        "source_run_type": str(candidate_config.get("source_run_type", "")),
        "entry_imbalance": _jsonable(replay_defaults.get("entry_imbalance")),
        "min_microprice_edge_ticks": _jsonable(replay_defaults.get("min_microprice_edge_ticks")),
        "hold_ns": _jsonable(replay_defaults.get("hold_ns")),
        "tick_size": _jsonable(replay_defaults.get("tick_size")),
        "market": _jsonable(replay_defaults.get("market")),
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
    }


def _summary(candidate: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    key = str(candidate.iloc[0]["scenario_key"]) if not candidate.empty else ""
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": key,
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
    thresholds: ImbalanceCandidatePromotionThresholds,
) -> dict[str, Any]:
    replay_defaults = source_config.get("replay_defaults", {}) if isinstance(source_config.get("replay_defaults", {}), dict) else {}
    failed_checks = list(source_config.get("failed_checks", []) or [])
    failed_checks.extend(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist())
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "strategy": "imbalance",
        "scenario_key": str(candidate["scenario_key"]),
        "parameters": {
            "entry_imbalance": _jsonable(candidate.get("entry_imbalance")),
            "min_microprice_edge_ticks": _jsonable(candidate.get("min_microprice_edge_ticks")),
            "hold_ns": _jsonable(candidate.get("hold_ns")),
            "tick_size": _jsonable(candidate.get("tick_size")),
            "market": _jsonable(candidate.get("market")),
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
        },
        "source_candidate": _jsonable(source_config),
        "failed_checks": list(dict.fromkeys(failed_checks)),
        "thresholds": asdict(thresholds),
        "recommendation": str(summary["recommendation"]),
    }


def _scenario_key(replay_defaults: dict[str, Any]) -> str:
    pieces = [
        ("strategy", "imbalance"),
        ("market", replay_defaults.get("market")),
        ("entry_imbalance", replay_defaults.get("entry_imbalance")),
        ("min_microprice_edge_ticks", replay_defaults.get("min_microprice_edge_ticks")),
        ("hold_ns", replay_defaults.get("hold_ns")),
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


def _validate_thresholds(thresholds: ImbalanceCandidatePromotionThresholds) -> None:
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
