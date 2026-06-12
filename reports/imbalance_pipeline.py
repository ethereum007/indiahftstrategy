from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.imbalance_candidate_promotion import (
    ImbalanceCandidatePromotionReport,
    ImbalanceCandidatePromotionThresholds,
    write_imbalance_candidate_promotion,
)
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds
from reports.imbalance_edge_sweep import ImbalanceEdgeSweepThresholds
from reports.imbalance_edge_walkforward import (
    ImbalanceEdgeWalkForwardReport,
    ImbalanceEdgeWalkForwardThresholds,
    write_imbalance_edge_walkforward,
)
from reports.imbalance_replay_walkforward import (
    ImbalanceReplayWalkForwardReport,
    ImbalanceReplayWalkForwardThresholds,
    write_imbalance_replay_walkforward,
)
from reports.manifest import write_experiment_manifest
from reports.proof import ProofThresholds


@dataclass(frozen=True)
class ImbalanceResearchPipelineReport:
    stages: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    edge: ImbalanceEdgeWalkForwardReport
    replay: ImbalanceReplayWalkForwardReport | None = None
    promotion: ImbalanceCandidatePromotionReport | None = None
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_imbalance_research_pipeline(
    tick_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    entry_imbalance_values: list[float],
    min_microprice_edge_ticks_values: list[float],
    forward_horizon_ns_values: list[int],
    tick_size: float = 0.05,
    max_spread_ticks: float = 2.0,
    min_depth: int = 1,
    min_signals: int = 1,
    min_direction_count: int = 1,
    min_mean_forward_edge_ticks: float = 0.0,
    min_win_rate: float = 0.0,
    min_median_forward_edge_ticks: float | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    instrument_id: str = "BOOK",
    instrument_kind: str = "OPT",
    lot_size: int = 75,
    qty: int = 75,
    exit_imbalance: float = 0.15,
    cooloff_ns: int = 0,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    max_position_lots: int = 20,
    sweep_thresholds: ImbalanceEdgeSweepThresholds | None = None,
    selection_thresholds: ImbalanceEdgeSelectionThresholds | None = None,
    edge_walkforward_thresholds: ImbalanceEdgeWalkForwardThresholds | None = None,
    proof_thresholds: ProofThresholds | None = None,
    replay_walkforward_thresholds: ImbalanceReplayWalkForwardThresholds | None = None,
    promotion_thresholds: ImbalanceCandidatePromotionThresholds | None = None,
) -> ImbalanceResearchPipelineReport:
    paths = [Path(path) for path in tick_paths]
    if not paths:
        raise ValueError("at least one tick file is required")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    edge_dir = out / "edge_walkforward"
    replay_dir = out / "replay_walkforward"
    promotion_dir = out / "promotion"

    sweep_thresholds = sweep_thresholds or ImbalanceEdgeSweepThresholds()
    selection_thresholds = selection_thresholds or ImbalanceEdgeSelectionThresholds(min_sweeps=len(paths))
    edge_walkforward_thresholds = edge_walkforward_thresholds or ImbalanceEdgeWalkForwardThresholds(
        min_folds=len(paths),
        min_passed_sweeps=len(paths),
    )
    proof_thresholds = proof_thresholds or ProofThresholds()
    replay_walkforward_thresholds = replay_walkforward_thresholds or ImbalanceReplayWalkForwardThresholds(
        min_folds=len(paths),
    )
    promotion_thresholds = promotion_thresholds or ImbalanceCandidatePromotionThresholds()

    edge = write_imbalance_edge_walkforward(
        paths,
        output_dir=edge_dir,
        labels=labels,
        entry_imbalance_values=entry_imbalance_values,
        min_microprice_edge_ticks_values=min_microprice_edge_ticks_values,
        forward_horizon_ns_values=forward_horizon_ns_values,
        tick_size=tick_size,
        max_spread_ticks=max_spread_ticks,
        min_depth=min_depth,
        min_signals=min_signals,
        min_direction_count=min_direction_count,
        min_mean_forward_edge_ticks=min_mean_forward_edge_ticks,
        min_win_rate=min_win_rate,
        min_median_forward_edge_ticks=min_median_forward_edge_ticks,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        sweep_thresholds=sweep_thresholds,
        selection_thresholds=selection_thresholds,
        walkforward_thresholds=edge_walkforward_thresholds,
    )
    if not edge.passed:
        return _write_pipeline_outputs(
            output_dir=out,
            edge=edge,
            replay=None,
            promotion=None,
            candidate_config=edge.candidate_config,
            labels=labels,
            tick_paths=paths,
            parameters=_parameters(
                entry_imbalance_values=entry_imbalance_values,
                min_microprice_edge_ticks_values=min_microprice_edge_ticks_values,
                forward_horizon_ns_values=forward_horizon_ns_values,
                tick_size=tick_size,
                max_spread_ticks=max_spread_ticks,
                min_depth=min_depth,
                min_signals=min_signals,
                min_direction_count=min_direction_count,
                min_mean_forward_edge_ticks=min_mean_forward_edge_ticks,
                min_win_rate=min_win_rate,
                min_median_forward_edge_ticks=min_median_forward_edge_ticks,
                timestamp_unit=timestamp_unit,
                timestamp_tz=timestamp_tz,
                filter_session=filter_session,
                instrument_id=instrument_id,
                instrument_kind=instrument_kind,
                lot_size=lot_size,
                qty=qty,
                exit_imbalance=exit_imbalance,
                cooloff_ns=cooloff_ns,
                feed_latency_us=feed_latency_us,
                order_latency_us=order_latency_us,
                max_position_lots=max_position_lots,
                sweep_thresholds=sweep_thresholds,
                selection_thresholds=selection_thresholds,
                edge_walkforward_thresholds=edge_walkforward_thresholds,
                proof_thresholds=proof_thresholds,
                replay_walkforward_thresholds=replay_walkforward_thresholds,
                promotion_thresholds=promotion_thresholds,
            ),
        )

    replay = write_imbalance_replay_walkforward(
        paths,
        output_dir=replay_dir,
        labels=labels,
        candidate_config=edge_dir,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        instrument_id=instrument_id,
        instrument_kind=instrument_kind,
        lot_size=lot_size,
        tick_size=tick_size,
        qty=qty,
        exit_imbalance=exit_imbalance,
        max_spread_ticks=max_spread_ticks,
        min_depth=min_depth,
        cooloff_ns=cooloff_ns,
        feed_latency_us=feed_latency_us,
        order_latency_us=order_latency_us,
        max_position_lots=max_position_lots,
        proof_thresholds=proof_thresholds,
        thresholds=replay_walkforward_thresholds,
    )
    if not replay.passed:
        return _write_pipeline_outputs(
            output_dir=out,
            edge=edge,
            replay=replay,
            promotion=None,
            candidate_config=replay.candidate_config,
            labels=labels,
            tick_paths=paths,
            parameters=_parameters(
                entry_imbalance_values=entry_imbalance_values,
                min_microprice_edge_ticks_values=min_microprice_edge_ticks_values,
                forward_horizon_ns_values=forward_horizon_ns_values,
                tick_size=tick_size,
                max_spread_ticks=max_spread_ticks,
                min_depth=min_depth,
                min_signals=min_signals,
                min_direction_count=min_direction_count,
                min_mean_forward_edge_ticks=min_mean_forward_edge_ticks,
                min_win_rate=min_win_rate,
                min_median_forward_edge_ticks=min_median_forward_edge_ticks,
                timestamp_unit=timestamp_unit,
                timestamp_tz=timestamp_tz,
                filter_session=filter_session,
                instrument_id=instrument_id,
                instrument_kind=instrument_kind,
                lot_size=lot_size,
                qty=qty,
                exit_imbalance=exit_imbalance,
                cooloff_ns=cooloff_ns,
                feed_latency_us=feed_latency_us,
                order_latency_us=order_latency_us,
                max_position_lots=max_position_lots,
                sweep_thresholds=sweep_thresholds,
                selection_thresholds=selection_thresholds,
                edge_walkforward_thresholds=edge_walkforward_thresholds,
                proof_thresholds=proof_thresholds,
                replay_walkforward_thresholds=replay_walkforward_thresholds,
                promotion_thresholds=promotion_thresholds,
            ),
        )

    promotion = write_imbalance_candidate_promotion(
        replay_dir,
        output_dir=promotion_dir,
        thresholds=promotion_thresholds,
    )
    return _write_pipeline_outputs(
        output_dir=out,
        edge=edge,
        replay=replay,
        promotion=promotion,
        candidate_config=promotion.candidate_config,
        labels=labels,
        tick_paths=paths,
        parameters=_parameters(
            entry_imbalance_values=entry_imbalance_values,
            min_microprice_edge_ticks_values=min_microprice_edge_ticks_values,
            forward_horizon_ns_values=forward_horizon_ns_values,
            tick_size=tick_size,
            max_spread_ticks=max_spread_ticks,
            min_depth=min_depth,
            min_signals=min_signals,
            min_direction_count=min_direction_count,
            min_mean_forward_edge_ticks=min_mean_forward_edge_ticks,
            min_win_rate=min_win_rate,
            min_median_forward_edge_ticks=min_median_forward_edge_ticks,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            instrument_id=instrument_id,
            instrument_kind=instrument_kind,
            lot_size=lot_size,
            qty=qty,
            exit_imbalance=exit_imbalance,
            cooloff_ns=cooloff_ns,
            feed_latency_us=feed_latency_us,
            order_latency_us=order_latency_us,
            max_position_lots=max_position_lots,
            sweep_thresholds=sweep_thresholds,
            selection_thresholds=selection_thresholds,
            edge_walkforward_thresholds=edge_walkforward_thresholds,
            proof_thresholds=proof_thresholds,
            replay_walkforward_thresholds=replay_walkforward_thresholds,
            promotion_thresholds=promotion_thresholds,
        ),
    )


def _write_pipeline_outputs(
    *,
    output_dir: Path,
    edge: ImbalanceEdgeWalkForwardReport,
    replay: ImbalanceReplayWalkForwardReport | None,
    promotion: ImbalanceCandidatePromotionReport | None,
    candidate_config: dict[str, Any],
    labels: list[str] | None,
    tick_paths: list[Path],
    parameters: dict[str, Any],
) -> ImbalanceResearchPipelineReport:
    stages = _stages(edge, replay, promotion)
    summary = _summary(stages, edge, replay, promotion)
    config = _candidate_config(candidate_config, summary.iloc[0], stages)

    stages.to_csv(output_dir / "imbalance_pipeline_stages.csv", index=False)
    summary.to_csv(output_dir / "imbalance_pipeline_summary.csv", index=False)
    (output_dir / "candidate_config.json").write_text(
        json.dumps(_jsonable(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        output_dir,
        run_type="imbalance_research_pipeline",
        parameters={"labels": labels, **parameters},
        inputs={
            "ticks": tick_paths,
            "edge_walkforward": output_dir / "edge_walkforward",
            "replay_walkforward": output_dir / "replay_walkforward",
            "promotion": output_dir / "promotion",
        },
    )
    return ImbalanceResearchPipelineReport(
        stages=stages,
        summary=summary,
        candidate_config=config,
        edge=edge,
        replay=replay,
        promotion=promotion,
        output_dir=output_dir,
    )


def _stages(
    edge: ImbalanceEdgeWalkForwardReport,
    replay: ImbalanceReplayWalkForwardReport | None,
    promotion: ImbalanceCandidatePromotionReport | None,
) -> pd.DataFrame:
    rows = [_stage_row("edge_walkforward", edge.output_dir, edge.summary, "passed")]
    rows.append(
        _stage_row("replay_walkforward", replay.output_dir, replay.summary, "passed")
        if replay is not None
        else _skipped_stage("replay_walkforward", "edge_walkforward_not_ready")
    )
    rows.append(
        _stage_row("promotion", promotion.output_dir, promotion.summary, "ready")
        if promotion is not None
        else _skipped_stage("promotion", "replay_walkforward_not_ready")
    )
    return pd.DataFrame(rows)


def _stage_row(stage: str, output_dir: Path | None, summary: pd.DataFrame, status_column: str) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    status = _to_bool(row.get(status_column, False))
    return {
        "stage": stage,
        "status": status,
        "status_column": status_column,
        "skipped": False,
        "output_dir": str(output_dir or ""),
        "failed_checks": _int(row, "failed_checks"),
        "recommendation": str(row.get("recommendation", "")),
    }


def _skipped_stage(stage: str, reason: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": False,
        "status_column": "",
        "skipped": True,
        "output_dir": "",
        "failed_checks": 1,
        "recommendation": reason,
    }


def _summary(
    stages: pd.DataFrame,
    edge: ImbalanceEdgeWalkForwardReport,
    replay: ImbalanceReplayWalkForwardReport | None,
    promotion: ImbalanceCandidatePromotionReport | None,
) -> pd.DataFrame:
    ready = bool(stages["status"].map(_to_bool).all()) if not stages.empty else False
    failed = int((~stages["status"].map(_to_bool)).sum()) if not stages.empty else 0
    edge_row = edge.summary.iloc[0] if not edge.summary.empty else pd.Series(dtype=object)
    replay_row = replay.summary.iloc[0] if replay is not None and not replay.summary.empty else pd.Series(dtype=object)
    promotion_row = promotion.summary.iloc[0] if promotion is not None and not promotion.summary.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_stages": failed,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_researching",
                "edge_passed": bool(edge.passed),
                "replay_passed": bool(replay.passed) if replay is not None else False,
                "promotion_ready": bool(promotion.ready) if promotion is not None else False,
                "candidate_scenario_key": str(promotion_row.get("candidate_scenario_key", "")),
                "edge_selectable_scenarios": _int(edge_row, "selectable_scenarios"),
                "replay_proof_pass_rate": _float(replay_row, "proof_pass_rate"),
                "replay_total_net_pnl": _float(replay_row, "total_net_pnl"),
                "replay_total_fills": _int(replay_row, "total_fills"),
            }
        ]
    )


def _candidate_config(source: dict[str, Any], summary: pd.Series, stages: pd.DataFrame) -> dict[str, Any]:
    config = dict(source)
    config["ready"] = bool(summary["ready"])
    config["source_run_type"] = "imbalance_research_pipeline"
    failed = list(config.get("failed_checks", []) or [])
    failed.extend(stages.loc[~stages["status"].map(_to_bool), "stage"].astype(str).tolist())
    config["failed_checks"] = list(dict.fromkeys(failed))
    config["pipeline"] = {
        "ready": _jsonable(summary.get("ready")),
        "failed_stages": _jsonable(summary.get("failed_stages")),
        "recommendation": _jsonable(summary.get("recommendation")),
        "stages": [
            {
                "stage": str(row.stage),
                "status": bool(row.status),
                "skipped": bool(row.skipped),
                "recommendation": str(row.recommendation),
            }
            for row in stages.itertuples(index=False)
        ],
    }
    return config


def _parameters(**values: Any) -> dict[str, Any]:
    return {
        key: asdict(value) if hasattr(value, "__dataclass_fields__") else value
        for key, value in values.items()
    }


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
