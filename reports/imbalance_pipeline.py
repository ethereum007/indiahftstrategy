from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
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
    edge: ImbalanceEdgeWalkForwardReport | None = None
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
    data_readiness_comparison_dir: str | Path | None = None,
    require_data_readiness_comparison: bool = False,
    market_portability_dir: str | Path | None = None,
    require_market_portability: bool = False,
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
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    instrument_id: str = "BOOK",
    instrument_kind: str = "OPT",
    lot_size: int = 75,
    qty: int = 75,
    exit_imbalance: float = 0.15,
    cooloff_ns: int = 0,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    generic_buy_notional_rate: float | None = None,
    generic_sell_notional_rate: float | None = None,
    generic_per_unit_fee: float | None = None,
    generic_per_contract_fee: float | None = None,
    generic_per_order_fee: float | None = None,
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
    market_portability_config = _read_market_portability_config(market_portability_dir)
    portability_stage = _market_portability_stage(
        market_portability_config,
        required=require_market_portability,
        input_dir=market_portability_dir,
        expected_market=market,
    )
    comparison_summary = _read_data_readiness_comparison_summary(data_readiness_comparison_dir)
    comparison_stage = _data_readiness_comparison_stage(
        comparison_summary,
        required=require_data_readiness_comparison,
        input_dir=data_readiness_comparison_dir,
    )
    parameters = _parameters(
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
        market=market,
        instrument_id=instrument_id,
        instrument_kind=instrument_kind,
        lot_size=lot_size,
        qty=qty,
        exit_imbalance=exit_imbalance,
        cooloff_ns=cooloff_ns,
        feed_latency_us=feed_latency_us,
        order_latency_us=order_latency_us,
        generic_buy_notional_rate=generic_buy_notional_rate,
        generic_sell_notional_rate=generic_sell_notional_rate,
        generic_per_unit_fee=generic_per_unit_fee,
        generic_per_contract_fee=generic_per_contract_fee,
        generic_per_order_fee=generic_per_order_fee,
        max_position_lots=max_position_lots,
        require_market_portability=require_market_portability,
        require_data_readiness_comparison=require_data_readiness_comparison,
        sweep_thresholds=sweep_thresholds,
        selection_thresholds=selection_thresholds,
        edge_walkforward_thresholds=edge_walkforward_thresholds,
        proof_thresholds=proof_thresholds,
        replay_walkforward_thresholds=replay_walkforward_thresholds,
        promotion_thresholds=promotion_thresholds,
    )
    if portability_stage is not None and not bool(portability_stage["status"]):
        return _write_pipeline_outputs(
            output_dir=out,
            edge=None,
            replay=None,
            promotion=None,
            candidate_config=_blocked_candidate_config("market_portability"),
            labels=labels,
            tick_paths=paths,
            parameters=parameters,
            comparison_stage=comparison_stage,
            portability_stage=portability_stage,
            blocked_reason="market_portability_not_ready",
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
        )
    if comparison_stage is not None and not bool(comparison_stage["status"]):
        return _write_pipeline_outputs(
            output_dir=out,
            edge=None,
            replay=None,
            promotion=None,
            candidate_config=_blocked_candidate_config("data_readiness_comparison"),
            labels=labels,
            tick_paths=paths,
            parameters=parameters,
            comparison_stage=comparison_stage,
            portability_stage=portability_stage,
            blocked_reason="data_readiness_comparison_not_ready",
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
        )

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
        market=market,
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
            parameters=parameters,
            comparison_stage=comparison_stage,
            portability_stage=portability_stage,
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
        )

    replay = write_imbalance_replay_walkforward(
        paths,
        output_dir=replay_dir,
        labels=labels,
        candidate_config=edge_dir,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
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
        generic_buy_notional_rate=generic_buy_notional_rate,
        generic_sell_notional_rate=generic_sell_notional_rate,
        generic_per_unit_fee=generic_per_unit_fee,
        generic_per_contract_fee=generic_per_contract_fee,
        generic_per_order_fee=generic_per_order_fee,
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
            parameters=parameters,
            comparison_stage=comparison_stage,
            portability_stage=portability_stage,
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
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
        parameters=parameters,
        comparison_stage=comparison_stage,
        portability_stage=portability_stage,
        data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
        if data_readiness_comparison_dir is not None
        else None,
        market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
    )


def _write_pipeline_outputs(
    *,
    output_dir: Path,
    edge: ImbalanceEdgeWalkForwardReport | None,
    replay: ImbalanceReplayWalkForwardReport | None,
    promotion: ImbalanceCandidatePromotionReport | None,
    candidate_config: dict[str, Any],
    labels: list[str] | None,
    tick_paths: list[Path],
    parameters: dict[str, Any],
    comparison_stage: dict[str, Any] | None = None,
    portability_stage: dict[str, Any] | None = None,
    blocked_reason: str = "preflight_not_ready",
    data_readiness_comparison_dir: Path | None = None,
    market_portability_dir: Path | None = None,
) -> ImbalanceResearchPipelineReport:
    stages = _stages(
        edge,
        replay,
        promotion,
        comparison_stage=comparison_stage,
        portability_stage=portability_stage,
        blocked_reason=blocked_reason,
    )
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
            "data_readiness_comparison": data_readiness_comparison_dir,
            "market_portability": market_portability_dir,
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
    edge: ImbalanceEdgeWalkForwardReport | None,
    replay: ImbalanceReplayWalkForwardReport | None,
    promotion: ImbalanceCandidatePromotionReport | None,
    *,
    comparison_stage: dict[str, Any] | None = None,
    portability_stage: dict[str, Any] | None = None,
    blocked_reason: str = "preflight_not_ready",
) -> pd.DataFrame:
    rows = []
    if portability_stage is not None:
        rows.append(portability_stage)
    if comparison_stage is not None:
        rows.append(comparison_stage)
    rows.append(
        _stage_row("edge_walkforward", edge.output_dir, edge.summary, "passed")
        if edge is not None
        else _skipped_stage("edge_walkforward", blocked_reason)
    )
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
    edge: ImbalanceEdgeWalkForwardReport | None,
    replay: ImbalanceReplayWalkForwardReport | None,
    promotion: ImbalanceCandidatePromotionReport | None,
) -> pd.DataFrame:
    ready = bool(stages["status"].map(_to_bool).all()) if not stages.empty else False
    failed = int((~stages["status"].map(_to_bool)).sum()) if not stages.empty else 0
    edge_row = edge.summary.iloc[0] if edge is not None and not edge.summary.empty else pd.Series(dtype=object)
    replay_row = replay.summary.iloc[0] if replay is not None and not replay.summary.empty else pd.Series(dtype=object)
    promotion_row = promotion.summary.iloc[0] if promotion is not None and not promotion.summary.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_stages": failed,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_researching",
                "edge_passed": bool(edge.passed) if edge is not None else False,
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


def _read_data_readiness_comparison_summary(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "data_readiness_comparison_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"data readiness comparison summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"data readiness comparison summary is empty: {candidate}")
    return frame


def _read_market_portability_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "market_portability_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"market portability config not found: {candidate}")
    return json.loads(candidate.read_text(encoding="utf-8"))


def _market_portability_stage(
    config: dict[str, Any],
    *,
    required: bool,
    input_dir: str | Path | None,
    expected_market: str,
) -> dict[str, Any] | None:
    if not config and not required:
        return None
    provided = bool(config)
    pair = _matching_portability_pair(config, expected_market) if provided else {}
    status = bool(pair)
    reason = "ready" if status else "market_portability_missing"
    if provided and not status:
        reason = _matching_portability_gap(config, expected_market).get(
            "next_gate",
            "market_portability_pair_not_ready",
        )
    return {
        "stage": "market_portability",
        "status": bool(status),
        "status_column": "ready_pairs",
        "skipped": False,
        "output_dir": str(input_dir or ""),
        "failed_checks": 0 if status else 1,
        "recommendation": reason,
    }


def _matching_portability_pair(config: dict[str, Any], expected_market: str) -> dict[str, Any]:
    expected = _identity(expected_market)
    for pair in config.get("ready_pairs") or []:
        if _identity(pair.get("strategy")) != "microprice_imbalance":
            continue
        if _identity(pair.get("market")) != expected:
            continue
        if str(pair.get("status", "")).strip().lower() in {"india_ready", "portable_research"}:
            return dict(pair)
    return {}


def _matching_portability_gap(config: dict[str, Any], expected_market: str) -> dict[str, Any]:
    expected = _identity(expected_market)
    for pair in config.get("gap_pairs") or []:
        if _identity(pair.get("strategy")) == "microprice_imbalance" and _identity(pair.get("market")) == expected:
            return dict(pair)
    return {}


def _data_readiness_comparison_stage(
    summary: pd.DataFrame,
    *,
    required: bool,
    input_dir: str | Path | None,
) -> dict[str, Any] | None:
    if summary.empty and not required:
        return None
    provided = not summary.empty
    row = summary.iloc[0] if provided else pd.Series(dtype=object)
    accepted = _to_bool(row.get("accepted", False)) if provided else False
    status = provided and accepted
    reason = "accepted" if status else "data_readiness_comparison_missing"
    if provided and not accepted:
        reason = "data_readiness_comparison_not_accepted"
    return {
        "stage": "data_readiness_comparison",
        "status": bool(status),
        "status_column": "accepted",
        "skipped": False,
        "output_dir": str(input_dir or ""),
        "failed_checks": _int(row, "total_failed_checks") if provided else 1,
        "recommendation": str(row.get("recommendation", reason)) if provided else reason,
    }


def _blocked_candidate_config(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": False,
        "strategy": "imbalance",
        "failed_checks": [reason],
        "parameters": {},
        "metrics": {},
    }


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


def _identity(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


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
