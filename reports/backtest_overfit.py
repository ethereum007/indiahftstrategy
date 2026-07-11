from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from reports.manifest import file_sha256, write_experiment_manifest


RUN_TYPE = "backtest_overfit_audit"
READY_NEXT_GATE = "promote-scenario"
REPAIR_NEXT_GATE = "compare-sweeps"

RUN_FILE_NAMES = (
    "scenario_runs.csv",
    "imbalance_edge_scenario_runs.csv",
)
SCORE_FILE_NAMES = (
    "scenario_scores.csv",
    "imbalance_edge_scenario_scores.csv",
)
DEFAULT_SCORE_COLUMNS = (
    "robust_score",
    "net_pnl",
    "mean_forward_edge_ticks",
)
NON_PARAMETER_COLUMNS = {
    "rank",
    "run",
    "run_dir",
    "sweep",
    "sweep_path",
    "scenario_key",
    "passed",
    "proof_passed",
    "selection_passed",
    "failed_checks",
    "recommendation",
    "sweeps_seen",
    "scenario_runs",
    "passed_runs",
    "pass_rate",
    "usable_signals",
    "signal_count",
    "execution_count",
    "fills",
    "orders_sent",
    "net_pnl",
    "total_net_pnl",
    "median_net_pnl",
    "mean_net_pnl",
    "min_net_pnl",
    "robust_score",
    "median_robust_score",
    "min_robust_score",
    "mean_forward_edge_ticks",
    "median_mean_forward_edge_ticks",
    "min_mean_forward_edge_ticks",
    "median_forward_edge_ticks",
    "win_rate",
    "median_win_rate",
    "min_win_rate",
    "direction_count",
    "min_direction_count",
    "max_drawdown",
    "worst_drawdown",
    "median_fills",
    "min_fills",
    "worst_regime_equity_change",
    "runs_with_losing_regimes",
    "total_costs",
    "turnover",
    "cost_bps",
    "pnl_per_fill",
    "maker_share",
    "order_to_trade_ratio",
    "otr_breached",
    "spread_net",
    "markout_mean",
    "markout_win_rate",
}

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
class BacktestOverfitConfig:
    split_column: str = "sweep"
    score_column: str = ""
    scenario_columns: tuple[str, ...] = ()
    max_partitions: int = 12
    require_selection_manifest: bool = True


@dataclass(frozen=True)
class BacktestOverfitThresholds:
    min_partitions: int = 4
    min_scenarios: int = 3
    max_probability_overfit: float = 0.25
    min_median_oos_score: float = 0.0
    min_oos_positive_rate: float = 0.5
    min_median_rank_correlation: float = 0.0
    max_median_degradation: float | None = None
    min_candidate_selection_rate: float = 0.25
    max_candidate_overfit_rate: float = 0.25
    min_candidate_oos_positive_rate: float = 0.5


@dataclass(frozen=True)
class BacktestOverfitReport:
    combinations: pd.DataFrame
    scenario_stability: pd.DataFrame
    partition_scores: pd.DataFrame
    partition_map: pd.DataFrame
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


def evaluate_backtest_overfit(
    scenario_runs: pd.DataFrame,
    *,
    scenario_scores: pd.DataFrame | None = None,
    config: BacktestOverfitConfig | None = None,
    thresholds: BacktestOverfitThresholds | None = None,
    selection_manifest_provided: bool = True,
) -> BacktestOverfitReport:
    config = config or BacktestOverfitConfig()
    thresholds = thresholds or BacktestOverfitThresholds()
    _validate_config(config, thresholds)

    runs = scenario_runs.copy()
    scores = pd.DataFrame() if scenario_scores is None else scenario_scores.copy()
    score_column = _score_column(runs, config.score_column)
    identified, scenario_columns = _attach_scenario_keys(
        runs,
        scores,
        config.scenario_columns,
    )
    observations = _observations(identified, config.split_column, score_column)
    partition_map = _partition_map(observations, config.split_column, config.max_partitions)
    partition_scores, excluded_scenarios = _partition_score_matrix(
        observations,
        partition_map,
        config.split_column,
    )
    combination_rows = _cscv_combinations(partition_scores, partition_map)
    stability = _scenario_stability(combination_rows, partition_scores.columns.tolist())
    selection_candidate = _selection_candidate(scores, partition_scores)
    checks = _checks(
        observations=observations,
        partition_scores=partition_scores,
        partition_map=partition_map,
        combinations_frame=combination_rows,
        stability=stability,
        selection_candidate=selection_candidate,
        selection_manifest_provided=selection_manifest_provided,
        excluded_scenarios=excluded_scenarios,
        config=config,
        thresholds=thresholds,
    )
    summary = _summary(
        observations=observations,
        partition_scores=partition_scores,
        partition_map=partition_map,
        combinations_frame=combination_rows,
        stability=stability,
        selection_candidate=selection_candidate,
        checks=checks,
        score_column=score_column,
        scenario_columns=scenario_columns,
        excluded_scenarios=excluded_scenarios,
    )
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(summary, action_queue)
    payload = {
        "schema_version": 1,
        "passed": bool(summary.iloc[0]["passed"]),
        "parameters": asdict(config),
        "thresholds": asdict(thresholds),
        "resolved_score_column": score_column,
        "resolved_scenario_columns": scenario_columns,
        "summary": _record(summary.iloc[0]),
    }
    return BacktestOverfitReport(
        combinations=combination_rows,
        scenario_stability=stability,
        partition_scores=partition_scores.reset_index(),
        partition_map=partition_map,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
    )


def write_backtest_overfit_audit(
    selection_path: str | Path,
    *,
    output_dir: str | Path,
    config: BacktestOverfitConfig | None = None,
    thresholds: BacktestOverfitThresholds | None = None,
) -> BacktestOverfitReport:
    config = config or BacktestOverfitConfig()
    thresholds = thresholds or BacktestOverfitThresholds()
    selection = Path(selection_path).resolve()
    runs_path, scores_path = _selection_files(selection)
    manifest_path = selection / "manifest.json" if selection.is_dir() else selection.parent / "manifest.json"
    manifest_provided = manifest_path.is_file()
    report = evaluate_backtest_overfit(
        pd.read_csv(runs_path),
        scenario_scores=pd.read_csv(scores_path) if scores_path is not None else None,
        config=config,
        thresholds=thresholds,
        selection_manifest_provided=manifest_provided,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.combinations.to_csv(out / "backtest_overfit_combinations.csv", index=False)
    report.scenario_stability.to_csv(out / "backtest_overfit_scenario_stability.csv", index=False)
    report.partition_scores.to_csv(out / "backtest_overfit_partition_scores.csv", index=False)
    report.partition_map.to_csv(out / "backtest_overfit_partition_map.csv", index=False)
    report.checks.to_csv(out / "backtest_overfit_checks.csv", index=False)
    report.summary.to_csv(out / "backtest_overfit_summary.csv", index=False)
    report.action_queue.to_csv(out / "backtest_overfit_action_queue.csv", index=False)

    payload = dict(report.config)
    payload.update(
        {
            "selection_path": str(selection),
            "scenario_runs_path": str(runs_path.resolve()),
            "scenario_scores_path": str(scores_path.resolve()) if scores_path is not None else "",
            "selection_manifest_path": str(manifest_path.resolve()) if manifest_provided else "",
            "selection_manifest_sha256": file_sha256(manifest_path) if manifest_provided else "",
        }
    )
    (out / "backtest_overfit_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "backtest_overfit_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.checks, report.action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {
        "selection": selection,
        "scenario_runs": runs_path,
    }
    if scores_path is not None:
        inputs["scenario_scores"] = scores_path
    if manifest_provided:
        inputs["selection_manifest"] = manifest_path
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "thresholds": asdict(thresholds),
            "resolved_score_column": payload["resolved_score_column"],
            "resolved_scenario_columns": payload["resolved_scenario_columns"],
        },
        inputs=inputs,
        extra={
            "passed": bool(report.passed),
            "probability_overfit": _float(report.summary.iloc[0].get("probability_overfit")),
            "selection_path": str(selection),
            "score_column": payload["resolved_score_column"],
            "scenario_columns": payload["resolved_scenario_columns"],
        },
    )
    return BacktestOverfitReport(
        report.combinations,
        report.scenario_stability,
        report.partition_scores,
        report.partition_map,
        report.checks,
        report.summary,
        report.action_queue,
        payload,
        out,
    )


def _attach_scenario_keys(
    runs: pd.DataFrame,
    scores: pd.DataFrame,
    configured_columns: tuple[str, ...],
) -> tuple[pd.DataFrame, list[str]]:
    if runs.empty:
        raise ValueError("scenario_runs is empty")
    out = runs.copy()
    if configured_columns:
        columns = list(configured_columns)
        _require_columns(out, columns, "scenario_runs")
        out["_scenario_key"] = out.apply(lambda row: _scenario_key(row, columns), axis=1)
        return out, columns
    if "scenario_key" in out.columns and out["scenario_key"].astype(str).str.strip().ne("").all():
        out["_scenario_key"] = out["scenario_key"].astype(str)
        return out, ["scenario_key"]
    parameter_columns = _inferred_parameter_columns(out, scores)
    if parameter_columns and not scores.empty and "scenario_key" in scores.columns:
        mapping = scores[parameter_columns + ["scenario_key"]].drop_duplicates()
        if mapping.duplicated(parameter_columns).any():
            raise ValueError("scenario_scores maps one parameter set to multiple scenario keys")
        out = out.merge(mapping, on=parameter_columns, how="left", validate="many_to_one")
        if out["scenario_key"].isna().any():
            raise ValueError("scenario_runs contains parameter sets missing from scenario_scores")
        out["_scenario_key"] = out["scenario_key"].astype(str)
        return out, parameter_columns
    if "run" in out.columns and out["run"].astype(str).str.strip().ne("").all():
        out["_scenario_key"] = out["run"].astype(str)
        return out, ["run"]
    raise ValueError("could not infer scenario identity; provide scenario_columns")


def _inferred_parameter_columns(runs: pd.DataFrame, scores: pd.DataFrame) -> list[str]:
    if scores.empty:
        return []
    return [
        column
        for column in scores.columns
        if column in runs.columns and column not in NON_PARAMETER_COLUMNS
    ]


def _observations(runs: pd.DataFrame, split_column: str, score_column: str) -> pd.DataFrame:
    _require_columns(runs, [split_column, score_column, "_scenario_key"], "scenario_runs")
    frame = runs[[split_column, "_scenario_key", score_column]].copy()
    frame[split_column] = frame[split_column].astype(str)
    frame["_scenario_key"] = frame["_scenario_key"].astype(str)
    frame["selection_score"] = pd.to_numeric(frame[score_column], errors="coerce")
    frame = frame.loc[np.isfinite(frame["selection_score"])].copy()
    if frame.empty:
        raise ValueError(f"scenario_runs has no finite {score_column} values")
    return frame[[split_column, "_scenario_key", "selection_score"]]


def _partition_map(observations: pd.DataFrame, split_column: str, max_partitions: int) -> pd.DataFrame:
    split_values = list(pd.unique(observations[split_column]))
    partition_count = min(len(split_values), max_partitions)
    if partition_count > 1 and partition_count % 2:
        partition_count -= 1
    if partition_count < 2:
        return pd.DataFrame(columns=["split", "partition", "partition_label"])
    groups = np.array_split(np.array(split_values, dtype=object), partition_count)
    rows = []
    for partition, values in enumerate(groups):
        label = f"P{partition:02d}"
        for value in values.tolist():
            rows.append({"split": str(value), "partition": partition, "partition_label": label})
    return pd.DataFrame(rows)


def _partition_score_matrix(
    observations: pd.DataFrame,
    partition_map: pd.DataFrame,
    split_column: str,
) -> tuple[pd.DataFrame, int]:
    scenario_count = int(observations["_scenario_key"].nunique())
    if partition_map.empty:
        return pd.DataFrame(), scenario_count
    merged = observations.merge(
        partition_map[["split", "partition"]],
        left_on=split_column,
        right_on="split",
        how="inner",
        validate="many_to_one",
    )
    matrix = merged.pivot_table(
        index="partition",
        columns="_scenario_key",
        values="selection_score",
        aggfunc="mean",
    ).sort_index()
    complete = matrix.dropna(axis=1, how="any")
    return complete, scenario_count - int(complete.shape[1])


def _cscv_combinations(matrix: pd.DataFrame, partition_map: pd.DataFrame) -> pd.DataFrame:
    columns = matrix.columns.astype(str).tolist()
    partition_count = int(len(matrix))
    if partition_count < 2 or partition_count % 2 or len(columns) < 2:
        return pd.DataFrame(columns=_combination_columns())
    half = partition_count // 2
    rows: list[dict[str, Any]] = []
    partitions = list(matrix.index)
    labels = _partition_labels(partition_map)
    for combination_id, is_positions in enumerate(combinations(range(partition_count), half)):
        is_partitions = [partitions[position] for position in is_positions]
        oos_partitions = [value for value in partitions if value not in is_partitions]
        is_scores = matrix.loc[is_partitions].mean(axis=0)
        oos_scores = matrix.loc[oos_partitions].mean(axis=0)
        selected = _best_scenario(is_scores)
        selected_is = float(is_scores[selected])
        selected_oos = float(oos_scores[selected])
        oos_ranks = oos_scores.rank(method="average", ascending=True)
        oos_rank = float(oos_ranks[selected])
        percentile = oos_rank / (len(oos_scores) + 1.0)
        logit = math.log(percentile / (1.0 - percentile))
        rank_correlation = _rank_correlation(is_scores, oos_scores)
        rows.append(
            {
                "combination_id": combination_id,
                "is_partitions": json.dumps([labels[int(value)] for value in is_partitions]),
                "oos_partitions": json.dumps([labels[int(value)] for value in oos_partitions]),
                "selected_scenario": selected,
                "selected_is_score": selected_is,
                "selected_oos_score": selected_oos,
                "selection_degradation": selected_is - selected_oos,
                "oos_rank": oos_rank,
                "oos_rank_percentile": percentile,
                "oos_rank_logit": logit,
                "overfit": bool(logit <= 0.0),
                "oos_positive": bool(selected_oos > 0.0),
                "rank_correlation": rank_correlation,
            }
        )
    return pd.DataFrame(rows, columns=_combination_columns())


def _scenario_stability(combinations_frame: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    rows = []
    total = int(len(combinations_frame))
    for scenario in scenarios:
        selected = combinations_frame.loc[
            combinations_frame.get("selected_scenario", pd.Series(dtype=str)).astype(str) == scenario
        ] if not combinations_frame.empty else pd.DataFrame()
        rows.append(
            {
                "scenario_key": scenario,
                "selected_combinations": int(len(selected)),
                "selection_rate": float(len(selected) / total) if total else 0.0,
                "median_selected_is_score": _median(selected, "selected_is_score"),
                "median_selected_oos_score": _median(selected, "selected_oos_score"),
                "median_selection_degradation": _median(selected, "selection_degradation"),
                "overfit_rate_when_selected": _bool_rate(selected, "overfit"),
                "oos_positive_rate_when_selected": _bool_rate(selected, "oos_positive"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["selected_combinations", "median_selected_oos_score", "scenario_key"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _checks(
    *,
    observations: pd.DataFrame,
    partition_scores: pd.DataFrame,
    partition_map: pd.DataFrame,
    combinations_frame: pd.DataFrame,
    stability: pd.DataFrame,
    selection_candidate: str,
    selection_manifest_provided: bool,
    excluded_scenarios: int,
    config: BacktestOverfitConfig,
    thresholds: BacktestOverfitThresholds,
) -> pd.DataFrame:
    split_count = int(observations[config.split_column].nunique())
    partition_count = int(partition_map["partition"].nunique()) if not partition_map.empty else 0
    scenario_count = int(partition_scores.shape[1])
    combination_count = int(len(combinations_frame))
    probability_overfit = _bool_rate(combinations_frame, "overfit")
    median_oos = _median(combinations_frame, "selected_oos_score")
    positive_rate = _bool_rate(combinations_frame, "oos_positive")
    median_correlation = _median(combinations_frame, "rank_correlation")
    median_degradation = _median(combinations_frame, "selection_degradation")
    candidate = _stability_row(stability, selection_candidate)
    candidate_selection_rate = _float(candidate.get("selection_rate"))
    candidate_overfit_rate = _float(candidate.get("overfit_rate_when_selected"))
    candidate_oos_positive_rate = _float(candidate.get("oos_positive_rate_when_selected"))
    rows = [
        _check(
            "selection_manifest_provided",
            selection_manifest_provided,
            "is",
            True,
            selection_manifest_provided or not config.require_selection_manifest,
            "selection manifest is required for audit provenance",
        ),
        _check(
            "split_count",
            split_count,
            ">=",
            thresholds.min_partitions,
            split_count >= thresholds.min_partitions,
            "not enough independent sweep periods for overfit audit",
        ),
        _check(
            "partition_count",
            partition_count,
            ">=",
            thresholds.min_partitions,
            partition_count >= thresholds.min_partitions and partition_count % 2 == 0,
            "CSCV requires enough even out-of-sample partitions",
        ),
        _check(
            "complete_scenario_count",
            scenario_count,
            ">=",
            thresholds.min_scenarios,
            scenario_count >= thresholds.min_scenarios,
            "not enough complete scenarios across all partitions",
        ),
        _check(
            "excluded_incomplete_scenarios",
            excluded_scenarios,
            "==",
            0,
            excluded_scenarios == 0,
            "one or more scenarios are missing score coverage in a partition",
        ),
        _check(
            "cscv_combination_count",
            combination_count,
            ">=",
            math.comb(thresholds.min_partitions, thresholds.min_partitions // 2),
            combination_count >= math.comb(thresholds.min_partitions, thresholds.min_partitions // 2),
            "not enough CSCV combinations were evaluated",
        ),
        _numeric_check(
            "probability_overfit",
            probability_overfit,
            "<=",
            thresholds.max_probability_overfit,
            "probability of backtest overfitting exceeds threshold",
        ),
        _numeric_check(
            "median_selected_oos_score",
            median_oos,
            ">=",
            thresholds.min_median_oos_score,
            "selected scenarios do not retain enough median OOS score",
        ),
        _numeric_check(
            "oos_positive_rate",
            positive_rate,
            ">=",
            thresholds.min_oos_positive_rate,
            "selected scenarios are not positive often enough OOS",
        ),
        _numeric_check(
            "median_rank_correlation",
            median_correlation,
            ">=",
            thresholds.min_median_rank_correlation,
            "in-sample and out-of-sample scenario rankings are unstable",
        ),
        _check(
            "selection_candidate_audited",
            selection_candidate,
            "in",
            "scenario_stability",
            not candidate.empty,
            "the rank-1 selection candidate is absent from scenario stability evidence",
        ),
        _numeric_check(
            "selection_candidate_rate",
            candidate_selection_rate,
            ">=",
            thresholds.min_candidate_selection_rate,
            "the rank-1 selection candidate is not selected consistently across combinations",
        ),
        _numeric_check(
            "selection_candidate_overfit_rate",
            candidate_overfit_rate,
            "<=",
            thresholds.max_candidate_overfit_rate,
            "the rank-1 selection candidate is overfit too often when selected",
        ),
        _numeric_check(
            "selection_candidate_oos_positive_rate",
            candidate_oos_positive_rate,
            ">=",
            thresholds.min_candidate_oos_positive_rate,
            "the rank-1 selection candidate is not positive often enough OOS",
        ),
    ]
    if thresholds.max_median_degradation is not None:
        rows.append(
            _numeric_check(
                "median_selection_degradation",
                median_degradation,
                "<=",
                thresholds.max_median_degradation,
                "selected scenario performance degrades too much OOS",
            )
        )
    return pd.DataFrame(rows)


def _summary(
    *,
    observations: pd.DataFrame,
    partition_scores: pd.DataFrame,
    partition_map: pd.DataFrame,
    combinations_frame: pd.DataFrame,
    stability: pd.DataFrame,
    selection_candidate: str,
    checks: pd.DataFrame,
    score_column: str,
    scenario_columns: list[str],
    excluded_scenarios: int,
) -> pd.DataFrame:
    passed = bool(not checks.empty and checks["passed"].astype(bool).all())
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    most_selected = stability.iloc[0] if not stability.empty else pd.Series(dtype=object)
    candidate = _stability_row(stability, selection_candidate)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "ready": passed,
                "score_column": score_column,
                "scenario_columns": ";".join(scenario_columns),
                "split_count": int(observations.iloc[:, 0].nunique()),
                "partition_count": int(partition_map["partition"].nunique()) if not partition_map.empty else 0,
                "scenario_count": int(partition_scores.shape[1]),
                "excluded_incomplete_scenarios": excluded_scenarios,
                "combination_count": int(len(combinations_frame)),
                "probability_overfit": _bool_rate(combinations_frame, "overfit"),
                "median_selected_is_score": _median(combinations_frame, "selected_is_score"),
                "median_selected_oos_score": _median(combinations_frame, "selected_oos_score"),
                "median_selection_degradation": _median(combinations_frame, "selection_degradation"),
                "oos_positive_rate": _bool_rate(combinations_frame, "oos_positive"),
                "median_rank_correlation": _median(combinations_frame, "rank_correlation"),
                "negative_rank_correlation_rate": _numeric_rate_below(
                    combinations_frame,
                    "rank_correlation",
                    0.0,
                ),
                "most_selected_scenario": str(most_selected.get("scenario_key", "")),
                "most_selected_scenario_rate": _float(most_selected.get("selection_rate")),
                "selection_candidate_scenario": selection_candidate,
                "selection_candidate_rate": _float(candidate.get("selection_rate")),
                "selection_candidate_overfit_rate": _float(
                    candidate.get("overfit_rate_when_selected")
                ),
                "selection_candidate_oos_positive_rate": _float(
                    candidate.get("oos_positive_rate_when_selected")
                ),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "eligible_for_promotion_review" if passed else "retain_in_research",
                "next_gate": READY_NEXT_GATE if passed else REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(READY_NEXT_GATE if passed else REPAIR_NEXT_GATE),
                "primary_action_status": "ready" if passed else "blocked",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if checks.empty:
        return pd.DataFrame(columns=ACTION_QUEUE_COLUMNS)
    for _, check in checks.loc[~checks["passed"].astype(bool)].iterrows():
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "source": "backtest_overfit_checks",
                "component": "selection_overfit",
                "check": str(check["check"]),
                "actual": check["value"],
                "operator": check["operator"],
                "expected": check["threshold"],
                "action": "expand_or_repair_walkforward_evidence",
                "reason": str(check["reason"]),
                "recommendation": _recommendation(str(check["check"])),
                "next_gate": REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(REPAIR_NEXT_GATE),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out["action_queue_count"] = int(len(action_queue))
    out["blocked_action_count"] = int(len(action_queue))
    return out


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Backtest Overfit Audit",
        "",
        f"- Status: **{'passed' if bool(summary['passed']) else 'blocked'}**",
        f"- Score column: `{summary['score_column']}`",
        f"- Periods/partitions/scenarios: {int(summary['split_count'])}/{int(summary['partition_count'])}/{int(summary['scenario_count'])}",
        f"- CSCV combinations: {int(summary['combination_count'])}",
        f"- Probability of backtest overfitting: {_format_number(summary['probability_overfit'])}",
        f"- Median selected OOS score: {_format_number(summary['median_selected_oos_score'])}",
        f"- OOS positive rate: {_format_number(summary['oos_positive_rate'])}",
        f"- Median IS/OOS rank correlation: {_format_number(summary['median_rank_correlation'])}",
        f"- Most selected scenario: `{summary['most_selected_scenario']}` ({_format_number(summary['most_selected_scenario_rate'])})",
        f"- Selection candidate: `{summary['selection_candidate_scenario']}`",
        f"- Candidate selection rate: {_format_number(summary['selection_candidate_rate'])}",
        f"- Candidate overfit rate when selected: {_format_number(summary['selection_candidate_overfit_rate'])}",
        f"- Candidate OOS positive rate when selected: {_format_number(summary['selection_candidate_oos_positive_rate'])}",
        f"- Next gate: `{summary['next_gate']}`",
        "",
        "PBO is the fraction of symmetric train/test combinations where the in-sample winner ranks at or below the out-of-sample median. This audit measures selection risk; it does not prove future profitability.",
    ]
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    if not failed.empty:
        lines.extend(["", "## Blocking Checks", ""])
        for _, row in failed.iterrows():
            lines.append(f"- `{row['check']}`: {row['reason']}")
    if not action_queue.empty:
        lines.extend(["", "## Action Queue", ""])
        for _, row in action_queue.iterrows():
            lines.append(f"- `{row['check']}`: {row['recommendation']}")
    return "\n".join(lines) + "\n"


def _selection_files(selection: Path) -> tuple[Path, Path | None]:
    if selection.is_file():
        return selection, None
    if not selection.is_dir():
        raise FileNotFoundError(f"selection path does not exist: {selection}")
    runs_path = _first_existing(selection, RUN_FILE_NAMES)
    if runs_path is None:
        raise FileNotFoundError(f"selection does not contain one of {RUN_FILE_NAMES}: {selection}")
    return runs_path, _first_existing(selection, SCORE_FILE_NAMES)


def _first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    return None


def _score_column(runs: pd.DataFrame, configured: str) -> str:
    if configured:
        if configured not in runs.columns:
            raise ValueError(f"scenario_runs missing score column {configured}")
        return configured
    for column in DEFAULT_SCORE_COLUMNS:
        if column in runs.columns:
            return column
    raise ValueError(f"scenario_runs missing a supported score column: {DEFAULT_SCORE_COLUMNS}")


def _best_scenario(scores: pd.Series) -> str:
    frame = pd.DataFrame({"scenario": scores.index.astype(str), "score": scores.to_numpy()})
    return str(
        frame.sort_values(["score", "scenario"], ascending=[False, True], kind="stable").iloc[0]["scenario"]
    )


def _selection_candidate(scores: pd.DataFrame, partition_scores: pd.DataFrame) -> str:
    if not scores.empty and "scenario_key" in scores.columns:
        work = scores.copy()
        if "selection_passed" in work.columns:
            passed = work["selection_passed"].map(_bool)
            if passed.any():
                work = work.loc[passed].copy()
        if "rank" in work.columns:
            work["_rank"] = pd.to_numeric(work["rank"], errors="coerce").fillna(len(work) + 1)
            work = work.sort_values(["_rank", "scenario_key"], kind="stable")
        else:
            work = work.sort_values("scenario_key", kind="stable")
        value = work.iloc[0].get("scenario_key")
        return "" if pd.isna(value) else str(value).strip()
    if partition_scores.empty:
        return ""
    return _best_scenario(partition_scores.mean(axis=0))


def _stability_row(stability: pd.DataFrame, scenario: str) -> pd.Series:
    if stability.empty or not scenario:
        return pd.Series(dtype=object)
    matched = stability.loc[stability["scenario_key"].astype(str) == scenario]
    return matched.iloc[0] if not matched.empty else pd.Series(dtype=object)


def _rank_correlation(left: pd.Series, right: pd.Series) -> float:
    left_rank = left.rank(method="average", ascending=True)
    right_rank = right.rank(method="average", ascending=True)
    if left_rank.nunique() <= 1 or right_rank.nunique() <= 1:
        return 0.0
    value = left_rank.corr(right_rank, method="pearson")
    return float(value) if pd.notna(value) else 0.0


def _partition_labels(partition_map: pd.DataFrame) -> dict[int, str]:
    labels: dict[int, str] = {}
    for partition, group in partition_map.groupby("partition", sort=True):
        labels[int(partition)] = f"{group.iloc[0]['partition_label']}:{'|'.join(group['split'].astype(str))}"
    return labels


def _combination_columns() -> list[str]:
    return [
        "combination_id",
        "is_partitions",
        "oos_partitions",
        "selected_scenario",
        "selected_is_score",
        "selected_oos_score",
        "selection_degradation",
        "oos_rank",
        "oos_rank_percentile",
        "oos_rank_logit",
        "overfit",
        "oos_positive",
        "rank_correlation",
    ]


def _scenario_key(row: pd.Series, columns: list[str]) -> str:
    return "|".join(f"{column}={_format_value(row[column])}" for column in columns)


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return "NA"
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return str(value)


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


def _numeric_check(
    name: str,
    value: float,
    operator: str,
    threshold: float,
    reason: str,
) -> dict[str, Any]:
    finite = bool(np.isfinite(value))
    if operator == "<=":
        passed = finite and value <= threshold
    elif operator == ">=":
        passed = finite and value >= threshold
    else:
        raise ValueError(f"unsupported operator {operator}")
    return _check(name, value, operator, threshold, passed, reason)


def _median(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return math.nan
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.median()) if values.notna().any() else math.nan


def _bool_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return math.nan
    return float(frame[column].map(_bool).mean())


def _numeric_rate_below(frame: pd.DataFrame, column: str, threshold: float) -> float:
    if frame.empty or column not in frame.columns:
        return math.nan
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float((values < threshold).mean()) if not values.empty else math.nan


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
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


def _require_columns(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _validate_config(config: BacktestOverfitConfig, thresholds: BacktestOverfitThresholds) -> None:
    if not config.split_column.strip():
        raise ValueError("split_column must not be blank")
    if config.max_partitions < 2 or config.max_partitions % 2:
        raise ValueError("max_partitions must be an even integer of at least 2")
    if thresholds.min_partitions < 2 or thresholds.min_partitions % 2:
        raise ValueError("min_partitions must be an even integer of at least 2")
    if thresholds.min_partitions > config.max_partitions:
        raise ValueError("min_partitions must not exceed max_partitions")
    if thresholds.min_scenarios < 2:
        raise ValueError("min_scenarios must be at least 2")
    if not 0.0 <= thresholds.max_probability_overfit <= 1.0:
        raise ValueError("max_probability_overfit must be between 0 and 1")
    if not 0.0 <= thresholds.min_oos_positive_rate <= 1.0:
        raise ValueError("min_oos_positive_rate must be between 0 and 1")
    if not -1.0 <= thresholds.min_median_rank_correlation <= 1.0:
        raise ValueError("min_median_rank_correlation must be between -1 and 1")
    if not 0.0 <= thresholds.min_candidate_selection_rate <= 1.0:
        raise ValueError("min_candidate_selection_rate must be between 0 and 1")
    if not 0.0 <= thresholds.max_candidate_overfit_rate <= 1.0:
        raise ValueError("max_candidate_overfit_rate must be between 0 and 1")
    if not 0.0 <= thresholds.min_candidate_oos_positive_rate <= 1.0:
        raise ValueError("min_candidate_oos_positive_rate must be between 0 and 1")


def _recommendation(check: str) -> str:
    if check in {"split_count", "partition_count", "cscv_combination_count"}:
        return "add independent chronological sweep periods before selecting parameters"
    if check in {"complete_scenario_count", "excluded_incomplete_scenarios"}:
        return "rerun the same scenario grid on every sweep period"
    if check == "selection_manifest_provided":
        return "regenerate selection with compare-sweeps so provenance is manifest-backed"
    return "reduce parameter search breadth or collect more OOS periods before promotion"


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"


def _format_number(value: Any) -> str:
    number = _float(value)
    return "n/a" if not np.isfinite(number) else f"{number:.4f}"
