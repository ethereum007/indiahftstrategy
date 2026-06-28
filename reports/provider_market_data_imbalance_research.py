from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from reports.imbalance_candidate_promotion import ImbalanceCandidatePromotionThresholds
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds
from reports.imbalance_edge_sweep import ImbalanceEdgeSweepThresholds
from reports.imbalance_edge_walkforward import ImbalanceEdgeWalkForwardThresholds
from reports.imbalance_pipeline import ImbalanceResearchPipelineReport, write_imbalance_research_pipeline
from reports.imbalance_replay_walkforward import ImbalanceReplayWalkForwardThresholds
from reports.manifest import write_experiment_manifest
from reports.proof import ProofThresholds
from reports.provider_market_data_research_handoff import (
    ProviderMarketDataResearchHandoffConfig,
    ProviderMarketDataResearchHandoffReport,
    write_provider_market_data_research_handoff,
)


DEFAULT_ENTRY_IMBALANCE_VALUES = (0.55, 0.65, 0.75)
DEFAULT_MIN_MICROPRICE_EDGE_TICKS_VALUES = (0.25, 0.50, 1.00)
DEFAULT_FORWARD_HORIZON_NS_VALUES = (100_000_000, 500_000_000, 1_000_000_000)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceResearchConfig:
    require_research_ready: bool = True
    allow_synthetic_smoke: bool = False
    min_tick_folds: int = 2
    tick_size: float = 0.05
    market: str = ""
    instrument_id: str = "PROVIDER_BOOK"
    instrument_kind: str = "FUT"
    lot_size: int = 75
    qty: int = 75
    entry_imbalance_values: tuple[float, ...] = field(default_factory=lambda: DEFAULT_ENTRY_IMBALANCE_VALUES)
    min_microprice_edge_ticks_values: tuple[float, ...] = field(
        default_factory=lambda: DEFAULT_MIN_MICROPRICE_EDGE_TICKS_VALUES
    )
    forward_horizon_ns_values: tuple[int, ...] = field(default_factory=lambda: DEFAULT_FORWARD_HORIZON_NS_VALUES)
    max_spread_ticks: float = 2.0
    min_depth: int = 1
    min_signals: int = 1
    min_direction_count: int = 1
    min_mean_forward_edge_ticks: float = 0.0
    min_win_rate: float = 0.0
    min_median_forward_edge_ticks: float | None = None
    filter_session: bool = True
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    min_passed_configs: int = 1
    min_best_usable_signals: int = 1
    min_best_mean_forward_edge_ticks: float = 0.0
    min_best_win_rate: float = 0.0
    min_selection_sweeps: int | None = None
    min_selection_pass_rate: float = 1.0
    min_selection_median_usable_signals: float = 1.0
    min_selection_median_mean_forward_edge_ticks: float = 0.0
    min_selection_min_win_rate: float = 0.0
    min_selection_median_robust_score: float | None = None
    min_edge_folds: int | None = None
    min_passed_edge_sweeps: int | None = None
    allow_unselected: bool = False
    exit_imbalance: float = 0.15
    cooloff_ns: int = 0
    feed_latency_us: float = 0.0
    order_latency_us: float = 0.0
    generic_buy_notional_rate: float | None = None
    generic_sell_notional_rate: float | None = None
    generic_per_unit_fee: float | None = None
    generic_per_contract_fee: float | None = None
    generic_per_order_fee: float | None = None
    max_position_lots: int = 20
    min_net_pnl: float = 0.0
    min_fills: int = 1
    max_drawdown: float | None = None
    max_otr: float | None = None
    min_markout_mean: float | None = None
    min_replay_folds: int | None = None
    min_proof_pass_rate: float = 1.0
    min_total_fills: int = 1
    min_total_net_pnl: float = 0.0
    max_worst_drawdown: float | None = None
    min_median_markout_mean: float | None = None


@dataclass(frozen=True)
class ProviderMarketDataImbalanceResearchReport:
    handoff: ProviderMarketDataResearchHandoffReport
    pipeline: ImbalanceResearchPipelineReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_imbalance_research(
    live_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceResearchConfig | None = None,
) -> ProviderMarketDataImbalanceResearchReport:
    config = _normalize_config(config or ProviderMarketDataImbalanceResearchConfig())
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    handoff_dir = out / "research_handoff"
    pipeline_dir = out / "imbalance_research"
    handoff = write_provider_market_data_research_handoff(
        live_evidence_dir,
        handoff_dir,
        config=ProviderMarketDataResearchHandoffConfig(
            strategies=("imbalance",),
            require_research_ready=config.require_research_ready,
            allow_synthetic_smoke=config.allow_synthetic_smoke,
            min_tick_folds=config.min_tick_folds,
            tick_size=config.tick_size,
            market=config.market,
            instrument_id=config.instrument_id,
            output_root=str(pipeline_dir),
        ),
    )
    pipeline = _write_pipeline(handoff, pipeline_dir, config) if handoff.ready else None
    checks = _checks(handoff, pipeline, config)
    summary = _summary(live_evidence_dir, handoff, pipeline, checks, out, handoff_dir, pipeline_dir, config)
    action_queue = _action_queue(handoff, pipeline, summary.iloc[0])
    payload = _config(summary.iloc[0], handoff, pipeline, checks, action_queue, config)

    summary.to_csv(out / "provider_market_data_imbalance_research_summary.csv", index=False)
    checks.to_csv(out / "provider_market_data_imbalance_research_checks.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_research_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_research_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_research_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )
    manifest_inputs: dict[str, Any] = {
        "live_evidence_dir": Path(live_evidence_dir),
        "research_handoff": handoff_dir,
    }
    summary_row = summary.iloc[0]
    capture_bundle = _path_from_text(str(summary_row["capture_bundle_path"]))
    if capture_bundle is not None and capture_bundle.exists():
        manifest_inputs["capture_bundle"] = capture_bundle
    capture_env_template = _path_from_text(str(summary_row["capture_env_template_path"]))
    if capture_env_template is not None and capture_env_template.exists():
        manifest_inputs["capture_env_template"] = capture_env_template
    adapter_handoff = _path_from_text(str(summary_row["adapter_handoff_path"]))
    if adapter_handoff is not None and adapter_handoff.exists():
        manifest_inputs["adapter_handoff"] = adapter_handoff
    source_env_template = _path_from_text(str(summary_row["source_credential_env_template_path"]))
    if source_env_template is not None and source_env_template.exists():
        manifest_inputs["source_credential_env_template"] = source_env_template
    if pipeline is not None:
        manifest_inputs["imbalance_research"] = pipeline_dir
    write_experiment_manifest(
        out,
        run_type="provider_market_data_imbalance_research",
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "pipeline_ready": bool(summary.iloc[0]["pipeline_ready"]),
            "handoff_ready": bool(summary.iloc[0]["handoff_ready"]),
            "candidate_ready": bool(summary.iloc[0]["candidate_ready"]),
            "exchange": str(summary.iloc[0]["exchange"]),
            "source_session": _source_session_contract_from_summary(summary.iloc[0]),
            "market_session": _market_session_contract_from_summary(summary.iloc[0]),
            "capture_bundle_provided": bool(summary.iloc[0]["capture_bundle_provided"]),
            "capture_env_template_exists": bool(summary.iloc[0]["capture_env_template_exists"]),
            "adapter_handoff_exists": bool(summary.iloc[0]["adapter_handoff_exists"]),
            "capture_env_template": {
                "path": str(summary.iloc[0]["capture_env_template_path"]),
                "exists": bool(summary.iloc[0]["capture_env_template_exists"]),
                "sha256": str(summary.iloc[0]["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(summary.iloc[0]["adapter_handoff_path"]),
                "exists": bool(summary.iloc[0]["adapter_handoff_exists"]),
                "sha256": str(summary.iloc[0]["adapter_handoff_sha256"]),
            },
            "capture_bundle_metadata_matches_session": bool(summary.iloc[0]["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_bundle": {
                "exchange": str(summary.iloc[0]["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary.iloc[0]),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary.iloc[0]),
                "metadata_matches_session": bool(summary.iloc[0]["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "source_credential_env_template": {
                "path": str(summary.iloc[0]["source_credential_env_template_path"]),
                "exists": bool(summary.iloc[0]["source_credential_env_template_exists"]),
                "sha256": str(summary.iloc[0]["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary.iloc[0]["source_live_fetch_contract_available"]),
                "next_gate": str(summary.iloc[0]["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary.iloc[0]["source_live_fetch_contract_command_template"]),
                "exchange": str(summary.iloc[0]["source_live_fetch_contract_exchange"]),
                "market": str(summary.iloc[0]["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary.iloc[0]),
            },
        },
    )
    return ProviderMarketDataImbalanceResearchReport(
        handoff=handoff,
        pipeline=pipeline,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
        output_dir=out,
    )


def _write_pipeline(
    handoff: ProviderMarketDataResearchHandoffReport,
    output_dir: Path,
    config: ProviderMarketDataImbalanceResearchConfig,
) -> ImbalanceResearchPipelineReport:
    datasets = handoff.datasets.sort_values("priority").reset_index(drop=True)
    tick_paths = datasets["capture_path"].astype(str).tolist()
    labels = datasets["fold_label"].astype(str).tolist()
    fold_count = int(len(tick_paths))
    market = config.market or _first_text(handoff.summary, "market") or "india_nse_index_derivatives"
    return write_imbalance_research_pipeline(
        tick_paths,
        output_dir=output_dir,
        labels=labels,
        entry_imbalance_values=list(config.entry_imbalance_values),
        min_microprice_edge_ticks_values=list(config.min_microprice_edge_ticks_values),
        forward_horizon_ns_values=list(config.forward_horizon_ns_values),
        tick_size=config.tick_size,
        max_spread_ticks=config.max_spread_ticks,
        min_depth=config.min_depth,
        min_signals=config.min_signals,
        min_direction_count=config.min_direction_count,
        min_mean_forward_edge_ticks=config.min_mean_forward_edge_ticks,
        min_win_rate=config.min_win_rate,
        min_median_forward_edge_ticks=config.min_median_forward_edge_ticks,
        timestamp_unit=config.timestamp_unit,
        timestamp_tz=config.timestamp_tz,
        filter_session=config.filter_session,
        market=market,
        instrument_id=config.instrument_id,
        instrument_kind=config.instrument_kind,
        lot_size=config.lot_size,
        qty=config.qty,
        exit_imbalance=config.exit_imbalance,
        cooloff_ns=config.cooloff_ns,
        feed_latency_us=config.feed_latency_us,
        order_latency_us=config.order_latency_us,
        generic_buy_notional_rate=config.generic_buy_notional_rate,
        generic_sell_notional_rate=config.generic_sell_notional_rate,
        generic_per_unit_fee=config.generic_per_unit_fee,
        generic_per_contract_fee=config.generic_per_contract_fee,
        generic_per_order_fee=config.generic_per_order_fee,
        max_position_lots=config.max_position_lots,
        sweep_thresholds=ImbalanceEdgeSweepThresholds(
            min_passed_configs=config.min_passed_configs,
            min_best_usable_signals=config.min_best_usable_signals,
            min_best_mean_forward_edge_ticks=config.min_best_mean_forward_edge_ticks,
            min_best_win_rate=config.min_best_win_rate,
        ),
        selection_thresholds=ImbalanceEdgeSelectionThresholds(
            min_sweeps=config.min_selection_sweeps if config.min_selection_sweeps is not None else fold_count,
            min_pass_rate=config.min_selection_pass_rate,
            min_median_usable_signals=config.min_selection_median_usable_signals,
            min_median_mean_forward_edge_ticks=config.min_selection_median_mean_forward_edge_ticks,
            min_min_win_rate=config.min_selection_min_win_rate,
            min_median_robust_score=config.min_selection_median_robust_score,
        ),
        edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(
            min_folds=config.min_edge_folds if config.min_edge_folds is not None else config.min_tick_folds,
            min_passed_sweeps=config.min_passed_edge_sweeps
            if config.min_passed_edge_sweeps is not None
            else config.min_tick_folds,
            require_selection=not config.allow_unselected,
        ),
        proof_thresholds=ProofThresholds(
            min_net_pnl=config.min_net_pnl,
            min_fills=config.min_fills,
            max_drawdown=config.max_drawdown,
            max_otr=config.max_otr,
            min_markout_mean=config.min_markout_mean,
        ),
        replay_walkforward_thresholds=ImbalanceReplayWalkForwardThresholds(
            min_folds=config.min_replay_folds if config.min_replay_folds is not None else config.min_tick_folds,
            min_proof_pass_rate=config.min_proof_pass_rate,
            min_total_fills=config.min_total_fills,
            min_total_net_pnl=config.min_total_net_pnl,
            max_worst_drawdown=config.max_worst_drawdown,
            min_median_markout_mean=config.min_median_markout_mean,
        ),
        promotion_thresholds=ImbalanceCandidatePromotionThresholds(
            min_proof_pass_rate=config.min_proof_pass_rate,
            min_total_fills=config.min_total_fills,
            min_total_net_pnl=config.min_total_net_pnl,
            max_worst_drawdown=config.max_worst_drawdown,
            min_median_markout_mean=config.min_median_markout_mean,
        ),
    )


def _checks(
    handoff: ProviderMarketDataResearchHandoffReport,
    pipeline: ImbalanceResearchPipelineReport | None,
    config: ProviderMarketDataImbalanceResearchConfig,
) -> pd.DataFrame:
    handoff_row = handoff.summary.iloc[0] if not handoff.summary.empty else pd.Series(dtype=object)
    pipeline_row = pipeline.summary.iloc[0] if pipeline is not None and not pipeline.summary.empty else pd.Series(dtype=object)
    candidate_ready = bool(pipeline.candidate_config.get("ready", False)) if pipeline is not None else False
    pipeline_ready = bool(pipeline.ready) if pipeline is not None else False
    return pd.DataFrame(
        [
            _check(
                "provider_research_handoff_ready",
                bool(handoff.ready),
                "is",
                True,
                bool(handoff.ready),
                "provider live evidence has not passed the research handoff gate",
            ),
            _check(
                "provider_research_handoff_research_ready",
                _truthy(handoff_row.get("research_ready")),
                "is",
                True,
                _truthy(handoff_row.get("research_ready")) or not config.require_research_ready,
                "provider live evidence is not research-ready",
            ),
            _check(
                "provider_tick_folds_present",
                int(handoff_row.get("dataset_count", 0) or 0),
                ">=",
                config.min_tick_folds,
                int(handoff_row.get("dataset_count", 0) or 0) >= config.min_tick_folds,
                "not enough provider tick folds for imbalance research",
            ),
            _check(
                "imbalance_research_pipeline_ready",
                pipeline_ready,
                "is",
                True,
                pipeline_ready,
                "imbalance research pipeline did not produce a ready candidate",
            ),
            _check(
                "imbalance_candidate_config_ready",
                candidate_ready,
                "is",
                True,
                candidate_ready,
                "imbalance candidate_config.json is not ready",
            ),
            _check(
                "tick_size_positive",
                config.tick_size,
                ">",
                0,
                config.tick_size > 0,
                "tick size must be positive",
            ),
            _check(
                "pipeline_market_matches_handoff",
                _first_text(pipeline.summary, "market") if pipeline is not None else "",
                "is",
                _first_text(handoff.summary, "market"),
                pipeline is not None
                and _first_text(pipeline.summary, "market") == _first_text(handoff.summary, "market"),
                "pipeline market identity does not match provider handoff market",
            ),
            _check(
                "pipeline_strategy_is_imbalance",
                _first_text(pipeline.summary, "strategy") if pipeline is not None else "",
                "is",
                "imbalance",
                pipeline is not None and _first_text(pipeline.summary, "strategy") == "imbalance",
                "pipeline did not preserve imbalance strategy identity",
            ),
        ]
    )


def _summary(
    live_evidence_dir: str | Path,
    handoff: ProviderMarketDataResearchHandoffReport,
    pipeline: ImbalanceResearchPipelineReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    handoff_dir: Path,
    pipeline_dir: Path,
    config: ProviderMarketDataImbalanceResearchConfig,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    handoff_row = handoff.summary.iloc[0] if not handoff.summary.empty else pd.Series(dtype=object)
    pipeline_row = pipeline.summary.iloc[0] if pipeline is not None and not pipeline.summary.empty else pd.Series(dtype=object)
    candidate = pipeline.candidate_config if pipeline is not None else {}
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "handoff_ready": bool(handoff.ready),
                "pipeline_ready": bool(pipeline.ready) if pipeline is not None else False,
                "candidate_ready": bool(candidate.get("ready", False)),
                "live_evidence_dir": str(live_evidence_dir),
                "output_dir": str(output_dir),
                "handoff_dir": str(handoff_dir),
                "imbalance_research_dir": str(pipeline_dir if pipeline is not None else ""),
                "market": _first_text(handoff.summary, "market") or config.market,
                "strategy": "imbalance",
                "provider": _first_text(handoff.summary, "provider"),
                "transport": _first_text(handoff.summary, "transport"),
                "exchange": str(handoff_row.get("exchange", "") or ""),
                "source_session_timezone": str(handoff_row.get("source_session_timezone", "") or ""),
                "source_session_open_local": str(handoff_row.get("source_session_open_local", "") or ""),
                "source_session_close_local": str(handoff_row.get("source_session_close_local", "") or ""),
                "market_session_timezone": str(handoff_row.get("market_session_timezone", "") or ""),
                "market_session_open_local": str(handoff_row.get("market_session_open_local", "") or ""),
                "market_session_close_local": str(handoff_row.get("market_session_close_local", "") or ""),
                "capture_bundle_path": str(handoff_row.get("capture_bundle_path", "") or ""),
                "capture_bundle_provided": _truthy(handoff_row.get("capture_bundle_provided")),
                "capture_bundle_exists": _truthy(handoff_row.get("capture_bundle_exists")),
                "capture_bundle_ready": _truthy(handoff_row.get("capture_bundle_ready")),
                "capture_env_template_path": str(handoff_row.get("capture_env_template_path", "") or ""),
                "capture_env_template_provided": _truthy(handoff_row.get("capture_env_template_provided")),
                "capture_env_template_exists": _truthy(handoff_row.get("capture_env_template_exists")),
                "capture_env_template_sha256": str(handoff_row.get("capture_env_template_sha256", "") or ""),
                "adapter_handoff_path": str(handoff_row.get("adapter_handoff_path", "") or ""),
                "adapter_handoff_provided": _truthy(handoff_row.get("adapter_handoff_provided")),
                "adapter_handoff_exists": _truthy(handoff_row.get("adapter_handoff_exists")),
                "adapter_handoff_sha256": str(handoff_row.get("adapter_handoff_sha256", "") or ""),
                "source_credential_env_template_path": str(
                    handoff_row.get("source_credential_env_template_path", "") or ""
                ),
                "source_credential_env_template_exists": _truthy(
                    handoff_row.get("source_credential_env_template_exists")
                ),
                "source_credential_env_template_sha256": str(
                    handoff_row.get("source_credential_env_template_sha256", "") or ""
                ),
                "source_live_fetch_contract_available": _truthy(
                    handoff_row.get("source_live_fetch_contract_available")
                ),
                "source_live_fetch_contract_next_gate": str(
                    handoff_row.get("source_live_fetch_contract_next_gate", "") or ""
                ),
                "source_live_fetch_contract_command_template": str(
                    handoff_row.get("source_live_fetch_contract_command_template", "") or ""
                ),
                "source_live_fetch_contract_exchange": str(
                    handoff_row.get("source_live_fetch_contract_exchange", "") or ""
                ),
                "source_live_fetch_contract_market": str(
                    handoff_row.get("source_live_fetch_contract_market", "") or ""
                ),
                "source_live_fetch_contract_session_timezone": str(
                    handoff_row.get("source_live_fetch_contract_session_timezone", "") or ""
                ),
                "source_live_fetch_contract_session_open_local": str(
                    handoff_row.get("source_live_fetch_contract_session_open_local", "") or ""
                ),
                "source_live_fetch_contract_session_close_local": str(
                    handoff_row.get("source_live_fetch_contract_session_close_local", "") or ""
                ),
                "capture_bundle_exchange": str(handoff_row.get("capture_bundle_exchange", "") or ""),
                "capture_bundle_source_session_timezone": str(
                    handoff_row.get("capture_bundle_source_session_timezone", "") or ""
                ),
                "capture_bundle_source_session_open_local": str(
                    handoff_row.get("capture_bundle_source_session_open_local", "") or ""
                ),
                "capture_bundle_source_session_close_local": str(
                    handoff_row.get("capture_bundle_source_session_close_local", "") or ""
                ),
                "capture_bundle_market_session_timezone": str(
                    handoff_row.get("capture_bundle_market_session_timezone", "") or ""
                ),
                "capture_bundle_market_session_open_local": str(
                    handoff_row.get("capture_bundle_market_session_open_local", "") or ""
                ),
                "capture_bundle_market_session_close_local": str(
                    handoff_row.get("capture_bundle_market_session_close_local", "") or ""
                ),
                "capture_bundle_metadata_matches_session": _truthy(
                    handoff_row.get("capture_bundle_metadata_matches_session")
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _truthy(
                    handoff_row.get("capture_bundle_live_fetch_contract_metadata_matches_session")
                ),
                "dataset_count": int(handoff_row.get("dataset_count", 0) or 0),
                "ready_command_count": int(handoff_row.get("ready_command_count", 0) or 0),
                "synthetic_dataset_count": int(handoff_row.get("synthetic_dataset_count", 0) or 0),
                "edge_passed": bool(pipeline_row.get("edge_passed", False)),
                "replay_passed": bool(pipeline_row.get("replay_passed", False)),
                "promotion_ready": bool(pipeline_row.get("promotion_ready", False)),
                "candidate_scenario_key": str(pipeline_row.get("candidate_scenario_key", "")),
                "edge_selectable_scenarios": int(pipeline_row.get("edge_selectable_scenarios", 0) or 0),
                "replay_total_fills": int(pipeline_row.get("replay_total_fills", 0) or 0),
                "replay_total_net_pnl": float(pipeline_row.get("replay_total_net_pnl", 0.0) or 0.0),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "catalog_provider_imbalance_research" if ready else "repair_provider_imbalance_research",
                "next_gate": "catalog-runs" if ready else _blocked_next_gate(handoff, pipeline),
                "next_gate_help_command": _ready_help_command(output_dir) if ready else _blocked_help_command(handoff, pipeline),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(
    handoff: ProviderMarketDataResearchHandoffReport,
    pipeline: ImbalanceResearchPipelineReport | None,
    summary: pd.Series,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "catalog_provider_imbalance_research",
                    "reason": "provider live evidence produced a promoted imbalance research candidate",
                    "next_gate": "catalog-runs",
                    "next_gate_help_command": _ready_help_command(Path(str(summary["output_dir"]))),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    if not handoff.ready:
        for row in handoff.action_queue.to_dict(orient="records"):
            rows.append(
                {
                    "priority": len(rows) + 1,
                    "queue_status": "blocked",
                    "action": f"provider_handoff_{row.get('action', 'repair')}",
                    "reason": str(row.get("reason", "")),
                    "next_gate": str(row.get("next_gate", "")),
                    "next_gate_help_command": str(row.get("next_gate_help_command", "")),
                }
            )
    if pipeline is not None:
        failed = pipeline.stages.loc[~pipeline.stages["status"].astype(bool)]
        for row in failed.to_dict(orient="records"):
            next_gate = _stage_next_gate(str(row.get("stage", "")))
            rows.append(
                {
                    "priority": len(rows) + 1,
                    "queue_status": "blocked",
                    "action": f"repair_imbalance_{row.get('stage', 'pipeline')}",
                    "reason": str(row.get("recommendation", "")),
                    "next_gate": next_gate,
                    "next_gate_help_command": _stage_help_command(next_gate),
                }
            )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_research",
                "reason": "provider imbalance research did not pass",
                "next_gate": "run-provider-market-data-imbalance-research",
                "next_gate_help_command": "python -m hft_cli run-provider-market-data-imbalance-research --help",
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    handoff: ProviderMarketDataResearchHandoffReport,
    pipeline: ImbalanceResearchPipelineReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceResearchConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "summary": _series_record(summary),
        "checks": _records(checks),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "capture_bundle": _handoff_capture_bundle(handoff),
        "research_handoff": {
            "ready": bool(handoff.ready),
            "output_dir": str(handoff.output_dir or ""),
            "summary": _first_record(handoff.summary),
            "datasets": _records(handoff.datasets),
            "commands": _records(handoff.commands),
        },
        "imbalance_research": {
            "ready": bool(pipeline.ready) if pipeline is not None else False,
            "output_dir": str(pipeline.output_dir or "") if pipeline is not None else "",
            "summary": _first_record(pipeline.summary if pipeline is not None else None),
            "stages": _records(pipeline.stages if pipeline is not None else None),
            "candidate_config": _jsonable(pipeline.candidate_config if pipeline is not None else {}),
        },
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _blocked_next_gate(
    handoff: ProviderMarketDataResearchHandoffReport,
    pipeline: ImbalanceResearchPipelineReport | None,
) -> str:
    if not handoff.ready and not handoff.action_queue.empty:
        return str(handoff.action_queue.iloc[0]["next_gate"])
    if pipeline is not None:
        failed = pipeline.stages.loc[~pipeline.stages["status"].astype(bool)]
        if not failed.empty:
            return _stage_next_gate(str(failed.iloc[0]["stage"]))
    return "run-provider-market-data-imbalance-research"


def _blocked_help_command(
    handoff: ProviderMarketDataResearchHandoffReport,
    pipeline: ImbalanceResearchPipelineReport | None,
) -> str:
    if not handoff.ready and not handoff.action_queue.empty:
        return str(handoff.action_queue.iloc[0]["next_gate_help_command"])
    next_gate = _blocked_next_gate(handoff, pipeline)
    if next_gate == "run-provider-market-data-imbalance-research":
        return "python -m hft_cli run-provider-market-data-imbalance-research --help"
    return _stage_help_command(next_gate)


def _stage_next_gate(stage: str) -> str:
    if stage == "edge_walkforward":
        return "walkforward-imbalance-edge"
    if stage == "replay_walkforward":
        return "walkforward-imbalance-replay"
    if stage == "promotion":
        return "promote-imbalance-candidate"
    return "pipeline-imbalance-research"


def _stage_help_command(next_gate: str) -> str:
    if next_gate in {"walkforward-imbalance-edge", "walkforward-imbalance-replay", "promote-imbalance-candidate"}:
        return f"python -m hft_cli {next_gate} --help"
    return "python -m hft_cli pipeline-imbalance-research --help"


def _ready_help_command(output_dir: str | Path) -> str:
    return f"python -m hft_cli catalog-runs --roots {Path(output_dir)} --out runs\\catalog\\latest"


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Research",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Capture bundle: {summary['capture_bundle_path']}",
        f"- Credential env template: {summary['capture_env_template_path']}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Tick folds: {summary['dataset_count']}",
        f"- Edge passed: {'yes' if bool(summary['edge_passed']) else 'no'}",
        f"- Replay passed: {'yes' if bool(summary['replay_passed']) else 'no'}",
        f"- Promotion ready: {'yes' if bool(summary['promotion_ready']) else 'no'}",
        "",
        "## Checks",
        "",
        _checks_table(checks),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "_None_"
    rows = [
        [
            str(row.get("check", "")),
            "pass" if _truthy(row.get("passed")) else "fail",
            str(row.get("value", "")),
            str(row.get("threshold", "")),
            str(row.get("reason", "")),
        ]
        for row in checks.to_dict(orient="records")
    ]
    return _markdown_table(["Check", "Status", "Value", "Threshold", "Reason"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(row.get("priority", "")),
            str(row.get("queue_status", "")),
            str(row.get("action", "")),
            str(row.get("next_gate", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
    return _markdown_table(["#", "Status", "Action", "Next gate", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _normalize_config(config: ProviderMarketDataImbalanceResearchConfig) -> ProviderMarketDataImbalanceResearchConfig:
    return ProviderMarketDataImbalanceResearchConfig(
        require_research_ready=bool(config.require_research_ready),
        allow_synthetic_smoke=bool(config.allow_synthetic_smoke),
        min_tick_folds=int(config.min_tick_folds),
        tick_size=float(config.tick_size),
        market=str(config.market or "").strip(),
        instrument_id=str(config.instrument_id or "PROVIDER_BOOK").strip(),
        instrument_kind=str(config.instrument_kind or "FUT").strip().upper(),
        lot_size=int(config.lot_size),
        qty=int(config.qty),
        entry_imbalance_values=tuple(float(value) for value in config.entry_imbalance_values),
        min_microprice_edge_ticks_values=tuple(float(value) for value in config.min_microprice_edge_ticks_values),
        forward_horizon_ns_values=tuple(int(value) for value in config.forward_horizon_ns_values),
        max_spread_ticks=float(config.max_spread_ticks),
        min_depth=int(config.min_depth),
        min_signals=int(config.min_signals),
        min_direction_count=int(config.min_direction_count),
        min_mean_forward_edge_ticks=float(config.min_mean_forward_edge_ticks),
        min_win_rate=float(config.min_win_rate),
        min_median_forward_edge_ticks=_optional_float(config.min_median_forward_edge_ticks),
        filter_session=bool(config.filter_session),
        timestamp_unit=str(config.timestamp_unit or "ns").strip(),
        timestamp_tz=None if config.timestamp_tz is None else str(config.timestamp_tz).strip(),
        min_passed_configs=int(config.min_passed_configs),
        min_best_usable_signals=int(config.min_best_usable_signals),
        min_best_mean_forward_edge_ticks=float(config.min_best_mean_forward_edge_ticks),
        min_best_win_rate=float(config.min_best_win_rate),
        min_selection_sweeps=_optional_int(config.min_selection_sweeps),
        min_selection_pass_rate=float(config.min_selection_pass_rate),
        min_selection_median_usable_signals=float(config.min_selection_median_usable_signals),
        min_selection_median_mean_forward_edge_ticks=float(config.min_selection_median_mean_forward_edge_ticks),
        min_selection_min_win_rate=float(config.min_selection_min_win_rate),
        min_selection_median_robust_score=_optional_float(config.min_selection_median_robust_score),
        min_edge_folds=_optional_int(config.min_edge_folds),
        min_passed_edge_sweeps=_optional_int(config.min_passed_edge_sweeps),
        allow_unselected=bool(config.allow_unselected),
        exit_imbalance=float(config.exit_imbalance),
        cooloff_ns=int(config.cooloff_ns),
        feed_latency_us=float(config.feed_latency_us),
        order_latency_us=float(config.order_latency_us),
        generic_buy_notional_rate=_optional_float(config.generic_buy_notional_rate),
        generic_sell_notional_rate=_optional_float(config.generic_sell_notional_rate),
        generic_per_unit_fee=_optional_float(config.generic_per_unit_fee),
        generic_per_contract_fee=_optional_float(config.generic_per_contract_fee),
        generic_per_order_fee=_optional_float(config.generic_per_order_fee),
        max_position_lots=int(config.max_position_lots),
        min_net_pnl=float(config.min_net_pnl),
        min_fills=int(config.min_fills),
        max_drawdown=_optional_float(config.max_drawdown),
        max_otr=_optional_float(config.max_otr),
        min_markout_mean=_optional_float(config.min_markout_mean),
        min_replay_folds=_optional_int(config.min_replay_folds),
        min_proof_pass_rate=float(config.min_proof_pass_rate),
        min_total_fills=int(config.min_total_fills),
        min_total_net_pnl=float(config.min_total_net_pnl),
        max_worst_drawdown=_optional_float(config.max_worst_drawdown),
        min_median_markout_mean=_optional_float(config.min_median_markout_mean),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _series_record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_session_timezone"]),
        "open_local": str(summary["source_session_open_local"]),
        "close_local": str(summary["source_session_close_local"]),
    }


def _market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["market_session_timezone"]),
        "open_local": str(summary["market_session_open_local"]),
        "close_local": str(summary["market_session_close_local"]),
    }


def _capture_bundle_source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_source_session_timezone"]),
        "open_local": str(summary["capture_bundle_source_session_open_local"]),
        "close_local": str(summary["capture_bundle_source_session_close_local"]),
    }


def _capture_bundle_market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_market_session_timezone"]),
        "open_local": str(summary["capture_bundle_market_session_open_local"]),
        "close_local": str(summary["capture_bundle_market_session_close_local"]),
    }


def _source_live_fetch_contract_session_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_live_fetch_contract_session_timezone"]),
        "open_local": str(summary["source_live_fetch_contract_session_open_local"]),
        "close_local": str(summary["source_live_fetch_contract_session_close_local"]),
    }


def _handoff_capture_bundle(handoff: ProviderMarketDataResearchHandoffReport) -> dict[str, Any]:
    payload = handoff.config.get("capture_bundle") if isinstance(handoff.config, dict) else {}
    if isinstance(payload, dict) and payload:
        return {str(key): _jsonable(value) for key, value in payload.items()}
    row = handoff.summary.iloc[0] if not handoff.summary.empty else pd.Series(dtype=object)
    return {
        "capture_bundle_path": str(row.get("capture_bundle_path", "") or ""),
        "capture_bundle_provided": _truthy(row.get("capture_bundle_provided")),
        "capture_bundle_exists": _truthy(row.get("capture_bundle_exists")),
        "capture_bundle_ready": _truthy(row.get("capture_bundle_ready")),
        "capture_env_template_path": str(row.get("capture_env_template_path", "") or ""),
        "capture_env_template_provided": _truthy(row.get("capture_env_template_provided")),
        "capture_env_template_exists": _truthy(row.get("capture_env_template_exists")),
        "capture_env_template_sha256": str(row.get("capture_env_template_sha256", "") or ""),
        "adapter_handoff_path": str(row.get("adapter_handoff_path", "") or ""),
        "adapter_handoff_provided": _truthy(row.get("adapter_handoff_provided")),
        "adapter_handoff_exists": _truthy(row.get("adapter_handoff_exists")),
        "adapter_handoff_sha256": str(row.get("adapter_handoff_sha256", "") or ""),
        "source_credential_env_template_path": str(row.get("source_credential_env_template_path", "") or ""),
        "source_credential_env_template_provided": _truthy(row.get("source_credential_env_template_provided")),
        "source_credential_env_template_exists": _truthy(row.get("source_credential_env_template_exists")),
        "source_credential_env_template_sha256": str(row.get("source_credential_env_template_sha256", "") or ""),
        "source_live_fetch_contract_available": _truthy(row.get("source_live_fetch_contract_available")),
        "source_live_fetch_contract_next_gate": str(row.get("source_live_fetch_contract_next_gate", "") or ""),
        "source_live_fetch_contract_command_template": str(
            row.get("source_live_fetch_contract_command_template", "") or ""
        ),
        "source_live_fetch_contract_exchange": str(row.get("source_live_fetch_contract_exchange", "") or ""),
        "source_live_fetch_contract_market": str(row.get("source_live_fetch_contract_market", "") or ""),
        "source_live_fetch_contract_session_timezone": str(
            row.get("source_live_fetch_contract_session_timezone", "") or ""
        ),
        "source_live_fetch_contract_session_open_local": str(
            row.get("source_live_fetch_contract_session_open_local", "") or ""
        ),
        "source_live_fetch_contract_session_close_local": str(
            row.get("source_live_fetch_contract_session_close_local", "") or ""
        ),
        "exchange": str(row.get("capture_bundle_exchange", "") or ""),
        "source_session": {
            "timezone": str(row.get("capture_bundle_source_session_timezone", "") or ""),
            "open_local": str(row.get("capture_bundle_source_session_open_local", "") or ""),
            "close_local": str(row.get("capture_bundle_source_session_close_local", "") or ""),
        },
        "market_session": {
            "timezone": str(row.get("capture_bundle_market_session_timezone", "") or ""),
            "open_local": str(row.get("capture_bundle_market_session_open_local", "") or ""),
            "close_local": str(row.get("capture_bundle_market_session_close_local", "") or ""),
        },
        "metadata_matches_session": _truthy(row.get("capture_bundle_metadata_matches_session")),
        "live_fetch_contract_metadata_matches_session": _truthy(
            row.get("capture_bundle_live_fetch_contract_metadata_matches_session")
        ),
    }


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _text(value: object, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "ready", "pass"}


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
