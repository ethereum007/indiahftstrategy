from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapters.broker import run_calibration_report
from adapters.halt_response_export import HaltResponseExportConfig, write_halt_response_export
from adapters.mapped_data import MappedDataConfig, write_mapped_data_normalization
from adapters.mapped_order_export import MappedOrderExportConfig, write_mapped_order_export
from adapters.order_export import OrderExportConfig, write_order_export
from adapters.order_mapping_draft import OrderMappingDraftConfig, write_order_mapping_draft
from adapters.order_reconciliation import ReconciliationThresholds, write_order_reconciliation
from adapters.order_upload_pack import OrderUploadPackConfig, write_order_upload_pack
from adapters.orders import OrderStagingLimits, write_staged_orders
from adapters.schema_audit import write_adapter_schema_audit
from data.chains import load_option_chain_csv
from data.diagnostics import chain_diagnostics, tick_diagnostics, write_diagnostics
from data.loaders import load_tick_csv
from reports.catalog import write_experiment_catalog
from reports.evidence import EvidenceThresholds, write_strategy_evidence_review
from reports.fill_model import FillModelCalibrationThresholds, write_fill_model_calibration
from reports.fill_model_drift import FillModelDriftThresholds, write_fill_model_drift_report
from reports.halt_execution import HaltExecutionThresholds, write_halt_execution_report
from reports.halt_incident import HaltIncidentThresholds, write_halt_incident_report
from reports.halt_response import HaltResponseConfig, write_halt_response_plan
from reports.imbalance_candidate_promotion import (
    ImbalanceCandidatePromotionThresholds,
    write_imbalance_candidate_promotion,
)
from reports.imbalance_edge import ImbalanceEdgeThresholds, write_imbalance_edge_audit
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds, write_imbalance_edge_selection
from reports.imbalance_edge_sweep import ImbalanceEdgeSweepThresholds, write_imbalance_edge_sweep
from reports.imbalance_edge_walkforward import (
    ImbalanceEdgeWalkForwardThresholds,
    write_imbalance_edge_walkforward,
)
from reports.imbalance_pipeline import write_imbalance_research_pipeline
from reports.imbalance_replay_walkforward import (
    ImbalanceReplayWalkForwardThresholds,
    write_imbalance_replay_walkforward,
)
from reports.instrument_metadata import InstrumentMetadataConfig, write_instrument_metadata_report
from reports.launch import LaunchThresholds, write_launch_bundle
from reports.leadlag_edge import LeadLagEdgeThresholds, write_leadlag_edge_audit
from reports.market_profile import MarketProfileReportConfig, write_market_profile_report
from reports.market_portability import MarketPortabilityReportConfig, write_market_portability_report
from reports.order_exposure import OrderExposureConfig, write_order_exposure_report
from reports.parity_edge import ParityEdgeThresholds, write_parity_edge_audit
from reports.proof import ProofThresholds, write_proof_report
from reports.proof_refresh import ProofRefreshThresholds, write_proof_refresh_report
from reports.promotion import PromotionThresholds, write_promotion_report
from reports.quote_risk import QuoteRiskThresholds, write_quote_risk_report
from reports.resume import ResumeGateThresholds, write_resume_gate_report
from reports.runtime_guard import write_runtime_guard_report
from reports.runtime_telemetry import write_runtime_telemetry_snapshot
from reports.replay_calibration import calibrated_replay_params_from_path, write_calibrated_replay_plan
from reports.scaleup import ScaleUpThresholds, write_scaleup_plan
from reports.settlement_candidate_promotion import (
    SettlementCandidatePromotionThresholds,
    write_settlement_candidate_promotion,
)
from reports.settlement_convergence import (
    SettlementConvergenceThresholds,
    write_settlement_convergence_audit,
)
from reports.settlement_convergence_walkforward import (
    SettlementConvergenceWalkForwardThresholds,
    write_settlement_convergence_walkforward,
)
from reports.settlement_launch_pipeline import (
    SettlementLaunchPipelineConfig,
    write_settlement_launch_pipeline,
)
from reports.settlement_order_plan import SettlementOrderPlanConfig, write_settlement_order_plan
from reports.shadow_comparison import ShadowComparisonThresholds, write_shadow_session_comparison
from reports.shadow_session import ShadowSessionThresholds, write_shadow_session_report
from reports.stress import StressConfig, write_stress_report
from reports.sweeps import write_sweep_comparison
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from research.run_leadlag import run_leadlag
from scanners.run_parity_box import run_scan
from strategies.run_imbalance_replay import run_imbalance_replay
from strategies.run_imbalance_sweep import run_imbalance_sweep
from strategies.run_leadlag_replay import run_leadlag_replay
from strategies.run_leadlag_sweep import run_leadlag_sweep
from strategies.run_parity_replay import run_parity_replay
from strategies.run_parity_sweep import run_parity_sweep
from strategies.run_surface_mm_replay import SurfaceMMReplayConfig, run_surface_mm_replay
from strategies.run_surface_mm_sweep import run_surface_mm_sweep
from strategies.run_surface_quotes import run_surface_quote_generation


def _add_generic_cost_args(parser: argparse.ArgumentParser, *, default: float | None = None) -> None:
    parser.add_argument("--generic-buy-notional-rate", type=float, default=default)
    parser.add_argument("--generic-sell-notional-rate", type=float, default=default)
    parser.add_argument("--generic-per-unit-fee", type=float, default=default)
    parser.add_argument("--generic-per-contract-fee", type=float, default=default)
    parser.add_argument("--generic-per-order-fee", type=float, default=default)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hft", description="India HFT research command runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan-parity-box", help="Run executable parity/box scanner.")
    scan.add_argument("--chain", required=True)
    scan.add_argument("--futures", required=True)
    scan.add_argument("--out", required=True)
    scan.add_argument("--no-filter-session", action="store_true")
    scan.add_argument("--asof-latency-ns", type=int, default=0)
    scan.add_argument("--depth-fraction", type=float, default=0.25)

    parity_edge = sub.add_parser("audit-parity-edge", help="Gate parity/box scan opportunities before replay.")
    parity_edge.add_argument("--scan", required=True)
    parity_edge.add_argument("--out", required=True)
    parity_edge.add_argument("--min-total-opportunities", type=int, default=1)
    parity_edge.add_argument("--min-parity-opportunities", type=int, default=0)
    parity_edge.add_argument("--min-box-opportunities", type=int, default=0)
    parity_edge.add_argument("--min-total-net-edge", type=float, default=0.0)
    parity_edge.add_argument("--min-median-net-edge", type=float, default=0.0)
    parity_edge.add_argument("--min-best-net-edge", type=float, default=0.0)
    parity_edge.add_argument("--min-median-persistence-ticks", type=float, default=0.0)
    parity_edge.add_argument("--min-direction-count", type=int, default=1)
    parity_edge.add_argument("--max-future-staleness-ns", type=int, default=None)
    parity_edge.add_argument("--fail-on-breach", action="store_true")

    parity = sub.add_parser("replay-parity", help="Replay parity taker strategy.")
    parity.add_argument("--chain", required=True)
    parity.add_argument("--futures", required=True)
    parity.add_argument("--out", required=True)
    parity.add_argument("--no-filter-session", action="store_true")
    parity.add_argument("--signal-limit", type=int, default=None)
    parity.add_argument("--depth-fraction", type=float, default=0.25)
    parity.add_argument("--feed-latency-us", type=float, default=0.0)
    parity.add_argument("--order-latency-us", type=float, default=0.0)
    parity.add_argument("--fill-model", default=None)
    parity.add_argument("--allow-unready-fill-model", action="store_true")

    leadlag = sub.add_parser("measure-leadlag", help="Measure lead-lag relationship.")
    leadlag.add_argument("--leader", required=True)
    leadlag.add_argument("--laggard", required=True)
    leadlag.add_argument("--out", required=True)
    leadlag.add_argument("--no-filter-session", action="store_true")
    leadlag.add_argument("--leader-tick-size", type=float, default=0.05)
    leadlag.add_argument("--laggard-tick-size", type=float, default=0.05)
    leadlag.add_argument("--delta", type=float, default=1.0)
    leadlag.add_argument("--innovation-ticks", type=float, default=2.0)

    leadlag_edge = sub.add_parser("audit-leadlag-edge", help="Gate lead-lag measurement evidence before replay.")
    leadlag_edge.add_argument("--measure", required=True)
    leadlag_edge.add_argument("--out", required=True)
    leadlag_edge.add_argument("--min-events", type=int, default=1)
    leadlag_edge.add_argument("--min-abs-correlation", type=float, default=0.0)
    leadlag_edge.add_argument("--min-correlation-samples", type=int, default=2)
    leadlag_edge.add_argument("--min-update-rate", type=float, default=0.0)
    leadlag_edge.add_argument("--max-median-update-ns", type=int, default=None)
    leadlag_edge.add_argument("--min-best-latency-net-pnl", type=float, default=0.0)
    leadlag_edge.add_argument("--min-best-latency-fills", type=int, default=1)
    leadlag_edge.add_argument("--min-profitable-latency-ns", type=int, default=0)
    leadlag_edge.add_argument("--fail-on-breach", action="store_true")

    imbalance_edge = sub.add_parser("audit-imbalance-edge", help="Gate microprice imbalance evidence before replay.")
    imbalance_edge.add_argument("--ticks", required=True)
    imbalance_edge.add_argument("--out", required=True)
    imbalance_edge.add_argument("--no-filter-session", action="store_true")
    imbalance_edge.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    imbalance_edge.add_argument("--tick-size", type=float, default=0.05)
    imbalance_edge.add_argument("--entry-imbalance", type=float, default=0.6)
    imbalance_edge.add_argument("--min-microprice-edge-ticks", type=float, default=0.25)
    imbalance_edge.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_edge.add_argument("--min-depth", type=int, default=1)
    imbalance_edge.add_argument("--forward-horizon-ns", type=int, default=100_000_000)
    imbalance_edge.add_argument("--min-signals", type=int, default=1)
    imbalance_edge.add_argument("--min-direction-count", type=int, default=1)
    imbalance_edge.add_argument("--min-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge.add_argument("--min-win-rate", type=float, default=0.0)
    imbalance_edge.add_argument("--min-median-forward-edge-ticks", type=float, default=None)
    imbalance_edge.add_argument("--fail-on-breach", action="store_true")

    imbalance_edge_sweep = sub.add_parser("sweep-imbalance-edge", help="Sweep microprice imbalance edge thresholds before replay.")
    imbalance_edge_sweep.add_argument("--ticks", required=True)
    imbalance_edge_sweep.add_argument("--out", required=True)
    imbalance_edge_sweep.add_argument("--no-filter-session", action="store_true")
    imbalance_edge_sweep.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    imbalance_edge_sweep.add_argument("--tick-size", type=float, default=0.05)
    imbalance_edge_sweep.add_argument("--entry-imbalance", nargs="+", required=True, type=float)
    imbalance_edge_sweep.add_argument("--min-microprice-edge-ticks", nargs="+", required=True, type=float)
    imbalance_edge_sweep.add_argument("--forward-horizon-ns", nargs="+", required=True, type=int)
    imbalance_edge_sweep.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_edge_sweep.add_argument("--min-depth", type=int, default=1)
    imbalance_edge_sweep.add_argument("--min-signals", type=int, default=1)
    imbalance_edge_sweep.add_argument("--min-direction-count", type=int, default=1)
    imbalance_edge_sweep.add_argument("--min-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge_sweep.add_argument("--min-win-rate", type=float, default=0.0)
    imbalance_edge_sweep.add_argument("--min-median-forward-edge-ticks", type=float, default=None)
    imbalance_edge_sweep.add_argument("--min-passed-configs", type=int, default=1)
    imbalance_edge_sweep.add_argument("--min-best-usable-signals", type=int, default=1)
    imbalance_edge_sweep.add_argument("--min-best-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge_sweep.add_argument("--min-best-win-rate", type=float, default=0.0)
    imbalance_edge_sweep.add_argument("--fail-on-breach", action="store_true")

    imbalance_edge_compare = sub.add_parser("compare-imbalance-edge-sweeps", help="Select stable imbalance edge parameters across sweeps.")
    imbalance_edge_compare.add_argument("--sweeps", nargs="+", required=True)
    imbalance_edge_compare.add_argument("--out", required=True)
    imbalance_edge_compare.add_argument("--label", action="append", dest="labels")
    imbalance_edge_compare.add_argument("--min-sweeps", type=int, default=1)
    imbalance_edge_compare.add_argument("--min-pass-rate", type=float, default=1.0)
    imbalance_edge_compare.add_argument("--min-median-usable-signals", type=float, default=1.0)
    imbalance_edge_compare.add_argument("--min-median-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge_compare.add_argument("--min-min-win-rate", type=float, default=0.0)
    imbalance_edge_compare.add_argument("--min-median-robust-score", type=float, default=None)
    imbalance_edge_compare.add_argument("--fail-on-breach", action="store_true")

    imbalance_edge_walkforward = sub.add_parser("walkforward-imbalance-edge", help="Run imbalance edge sweeps across tick folds and select stable parameters.")
    imbalance_edge_walkforward.add_argument("--ticks", nargs="+", required=True)
    imbalance_edge_walkforward.add_argument("--out", required=True)
    imbalance_edge_walkforward.add_argument("--label", action="append", dest="labels")
    imbalance_edge_walkforward.add_argument("--no-filter-session", action="store_true")
    imbalance_edge_walkforward.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    imbalance_edge_walkforward.add_argument("--tick-size", type=float, default=0.05)
    imbalance_edge_walkforward.add_argument("--entry-imbalance", nargs="+", required=True, type=float)
    imbalance_edge_walkforward.add_argument("--min-microprice-edge-ticks", nargs="+", required=True, type=float)
    imbalance_edge_walkforward.add_argument("--forward-horizon-ns", nargs="+", required=True, type=int)
    imbalance_edge_walkforward.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_edge_walkforward.add_argument("--min-depth", type=int, default=1)
    imbalance_edge_walkforward.add_argument("--min-signals", type=int, default=1)
    imbalance_edge_walkforward.add_argument("--min-direction-count", type=int, default=1)
    imbalance_edge_walkforward.add_argument("--min-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge_walkforward.add_argument("--min-win-rate", type=float, default=0.0)
    imbalance_edge_walkforward.add_argument("--min-median-forward-edge-ticks", type=float, default=None)
    imbalance_edge_walkforward.add_argument("--min-passed-configs", type=int, default=1)
    imbalance_edge_walkforward.add_argument("--min-best-usable-signals", type=int, default=1)
    imbalance_edge_walkforward.add_argument("--min-best-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge_walkforward.add_argument("--min-best-win-rate", type=float, default=0.0)
    imbalance_edge_walkforward.add_argument("--min-selection-sweeps", type=int, default=None)
    imbalance_edge_walkforward.add_argument("--min-selection-pass-rate", type=float, default=1.0)
    imbalance_edge_walkforward.add_argument("--min-selection-median-usable-signals", type=float, default=1.0)
    imbalance_edge_walkforward.add_argument("--min-selection-median-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_edge_walkforward.add_argument("--min-selection-min-win-rate", type=float, default=0.0)
    imbalance_edge_walkforward.add_argument("--min-selection-median-robust-score", type=float, default=None)
    imbalance_edge_walkforward.add_argument("--min-folds", type=int, default=None)
    imbalance_edge_walkforward.add_argument("--min-passed-sweeps", type=int, default=None)
    imbalance_edge_walkforward.add_argument("--allow-unselected", action="store_true")
    imbalance_edge_walkforward.add_argument("--fail-on-breach", action="store_true")

    leadlag_replay = sub.add_parser("replay-leadlag", help="Replay lead-lag taker strategy.")
    leadlag_replay.add_argument("--leader", required=True)
    leadlag_replay.add_argument("--laggard", required=True)
    leadlag_replay.add_argument("--out", required=True)
    leadlag_replay.add_argument("--no-filter-session", action="store_true")
    leadlag_replay.add_argument("--leader-tick", type=float, default=0.05)
    leadlag_replay.add_argument("--laggard-tick", type=float, default=0.05)
    leadlag_replay.add_argument("--delta", type=float, default=1.0)
    leadlag_replay.add_argument("--trigger-ticks", type=float, default=3.0)
    leadlag_replay.add_argument("--qty", type=int, default=75)
    leadlag_replay.add_argument("--feed-latency-us", type=float, default=0.0)
    leadlag_replay.add_argument("--order-latency-us", type=float, default=0.0)
    leadlag_replay.add_argument("--fill-model", default=None)
    leadlag_replay.add_argument("--allow-unready-fill-model", action="store_true")

    imbalance_replay = sub.add_parser("replay-imbalance", help="Replay microprice/order-book imbalance strategy.")
    imbalance_replay.add_argument("--ticks", required=True)
    imbalance_replay.add_argument("--out", required=True)
    imbalance_replay.add_argument("--no-filter-session", action="store_true")
    imbalance_replay.add_argument("--market", default=None)
    imbalance_replay.add_argument("--instrument-id", default="BOOK")
    imbalance_replay.add_argument("--instrument-kind", default="OPT", choices=["FUT", "OPT", "EQ"])
    imbalance_replay.add_argument("--lot-size", type=int, default=75)
    imbalance_replay.add_argument("--tick-size", type=float, default=None)
    imbalance_replay.add_argument("--qty", type=int, default=75)
    imbalance_replay.add_argument("--entry-imbalance", type=float, default=None)
    imbalance_replay.add_argument("--exit-imbalance", type=float, default=0.15)
    imbalance_replay.add_argument("--min-microprice-edge-ticks", type=float, default=None)
    imbalance_replay.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_replay.add_argument("--min-depth", type=int, default=1)
    imbalance_replay.add_argument("--hold-ns", type=int, default=None)
    imbalance_replay.add_argument("--cooloff-ns", type=int, default=0)
    imbalance_replay.add_argument("--feed-latency-us", type=float, default=0.0)
    imbalance_replay.add_argument("--order-latency-us", type=float, default=0.0)
    imbalance_replay.add_argument("--markout-horizons-ns", nargs="+", default=None, type=int)
    imbalance_replay.add_argument("--candidate-config", default=None)
    imbalance_replay.add_argument("--fill-model", default=None)
    imbalance_replay.add_argument("--allow-unready-fill-model", action="store_true")
    _add_generic_cost_args(imbalance_replay)

    imbalance_replay_walkforward = sub.add_parser("walkforward-imbalance-replay", help="Replay one imbalance candidate across tick folds and aggregate proof.")
    imbalance_replay_walkforward.add_argument("--ticks", nargs="+", required=True)
    imbalance_replay_walkforward.add_argument("--out", required=True)
    imbalance_replay_walkforward.add_argument("--label", action="append", dest="labels")
    imbalance_replay_walkforward.add_argument("--candidate-config", default=None)
    imbalance_replay_walkforward.add_argument("--no-filter-session", action="store_true")
    imbalance_replay_walkforward.add_argument("--market", default=None)
    imbalance_replay_walkforward.add_argument("--instrument-id", default="BOOK")
    imbalance_replay_walkforward.add_argument("--instrument-kind", default="OPT", choices=["FUT", "OPT", "EQ"])
    imbalance_replay_walkforward.add_argument("--lot-size", type=int, default=75)
    imbalance_replay_walkforward.add_argument("--tick-size", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--qty", type=int, default=75)
    imbalance_replay_walkforward.add_argument("--entry-imbalance", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--exit-imbalance", type=float, default=0.15)
    imbalance_replay_walkforward.add_argument("--min-microprice-edge-ticks", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_replay_walkforward.add_argument("--min-depth", type=int, default=1)
    imbalance_replay_walkforward.add_argument("--hold-ns", type=int, default=None)
    imbalance_replay_walkforward.add_argument("--cooloff-ns", type=int, default=0)
    imbalance_replay_walkforward.add_argument("--feed-latency-us", type=float, default=0.0)
    imbalance_replay_walkforward.add_argument("--order-latency-us", type=float, default=0.0)
    imbalance_replay_walkforward.add_argument("--markout-horizons-ns", nargs="+", default=None, type=int)
    imbalance_replay_walkforward.add_argument("--min-net-pnl", type=float, default=0.0)
    imbalance_replay_walkforward.add_argument("--min-fills", type=int, default=1)
    imbalance_replay_walkforward.add_argument("--max-drawdown", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--max-otr", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--min-markout-mean", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--min-folds", type=int, default=None)
    imbalance_replay_walkforward.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    imbalance_replay_walkforward.add_argument("--min-total-fills", type=int, default=1)
    imbalance_replay_walkforward.add_argument("--min-total-net-pnl", type=float, default=0.0)
    imbalance_replay_walkforward.add_argument("--max-worst-drawdown", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--min-median-markout-mean", type=float, default=None)
    imbalance_replay_walkforward.add_argument("--fail-on-breach", action="store_true")
    _add_generic_cost_args(imbalance_replay_walkforward)

    imbalance_promotion = sub.add_parser("promote-imbalance-candidate", help="Promote a proven imbalance replay walk-forward candidate for paper/shadow launch.")
    imbalance_promotion.add_argument("--walkforward", required=True)
    imbalance_promotion.add_argument("--out", required=True)
    imbalance_promotion.add_argument("--allow-unpassed-walkforward", action="store_true")
    imbalance_promotion.add_argument("--allow-unready-candidate", action="store_true")
    imbalance_promotion.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    imbalance_promotion.add_argument("--min-total-fills", type=int, default=1)
    imbalance_promotion.add_argument("--min-total-net-pnl", type=float, default=0.0)
    imbalance_promotion.add_argument("--max-worst-drawdown", type=float, default=None)
    imbalance_promotion.add_argument("--min-median-markout-mean", type=float, default=None)
    imbalance_promotion.add_argument("--fail-on-breach", action="store_true")

    imbalance_pipeline = sub.add_parser("pipeline-imbalance-research", help="Run edge, replay-proof, and promotion gates for imbalance research.")
    imbalance_pipeline.add_argument("--ticks", nargs="+", required=True)
    imbalance_pipeline.add_argument("--out", required=True)
    imbalance_pipeline.add_argument("--label", action="append", dest="labels")
    imbalance_pipeline.add_argument("--no-filter-session", action="store_true")
    imbalance_pipeline.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    imbalance_pipeline.add_argument("--tick-size", type=float, default=0.05)
    imbalance_pipeline.add_argument("--entry-imbalance", nargs="+", required=True, type=float)
    imbalance_pipeline.add_argument("--min-microprice-edge-ticks", nargs="+", required=True, type=float)
    imbalance_pipeline.add_argument("--forward-horizon-ns", nargs="+", required=True, type=int)
    imbalance_pipeline.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_pipeline.add_argument("--min-depth", type=int, default=1)
    imbalance_pipeline.add_argument("--min-signals", type=int, default=1)
    imbalance_pipeline.add_argument("--min-direction-count", type=int, default=1)
    imbalance_pipeline.add_argument("--min-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-win-rate", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-median-forward-edge-ticks", type=float, default=None)
    imbalance_pipeline.add_argument("--min-passed-configs", type=int, default=1)
    imbalance_pipeline.add_argument("--min-best-usable-signals", type=int, default=1)
    imbalance_pipeline.add_argument("--min-best-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-best-win-rate", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-selection-sweeps", type=int, default=None)
    imbalance_pipeline.add_argument("--min-selection-pass-rate", type=float, default=1.0)
    imbalance_pipeline.add_argument("--min-selection-median-usable-signals", type=float, default=1.0)
    imbalance_pipeline.add_argument("--min-selection-median-mean-forward-edge-ticks", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-selection-min-win-rate", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-selection-median-robust-score", type=float, default=None)
    imbalance_pipeline.add_argument("--min-edge-folds", type=int, default=None)
    imbalance_pipeline.add_argument("--min-passed-edge-sweeps", type=int, default=None)
    imbalance_pipeline.add_argument("--allow-unselected", action="store_true")
    imbalance_pipeline.add_argument("--instrument-id", default="BOOK")
    imbalance_pipeline.add_argument("--instrument-kind", default="OPT", choices=["FUT", "OPT", "EQ"])
    imbalance_pipeline.add_argument("--lot-size", type=int, default=75)
    imbalance_pipeline.add_argument("--qty", type=int, default=75)
    imbalance_pipeline.add_argument("--exit-imbalance", type=float, default=0.15)
    imbalance_pipeline.add_argument("--cooloff-ns", type=int, default=0)
    imbalance_pipeline.add_argument("--feed-latency-us", type=float, default=0.0)
    imbalance_pipeline.add_argument("--order-latency-us", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-net-pnl", type=float, default=0.0)
    imbalance_pipeline.add_argument("--min-fills", type=int, default=1)
    imbalance_pipeline.add_argument("--max-drawdown", type=float, default=None)
    imbalance_pipeline.add_argument("--max-otr", type=float, default=None)
    imbalance_pipeline.add_argument("--min-markout-mean", type=float, default=None)
    imbalance_pipeline.add_argument("--min-replay-folds", type=int, default=None)
    imbalance_pipeline.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    imbalance_pipeline.add_argument("--min-total-fills", type=int, default=1)
    imbalance_pipeline.add_argument("--min-total-net-pnl", type=float, default=0.0)
    imbalance_pipeline.add_argument("--max-worst-drawdown", type=float, default=None)
    imbalance_pipeline.add_argument("--min-median-markout-mean", type=float, default=None)
    imbalance_pipeline.add_argument("--fail-on-breach", action="store_true")
    _add_generic_cost_args(imbalance_pipeline)

    settlement = sub.add_parser("audit-settlement-convergence", help="Audit expiry settlement-window option convergence opportunities.")
    settlement.add_argument("--index-ticks", required=True)
    settlement.add_argument("--chain", required=True)
    settlement.add_argument("--out", required=True)
    settlement.add_argument("--window-start-ns", type=int, required=True)
    settlement.add_argument("--window-end-ns", type=int, required=True)
    settlement.add_argument("--index-price-col", default=None)
    settlement.add_argument("--lot-size", type=int, default=75)
    settlement.add_argument("--tick-size", type=float, default=0.05)
    settlement.add_argument("--qty", type=int, default=75)
    settlement.add_argument("--depth-fraction", type=float, default=1.0)
    settlement.add_argument("--min-known-fraction", type=float, default=0.0)
    settlement.add_argument("--min-gross-edge-ticks", type=float, default=0.0)
    settlement.add_argument("--min-net-edge", type=float, default=0.0)
    settlement.add_argument("--min-opportunities", type=int, default=1)
    settlement.add_argument("--min-total-net-edge", type=float, default=0.0)
    settlement.add_argument("--min-best-net-edge", type=float, default=0.0)
    settlement.add_argument("--min-median-known-fraction", type=float, default=0.0)
    settlement.add_argument("--min-direction-count", type=int, default=1)
    settlement.add_argument("--fail-on-breach", action="store_true")

    settlement_walkforward = sub.add_parser("walkforward-settlement-convergence", help="Run settlement convergence audits across expiry folds.")
    settlement_walkforward.add_argument("--index-ticks", nargs="+", required=True)
    settlement_walkforward.add_argument("--chains", nargs="+", required=True)
    settlement_walkforward.add_argument("--out", required=True)
    settlement_walkforward.add_argument("--label", action="append", dest="labels")
    settlement_walkforward.add_argument("--window-start-ns", nargs="+", type=int, required=True)
    settlement_walkforward.add_argument("--window-end-ns", nargs="+", type=int, required=True)
    settlement_walkforward.add_argument("--index-price-col", default=None)
    settlement_walkforward.add_argument("--lot-size", type=int, default=75)
    settlement_walkforward.add_argument("--tick-size", type=float, default=0.05)
    settlement_walkforward.add_argument("--qty", type=int, default=75)
    settlement_walkforward.add_argument("--depth-fraction", type=float, default=1.0)
    settlement_walkforward.add_argument("--min-known-fraction", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-gross-edge-ticks", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-net-edge", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-fold-opportunities", type=int, default=1)
    settlement_walkforward.add_argument("--min-fold-total-net-edge", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-fold-best-net-edge", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-fold-median-known-fraction", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-fold-direction-count", type=int, default=1)
    settlement_walkforward.add_argument("--min-folds", type=int, default=None)
    settlement_walkforward.add_argument("--min-pass-rate", type=float, default=1.0)
    settlement_walkforward.add_argument("--min-total-opportunities", type=int, default=1)
    settlement_walkforward.add_argument("--min-total-net-edge", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-median-best-net-edge", type=float, default=0.0)
    settlement_walkforward.add_argument("--min-median-known-fraction", type=float, default=0.0)
    settlement_walkforward.add_argument("--fail-on-breach", action="store_true")

    settlement_promotion = sub.add_parser("promote-settlement-candidate", help="Promote a proven settlement convergence walk-forward candidate.")
    settlement_promotion.add_argument("--walkforward", required=True)
    settlement_promotion.add_argument("--out", required=True)
    settlement_promotion.add_argument("--allow-unpassed-walkforward", action="store_true")
    settlement_promotion.add_argument("--allow-unready-candidate", action="store_true")
    settlement_promotion.add_argument("--min-pass-rate", type=float, default=1.0)
    settlement_promotion.add_argument("--min-total-opportunities", type=int, default=1)
    settlement_promotion.add_argument("--min-total-net-edge", type=float, default=0.0)
    settlement_promotion.add_argument("--min-median-best-net-edge", type=float, default=0.0)
    settlement_promotion.add_argument("--min-median-known-fraction", type=float, default=0.0)
    settlement_promotion.add_argument("--fail-on-breach", action="store_true")

    settlement_orders = sub.add_parser(
        "plan-settlement-orders",
        help="Create broker-neutral order candidates from a promoted settlement convergence candidate.",
    )
    settlement_orders.add_argument("--promotion", required=True)
    settlement_orders.add_argument("--out", required=True)
    settlement_orders.add_argument("--symbol-prefix", default="NIFTY")
    settlement_orders.add_argument("--qty", type=int, default=None)
    settlement_orders.add_argument("--price-offset-ticks", type=float, default=0.0)
    settlement_orders.add_argument("--tick-size", type=float, default=0.05)
    settlement_orders.add_argument("--output-file", default="settlement_order_candidates.csv")
    settlement_orders.add_argument("--allow-unready-promotion", action="store_true")
    settlement_orders.add_argument("--fail-on-breach", action="store_true")

    settlement_pipeline = sub.add_parser(
        "pipeline-settlement-launch",
        help="Run promoted settlement candidate through order plan, staging, launch, export, and upload pack.",
    )
    settlement_pipeline.add_argument("--promotion", required=True)
    settlement_pipeline.add_argument("--out", required=True)
    settlement_pipeline.add_argument("--adapter", default="arrow_money")
    settlement_pipeline.add_argument("--mode", default="shadow", choices=["paper", "shadow"])
    settlement_pipeline.add_argument("--route-tag", default=None)
    settlement_pipeline.add_argument("--symbol-prefix", default="NIFTY")
    settlement_pipeline.add_argument("--qty", type=int, default=None)
    settlement_pipeline.add_argument("--price-offset-ticks", type=float, default=0.0)
    settlement_pipeline.add_argument("--tick-size", type=float, default=0.05)
    settlement_pipeline.add_argument("--max-order-qty", type=int, default=None)
    settlement_pipeline.add_argument("--max-notional", type=float, default=None)
    settlement_pipeline.add_argument("--price-band-pct", type=float, default=None)
    settlement_pipeline.add_argument("--max-orders", type=int, default=None)
    settlement_pipeline.add_argument("--contract-multiplier", type=float, default=1.0)
    settlement_pipeline.add_argument("--product", default="MIS")
    settlement_pipeline.add_argument("--exchange", default="NFO")
    settlement_pipeline.add_argument("--allow-placeholder-schema", action="store_true")
    settlement_pipeline.add_argument("--fail-on-breach", action="store_true")

    calibration = sub.add_parser("calibrate", help="Compare simulated orders to live fills.")
    calibration.add_argument("--simulated-orders", required=True)
    calibration.add_argument("--live-fills", required=True)
    calibration.add_argument("--out", required=True)
    calibration.add_argument("--adapter", default="normalized")

    fill_model = sub.add_parser("calibrate-fill-model", help="Recommend fill-model assumptions from reconciliation evidence.")
    fill_model.add_argument("--reconciliation", required=True)
    fill_model.add_argument("--out", required=True)
    fill_model.add_argument("--tick-size", type=float, default=0.05)
    fill_model.add_argument("--min-orders", type=int, default=1)
    fill_model.add_argument("--min-live-fill-rate", type=float, default=0.0)
    fill_model.add_argument("--max-mismatch-rate", type=float, default=0.0)
    fill_model.add_argument("--max-overfill-rate", type=float, default=0.0)
    fill_model.add_argument("--max-unmatched-fills", type=int, default=0)
    fill_model.add_argument("--max-adverse-slippage-ticks", type=float, default=None)
    fill_model.add_argument("--latency-quantile", type=float, default=0.95)
    fill_model.add_argument("--fill-ratio-quantile", type=float, default=0.25)
    fill_model.add_argument("--slippage-quantile", type=float, default=0.95)
    fill_model.add_argument("--min-queue-conservatism", type=float, default=1.0)
    fill_model.add_argument("--max-queue-conservatism", type=float, default=10.0)
    fill_model.add_argument("--base-edge-ticks", type=float, default=0.0)
    fill_model.add_argument("--fail-on-breach", action="store_true")

    fill_model_drift = sub.add_parser("compare-fill-models", help="Gate drift between two fill-model configs.")
    fill_model_drift.add_argument("--baseline", required=True)
    fill_model_drift.add_argument("--latest", required=True)
    fill_model_drift.add_argument("--out", required=True)
    fill_model_drift.add_argument("--allow-unready-baseline", action="store_true")
    fill_model_drift.add_argument("--allow-unready-latest", action="store_true")
    fill_model_drift.add_argument("--require-same-instruments", action="store_true")
    fill_model_drift.add_argument("--max-queue-conservatism-increase-pct", type=float, default=0.25)
    fill_model_drift.add_argument("--max-order-latency-increase-us", type=float, default=100.0)
    fill_model_drift.add_argument("--max-slippage-tick-increase", type=float, default=1.0)
    fill_model_drift.add_argument("--max-min-edge-tick-increase", type=float, default=1.0)
    fill_model_drift.add_argument("--fail-on-breach", action="store_true")

    calibrated_replay = sub.add_parser("plan-calibrated-replay", help="Apply fill-model config to replay parameters.")
    calibrated_replay.add_argument("--fill-model", required=True)
    calibrated_replay.add_argument("--strategy", required=True, choices=["leadlag", "parity", "surface_mm", "surface_quotes", "imbalance"])
    calibrated_replay.add_argument("--out", required=True)
    calibrated_replay.add_argument("--order-latency-us", type=float, default=None)
    calibrated_replay.add_argument("--trigger-ticks", type=float, default=None)
    calibrated_replay.add_argument("--depth-fraction", type=float, default=None)
    calibrated_replay.add_argument("--fill-depth-fraction", type=float, default=None)
    calibrated_replay.add_argument("--edge-ticks", type=float, default=None)
    calibrated_replay.add_argument("--allow-unready-fill-model", action="store_true")
    calibrated_replay.add_argument("--fail-on-breach", action="store_true")

    proof_refresh = sub.add_parser("review-proof-refresh", help="Gate whether proof can be reused after fill-model drift.")
    proof_refresh.add_argument("--drift", required=True)
    proof_refresh.add_argument("--baseline-proof", required=True)
    proof_refresh.add_argument("--latest-proof", default=None)
    proof_refresh.add_argument("--calibrated-replay", default=None)
    proof_refresh.add_argument("--out", required=True)
    proof_refresh.add_argument("--strategy", default=None)
    proof_refresh.add_argument("--require-calibrated-replay", action="store_true")
    proof_refresh.add_argument("--fail-on-breach", action="store_true")

    schema_audit = sub.add_parser("audit-adapter-schema", help="Audit a vendor sample CSV against an adapter schema.")
    schema_audit.add_argument("--sample", required=True)
    schema_audit.add_argument("--out", required=True)
    schema_audit.add_argument("--adapter", default="normalized")
    schema_audit.add_argument("--kind", default="ticks")
    schema_audit.add_argument("--fail-on-missing", action="store_true")

    mapped_data = sub.add_parser("normalize-mapped-data", help="Normalize vendor CSV data using a reviewed adapter mapping.")
    mapped_data.add_argument("--input", required=True)
    mapped_data.add_argument("--mapping", required=True)
    mapped_data.add_argument("--out", required=True)
    mapped_data.add_argument("--adapter", default="normalized")
    mapped_data.add_argument("--kind", default="ticks")
    mapped_data.add_argument("--output-file", default="normalized_data.csv")
    mapped_data.add_argument("--timestamp-unit", default="ns")
    mapped_data.add_argument("--timestamp-tz", default=None)
    mapped_data.add_argument("--market", default="india_nse_index_derivatives")
    mapped_data.add_argument("--no-filter-session", action="store_true")
    mapped_data.add_argument("--allow-missing-required", action="store_true")
    mapped_data.add_argument("--fail-on-breach", action="store_true")

    diag_ticks = sub.add_parser("diagnose-ticks", help="Run data-quality diagnostics for top-of-book ticks.")
    diag_ticks.add_argument("--ticks", required=True)
    diag_ticks.add_argument("--out", required=True)
    diag_ticks.add_argument("--tick-size", type=float, default=None)
    diag_ticks.add_argument("--market", default="india_nse_index_derivatives")
    diag_ticks.add_argument("--no-filter-session", action="store_true")

    diag_chain = sub.add_parser("diagnose-chain", help="Run data-quality diagnostics for option-chain snapshots.")
    diag_chain.add_argument("--chain", required=True)
    diag_chain.add_argument("--out", required=True)
    diag_chain.add_argument("--tick-size", type=float, default=None)
    diag_chain.add_argument("--market", default="india_nse_index_derivatives")
    diag_chain.add_argument("--no-filter-session", action="store_true")

    instrument_metadata = sub.add_parser(
        "instrument-metadata-report",
        help="Parse and audit option instrument metadata coverage in a CSV file.",
    )
    instrument_metadata.add_argument("--input", required=True)
    instrument_metadata.add_argument("--out", required=True)
    instrument_metadata.add_argument("--instrument-column", default="instrument_id")
    instrument_metadata.add_argument("--min-parse-coverage", type=float, default=1.0)
    instrument_metadata.add_argument("--fail-on-unparsed", action="store_true")

    market_profile = sub.add_parser("market-profile-report", help="Export market/session/cost assumptions.")
    market_profile.add_argument("--out", required=True)
    market_profile.add_argument("--market", action="append", dest="markets")
    market_profile.add_argument("--price", type=float, default=None)
    market_profile.add_argument("--qty", type=int, default=None)
    market_profile.add_argument("--buy-notional-rate", type=float, default=0.0)
    market_profile.add_argument("--sell-notional-rate", type=float, default=0.0)
    market_profile.add_argument("--per-unit-fee", type=float, default=0.0)
    market_profile.add_argument("--per-contract-fee", type=float, default=0.0)
    market_profile.add_argument("--per-order-fee", type=float, default=0.0)

    portability = sub.add_parser(
        "market-portability-report",
        help="Export strategy portability across market profiles.",
    )
    portability.add_argument("--out", required=True)
    portability.add_argument("--market", action="append", dest="markets")
    portability.add_argument("--strategy", action="append", dest="strategies")
    portability.add_argument("--explicit-fee-model", action="store_true")

    proof = sub.add_parser("proof-report", help="Evaluate replay output folders against proof thresholds.")
    proof.add_argument("--runs", nargs="+", required=True)
    proof.add_argument("--out", required=True)
    proof.add_argument("--run-name", action="append", dest="run_names")
    proof.add_argument("--min-net-pnl", type=float, default=0.0)
    proof.add_argument("--min-fills", type=int, default=1)
    proof.add_argument("--max-drawdown", type=float, default=None)
    proof.add_argument("--max-otr", type=float, default=None)
    proof.add_argument("--min-maker-share", type=float, default=None)
    proof.add_argument("--min-worst-regime-equity-change", type=float, default=None)
    proof.add_argument("--min-markout-mean", type=float, default=None)
    proof.add_argument("--min-spread-net", type=float, default=None)
    proof.add_argument("--fail-on-breach", action="store_true")

    catalog = sub.add_parser("catalog-runs", help="Build an experiment catalog from manifest-bearing run folders.")
    catalog.add_argument("--roots", nargs="+", required=True)
    catalog.add_argument("--out", required=True)

    evidence = sub.add_parser("review-strategy-evidence", help="Gate strategy evidence from an experiment catalog.")
    evidence.add_argument("--catalog", required=True)
    evidence.add_argument("--out", required=True)
    evidence.add_argument("--required-run-type", action="append", dest="required_run_types")
    evidence.add_argument("--min-passed-per-type", type=int, default=1)
    evidence.add_argument("--allow-dirty-git", action="store_true")
    evidence.add_argument("--require-same-git-commit", action="store_true")
    evidence.add_argument("--fail-on-breach", action="store_true")

    leadlag_sweep = sub.add_parser("sweep-leadlag", help="Run lead-lag replay robustness sweep.")
    leadlag_sweep.add_argument("--leader", required=True)
    leadlag_sweep.add_argument("--laggard", required=True)
    leadlag_sweep.add_argument("--out", required=True)
    leadlag_sweep.add_argument("--no-filter-session", action="store_true")
    leadlag_sweep.add_argument("--leader-tick", type=float, default=0.05)
    leadlag_sweep.add_argument("--laggard-tick", type=float, default=0.05)
    leadlag_sweep.add_argument("--delta", type=float, default=1.0)
    leadlag_sweep.add_argument("--trigger-ticks", nargs="+", required=True, type=float)
    leadlag_sweep.add_argument("--feed-latency-us", nargs="+", default=[0.0], type=float)
    leadlag_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    leadlag_sweep.add_argument("--qty", type=int, default=75)
    leadlag_sweep.add_argument("--flat-after-ns", type=int, default=500_000_000)
    leadlag_sweep.add_argument("--cooloff-ns", type=int, default=0)
    leadlag_sweep.add_argument("--markout-horizons-ns", nargs="+", default=None, type=int)
    leadlag_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    leadlag_sweep.add_argument("--min-fills", type=int, default=1)
    leadlag_sweep.add_argument("--max-drawdown", type=float, default=None)
    leadlag_sweep.add_argument("--max-otr", type=float, default=None)
    leadlag_sweep.add_argument("--min-markout-mean", type=float, default=None)
    leadlag_sweep.add_argument("--fail-on-breach", action="store_true")

    imbalance_sweep = sub.add_parser("sweep-imbalance", help="Run microprice imbalance replay robustness sweep.")
    imbalance_sweep.add_argument("--ticks", required=True)
    imbalance_sweep.add_argument("--out", required=True)
    imbalance_sweep.add_argument("--no-filter-session", action="store_true")
    imbalance_sweep.add_argument("--market", default=None)
    imbalance_sweep.add_argument("--instrument-id", default="BOOK")
    imbalance_sweep.add_argument("--instrument-kind", default="OPT", choices=["FUT", "OPT", "EQ"])
    imbalance_sweep.add_argument("--lot-size", type=int, default=75)
    imbalance_sweep.add_argument("--tick-size", type=float, default=None)
    imbalance_sweep.add_argument("--qty", type=int, default=75)
    imbalance_sweep.add_argument("--entry-imbalance", nargs="+", default=None, type=float)
    imbalance_sweep.add_argument("--exit-imbalance", type=float, default=0.15)
    imbalance_sweep.add_argument("--min-microprice-edge-ticks", nargs="+", default=None, type=float)
    imbalance_sweep.add_argument("--max-spread-ticks", type=float, default=2.0)
    imbalance_sweep.add_argument("--min-depth", type=int, default=1)
    imbalance_sweep.add_argument("--hold-ns", nargs="+", default=None, type=int)
    imbalance_sweep.add_argument("--cooloff-ns", type=int, default=0)
    imbalance_sweep.add_argument("--feed-latency-us", nargs="+", default=[0.0], type=float)
    imbalance_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    imbalance_sweep.add_argument("--markout-horizons-ns", nargs="+", default=None, type=int)
    imbalance_sweep.add_argument("--candidate-config", default=None)
    imbalance_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    imbalance_sweep.add_argument("--min-fills", type=int, default=1)
    imbalance_sweep.add_argument("--max-drawdown", type=float, default=None)
    imbalance_sweep.add_argument("--max-otr", type=float, default=None)
    imbalance_sweep.add_argument("--min-markout-mean", type=float, default=None)
    imbalance_sweep.add_argument("--fail-on-breach", action="store_true")
    _add_generic_cost_args(imbalance_sweep)

    parity_sweep = sub.add_parser("sweep-parity", help="Run parity replay robustness sweep.")
    parity_sweep.add_argument("--chain", required=True)
    parity_sweep.add_argument("--futures", required=True)
    parity_sweep.add_argument("--out", required=True)
    parity_sweep.add_argument("--no-filter-session", action="store_true")
    parity_sweep.add_argument("--depth-fraction", nargs="+", required=True, type=float)
    parity_sweep.add_argument("--asof-latency-ns", nargs="+", default=[0], type=int)
    parity_sweep.add_argument("--feed-latency-us", nargs="+", default=[0.0], type=float)
    parity_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    parity_sweep.add_argument("--signal-limit", type=int, default=None)
    parity_sweep.add_argument("--max-signal-age-ns", type=int, default=1_000_000)
    parity_sweep.add_argument("--max-qty", type=int, default=None)
    parity_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    parity_sweep.add_argument("--min-fills", type=int, default=1)
    parity_sweep.add_argument("--max-drawdown", type=float, default=None)
    parity_sweep.add_argument("--max-otr", type=float, default=None)
    parity_sweep.add_argument("--min-spread-net", type=float, default=None)
    parity_sweep.add_argument("--fail-on-breach", action="store_true")

    surface_mm_sweep = sub.add_parser("sweep-surface-mm", help="Run surface MM replay robustness sweep.")
    surface_mm_sweep.add_argument("--quotes", required=True)
    surface_mm_sweep.add_argument("--chain", required=True)
    surface_mm_sweep.add_argument("--out", required=True)
    surface_mm_sweep.add_argument("--no-filter-session", action="store_true")
    surface_mm_sweep.add_argument("--quote-ttl-ns", nargs="+", required=True, type=int)
    surface_mm_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    surface_mm_sweep.add_argument("--fill-depth-fraction", nargs="+", required=True, type=float)
    surface_mm_sweep.add_argument("--markout-horizon-ns", nargs="+", default=[1_000_000_000], type=int)
    surface_mm_sweep.add_argument("--lot-size", type=int, default=75)
    surface_mm_sweep.add_argument("--option-tick", type=float, default=0.05)
    surface_mm_sweep.add_argument("--contract-multiplier", type=float, default=1.0)
    surface_mm_sweep.add_argument("--max-quotes", type=int, default=None)
    surface_mm_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    surface_mm_sweep.add_argument("--min-fills", type=int, default=1)
    surface_mm_sweep.add_argument("--max-drawdown", type=float, default=None)
    surface_mm_sweep.add_argument("--max-otr", type=float, default=None)
    surface_mm_sweep.add_argument("--min-maker-share", type=float, default=1.0)
    surface_mm_sweep.add_argument("--min-markout-mean", type=float, default=None)
    surface_mm_sweep.add_argument("--fail-on-breach", action="store_true")

    compare_sweeps = sub.add_parser("compare-sweeps", help="Rank scenarios across multiple sweep outputs.")
    compare_sweeps.add_argument("--sweeps", nargs="+", required=True)
    compare_sweeps.add_argument("--out", required=True)
    compare_sweeps.add_argument("--label", action="append", dest="labels")
    compare_sweeps.add_argument("--group-cols", nargs="+", default=None)
    compare_sweeps.add_argument("--min-pass-rate", type=float, default=1.0)
    compare_sweeps.add_argument("--min-sweeps", type=int, default=1)
    compare_sweeps.add_argument("--min-median-net-pnl", type=float, default=0.0)
    compare_sweeps.add_argument("--max-worst-drawdown", type=float, default=None)
    compare_sweeps.add_argument("--fail-on-breach", action="store_true")

    promote = sub.add_parser("promote-scenario", help="Gate a sweep selection for paper/shadow promotion.")
    promote.add_argument("--selection", required=True)
    promote.add_argument("--out", required=True)
    promote.add_argument("--min-pass-rate", type=float, default=1.0)
    promote.add_argument("--min-sweeps", type=int, default=1)
    promote.add_argument("--min-median-net-pnl", type=float, default=0.0)
    promote.add_argument("--min-min-net-pnl", type=float, default=None)
    promote.add_argument("--max-worst-drawdown", type=float, default=None)
    promote.add_argument("--min-median-fills", type=float, default=1.0)
    promote.add_argument("--max-runs-with-losing-regimes", type=int, default=None)
    promote.add_argument("--max-otr", type=float, default=None)
    promote.add_argument("--min-maker-share", type=float, default=None)
    promote.add_argument("--min-markout-mean", type=float, default=None)
    promote.add_argument("--fail-on-breach", action="store_true")

    launch = sub.add_parser("launch-bundle", help="Package promoted strategy and staged orders for paper/shadow launch.")
    launch.add_argument("--promotion", required=True)
    launch.add_argument("--staged-orders", required=True)
    launch.add_argument("--out", required=True)
    launch.add_argument("--mode", default="paper", choices=["paper", "shadow"])
    launch.add_argument("--adapter", default="normalized")
    launch.add_argument("--min-accepted-orders", type=int, default=1)
    launch.add_argument("--min-acceptance-rate", type=float, default=1.0)
    launch.add_argument("--allow-unready-promotion", action="store_true")
    launch.add_argument("--allow-rejections", action="store_true")
    launch.add_argument("--max-total-notional", type=float, default=None)
    launch.add_argument("--max-order-notional", type=float, default=None)
    launch.add_argument("--fail-on-breach", action="store_true")

    export_orders = sub.add_parser("export-launch-orders", help="Export launch orders for broker/paper adapters.")
    export_orders.add_argument("--launch", required=True)
    export_orders.add_argument("--out", required=True)
    export_orders.add_argument("--adapter", default="normalized")
    export_orders.add_argument("--route-tag", default=None)
    export_orders.add_argument("--allow-unready-launch", action="store_true")
    export_orders.add_argument("--allow-non-limit", action="store_true")
    export_orders.add_argument("--max-orders", type=int, default=None)
    export_orders.add_argument("--fail-on-breach", action="store_true")

    upload_pack = sub.add_parser(
        "pack-broker-upload",
        help="Create a broker upload review pack from exported broker-neutral orders.",
    )
    upload_pack.add_argument("--export", required=True)
    upload_pack.add_argument("--out", required=True)
    upload_pack.add_argument("--adapter", default="arrow_money")
    upload_pack.add_argument("--product", default="MIS")
    upload_pack.add_argument("--exchange", default="NFO")
    upload_pack.add_argument("--output-file", default="broker_upload_orders.csv")
    upload_pack.add_argument("--mapping-file", default="broker_upload_mapping.csv")
    upload_pack.add_argument("--allow-placeholder-schema", action="store_true")
    upload_pack.add_argument("--fail-on-breach", action="store_true")

    mapping_draft = sub.add_parser("draft-order-mapping", help="Draft a vendor order mapping from broker orders and a sample upload header.")
    mapping_draft.add_argument("--export", required=True)
    mapping_draft.add_argument("--sample", required=True)
    mapping_draft.add_argument("--out", required=True)
    mapping_draft.add_argument("--adapter", default="normalized")
    mapping_draft.add_argument("--output-file", default="order_mapping_draft.csv")
    mapping_draft.add_argument("--required-column", action="append", dest="required_columns")
    mapping_draft.add_argument("--optional-column", action="append", dest="optional_columns")
    mapping_draft.add_argument("--default", action="append", dest="defaults")
    mapping_draft.add_argument("--fail-on-unmapped", action="store_true")

    mapped_export = sub.add_parser("map-broker-orders", help="Map broker-neutral orders into a vendor CSV shape.")
    mapped_export.add_argument("--export", required=True)
    mapped_export.add_argument("--mapping", required=True)
    mapped_export.add_argument("--out", required=True)
    mapped_export.add_argument("--adapter", default="normalized")
    mapped_export.add_argument("--output-file", default="mapped_broker_orders.csv")
    mapped_export.add_argument("--allow-missing-required", action="store_true")
    mapped_export.add_argument("--fail-on-breach", action="store_true")

    reconcile = sub.add_parser("reconcile-broker-fills", help="Reconcile exported orders against broker/drop-copy fills.")
    reconcile.add_argument("--export", required=True)
    reconcile.add_argument("--fills", required=True)
    reconcile.add_argument("--out", required=True)
    reconcile.add_argument("--adapter", default="normalized")
    reconcile.add_argument("--min-order-fill-rate", type=float, default=0.0)
    reconcile.add_argument("--max-unfilled-orders", type=int, default=None)
    reconcile.add_argument("--max-partial-orders", type=int, default=None)
    reconcile.add_argument("--max-overfilled-orders", type=int, default=0)
    reconcile.add_argument("--max-mismatched-orders", type=int, default=0)
    reconcile.add_argument("--max-unmatched-fills", type=int, default=0)
    reconcile.add_argument("--max-adverse-slippage", type=float, default=None)
    reconcile.add_argument("--fail-on-breach", action="store_true")

    shadow_session = sub.add_parser("shadow-session-report", help="Gate a full paper/shadow session after reconciliation.")
    shadow_session.add_argument("--launch", required=True)
    shadow_session.add_argument("--export", required=True)
    shadow_session.add_argument("--reconciliation", required=True)
    shadow_session.add_argument("--out", required=True)
    shadow_session.add_argument("--allow-unready-launch", action="store_true")
    shadow_session.add_argument("--allow-unready-export", action="store_true")
    shadow_session.add_argument("--allow-failed-reconciliation", action="store_true")
    shadow_session.add_argument("--max-failed-component-checks", type=int, default=0)
    shadow_session.add_argument("--min-order-fill-rate", type=float, default=0.0)
    shadow_session.add_argument("--max-unmatched-fills", type=int, default=0)
    shadow_session.add_argument("--max-mismatched-orders", type=int, default=0)
    shadow_session.add_argument("--max-overfilled-orders", type=int, default=0)
    shadow_session.add_argument("--max-unfilled-orders", type=int, default=None)
    shadow_session.add_argument("--max-adverse-slippage", type=float, default=None)
    shadow_session.add_argument("--fail-on-breach", action="store_true")

    shadow_compare = sub.add_parser("compare-shadow-sessions", help="Compare multiple paper/shadow session reports.")
    shadow_compare.add_argument("--sessions", nargs="+", required=True)
    shadow_compare.add_argument("--out", required=True)
    shadow_compare.add_argument("--label", action="append", dest="labels")
    shadow_compare.add_argument("--min-sessions", type=int, default=1)
    shadow_compare.add_argument("--min-acceptance-rate", type=float, default=1.0)
    shadow_compare.add_argument("--allow-mixed-scenarios", action="store_true")
    shadow_compare.add_argument("--min-median-order-fill-rate", type=float, default=0.0)
    shadow_compare.add_argument("--min-worst-order-fill-rate", type=float, default=None)
    shadow_compare.add_argument("--max-total-failed-component-checks", type=int, default=0)
    shadow_compare.add_argument("--max-total-unmatched-fills", type=int, default=0)
    shadow_compare.add_argument("--max-total-mismatched-orders", type=int, default=0)
    shadow_compare.add_argument("--max-total-overfilled-orders", type=int, default=0)
    shadow_compare.add_argument("--max-worst-adverse-slippage", type=float, default=None)
    shadow_compare.add_argument("--fail-on-breach", action="store_true")

    scaleup = sub.add_parser("plan-scaleup", help="Create a controlled paper/shadow scale-up plan.")
    scaleup.add_argument("--evidence", required=True)
    scaleup.add_argument("--shadow-comparison", required=True)
    scaleup.add_argument("--launch", required=True)
    scaleup.add_argument("--out", required=True)
    scaleup.add_argument("--order-exposure", default=None)
    scaleup.add_argument("--proof-refresh", default=None)
    scaleup.add_argument("--instrument-metadata", default=None)
    scaleup.add_argument("--target-mode", default="shadow", choices=["paper", "shadow", "live_dryrun"])
    scaleup.add_argument("--max-scale-multiplier", type=float, default=1.0)
    scaleup.add_argument("--min-shadow-sessions", type=int, default=1)
    scaleup.add_argument("--min-shadow-acceptance-rate", type=float, default=1.0)
    scaleup.add_argument("--min-median-order-fill-rate", type=float, default=0.0)
    scaleup.add_argument("--min-worst-order-fill-rate", type=float, default=None)
    scaleup.add_argument("--max-worst-adverse-slippage", type=float, default=None)
    scaleup.add_argument("--max-total-failed-component-checks", type=int, default=0)
    scaleup.add_argument("--max-total-unmatched-fills", type=int, default=0)
    scaleup.add_argument("--max-total-mismatched-orders", type=int, default=0)
    scaleup.add_argument("--max-total-overfilled-orders", type=int, default=0)
    scaleup.add_argument("--max-orders-per-session", type=int, default=None)
    scaleup.add_argument("--max-session-notional", type=float, default=None)
    scaleup.add_argument("--max-gross-notional", type=float, default=None)
    scaleup.add_argument("--max-abs-net-delta", type=float, default=None)
    scaleup.add_argument("--max-abs-net-vega", type=float, default=None)
    scaleup.add_argument("--stop-loss", type=float, default=None)
    scaleup.add_argument("--allowed-adapter", action="append", dest="allowed_adapters")
    scaleup.add_argument("--require-proof-refresh", action="store_true")
    scaleup.add_argument("--require-instrument-metadata", action="store_true")
    scaleup.add_argument("--min-instrument-parse-coverage", type=float, default=1.0)
    scaleup.add_argument("--fail-on-breach", action="store_true")

    runtime_telemetry = sub.add_parser("build-runtime-telemetry", help="Build a guard-ready runtime telemetry snapshot.")
    runtime_telemetry.add_argument("--scaleup", required=True)
    runtime_telemetry.add_argument("--out", required=True)
    runtime_telemetry.add_argument("--export", default=None)
    runtime_telemetry.add_argument("--reconciliation", default=None)
    runtime_telemetry.add_argument("--instrument-metadata", default=None)
    runtime_telemetry.add_argument("--pnl", default=None)
    runtime_telemetry.add_argument("--open-orders", default=None)
    runtime_telemetry.add_argument("--positions", default=None)
    runtime_telemetry.add_argument("--snapshot-ts-ns", type=float, default=None)
    runtime_telemetry.add_argument("--fail-on-breach", action="store_true")

    runtime_guard = sub.add_parser("monitor-scaleup-guard", help="Evaluate runtime telemetry against scale-up guardrails.")
    runtime_guard.add_argument("--scaleup", required=True)
    runtime_guard.add_argument("--telemetry", required=True)
    runtime_guard.add_argument("--out", required=True)
    runtime_guard.add_argument("--fail-on-halt", action="store_true")

    halt_response = sub.add_parser("plan-halt-response", help="Create cancel/flatten actions after a guard halt.")
    halt_response.add_argument("--guard", required=True)
    halt_response.add_argument("--out", required=True)
    halt_response.add_argument("--open-orders", default=None)
    halt_response.add_argument("--positions", default=None)
    halt_response.add_argument("--allow-continue-guard", action="store_true")
    halt_response.add_argument("--allow-missing-flatten-prices", action="store_true")
    halt_response.add_argument("--default-order-type", default="LIMIT")
    halt_response.add_argument("--default-time-in-force", default="DAY")
    halt_response.add_argument("--fail-on-breach", action="store_true")

    halt_export = sub.add_parser("export-halt-response", help="Map halt response actions into broker files.")
    halt_export.add_argument("--halt-response", required=True)
    halt_export.add_argument("--out", required=True)
    halt_export.add_argument("--adapter", default="normalized")
    halt_export.add_argument("--cancel-mapping", default=None)
    halt_export.add_argument("--flatten-mapping", default=None)
    halt_export.add_argument("--cancel-output-file", default="broker_cancel_orders.csv")
    halt_export.add_argument("--flatten-output-file", default="broker_flatten_orders.csv")
    halt_export.add_argument("--allow-unready-response", action="store_true")
    halt_export.add_argument("--allow-missing-required", action="store_true")
    halt_export.add_argument("--fail-on-breach", action="store_true")

    halt_execution = sub.add_parser("reconcile-halt-execution", help="Verify emergency cancel/flatten execution.")
    halt_execution.add_argument("--halt-response", required=True)
    halt_execution.add_argument("--out", required=True)
    halt_execution.add_argument("--cancel-acks", default=None)
    halt_execution.add_argument("--flatten-fills", default=None)
    halt_execution.add_argument("--positions", default=None)
    halt_execution.add_argument("--allow-unready-response", action="store_true")
    halt_execution.add_argument("--allow-missing-cancel-acks", action="store_true")
    halt_execution.add_argument("--allow-incomplete-flatten-fills", action="store_true")
    halt_execution.add_argument("--allow-missing-final-positions", action="store_true")
    halt_execution.add_argument("--position-tolerance", type=float, default=0.0)
    halt_execution.add_argument("--fail-on-breach", action="store_true")

    halt_incident = sub.add_parser("review-halt-incident", help="Summarize guard, response, export, and execution evidence.")
    halt_incident.add_argument("--guard", required=True)
    halt_incident.add_argument("--halt-response", required=True)
    halt_incident.add_argument("--halt-execution", required=True)
    halt_incident.add_argument("--out", required=True)
    halt_incident.add_argument("--halt-export", default=None)
    halt_incident.add_argument("--allow-continue-guard", action="store_true")
    halt_incident.add_argument("--allow-unready-response", action="store_true")
    halt_incident.add_argument("--require-export", action="store_true")
    halt_incident.add_argument("--allow-incomplete-execution", action="store_true")
    halt_incident.add_argument("--fail-on-breach", action="store_true")

    resume_gate = sub.add_parser("review-resume-gate", help="Authorize post-halt resume against a fresh scale-up plan.")
    resume_gate.add_argument("--incident", required=True)
    resume_gate.add_argument("--scaleup", required=True)
    resume_gate.add_argument("--out", required=True)
    resume_gate.add_argument("--operator-review", default=None)
    resume_gate.add_argument("--allow-open-incident", action="store_true")
    resume_gate.add_argument("--allow-unready-scaleup", action="store_true")
    resume_gate.add_argument("--allow-scenario-change", action="store_true")
    resume_gate.add_argument("--allow-adapter-change", action="store_true")
    resume_gate.add_argument("--require-operator-approval", action="store_true")
    resume_gate.add_argument("--max-failed-scaleup-checks", type=int, default=0)
    resume_gate.add_argument("--fail-on-breach", action="store_true")

    stress = sub.add_parser("stress-replay", help="Stress replay outputs for extra costs and slippage.")
    stress.add_argument("--runs", nargs="+", required=True)
    stress.add_argument("--out", required=True)
    stress.add_argument("--run-name", action="append", dest="run_names")
    stress.add_argument("--cost-multiplier", nargs="+", default=[1.0], type=float)
    stress.add_argument("--slippage-ticks", nargs="+", default=[0.0], type=float)
    stress.add_argument("--adverse-bps", nargs="+", default=[0.0], type=float)
    stress.add_argument("--tick-size", type=float, default=0.05)
    stress.add_argument("--contract-multiplier", type=float, default=1.0)
    stress.add_argument("--min-net-pnl", type=float, default=0.0)
    stress.add_argument("--min-fills", type=int, default=1)
    stress.add_argument("--max-drawdown", type=float, default=None)
    stress.add_argument("--fail-on-breach", action="store_true")

    surface_quote = sub.add_parser("quote-surface", help="Generate surface-driven market-making quotes.")
    surface_quote.add_argument("--chain", required=True)
    surface_quote.add_argument("--futures", required=True)
    surface_quote.add_argument("--out", required=True)
    surface_quote.add_argument("--no-filter-session", action="store_true")
    surface_quote.add_argument("--asof-latency-ns", type=int, default=0)
    surface_quote.add_argument("--tte-years", type=float, default=30 / 365)
    surface_quote.add_argument("--tick-size", type=float, default=0.05)
    surface_quote.add_argument("--lot-size", type=int, default=75)
    surface_quote.add_argument("--quote-lots", type=int, default=1)
    surface_quote.add_argument("--edge-ticks", type=float, default=2.0)
    surface_quote.add_argument("--inventory-skew-ticks-per-lot", type=float, default=0.5)
    surface_quote.add_argument("--max-market-spread-ticks", type=float, default=None)
    surface_quote.add_argument("--max-quotes-per-snapshot", type=int, default=None)
    surface_quote.add_argument("--max-snapshots", type=int, default=None)

    quote_review = sub.add_parser("review-quotes", help="Review generated surface quotes for MM risk hygiene.")
    quote_review.add_argument("--quotes", required=True)
    quote_review.add_argument("--out", required=True)
    quote_review.add_argument("--min-quotes", type=int, default=1)
    quote_review.add_argument("--min-instruments", type=int, default=1)
    quote_review.add_argument("--max-marketable-quotes", type=int, default=0)
    quote_review.add_argument("--min-quote-edge", type=float, default=0.0)
    quote_review.add_argument("--min-bid-share", type=float, default=0.25)
    quote_review.add_argument("--max-bid-share", type=float, default=0.75)
    quote_review.add_argument("--max-market-spread-ticks", type=float, default=None)
    quote_review.add_argument("--max-quotes-per-instrument", type=int, default=None)
    quote_review.add_argument("--fail-on-breach", action="store_true")

    exposure = sub.add_parser("review-order-exposure", help="Review option order-batch delta/vega/notional exposure.")
    exposure.add_argument("--orders", required=True)
    exposure.add_argument("--out", required=True)
    exposure.add_argument("--forward", type=float, default=None)
    exposure.add_argument("--tte-years", type=float, default=30 / 365)
    exposure.add_argument("--vol", type=float, default=None)
    exposure.add_argument("--contract-multiplier", type=float, default=1.0)
    exposure.add_argument("--allow-missing-greeks", action="store_true")
    exposure.add_argument("--max-abs-net-delta", type=float, default=None)
    exposure.add_argument("--max-abs-net-vega", type=float, default=None)
    exposure.add_argument("--max-gross-notional", type=float, default=None)
    exposure.add_argument("--max-side-imbalance", type=float, default=None)
    exposure.add_argument("--max-instrument-concentration", type=float, default=None)
    exposure.add_argument("--min-orders", type=int, default=1)
    exposure.add_argument("--fail-on-breach", action="store_true")

    surface_mm = sub.add_parser("replay-surface-mm", help="Replay passive surface market-making quotes.")
    surface_mm.add_argument("--quotes", required=True)
    surface_mm.add_argument("--chain", required=True)
    surface_mm.add_argument("--out", required=True)
    surface_mm.add_argument("--no-filter-session", action="store_true")
    surface_mm.add_argument("--order-latency-us", type=float, default=0.0)
    surface_mm.add_argument("--quote-ttl-ns", type=int, default=1_000_000_000)
    surface_mm.add_argument("--markout-horizon-ns", type=int, default=1_000_000_000)
    surface_mm.add_argument("--fill-depth-fraction", type=float, default=1.0)
    surface_mm.add_argument("--lot-size", type=int, default=75)
    surface_mm.add_argument("--option-tick", type=float, default=0.05)
    surface_mm.add_argument("--contract-multiplier", type=float, default=1.0)
    surface_mm.add_argument("--max-quotes", type=int, default=None)
    surface_mm.add_argument("--fill-model", default=None)
    surface_mm.add_argument("--allow-unready-fill-model", action="store_true")

    order_stage = sub.add_parser("stage-orders", help="Stage broker-neutral orders after pre-trade checks.")
    order_stage.add_argument("--orders", required=True)
    order_stage.add_argument("--out", required=True)
    order_stage.add_argument("--source", default="orders", choices=["orders", "surface_quotes"])
    order_stage.add_argument("--adapter", default="normalized")
    order_stage.add_argument("--max-order-qty", type=int, default=None)
    order_stage.add_argument("--max-notional", type=float, default=None)
    order_stage.add_argument("--price-band-pct", type=float, default=None)
    order_stage.add_argument("--max-orders", type=int, default=None)
    order_stage.add_argument("--contract-multiplier", type=float, default=1.0)
    order_stage.add_argument("--allow-marketable", action="store_true")
    order_stage.add_argument("--fail-on-reject", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "scan-parity-box":
        result = run_scan(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            asof_latency_ns=args.asof_latency_ns,
            depth_fraction=args.depth_fraction,
        )
        print(result.report.to_string(index=False))
        return 0
    if args.command == "audit-parity-edge":
        result = write_parity_edge_audit(
            args.scan,
            output_dir=args.out,
            thresholds=ParityEdgeThresholds(
                min_total_opportunities=args.min_total_opportunities,
                min_parity_opportunities=args.min_parity_opportunities,
                min_box_opportunities=args.min_box_opportunities,
                min_total_net_edge=args.min_total_net_edge,
                min_median_net_edge=args.min_median_net_edge,
                min_best_net_edge=args.min_best_net_edge,
                min_median_persistence_ticks=args.min_median_persistence_ticks,
                min_direction_count=args.min_direction_count,
                max_future_staleness_ns=args.max_future_staleness_ns,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "replay-parity":
        replay_params = calibrated_replay_params_from_path(
            "parity",
            {"order_latency_us": args.order_latency_us, "depth_fraction": args.depth_fraction},
            args.fill_model,
            require_ready=not args.allow_unready_fill_model,
        )
        result = run_parity_replay(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            signal_limit=args.signal_limit,
            depth_fraction=replay_params["depth_fraction"],
            feed_latency_us=args.feed_latency_us,
            order_latency_us=replay_params["order_latency_us"],
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "measure-leadlag":
        result = run_leadlag(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            leader_tick_size=args.leader_tick_size,
            laggard_tick_size=args.laggard_tick_size,
            delta=args.delta,
            innovation_ticks=args.innovation_ticks,
        )
        print(result.summary.latency_curve.to_string(index=False))
        return 0
    if args.command == "audit-leadlag-edge":
        result = write_leadlag_edge_audit(
            args.measure,
            output_dir=args.out,
            thresholds=LeadLagEdgeThresholds(
                min_events=args.min_events,
                min_abs_correlation=args.min_abs_correlation,
                min_correlation_samples=args.min_correlation_samples,
                min_update_rate=args.min_update_rate,
                max_median_update_ns=args.max_median_update_ns,
                min_best_latency_net_pnl=args.min_best_latency_net_pnl,
                min_best_latency_fills=args.min_best_latency_fills,
                min_profitable_latency_ns=args.min_profitable_latency_ns,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "audit-imbalance-edge":
        result = write_imbalance_edge_audit(
            args.ticks,
            output_dir=args.out,
            tick_size=args.tick_size,
            filter_session=not args.no_filter_session,
            market=args.market,
            thresholds=ImbalanceEdgeThresholds(
                entry_imbalance=args.entry_imbalance,
                min_microprice_edge_ticks=args.min_microprice_edge_ticks,
                max_spread_ticks=args.max_spread_ticks,
                min_depth=args.min_depth,
                forward_horizon_ns=args.forward_horizon_ns,
                min_signals=args.min_signals,
                min_direction_count=args.min_direction_count,
                min_mean_forward_edge_ticks=args.min_mean_forward_edge_ticks,
                min_win_rate=args.min_win_rate,
                min_median_forward_edge_ticks=args.min_median_forward_edge_ticks,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "sweep-imbalance-edge":
        result = write_imbalance_edge_sweep(
            args.ticks,
            output_dir=args.out,
            tick_size=args.tick_size,
            filter_session=not args.no_filter_session,
            market=args.market,
            entry_imbalance_values=args.entry_imbalance,
            min_microprice_edge_ticks_values=args.min_microprice_edge_ticks,
            forward_horizon_ns_values=args.forward_horizon_ns,
            max_spread_ticks=args.max_spread_ticks,
            min_depth=args.min_depth,
            min_signals=args.min_signals,
            min_direction_count=args.min_direction_count,
            min_mean_forward_edge_ticks=args.min_mean_forward_edge_ticks,
            min_win_rate=args.min_win_rate,
            min_median_forward_edge_ticks=args.min_median_forward_edge_ticks,
            thresholds=ImbalanceEdgeSweepThresholds(
                min_passed_configs=args.min_passed_configs,
                min_best_usable_signals=args.min_best_usable_signals,
                min_best_mean_forward_edge_ticks=args.min_best_mean_forward_edge_ticks,
                min_best_win_rate=args.min_best_win_rate,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "compare-imbalance-edge-sweeps":
        result = write_imbalance_edge_selection(
            args.sweeps,
            output_dir=args.out,
            labels=args.labels,
            thresholds=ImbalanceEdgeSelectionThresholds(
                min_sweeps=args.min_sweeps,
                min_pass_rate=args.min_pass_rate,
                min_median_usable_signals=args.min_median_usable_signals,
                min_median_mean_forward_edge_ticks=args.min_median_mean_forward_edge_ticks,
                min_min_win_rate=args.min_min_win_rate,
                min_median_robust_score=args.min_median_robust_score,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.has_selection else 0
    if args.command == "walkforward-imbalance-edge":
        fold_count = len(args.ticks)
        result = write_imbalance_edge_walkforward(
            args.ticks,
            output_dir=args.out,
            labels=args.labels,
            tick_size=args.tick_size,
            filter_session=not args.no_filter_session,
            market=args.market,
            entry_imbalance_values=args.entry_imbalance,
            min_microprice_edge_ticks_values=args.min_microprice_edge_ticks,
            forward_horizon_ns_values=args.forward_horizon_ns,
            max_spread_ticks=args.max_spread_ticks,
            min_depth=args.min_depth,
            min_signals=args.min_signals,
            min_direction_count=args.min_direction_count,
            min_mean_forward_edge_ticks=args.min_mean_forward_edge_ticks,
            min_win_rate=args.min_win_rate,
            min_median_forward_edge_ticks=args.min_median_forward_edge_ticks,
            sweep_thresholds=ImbalanceEdgeSweepThresholds(
                min_passed_configs=args.min_passed_configs,
                min_best_usable_signals=args.min_best_usable_signals,
                min_best_mean_forward_edge_ticks=args.min_best_mean_forward_edge_ticks,
                min_best_win_rate=args.min_best_win_rate,
            ),
            selection_thresholds=ImbalanceEdgeSelectionThresholds(
                min_sweeps=args.min_selection_sweeps if args.min_selection_sweeps is not None else fold_count,
                min_pass_rate=args.min_selection_pass_rate,
                min_median_usable_signals=args.min_selection_median_usable_signals,
                min_median_mean_forward_edge_ticks=args.min_selection_median_mean_forward_edge_ticks,
                min_min_win_rate=args.min_selection_min_win_rate,
                min_median_robust_score=args.min_selection_median_robust_score,
            ),
            walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(
                min_folds=args.min_folds if args.min_folds is not None else fold_count,
                min_passed_sweeps=args.min_passed_sweeps if args.min_passed_sweeps is not None else fold_count,
                require_selection=not args.allow_unselected,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "replay-leadlag":
        replay_params = calibrated_replay_params_from_path(
            "leadlag",
            {"order_latency_us": args.order_latency_us, "trigger_ticks": args.trigger_ticks},
            args.fill_model,
            require_ready=not args.allow_unready_fill_model,
        )
        result = run_leadlag_replay(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            trigger_ticks=replay_params["trigger_ticks"],
            qty=args.qty,
            feed_latency_us=args.feed_latency_us,
            order_latency_us=replay_params["order_latency_us"],
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "replay-imbalance":
        candidate_defaults = _imbalance_candidate_replay_defaults(args.candidate_config)
        market = args.market or candidate_defaults.get("market") or INDIA_NSE_INDEX_DERIVATIVES.name
        tick_size = _coalesce_number(args.tick_size, candidate_defaults.get("tick_size"), 0.05)
        entry_imbalance = _coalesce_number(args.entry_imbalance, candidate_defaults.get("entry_imbalance"), 0.6)
        min_edge_ticks = _coalesce_number(
            args.min_microprice_edge_ticks,
            candidate_defaults.get("min_microprice_edge_ticks"),
            0.25,
        )
        hold_ns = int(_coalesce_number(args.hold_ns, candidate_defaults.get("hold_ns"), 500_000_000))
        markout_horizons_ns = args.markout_horizons_ns or candidate_defaults.get("markout_horizons_ns")
        replay_params = calibrated_replay_params_from_path(
            "imbalance",
            {
                "order_latency_us": args.order_latency_us,
                "min_microprice_edge_ticks": min_edge_ticks,
            },
            args.fill_model,
            require_ready=not args.allow_unready_fill_model,
        )
        result = run_imbalance_replay(
            ticks_path=args.ticks,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            market=market,
            instrument_id=args.instrument_id,
            instrument_kind=args.instrument_kind,
            lot_size=args.lot_size,
            tick_size=tick_size,
            qty=args.qty,
            entry_imbalance=entry_imbalance,
            exit_imbalance=args.exit_imbalance,
            min_microprice_edge_ticks=replay_params["min_microprice_edge_ticks"],
            max_spread_ticks=args.max_spread_ticks,
            min_depth=args.min_depth,
            hold_ns=hold_ns,
            cooloff_ns=args.cooloff_ns,
            feed_latency_us=args.feed_latency_us,
            order_latency_us=replay_params["order_latency_us"],
            **_generic_cost_kwargs(args, candidate_defaults),
            markout_horizons_ns=markout_horizons_ns,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "walkforward-imbalance-replay":
        result = write_imbalance_replay_walkforward(
            args.ticks,
            output_dir=args.out,
            labels=args.labels,
            candidate_config=args.candidate_config,
            filter_session=not args.no_filter_session,
            market=args.market,
            instrument_id=args.instrument_id,
            instrument_kind=args.instrument_kind,
            lot_size=args.lot_size,
            tick_size=args.tick_size,
            qty=args.qty,
            entry_imbalance=args.entry_imbalance,
            exit_imbalance=args.exit_imbalance,
            min_microprice_edge_ticks=args.min_microprice_edge_ticks,
            max_spread_ticks=args.max_spread_ticks,
            min_depth=args.min_depth,
            hold_ns=args.hold_ns,
            cooloff_ns=args.cooloff_ns,
            feed_latency_us=args.feed_latency_us,
            order_latency_us=args.order_latency_us,
            **_generic_cost_override_kwargs(args),
            markout_horizons_ns=args.markout_horizons_ns,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_markout_mean=args.min_markout_mean,
            ),
            thresholds=ImbalanceReplayWalkForwardThresholds(
                min_folds=args.min_folds if args.min_folds is not None else len(args.ticks),
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "promote-imbalance-candidate":
        result = write_imbalance_candidate_promotion(
            args.walkforward,
            output_dir=args.out,
            thresholds=ImbalanceCandidatePromotionThresholds(
                require_walkforward_passed=not args.allow_unpassed_walkforward,
                require_candidate_ready=not args.allow_unready_candidate,
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pipeline-imbalance-research":
        fold_count = len(args.ticks)
        result = write_imbalance_research_pipeline(
            args.ticks,
            output_dir=args.out,
            labels=args.labels,
            tick_size=args.tick_size,
            filter_session=not args.no_filter_session,
            market=args.market,
            entry_imbalance_values=args.entry_imbalance,
            min_microprice_edge_ticks_values=args.min_microprice_edge_ticks,
            forward_horizon_ns_values=args.forward_horizon_ns,
            max_spread_ticks=args.max_spread_ticks,
            min_depth=args.min_depth,
            min_signals=args.min_signals,
            min_direction_count=args.min_direction_count,
            min_mean_forward_edge_ticks=args.min_mean_forward_edge_ticks,
            min_win_rate=args.min_win_rate,
            min_median_forward_edge_ticks=args.min_median_forward_edge_ticks,
            instrument_id=args.instrument_id,
            instrument_kind=args.instrument_kind,
            lot_size=args.lot_size,
            qty=args.qty,
            exit_imbalance=args.exit_imbalance,
            cooloff_ns=args.cooloff_ns,
            feed_latency_us=args.feed_latency_us,
            order_latency_us=args.order_latency_us,
            **_generic_cost_override_kwargs(args),
            sweep_thresholds=ImbalanceEdgeSweepThresholds(
                min_passed_configs=args.min_passed_configs,
                min_best_usable_signals=args.min_best_usable_signals,
                min_best_mean_forward_edge_ticks=args.min_best_mean_forward_edge_ticks,
                min_best_win_rate=args.min_best_win_rate,
            ),
            selection_thresholds=ImbalanceEdgeSelectionThresholds(
                min_sweeps=args.min_selection_sweeps if args.min_selection_sweeps is not None else fold_count,
                min_pass_rate=args.min_selection_pass_rate,
                min_median_usable_signals=args.min_selection_median_usable_signals,
                min_median_mean_forward_edge_ticks=args.min_selection_median_mean_forward_edge_ticks,
                min_min_win_rate=args.min_selection_min_win_rate,
                min_median_robust_score=args.min_selection_median_robust_score,
            ),
            edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(
                min_folds=args.min_edge_folds if args.min_edge_folds is not None else fold_count,
                min_passed_sweeps=args.min_passed_edge_sweeps
                if args.min_passed_edge_sweeps is not None
                else fold_count,
                require_selection=not args.allow_unselected,
            ),
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_markout_mean=args.min_markout_mean,
            ),
            replay_walkforward_thresholds=ImbalanceReplayWalkForwardThresholds(
                min_folds=args.min_replay_folds if args.min_replay_folds is not None else fold_count,
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
            ),
            promotion_thresholds=ImbalanceCandidatePromotionThresholds(
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "audit-settlement-convergence":
        result = write_settlement_convergence_audit(
            args.index_ticks,
            args.chain,
            output_dir=args.out,
            window_start_ns=args.window_start_ns,
            window_end_ns=args.window_end_ns,
            index_price_col=args.index_price_col,
            lot_size=args.lot_size,
            tick_size=args.tick_size,
            qty=args.qty,
            depth_fraction=args.depth_fraction,
            min_known_fraction=args.min_known_fraction,
            min_gross_edge_ticks=args.min_gross_edge_ticks,
            min_net_edge=args.min_net_edge,
            thresholds=SettlementConvergenceThresholds(
                min_opportunities=args.min_opportunities,
                min_total_net_edge=args.min_total_net_edge,
                min_best_net_edge=args.min_best_net_edge,
                min_median_known_fraction=args.min_median_known_fraction,
                min_direction_count=args.min_direction_count,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "walkforward-settlement-convergence":
        result = write_settlement_convergence_walkforward(
            args.index_ticks,
            args.chains,
            output_dir=args.out,
            labels=args.labels,
            window_start_ns=args.window_start_ns,
            window_end_ns=args.window_end_ns,
            index_price_col=args.index_price_col,
            lot_size=args.lot_size,
            tick_size=args.tick_size,
            qty=args.qty,
            depth_fraction=args.depth_fraction,
            min_known_fraction=args.min_known_fraction,
            min_gross_edge_ticks=args.min_gross_edge_ticks,
            min_net_edge=args.min_net_edge,
            audit_thresholds=SettlementConvergenceThresholds(
                min_opportunities=args.min_fold_opportunities,
                min_total_net_edge=args.min_fold_total_net_edge,
                min_best_net_edge=args.min_fold_best_net_edge,
                min_median_known_fraction=args.min_fold_median_known_fraction,
                min_direction_count=args.min_fold_direction_count,
            ),
            thresholds=SettlementConvergenceWalkForwardThresholds(
                min_folds=args.min_folds if args.min_folds is not None else len(args.index_ticks),
                min_pass_rate=args.min_pass_rate,
                min_total_opportunities=args.min_total_opportunities,
                min_total_net_edge=args.min_total_net_edge,
                min_median_best_net_edge=args.min_median_best_net_edge,
                min_median_known_fraction=args.min_median_known_fraction,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "promote-settlement-candidate":
        result = write_settlement_candidate_promotion(
            args.walkforward,
            output_dir=args.out,
            thresholds=SettlementCandidatePromotionThresholds(
                require_walkforward_passed=not args.allow_unpassed_walkforward,
                require_candidate_ready=not args.allow_unready_candidate,
                min_pass_rate=args.min_pass_rate,
                min_total_opportunities=args.min_total_opportunities,
                min_total_net_edge=args.min_total_net_edge,
                min_median_best_net_edge=args.min_median_best_net_edge,
                min_median_known_fraction=args.min_median_known_fraction,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "plan-settlement-orders":
        result = write_settlement_order_plan(
            args.promotion,
            output_dir=args.out,
            config=SettlementOrderPlanConfig(
                symbol_prefix=args.symbol_prefix,
                require_promotion_ready=not args.allow_unready_promotion,
                qty=args.qty,
                price_offset_ticks=args.price_offset_ticks,
                tick_size=args.tick_size,
                output_filename=args.output_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pipeline-settlement-launch":
        result = write_settlement_launch_pipeline(
            args.promotion,
            output_dir=args.out,
            config=SettlementLaunchPipelineConfig(
                adapter=args.adapter,
                mode=args.mode,
                route_tag=args.route_tag,
                symbol_prefix=args.symbol_prefix,
                qty=args.qty,
                price_offset_ticks=args.price_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                product=args.product,
                exchange=args.exchange,
                require_reviewed_schema=not args.allow_placeholder_schema,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "calibrate":
        _, summary = run_calibration_report(
            simulated_orders_path=args.simulated_orders,
            live_fills_path=args.live_fills,
            output_dir=args.out,
            adapter=args.adapter,
        )
        print(summary.to_string(index=False))
        return 0
    if args.command == "calibrate-fill-model":
        result = write_fill_model_calibration(
            reconciliation_dir=args.reconciliation,
            output_dir=args.out,
            thresholds=FillModelCalibrationThresholds(
                tick_size=args.tick_size,
                min_orders=args.min_orders,
                min_live_fill_rate=args.min_live_fill_rate,
                max_mismatch_rate=args.max_mismatch_rate,
                max_overfill_rate=args.max_overfill_rate,
                max_unmatched_fills=args.max_unmatched_fills,
                max_adverse_slippage_ticks=args.max_adverse_slippage_ticks,
                latency_quantile=args.latency_quantile,
                fill_ratio_quantile=args.fill_ratio_quantile,
                slippage_quantile=args.slippage_quantile,
                min_queue_conservatism=args.min_queue_conservatism,
                max_queue_conservatism=args.max_queue_conservatism,
                base_edge_ticks=args.base_edge_ticks,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "compare-fill-models":
        result = write_fill_model_drift_report(
            baseline_path=args.baseline,
            latest_path=args.latest,
            output_dir=args.out,
            thresholds=FillModelDriftThresholds(
                require_baseline_ready=not args.allow_unready_baseline,
                require_latest_ready=not args.allow_unready_latest,
                require_same_instruments=args.require_same_instruments,
                max_queue_conservatism_increase_pct=args.max_queue_conservatism_increase_pct,
                max_order_latency_increase_us=args.max_order_latency_increase_us,
                max_slippage_tick_increase=args.max_slippage_tick_increase,
                max_min_edge_tick_increase=args.max_min_edge_tick_increase,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "plan-calibrated-replay":
        base_params = {
            key: value
            for key, value in {
                "order_latency_us": args.order_latency_us,
                "trigger_ticks": args.trigger_ticks,
                "depth_fraction": args.depth_fraction,
                "fill_depth_fraction": args.fill_depth_fraction,
                "edge_ticks": args.edge_ticks,
            }.items()
            if value is not None
        }
        result = write_calibrated_replay_plan(
            strategy=args.strategy,
            fill_model_path=args.fill_model,
            output_dir=args.out,
            base_params=base_params,
            require_ready=not args.allow_unready_fill_model,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "review-proof-refresh":
        result = write_proof_refresh_report(
            drift_path=args.drift,
            baseline_proof_path=args.baseline_proof,
            latest_proof_path=args.latest_proof,
            calibrated_replay_path=args.calibrated_replay,
            output_dir=args.out,
            thresholds=ProofRefreshThresholds(
                require_calibrated_replay_when_drift_fails=args.require_calibrated_replay,
                expected_strategy=args.strategy,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "audit-adapter-schema":
        result = write_adapter_schema_audit(
            args.sample,
            output_dir=args.out,
            adapter=args.adapter,
            kind=args.kind,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_missing and not result.passed else 0
    if args.command == "normalize-mapped-data":
        result = write_mapped_data_normalization(
            args.input,
            args.mapping,
            output_dir=args.out,
            config=MappedDataConfig(
                adapter=args.adapter,
                kind=args.kind,
                output_filename=args.output_file,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                filter_session=not args.no_filter_session,
                market=args.market,
                require_all_mapped=not args.allow_missing_required,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "diagnose-ticks":
        ticks = load_tick_csv(args.ticks, filter_session=not args.no_filter_session, market=args.market).data
        result = write_diagnostics(tick_diagnostics(ticks, tick_size=args.tick_size, market=args.market), args.out)
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "diagnose-chain":
        chain = load_option_chain_csv(args.chain, filter_session=not args.no_filter_session, market=args.market).data
        result = write_diagnostics(chain_diagnostics(chain, tick_size=args.tick_size, market=args.market), args.out)
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "instrument-metadata-report":
        result = write_instrument_metadata_report(
            args.input,
            output_dir=args.out,
            config=InstrumentMetadataConfig(
                instrument_column=args.instrument_column,
                min_parse_coverage=args.min_parse_coverage,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_unparsed and not result.passed else 0
    if args.command == "market-profile-report":
        result = write_market_profile_report(
            args.out,
            config=MarketProfileReportConfig(
                markets=tuple(args.markets) if args.markets else MarketProfileReportConfig().markets,
                price=args.price,
                qty=args.qty,
                buy_notional_rate=args.buy_notional_rate,
                sell_notional_rate=args.sell_notional_rate,
                per_unit_fee=args.per_unit_fee,
                per_contract_fee=args.per_contract_fee,
                per_order_fee=args.per_order_fee,
            ),
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "market-portability-report":
        result = write_market_portability_report(
            args.out,
            config=MarketPortabilityReportConfig(
                markets=tuple(args.markets) if args.markets else MarketPortabilityReportConfig().markets,
                strategies=tuple(args.strategies or ()),
                explicit_fee_model=args.explicit_fee_model,
            ),
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "proof-report":
        result = write_proof_report(
            args.runs,
            output_dir=args.out,
            run_names=args.run_names,
            thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_maker_share=args.min_maker_share,
                min_worst_regime_equity_change=args.min_worst_regime_equity_change,
                min_markout_mean=args.min_markout_mean,
                min_spread_net=args.min_spread_net,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "catalog-runs":
        result = write_experiment_catalog(args.roots, output_dir=args.out)
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "review-strategy-evidence":
        result = write_strategy_evidence_review(
            args.catalog,
            output_dir=args.out,
            thresholds=EvidenceThresholds(
                required_run_types=tuple(args.required_run_types)
                if args.required_run_types
                else EvidenceThresholds().required_run_types,
                min_passed_per_type=args.min_passed_per_type,
                allow_dirty_git=args.allow_dirty_git,
                require_same_git_commit=args.require_same_git_commit,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "sweep-leadlag":
        result = run_leadlag_sweep(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            trigger_ticks_values=args.trigger_ticks,
            feed_latency_us_values=args.feed_latency_us,
            order_latency_us_values=args.order_latency_us,
            filter_session=not args.no_filter_session,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            qty=args.qty,
            flat_after_ns=args.flat_after_ns,
            cooloff_ns=args.cooloff_ns,
            markout_horizons_ns=args.markout_horizons_ns,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_markout_mean=args.min_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "sweep-imbalance":
        candidate_defaults = _imbalance_candidate_replay_defaults(args.candidate_config)
        market = args.market or candidate_defaults.get("market") or INDIA_NSE_INDEX_DERIVATIVES.name
        tick_size = _coalesce_number(args.tick_size, candidate_defaults.get("tick_size"), 0.05)
        entry_imbalance_values = _coalesce_list(
            args.entry_imbalance,
            candidate_defaults.get("entry_imbalance"),
            "entry_imbalance",
        )
        min_edge_values = _coalesce_list(
            args.min_microprice_edge_ticks,
            candidate_defaults.get("min_microprice_edge_ticks"),
            "min_microprice_edge_ticks",
        )
        hold_ns_values = [
            int(value)
            for value in _coalesce_list(args.hold_ns, candidate_defaults.get("hold_ns"), "hold_ns")
        ]
        markout_horizons_ns = args.markout_horizons_ns or candidate_defaults.get("markout_horizons_ns")
        result = run_imbalance_sweep(
            ticks_path=args.ticks,
            output_dir=args.out,
            entry_imbalance_values=entry_imbalance_values,
            min_microprice_edge_ticks_values=min_edge_values,
            hold_ns_values=hold_ns_values,
            feed_latency_us_values=args.feed_latency_us,
            order_latency_us_values=args.order_latency_us,
            filter_session=not args.no_filter_session,
            market=market,
            instrument_id=args.instrument_id,
            instrument_kind=args.instrument_kind,
            lot_size=args.lot_size,
            tick_size=tick_size,
            qty=args.qty,
            exit_imbalance=args.exit_imbalance,
            max_spread_ticks=args.max_spread_ticks,
            min_depth=args.min_depth,
            cooloff_ns=args.cooloff_ns,
            **_generic_cost_kwargs(args, candidate_defaults),
            markout_horizons_ns=markout_horizons_ns,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_markout_mean=args.min_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "sweep-parity":
        result = run_parity_sweep(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            depth_fraction_values=args.depth_fraction,
            asof_latency_ns_values=args.asof_latency_ns,
            feed_latency_us_values=args.feed_latency_us,
            order_latency_us_values=args.order_latency_us,
            filter_session=not args.no_filter_session,
            signal_limit=args.signal_limit,
            max_signal_age_ns=args.max_signal_age_ns,
            max_qty=args.max_qty,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_spread_net=args.min_spread_net,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "sweep-surface-mm":
        result = run_surface_mm_sweep(
            quotes_path=args.quotes,
            chain_path=args.chain,
            output_dir=args.out,
            quote_ttl_ns_values=args.quote_ttl_ns,
            order_latency_us_values=args.order_latency_us,
            fill_depth_fraction_values=args.fill_depth_fraction,
            markout_horizon_ns_values=args.markout_horizon_ns,
            filter_session=not args.no_filter_session,
            lot_size=args.lot_size,
            option_tick=args.option_tick,
            contract_multiplier=args.contract_multiplier,
            max_quotes=args.max_quotes,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_maker_share=args.min_maker_share,
                min_markout_mean=args.min_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "compare-sweeps":
        result = write_sweep_comparison(
            args.sweeps,
            output_dir=args.out,
            labels=args.labels,
            group_cols=args.group_cols,
            min_pass_rate=args.min_pass_rate,
            min_sweeps=args.min_sweeps,
            min_median_net_pnl=args.min_median_net_pnl,
            max_worst_drawdown=args.max_worst_drawdown,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.has_selection else 0
    if args.command == "promote-scenario":
        result = write_promotion_report(
            args.selection,
            output_dir=args.out,
            thresholds=PromotionThresholds(
                min_pass_rate=args.min_pass_rate,
                min_sweeps=args.min_sweeps,
                min_median_net_pnl=args.min_median_net_pnl,
                min_min_net_pnl=args.min_min_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_fills=args.min_median_fills,
                max_runs_with_losing_regimes=args.max_runs_with_losing_regimes,
                max_otr=args.max_otr,
                min_maker_share=args.min_maker_share,
                min_markout_mean=args.min_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "launch-bundle":
        result = write_launch_bundle(
            promotion_dir=args.promotion,
            staged_orders_dir=args.staged_orders,
            output_dir=args.out,
            mode=args.mode,
            adapter=args.adapter,
            thresholds=LaunchThresholds(
                min_accepted_orders=args.min_accepted_orders,
                min_acceptance_rate=args.min_acceptance_rate,
                require_promotion_ready=not args.allow_unready_promotion,
                require_no_rejections=not args.allow_rejections,
                max_total_notional=args.max_total_notional,
                max_order_notional=args.max_order_notional,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "export-launch-orders":
        result = write_order_export(
            args.launch,
            output_dir=args.out,
            config=OrderExportConfig(
                adapter=args.adapter,
                route_tag=args.route_tag,
                require_launch_ready=not args.allow_unready_launch,
                require_limit_orders=not args.allow_non_limit,
                max_orders=args.max_orders,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pack-broker-upload":
        result = write_order_upload_pack(
            args.export,
            output_dir=args.out,
            config=OrderUploadPackConfig(
                adapter=args.adapter,
                product=args.product,
                exchange=args.exchange,
                require_reviewed_schema=not args.allow_placeholder_schema,
                output_filename=args.output_file,
                mapping_filename=args.mapping_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "draft-order-mapping":
        result = write_order_mapping_draft(
            args.export,
            args.sample,
            output_dir=args.out,
            config=OrderMappingDraftConfig(
                adapter=args.adapter,
                output_filename=args.output_file,
                required_columns=tuple(args.required_columns or ()),
                optional_columns=tuple(args.optional_columns or ()),
                default_values=_parse_key_value_args(args.defaults or (), "--default"),
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_unmapped and not result.ready else 0
    if args.command == "map-broker-orders":
        result = write_mapped_order_export(
            args.export,
            args.mapping,
            output_dir=args.out,
            config=MappedOrderExportConfig(
                adapter=args.adapter,
                output_filename=args.output_file,
                require_all_mapped=not args.allow_missing_required,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "reconcile-broker-fills":
        result = write_order_reconciliation(
            export_dir=args.export,
            fills_path=args.fills,
            output_dir=args.out,
            adapter=args.adapter,
            thresholds=ReconciliationThresholds(
                min_order_fill_rate=args.min_order_fill_rate,
                max_unfilled_orders=args.max_unfilled_orders,
                max_partial_orders=args.max_partial_orders,
                max_overfilled_orders=args.max_overfilled_orders,
                max_mismatched_orders=args.max_mismatched_orders,
                max_unmatched_fills=args.max_unmatched_fills,
                max_adverse_slippage=args.max_adverse_slippage,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "shadow-session-report":
        result = write_shadow_session_report(
            launch_dir=args.launch,
            export_dir=args.export,
            reconciliation_dir=args.reconciliation,
            output_dir=args.out,
            thresholds=ShadowSessionThresholds(
                require_launch_ready=not args.allow_unready_launch,
                require_export_ready=not args.allow_unready_export,
                require_reconciliation_passed=not args.allow_failed_reconciliation,
                max_failed_component_checks=args.max_failed_component_checks,
                min_order_fill_rate=args.min_order_fill_rate,
                max_unmatched_fills=args.max_unmatched_fills,
                max_mismatched_orders=args.max_mismatched_orders,
                max_overfilled_orders=args.max_overfilled_orders,
                max_unfilled_orders=args.max_unfilled_orders,
                max_adverse_slippage=args.max_adverse_slippage,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.accepted else 0
    if args.command == "compare-shadow-sessions":
        result = write_shadow_session_comparison(
            args.sessions,
            output_dir=args.out,
            labels=args.labels,
            thresholds=ShadowComparisonThresholds(
                min_sessions=args.min_sessions,
                min_acceptance_rate=args.min_acceptance_rate,
                require_same_scenario=not args.allow_mixed_scenarios,
                min_median_order_fill_rate=args.min_median_order_fill_rate,
                min_worst_order_fill_rate=args.min_worst_order_fill_rate,
                max_total_failed_component_checks=args.max_total_failed_component_checks,
                max_total_unmatched_fills=args.max_total_unmatched_fills,
                max_total_mismatched_orders=args.max_total_mismatched_orders,
                max_total_overfilled_orders=args.max_total_overfilled_orders,
                max_worst_adverse_slippage=args.max_worst_adverse_slippage,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.accepted else 0
    if args.command == "plan-scaleup":
        result = write_scaleup_plan(
            evidence_dir=args.evidence,
            shadow_comparison_dir=args.shadow_comparison,
            launch_dir=args.launch,
            output_dir=args.out,
            order_exposure_dir=args.order_exposure,
            proof_refresh_dir=args.proof_refresh,
            instrument_metadata_dir=args.instrument_metadata,
            thresholds=ScaleUpThresholds(
                target_mode=args.target_mode,
                max_scale_multiplier=args.max_scale_multiplier,
                min_shadow_sessions=args.min_shadow_sessions,
                min_shadow_acceptance_rate=args.min_shadow_acceptance_rate,
                min_median_order_fill_rate=args.min_median_order_fill_rate,
                min_worst_order_fill_rate=args.min_worst_order_fill_rate,
                max_worst_adverse_slippage=args.max_worst_adverse_slippage,
                max_total_failed_component_checks=args.max_total_failed_component_checks,
                max_total_unmatched_fills=args.max_total_unmatched_fills,
                max_total_mismatched_orders=args.max_total_mismatched_orders,
                max_total_overfilled_orders=args.max_total_overfilled_orders,
                max_orders_per_session=args.max_orders_per_session,
                max_session_notional=args.max_session_notional,
                max_gross_notional=args.max_gross_notional,
                max_abs_net_delta=args.max_abs_net_delta,
                max_abs_net_vega=args.max_abs_net_vega,
                stop_loss=args.stop_loss,
                allowed_adapters=tuple(args.allowed_adapters or ()),
                require_proof_refresh=args.require_proof_refresh,
                require_instrument_metadata=args.require_instrument_metadata,
                min_instrument_parse_coverage=args.min_instrument_parse_coverage,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "build-runtime-telemetry":
        result = write_runtime_telemetry_snapshot(
            scaleup_dir=args.scaleup,
            output_dir=args.out,
            export_dir=args.export,
            reconciliation_dir=args.reconciliation,
            instrument_metadata_dir=args.instrument_metadata,
            pnl_path=args.pnl,
            open_orders_path=args.open_orders,
            positions_path=args.positions,
            snapshot_ts_ns=args.snapshot_ts_ns,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "monitor-scaleup-guard":
        result = write_runtime_guard_report(
            scaleup_dir=args.scaleup,
            telemetry_path=args.telemetry,
            output_dir=args.out,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_halt and result.halted else 0
    if args.command == "plan-halt-response":
        result = write_halt_response_plan(
            guard_dir=args.guard,
            output_dir=args.out,
            open_orders_path=args.open_orders,
            positions_path=args.positions,
            config=HaltResponseConfig(
                require_guard_halt=not args.allow_continue_guard,
                require_flatten_prices=not args.allow_missing_flatten_prices,
                default_order_type=args.default_order_type,
                default_time_in_force=args.default_time_in_force,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "export-halt-response":
        result = write_halt_response_export(
            halt_response_dir=args.halt_response,
            output_dir=args.out,
            cancel_mapping_path=args.cancel_mapping,
            flatten_mapping_path=args.flatten_mapping,
            config=HaltResponseExportConfig(
                adapter=args.adapter,
                cancel_output_filename=args.cancel_output_file,
                flatten_output_filename=args.flatten_output_file,
                require_response_ready=not args.allow_unready_response,
                require_all_mapped=not args.allow_missing_required,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "reconcile-halt-execution":
        result = write_halt_execution_report(
            halt_response_dir=args.halt_response,
            output_dir=args.out,
            cancel_acks_path=args.cancel_acks,
            flatten_fills_path=args.flatten_fills,
            positions_path=args.positions,
            thresholds=HaltExecutionThresholds(
                require_response_ready=not args.allow_unready_response,
                require_all_cancel_acks=not args.allow_missing_cancel_acks,
                require_all_flatten_fills=not args.allow_incomplete_flatten_fills,
                require_final_positions=not args.allow_missing_final_positions,
                position_tolerance=args.position_tolerance,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "review-halt-incident":
        result = write_halt_incident_report(
            guard_dir=args.guard,
            halt_response_dir=args.halt_response,
            halt_export_dir=args.halt_export,
            halt_execution_dir=args.halt_execution,
            output_dir=args.out,
            thresholds=HaltIncidentThresholds(
                require_guard_halt=not args.allow_continue_guard,
                require_response_ready=not args.allow_unready_response,
                require_export_ready=args.require_export,
                require_execution_passed=not args.allow_incomplete_execution,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "review-resume-gate":
        result = write_resume_gate_report(
            incident_dir=args.incident,
            scaleup_dir=args.scaleup,
            output_dir=args.out,
            operator_review_path=args.operator_review,
            thresholds=ResumeGateThresholds(
                require_incident_passed=not args.allow_open_incident,
                require_scaleup_ready=not args.allow_unready_scaleup,
                require_same_scenario=not args.allow_scenario_change,
                require_same_adapter=not args.allow_adapter_change,
                require_operator_approval=args.require_operator_approval,
                max_failed_scaleup_checks=args.max_failed_scaleup_checks,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "stress-replay":
        result = write_stress_report(
            args.runs,
            output_dir=args.out,
            run_names=args.run_names,
            config=StressConfig(
                cost_multipliers=args.cost_multiplier,
                slippage_ticks=args.slippage_ticks,
                adverse_bps=args.adverse_bps,
                tick_size=args.tick_size,
                contract_multiplier=args.contract_multiplier,
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "quote-surface":
        result = run_surface_quote_generation(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            asof_latency_ns=args.asof_latency_ns,
            tte_years=args.tte_years,
            tick_size=args.tick_size,
            lot_size=args.lot_size,
            quote_lots=args.quote_lots,
            edge_ticks=args.edge_ticks,
            inventory_skew_ticks_per_lot=args.inventory_skew_ticks_per_lot,
            max_market_spread_ticks=args.max_market_spread_ticks,
            max_quotes_per_snapshot=args.max_quotes_per_snapshot,
            max_snapshots=args.max_snapshots,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "review-quotes":
        result = write_quote_risk_report(
            args.quotes,
            output_dir=args.out,
            thresholds=QuoteRiskThresholds(
                min_quotes=args.min_quotes,
                min_instruments=args.min_instruments,
                max_marketable_quotes=args.max_marketable_quotes,
                min_quote_edge=args.min_quote_edge,
                min_bid_share=args.min_bid_share,
                max_bid_share=args.max_bid_share,
                max_market_spread_ticks=args.max_market_spread_ticks,
                max_quotes_per_instrument=args.max_quotes_per_instrument,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "review-order-exposure":
        result = write_order_exposure_report(
            args.orders,
            output_dir=args.out,
            config=OrderExposureConfig(
                forward=args.forward,
                tte_years=args.tte_years,
                vol=args.vol,
                contract_multiplier=args.contract_multiplier,
                require_greeks=not args.allow_missing_greeks,
                max_abs_net_delta=args.max_abs_net_delta,
                max_abs_net_vega=args.max_abs_net_vega,
                max_gross_notional=args.max_gross_notional,
                max_side_imbalance=args.max_side_imbalance,
                max_instrument_concentration=args.max_instrument_concentration,
                min_orders=args.min_orders,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "replay-surface-mm":
        replay_params = calibrated_replay_params_from_path(
            "surface_mm",
            {"order_latency_us": args.order_latency_us, "fill_depth_fraction": args.fill_depth_fraction},
            args.fill_model,
            require_ready=not args.allow_unready_fill_model,
        )
        result = run_surface_mm_replay(
            quotes_path=args.quotes,
            chain_path=args.chain,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            config=SurfaceMMReplayConfig(
                order_latency_us=replay_params["order_latency_us"],
                quote_ttl_ns=args.quote_ttl_ns,
                markout_horizon_ns=args.markout_horizon_ns,
                fill_depth_fraction=replay_params["fill_depth_fraction"],
                lot_size=args.lot_size,
                option_tick=args.option_tick,
                contract_multiplier=args.contract_multiplier,
                max_quotes=args.max_quotes,
            ),
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "stage-orders":
        result = write_staged_orders(
            args.orders,
            output_dir=args.out,
            source=args.source,
            adapter=args.adapter,
            limits=OrderStagingLimits(
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                require_nonmarketable=not args.allow_marketable,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_reject and not result.passed else 0
    raise RuntimeError(f"unhandled command {args.command}")


def _imbalance_candidate_replay_defaults(path: str | None) -> dict:
    if path is None:
        return {}
    candidate = _candidate_config_path(path)
    config = json.loads(candidate.read_text(encoding="utf-8"))
    if str(config.get("strategy", "")).strip().lower() != "imbalance":
        raise ValueError(f"candidate config is not for imbalance strategy: {candidate}")
    if not _truthy(config.get("ready", False)):
        failed = config.get("failed_checks", []) or []
        raise ValueError(f"imbalance candidate config is not ready: {failed}")
    defaults = config.get("replay_defaults", {}) or {}
    if not isinstance(defaults, dict):
        raise ValueError(f"candidate config replay_defaults must be an object: {candidate}")
    return defaults


def _candidate_config_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "candidate_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate}")
    return candidate


def _coalesce_number(*values: object) -> float:
    for value in values:
        if value is None:
            continue
        return float(value)
    raise ValueError("at least one numeric value is required")


def _coalesce_list(cli_values: list | None, candidate_value: object, name: str) -> list:
    if cli_values:
        return list(cli_values)
    if isinstance(candidate_value, list) and candidate_value:
        return list(candidate_value)
    if candidate_value is not None:
        return [candidate_value]
    raise ValueError(f"{name} is required unless --candidate-config supplies it")


def _generic_cost_override_kwargs(args: argparse.Namespace) -> dict:
    return {
        "generic_buy_notional_rate": args.generic_buy_notional_rate,
        "generic_sell_notional_rate": args.generic_sell_notional_rate,
        "generic_per_unit_fee": args.generic_per_unit_fee,
        "generic_per_contract_fee": args.generic_per_contract_fee,
        "generic_per_order_fee": args.generic_per_order_fee,
    }


def _parse_key_value_args(values: tuple[str, ...] | list[str], flag: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{flag} expects target=value, got {value!r}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{flag} target must not be blank")
        parsed[key] = raw.strip()
    return parsed


def _generic_cost_kwargs(args: argparse.Namespace, candidate_defaults: dict | None = None) -> dict:
    defaults = {}
    if candidate_defaults is not None:
        maybe_defaults = candidate_defaults.get("generic_costs", {})
        if isinstance(maybe_defaults, dict):
            defaults = maybe_defaults
    return {
        "generic_buy_notional_rate": _coalesce_number(
            args.generic_buy_notional_rate,
            defaults.get("buy_notional_rate"),
            0.0,
        ),
        "generic_sell_notional_rate": _coalesce_number(
            args.generic_sell_notional_rate,
            defaults.get("sell_notional_rate"),
            0.0,
        ),
        "generic_per_unit_fee": _coalesce_number(args.generic_per_unit_fee, defaults.get("per_unit_fee"), 0.0),
        "generic_per_contract_fee": _coalesce_number(
            args.generic_per_contract_fee,
            defaults.get("per_contract_fee"),
            0.0,
        ),
        "generic_per_order_fee": _coalesce_number(args.generic_per_order_fee, defaults.get("per_order_fee"), 0.0),
    }


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


if __name__ == "__main__":
    raise SystemExit(main())
