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
from reports.manifest import write_experiment_manifest
from reports.promotion import PromotionReport, PromotionThresholds, write_promotion_report
from reports.sweeps import SweepComparison, write_sweep_comparison


RUN_TYPE = "robust_selection_pipeline"
READY_NEXT_GATE = "stage-orders"
STAGE_NEXT_GATES = {
    "selection": "compare-sweeps",
    "backtest_overfit": "audit-backtest-overfit",
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
    stages: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    candidate_config: dict[str, Any]
    selection: SweepComparison
    overfit: BacktestOverfitReport
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
    promotion_thresholds: PromotionThresholds | None = None,
) -> RobustSelectionPipelineReport:
    paths = [Path(path).resolve() for path in sweep_paths]
    if not paths:
        raise ValueError("at least one sweep path is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match sweep_paths length")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    selection_dir = out / "01_selection"
    overfit_dir = out / "02_backtest_overfit"
    promotion_dir = out / "03_promotion"

    resolved_selection_min_sweeps = (
        len(paths) if selection_min_sweeps is None else selection_min_sweeps
    )
    overfit_config = overfit_config or BacktestOverfitConfig()
    if group_cols and not overfit_config.scenario_columns:
        overfit_config = replace(overfit_config, scenario_columns=tuple(group_cols))
    if not overfit_config.require_selection_manifest:
        overfit_config = replace(overfit_config, require_selection_manifest=True)
    overfit_thresholds = overfit_thresholds or BacktestOverfitThresholds()
    promotion_thresholds = replace(
        promotion_thresholds or PromotionThresholds(),
        require_overfit_audit=True,
    )

    selection = write_sweep_comparison(
        paths,
        output_dir=selection_dir,
        labels=labels,
        group_cols=group_cols,
        min_pass_rate=selection_min_pass_rate,
        min_sweeps=resolved_selection_min_sweeps,
        min_median_net_pnl=selection_min_median_net_pnl,
        max_worst_drawdown=selection_max_worst_drawdown,
    )
    overfit = write_backtest_overfit_audit(
        selection_dir,
        output_dir=overfit_dir,
        config=overfit_config,
        thresholds=overfit_thresholds,
    )
    promotion = write_promotion_report(
        selection_dir,
        output_dir=promotion_dir,
        overfit_audit_path=overfit_dir,
        thresholds=promotion_thresholds,
    )

    stages = _stages(selection, overfit, promotion)
    action_queue = _action_queue(stages)
    summary = _summary(
        stages,
        action_queue,
        selection,
        overfit,
        promotion,
        strategy=strategy,
        market=market,
        sweep_count=len(paths),
    )
    candidate_config = _candidate_config(
        promotion_dir,
        summary.iloc[0],
        stages,
        paths,
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
        "selection": {
            "min_pass_rate": selection_min_pass_rate,
            "min_sweeps": resolved_selection_min_sweeps,
            "min_median_net_pnl": selection_min_median_net_pnl,
            "max_worst_drawdown": selection_max_worst_drawdown,
        },
        "overfit_config": asdict(overfit_config),
        "overfit_thresholds": asdict(overfit_thresholds),
        "promotion_thresholds": asdict(promotion_thresholds),
    }
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters=parameters,
        inputs={
            "sweeps": paths,
            "selection_manifest": selection_dir / "manifest.json",
            "backtest_overfit_manifest": overfit_dir / "manifest.json",
            "promotion_manifest": promotion_dir / "manifest.json",
        },
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "strategy": strategy,
            "market": market,
            "candidate_scenario_key": str(summary.iloc[0]["candidate_scenario_key"]),
            "probability_overfit": _float(summary.iloc[0].get("probability_overfit")),
            "authorizes_submission": False,
        },
    )
    return RobustSelectionPipelineReport(
        stages=stages,
        summary=summary,
        action_queue=action_queue,
        candidate_config=candidate_config,
        selection=selection,
        overfit=overfit,
        promotion=promotion,
        output_dir=out,
    )


def _stages(
    selection: SweepComparison,
    overfit: BacktestOverfitReport,
    promotion: PromotionReport,
) -> pd.DataFrame:
    selection_row = (
        selection.summary.iloc[0]
        if not selection.summary.empty
        else pd.Series(dtype=object)
    )
    overfit_row = overfit.summary.iloc[0] if not overfit.summary.empty else pd.Series(dtype=object)
    promotion_row = (
        promotion.summary.iloc[0]
        if not promotion.summary.empty
        else pd.Series(dtype=object)
    )
    return pd.DataFrame(
        [
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
    promotion: PromotionReport,
    *,
    strategy: str,
    market: str,
    sweep_count: int,
) -> pd.DataFrame:
    ready = bool(stages["status"].map(_to_bool).all()) if not stages.empty else False
    selection_row = selection.summary.iloc[0] if not selection.summary.empty else pd.Series(dtype=object)
    overfit_row = overfit.summary.iloc[0] if not overfit.summary.empty else pd.Series(dtype=object)
    promotion_row = promotion.summary.iloc[0] if not promotion.summary.empty else pd.Series(dtype=object)
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
    sweep_paths: list[Path],
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
        "next_gate": str(summary["next_gate"]),
        "sweep_paths": [str(path) for path in sweep_paths],
        "selection_path": str(promotion_dir.parent / "01_selection"),
        "backtest_overfit_path": str(promotion_dir.parent / "02_backtest_overfit"),
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
        f"- Sweep periods: {int(summary['sweep_count'])}",
        f"- Candidate: `{summary['candidate_scenario_key']}`",
        f"- Probability of backtest overfitting: {_format_number(summary['probability_overfit'])}",
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
