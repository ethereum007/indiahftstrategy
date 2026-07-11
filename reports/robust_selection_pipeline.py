from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.backtest_overfit import (
    BacktestOverfitConfig,
    BacktestOverfitReport,
    BacktestOverfitThresholds,
    write_backtest_overfit_audit,
)
from reports.backtest_holdout import (
    BacktestHoldoutConfig,
    BacktestHoldoutReport,
    BacktestHoldoutThresholds,
    write_backtest_holdout_audit,
)
from reports.backtest_significance import (
    BacktestSignificanceConfig,
    BacktestSignificanceReport,
    BacktestSignificanceThresholds,
    write_backtest_significance_audit,
)
from reports.manifest import write_experiment_manifest
from reports.promotion import (
    SCORE_METRIC_COLUMNS,
    PromotionReport,
    PromotionThresholds,
    write_promotion_report,
)
from reports.research_family_registration import (
    load_research_family_registration,
)
from reports.sweep_provenance import build_sweep_provenance
from reports.sweeps import SweepComparison, write_sweep_comparison


RUN_TYPE = "robust_selection_pipeline"
READY_NEXT_GATE = "stage-orders"
STAGE_NEXT_GATES = {
    "research_registration": "register-research-family",
    "sweep_provenance": "pipeline-robust-selection",
    "selection": "compare-sweeps",
    "backtest_overfit": "audit-backtest-overfit",
    "backtest_significance": "audit-backtest-significance",
    "backtest_holdout": "audit-backtest-holdout",
    "promotion": "promote-scenario",
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
class RobustSelectionPipelineReport:
    research_registration: pd.DataFrame
    preflight: pd.DataFrame
    sweep_provenance: pd.DataFrame
    stages: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    candidate_config: dict[str, Any]
    selection: SweepComparison
    overfit: BacktestOverfitReport
    significance: BacktestSignificanceReport
    holdout: BacktestHoldoutReport
    promotion: PromotionReport
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_robust_selection_pipeline(
    sweep_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    group_cols: list[str] | None = None,
    strategy: str = "generic",
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    selection_min_pass_rate: float = 1.0,
    selection_min_sweeps: int | None = None,
    selection_min_median_net_pnl: float = 0.0,
    selection_max_worst_drawdown: float | None = None,
    overfit_config: BacktestOverfitConfig | None = None,
    overfit_thresholds: BacktestOverfitThresholds | None = None,
    significance_config: BacktestSignificanceConfig | None = None,
    significance_thresholds: BacktestSignificanceThresholds | None = None,
    holdout_sweeps: int = 3,
    holdout_config: BacktestHoldoutConfig | None = None,
    holdout_thresholds: BacktestHoldoutThresholds | None = None,
    promotion_thresholds: PromotionThresholds | None = None,
    research_registration_path: str | Path | None = None,
    registered_study_label: str | None = None,
    require_research_registration: bool = False,
) -> RobustSelectionPipelineReport:
    paths = [Path(path).resolve() for path in sweep_paths]
    if not paths:
        raise ValueError("at least one sweep path is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match sweep_paths length")
    if holdout_sweeps < 1:
        raise ValueError("holdout_sweeps must be positive")
    if len(paths) <= holdout_sweeps:
        raise ValueError("sweep_paths must include development and holdout periods")

    development_paths = paths[:-holdout_sweeps]
    reserved_paths = paths[-holdout_sweeps:]
    development_labels = labels[:-holdout_sweeps] if labels is not None else None
    reserved_labels = labels[-holdout_sweeps:] if labels is not None else None

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    selection_dir = out / "01_selection"
    overfit_dir = out / "02_backtest_overfit"
    significance_dir = out / "02_backtest_significance"
    holdout_dir = out / "02_backtest_holdout"
    promotion_dir = out / "03_promotion"

    resolved_selection_min_sweeps = (
        len(development_paths)
        if selection_min_sweeps is None
        else selection_min_sweeps
    )
    overfit_config = overfit_config or BacktestOverfitConfig()
    if not overfit_config.require_selection_manifest:
        overfit_config = replace(overfit_config, require_selection_manifest=True)
    overfit_thresholds = overfit_thresholds or BacktestOverfitThresholds()
    significance_config = significance_config or BacktestSignificanceConfig()
    significance_thresholds = (
        significance_thresholds or BacktestSignificanceThresholds()
    )
    promotion_thresholds = replace(
        promotion_thresholds or PromotionThresholds(),
        require_overfit_audit=True,
        require_significance_audit=True,
        require_holdout_audit=True,
    )

    sweep_provenance = build_sweep_provenance(
        paths,
        labels,
        roles=(
            ["development"] * len(development_paths)
            + ["holdout"] * len(reserved_paths)
        ),
    )
    sweep_provenance_path = out / "robust_selection_pipeline_sweep_provenance.csv"
    sweep_provenance.to_csv(sweep_provenance_path, index=False)
    sweep_provenance_passed = bool(
        not sweep_provenance.empty and sweep_provenance["passed"].astype(bool).all()
    )

    selection = write_sweep_comparison(
        development_paths,
        output_dir=selection_dir,
        labels=development_labels,
        group_cols=group_cols,
        min_pass_rate=selection_min_pass_rate,
        min_sweeps=resolved_selection_min_sweeps,
        min_median_net_pnl=selection_min_median_net_pnl,
        max_worst_drawdown=selection_max_worst_drawdown,
    )
    resolved_group_cols = group_cols or [
        column
        for column in selection.scenario_scores.columns
        if column not in SCORE_METRIC_COLUMNS
    ]
    if not resolved_group_cols:
        raise ValueError("unable to resolve scenario group columns")
    if not overfit_config.scenario_columns:
        overfit_config = replace(
            overfit_config,
            scenario_columns=tuple(resolved_group_cols),
        )
    overfit = write_backtest_overfit_audit(
        selection_dir,
        output_dir=overfit_dir,
        config=overfit_config,
        thresholds=overfit_thresholds,
    )
    significance = write_backtest_significance_audit(
        overfit_dir,
        output_dir=significance_dir,
        config=significance_config,
        thresholds=significance_thresholds,
    )
    resolved_score_column = str(
        overfit.config.get("resolved_score_column", overfit_config.score_column)
    )
    overfit_row = (
        overfit.summary.iloc[0]
        if not overfit.summary.empty
        else pd.Series(dtype=object)
    )
    research_registration = _research_registration_binding(
        research_registration_path,
        registered_study_label=registered_study_label,
        require_registration=require_research_registration,
        output_dir=out,
        strategy=strategy,
        market=market,
        primary_metric=resolved_score_column,
        scenario_count=_int(overfit_row.get("scenario_count")),
        development_sweeps=len(development_paths),
        holdout_sweeps=len(reserved_paths),
    )
    research_registration_path_out = (
        out / "robust_selection_pipeline_research_registration.csv"
    )
    research_registration.to_csv(research_registration_path_out, index=False)
    research_registration_passed = bool(
        not research_registration.empty
        and research_registration["passed"].map(_to_bool).all()
    )
    preflight = pd.DataFrame(
        [
            {
                "component": "research_registration",
                "passed": research_registration_passed,
                "evidence_path": str(research_registration_path_out),
                "detail": str(research_registration.iloc[0].get("detail", "")),
            },
            {
                "component": "sweep_provenance",
                "passed": sweep_provenance_passed,
                "evidence_path": str(sweep_provenance_path),
                "detail": (
                    f"current_sweep_manifests="
                    f"{int(sweep_provenance['passed'].map(_to_bool).sum())}/"
                    f"{len(sweep_provenance)}"
                ),
            },
        ]
    )
    preflight_path = out / "robust_selection_pipeline_preflight.csv"
    preflight.to_csv(preflight_path, index=False)
    preflight_passed = bool(preflight["passed"].map(_to_bool).all())
    holdout_config = holdout_config or BacktestHoldoutConfig(
        group_columns=tuple(resolved_group_cols),
    )
    holdout_config = replace(
        holdout_config,
        group_columns=tuple(resolved_group_cols),
        score_column=resolved_score_column,
        require_selection_manifest=True,
        require_sweep_manifests=True,
    )
    holdout_thresholds = holdout_thresholds or BacktestHoldoutThresholds(
        min_sweeps=holdout_sweeps
    )
    holdout = write_backtest_holdout_audit(
        selection_dir,
        reserved_paths,
        output_dir=holdout_dir,
        config=holdout_config,
        labels=reserved_labels,
        thresholds=holdout_thresholds,
    )
    promotion = write_promotion_report(
        selection_dir,
        output_dir=promotion_dir,
        overfit_audit_path=overfit_dir,
        significance_audit_path=significance_dir,
        holdout_audit_path=holdout_dir,
        thresholds=promotion_thresholds,
        upstream_integrity_passed=preflight_passed,
        upstream_integrity_path=preflight_path,
    )

    stages = _stages(
        research_registration,
        sweep_provenance,
        selection,
        overfit,
        significance,
        holdout,
        promotion,
    )
    action_queue = _action_queue(stages)
    summary = _summary(
        stages,
        action_queue,
        selection,
        overfit,
        significance,
        holdout,
        promotion,
        strategy=strategy,
        market=market,
        sweep_count=len(paths),
        research_registration=research_registration,
        sweep_provenance=sweep_provenance,
    )
    candidate_config = _candidate_config(
        promotion_dir,
        summary.iloc[0],
        stages,
        development_paths,
        reserved_paths,
        strategy=strategy,
        market=market,
    )

    stages.to_csv(out / "robust_selection_pipeline_stages.csv", index=False)
    summary.to_csv(out / "robust_selection_pipeline_summary.csv", index=False)
    action_queue.to_csv(out / "robust_selection_pipeline_action_queue.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(candidate_config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "robust_selection_pipeline_runbook.md").write_text(
        _runbook(summary.iloc[0], stages, action_queue),
        encoding="utf-8",
    )

    parameters = {
        "labels": labels,
        "group_cols": group_cols,
        "strategy": strategy,
        "market": market,
        "require_sweep_manifests": True,
        "research_registration_path": (
            str(Path(research_registration_path).resolve())
            if research_registration_path is not None
            else ""
        ),
        "registered_study_label": str(registered_study_label or ""),
        "require_research_registration": bool(require_research_registration),
        "selection": {
            "min_pass_rate": selection_min_pass_rate,
            "min_sweeps": resolved_selection_min_sweeps,
            "min_median_net_pnl": selection_min_median_net_pnl,
            "max_worst_drawdown": selection_max_worst_drawdown,
        },
        "overfit_config": asdict(overfit_config),
        "overfit_thresholds": asdict(overfit_thresholds),
        "significance_config": asdict(significance_config),
        "significance_thresholds": asdict(significance_thresholds),
        "holdout_sweeps": holdout_sweeps,
        "holdout_config": asdict(holdout_config),
        "holdout_thresholds": asdict(holdout_thresholds),
        "promotion_thresholds": asdict(promotion_thresholds),
    }
    inputs: dict[str, Any] = {
        "development_sweeps": development_paths,
        "holdout_sweeps": reserved_paths,
        "sweep_manifests": [
            Path(path)
            for path in sweep_provenance["manifest_path"].astype(str)
            if path and Path(path).is_file()
        ],
        "selection_manifest": selection_dir / "manifest.json",
        "backtest_overfit_manifest": overfit_dir / "manifest.json",
        "backtest_significance_manifest": significance_dir / "manifest.json",
        "backtest_holdout_manifest": holdout_dir / "manifest.json",
        "promotion_manifest": promotion_dir / "manifest.json",
    }
    registration_row = research_registration.iloc[0]
    if _to_bool(registration_row.get("provided", False)):
        registration_root = Path(str(registration_row.get("registration_path", "")))
        registration_manifest = Path(
            str(registration_row.get("registration_manifest_path", ""))
        )
        if registration_root.is_dir():
            inputs["research_family_registration"] = registration_root
        if registration_manifest.is_file():
            inputs["research_family_registration_manifest"] = registration_manifest
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters=parameters,
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "strategy": strategy,
            "market": market,
            "candidate_scenario_key": str(summary.iloc[0]["candidate_scenario_key"]),
            "probability_overfit": _float(summary.iloc[0].get("probability_overfit")),
            "sweep_provenance_passed": bool(
                summary.iloc[0]["sweep_provenance_passed"]
            ),
            "research_registration_provided": bool(
                summary.iloc[0]["research_registration_provided"]
            ),
            "research_registration_passed": bool(
                summary.iloc[0]["research_registration_passed"]
            ),
            "research_registration_id": str(
                summary.iloc[0]["research_registration_id"]
            ),
            "research_registration_manifest_sha256": str(
                summary.iloc[0]["research_registration_manifest_sha256"]
            ),
            "registered_study_label": str(
                summary.iloc[0]["registered_study_label"]
            ),
            "backtest_significance_passed": bool(
                summary.iloc[0]["backtest_significance_passed"]
            ),
            "backtest_holdout_passed": bool(
                summary.iloc[0]["backtest_holdout_passed"]
            ),
            "authorizes_submission": False,
        },
    )
    return RobustSelectionPipelineReport(
        research_registration=research_registration,
        preflight=preflight,
        sweep_provenance=sweep_provenance,
        stages=stages,
        summary=summary,
        action_queue=action_queue,
        candidate_config=candidate_config,
        selection=selection,
        overfit=overfit,
        significance=significance,
        holdout=holdout,
        promotion=promotion,
        output_dir=out,
    )


def _research_registration_binding(
    raw_path: str | Path | None,
    *,
    registered_study_label: str | None,
    require_registration: bool,
    output_dir: Path,
    strategy: str,
    market: str,
    primary_metric: str,
    scenario_count: int,
    development_sweeps: int,
    holdout_sweeps: int,
) -> pd.DataFrame:
    provided = raw_path is not None
    study_label = str(registered_study_label or "").strip()
    requested = bool(provided or study_label or require_registration)
    base: dict[str, Any] = {
        "provided": provided,
        "required": bool(require_registration),
        "skipped": False,
        "passed": False,
        "registration_path": "",
        "registration_manifest_path": "",
        "registration_manifest_sha256": "",
        "registration_manifest_current": False,
        "registration_manifest_error": "",
        "registration_family_id": "",
        "registration_id": "",
        "registration_id_consistent": False,
        "registration_ready": False,
        "registered_study_label": study_label,
        "study_match_count": 0,
        "unique_study_match": False,
        "planned_study_path": "",
        "actual_study_path": str(output_dir.resolve()),
        "study_path_matches": False,
        "planned_strategy": "",
        "actual_strategy": strategy,
        "strategy_matches": False,
        "planned_market": "",
        "actual_market": market,
        "market_matches": False,
        "planned_primary_metric": "",
        "actual_primary_metric": primary_metric,
        "primary_metric_matches": False,
        "max_scenarios": 0,
        "actual_scenarios": scenario_count,
        "search_breadth_within_plan": False,
        "planned_development_sweeps": 0,
        "actual_development_sweeps": development_sweeps,
        "development_sweeps_match": False,
        "planned_holdout_sweeps": 0,
        "actual_holdout_sweeps": holdout_sweeps,
        "holdout_sweeps_match": False,
        "contract_matches": False,
        "failed_checks": 0,
        "failed_check_names": "",
        "detail": "",
        "recommendation": "register_or_repair_the_research_family_plan",
    }
    if not provided:
        passed = not requested
        base.update(
            {
                "skipped": passed,
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "failed_check_names": "" if passed else "registration_provided",
                "detail": (
                    "optional_registration_not_provided"
                    if passed
                    else "research_registration_and_study_label_are_required"
                ),
                "recommendation": (
                    "continue_without_prospective_registration"
                    if passed
                    else "register_the_research_family_before_running_this_study"
                ),
            }
        )
        return pd.DataFrame([base])

    raw = Path(raw_path).resolve()
    root = raw if raw.is_dir() else raw.parent
    base["registration_path"] = str(root)
    base["registration_manifest_path"] = str(root / "manifest.json")
    try:
        snapshot = load_research_family_registration(root)
    except (OSError, ValueError, KeyError) as exc:
        base.update(
            {
                "registration_manifest_error": f"{type(exc).__name__}: {exc}",
                "failed_checks": 1,
                "failed_check_names": "registration_loadable",
                "detail": "registration_artifacts_could_not_be_loaded",
            }
        )
        return pd.DataFrame([base])

    matches = snapshot.studies.loc[
        snapshot.studies.get(
            "study_label",
            pd.Series("", index=snapshot.studies.index),
        )
        .astype(str)
        .eq(study_label)
    ]
    unique_match = bool(study_label and len(matches) == 1)
    plan = matches.iloc[0] if unique_match else pd.Series(dtype=object)
    planned_path = str(plan.get("planned_study_path", ""))
    planned_strategy = str(plan.get("strategy", ""))
    planned_market = str(plan.get("market", ""))
    planned_metric = str(plan.get("primary_metric", ""))
    max_scenarios = _int(plan.get("max_scenarios"))
    planned_development = _int(plan.get("development_sweeps"))
    planned_holdout = _int(plan.get("holdout_sweeps"))
    path_matches = bool(
        planned_path
        and _canonical_path(planned_path) == _canonical_path(output_dir)
    )
    strategy_matches = bool(planned_strategy and planned_strategy == strategy)
    market_matches = bool(planned_market and planned_market == market)
    metric_matches = bool(planned_metric and planned_metric == primary_metric)
    breadth_matches = bool(
        scenario_count > 0
        and max_scenarios > 0
        and scenario_count <= max_scenarios
    )
    development_matches = bool(
        planned_development > 0 and planned_development == development_sweeps
    )
    holdout_matches = bool(
        planned_holdout > 0 and planned_holdout == holdout_sweeps
    )
    contract_matches = bool(
        unique_match
        and path_matches
        and strategy_matches
        and market_matches
        and metric_matches
        and breadth_matches
        and development_matches
        and holdout_matches
    )
    checks = {
        "registration_ready": snapshot.ready,
        "registration_manifest_current": snapshot.manifest_current,
        "registration_id_consistent": snapshot.registration_id_consistent,
        "unique_study_match": unique_match,
        "study_path_matches": path_matches,
        "strategy_matches": strategy_matches,
        "market_matches": market_matches,
        "primary_metric_matches": metric_matches,
        "search_breadth_within_plan": breadth_matches,
        "development_sweeps_match": development_matches,
        "holdout_sweeps_match": holdout_matches,
    }
    failed = [name for name, value in checks.items() if not value]
    passed = not failed
    base.update(
        {
            "passed": passed,
            "registration_path": str(snapshot.root),
            "registration_manifest_path": str(snapshot.root / "manifest.json"),
            "registration_manifest_sha256": snapshot.manifest_sha256,
            "registration_manifest_current": snapshot.manifest_current,
            "registration_manifest_error": snapshot.manifest_error,
            "registration_family_id": snapshot.family_id,
            "registration_id": snapshot.registration_id,
            "registration_id_consistent": snapshot.registration_id_consistent,
            "registration_ready": snapshot.ready,
            "study_match_count": int(len(matches)),
            "unique_study_match": unique_match,
            "planned_study_path": planned_path,
            "study_path_matches": path_matches,
            "planned_strategy": planned_strategy,
            "strategy_matches": strategy_matches,
            "planned_market": planned_market,
            "market_matches": market_matches,
            "planned_primary_metric": planned_metric,
            "primary_metric_matches": metric_matches,
            "max_scenarios": max_scenarios,
            "search_breadth_within_plan": breadth_matches,
            "planned_development_sweeps": planned_development,
            "development_sweeps_match": development_matches,
            "planned_holdout_sweeps": planned_holdout,
            "holdout_sweeps_match": holdout_matches,
            "contract_matches": contract_matches,
            "failed_checks": len(failed),
            "failed_check_names": ",".join(failed),
            "detail": (
                f"registration_id={snapshot.registration_id};study={study_label}"
                if passed
                else f"failed_checks={','.join(failed)}"
            ),
            "recommendation": (
                "continue_to_manifest_bound_sweep_validation"
                if passed
                else "register_or_repair_the_research_family_plan"
            ),
        }
    )
    return pd.DataFrame([base])


def _stages(
    research_registration: pd.DataFrame,
    sweep_provenance: pd.DataFrame,
    selection: SweepComparison,
    overfit: BacktestOverfitReport,
    significance: BacktestSignificanceReport,
    holdout: BacktestHoldoutReport,
    promotion: PromotionReport,
) -> pd.DataFrame:
    selection_row = (
        selection.summary.iloc[0]
        if not selection.summary.empty
        else pd.Series(dtype=object)
    )
    overfit_row = overfit.summary.iloc[0] if not overfit.summary.empty else pd.Series(dtype=object)
    significance_row = (
        significance.summary.iloc[0]
        if not significance.summary.empty
        else pd.Series(dtype=object)
    )
    holdout_row = (
        holdout.summary.iloc[0]
        if not holdout.summary.empty
        else pd.Series(dtype=object)
    )
    promotion_row = (
        promotion.summary.iloc[0]
        if not promotion.summary.empty
        else pd.Series(dtype=object)
    )
    provenance_passed = bool(
        not sweep_provenance.empty and sweep_provenance["passed"].astype(bool).all()
    )
    provenance_failed = int(
        (~sweep_provenance["passed"].astype(bool)).sum()
    ) if not sweep_provenance.empty else 1
    registration_row = (
        research_registration.iloc[0]
        if not research_registration.empty
        else pd.Series(dtype=object)
    )
    registration_passed = _to_bool(registration_row.get("passed", False))
    registration_skipped = _to_bool(registration_row.get("skipped", False))
    return pd.DataFrame(
        [
            {
                "stage": "research_registration",
                "status": registration_passed,
                "status_column": "passed",
                "skipped": registration_skipped,
                "output_dir": str(
                    registration_row.get("registration_path", "")
                ),
                "failed_checks": 0 if registration_passed else 1,
                "recommendation": str(
                    registration_row.get(
                        "recommendation",
                        "register_or_repair_the_research_family_plan",
                    )
                ),
                "detail": str(registration_row.get("detail", "")),
            },
            {
                "stage": "sweep_provenance",
                "status": provenance_passed,
                "status_column": "passed",
                "skipped": False,
                "output_dir": "",
                "failed_checks": provenance_failed,
                "recommendation": (
                    "continue_to_selection"
                    if provenance_passed
                    else "regenerate_or_restore_manifest_backed_sweep_inputs"
                ),
                "detail": (
                    f"current_sweep_manifests={len(sweep_provenance) - provenance_failed}/"
                    f"{len(sweep_provenance)}"
                ),
            },
            {
                "stage": "selection",
                "status": bool(selection.has_selection),
                "status_column": "selectable_scenarios",
                "skipped": False,
                "output_dir": str(selection.output_dir or ""),
                "failed_checks": 0 if selection.has_selection else 1,
                "recommendation": (
                    "audit_parameter_selection"
                    if selection.has_selection
                    else "rerun_consistent_scenarios_across_all_sweeps"
                ),
                "detail": f"selectable_scenarios={_int(selection_row.get('selectable_scenarios'))}",
            },
            {
                "stage": "backtest_overfit",
                "status": bool(overfit.passed),
                "status_column": "passed",
                "skipped": False,
                "output_dir": str(overfit.output_dir or ""),
                "failed_checks": _int(overfit_row.get("failed_checks")),
                "recommendation": str(overfit_row.get("recommendation", "")),
                "detail": f"probability_overfit={_format_number(overfit_row.get('probability_overfit'))}",
            },
            {
                "stage": "backtest_significance",
                "status": bool(significance.passed),
                "status_column": "passed",
                "skipped": False,
                "output_dir": str(significance.output_dir or ""),
                "failed_checks": _int(significance_row.get("failed_checks")),
                "recommendation": str(significance_row.get("recommendation", "")),
                "detail": (
                    "adjusted_sign_pvalue="
                    f"{_format_number(significance_row.get('adjusted_sign_pvalue'))}"
                ),
            },
            {
                "stage": "backtest_holdout",
                "status": bool(holdout.passed),
                "status_column": "passed",
                "skipped": False,
                "output_dir": str(holdout.output_dir or ""),
                "failed_checks": _int(holdout_row.get("failed_checks")),
                "recommendation": str(holdout_row.get("recommendation", "")),
                "detail": (
                    "covered_sweeps="
                    f"{_int(holdout_row.get('covered_sweeps'))}/"
                    f"{_int(holdout_row.get('expected_sweeps'))}"
                ),
            },
            {
                "stage": "promotion",
                "status": bool(promotion.ready),
                "status_column": "ready",
                "skipped": False,
                "output_dir": str(promotion.output_dir or ""),
                "failed_checks": _int(promotion_row.get("failed_checks")),
                "recommendation": str(promotion_row.get("recommendation", "")),
                "detail": f"candidate={str(promotion_row.get('candidate_scenario_key', ''))}",
            },
        ]
    )


def _summary(
    stages: pd.DataFrame,
    action_queue: pd.DataFrame,
    selection: SweepComparison,
    overfit: BacktestOverfitReport,
    significance: BacktestSignificanceReport,
    holdout: BacktestHoldoutReport,
    promotion: PromotionReport,
    *,
    strategy: str,
    market: str,
    sweep_count: int,
    research_registration: pd.DataFrame,
    sweep_provenance: pd.DataFrame,
) -> pd.DataFrame:
    ready = bool(stages["status"].map(_to_bool).all()) if not stages.empty else False
    selection_row = selection.summary.iloc[0] if not selection.summary.empty else pd.Series(dtype=object)
    overfit_row = overfit.summary.iloc[0] if not overfit.summary.empty else pd.Series(dtype=object)
    significance_row = (
        significance.summary.iloc[0]
        if not significance.summary.empty
        else pd.Series(dtype=object)
    )
    holdout_row = (
        holdout.summary.iloc[0]
        if not holdout.summary.empty
        else pd.Series(dtype=object)
    )
    promotion_row = promotion.summary.iloc[0] if not promotion.summary.empty else pd.Series(dtype=object)
    registration_row = (
        research_registration.iloc[0]
        if not research_registration.empty
        else pd.Series(dtype=object)
    )
    first_failed = stages.loc[~stages["status"].map(_to_bool)]
    next_gate = READY_NEXT_GATE if ready else STAGE_NEXT_GATES.get(
        str(first_failed.iloc[0]["stage"]) if not first_failed.empty else "",
        "pipeline-robust-selection",
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": strategy,
                "market": market,
                "sweep_count": sweep_count,
                "development_sweep_count": int(
                    sweep_provenance["study_role"].astype(str).eq("development").sum()
                ),
                "holdout_sweep_count": int(
                    sweep_provenance["study_role"].astype(str).eq("holdout").sum()
                ),
                "research_registration_provided": _to_bool(
                    registration_row.get("provided", False)
                ),
                "research_registration_required": _to_bool(
                    registration_row.get("required", False)
                ),
                "research_registration_passed": _to_bool(
                    registration_row.get("passed", False)
                ),
                "research_registration_id": str(
                    registration_row.get("registration_id", "")
                ),
                "research_registration_manifest_sha256": str(
                    registration_row.get("registration_manifest_sha256", "")
                ),
                "registered_study_label": str(
                    registration_row.get("registered_study_label", "")
                ),
                "sweep_provenance_passed": bool(
                    not sweep_provenance.empty
                    and sweep_provenance["passed"].astype(bool).all()
                ),
                "sweep_manifest_count": int(
                    sweep_provenance["manifest_exists"].astype(bool).sum()
                ),
                "sweep_manifest_current_count": int(
                    sweep_provenance["passed"].astype(bool).sum()
                ),
                "sweep_manifest_required_artifact_match_count": int(
                    sweep_provenance["required_artifact_matches"].astype(int).sum()
                ),
                "selection_passed": bool(selection.has_selection),
                "selectable_scenarios": _int(selection_row.get("selectable_scenarios")),
                "backtest_overfit_passed": bool(overfit.passed),
                "probability_overfit": _float(overfit_row.get("probability_overfit")),
                "overfit_partition_count": _int(overfit_row.get("partition_count")),
                "overfit_scenario_count": _int(overfit_row.get("scenario_count")),
                "overfit_combination_count": _int(overfit_row.get("combination_count")),
                "selection_candidate_scenario": str(
                    overfit_row.get("selection_candidate_scenario", "")
                ),
                "selection_candidate_rate": _float(
                    overfit_row.get("selection_candidate_rate")
                ),
                "selection_candidate_overfit_rate": _float(
                    overfit_row.get("selection_candidate_overfit_rate")
                ),
                "selection_candidate_oos_positive_rate": _float(
                    overfit_row.get("selection_candidate_oos_positive_rate")
                ),
                "backtest_significance_passed": bool(significance.passed),
                "adjusted_sign_pvalue": _float(
                    significance_row.get("adjusted_sign_pvalue")
                ),
                "bootstrap_mean_lower": _float(
                    significance_row.get("bootstrap_mean_lower")
                ),
                "bootstrap_probability_positive": _float(
                    significance_row.get("bootstrap_probability_positive")
                ),
                "backtest_holdout_passed": bool(holdout.passed),
                "holdout_candidate_coverage_rate": _float(
                    holdout_row.get("candidate_coverage_rate")
                ),
                "holdout_proof_pass_rate": _float(
                    holdout_row.get("proof_pass_rate")
                ),
                "holdout_mean_score": _float(holdout_row.get("mean_score")),
                "holdout_worst_score": _float(holdout_row.get("worst_score")),
                "holdout_mean_net_pnl": _float(
                    holdout_row.get("mean_net_pnl")
                ),
                "holdout_worst_net_pnl": _float(
                    holdout_row.get("worst_net_pnl")
                ),
                "promotion_ready": bool(promotion.ready),
                "candidate_scenario_key": str(
                    promotion_row.get("candidate_scenario_key", "")
                ),
                "failed_stages": int((~stages["status"].map(_to_bool)).sum()),
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "recommendation": (
                    "stage_broker_neutral_orders_for_paper_or_shadow_review"
                    if ready
                    else "keep_candidate_in_research"
                ),
                "authorizes_submission": False,
            }
        ]
    )


def _action_queue(stages: pd.DataFrame) -> pd.DataFrame:
    failed = stages.loc[~stages["status"].map(_to_bool)] if not stages.empty else stages
    rows: list[dict[str, Any]] = []
    for priority, row in enumerate(failed.itertuples(index=False), start=1):
        next_gate = STAGE_NEXT_GATES.get(str(row.stage), "pipeline-robust-selection")
        reason = str(row.recommendation) or f"{row.stage} stage did not pass"
        rows.append(
            {
                "priority": priority,
                "queue_status": "blocked",
                "source": RUN_TYPE,
                "component": str(row.stage),
                "check": f"{row.stage}_ready",
                "actual": False,
                "operator": "is",
                "expected": True,
                "action": reason,
                "reason": reason,
                "recommendation": reason,
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _candidate_config(
    promotion_dir: Path,
    summary: pd.Series,
    stages: pd.DataFrame,
    development_sweep_paths: list[Path],
    holdout_sweep_paths: list[Path],
    *,
    strategy: str,
    market: str,
) -> dict[str, Any]:
    source_path = promotion_dir / "candidate_config.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    config = dict(source)
    config["ready"] = bool(summary["ready"])
    config["strategy"] = strategy
    config["market"] = market
    config["source_run_type"] = RUN_TYPE
    config["authorizes_submission"] = False
    config["failed_checks"] = stages.loc[
        ~stages["status"].map(_to_bool), "stage"
    ].astype(str).tolist()
    config["pipeline"] = {
        "ready": bool(summary["ready"]),
        "research_registration_provided": bool(
            summary["research_registration_provided"]
        ),
        "research_registration_required": bool(
            summary["research_registration_required"]
        ),
        "research_registration_passed": bool(
            summary["research_registration_passed"]
        ),
        "research_registration_id": str(summary["research_registration_id"]),
        "research_registration_manifest_sha256": str(
            summary["research_registration_manifest_sha256"]
        ),
        "registered_study_label": str(summary["registered_study_label"]),
        "sweep_provenance_passed": bool(summary["sweep_provenance_passed"]),
        "next_gate": str(summary["next_gate"]),
        "development_sweep_paths": [str(path) for path in development_sweep_paths],
        "holdout_sweep_paths": [str(path) for path in holdout_sweep_paths],
        "selection_path": str(promotion_dir.parent / "01_selection"),
        "backtest_overfit_path": str(promotion_dir.parent / "02_backtest_overfit"),
        "backtest_significance_path": str(
            promotion_dir.parent / "02_backtest_significance"
        ),
        "backtest_holdout_path": str(
            promotion_dir.parent / "02_backtest_holdout"
        ),
        "promotion_path": str(promotion_dir),
        "stages": [
            {
                "stage": str(row.stage),
                "status": bool(row.status),
                "recommendation": str(row.recommendation),
            }
            for row in stages.itertuples(index=False)
        ],
    }
    return config


def _runbook(summary: pd.Series, stages: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Robust Selection Pipeline",
        "",
        f"- Status: **{'ready' if bool(summary['ready']) else 'blocked'}**",
        f"- Strategy/market: `{summary['strategy']}` / `{summary['market']}`",
        (
            "- Research registration: "
            f"{'bound' if bool(summary['research_registration_provided']) else 'not provided'}"
            f"; passed `{str(bool(summary['research_registration_passed'])).lower()}`"
        ),
        f"- Registered study label: `{summary['registered_study_label']}`",
        (
            "- Sweep periods (development/holdout): "
            f"{int(summary['sweep_count'])} "
            f"({int(summary['development_sweep_count'])}/"
            f"{int(summary['holdout_sweep_count'])})"
        ),
        f"- Current sweep manifests: {int(summary['sweep_manifest_current_count'])}/{int(summary['sweep_count'])}",
        f"- Candidate: `{summary['candidate_scenario_key']}`",
        f"- Probability of backtest overfitting: {_format_number(summary['probability_overfit'])}",
        f"- Trial-adjusted sign p-value: {_format_number(summary['adjusted_sign_pvalue'])}",
        f"- Bootstrap mean lower bound: {_format_number(summary['bootstrap_mean_lower'])}",
        "- Bootstrap P(mean > 0): "
        f"{_format_number(summary['bootstrap_probability_positive'])}",
        "- Holdout coverage/proof pass rate: "
        f"{_format_number(summary['holdout_candidate_coverage_rate'])} / "
        f"{_format_number(summary['holdout_proof_pass_rate'])}",
        "- Holdout mean/worst score: "
        f"{_format_number(summary['holdout_mean_score'])} / "
        f"{_format_number(summary['holdout_worst_score'])}",
        f"- Candidate selection rate: {_format_number(summary['selection_candidate_rate'])}",
        "- Candidate conditional overfit rate: "
        f"{_format_number(summary['selection_candidate_overfit_rate'])}",
        "- Candidate conditional OOS positive rate: "
        f"{_format_number(summary['selection_candidate_oos_positive_rate'])}",
        f"- Next gate: `{summary['next_gate']}`",
        "- Authorizes submission: `false`",
        "",
        "## Stages",
        "",
    ]
    for row in stages.itertuples(index=False):
        lines.append(
            f"- `{row.stage}`: {'passed' if bool(row.status) else 'blocked'} ({row.detail})"
        )
    if not action_queue.empty:
        lines.extend(["", "## Blocking Actions", ""])
        for row in action_queue.itertuples(index=False):
            lines.append(f"- `{row.component}`: {row.recommendation}")
    lines.extend(
        [
            "",
            "A ready result permits broker-neutral order staging for paper or shadow "
            "review only. It never authorizes broker submission.",
        ]
    )
    return "\n".join(lines) + "\n"


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"


def _canonical_path(value: str | Path) -> str:
    return str(Path(value).resolve()).casefold()


def _int(value: Any) -> int:
    number = _float(value)
    return int(number) if np.isfinite(number) else 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _format_number(value: Any) -> str:
    number = _float(value)
    return "n/a" if not np.isfinite(number) else f"{number:.4f}"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


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
