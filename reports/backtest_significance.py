from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "backtest_significance_audit"
READY_NEXT_GATE = "promote-scenario"
REPAIR_NEXT_GATE = "audit-backtest-significance"

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]


@dataclass(frozen=True)
class BacktestSignificanceConfig:
    bootstrap_samples: int = 10_000
    confidence_level: float = 0.95
    random_seed: int = 1729
    zero_tolerance: float = 0.0
    require_overfit_manifest: bool = True


@dataclass(frozen=True)
class BacktestSignificanceThresholds:
    min_observations: int = 6
    min_nonzero_observations: int = 6
    min_positive_rate: float = 0.5
    max_adjusted_sign_pvalue: float = 0.1
    min_bootstrap_probability_positive: float = 0.95
    min_bootstrap_mean_lower: float = 0.0
    require_overfit_passed: bool = True


@dataclass(frozen=True)
class BacktestSignificanceReport:
    observations: pd.DataFrame
    bootstrap_quantiles: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])

    @property
    def ready(self) -> bool:
        return self.passed


def evaluate_backtest_significance(
    partition_scores: pd.DataFrame,
    overfit_summary: pd.DataFrame,
    *,
    config: BacktestSignificanceConfig | None = None,
    thresholds: BacktestSignificanceThresholds | None = None,
    overfit_manifest_current: bool = True,
) -> BacktestSignificanceReport:
    config = config or BacktestSignificanceConfig()
    thresholds = thresholds or BacktestSignificanceThresholds()
    _validate(config, thresholds)
    summary_row = (
        overfit_summary.iloc[0]
        if not overfit_summary.empty
        else pd.Series(dtype=object)
    )
    candidate = str(summary_row.get("selection_candidate_scenario", "")).strip()
    observations = _candidate_observations(
        partition_scores,
        candidate,
        zero_tolerance=config.zero_tolerance,
    )
    scores = observations["score"].to_numpy(dtype=float) if not observations.empty else np.array([])
    positive_count = int(observations["positive"].sum()) if not observations.empty else 0
    negative_count = int(observations["negative"].sum()) if not observations.empty else 0
    zero_count = int(observations["zero"].sum()) if not observations.empty else 0
    nonzero_count = positive_count + negative_count
    observation_count = int(len(observations))
    positive_rate = positive_count / observation_count if observation_count else math.nan
    nonzero_positive_rate = positive_count / nonzero_count if nonzero_count else math.nan
    sign_pvalue = _one_sided_sign_pvalue(positive_count, nonzero_count)
    trial_count = max(1, _int(summary_row.get("scenario_count")))
    adjusted_sign_pvalue = (
        min(1.0, sign_pvalue * trial_count)
        if np.isfinite(sign_pvalue)
        else math.nan
    )
    bootstrap_means = _bootstrap_means(scores, config)
    bootstrap_quantiles = _bootstrap_quantiles(
        bootstrap_means,
        confidence_level=config.confidence_level,
    )
    bootstrap_probability_positive = (
        float(np.mean(bootstrap_means > 0.0))
        if len(bootstrap_means)
        else math.nan
    )
    bootstrap_lower = _quantile_value(
        bootstrap_quantiles,
        (1.0 - config.confidence_level) / 2.0,
    )
    bootstrap_upper = _quantile_value(
        bootstrap_quantiles,
        1.0 - (1.0 - config.confidence_level) / 2.0,
    )
    observed_mean = float(np.mean(scores)) if len(scores) else math.nan
    observed_median = float(np.median(scores)) if len(scores) else math.nan
    overfit_passed = _to_bool(summary_row.get("passed", False))
    candidate_present = bool(candidate and candidate in partition_scores.columns)
    checks = _checks(
        candidate=candidate,
        candidate_present=candidate_present,
        overfit_passed=overfit_passed,
        overfit_manifest_current=overfit_manifest_current,
        observation_count=observation_count,
        nonzero_count=nonzero_count,
        positive_rate=positive_rate,
        adjusted_sign_pvalue=adjusted_sign_pvalue,
        bootstrap_probability_positive=bootstrap_probability_positive,
        bootstrap_lower=bootstrap_lower,
        config=config,
        thresholds=thresholds,
    )
    passed = bool(not checks.empty and checks["passed"].astype(bool).all())
    failed_checks = int((~checks["passed"].astype(bool)).sum())
    action_queue = _action_queue(checks)
    result_summary = pd.DataFrame(
        [
            {
                "passed": passed,
                "candidate_scenario": candidate,
                "overfit_audit_passed": overfit_passed,
                "overfit_manifest_current": bool(overfit_manifest_current),
                "observation_count": observation_count,
                "nonzero_observation_count": nonzero_count,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "zero_count": zero_count,
                "positive_rate": positive_rate,
                "nonzero_positive_rate": nonzero_positive_rate,
                "observed_mean_score": observed_mean,
                "observed_median_score": observed_median,
                "scenario_trial_count": trial_count,
                "sign_pvalue": sign_pvalue,
                "adjusted_sign_pvalue": adjusted_sign_pvalue,
                "bootstrap_samples": config.bootstrap_samples,
                "bootstrap_confidence_level": config.confidence_level,
                "bootstrap_mean_lower": bootstrap_lower,
                "bootstrap_mean_upper": bootstrap_upper,
                "bootstrap_probability_positive": bootstrap_probability_positive,
                "failed_checks": failed_checks,
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": READY_NEXT_GATE if passed else REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(
                    READY_NEXT_GATE if passed else REPAIR_NEXT_GATE
                ),
                "recommendation": (
                    "eligible_for_manifest_bound_promotion"
                    if passed
                    else "collect_more_chronological_periods_or_reduce_search_breadth"
                ),
                "authorizes_submission": False,
            }
        ]
    )
    payload = {
        "schema_version": 1,
        "passed": passed,
        "parameters": asdict(config),
        "thresholds": asdict(thresholds),
        "summary": _record(result_summary.iloc[0]),
    }
    return BacktestSignificanceReport(
        observations=observations,
        bootstrap_quantiles=bootstrap_quantiles,
        checks=checks,
        summary=result_summary,
        action_queue=action_queue,
        config=payload,
    )


def write_backtest_significance_audit(
    overfit_audit_path: str | Path,
    *,
    output_dir: str | Path,
    config: BacktestSignificanceConfig | None = None,
    thresholds: BacktestSignificanceThresholds | None = None,
) -> BacktestSignificanceReport:
    config = config or BacktestSignificanceConfig()
    thresholds = thresholds or BacktestSignificanceThresholds()
    audit = Path(overfit_audit_path).resolve()
    root = audit if audit.is_dir() else audit.parent
    summary_path = root / "backtest_overfit_summary.csv"
    scores_path = root / "backtest_overfit_partition_scores.csv"
    overfit_config_path = root / "backtest_overfit_config.json"
    manifest_path = root / "manifest.json"
    for path in (summary_path, scores_path):
        if not path.is_file():
            raise FileNotFoundError(f"required overfit audit artifact not found: {path}")
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type="backtest_overfit_audit",
        required_artifacts=(
            "backtest_overfit_summary.csv",
            "backtest_overfit_partition_scores.csv",
        ),
        require_input_fingerprints=True,
    )
    report = evaluate_backtest_significance(
        pd.read_csv(scores_path),
        pd.read_csv(summary_path),
        config=config,
        thresholds=thresholds,
        overfit_manifest_current=integrity.passed,
    )
    overfit_config = _read_json_object(overfit_config_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.observations.to_csv(
        out / "backtest_significance_observations.csv",
        index=False,
    )
    report.bootstrap_quantiles.to_csv(
        out / "backtest_significance_bootstrap_quantiles.csv",
        index=False,
    )
    report.checks.to_csv(out / "backtest_significance_checks.csv", index=False)
    report.summary.to_csv(out / "backtest_significance_summary.csv", index=False)
    report.action_queue.to_csv(
        out / "backtest_significance_action_queue.csv",
        index=False,
    )
    payload = dict(report.config)
    payload.update(
        {
            "overfit_audit_path": str(root),
            "overfit_manifest_path": str(manifest_path),
            "overfit_manifest_sha256": (
                file_sha256(manifest_path) if manifest_path.is_file() else ""
            ),
            "overfit_manifest_integrity": _integrity_record(integrity),
            "selection_path": str(overfit_config.get("selection_path", "")),
            "selection_manifest_sha256": str(
                overfit_config.get("selection_manifest_sha256", "")
            ),
        }
    )
    (out / "backtest_significance_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "backtest_significance_runbook.md").write_text(
        _runbook(report.summary.iloc[0], report.checks, report.action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "thresholds": asdict(thresholds),
        },
        inputs={
            "backtest_overfit_audit": root,
            "backtest_overfit_manifest": manifest_path,
            "backtest_overfit_summary": summary_path,
            "backtest_overfit_partition_scores": scores_path,
        },
        extra={
            "passed": bool(report.passed),
            "candidate_scenario": str(report.summary.iloc[0]["candidate_scenario"]),
            "adjusted_sign_pvalue": _float(
                report.summary.iloc[0]["adjusted_sign_pvalue"]
            ),
            "bootstrap_probability_positive": _float(
                report.summary.iloc[0]["bootstrap_probability_positive"]
            ),
            "authorizes_submission": False,
        },
    )
    return BacktestSignificanceReport(
        observations=report.observations,
        bootstrap_quantiles=report.bootstrap_quantiles,
        checks=report.checks,
        summary=report.summary,
        action_queue=report.action_queue,
        config=payload,
        output_dir=out,
    )


def _candidate_observations(
    partition_scores: pd.DataFrame,
    candidate: str,
    *,
    zero_tolerance: float,
) -> pd.DataFrame:
    columns = [
        "partition",
        "candidate_scenario",
        "score",
        "positive",
        "negative",
        "zero",
    ]
    if not candidate or candidate not in partition_scores.columns:
        return pd.DataFrame(columns=columns)
    scores = pd.to_numeric(partition_scores[candidate], errors="coerce")
    finite = np.isfinite(scores)
    frame = pd.DataFrame(
        {
            "partition": (
                partition_scores["partition"]
                if "partition" in partition_scores.columns
                else np.arange(len(partition_scores))
            ),
            "candidate_scenario": candidate,
            "score": scores,
        }
    ).loc[finite].reset_index(drop=True)
    frame["positive"] = frame["score"] > zero_tolerance
    frame["negative"] = frame["score"] < -zero_tolerance
    frame["zero"] = ~(frame["positive"] | frame["negative"])
    return frame[columns]


def _one_sided_sign_pvalue(positive_count: int, nonzero_count: int) -> float:
    if nonzero_count <= 0:
        return math.nan
    numerator = sum(
        math.comb(nonzero_count, successes)
        for successes in range(positive_count, nonzero_count + 1)
    )
    return float(numerator / (2**nonzero_count))


def _bootstrap_means(
    scores: np.ndarray,
    config: BacktestSignificanceConfig,
) -> np.ndarray:
    if not len(scores):
        return np.array([], dtype=float)
    rng = np.random.default_rng(config.random_seed)
    positions = rng.integers(
        0,
        len(scores),
        size=(config.bootstrap_samples, len(scores)),
    )
    return scores[positions].mean(axis=1)


def _bootstrap_quantiles(
    bootstrap_means: np.ndarray,
    *,
    confidence_level: float,
) -> pd.DataFrame:
    alpha = (1.0 - confidence_level) / 2.0
    quantiles = sorted({0.01, alpha, 0.05, 0.5, 0.95, 1.0 - alpha, 0.99})
    return pd.DataFrame(
        [
            {
                "quantile": quantile,
                "mean_score": float(np.quantile(bootstrap_means, quantile))
                if len(bootstrap_means)
                else math.nan,
            }
            for quantile in quantiles
        ]
    )


def _quantile_value(frame: pd.DataFrame, quantile: float) -> float:
    if frame.empty:
        return math.nan
    distance = (frame["quantile"].astype(float) - quantile).abs()
    if distance.min() > 1e-12:
        return math.nan
    return float(frame.loc[distance.idxmin(), "mean_score"])


def _checks(
    *,
    candidate: str,
    candidate_present: bool,
    overfit_passed: bool,
    overfit_manifest_current: bool,
    observation_count: int,
    nonzero_count: int,
    positive_rate: float,
    adjusted_sign_pvalue: float,
    bootstrap_probability_positive: float,
    bootstrap_lower: float,
    config: BacktestSignificanceConfig,
    thresholds: BacktestSignificanceThresholds,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "overfit_audit_passed",
                overfit_passed,
                "is",
                True,
                overfit_passed or not thresholds.require_overfit_passed,
                "backtest overfit audit must pass before significance review",
            ),
            _check(
                "overfit_manifest_current",
                overfit_manifest_current,
                "is",
                True,
                overfit_manifest_current or not config.require_overfit_manifest,
                "backtest overfit artifacts or source inputs drifted from their manifest",
            ),
            _check(
                "candidate_present",
                candidate,
                "in",
                "partition_scores",
                candidate_present,
                "selected candidate is absent from overfit partition scores",
            ),
            _numeric_check(
                "observation_count",
                observation_count,
                ">=",
                thresholds.min_observations,
                "not enough chronological partition observations",
            ),
            _numeric_check(
                "nonzero_observation_count",
                nonzero_count,
                ">=",
                thresholds.min_nonzero_observations,
                "too many zero-score partitions for an exact sign test",
            ),
            _numeric_check(
                "positive_rate",
                positive_rate,
                ">=",
                thresholds.min_positive_rate,
                "candidate is not positive across enough partitions",
            ),
            _numeric_check(
                "adjusted_sign_pvalue",
                adjusted_sign_pvalue,
                "<=",
                thresholds.max_adjusted_sign_pvalue,
                "candidate sign evidence does not survive scenario-trial correction",
            ),
            _numeric_check(
                "bootstrap_probability_positive",
                bootstrap_probability_positive,
                ">=",
                thresholds.min_bootstrap_probability_positive,
                "bootstrap support for a positive mean is too weak",
            ),
            _numeric_check(
                "bootstrap_mean_lower",
                bootstrap_lower,
                ">=",
                thresholds.min_bootstrap_mean_lower,
                "lower bootstrap confidence bound does not clear the score hurdle",
            ),
        ]
    )


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    rows = []
    for priority, row in enumerate(failed.itertuples(index=False), start=1):
        recommendation = _recommendation(str(row.check))
        rows.append(
            {
                "priority": priority,
                "queue_status": "blocked",
                "source": RUN_TYPE,
                "component": "candidate_significance",
                "check": str(row.check),
                "actual": row.actual,
                "operator": row.operator,
                "expected": row.expected,
                "action": recommendation,
                "reason": str(row.reason),
                "recommendation": recommendation,
                "next_gate": REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(REPAIR_NEXT_GATE),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _check(
    check: str,
    actual: Any,
    operator: str,
    expected: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _numeric_check(
    check: str,
    actual: Any,
    operator: str,
    expected: float | int,
    reason: str,
) -> dict[str, Any]:
    value = _float(actual)
    passed = bool(
        np.isfinite(value)
        and ((operator == ">=" and value >= expected) or (operator == "<=" and value <= expected))
    )
    return _check(check, actual, operator, expected, passed, reason)


def _validate(
    config: BacktestSignificanceConfig,
    thresholds: BacktestSignificanceThresholds,
) -> None:
    if config.bootstrap_samples < 100:
        raise ValueError("bootstrap_samples must be at least 100")
    if not 0.0 < config.confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if config.zero_tolerance < 0.0:
        raise ValueError("zero_tolerance must be non-negative")
    if thresholds.min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if thresholds.min_nonzero_observations < 1:
        raise ValueError("min_nonzero_observations must be positive")
    for name, value in (
        ("min_positive_rate", thresholds.min_positive_rate),
        ("max_adjusted_sign_pvalue", thresholds.max_adjusted_sign_pvalue),
        (
            "min_bootstrap_probability_positive",
            thresholds.min_bootstrap_probability_positive,
        ),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")


def _recommendation(check: str) -> str:
    if check in {"overfit_audit_passed", "overfit_manifest_current", "candidate_present"}:
        return "regenerate_current_passing_backtest_overfit_audit"
    if check in {"observation_count", "nonzero_observation_count"}:
        return "collect_more_chronological_sweep_periods"
    if check == "adjusted_sign_pvalue":
        return "reduce_parameter_search_breadth_or_collect_more_positive_periods"
    return "keep_candidate_in_research_until_positive_edge_is_statistically_supported"


def _runbook(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Backtest Significance Audit",
        "",
        f"- Status: **{'passed' if bool(summary['passed']) else 'blocked'}**",
        f"- Candidate: `{summary['candidate_scenario']}`",
        f"- Partition observations: {int(summary['observation_count'])}",
        (
            "- Positive/negative/zero: "
            f"{int(summary['positive_count'])}/"
            f"{int(summary['negative_count'])}/"
            f"{int(summary['zero_count'])}"
        ),
        f"- Scenario trials: {int(summary['scenario_trial_count'])}",
        f"- Exact sign p-value: {_format_number(summary['sign_pvalue'])}",
        (
            "- Trial-adjusted sign p-value: "
            f"{_format_number(summary['adjusted_sign_pvalue'])}"
        ),
        (
            "- Bootstrap mean interval: "
            f"[{_format_number(summary['bootstrap_mean_lower'])}, "
            f"{_format_number(summary['bootstrap_mean_upper'])}]"
        ),
        (
            "- Bootstrap P(mean > 0): "
            f"{_format_number(summary['bootstrap_probability_positive'])}"
        ),
        f"- Next gate: `{summary['next_gate']}`",
        "- Authorizes submission: `false`",
        "",
        (
            "The exact sign test excludes zero-score partitions and applies a "
            "Bonferroni correction for the number of scenarios searched. "
            "Bootstrap resampling is deterministic from the recorded seed."
        ),
        (
            "These diagnostics treat disjoint chronological partition scores as "
            "exchangeable. Dependence, non-stationarity, and execution slippage "
            "can invalidate the inference; passing is research evidence and never "
            "authorizes trading."
        ),
    ]
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    if not failed.empty:
        lines.extend(["", "## Blocking Checks", ""])
        for row in failed.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.reason}")
    if not action_queue.empty:
        lines.extend(["", "## Actions", ""])
        for row in action_queue.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.recommendation}")
    return "\n".join(lines) + "\n"


def _integrity_record(integrity: Any) -> dict[str, Any]:
    return {
        "passed": bool(integrity.passed),
        "error": str(integrity.error),
        "run_type": str(integrity.run_type),
        "artifact_count": int(integrity.artifact_count),
        "artifact_match_count": int(integrity.artifact_match_count),
        "input_fingerprint_count": int(integrity.input_fingerprint_count),
        "input_fingerprint_match_count": int(integrity.input_fingerprint_match_count),
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


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


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready"}
    return bool(value)


def _int(value: Any) -> int:
    number = _float(value)
    return int(number) if np.isfinite(number) else 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _format_number(value: Any) -> str:
    number = _float(value)
    return "n/a" if not np.isfinite(number) else f"{number:.6f}"


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"
