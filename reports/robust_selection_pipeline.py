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
from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.promotion import (
    SCORE_METRIC_COLUMNS,
    PromotionReport,
    PromotionThresholds,
    write_promotion_report,
)
from reports.research_family_registration import (
    load_research_family_registration,
)
from reports.research_family_launch import (
    load_research_family_launch_attempt_ledger,
    load_research_family_launch_contract,
    load_research_family_launch_execution_receipt,
)
from reports.robust_selection_semantics import (
    build_robust_selection_semantics,
    semantic_digest,
)
from reports.sweep_provenance import build_sweep_provenance
from reports.sweeps import SweepComparison, write_sweep_comparison
from reports.walkforward_split_audit import (
    RUN_TYPE as WALKFORWARD_SPLIT_AUDIT_RUN_TYPE,
)


RUN_TYPE = "robust_selection_pipeline"
READY_NEXT_GATE = "stage-orders"
STAGE_NEXT_GATES = {
    "research_launch_execution_receipt": "run-research-family-study",
    "research_launch_contract": "plan-research-family-launches",
    "research_registration": "register-research-family",
    "walkforward_split_audit": "audit-walkforward-splits",
    "sweep_provenance": "pipeline-robust-selection",
    "selection": "compare-sweeps",
    "backtest_overfit": "audit-backtest-overfit",
    "backtest_significance": "audit-backtest-significance",
    "backtest_holdout": "audit-backtest-holdout",
    "promotion": "promote-scenario",
}

WALKFORWARD_SPLIT_AUDIT_ARTIFACTS = (
    "walkforward_split_assignments.csv",
    "walkforward_split_folds.csv",
    "walkforward_split_checks.csv",
    "walkforward_split_summary.csv",
    "walkforward_split_action_queue.csv",
    "walkforward_split_config.json",
    "walkforward_split_runbook.md",
)

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
    research_launch_execution_receipt: pd.DataFrame
    research_launch_contract: pd.DataFrame
    research_registration: pd.DataFrame
    walkforward_split_audit: pd.DataFrame
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
    walkforward_split_audit_path: str | Path | None = None,
    require_walkforward_split_audit: bool = False,
    research_launch_matrix_path: str | Path | None = None,
    research_launch_contract_id: str | None = None,
    require_research_launch_contract: bool = False,
    research_launch_execution_receipt_path: str | Path | None = None,
    require_research_launch_execution_receipt: bool = False,
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
    walkforward_split_audit = _walkforward_split_audit_binding(
        walkforward_split_audit_path,
        require_audit=require_walkforward_split_audit,
    )
    walkforward_split_audit_path_out = (
        out / "robust_selection_pipeline_walkforward_split_audit.csv"
    )
    walkforward_split_audit.to_csv(
        walkforward_split_audit_path_out,
        index=False,
    )
    walkforward_split_audit_row = walkforward_split_audit.iloc[0]
    walkforward_split_audit_passed = bool(
        walkforward_split_audit["passed"].map(_to_bool).all()
    )
    runtime_semantics = build_robust_selection_semantics(
        sweep_paths=paths,
        labels=labels,
        group_cols=resolved_group_cols,
        strategy=strategy,
        market=market,
        selection={
            "min_pass_rate": selection_min_pass_rate,
            "min_sweeps": resolved_selection_min_sweeps,
            "min_median_net_pnl": selection_min_median_net_pnl,
            "max_worst_drawdown": selection_max_worst_drawdown,
        },
        overfit_config=asdict(overfit_config),
        overfit_thresholds=asdict(overfit_thresholds),
        significance_config=asdict(significance_config),
        significance_thresholds=asdict(significance_thresholds),
        holdout_sweeps=holdout_sweeps,
        holdout_config=asdict(holdout_config),
        holdout_thresholds=asdict(holdout_thresholds),
        promotion_thresholds=asdict(promotion_thresholds),
        walkforward_split_audit={
            "path": str(walkforward_split_audit_row.get("audit_path", "")),
            "required": bool(require_walkforward_split_audit),
            "manifest_sha256": str(
                walkforward_split_audit_row.get("manifest_sha256", "")
            ),
        },
    )
    runtime_semantic_digest = semantic_digest(runtime_semantics)
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
    research_launch_contract = _research_launch_contract_binding(
        research_launch_matrix_path,
        research_launch_contract_id=research_launch_contract_id,
        require_contract=require_research_launch_contract,
        output_dir=out,
        sweep_paths=paths,
        labels=labels,
        group_cols=resolved_group_cols,
        strategy=strategy,
        market=market,
        holdout_sweeps=holdout_sweeps,
        research_registration=research_registration.iloc[0],
        registered_study_label=registered_study_label,
    )
    research_launch_contract_path_out = (
        out / "robust_selection_pipeline_research_launch_contract.csv"
    )
    research_launch_contract.to_csv(
        research_launch_contract_path_out,
        index=False,
    )
    research_launch_contract_passed = bool(
        not research_launch_contract.empty
        and research_launch_contract["passed"].map(_to_bool).all()
    )
    research_launch_execution_receipt = _research_launch_execution_receipt_binding(
        research_launch_execution_receipt_path,
        require_receipt=require_research_launch_execution_receipt,
        research_launch_contract=research_launch_contract.iloc[0],
        runtime_semantics=runtime_semantics,
        runtime_semantic_digest=runtime_semantic_digest,
    )
    research_launch_execution_receipt_path_out = (
        out / "robust_selection_pipeline_research_launch_execution_receipt.csv"
    )
    research_launch_execution_receipt.to_csv(
        research_launch_execution_receipt_path_out,
        index=False,
    )
    research_launch_execution_receipt_passed = bool(
        not research_launch_execution_receipt.empty
        and research_launch_execution_receipt["passed"].map(_to_bool).all()
    )
    preflight = pd.DataFrame(
        [
            {
                "component": "research_launch_execution_receipt",
                "passed": research_launch_execution_receipt_passed,
                "evidence_path": str(
                    research_launch_execution_receipt_path_out
                ),
                "detail": str(
                    research_launch_execution_receipt.iloc[0].get("detail", "")
                ),
            },
            {
                "component": "research_launch_contract",
                "passed": research_launch_contract_passed,
                "evidence_path": str(research_launch_contract_path_out),
                "detail": str(
                    research_launch_contract.iloc[0].get("detail", "")
                ),
            },
            {
                "component": "research_registration",
                "passed": research_registration_passed,
                "evidence_path": str(research_registration_path_out),
                "detail": str(research_registration.iloc[0].get("detail", "")),
            },
            {
                "component": "walkforward_split_audit",
                "passed": walkforward_split_audit_passed,
                "evidence_path": str(walkforward_split_audit_path_out),
                "detail": str(
                    walkforward_split_audit.iloc[0].get("detail", "")
                ),
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
        research_launch_execution_receipt,
        research_launch_contract,
        research_registration,
        walkforward_split_audit,
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
        research_launch_execution_receipt=research_launch_execution_receipt,
        research_launch_contract=research_launch_contract,
        research_registration=research_registration,
        walkforward_split_audit=walkforward_split_audit,
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
        "walkforward_split_audit_path": (
            str(Path(walkforward_split_audit_path).resolve())
            if walkforward_split_audit_path is not None
            else ""
        ),
        "require_walkforward_split_audit": bool(
            require_walkforward_split_audit
        ),
        "research_launch_matrix_path": (
            str(Path(research_launch_matrix_path).resolve())
            if research_launch_matrix_path is not None
            else ""
        ),
        "research_launch_contract_id": str(research_launch_contract_id or ""),
        "require_research_launch_contract": bool(
            require_research_launch_contract
        ),
        "research_launch_execution_receipt_path": (
            str(Path(research_launch_execution_receipt_path).resolve())
            if research_launch_execution_receipt_path is not None
            else ""
        ),
        "require_research_launch_execution_receipt": bool(
            require_research_launch_execution_receipt
        ),
        "runtime_semantic_digest": runtime_semantic_digest,
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
    split_audit_row = walkforward_split_audit.iloc[0]
    if _to_bool(split_audit_row.get("provided", False)):
        split_audit_root = Path(str(split_audit_row.get("audit_path", "")))
        split_audit_manifest = Path(
            str(split_audit_row.get("manifest_path", ""))
        )
        if split_audit_root.is_dir():
            inputs["walkforward_split_audit"] = split_audit_root
        if split_audit_manifest.is_file():
            inputs["walkforward_split_audit_manifest"] = split_audit_manifest
            split_audit_dependencies = manifest_dependency_paths(
                split_audit_manifest
            )
            if split_audit_dependencies:
                inputs["walkforward_split_audit_dependencies"] = (
                    split_audit_dependencies
                )
    launch_contract_row = research_launch_contract.iloc[0]
    launch_contract_path = Path(
        str(launch_contract_row.get("contract_path", ""))
    )
    if launch_contract_path.is_file():
        inputs["research_family_launch_contract"] = launch_contract_path
    receipt_row = research_launch_execution_receipt.iloc[0]
    receipt_path = Path(str(receipt_row.get("receipt_path", "")))
    if receipt_path.is_file():
        inputs["research_family_launch_execution_receipt"] = receipt_path
    attempt_record_path = Path(
        str(receipt_row.get("attempt_record_path", ""))
    )
    if attempt_record_path.is_file():
        inputs["research_family_launch_attempt_record"] = attempt_record_path
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
            "walkforward_split_audit_provided": bool(
                summary.iloc[0]["walkforward_split_audit_provided"]
            ),
            "walkforward_split_audit_passed": bool(
                summary.iloc[0]["walkforward_split_audit_passed"]
            ),
            "walkforward_split_audit_manifest_sha256": str(
                summary.iloc[0]["walkforward_split_audit_manifest_sha256"]
            ),
            "walkforward_split_future_training_rows": int(
                summary.iloc[0]["walkforward_split_future_training_rows"]
            ),
            "walkforward_split_overlapping_training_labels": int(
                summary.iloc[0][
                    "walkforward_split_overlapping_training_labels"
                ]
            ),
            "walkforward_split_embargo_breach_rows": int(
                summary.iloc[0]["walkforward_split_embargo_breach_rows"]
            ),
            "research_launch_contract_provided": bool(
                summary.iloc[0]["research_launch_contract_provided"]
            ),
            "research_launch_contract_passed": bool(
                summary.iloc[0]["research_launch_contract_passed"]
            ),
            "research_launch_contract_id": str(
                summary.iloc[0]["research_launch_contract_id"]
            ),
            "research_launch_contract_sha256": str(
                summary.iloc[0]["research_launch_contract_sha256"]
            ),
            "research_launch_matrix_manifest_sha256": str(
                summary.iloc[0]["research_launch_matrix_manifest_sha256"]
            ),
            "research_launch_execution_receipt_provided": bool(
                summary.iloc[0]["research_launch_execution_receipt_provided"]
            ),
            "research_launch_execution_receipt_passed": bool(
                summary.iloc[0]["research_launch_execution_receipt_passed"]
            ),
            "research_launch_execution_receipt_id": str(
                summary.iloc[0]["research_launch_execution_receipt_id"]
            ),
            "research_launch_dispatch_id": str(
                summary.iloc[0]["research_launch_dispatch_id"]
            ),
            "research_launch_attempt_id": str(
                summary.iloc[0]["research_launch_attempt_id"]
            ),
            "research_launch_attempt_number": int(
                summary.iloc[0]["research_launch_attempt_number"]
            ),
            "research_launch_attempt_record_sha256": str(
                summary.iloc[0]["research_launch_attempt_record_sha256"]
            ),
            "research_launch_argv_sha256": str(
                summary.iloc[0]["research_launch_argv_sha256"]
            ),
            "research_launch_semantic_sha256": str(
                summary.iloc[0]["research_launch_semantic_sha256"]
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
        research_launch_execution_receipt=research_launch_execution_receipt,
        research_launch_contract=research_launch_contract,
        research_registration=research_registration,
        walkforward_split_audit=walkforward_split_audit,
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


def _research_launch_execution_receipt_binding(
    raw_receipt_path: str | Path | None,
    *,
    require_receipt: bool,
    research_launch_contract: pd.Series,
    runtime_semantics: dict[str, Any],
    runtime_semantic_digest: str,
) -> pd.DataFrame:
    provided = raw_receipt_path is not None
    requested = bool(provided or require_receipt)
    base: dict[str, Any] = {
        "provided": provided,
        "required": bool(require_receipt),
        "skipped": False,
        "passed": False,
        "receipt_path": "",
        "receipt_sha256": "",
        "receipt_id": "",
        "dispatch_id": "",
        "attempt_id": "",
        "attempt_number": 0,
        "attempt_ledger_path": "",
        "attempt_record_path": "",
        "attempt_record_sha256": "",
        "attempt_ledger_matches": False,
        "retry_of_attempt_id": "",
        "retry_attested": False,
        "contract_id": "",
        "contract_id_matches": False,
        "contract_sha256_matches": False,
        "contract_path_matches": False,
        "launch_matrix_manifest_matches": False,
        "argv_matches": False,
        "argv_sha256": "",
        "semantic_matches": False,
        "semantic_sha256": runtime_semantic_digest,
        "non_authorizing": False,
        "failed_checks": 0,
        "failed_check_names": "",
        "detail": "",
        "recommendation": "run_the_study_through_the_contract_executor",
    }
    if not provided:
        passed = not requested
        base.update(
            {
                "skipped": passed,
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "failed_check_names": "" if passed else "execution_receipt_provided",
                "detail": (
                    "optional_execution_receipt_not_provided"
                    if passed
                    else "launch_execution_receipt_is_required"
                ),
                "recommendation": (
                    "continue_without_execution_receipt"
                    if passed
                    else "run_the_study_through_the_contract_executor"
                ),
            }
        )
        return pd.DataFrame([base])
    receipt_path = Path(raw_receipt_path).resolve()
    base["receipt_path"] = str(receipt_path)
    try:
        receipt = load_research_family_launch_execution_receipt(receipt_path)
        contract = load_research_family_launch_contract(
            str(research_launch_contract.get("launch_matrix_path", "")),
            str(research_launch_contract.get("contract_id", "")),
        )
        attempt_ledger = load_research_family_launch_attempt_ledger(
            contract.matrix.root
        )
    except (OSError, ValueError, KeyError) as exc:
        base.update(
            {
                "failed_checks": 1,
                "failed_check_names": "execution_receipt_loadable",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
        return pd.DataFrame([base])
    payload = receipt.payload
    matching_attempts = [
        record
        for record in attempt_ledger.records
        if str(record.get("attempt_id", "")) == receipt.attempt_id
    ]
    attempt_record = matching_attempts[0] if len(matching_attempts) == 1 else {}
    attempt_ledger_matches = bool(
        len(matching_attempts) == 1
        and _canonical_path(attempt_ledger.path)
        == _canonical_path(receipt.attempt_ledger_path)
        and _canonical_path(attempt_record.get("attempt_record_path", ""))
        == _canonical_path(receipt.attempt_record_path)
        and str(attempt_record.get("record_sha256", ""))
        == receipt.attempt_record_sha256
        and str(attempt_record.get("receipt_sha256", ""))
        == file_sha256(receipt.path)
    )
    contract_id_matches = bool(
        _to_bool(research_launch_contract.get("passed", False))
        and receipt.contract_id == str(research_launch_contract.get("contract_id", ""))
    )
    expected_contract_sha = str(research_launch_contract.get("contract_sha256", ""))
    contract_sha_matches = bool(
        str(payload.get("contract_sha256", "")) == expected_contract_sha
        and file_sha256(contract.contract_path) == expected_contract_sha
    )
    contract_path_matches = bool(
        _canonical_path(payload.get("contract_path", ""))
        == _canonical_path(contract.contract_path)
    )
    matrix_manifest_matches = bool(
        str(payload.get("launch_matrix_manifest_sha256", ""))
        == str(
            research_launch_contract.get(
                "launch_matrix_manifest_sha256",
                "",
            )
        )
    )
    argv_matches = receipt.argv == contract.argv
    semantic_matches = bool(
        receipt.semantic_sha256 == runtime_semantic_digest
        and payload.get("semantic_parameters", {}) == runtime_semantics
    )
    non_authorizing = not _to_bool(payload.get("authorizes_submission", False))
    checks = {
        "attempt_ledger_matches": attempt_ledger_matches,
        "contract_id_matches": contract_id_matches,
        "contract_sha256_matches": contract_sha_matches,
        "contract_path_matches": contract_path_matches,
        "launch_matrix_manifest_matches": matrix_manifest_matches,
        "argv_matches": argv_matches,
        "semantic_matches": semantic_matches,
        "non_authorizing": non_authorizing,
    }
    failed = [name for name, value in checks.items() if not value]
    passed = not failed
    base.update(
        {
            "passed": passed,
            "receipt_path": str(receipt.path),
            "receipt_sha256": file_sha256(receipt.path),
            "receipt_id": receipt.receipt_id,
            "dispatch_id": receipt.dispatch_id,
            "attempt_id": receipt.attempt_id,
            "attempt_number": receipt.attempt_number,
            "attempt_ledger_path": str(receipt.attempt_ledger_path),
            "attempt_record_path": str(receipt.attempt_record_path),
            "attempt_record_sha256": receipt.attempt_record_sha256,
            "attempt_ledger_matches": attempt_ledger_matches,
            "retry_of_attempt_id": receipt.retry_of_attempt_id,
            "retry_attested": _to_bool(
                receipt.payload.get("retry_attested", False)
            ),
            "contract_id": receipt.contract_id,
            "contract_id_matches": contract_id_matches,
            "contract_sha256_matches": contract_sha_matches,
            "contract_path_matches": contract_path_matches,
            "launch_matrix_manifest_matches": matrix_manifest_matches,
            "argv_matches": argv_matches,
            "argv_sha256": receipt.argv_sha256,
            "semantic_matches": semantic_matches,
            "semantic_sha256": receipt.semantic_sha256,
            "non_authorizing": non_authorizing,
            "failed_checks": len(failed),
            "failed_check_names": ",".join(failed),
            "detail": (
                f"receipt_id={receipt.receipt_id};dispatch_id={receipt.dispatch_id}"
                if passed
                else f"failed_checks={','.join(failed)}"
            ),
            "recommendation": (
                "continue_to_contract_registration_and_sweep_validation"
                if passed
                else "run_the_study_through_the_contract_executor"
            ),
        }
    )
    return pd.DataFrame([base])


def _research_launch_contract_binding(
    raw_matrix_path: str | Path | None,
    *,
    research_launch_contract_id: str | None,
    require_contract: bool,
    output_dir: Path,
    sweep_paths: list[Path],
    labels: list[str] | None,
    group_cols: list[str],
    strategy: str,
    market: str,
    holdout_sweeps: int,
    research_registration: pd.Series,
    registered_study_label: str | None,
) -> pd.DataFrame:
    provided = raw_matrix_path is not None
    contract_id = str(research_launch_contract_id or "").strip()
    requested = bool(provided or contract_id or require_contract)
    base: dict[str, Any] = {
        "provided": provided,
        "required": bool(require_contract),
        "skipped": False,
        "passed": False,
        "launch_matrix_path": "",
        "launch_matrix_manifest_path": "",
        "launch_matrix_manifest_sha256": "",
        "launch_matrix_manifest_current": False,
        "launch_matrix_manifest_error": "",
        "contract_id": contract_id,
        "contract_path": "",
        "contract_sha256": "",
        "contract_valid": False,
        "contract_ready": False,
        "study_label_matches": False,
        "study_path_matches": False,
        "strategy_matches": False,
        "market_matches": False,
        "sweep_paths_match": False,
        "sweep_labels_match": False,
        "group_columns_match": False,
        "holdout_sweeps_match": False,
        "registration_id_matches": False,
        "registration_manifest_matches": False,
        "failed_checks": 0,
        "failed_check_names": "",
        "detail": "",
        "recommendation": "plan_or_repair_the_registered_launch_contract",
    }
    if not provided:
        passed = not requested
        base.update(
            {
                "skipped": passed,
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "failed_check_names": "" if passed else "launch_matrix_provided",
                "detail": (
                    "optional_launch_contract_not_provided"
                    if passed
                    else "launch_matrix_and_contract_id_are_required"
                ),
                "recommendation": (
                    "continue_without_launch_contract"
                    if passed
                    else "plan_the_registered_research_family_launches"
                ),
            }
        )
        return pd.DataFrame([base])
    matrix_path = Path(raw_matrix_path).resolve()
    base["launch_matrix_path"] = str(matrix_path)
    if not contract_id:
        base.update(
            {
                "failed_checks": 1,
                "failed_check_names": "contract_id_provided",
                "detail": "research_launch_contract_id_is_required",
            }
        )
        return pd.DataFrame([base])
    try:
        contract = load_research_family_launch_contract(matrix_path, contract_id)
    except (OSError, ValueError, KeyError) as exc:
        base.update(
            {
                "launch_matrix_manifest_error": f"{type(exc).__name__}: {exc}",
                "failed_checks": 1,
                "failed_check_names": "launch_contract_loadable",
                "detail": "launch_contract_artifacts_could_not_be_loaded",
            }
        )
        return pd.DataFrame([base])
    matrix = contract.matrix
    row = contract.row
    core = contract.payload.get("contract_core", {})
    study = core.get("study", {}) if isinstance(core, dict) else {}
    planned_sweeps = core.get("sweep_paths", []) if isinstance(core, dict) else []
    planned_labels = core.get("sweep_labels", []) if isinstance(core, dict) else []
    planned_groups = core.get("group_cols", []) if isinstance(core, dict) else []
    actual_label = str(registered_study_label or "").strip()
    study_label_matches = bool(
        actual_label
        and str(row.get("study_label", "")) == actual_label
        and str(study.get("study_label", "")) == actual_label
    )
    study_path_matches = bool(
        _canonical_path(study.get("planned_study_path", ""))
        == _canonical_path(output_dir)
    )
    strategy_matches = str(study.get("strategy", "")) == strategy
    market_matches = str(study.get("market", "")) == market
    sweep_paths_match = bool(
        isinstance(planned_sweeps, list)
        and [_canonical_path(value) for value in planned_sweeps]
        == [_canonical_path(value) for value in sweep_paths]
    )
    actual_labels = [str(value) for value in (labels or [])]
    sweep_labels_match = bool(
        isinstance(planned_labels, list)
        and [str(value) for value in planned_labels] == actual_labels
    )
    group_columns_match = bool(
        isinstance(planned_groups, list)
        and [str(value) for value in planned_groups]
        == [str(value) for value in group_cols]
    )
    holdout_matches = bool(
        _int(study.get("holdout_sweeps")) == holdout_sweeps
    )
    registration_id_matches = bool(
        _to_bool(research_registration.get("passed", False))
        and str(core.get("registration_id", ""))
        == str(research_registration.get("registration_id", ""))
    )
    registration_manifest_matches = bool(
        str(core.get("registration_manifest_sha256", ""))
        == str(research_registration.get("registration_manifest_sha256", ""))
    )
    checks = {
        "launch_matrix_manifest_current": matrix.manifest_current,
        "contract_valid": _to_bool(row.get("contract_valid", False)),
        "contract_ready": _to_bool(row.get("contract_ready", False)),
        "study_label_matches": study_label_matches,
        "study_path_matches": study_path_matches,
        "strategy_matches": strategy_matches,
        "market_matches": market_matches,
        "sweep_paths_match": sweep_paths_match,
        "sweep_labels_match": sweep_labels_match,
        "group_columns_match": group_columns_match,
        "holdout_sweeps_match": holdout_matches,
        "registration_id_matches": registration_id_matches,
        "registration_manifest_matches": registration_manifest_matches,
    }
    failed = [name for name, value in checks.items() if not value]
    contract_sha256 = file_sha256(contract.contract_path)
    passed = not failed
    base.update(
        {
            "passed": passed,
            "launch_matrix_path": str(matrix.root),
            "launch_matrix_manifest_path": str(matrix.root / "manifest.json"),
            "launch_matrix_manifest_sha256": matrix.manifest_sha256,
            "launch_matrix_manifest_current": matrix.manifest_current,
            "launch_matrix_manifest_error": matrix.manifest_error,
            "contract_id": contract.contract_id,
            "contract_path": str(contract.contract_path),
            "contract_sha256": contract_sha256,
            "contract_valid": _to_bool(row.get("contract_valid", False)),
            "contract_ready": _to_bool(row.get("contract_ready", False)),
            "study_label_matches": study_label_matches,
            "study_path_matches": study_path_matches,
            "strategy_matches": strategy_matches,
            "market_matches": market_matches,
            "sweep_paths_match": sweep_paths_match,
            "sweep_labels_match": sweep_labels_match,
            "group_columns_match": group_columns_match,
            "holdout_sweeps_match": holdout_matches,
            "registration_id_matches": registration_id_matches,
            "registration_manifest_matches": registration_manifest_matches,
            "failed_checks": len(failed),
            "failed_check_names": ",".join(failed),
            "detail": (
                f"contract_id={contract.contract_id};study={actual_label}"
                if passed
                else f"failed_checks={','.join(failed)}"
            ),
            "recommendation": (
                "continue_to_registration_and_sweep_validation"
                if passed
                else "plan_or_repair_the_registered_launch_contract"
            ),
        }
    )
    return pd.DataFrame([base])


def _walkforward_split_audit_binding(
    raw_path: str | Path | None,
    *,
    require_audit: bool,
) -> pd.DataFrame:
    provided = raw_path is not None
    base: dict[str, Any] = {
        "provided": provided,
        "required": bool(require_audit),
        "skipped": False,
        "passed": False,
        "audit_path": "",
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_current": False,
        "manifest_error": "",
        "manifest_artifact_count": 0,
        "manifest_artifact_match_count": 0,
        "manifest_input_count": 0,
        "manifest_input_match_count": 0,
        "summary_passed": False,
        "summary_ready": False,
        "config_passed": False,
        "config_ready": False,
        "checks_passed": False,
        "folds_passed": False,
        "non_authorizing": False,
        "source_rows": 0,
        "fold_count": 0,
        "future_training_rows": 0,
        "overlapping_training_labels": 0,
        "embargo_breach_rows": 0,
        "blocked_action_count": 0,
        "failed_checks": 0,
        "failed_check_names": "",
        "detail": "",
        "recommendation": "supply_or_repair_walkforward_split_audit",
    }
    if not provided:
        passed = not require_audit
        base.update(
            {
                "skipped": passed,
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "failed_check_names": "" if passed else "audit_provided",
                "detail": (
                    "optional_walkforward_split_audit_not_provided"
                    if passed
                    else "walkforward_split_audit_is_required"
                ),
                "recommendation": (
                    "continue_without_model_split_evidence"
                    if passed
                    else "run_audit_walkforward_splits_before_robust_selection"
                ),
            }
        )
        return pd.DataFrame([base])

    raw = Path(raw_path).resolve()
    if raw.name == "manifest.json":
        root = raw.parent
        manifest_path = raw
    else:
        root = raw
        manifest_path = root / "manifest.json"
    base.update(
        {
            "audit_path": str(root),
            "manifest_path": str(manifest_path),
        }
    )
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=WALKFORWARD_SPLIT_AUDIT_RUN_TYPE,
        required_artifacts=WALKFORWARD_SPLIT_AUDIT_ARTIFACTS,
        require_input_fingerprints=True,
    )
    manifest_sha256 = ""
    if manifest_path.is_file():
        try:
            manifest_sha256 = file_sha256(manifest_path)
        except OSError:
            manifest_sha256 = ""
    base.update(
        {
            "manifest_sha256": manifest_sha256,
            "manifest_current": bool(integrity.passed),
            "manifest_error": str(integrity.error),
            "manifest_artifact_count": int(integrity.artifact_count),
            "manifest_artifact_match_count": int(
                integrity.artifact_match_count
            ),
            "manifest_input_count": int(integrity.input_fingerprint_count),
            "manifest_input_match_count": int(
                integrity.input_fingerprint_match_count
            ),
        }
    )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        config = json.loads(
            (root / "walkforward_split_config.json").read_text(
                encoding="utf-8"
            )
        )
        summary = pd.read_csv(root / "walkforward_split_summary.csv")
        checks = pd.read_csv(root / "walkforward_split_checks.csv")
        folds = pd.read_csv(root / "walkforward_split_folds.csv")
        action_queue = pd.read_csv(
            root / "walkforward_split_action_queue.csv"
        )
        if not isinstance(manifest, dict) or not isinstance(config, dict):
            raise ValueError("audit JSON artifacts must be objects")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        base.update(
            {
                "failed_checks": 1,
                "failed_check_names": "audit_loadable",
                "detail": f"audit_artifacts_unreadable:{type(exc).__name__}",
            }
        )
        return pd.DataFrame([base])

    summary_row = (
        summary.iloc[0] if len(summary) == 1 else pd.Series(dtype=object)
    )
    manifest_extra = (
        manifest.get("extra", {}) if isinstance(manifest, dict) else {}
    )
    manifest_extra = manifest_extra if isinstance(manifest_extra, dict) else {}
    summary_passed = _to_bool(summary_row.get("passed", False))
    summary_ready = _to_bool(summary_row.get("ready", False))
    config_passed = _to_bool(config.get("passed", False))
    config_ready = _to_bool(config.get("ready", False))
    checks_passed = bool(
        not checks.empty
        and "passed" in checks.columns
        and checks["passed"].map(_to_bool).all()
    )
    folds_passed = bool(
        not folds.empty
        and "passed" in folds.columns
        and folds["passed"].map(_to_bool).all()
    )
    future_training_rows = _int(summary_row.get("future_training_rows"))
    overlapping_training_labels = _int(
        summary_row.get("overlapping_training_labels")
    )
    embargo_breach_rows = _int(summary_row.get("embargo_breach_rows"))
    blocked_action_count = _int(summary_row.get("blocked_action_count"))
    metrics_zero = bool(
        future_training_rows == 0
        and overlapping_training_labels == 0
        and embargo_breach_rows == 0
    )
    non_authorizing = bool(
        "authorizes_submission" in summary_row.index
        and not _to_bool(summary_row.get("authorizes_submission", True))
        and "authorizes_submission" in config
        and not _to_bool(config.get("authorizes_submission", True))
        and "authorizes_submission" in manifest_extra
        and not _to_bool(manifest_extra.get("authorizes_submission", True))
    )
    manifest_declares_pass = bool(
        _to_bool(manifest_extra.get("passed", False))
    )
    no_blocked_actions = bool(
        action_queue.empty and blocked_action_count == 0
    )
    validations = {
        "manifest_current": bool(integrity.passed),
        "summary_passed": summary_passed,
        "summary_ready": summary_ready,
        "config_passed": config_passed,
        "config_ready": config_ready,
        "manifest_declares_pass": manifest_declares_pass,
        "checks_passed": checks_passed,
        "folds_passed": folds_passed,
        "leakage_metrics_zero": metrics_zero,
        "no_blocked_actions": no_blocked_actions,
        "non_authorizing": non_authorizing,
    }
    failed = [name for name, value in validations.items() if not value]
    passed = not failed
    base.update(
        {
            "passed": passed,
            "summary_passed": summary_passed,
            "summary_ready": summary_ready,
            "config_passed": config_passed,
            "config_ready": config_ready,
            "checks_passed": checks_passed,
            "folds_passed": folds_passed,
            "non_authorizing": non_authorizing,
            "source_rows": _int(summary_row.get("source_rows")),
            "fold_count": _int(summary_row.get("fold_count")),
            "future_training_rows": future_training_rows,
            "overlapping_training_labels": overlapping_training_labels,
            "embargo_breach_rows": embargo_breach_rows,
            "blocked_action_count": blocked_action_count,
            "failed_checks": len(failed),
            "failed_check_names": ",".join(failed),
            "detail": (
                f"folds={_int(summary_row.get('fold_count'))};"
                f"source_rows={_int(summary_row.get('source_rows'))};"
                f"manifest_sha256={manifest_sha256}"
                if passed
                else f"failed_checks={','.join(failed)}"
            ),
            "recommendation": (
                "continue_to_manifest_bound_sweep_validation"
                if passed
                else "rerun_or_repair_the_walkforward_split_audit"
            ),
        }
    )
    return pd.DataFrame([base])


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
    research_launch_execution_receipt: pd.DataFrame,
    research_launch_contract: pd.DataFrame,
    research_registration: pd.DataFrame,
    walkforward_split_audit: pd.DataFrame,
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
    split_audit_row = (
        walkforward_split_audit.iloc[0]
        if not walkforward_split_audit.empty
        else pd.Series(dtype=object)
    )
    split_audit_passed = _to_bool(split_audit_row.get("passed", False))
    split_audit_skipped = _to_bool(split_audit_row.get("skipped", False))
    launch_contract_row = (
        research_launch_contract.iloc[0]
        if not research_launch_contract.empty
        else pd.Series(dtype=object)
    )
    launch_contract_passed = _to_bool(launch_contract_row.get("passed", False))
    launch_contract_skipped = _to_bool(launch_contract_row.get("skipped", False))
    receipt_row = (
        research_launch_execution_receipt.iloc[0]
        if not research_launch_execution_receipt.empty
        else pd.Series(dtype=object)
    )
    receipt_passed = _to_bool(receipt_row.get("passed", False))
    receipt_skipped = _to_bool(receipt_row.get("skipped", False))
    return pd.DataFrame(
        [
            {
                "stage": "research_launch_execution_receipt",
                "status": receipt_passed,
                "status_column": "passed",
                "skipped": receipt_skipped,
                "output_dir": str(receipt_row.get("receipt_path", "")),
                "failed_checks": 0 if receipt_passed else 1,
                "recommendation": str(
                    receipt_row.get(
                        "recommendation",
                        "run_the_study_through_the_contract_executor",
                    )
                ),
                "detail": str(receipt_row.get("detail", "")),
            },
            {
                "stage": "research_launch_contract",
                "status": launch_contract_passed,
                "status_column": "passed",
                "skipped": launch_contract_skipped,
                "output_dir": str(
                    launch_contract_row.get("launch_matrix_path", "")
                ),
                "failed_checks": 0 if launch_contract_passed else 1,
                "recommendation": str(
                    launch_contract_row.get(
                        "recommendation",
                        "plan_or_repair_the_registered_launch_contract",
                    )
                ),
                "detail": str(launch_contract_row.get("detail", "")),
            },
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
                "stage": "walkforward_split_audit",
                "status": split_audit_passed,
                "status_column": "passed",
                "skipped": split_audit_skipped,
                "output_dir": str(split_audit_row.get("audit_path", "")),
                "failed_checks": _int(
                    split_audit_row.get("failed_checks")
                ),
                "recommendation": str(
                    split_audit_row.get(
                        "recommendation",
                        "supply_or_repair_walkforward_split_audit",
                    )
                ),
                "detail": str(split_audit_row.get("detail", "")),
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
    research_launch_execution_receipt: pd.DataFrame,
    research_launch_contract: pd.DataFrame,
    research_registration: pd.DataFrame,
    walkforward_split_audit: pd.DataFrame,
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
    split_audit_row = (
        walkforward_split_audit.iloc[0]
        if not walkforward_split_audit.empty
        else pd.Series(dtype=object)
    )
    launch_contract_row = (
        research_launch_contract.iloc[0]
        if not research_launch_contract.empty
        else pd.Series(dtype=object)
    )
    receipt_row = (
        research_launch_execution_receipt.iloc[0]
        if not research_launch_execution_receipt.empty
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
                "research_launch_execution_receipt_provided": _to_bool(
                    receipt_row.get("provided", False)
                ),
                "research_launch_execution_receipt_required": _to_bool(
                    receipt_row.get("required", False)
                ),
                "research_launch_execution_receipt_passed": _to_bool(
                    receipt_row.get("passed", False)
                ),
                "research_launch_execution_receipt_id": str(
                    receipt_row.get("receipt_id", "")
                ),
                "research_launch_dispatch_id": str(
                    receipt_row.get("dispatch_id", "")
                ),
                "research_launch_attempt_id": str(
                    receipt_row.get("attempt_id", "")
                ),
                "research_launch_attempt_number": _int(
                    receipt_row.get("attempt_number")
                ),
                "research_launch_attempt_record_sha256": str(
                    receipt_row.get("attempt_record_sha256", "")
                ),
                "research_launch_retry_of_attempt_id": str(
                    receipt_row.get("retry_of_attempt_id", "")
                ),
                "research_launch_retry_attested": _to_bool(
                    receipt_row.get("retry_attested", False)
                ),
                "research_launch_execution_receipt_sha256": str(
                    receipt_row.get("receipt_sha256", "")
                ),
                "research_launch_argv_sha256": str(
                    receipt_row.get("argv_sha256", "")
                ),
                "research_launch_semantic_sha256": str(
                    receipt_row.get("semantic_sha256", "")
                ),
                "research_launch_contract_provided": _to_bool(
                    launch_contract_row.get("provided", False)
                ),
                "research_launch_contract_required": _to_bool(
                    launch_contract_row.get("required", False)
                ),
                "research_launch_contract_passed": _to_bool(
                    launch_contract_row.get("passed", False)
                ),
                "research_launch_contract_id": str(
                    launch_contract_row.get("contract_id", "")
                ),
                "research_launch_contract_sha256": str(
                    launch_contract_row.get("contract_sha256", "")
                ),
                "research_launch_matrix_manifest_sha256": str(
                    launch_contract_row.get("launch_matrix_manifest_sha256", "")
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
                "walkforward_split_audit_provided": _to_bool(
                    split_audit_row.get("provided", False)
                ),
                "walkforward_split_audit_required": _to_bool(
                    split_audit_row.get("required", False)
                ),
                "walkforward_split_audit_passed": _to_bool(
                    split_audit_row.get("passed", False)
                ),
                "walkforward_split_audit_manifest_sha256": str(
                    split_audit_row.get("manifest_sha256", "")
                ),
                "walkforward_split_source_rows": _int(
                    split_audit_row.get("source_rows")
                ),
                "walkforward_split_fold_count": _int(
                    split_audit_row.get("fold_count")
                ),
                "walkforward_split_future_training_rows": _int(
                    split_audit_row.get("future_training_rows")
                ),
                "walkforward_split_overlapping_training_labels": _int(
                    split_audit_row.get("overlapping_training_labels")
                ),
                "walkforward_split_embargo_breach_rows": _int(
                    split_audit_row.get("embargo_breach_rows")
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
        "research_launch_execution_receipt_provided": bool(
            summary["research_launch_execution_receipt_provided"]
        ),
        "research_launch_execution_receipt_required": bool(
            summary["research_launch_execution_receipt_required"]
        ),
        "research_launch_execution_receipt_passed": bool(
            summary["research_launch_execution_receipt_passed"]
        ),
        "research_launch_execution_receipt_id": str(
            summary["research_launch_execution_receipt_id"]
        ),
        "research_launch_dispatch_id": str(
            summary["research_launch_dispatch_id"]
        ),
        "research_launch_attempt_id": str(
            summary["research_launch_attempt_id"]
        ),
        "research_launch_attempt_number": int(
            summary["research_launch_attempt_number"]
        ),
        "research_launch_attempt_record_sha256": str(
            summary["research_launch_attempt_record_sha256"]
        ),
        "research_launch_retry_of_attempt_id": str(
            summary["research_launch_retry_of_attempt_id"]
        ),
        "research_launch_retry_attested": bool(
            summary["research_launch_retry_attested"]
        ),
        "research_launch_execution_receipt_sha256": str(
            summary["research_launch_execution_receipt_sha256"]
        ),
        "research_launch_argv_sha256": str(
            summary["research_launch_argv_sha256"]
        ),
        "research_launch_semantic_sha256": str(
            summary["research_launch_semantic_sha256"]
        ),
        "research_launch_contract_provided": bool(
            summary["research_launch_contract_provided"]
        ),
        "research_launch_contract_required": bool(
            summary["research_launch_contract_required"]
        ),
        "research_launch_contract_passed": bool(
            summary["research_launch_contract_passed"]
        ),
        "research_launch_contract_id": str(
            summary["research_launch_contract_id"]
        ),
        "research_launch_contract_sha256": str(
            summary["research_launch_contract_sha256"]
        ),
        "research_launch_matrix_manifest_sha256": str(
            summary["research_launch_matrix_manifest_sha256"]
        ),
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
        "walkforward_split_audit_provided": bool(
            summary["walkforward_split_audit_provided"]
        ),
        "walkforward_split_audit_required": bool(
            summary["walkforward_split_audit_required"]
        ),
        "walkforward_split_audit_passed": bool(
            summary["walkforward_split_audit_passed"]
        ),
        "walkforward_split_audit_manifest_sha256": str(
            summary["walkforward_split_audit_manifest_sha256"]
        ),
        "walkforward_split_source_rows": int(
            summary["walkforward_split_source_rows"]
        ),
        "walkforward_split_fold_count": int(
            summary["walkforward_split_fold_count"]
        ),
        "walkforward_split_future_training_rows": int(
            summary["walkforward_split_future_training_rows"]
        ),
        "walkforward_split_overlapping_training_labels": int(
            summary["walkforward_split_overlapping_training_labels"]
        ),
        "walkforward_split_embargo_breach_rows": int(
            summary["walkforward_split_embargo_breach_rows"]
        ),
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
            "- Research launch execution receipt: "
            f"{'bound' if bool(summary['research_launch_execution_receipt_provided']) else 'not provided'}"
            f"; passed `{str(bool(summary['research_launch_execution_receipt_passed'])).lower()}`"
        ),
        f"- Launch dispatch ID: `{summary['research_launch_dispatch_id']}`",
        (
            "- Launch attempt: "
            f"`{summary['research_launch_attempt_id']}` "
            f"(number {int(summary['research_launch_attempt_number'])})"
        ),
        (
            "- Research launch contract: "
            f"{'bound' if bool(summary['research_launch_contract_provided']) else 'not provided'}"
            f"; passed `{str(bool(summary['research_launch_contract_passed'])).lower()}`"
        ),
        f"- Launch contract ID: `{summary['research_launch_contract_id']}`",
        (
            "- Research registration: "
            f"{'bound' if bool(summary['research_registration_provided']) else 'not provided'}"
            f"; passed `{str(bool(summary['research_registration_passed'])).lower()}`"
        ),
        f"- Registered study label: `{summary['registered_study_label']}`",
        (
            "- Walk-forward split audit: "
            f"{'bound' if bool(summary['walkforward_split_audit_provided']) else 'not provided'}"
            f"; passed `{str(bool(summary['walkforward_split_audit_passed'])).lower()}`"
        ),
        (
            "- Walk-forward leakage rows (future/overlap/embargo): "
            f"{int(summary['walkforward_split_future_training_rows'])}/"
            f"{int(summary['walkforward_split_overlapping_training_labels'])}/"
            f"{int(summary['walkforward_split_embargo_breach_rows'])}"
        ),
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
