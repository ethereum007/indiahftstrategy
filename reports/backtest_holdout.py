from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.backtest_overfit import DEFAULT_SCORE_COLUMNS
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.sweep_provenance import (
    build_sweep_provenance,
    sweep_manifest_path,
    sweep_runs_path,
)


RUN_TYPE = "backtest_holdout_audit"
READY_NEXT_GATE = "promote-scenario"
REPAIR_NEXT_GATE = "audit-backtest-holdout"

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
class BacktestHoldoutConfig:
    group_columns: tuple[str, ...]
    score_column: str = ""
    proof_column: str = "proof_passed"
    require_selection_manifest: bool = True
    require_sweep_manifests: bool = True


@dataclass(frozen=True)
class BacktestHoldoutThresholds:
    min_sweeps: int = 3
    min_candidate_coverage_rate: float = 1.0
    min_proof_pass_rate: float = 1.0
    min_mean_score: float = 0.0
    min_median_score: float = 0.0
    min_worst_score: float = 0.0
    min_mean_net_pnl: float = 0.0
    min_worst_net_pnl: float = 0.0
    min_fills_per_sweep: float = 1.0
    max_worst_drawdown: float | None = None
    require_selection_passed: bool = True


@dataclass(frozen=True)
class BacktestHoldoutReport:
    observations: pd.DataFrame
    provenance: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False

    @property
    def ready(self) -> bool:
        return self.passed


def evaluate_backtest_holdout(
    observations: pd.DataFrame,
    provenance: pd.DataFrame,
    *,
    candidate_scenario: str,
    expected_sweeps: int,
    selection_passed: bool,
    selection_manifest_current: bool,
    selection_holdout_disjoint: bool,
    config: BacktestHoldoutConfig,
    thresholds: BacktestHoldoutThresholds | None = None,
) -> BacktestHoldoutReport:
    thresholds = thresholds or BacktestHoldoutThresholds()
    _validate(config, thresholds)
    frame = observations.copy()
    sweep_count = int(expected_sweeps)
    observed_sweeps = int(frame["sweep"].nunique()) if not frame.empty else 0
    covered = _bool_count(frame, "candidate_present")
    candidate_coverage_rate = covered / sweep_count if sweep_count else math.nan
    proof_pass_rate = _bool_rate(frame, "proof_passed")
    score = _numeric(frame, "score")
    net_pnl = _numeric(frame, "net_pnl")
    fills = _numeric(frame, "fills")
    drawdown = _numeric(frame, "max_drawdown")
    finite_score_count = int(np.isfinite(score).sum())
    manifests_current = bool(
        not provenance.empty
        and len(provenance) == sweep_count
        and provenance["passed"].astype(bool).all()
    )
    unique_holdouts = bool(
        not provenance.empty
        and provenance["sweep_path"].astype(str).nunique() == sweep_count
    )
    mean_score = _mean(score)
    median_score = _median(score)
    worst_score = _min(score)
    mean_net_pnl = _mean(net_pnl)
    worst_net_pnl = _min(net_pnl)
    min_fills = _min(fills)
    worst_drawdown = _max(drawdown)
    checks = _checks(
        candidate_scenario=candidate_scenario,
        expected_sweeps=sweep_count,
        observed_sweeps=observed_sweeps,
        covered_sweeps=covered,
        finite_score_count=finite_score_count,
        selection_passed=selection_passed,
        selection_manifest_current=selection_manifest_current,
        selection_holdout_disjoint=selection_holdout_disjoint,
        holdout_manifests_current=manifests_current,
        unique_holdouts=unique_holdouts,
        candidate_coverage_rate=candidate_coverage_rate,
        proof_pass_rate=proof_pass_rate,
        mean_score=mean_score,
        median_score=median_score,
        worst_score=worst_score,
        mean_net_pnl=mean_net_pnl,
        worst_net_pnl=worst_net_pnl,
        min_fills=min_fills,
        worst_drawdown=worst_drawdown,
        config=config,
        thresholds=thresholds,
    )
    passed = bool(not checks.empty and checks["passed"].astype(bool).all())
    failed_checks = int((~checks["passed"].astype(bool)).sum())
    action_queue = _action_queue(checks)
    summary = pd.DataFrame(
        [
            {
                "passed": passed,
                "candidate_scenario": candidate_scenario,
                "selection_passed": bool(selection_passed),
                "selection_manifest_current": bool(selection_manifest_current),
                "selection_holdout_disjoint": bool(selection_holdout_disjoint),
                "holdout_manifests_current": manifests_current,
                "expected_sweeps": sweep_count,
                "observed_sweeps": observed_sweeps,
                "covered_sweeps": covered,
                "candidate_coverage_rate": candidate_coverage_rate,
                "proof_pass_rate": proof_pass_rate,
                "finite_score_count": finite_score_count,
                "mean_score": mean_score,
                "median_score": median_score,
                "worst_score": worst_score,
                "mean_net_pnl": mean_net_pnl,
                "worst_net_pnl": worst_net_pnl,
                "min_fills": min_fills,
                "worst_drawdown": worst_drawdown,
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
                    else "keep_candidate_in_research_and_collect_new_holdout_periods"
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
        "summary": _record(summary.iloc[0]),
    }
    return BacktestHoldoutReport(
        observations=frame,
        provenance=provenance,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
    )


def write_backtest_holdout_audit(
    selection_path: str | Path,
    holdout_sweep_paths: list[str | Path],
    *,
    output_dir: str | Path,
    config: BacktestHoldoutConfig,
    labels: list[str] | None = None,
    thresholds: BacktestHoldoutThresholds | None = None,
) -> BacktestHoldoutReport:
    thresholds = thresholds or BacktestHoldoutThresholds()
    _validate(config, thresholds)
    selection = Path(selection_path).resolve()
    paths = [Path(path).resolve() for path in holdout_sweep_paths]
    if not paths:
        raise ValueError("at least one holdout sweep path is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match holdout_sweep_paths length")
    resolved_labels = labels or [path.stem for path in paths]
    scores_path = selection / "scenario_scores.csv"
    runs_path = selection / "scenario_runs.csv"
    summary_path = selection / "selection_summary.csv"
    manifest_path = selection / "manifest.json"
    for path in (scores_path, runs_path, summary_path):
        if not path.is_file():
            raise FileNotFoundError(f"required selection artifact not found: {path}")
    scores = pd.read_csv(scores_path)
    development_runs = pd.read_csv(runs_path)
    selection_summary = pd.read_csv(summary_path)
    if selection_summary.empty:
        raise ValueError(f"selection summary is empty: {summary_path}")
    summary_row = selection_summary.iloc[0]
    candidate = str(summary_row.get("best_scenario_key", "")).strip()
    candidate_row = scores.loc[scores.get("scenario_key", pd.Series(dtype=str)) == candidate]
    selection_passed = bool(
        _int(summary_row.get("selectable_scenarios")) > 0
        and not candidate_row.empty
        and _to_bool(candidate_row.iloc[0].get("selection_passed", False))
    )
    selection_integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type="sweep_comparison",
        required_artifacts=(
            "scenario_scores.csv",
            "scenario_runs.csv",
            "selection_summary.csv",
        ),
        require_input_fingerprints=True,
    )
    development_paths = _development_sweep_paths(development_runs)
    holdout_keys = {_canonical_sweep_path(path) for path in paths}
    selection_holdout_disjoint = bool(
        len(holdout_keys) == len(paths)
        and not holdout_keys.intersection(development_paths)
    )
    provenance = build_sweep_provenance(
        paths,
        resolved_labels,
        roles=["holdout"] * len(paths),
    )
    score_column = _resolve_score_column(paths, config.score_column)
    observations = _holdout_observations(
        paths,
        resolved_labels,
        candidate,
        config.group_columns,
        score_column=score_column,
        proof_column=config.proof_column,
    )
    report = evaluate_backtest_holdout(
        observations,
        provenance,
        candidate_scenario=candidate,
        expected_sweeps=len(paths),
        selection_passed=selection_passed,
        selection_manifest_current=selection_integrity.passed,
        selection_holdout_disjoint=selection_holdout_disjoint,
        config=config,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.observations.to_csv(out / "backtest_holdout_observations.csv", index=False)
    report.provenance.to_csv(out / "backtest_holdout_provenance.csv", index=False)
    report.checks.to_csv(out / "backtest_holdout_checks.csv", index=False)
    report.summary.to_csv(out / "backtest_holdout_summary.csv", index=False)
    report.action_queue.to_csv(
        out / "backtest_holdout_action_queue.csv",
        index=False,
    )
    payload = dict(report.config)
    payload.update(
        {
            "selection_path": str(selection),
            "selection_manifest_path": str(manifest_path),
            "selection_manifest_sha256": (
                file_sha256(manifest_path) if manifest_path.is_file() else ""
            ),
            "selection_manifest_integrity": _integrity_record(selection_integrity),
            "development_sweep_paths": sorted(development_paths),
            "holdout_sweep_paths": [str(path) for path in paths],
            "holdout_labels": resolved_labels,
            "resolved_score_column": score_column,
        }
    )
    (out / "backtest_holdout_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "backtest_holdout_runbook.md").write_text(
        _runbook(report.summary.iloc[0], report.checks, report.action_queue),
        encoding="utf-8",
    )
    holdout_manifests = [
        sweep_manifest_path(path)
        for path in paths
        if sweep_manifest_path(path).is_file()
    ]
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "thresholds": asdict(thresholds),
            "labels": resolved_labels,
            "resolved_score_column": score_column,
        },
        inputs={
            "selection": selection,
            "selection_manifest": manifest_path,
            "holdout_sweeps": paths,
            "holdout_sweep_manifests": holdout_manifests,
        },
        extra={
            "passed": bool(report.passed),
            "candidate_scenario": candidate,
            "expected_sweeps": len(paths),
            "selection_holdout_disjoint": selection_holdout_disjoint,
            "authorizes_submission": False,
        },
    )
    return BacktestHoldoutReport(
        observations=report.observations,
        provenance=report.provenance,
        checks=report.checks,
        summary=report.summary,
        action_queue=report.action_queue,
        config=payload,
        output_dir=out,
    )


def _holdout_observations(
    paths: list[Path],
    labels: list[str],
    candidate: str,
    group_columns: tuple[str, ...],
    *,
    score_column: str,
    proof_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path, label in zip(paths, labels):
        target = sweep_runs_path(path)
        if not target.is_file():
            raise FileNotFoundError(f"sweep_runs.csv not found for holdout: {path}")
        frame = pd.read_csv(target)
        missing = [column for column in group_columns if column not in frame.columns]
        if missing:
            raise ValueError(f"holdout sweep missing scenario columns {missing}: {target}")
        keys = frame.apply(
            lambda row: _scenario_key(group_columns, row),
            axis=1,
        )
        selected = frame.loc[keys == candidate].copy()
        scores = _numeric(selected, score_column)
        net_pnl = _numeric(selected, "net_pnl")
        fills = _numeric(selected, "fills")
        drawdown = _numeric(selected, "max_drawdown")
        proof = (
            selected[proof_column].map(_to_bool)
            if proof_column in selected.columns
            else pd.Series(False, index=selected.index)
        )
        rows.append(
            {
                "sweep": str(label),
                "sweep_path": str(path),
                "candidate_scenario": candidate,
                "candidate_present": bool(not selected.empty),
                "candidate_run_count": int(len(selected)),
                "finite_score_count": int(np.isfinite(scores).sum()),
                "score": _mean(scores),
                "net_pnl": _mean(net_pnl),
                "fills": _min(fills),
                "max_drawdown": _max(drawdown),
                "proof_passed": bool(not selected.empty and proof.astype(bool).all()),
            }
        )
    return pd.DataFrame(rows)


def _checks(
    *,
    candidate_scenario: str,
    expected_sweeps: int,
    observed_sweeps: int,
    covered_sweeps: int,
    finite_score_count: int,
    selection_passed: bool,
    selection_manifest_current: bool,
    selection_holdout_disjoint: bool,
    holdout_manifests_current: bool,
    unique_holdouts: bool,
    candidate_coverage_rate: float,
    proof_pass_rate: float,
    mean_score: float,
    median_score: float,
    worst_score: float,
    mean_net_pnl: float,
    worst_net_pnl: float,
    min_fills: float,
    worst_drawdown: float,
    config: BacktestHoldoutConfig,
    thresholds: BacktestHoldoutThresholds,
) -> pd.DataFrame:
    rows = [
        _check(
            "selection_passed",
            selection_passed,
            "is",
            True,
            selection_passed or not thresholds.require_selection_passed,
            "development selection did not produce a selectable candidate",
        ),
        _check(
            "selection_manifest_current",
            selection_manifest_current,
            "is",
            True,
            selection_manifest_current or not config.require_selection_manifest,
            "selection artifacts or development inputs drifted from their manifest",
        ),
        _check(
            "selection_holdout_disjoint",
            selection_holdout_disjoint,
            "is",
            True,
            selection_holdout_disjoint,
            "one or more holdout sweeps were consumed during candidate selection",
        ),
        _check(
            "unique_holdout_sweeps",
            unique_holdouts,
            "is",
            True,
            unique_holdouts,
            "holdout paths contain duplicates",
        ),
        _check(
            "holdout_manifests_current",
            holdout_manifests_current,
            "is",
            True,
            holdout_manifests_current or not config.require_sweep_manifests,
            "holdout sweeps or source inputs drifted from their manifests",
        ),
        _check(
            "candidate_present",
            candidate_scenario,
            "is_not",
            "",
            bool(candidate_scenario),
            "selection candidate key is missing",
        ),
        _numeric_check(
            "holdout_sweep_count",
            expected_sweeps,
            ">=",
            thresholds.min_sweeps,
            "not enough reserved chronological holdout sweeps",
        ),
        _numeric_check(
            "observed_sweep_count",
            observed_sweeps,
            "==",
            expected_sweeps,
            "holdout observations do not cover every reserved sweep",
        ),
        _numeric_check(
            "finite_score_count",
            finite_score_count,
            "==",
            expected_sweeps,
            "selected candidate lacks a finite score in one or more holdouts",
        ),
        _numeric_check(
            "candidate_coverage_rate",
            candidate_coverage_rate,
            ">=",
            thresholds.min_candidate_coverage_rate,
            "selected candidate is missing from one or more holdout sweeps",
        ),
        _numeric_check(
            "proof_pass_rate",
            proof_pass_rate,
            ">=",
            thresholds.min_proof_pass_rate,
            "selected candidate failed the underlying proof in holdout",
        ),
        _numeric_check(
            "mean_score",
            mean_score,
            ">=",
            thresholds.min_mean_score,
            "mean holdout score is below the required hurdle",
        ),
        _numeric_check(
            "median_score",
            median_score,
            ">=",
            thresholds.min_median_score,
            "median holdout score is below the required hurdle",
        ),
        _numeric_check(
            "worst_score",
            worst_score,
            ">=",
            thresholds.min_worst_score,
            "worst holdout score is below the required hurdle",
        ),
        _numeric_check(
            "mean_net_pnl",
            mean_net_pnl,
            ">=",
            thresholds.min_mean_net_pnl,
            "mean holdout net PnL is below the required hurdle",
        ),
        _numeric_check(
            "worst_net_pnl",
            worst_net_pnl,
            ">=",
            thresholds.min_worst_net_pnl,
            "worst holdout net PnL is below the required hurdle",
        ),
        _numeric_check(
            "min_fills",
            min_fills,
            ">=",
            thresholds.min_fills_per_sweep,
            "one or more holdout sweeps lack enough fills",
        ),
    ]
    if thresholds.max_worst_drawdown is not None:
        rows.append(
            _numeric_check(
                "worst_drawdown",
                worst_drawdown,
                "<=",
                thresholds.max_worst_drawdown,
                "holdout drawdown exceeds the allowed ceiling",
            )
        )
    return pd.DataFrame(rows)


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
                "component": "chronological_holdout",
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


def _recommendation(check: str) -> str:
    if check in {"selection_passed", "selection_manifest_current"}:
        return "regenerate_current_manifest_bound_development_selection"
    if check == "selection_holdout_disjoint":
        return "reserve_new_sweeps_never_consumed_by_selection"
    if check in {"unique_holdout_sweeps", "holdout_sweep_count"}:
        return "supply_three_distinct_chronological_holdout_sweeps"
    if check == "holdout_manifests_current":
        return "regenerate_holdout_sweeps_from_current_fingerprinted_inputs"
    if check in {"candidate_present", "observed_sweep_count", "finite_score_count"}:
        return "rerun_the_frozen_candidate_unchanged_on_every_holdout"
    return "keep_candidate_in_research_and_collect_new_unseen_holdout_periods"


def _development_sweep_paths(frame: pd.DataFrame) -> set[str]:
    if "sweep_path" not in frame.columns:
        return set()
    return {
        _canonical_sweep_path(Path(value))
        for value in frame["sweep_path"].dropna().astype(str)
    }


def _canonical_sweep_path(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_file() and resolved.name == "sweep_runs.csv":
        resolved = resolved.parent
    return str(resolved).casefold()


def _resolve_score_column(paths: list[Path], configured: str) -> str:
    first = sweep_runs_path(paths[0])
    if not first.is_file():
        raise FileNotFoundError(f"sweep_runs.csv not found for holdout: {paths[0]}")
    columns = pd.read_csv(first, nrows=0).columns
    if configured:
        if configured not in columns:
            raise ValueError(f"holdout sweep missing score column {configured}: {first}")
        return configured
    for column in DEFAULT_SCORE_COLUMNS:
        if column in columns:
            return column
    raise ValueError(
        f"holdout sweeps are missing a supported score column: {DEFAULT_SCORE_COLUMNS}"
    )


def _scenario_key(group_columns: tuple[str, ...], row: pd.Series) -> str:
    return "|".join(
        f"{column}={_format_value(row[column])}" for column in group_columns
    )


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return "NA"
    if isinstance(value, (float, np.floating)) and value.is_integer():
        return str(int(value))
    return str(value)


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
    expected_value = _float(expected)
    passed = bool(
        np.isfinite(value)
        and np.isfinite(expected_value)
        and (
            (operator == ">=" and value >= expected_value)
            or (operator == "<=" and value <= expected_value)
            or (operator == "==" and value == expected_value)
        )
    )
    return _check(check, actual, operator, expected, passed, reason)


def _validate(
    config: BacktestHoldoutConfig,
    thresholds: BacktestHoldoutThresholds,
) -> None:
    if not config.group_columns:
        raise ValueError("group_columns must identify the frozen scenario")
    if len(set(config.group_columns)) != len(config.group_columns):
        raise ValueError("group_columns must be unique")
    if thresholds.min_sweeps < 1:
        raise ValueError("min_sweeps must be positive")
    for name, value in (
        ("min_candidate_coverage_rate", thresholds.min_candidate_coverage_rate),
        ("min_proof_pass_rate", thresholds.min_proof_pass_rate),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
    for name, value in (
        ("min_mean_score", thresholds.min_mean_score),
        ("min_median_score", thresholds.min_median_score),
        ("min_worst_score", thresholds.min_worst_score),
        ("min_mean_net_pnl", thresholds.min_mean_net_pnl),
        ("min_worst_net_pnl", thresholds.min_worst_net_pnl),
        ("min_fills_per_sweep", thresholds.min_fills_per_sweep),
    ):
        if not np.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if (
        thresholds.max_worst_drawdown is not None
        and not np.isfinite(thresholds.max_worst_drawdown)
    ):
        raise ValueError("max_worst_drawdown must be finite when provided")


def _runbook(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Chronological Holdout Audit",
        "",
        f"- Status: **{'passed' if bool(summary['passed']) else 'blocked'}**",
        f"- Frozen candidate: `{summary['candidate_scenario']}`",
        (
            "- Reserved/covered sweeps: "
            f"{int(summary['expected_sweeps'])}/{int(summary['covered_sweeps'])}"
        ),
        f"- Proof pass rate: {_format_number(summary['proof_pass_rate'])}",
        f"- Mean/median/worst score: {_format_number(summary['mean_score'])} / "
        f"{_format_number(summary['median_score'])} / "
        f"{_format_number(summary['worst_score'])}",
        f"- Mean/worst net PnL: {_format_number(summary['mean_net_pnl'])} / "
        f"{_format_number(summary['worst_net_pnl'])}",
        f"- Next gate: `{summary['next_gate']}`",
        "- Authorizes submission: `false`",
        "",
        (
            "This audit evaluates only the development-selected scenario. It does "
            "not rank or substitute candidates using holdout outcomes."
        ),
        (
            "Selection isolation is proven from manifest-bound development paths. "
            "It cannot prove that a human never inspected the holdout beforehand."
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


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _bool_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    return int(frame[column].map(_to_bool).sum())


def _bool_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return math.nan
    return float(frame[column].map(_to_bool).mean())


def _mean(values: pd.Series) -> float:
    finite = values.loc[np.isfinite(values)]
    return float(finite.mean()) if not finite.empty else math.nan


def _median(values: pd.Series) -> float:
    finite = values.loc[np.isfinite(values)]
    return float(finite.median()) if not finite.empty else math.nan


def _min(values: pd.Series) -> float:
    finite = values.loc[np.isfinite(values)]
    return float(finite.min()) if not finite.empty else math.nan


def _max(values: pd.Series) -> float:
    finite = values.loc[np.isfinite(values)]
    return float(finite.max()) if not finite.empty else math.nan


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
