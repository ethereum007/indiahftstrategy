from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapters.applied_mapped_data import (
    AppliedMappedDataConfig,
    verify_applied_mapped_data_normalization,
    write_applied_mapped_data_normalization,
)
from adapters.broker_readiness import BrokerReadinessThresholds, write_broker_readiness_report
from adapters.broker import run_calibration_report
from adapters.halt_response_export import HaltResponseExportConfig, write_halt_response_export
from adapters.mapped_data import MappedDataConfig, write_mapped_data_normalization
from adapters.reviewed_mapped_data import (
    ReviewedMappedDataConfig,
    verify_reviewed_mapped_data_normalization,
    write_reviewed_mapped_data_normalization,
)
from adapters.mapped_order_export import MappedOrderExportConfig, write_mapped_order_export
from adapters.nse_market_calendar import NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA
from adapters.order_export import OrderExportConfig, write_order_export
from adapters.order_mapping_draft import OrderMappingDraftConfig, write_order_mapping_draft
from adapters.order_reconciliation import ReconciliationThresholds, write_order_reconciliation
from adapters.order_upload_pack import OrderUploadPackConfig, write_order_upload_pack
from adapters.orders import OrderStagingLimits, write_staged_orders
from adapters.schema_audit import write_adapter_schema_audit
from adapters.vendor_intake import (
    VendorCsvIntakeConfig,
    verify_vendor_csv_intake_report,
    write_vendor_csv_intake_report,
)
from adapters.vendor_mapping_review import (
    VendorMappingReviewConfig,
    verify_vendor_mapping_review,
    write_vendor_mapping_review,
)
from adapters.vendor_mapping_application import (
    VendorMappingApplicationConfig,
    verify_vendor_mapping_application,
    write_vendor_mapping_application,
)
from adapters.vendor_mapping_scope_review import (
    VendorMappingScopeReviewConfig,
    verify_vendor_mapping_scope_review,
    write_vendor_mapping_scope_review,
)
from data.chains import load_option_chain_csv
from data.diagnostics import chain_diagnostics, tick_diagnostics, write_diagnostics
from data.loaders import load_tick_csv
from reports.backtest_overfit import (
    BacktestOverfitConfig,
    BacktestOverfitThresholds,
    write_backtest_overfit_audit,
)
from reports.backtest_holdout import (
    BacktestHoldoutConfig,
    BacktestHoldoutThresholds,
    write_backtest_holdout_audit,
)
from reports.backtest_significance import (
    BacktestSignificanceConfig,
    BacktestSignificanceThresholds,
    write_backtest_significance_audit,
)
from reports.walkforward_split_audit import (
    WalkForwardSplitAuditConfig,
    WalkForwardSplitAuditThresholds,
    write_walk_forward_split_audit,
)
from reports.catalog import write_experiment_catalog
from reports.broker_dispatch import BrokerDispatchThresholds, write_broker_dispatch_plan
from reports.broker_dispatch_ack import BrokerDispatchAckThresholds, write_broker_dispatch_acknowledgements
from reports.broker_dispatch_roundtrip import BrokerDispatchRoundTripThresholds, write_broker_dispatch_roundtrip
from reports.broker_dispatch_send import BrokerDispatchSendThresholds, write_broker_dispatch_send_packet
from reports.broker_vendor_data_readiness import (
    BrokerVendorDataReadinessConfig,
    write_broker_vendor_data_readiness_pipeline,
)
from reports.cutover import CutoverGateThresholds, write_cutover_gate_report
from reports.data_readiness_comparison import (
    DataReadinessComparisonThresholds,
    verify_data_readiness_comparison,
    write_data_readiness_comparison,
)
from reports.data_readiness import (
    DataReadinessThresholds,
    verify_data_readiness_report,
    write_data_readiness_report,
)
from reports.evidence import (
    EvidenceThresholds,
    evidence_profile_run_types,
    verify_strategy_evidence_review,
    write_strategy_evidence_review,
)
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
from reports.imbalance_launch_pipeline import ImbalanceLaunchPipelineConfig, write_imbalance_launch_pipeline
from reports.imbalance_order_plan import ImbalanceOrderPlanConfig, write_imbalance_order_plan
from reports.imbalance_pipeline import write_imbalance_research_pipeline
from reports.imbalance_replay_walkforward import (
    ImbalanceReplayWalkForwardThresholds,
    write_imbalance_replay_walkforward,
)
from reports.instrument_metadata import InstrumentMetadataConfig, write_instrument_metadata_report
from reports.launch import LaunchThresholds, write_launch_bundle
from reports.leadlag_candidate_promotion import (
    LeadLagCandidatePromotionThresholds,
    write_leadlag_candidate_promotion,
)
from reports.leadlag_edge import LeadLagEdgeThresholds, write_leadlag_edge_audit
from reports.leadlag_launch_pipeline import LeadLagLaunchPipelineConfig, write_leadlag_launch_pipeline
from reports.leadlag_order_plan import LeadLagOrderPlanConfig, write_leadlag_order_plan
from reports.leadlag_replay_walkforward import (
    LeadLagReplayWalkForwardThresholds,
    write_leadlag_replay_walkforward,
)
from reports.market_calendar import (
    verify_market_calendar_report,
    write_market_calendar_from_sessions,
    write_market_calendar_report,
)
from reports.market_profile import MarketProfileReportConfig, write_market_profile_report
from reports.market_portability import MarketPortabilityReportConfig, write_market_portability_report
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.order_exposure import OrderExposureConfig, write_order_exposure_report
from reports.parity_candidate_promotion import (
    ParityCandidatePromotionThresholds,
    write_parity_candidate_promotion,
)
from reports.parity_edge import ParityEdgeThresholds, write_parity_edge_audit
from reports.parity_launch_pipeline import ParityLaunchPipelineConfig, write_parity_launch_pipeline
from reports.parity_order_plan import ParityOrderPlanConfig, write_parity_order_plan
from reports.proof import (
    ProofThresholds,
    verify_proof_report,
    write_proof_report,
)
from reports.proof_refresh import (
    ProofRefreshThresholds,
    verify_proof_refresh_report,
    write_proof_refresh_report,
)
from reports.promotion import PromotionThresholds, write_promotion_report
from reports.robust_selection_pipeline import write_robust_selection_pipeline
from reports.research_family import (
    ResearchFamilyConfig,
    ResearchFamilyThresholds,
    write_research_family_audit,
)
from reports.research_family_launch import (
    load_research_family_launch_contract,
    recover_research_family_launch_attempt_outcome,
    write_research_family_launch_attempt_outcome,
    write_research_family_launch_execution_receipt,
    write_research_family_launch_matrix,
)
from reports.research_family_registration import (
    ResearchFamilyRegistrationThresholds,
    write_research_family_registration,
)
from reports.provider_market_data_fetcher import (
    ProviderMarketDataFetcherConfig,
    write_provider_market_data_fetcher_plan,
)
from reports.provider_market_data_client import (
    ProviderMarketDataClientConfig,
    write_provider_market_data_client_plan,
)
from reports.provider_market_data_capture import (
    ProviderMarketDataCaptureConfig,
    write_provider_market_data_capture_review,
)
from reports.provider_market_data_batch import (
    ProviderMarketDataBatchConfig,
    write_provider_market_data_batch_pipeline,
)
from reports.provider_market_data_live_session import (
    ProviderMarketDataLiveSessionConfig,
    write_provider_market_data_live_session_plan,
)
from reports.provider_market_data_live_preflight import (
    ProviderMarketDataLivePreflightConfig,
    write_provider_market_data_live_session_preflight,
)
from reports.provider_market_data_live_bundle import (
    ProviderMarketDataLiveCaptureBundleConfig,
    write_provider_market_data_live_capture_bundle,
)
from reports.provider_market_data_live_rehearsal import (
    ProviderMarketDataLiveRehearsalConfig,
    write_provider_market_data_live_rehearsal,
)
from reports.provider_market_data_live_evidence import (
    ProviderMarketDataLiveEvidenceConfig,
    write_provider_market_data_live_evidence_review,
)
from reports.provider_market_data_research_handoff import (
    ProviderMarketDataResearchHandoffConfig,
    write_provider_market_data_research_handoff,
)
from reports.provider_market_data_imbalance_research import (
    ProviderMarketDataImbalanceResearchConfig,
    write_provider_market_data_imbalance_research,
)
from reports.provider_market_data_imbalance_evidence import (
    ProviderMarketDataImbalanceEvidenceConfig,
    write_provider_market_data_imbalance_evidence_review,
)
from reports.provider_market_data_imbalance_launch import (
    ProviderMarketDataImbalanceLaunchConfig,
    write_provider_market_data_imbalance_launch_packet,
)
from reports.provider_market_data_imbalance_launch_evidence import (
    ProviderMarketDataImbalanceLaunchEvidenceConfig,
    write_provider_market_data_imbalance_launch_evidence_review,
)
from reports.provider_market_data_imbalance_scorecard import (
    ProviderMarketDataImbalanceScorecardConfig,
    write_provider_market_data_imbalance_scorecard,
)
from reports.provider_market_data_imbalance_route_readiness import (
    ProviderMarketDataImbalanceRouteReadinessConfig,
    write_provider_market_data_imbalance_route_readiness,
)
from reports.provider_market_data_imbalance_scaleup import (
    ProviderMarketDataImbalanceScaleupConfig,
    write_provider_market_data_imbalance_scaleup_plan,
)
from reports.provider_market_data_imbalance_runtime_telemetry import (
    ProviderMarketDataImbalanceRuntimeTelemetryConfig,
    write_provider_market_data_imbalance_runtime_telemetry_snapshot,
)
from reports.provider_market_data_imbalance_runtime_guard import (
    ProviderMarketDataImbalanceRuntimeGuardConfig,
    write_provider_market_data_imbalance_runtime_guard,
)
from reports.provider_market_data_imbalance_runtime_session import (
    ProviderMarketDataImbalanceRuntimeSessionConfig,
    write_provider_market_data_imbalance_runtime_session,
)
from reports.provider_market_data_imbalance_broker_readiness import (
    ProviderMarketDataImbalanceBrokerReadinessConfig,
    write_provider_market_data_imbalance_broker_readiness,
)
from reports.provider_market_data_imbalance_cutover import (
    ProviderMarketDataImbalanceCutoverConfig,
    write_provider_market_data_imbalance_cutover,
)
from reports.provider_market_data_imbalance_route_enable import (
    ProviderMarketDataImbalanceRouteEnableConfig,
    write_provider_market_data_imbalance_route_enable,
)
from reports.provider_market_data_imbalance_broker_dispatch import (
    ProviderMarketDataImbalanceBrokerDispatchConfig,
    write_provider_market_data_imbalance_broker_dispatch,
)
from reports.provider_market_data_imbalance_broker_dispatch_send import (
    ProviderMarketDataImbalanceBrokerDispatchSendConfig,
    write_provider_market_data_imbalance_broker_dispatch_send,
)
from reports.provider_market_data_imbalance_broker_dispatch_ack import (
    ProviderMarketDataImbalanceBrokerDispatchAckConfig,
    write_provider_market_data_imbalance_broker_dispatch_ack,
)
from reports.provider_market_data_imbalance_broker_dispatch_roundtrip import (
    ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig,
    write_provider_market_data_imbalance_broker_dispatch_roundtrip,
)
from reports.provider_market_data_imbalance_broker_rehearsal_certificate import (
    ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig,
    write_provider_market_data_imbalance_broker_rehearsal_certificate,
)
from reports.provider_market_data_imbalance_release_review import (
    ProviderMarketDataImbalanceReleaseReviewConfig,
    verify_provider_market_data_imbalance_release_review,
    write_provider_market_data_imbalance_release_review,
)
from reports.provider_market_data_imbalance_release_decision import (
    ProviderMarketDataImbalanceReleaseDecisionConfig,
    verify_provider_market_data_imbalance_release_decision,
    write_provider_market_data_imbalance_release_decision,
)
from reports.provider_market_data_imbalance_live_dryrun_handoff import (
    ProviderMarketDataImbalanceLiveDryrunHandoffConfig,
    verify_provider_market_data_imbalance_live_dryrun_handoff,
    write_provider_market_data_imbalance_live_dryrun_handoff,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_preflight import (
    ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig,
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight,
    write_provider_market_data_imbalance_live_dryrun_runtime_preflight,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher,
    write_provider_market_data_imbalance_live_dryrun_runtime_launcher,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator import (
    ProviderMarketDataImbalanceLiveDryrunShadowConfig,
    verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
    write_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration import (
    ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
    verify_provider_market_data_imbalance_live_dryrun_shadow_calibration,
    write_provider_market_data_imbalance_live_dryrun_shadow_calibration,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration_stability import (
    ProviderShadowCalibrationStabilityConfig,
    verify_provider_shadow_calibration_stability,
    write_provider_shadow_calibration_stability,
)
from reports.provider_market_data_imbalance_broker_lineage_migration import (
    ProviderBrokerLineageMigrationConfig,
    verify_provider_broker_lineage_migration_audit,
    write_provider_broker_lineage_migration_audit,
)
from reports.provider_market_data_imbalance_broker_lineage_audit_usage import (
    ProviderBrokerLineageAuditUsageConfig,
    write_provider_broker_lineage_audit_usage_review,
)
from reports.provider_market_data_imbalance_broker_lineage_refresh_convergence import (
    write_provider_broker_lineage_refresh_convergence,
)
from reports.provider_market_data_imbalance_broker_active_lineage import (
    write_provider_broker_active_lineage_index,
)
from reports.provider_market_data_imbalance_active_lineage_chain import (
    ProviderMarketDataImbalanceActiveLineageChainConfig,
    write_provider_market_data_imbalance_active_lineage_chain_audit,
)
from reports.provider_market_data_live_ingest import (
    ProviderMarketDataLiveIngestConfig,
    write_provider_market_data_live_session_ingest,
)
from reports.provider_market_data_pipeline import (
    ProviderMarketDataPipelineConfig,
    write_provider_market_data_pipeline,
)
from reports.quote_lifecycle import QuoteLifecycleThresholds, write_quote_lifecycle_plan
from reports.quote_risk import QuoteRiskThresholds, write_quote_risk_report
from reports.resume import ResumeGateThresholds, write_resume_gate_report
from reports.route_enable import RouteEnableThresholds, write_route_enable_packet
from reports.route_readiness import write_route_readiness_review
from reports.runtime_guard import write_runtime_guard_report
from reports.runtime_session import write_runtime_session_monitor
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
from reports.strategy_portfolio import StrategyPortfolioConfig, write_strategy_portfolio_allocations
from reports.strategy_scorecard import StrategyScorecardThresholds, write_strategy_scorecard
from reports.stress import StressConfig, write_stress_report
from reports.sweeps import write_sweep_comparison
from reports.surface_mm_pipeline import write_surface_mm_research_pipeline
from reports.surface_mm_launch_pipeline import (
    SurfaceMMLaunchPipelineConfig,
    write_surface_mm_launch_pipeline,
)
from reports.surface_quality import SurfaceQualityThresholds, write_surface_quality_report
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
    write_vendor_market_data_pipeline,
)
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


def _add_market_calendar_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--market-calendar",
        default=None,
        help=(
            "Versioned exchange-calendar JSON; supplied coverage is enforced "
            "fail-closed and fingerprinted into evidence."
        ),
    )


def _add_scaleup_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-mode", default="shadow", choices=["paper", "shadow", "live_dryrun"])
    parser.add_argument("--max-scale-multiplier", type=float, default=1.0)
    parser.add_argument("--min-shadow-sessions", type=int, default=1)
    parser.add_argument("--min-shadow-acceptance-rate", type=float, default=1.0)
    parser.add_argument("--min-median-order-fill-rate", type=float, default=0.0)
    parser.add_argument("--min-worst-order-fill-rate", type=float, default=None)
    parser.add_argument("--max-worst-adverse-slippage", type=float, default=None)
    parser.add_argument("--max-total-failed-component-checks", type=int, default=0)
    parser.add_argument("--max-total-unmatched-fills", type=int, default=0)
    parser.add_argument("--max-total-mismatched-orders", type=int, default=0)
    parser.add_argument("--max-total-overfilled-orders", type=int, default=0)
    parser.add_argument("--max-telemetry-age-ns", type=float, default=None)
    parser.add_argument("--max-lifecycle-orders", type=int, default=None)
    parser.add_argument("--max-replace-orders", type=int, default=None)
    parser.add_argument("--max-open-order-count", type=int, default=None)
    parser.add_argument("--max-open-order-qty", type=float, default=None)
    parser.add_argument("--max-open-order-notional", type=float, default=None)
    parser.add_argument("--max-open-order-age-ns", type=float, default=None)
    parser.add_argument("--max-gross-position-qty", type=float, default=None)
    parser.add_argument("--max-abs-net-position-qty", type=float, default=None)
    parser.add_argument("--max-orders-per-session", type=int, default=None)
    parser.add_argument("--max-session-notional", type=float, default=None)
    parser.add_argument("--max-gross-notional", type=float, default=None)
    parser.add_argument("--max-abs-net-delta", type=float, default=None)
    parser.add_argument("--max-abs-net-vega", type=float, default=None)
    parser.add_argument("--stop-loss", type=float, default=None)
    parser.add_argument("--allowed-adapter", action="append", dest="allowed_adapters")
    parser.add_argument("--require-proof-refresh", action="store_true")
    parser.add_argument("--require-instrument-metadata", action="store_true")
    parser.add_argument("--require-data-readiness", action="store_true")
    parser.add_argument("--require-data-readiness-comparison", action="store_true")
    parser.add_argument("--require-strategy-portfolio", action="store_true")
    parser.add_argument("--require-route-readiness", action="store_true")
    parser.add_argument("--require-broker-readiness", action="store_true")
    parser.add_argument("--require-resume-gate", action="store_true")
    parser.add_argument("--require-dispatch-roundtrip", action="store_true")
    parser.add_argument("--min-instrument-parse-coverage", type=float, default=1.0)
    parser.add_argument("--expected-strategy", default=None)
    parser.add_argument("--expected-market", default=None)


def _scaleup_thresholds_from_args(args: argparse.Namespace) -> ScaleUpThresholds:
    return ScaleUpThresholds(
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
        max_telemetry_age_ns=args.max_telemetry_age_ns,
        max_lifecycle_orders=args.max_lifecycle_orders,
        max_replace_orders=args.max_replace_orders,
        max_open_order_count=args.max_open_order_count,
        max_open_order_qty=args.max_open_order_qty,
        max_open_order_notional=args.max_open_order_notional,
        max_open_order_age_ns=args.max_open_order_age_ns,
        max_gross_position_qty=args.max_gross_position_qty,
        max_abs_net_position_qty=args.max_abs_net_position_qty,
        max_orders_per_session=args.max_orders_per_session,
        max_session_notional=args.max_session_notional,
        max_gross_notional=args.max_gross_notional,
        max_abs_net_delta=args.max_abs_net_delta,
        max_abs_net_vega=args.max_abs_net_vega,
        stop_loss=args.stop_loss,
        allowed_adapters=tuple(args.allowed_adapters or ()),
        require_proof_refresh=args.require_proof_refresh,
        require_instrument_metadata=args.require_instrument_metadata,
        require_data_readiness=args.require_data_readiness,
        require_data_readiness_comparison=args.require_data_readiness_comparison,
        require_strategy_portfolio=args.require_strategy_portfolio,
        require_route_readiness=args.require_route_readiness,
        require_broker_readiness=args.require_broker_readiness,
        require_resume_gate=args.require_resume_gate,
        require_dispatch_roundtrip=args.require_dispatch_roundtrip,
        min_instrument_parse_coverage=args.min_instrument_parse_coverage,
        expected_strategy=args.expected_strategy,
        expected_market=args.expected_market,
    )


def _catalog_exit_code(
    result,
    *,
    fail_on_actions: bool,
    fail_on_blocked_actions: bool,
    fail_on_catalog_gaps: bool,
    fail_on_placeholder_schema: bool,
    fail_on_blocked_placeholder_schema: bool,
    fail_on_broker_roundtrip_portfolio_breach: bool,
    require_broker_roundtrip_portfolio_safe: bool,
    fail_on_broker_roundtrip_portfolio_concentration_breach: bool,
    require_broker_roundtrip_portfolio_concentration_ok: bool,
    fail_on_broker_roundtrip_resume_route_breach: bool,
    require_broker_roundtrip_resume_route_ready: bool,
    fail_on_provider_broker_roundtrip_synthetic_sidecar_breach: bool,
    require_provider_broker_roundtrip_synthetic_sidecar_ready: bool,
    fail_on_provider_lineage_selection_blocks: bool,
) -> int:
    if fail_on_catalog_gaps and _catalog_gap_count(result) > 0:
        return 2
    if (
        fail_on_broker_roundtrip_portfolio_breach
        and _catalog_summary_metric(result, "broker_roundtrip_portfolio_breach_runs") > 0
    ):
        return 2
    if (
        require_broker_roundtrip_portfolio_safe
        and _catalog_summary_metric(result, "broker_roundtrip_portfolio_safe_runs") <= 0
    ):
        return 2
    if (
        fail_on_broker_roundtrip_portfolio_concentration_breach
        and _catalog_summary_metric(result, "broker_roundtrip_portfolio_concentration_breach_runs") > 0
    ):
        return 2
    if (
        require_broker_roundtrip_portfolio_concentration_ok
        and _catalog_summary_metric(result, "broker_roundtrip_portfolio_concentration_ok_runs") <= 0
    ):
        return 2
    if (
        fail_on_broker_roundtrip_resume_route_breach
        and _catalog_summary_metric(result, "broker_roundtrip_resume_route_breach_runs") > 0
    ):
        return 2
    if (
        require_broker_roundtrip_resume_route_ready
        and _catalog_summary_metric(result, "broker_roundtrip_resume_route_ready_runs") <= 0
    ):
        return 2
    if (
        fail_on_provider_broker_roundtrip_synthetic_sidecar_breach
        and _catalog_summary_metric(result, "provider_broker_roundtrip_synthetic_sidecar_breach_runs") > 0
    ):
        return 2
    if (
        require_provider_broker_roundtrip_synthetic_sidecar_ready
        and _catalog_summary_metric(result, "provider_broker_roundtrip_synthetic_sidecar_ready_runs") <= 0
    ):
        return 2
    if fail_on_placeholder_schema and _catalog_summary_metric(result, "placeholder_schema_active_runs") > 0:
        return 2
    if (
        fail_on_provider_lineage_selection_blocks
        and _catalog_summary_metric(
            result, "provider_lineage_selection_blocked_runs"
        )
        > 0
    ):
        return 2
    if (
        fail_on_blocked_placeholder_schema
        and _catalog_summary_metric(result, "placeholder_schema_blocked_runs") > 0
    ):
        return 2
    action_queue = result.action_queue
    action_count = 0 if action_queue is None else int(len(action_queue))
    if fail_on_actions and action_count > 0:
        return 2
    if fail_on_blocked_actions and action_count > 0:
        statuses = action_queue["queue_status"].astype(str)
        blocked_or_unknown = int(statuses.isin(["blocked", "unknown"]).sum())
        if blocked_or_unknown > 0:
            return 2
    return 0


def _market_portability_exit_code(
    result,
    *,
    fail_on_breach: bool,
    fail_on_gaps: bool,
    fail_on_actions: bool,
    fail_on_blocked_actions: bool,
) -> int:
    if fail_on_breach and not result.ready:
        return 2
    if fail_on_gaps and result.gaps is not None and len(result.gaps) > 0:
        return 2
    action_queue = result.action_queue
    action_count = 0 if action_queue is None else int(len(action_queue))
    if fail_on_actions and action_count > 0:
        return 2
    if fail_on_blocked_actions and action_queue is not None and not action_queue.empty:
        statuses = action_queue["queue_status"].astype(str)
        if int(statuses.isin(["blocked", "unknown"]).sum()) > 0:
            return 2
    return 0


def _catalog_gap_count(result) -> int:
    summary = result.summary
    if summary.empty:
        return 0
    row = summary.iloc[0]
    return sum(
        _catalog_metric(row, column)
        for column in [
            "status_false_runs",
            "missing_summary_runs",
            "dirty_runs",
            "input_unfingerprinted_count",
        ]
    )


def _catalog_summary_metric(result, column: str) -> int:
    summary = result.summary
    if summary.empty:
        return 0
    return _catalog_metric(summary.iloc[0], column)


def _catalog_metric(row, column: str) -> int:
    try:
        value = row.get(column, 0)
    except AttributeError:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hft", description="India HFT research command runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan-parity-box", help="Run executable parity/box scanner.")
    scan.add_argument("--chain", required=True)
    scan.add_argument("--futures", required=True)
    scan.add_argument("--out", required=True)
    scan.add_argument("--no-filter-session", action="store_true")
    scan.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
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
    leadlag_edge.add_argument("--strategy", default="lead_lag_taker")
    leadlag_edge.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    leadlag_edge.add_argument("--min-events", type=int, default=1)
    leadlag_edge.add_argument("--min-abs-correlation", type=float, default=0.0)
    leadlag_edge.add_argument("--min-correlation-samples", type=int, default=2)
    leadlag_edge.add_argument("--min-update-rate", type=float, default=0.0)
    leadlag_edge.add_argument("--max-median-update-ns", type=int, default=None)
    leadlag_edge.add_argument("--min-best-latency-net-pnl", type=float, default=0.0)
    leadlag_edge.add_argument("--min-best-latency-fills", type=int, default=1)
    leadlag_edge.add_argument("--min-profitable-latency-ns", type=int, default=0)
    leadlag_edge.add_argument("--min-best-latency-fill-rate", type=float, default=None)
    leadlag_edge.add_argument("--min-best-latency-avg-net-edge", type=float, default=None)
    leadlag_edge.add_argument("--max-best-latency-cost-drag-ratio", type=float, default=None)
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
    leadlag_replay.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    leadlag_replay.add_argument("--leader-tick", type=float, default=0.05)
    leadlag_replay.add_argument("--laggard-tick", type=float, default=0.05)
    leadlag_replay.add_argument("--delta", type=float, default=1.0)
    leadlag_replay.add_argument("--trigger-ticks", type=float, default=3.0)
    leadlag_replay.add_argument("--qty", type=int, default=75)
    leadlag_replay.add_argument("--feed-latency-us", type=float, default=0.0)
    leadlag_replay.add_argument("--order-latency-us", type=float, default=0.0)
    leadlag_replay.add_argument("--fill-model", default=None)
    leadlag_replay.add_argument("--allow-unready-fill-model", action="store_true")
    _add_generic_cost_args(leadlag_replay)

    leadlag_replay_walkforward = sub.add_parser("walkforward-leadlag-replay", help="Replay one lead-lag candidate across paired leader/laggard folds and aggregate proof.")
    leadlag_replay_walkforward.add_argument("--leaders", nargs="+", required=True)
    leadlag_replay_walkforward.add_argument("--laggards", nargs="+", required=True)
    leadlag_replay_walkforward.add_argument("--out", required=True)
    leadlag_replay_walkforward.add_argument("--label", action="append", dest="labels")
    leadlag_replay_walkforward.add_argument("--candidate-config", default=None)
    leadlag_replay_walkforward.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    leadlag_replay_walkforward.add_argument("--timestamp-tz", default=None)
    leadlag_replay_walkforward.add_argument("--no-filter-session", action="store_true")
    leadlag_replay_walkforward.add_argument("--market", default=None)
    leadlag_replay_walkforward.add_argument("--lot-size", type=int, default=75)
    leadlag_replay_walkforward.add_argument("--leader-tick", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--laggard-tick", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--delta", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--trigger-ticks", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--qty", type=int, default=None)
    leadlag_replay_walkforward.add_argument("--flat-after-ns", type=int, default=None)
    leadlag_replay_walkforward.add_argument("--cooloff-ns", type=int, default=None)
    leadlag_replay_walkforward.add_argument("--feed-latency-us", type=float, default=0.0)
    leadlag_replay_walkforward.add_argument("--order-latency-us", type=float, default=0.0)
    leadlag_replay_walkforward.add_argument("--markout-horizons-ns", nargs="+", default=None, type=int)
    leadlag_replay_walkforward.add_argument("--min-net-pnl", type=float, default=0.0)
    leadlag_replay_walkforward.add_argument("--min-fills", type=int, default=1)
    leadlag_replay_walkforward.add_argument("--max-drawdown", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--max-otr", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--min-markout-mean", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--min-folds", type=int, default=None)
    leadlag_replay_walkforward.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    leadlag_replay_walkforward.add_argument("--min-total-fills", type=int, default=1)
    leadlag_replay_walkforward.add_argument("--min-total-net-pnl", type=float, default=0.0)
    leadlag_replay_walkforward.add_argument("--max-worst-drawdown", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--min-median-markout-mean", type=float, default=None)
    leadlag_replay_walkforward.add_argument("--fail-on-breach", action="store_true")
    _add_generic_cost_args(leadlag_replay_walkforward)

    leadlag_promotion = sub.add_parser("promote-leadlag-candidate", help="Promote a proven lead-lag replay walk-forward candidate for paper/shadow launch.")
    leadlag_promotion.add_argument("--walkforward", required=True)
    leadlag_promotion.add_argument("--out", required=True)
    leadlag_promotion.add_argument("--allow-unpassed-walkforward", action="store_true")
    leadlag_promotion.add_argument("--allow-unready-candidate", action="store_true")
    leadlag_promotion.add_argument("--allow-unbound-edge-audit", action="store_true")
    leadlag_promotion.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    leadlag_promotion.add_argument("--min-total-fills", type=int, default=1)
    leadlag_promotion.add_argument("--min-total-net-pnl", type=float, default=0.0)
    leadlag_promotion.add_argument("--max-worst-drawdown", type=float, default=None)
    leadlag_promotion.add_argument("--min-median-markout-mean", type=float, default=None)
    leadlag_promotion.add_argument("--fail-on-breach", action="store_true")

    leadlag_orders = sub.add_parser(
        "plan-leadlag-orders",
        help="Create broker-neutral paper/shadow order templates from a promoted lead-lag candidate.",
    )
    leadlag_orders.add_argument("--promotion", required=True)
    leadlag_orders.add_argument("--out", required=True)
    leadlag_orders.add_argument("--laggard-instrument-id", default="LAGGARD")
    leadlag_orders.add_argument("--qty", type=int, default=None)
    leadlag_orders.add_argument("--reference-price", type=float, default=None)
    leadlag_orders.add_argument("--buy-limit-price", type=float, default=None)
    leadlag_orders.add_argument("--sell-limit-price", type=float, default=None)
    leadlag_orders.add_argument("--entry-offset-ticks", type=float, default=0.0)
    leadlag_orders.add_argument("--tick-size", type=float, default=None)
    leadlag_orders.add_argument("--max-order-qty", type=int, default=None)
    leadlag_orders.add_argument("--max-notional", type=float, default=None)
    leadlag_orders.add_argument("--price-band-pct", type=float, default=None)
    leadlag_orders.add_argument("--output-file", default="leadlag_order_candidates.csv")
    leadlag_orders.add_argument("--allow-unready-promotion", action="store_true")
    leadlag_orders.add_argument("--allow-unbound-edge-audit", action="store_true")
    leadlag_orders.add_argument("--fail-on-breach", action="store_true")

    leadlag_pipeline = sub.add_parser(
        "pipeline-leadlag-launch",
        help="Run promoted lead-lag candidate through order plan, staging, launch, export, and upload pack.",
    )
    leadlag_pipeline.add_argument("--promotion", required=True)
    leadlag_pipeline.add_argument("--out", required=True)
    leadlag_pipeline.add_argument("--adapter", default="arrow_money")
    leadlag_pipeline.add_argument("--mode", default="shadow", choices=["paper", "shadow"])
    leadlag_pipeline.add_argument("--route-tag", default=None)
    leadlag_pipeline.add_argument("--laggard-instrument-id", default="LAGGARD")
    leadlag_pipeline.add_argument("--qty", type=int, default=None)
    leadlag_pipeline.add_argument("--reference-price", type=float, default=None)
    leadlag_pipeline.add_argument("--buy-limit-price", type=float, default=None)
    leadlag_pipeline.add_argument("--sell-limit-price", type=float, default=None)
    leadlag_pipeline.add_argument("--entry-offset-ticks", type=float, default=0.0)
    leadlag_pipeline.add_argument("--tick-size", type=float, default=None)
    leadlag_pipeline.add_argument("--max-order-qty", type=int, default=None)
    leadlag_pipeline.add_argument("--max-notional", type=float, default=None)
    leadlag_pipeline.add_argument("--price-band-pct", type=float, default=None)
    leadlag_pipeline.add_argument("--max-orders", type=int, default=None)
    leadlag_pipeline.add_argument("--contract-multiplier", type=float, default=1.0)
    leadlag_pipeline.add_argument("--product", default="MIS")
    leadlag_pipeline.add_argument("--exchange", default="NFO")
    leadlag_pipeline.add_argument("--broker-schema-audit", default=None)
    leadlag_pipeline.add_argument("--broker-mapping-draft", default=None)
    leadlag_pipeline.add_argument("--broker-mapped-orders", default=None)
    leadlag_pipeline.add_argument("--broker-halt-export", default=None)
    leadlag_pipeline.add_argument("--broker-reconciliation", default=None)
    leadlag_pipeline.add_argument("--broker-runtime-session", default=None)
    leadlag_pipeline.add_argument("--broker-vendor-data-readiness", default=None)
    leadlag_pipeline.add_argument("--require-broker-schema-audit", action="store_true")
    leadlag_pipeline.add_argument("--require-broker-mapping-draft", action="store_true")
    leadlag_pipeline.add_argument("--require-broker-mapped-orders", action="store_true")
    leadlag_pipeline.add_argument("--require-broker-halt-export", action="store_true")
    leadlag_pipeline.add_argument("--require-broker-reconciliation", action="store_true")
    leadlag_pipeline.add_argument("--require-broker-runtime-session", action="store_true")
    leadlag_pipeline.add_argument("--allow-placeholder-schema", action="store_true")
    leadlag_pipeline.add_argument("--fail-on-breach", action="store_true")

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

    imbalance_orders = sub.add_parser(
        "plan-imbalance-orders",
        help="Create broker-neutral paper/shadow order templates from a promoted imbalance candidate.",
    )
    imbalance_orders.add_argument("--promotion", required=True)
    imbalance_orders.add_argument("--out", required=True)
    imbalance_orders.add_argument("--instrument-id", default="BOOK")
    imbalance_orders.add_argument("--qty", type=int, default=None)
    imbalance_orders.add_argument("--reference-price", type=float, default=None)
    imbalance_orders.add_argument("--buy-limit-price", type=float, default=None)
    imbalance_orders.add_argument("--sell-limit-price", type=float, default=None)
    imbalance_orders.add_argument("--entry-offset-ticks", type=float, default=0.0)
    imbalance_orders.add_argument("--tick-size", type=float, default=None)
    imbalance_orders.add_argument("--max-order-qty", type=int, default=None)
    imbalance_orders.add_argument("--max-notional", type=float, default=None)
    imbalance_orders.add_argument("--price-band-pct", type=float, default=None)
    imbalance_orders.add_argument("--output-file", default="imbalance_order_candidates.csv")
    imbalance_orders.add_argument("--allow-unready-promotion", action="store_true")
    imbalance_orders.add_argument("--fail-on-breach", action="store_true")

    imbalance_launch_pipeline = sub.add_parser(
        "pipeline-imbalance-launch",
        help="Run promoted imbalance candidate through order plan, staging, launch, export, and upload pack.",
    )
    imbalance_launch_pipeline.add_argument("--promotion", required=True)
    imbalance_launch_pipeline.add_argument("--out", required=True)
    imbalance_launch_pipeline.add_argument("--adapter", default="arrow_money")
    imbalance_launch_pipeline.add_argument("--mode", default="shadow", choices=["paper", "shadow"])
    imbalance_launch_pipeline.add_argument("--route-tag", default=None)
    imbalance_launch_pipeline.add_argument("--instrument-id", default="BOOK")
    imbalance_launch_pipeline.add_argument("--qty", type=int, default=None)
    imbalance_launch_pipeline.add_argument("--reference-price", type=float, default=None)
    imbalance_launch_pipeline.add_argument("--buy-limit-price", type=float, default=None)
    imbalance_launch_pipeline.add_argument("--sell-limit-price", type=float, default=None)
    imbalance_launch_pipeline.add_argument("--entry-offset-ticks", type=float, default=0.0)
    imbalance_launch_pipeline.add_argument("--tick-size", type=float, default=None)
    imbalance_launch_pipeline.add_argument("--max-order-qty", type=int, default=None)
    imbalance_launch_pipeline.add_argument("--max-notional", type=float, default=None)
    imbalance_launch_pipeline.add_argument("--price-band-pct", type=float, default=None)
    imbalance_launch_pipeline.add_argument("--max-orders", type=int, default=None)
    imbalance_launch_pipeline.add_argument("--contract-multiplier", type=float, default=1.0)
    imbalance_launch_pipeline.add_argument("--product", default="MIS")
    imbalance_launch_pipeline.add_argument("--exchange", default="NFO")
    imbalance_launch_pipeline.add_argument("--broker-schema-audit", default=None)
    imbalance_launch_pipeline.add_argument("--broker-mapping-draft", default=None)
    imbalance_launch_pipeline.add_argument("--broker-mapped-orders", default=None)
    imbalance_launch_pipeline.add_argument("--broker-halt-export", default=None)
    imbalance_launch_pipeline.add_argument("--broker-reconciliation", default=None)
    imbalance_launch_pipeline.add_argument("--broker-runtime-session", default=None)
    imbalance_launch_pipeline.add_argument("--broker-vendor-data-readiness", default=None)
    imbalance_launch_pipeline.add_argument("--require-broker-schema-audit", action="store_true")
    imbalance_launch_pipeline.add_argument("--require-broker-mapping-draft", action="store_true")
    imbalance_launch_pipeline.add_argument("--require-broker-mapped-orders", action="store_true")
    imbalance_launch_pipeline.add_argument("--require-broker-halt-export", action="store_true")
    imbalance_launch_pipeline.add_argument("--require-broker-reconciliation", action="store_true")
    imbalance_launch_pipeline.add_argument("--require-broker-runtime-session", action="store_true")
    imbalance_launch_pipeline.add_argument("--allow-placeholder-schema", action="store_true")
    imbalance_launch_pipeline.add_argument("--fail-on-breach", action="store_true")

    imbalance_pipeline = sub.add_parser("pipeline-imbalance-research", help="Run edge, replay-proof, and promotion gates for imbalance research.")
    imbalance_pipeline.add_argument("--ticks", nargs="+", required=True)
    imbalance_pipeline.add_argument("--out", required=True)
    imbalance_pipeline.add_argument("--label", action="append", dest="labels")
    imbalance_pipeline.add_argument("--data-readiness-comparison", default=None)
    imbalance_pipeline.add_argument("--require-data-readiness-comparison", action="store_true")
    imbalance_pipeline.add_argument("--market-portability", default=None)
    imbalance_pipeline.add_argument("--require-market-portability", action="store_true")
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
    settlement_walkforward.add_argument("--data-readiness-comparison", default=None)
    settlement_walkforward.add_argument("--require-data-readiness-comparison", action="store_true")
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
    settlement_pipeline.add_argument("--broker-schema-audit", default=None)
    settlement_pipeline.add_argument("--broker-mapping-draft", default=None)
    settlement_pipeline.add_argument("--broker-mapped-orders", default=None)
    settlement_pipeline.add_argument("--broker-halt-export", default=None)
    settlement_pipeline.add_argument("--broker-reconciliation", default=None)
    settlement_pipeline.add_argument("--broker-runtime-session", default=None)
    settlement_pipeline.add_argument("--broker-vendor-data-readiness", default=None)
    settlement_pipeline.add_argument("--require-broker-schema-audit", action="store_true")
    settlement_pipeline.add_argument("--require-broker-mapping-draft", action="store_true")
    settlement_pipeline.add_argument("--require-broker-mapped-orders", action="store_true")
    settlement_pipeline.add_argument("--require-broker-halt-export", action="store_true")
    settlement_pipeline.add_argument("--require-broker-reconciliation", action="store_true")
    settlement_pipeline.add_argument("--require-broker-runtime-session", action="store_true")
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
    fill_model.add_argument("--fail-on-blocked-actions", action="store_true")
    fill_model.add_argument("--fail-on-actions", action="store_true")

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
    fill_model_drift.add_argument("--fail-on-blocked-actions", action="store_true")
    fill_model_drift.add_argument("--fail-on-actions", action="store_true")

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
    proof_refresh.add_argument("--market", default=None)
    proof_refresh.add_argument("--require-calibrated-replay", action="store_true")
    proof_refresh.add_argument("--fail-on-breach", action="store_true")
    proof_refresh.add_argument("--fail-on-blocked-actions", action="store_true")
    proof_refresh.add_argument("--fail-on-actions", action="store_true")

    proof_refresh_verify = sub.add_parser(
        "verify-proof-refresh-report",
        help=(
            "Reconstruct a proof-refresh report from its manifest-bound "
            "drift and proof evidence."
        ),
    )
    proof_refresh_verify.add_argument("--report", required=True)
    proof_refresh_verify.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

    schema_audit = sub.add_parser("audit-adapter-schema", help="Audit a vendor sample CSV against an adapter schema.")
    schema_audit.add_argument("--sample", required=True)
    schema_audit.add_argument("--out", required=True)
    schema_audit.add_argument("--adapter", default="normalized")
    schema_audit.add_argument("--kind", default="ticks")
    schema_audit.add_argument("--fail-on-missing", action="store_true")
    schema_audit.add_argument("--fail-on-blocked-actions", action="store_true")
    schema_audit.add_argument("--fail-on-actions", action="store_true")

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
    _add_market_calendar_arg(mapped_data)
    mapped_data.add_argument("--no-filter-session", action="store_true")
    mapped_data.add_argument("--allow-missing-required", action="store_true")
    mapped_data.add_argument("--fail-on-breach", action="store_true")
    mapped_data.add_argument("--fail-on-blocked-actions", action="store_true")
    mapped_data.add_argument("--fail-on-actions", action="store_true")
    reviewed_mapped_data = sub.add_parser(
        "normalize-reviewed-mapped-data",
        help="Normalize the exact vendor source and mapping from a verified approval.",
    )
    reviewed_mapped_data.add_argument("--review", required=True)
    reviewed_mapped_data.add_argument("--out", required=True)
    reviewed_mapped_data.add_argument("--output-file", default="normalized_data.csv")
    reviewed_mapped_data.add_argument("--timestamp-unit", default="ns")
    reviewed_mapped_data.add_argument("--timestamp-tz", default=None)
    reviewed_mapped_data.add_argument(
        "--market",
        default="india_nse_index_derivatives",
    )
    _add_market_calendar_arg(reviewed_mapped_data)
    reviewed_mapped_data.add_argument("--no-filter-session", action="store_true")
    reviewed_mapped_data.add_argument(
        "--allow-missing-required",
        action="store_true",
    )
    reviewed_mapped_data.add_argument("--fail-on-breach", action="store_true")
    reviewed_mapped_data.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    reviewed_mapped_data.add_argument("--fail-on-actions", action="store_true")
    verify_reviewed_mapped_data = sub.add_parser(
        "verify-reviewed-mapped-data",
        help="Reconstruct reviewed mapped-data evidence and all retained inputs.",
    )
    verify_reviewed_mapped_data.add_argument("--normalization", required=True)
    verify_reviewed_mapped_data.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    applied_mapped_data = sub.add_parser(
        "normalize-applied-vendor-mapping",
        help=(
            "Normalize only the target source and mapping retained by a verified "
            "mapping application."
        ),
    )
    applied_mapped_data.add_argument("--application", required=True)
    applied_mapped_data.add_argument("--out", required=True)
    applied_mapped_data.add_argument("--output-file", default="normalized_data.csv")
    applied_mapped_data.add_argument("--timestamp-unit", default="ns")
    applied_mapped_data.add_argument("--timestamp-tz", default=None)
    applied_mapped_data.add_argument(
        "--market",
        default="india_nse_index_derivatives",
    )
    _add_market_calendar_arg(applied_mapped_data)
    applied_mapped_data.add_argument("--no-filter-session", action="store_true")
    applied_mapped_data.add_argument(
        "--allow-missing-required",
        action="store_true",
    )
    applied_mapped_data.add_argument("--fail-on-breach", action="store_true")
    applied_mapped_data.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    applied_mapped_data.add_argument("--fail-on-actions", action="store_true")
    verify_applied_mapped_data = sub.add_parser(
        "verify-applied-vendor-mapping-normalization",
        help=(
            "Reconstruct target-applied normalization and its retained mapping "
            "application."
        ),
    )
    verify_applied_mapped_data.add_argument("--normalization", required=True)
    verify_applied_mapped_data.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

    market_data_source = sub.add_parser(
        "plan-market-data-source",
        help="Validate a file, Arrow.money, or iRage market-data source plan without storing credentials.",
    )
    market_data_source.add_argument("--out", required=True)
    market_data_source.add_argument("--provider", default="file_replay")
    market_data_source.add_argument("--adapter", default="")
    market_data_source.add_argument("--kind", default="ticks", choices=["ticks", "chain"])
    market_data_source.add_argument("--transport", default="file", choices=["file", "rest", "websocket"])
    market_data_source.add_argument("--source-uri", required=True)
    market_data_source.add_argument("--market", default="india_nse_index_derivatives")
    market_data_source.add_argument("--exchange", default="NFO")
    market_data_source.add_argument("--session-timezone", default="")
    market_data_source.add_argument("--session-open", default="")
    market_data_source.add_argument("--session-close", default="")
    market_data_source.add_argument("--auth-env", action="append", dest="auth_envs")
    market_data_source.add_argument("--label", default="")
    market_data_source.add_argument("--fail-on-breach", action="store_true")
    market_data_source.add_argument("--fail-on-blocked-actions", action="store_true")
    market_data_source.add_argument("--fail-on-actions", action="store_true")

    market_data_fetch = sub.add_parser(
        "plan-market-data-fetch",
        help="Plan a dry-run provider fetch from a market-data source plan without calling APIs or storing credentials.",
    )
    market_data_fetch.add_argument("--source-plan", required=True)
    market_data_fetch.add_argument("--out", required=True)
    market_data_fetch.add_argument("--symbol", action="append", dest="symbols")
    market_data_fetch.add_argument("--window-start", default="")
    market_data_fetch.add_argument("--window-end", default="")
    market_data_fetch.add_argument("--poll-interval-ms", type=int, default=1000)
    market_data_fetch.add_argument("--max-latency-ms", type=int, default=250)
    market_data_fetch.add_argument("--expected-market", default="india_nse_index_derivatives")
    market_data_fetch.add_argument("--output-file", default="provider_market_data.csv")
    market_data_fetch.add_argument("--fail-on-breach", action="store_true")
    market_data_fetch.add_argument("--fail-on-blocked-actions", action="store_true")
    market_data_fetch.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_fetcher = sub.add_parser(
        "plan-provider-market-data-fetcher",
        help="Prepare a dry-run provider fetcher request template from a market-data fetch plan.",
    )
    provider_market_data_fetcher.add_argument("--fetch-plan", required=True)
    provider_market_data_fetcher.add_argument("--out", required=True)
    provider_market_data_fetcher.add_argument("--require-env-present", action="store_true")
    provider_market_data_fetcher.add_argument("--connect-timeout-ms", type=int, default=5000)
    provider_market_data_fetcher.add_argument("--read-timeout-ms", type=int, default=1000)
    provider_market_data_fetcher.add_argument("--heartbeat-timeout-ms", type=int, default=30000)
    provider_market_data_fetcher.add_argument("--max-reconnects", type=int, default=3)
    provider_market_data_fetcher.add_argument("--batch-size", type=int, default=5000)
    provider_market_data_fetcher.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_fetcher.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_fetcher.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_client = sub.add_parser(
        "prepare-provider-market-data-client",
        help="Prepare a dry-run provider market-data client packet from a fetcher request template.",
    )
    provider_market_data_client.add_argument("--fetcher-plan", required=True)
    provider_market_data_client.add_argument("--out", required=True)
    provider_market_data_client.add_argument("--require-env-present", action="store_true")
    provider_market_data_client.add_argument("--session-label", default="")
    provider_market_data_client.add_argument("--max-clock-skew-ms", type=int, default=250)
    provider_market_data_client.add_argument("--max-local-buffer-rows", type=int, default=100000)
    provider_market_data_client.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_client.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_client.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_live_session = sub.add_parser(
        "plan-provider-market-data-live-session",
        help="Create a credential-safe live capture session plan from a provider client packet.",
    )
    provider_market_data_live_session.add_argument("--client-packet", required=True)
    provider_market_data_live_session.add_argument("--out", required=True)
    provider_market_data_live_session.add_argument("--trade-date", required=True)
    provider_market_data_live_session.add_argument("--window", action="append", dest="windows")
    provider_market_data_live_session.add_argument("--capture-dir", default="captures/provider_market_data")
    provider_market_data_live_session.add_argument("--batch-output-dir", default="")
    provider_market_data_live_session.add_argument("--min-capture-rows", type=int, default=1)
    provider_market_data_live_session.add_argument("--pipeline-min-rows", type=int, default=1)
    provider_market_data_live_session.add_argument("--tick-size", type=float, default=None)
    provider_market_data_live_session.add_argument("--max-off-tick-price-rows", type=int, default=None)
    provider_market_data_live_session.add_argument("--max-p99-gap-ns", type=float, default=None)
    provider_market_data_live_session.add_argument("--max-median-spread-ticks", type=float, default=None)
    provider_market_data_live_session.add_argument("--require-env-present", action="store_true")
    provider_market_data_live_session.add_argument("--allow-weekend", action="store_true")
    _add_market_calendar_arg(provider_market_data_live_session)
    provider_market_data_live_session.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_live_session.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_live_session.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_live_preflight = sub.add_parser(
        "preflight-provider-market-data-live-session",
        help="Verify a live session packet, runtime credentials, output paths, and timing before provider capture.",
    )
    provider_market_data_live_preflight.add_argument("--live-session-packet", required=True)
    provider_market_data_live_preflight.add_argument("--out", required=True)
    provider_market_data_live_preflight.add_argument("--require-env-present", action="store_true")
    provider_market_data_live_preflight.add_argument("--now-iso", default="")
    provider_market_data_live_preflight.add_argument("--allow-existing-captures", action="store_true")
    provider_market_data_live_preflight.add_argument("--allow-existing-batch", action="store_true")
    provider_market_data_live_preflight.add_argument("--no-require-before-last-window", action="store_true")
    provider_market_data_live_preflight.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_live_preflight.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_live_preflight.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_live_bundle = sub.add_parser(
        "bundle-provider-market-data-live-capture",
        help="Build a credential-safe per-window provider adapter capture bundle from a live session packet.",
    )
    provider_market_data_live_bundle.add_argument("--live-session-packet", required=True)
    provider_market_data_live_bundle.add_argument("--out", required=True)
    provider_market_data_live_bundle.add_argument("--preflight-config", default="")
    provider_market_data_live_bundle.add_argument("--adapter-command-template", default="")
    provider_market_data_live_bundle.add_argument("--ingest-output-dir", default="")
    provider_market_data_live_bundle.add_argument("--no-require-preflight-ready", action="store_true")
    provider_market_data_live_bundle.add_argument("--require-env-present", action="store_true")
    provider_market_data_live_bundle.add_argument("--allow-existing-captures", action="store_true")
    provider_market_data_live_bundle.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_live_bundle.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_live_bundle.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_live_rehearsal = sub.add_parser(
        "rehearse-provider-market-data-live-capture",
        help="Write synthetic normalized captures from a live capture bundle and optionally run live ingest as a rehearsal.",
    )
    provider_market_data_live_rehearsal.add_argument("--capture-bundle", required=True)
    provider_market_data_live_rehearsal.add_argument("--out", required=True)
    provider_market_data_live_rehearsal.add_argument("--rows-per-window", type=int, default=5)
    provider_market_data_live_rehearsal.add_argument("--base-price", type=float, default=100.0)
    provider_market_data_live_rehearsal.add_argument("--tick-size", type=float, default=0.05)
    provider_market_data_live_rehearsal.add_argument("--overwrite-captures", action="store_true")
    provider_market_data_live_rehearsal.add_argument("--no-run-ingest", action="store_true")
    provider_market_data_live_rehearsal.add_argument("--ingest-output-dir", default="")
    provider_market_data_live_rehearsal.add_argument("--ingest-min-capture-rows", type=int, default=1)
    provider_market_data_live_rehearsal.add_argument("--ingest-pipeline-min-rows", type=int, default=1)
    provider_market_data_live_rehearsal.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_live_rehearsal.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_live_rehearsal.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_live_ingest = sub.add_parser(
        "ingest-provider-market-data-live-session",
        help="Verify live-session capture files and run provider batch ingestion from the session packet.",
    )
    provider_market_data_live_ingest.add_argument("--live-session-packet", required=True)
    provider_market_data_live_ingest.add_argument("--out", required=True)
    provider_market_data_live_ingest.add_argument("--capture-bundle", default="")
    provider_market_data_live_ingest.add_argument("--batch-output-dir", default="")
    provider_market_data_live_ingest.add_argument("--min-capture-rows", type=int, default=None)
    provider_market_data_live_ingest.add_argument("--pipeline-min-rows", type=int, default=None)
    provider_market_data_live_ingest.add_argument("--tick-size", type=float, default=None)
    provider_market_data_live_ingest.add_argument("--max-off-tick-price-rows", type=int, default=None)
    provider_market_data_live_ingest.add_argument("--max-p99-gap-ns", type=float, default=None)
    provider_market_data_live_ingest.add_argument("--max-median-spread-ticks", type=float, default=None)
    provider_market_data_live_ingest.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_live_ingest.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_live_ingest.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_live_evidence = sub.add_parser(
        "review-provider-market-data-live-evidence",
        help="Review live provider ingest artifacts and block synthetic rehearsal captures from research evidence.",
    )
    provider_market_data_live_evidence.add_argument("--live-ingest-dir", required=True)
    provider_market_data_live_evidence.add_argument("--out", required=True)
    provider_market_data_live_evidence.add_argument("--allow-synthetic-rehearsal", action="store_true")
    provider_market_data_live_evidence.add_argument("--no-require-ingest-ready", action="store_true")
    provider_market_data_live_evidence.add_argument("--no-require-batch-ready", action="store_true")
    provider_market_data_live_evidence.add_argument("--no-require-manifest", action="store_true")
    provider_market_data_live_evidence.add_argument("--min-capture-rows", type=int, default=1)
    provider_market_data_live_evidence.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_live_evidence.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_live_evidence.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_research_handoff = sub.add_parser(
        "handoff-provider-market-data-research",
        help="Turn research-ready provider live evidence into concrete strategy walk-forward command plans.",
    )
    provider_market_data_research_handoff.add_argument("--live-evidence-dir", required=True)
    provider_market_data_research_handoff.add_argument("--out", required=True)
    provider_market_data_research_handoff.add_argument("--strategy", action="append", dest="strategies")
    provider_market_data_research_handoff.add_argument("--no-require-research-ready", action="store_true")
    provider_market_data_research_handoff.add_argument("--allow-synthetic-smoke", action="store_true")
    provider_market_data_research_handoff.add_argument("--min-tick-folds", type=int, default=2)
    provider_market_data_research_handoff.add_argument("--tick-size", type=float, default=0.05)
    provider_market_data_research_handoff.add_argument("--market", default="")
    provider_market_data_research_handoff.add_argument("--instrument-id", default="PROVIDER_BOOK")
    provider_market_data_research_handoff.add_argument("--output-root", default="runs/provider_market_data_research")
    provider_market_data_research_handoff.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_research_handoff.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_research_handoff.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_research = sub.add_parser(
        "run-provider-market-data-imbalance-research",
        help="Run the full imbalance research pipeline from research-ready provider live evidence.",
    )
    provider_market_data_imbalance_research.add_argument("--live-evidence-dir", required=True)
    provider_market_data_imbalance_research.add_argument("--out", required=True)
    provider_market_data_imbalance_research.add_argument("--no-require-research-ready", action="store_true")
    provider_market_data_imbalance_research.add_argument("--allow-synthetic-smoke", action="store_true")
    provider_market_data_imbalance_research.add_argument("--min-tick-folds", type=int, default=2)
    provider_market_data_imbalance_research.add_argument("--tick-size", type=float, default=0.05)
    provider_market_data_imbalance_research.add_argument("--market", default="")
    provider_market_data_imbalance_research.add_argument("--instrument-id", default="PROVIDER_BOOK")
    provider_market_data_imbalance_research.add_argument(
        "--instrument-kind",
        default="FUT",
        choices=["FUT", "OPT", "EQ"],
    )
    provider_market_data_imbalance_research.add_argument("--lot-size", type=int, default=75)
    provider_market_data_imbalance_research.add_argument("--qty", type=int, default=75)
    provider_market_data_imbalance_research.add_argument(
        "--entry-imbalance",
        nargs="+",
        type=float,
        default=list(ProviderMarketDataImbalanceResearchConfig().entry_imbalance_values),
    )
    provider_market_data_imbalance_research.add_argument(
        "--min-microprice-edge-ticks",
        nargs="+",
        type=float,
        default=list(ProviderMarketDataImbalanceResearchConfig().min_microprice_edge_ticks_values),
    )
    provider_market_data_imbalance_research.add_argument(
        "--forward-horizon-ns",
        nargs="+",
        type=int,
        default=list(ProviderMarketDataImbalanceResearchConfig().forward_horizon_ns_values),
    )
    provider_market_data_imbalance_research.add_argument("--max-spread-ticks", type=float, default=2.0)
    provider_market_data_imbalance_research.add_argument("--min-depth", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--min-signals", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--min-direction-count", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--min-mean-forward-edge-ticks", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--min-win-rate", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--min-median-forward-edge-ticks", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--no-filter-session", action="store_true")
    provider_market_data_imbalance_research.add_argument("--timestamp-unit", default="ns")
    provider_market_data_imbalance_research.add_argument("--timestamp-tz", default=None)
    provider_market_data_imbalance_research.add_argument("--min-passed-configs", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--min-best-usable-signals", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--min-best-mean-forward-edge-ticks", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--min-best-win-rate", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--min-selection-sweeps", type=int, default=None)
    provider_market_data_imbalance_research.add_argument("--min-selection-pass-rate", type=float, default=1.0)
    provider_market_data_imbalance_research.add_argument("--min-selection-median-usable-signals", type=float, default=1.0)
    provider_market_data_imbalance_research.add_argument(
        "--min-selection-median-mean-forward-edge-ticks",
        type=float,
        default=0.0,
    )
    provider_market_data_imbalance_research.add_argument("--min-selection-min-win-rate", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--min-selection-median-robust-score", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--min-edge-folds", type=int, default=None)
    provider_market_data_imbalance_research.add_argument("--min-passed-edge-sweeps", type=int, default=None)
    provider_market_data_imbalance_research.add_argument("--allow-unselected", action="store_true")
    provider_market_data_imbalance_research.add_argument("--exit-imbalance", type=float, default=0.15)
    provider_market_data_imbalance_research.add_argument("--cooloff-ns", type=int, default=0)
    provider_market_data_imbalance_research.add_argument("--feed-latency-us", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--order-latency-us", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--max-position-lots", type=int, default=20)
    provider_market_data_imbalance_research.add_argument("--min-net-pnl", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--min-fills", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--max-drawdown", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--max-otr", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--min-markout-mean", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--min-replay-folds", type=int, default=None)
    provider_market_data_imbalance_research.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    provider_market_data_imbalance_research.add_argument("--min-total-fills", type=int, default=1)
    provider_market_data_imbalance_research.add_argument("--min-total-net-pnl", type=float, default=0.0)
    provider_market_data_imbalance_research.add_argument("--max-worst-drawdown", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--min-median-markout-mean", type=float, default=None)
    provider_market_data_imbalance_research.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_research.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_research.add_argument("--fail-on-actions", action="store_true")
    _add_generic_cost_args(provider_market_data_imbalance_research)

    provider_market_data_imbalance_evidence = sub.add_parser(
        "review-provider-market-data-imbalance-evidence",
        help="Catalog and gate provider live-data imbalance research evidence before broker launch packaging.",
    )
    provider_market_data_imbalance_evidence.add_argument("--provider-research-dir", required=True)
    provider_market_data_imbalance_evidence.add_argument("--out", required=True)
    provider_market_data_imbalance_evidence.add_argument("--no-require-provider-research-ready", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--no-require-strategy-evidence-ready", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--allow-dirty-git", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--require-same-git-commit", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--no-require-same-strategy", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--no-require-same-market", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--expected-market", default="")
    provider_market_data_imbalance_evidence.add_argument("--min-passed-per-type", type=int, default=1)
    provider_market_data_imbalance_evidence.add_argument("--require-file-inputs", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_evidence.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_launch = sub.add_parser(
        "pipeline-provider-market-data-imbalance-launch",
        help="Build broker launch artifacts from a ready provider live-data imbalance evidence review.",
    )
    provider_market_data_imbalance_launch.add_argument("--provider-evidence-dir", required=True)
    provider_market_data_imbalance_launch.add_argument("--out", required=True)
    provider_market_data_imbalance_launch.add_argument("--no-require-provider-evidence-ready", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--no-require-launch-ready", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--adapter", default="arrow_money")
    provider_market_data_imbalance_launch.add_argument("--mode", default="shadow", choices=["paper", "shadow"])
    provider_market_data_imbalance_launch.add_argument("--route-tag", default=None)
    provider_market_data_imbalance_launch.add_argument("--instrument-id", default="BOOK")
    provider_market_data_imbalance_launch.add_argument("--qty", type=int, default=None)
    provider_market_data_imbalance_launch.add_argument("--reference-price", type=float, default=None)
    provider_market_data_imbalance_launch.add_argument("--buy-limit-price", type=float, default=None)
    provider_market_data_imbalance_launch.add_argument("--sell-limit-price", type=float, default=None)
    provider_market_data_imbalance_launch.add_argument("--entry-offset-ticks", type=float, default=0.0)
    provider_market_data_imbalance_launch.add_argument("--tick-size", type=float, default=None)
    provider_market_data_imbalance_launch.add_argument("--max-order-qty", type=int, default=None)
    provider_market_data_imbalance_launch.add_argument("--max-notional", type=float, default=None)
    provider_market_data_imbalance_launch.add_argument("--price-band-pct", type=float, default=None)
    provider_market_data_imbalance_launch.add_argument("--max-orders", type=int, default=None)
    provider_market_data_imbalance_launch.add_argument("--contract-multiplier", type=float, default=1.0)
    provider_market_data_imbalance_launch.add_argument("--product", default="MIS")
    provider_market_data_imbalance_launch.add_argument("--exchange", default="NFO")
    provider_market_data_imbalance_launch.add_argument("--broker-schema-audit", default=None)
    provider_market_data_imbalance_launch.add_argument("--broker-mapping-draft", default=None)
    provider_market_data_imbalance_launch.add_argument("--broker-mapped-orders", default=None)
    provider_market_data_imbalance_launch.add_argument("--broker-halt-export", default=None)
    provider_market_data_imbalance_launch.add_argument("--broker-reconciliation", default=None)
    provider_market_data_imbalance_launch.add_argument("--broker-runtime-session", default=None)
    provider_market_data_imbalance_launch.add_argument("--broker-vendor-data-readiness", default=None)
    provider_market_data_imbalance_launch.add_argument("--require-broker-schema-audit", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--require-broker-mapping-draft", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--require-broker-mapped-orders", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--require-broker-halt-export", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--require-broker-reconciliation", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--require-broker-runtime-session", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--allow-placeholder-schema", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_launch.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_launch_evidence = sub.add_parser(
        "review-provider-market-data-imbalance-launch-evidence",
        help="Review provider imbalance launch packets against the full launch-ready imbalance evidence profile.",
    )
    provider_market_data_imbalance_launch_evidence.add_argument("--provider-launch-dir", required=True)
    provider_market_data_imbalance_launch_evidence.add_argument("--out", required=True)
    provider_market_data_imbalance_launch_evidence.add_argument("--no-require-provider-launch-ready", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--no-require-strategy-evidence-ready", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--allow-dirty-git", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--require-same-git-commit", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--no-require-same-strategy", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--no-require-same-market", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--expected-market", default="")
    provider_market_data_imbalance_launch_evidence.add_argument("--min-passed-per-type", type=int, default=1)
    provider_market_data_imbalance_launch_evidence.add_argument("--require-file-inputs", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--require-no-placeholder-schema", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--require-no-blocked-placeholder-schema", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_launch_evidence.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_scorecard = sub.add_parser(
        "score-provider-market-data-imbalance-readiness",
        help="Score a provider live-data imbalance launch-evidence review for shadow scale-up readiness.",
    )
    provider_market_data_imbalance_scorecard.add_argument("--provider-launch-evidence-dir", required=True)
    provider_market_data_imbalance_scorecard.add_argument("--out", required=True)
    provider_market_data_imbalance_scorecard.add_argument("--no-require-launch-evidence-ready", action="store_true")
    provider_market_data_imbalance_scorecard.add_argument("--no-require-scorecard-ready", action="store_true")
    provider_market_data_imbalance_scorecard.add_argument("--allow-dirty-git", action="store_true")
    provider_market_data_imbalance_scorecard.add_argument("--market", default="")
    provider_market_data_imbalance_scorecard.add_argument("--require-file-inputs", action="store_true")
    provider_market_data_imbalance_scorecard.add_argument("--research-family", default=None)
    provider_market_data_imbalance_scorecard.add_argument(
        "--require-research-family",
        action="store_true",
    )
    provider_market_data_imbalance_scorecard.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_scorecard.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_scorecard.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_route_readiness = sub.add_parser(
        "review-provider-market-data-imbalance-route-readiness",
        help="Build provider imbalance route-readiness evidence before shadow scale-up planning.",
    )
    provider_market_data_imbalance_route_readiness.add_argument("--provider-launch-evidence-dir", required=True)
    provider_market_data_imbalance_route_readiness.add_argument("--out", required=True)
    provider_market_data_imbalance_route_readiness.add_argument("--market-portability", default=None)
    provider_market_data_imbalance_route_readiness.add_argument("--strategy-evidence", default=None)
    provider_market_data_imbalance_route_readiness.add_argument("--ops-evidence", action="append", dest="ops_evidence")
    provider_market_data_imbalance_route_readiness.add_argument(
        "--no-require-provider-launch-evidence-ready",
        action="store_true",
    )
    provider_market_data_imbalance_route_readiness.add_argument(
        "--no-require-route-readiness-ready",
        action="store_true",
    )
    provider_market_data_imbalance_route_readiness.add_argument("--no-provider-launch-evidence-inputs", action="store_true")
    provider_market_data_imbalance_route_readiness.add_argument("--market", default="")
    provider_market_data_imbalance_route_readiness.add_argument("--strategy", default="microprice_imbalance")
    provider_market_data_imbalance_route_readiness.add_argument("--allow-non-file-ops-inputs", action="store_true")
    provider_market_data_imbalance_route_readiness.add_argument("--no-build-market-portability", action="store_true")
    provider_market_data_imbalance_route_readiness.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_route_readiness.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_route_readiness.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_scaleup = sub.add_parser(
        "plan-provider-market-data-imbalance-scaleup",
        help="Infer provider imbalance evidence/launch paths and create a shadow scale-up plan.",
    )
    provider_market_data_imbalance_scaleup.add_argument("--scorecard", required=True)
    provider_market_data_imbalance_scaleup.add_argument("--shadow-comparison", required=True)
    provider_market_data_imbalance_scaleup.add_argument("--out", required=True)
    provider_market_data_imbalance_scaleup.add_argument("--order-exposure", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--proof-refresh", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--instrument-metadata", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--data-readiness", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--data-readiness-comparison", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--strategy-portfolio", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--route-readiness", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--broker-readiness", default=None)
    provider_market_data_imbalance_scaleup.add_argument("--no-require-scorecard-ready", action="store_true")
    provider_market_data_imbalance_scaleup.add_argument("--no-require-scaleup-ready", action="store_true")
    _add_scaleup_threshold_args(provider_market_data_imbalance_scaleup)
    provider_market_data_imbalance_scaleup.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_scaleup.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_scaleup.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_runtime_telemetry = sub.add_parser(
        "build-provider-market-data-imbalance-runtime-telemetry",
        help="Build guard-ready runtime telemetry from a provider imbalance scale-up wrapper.",
    )
    provider_market_data_imbalance_runtime_telemetry.add_argument("--scaleup", required=True)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--out", required=True)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--export", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--upload-pack", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--reconciliation", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--instrument-metadata", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--pnl", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--open-orders", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--positions", default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--snapshot-ts-ns", type=float, default=None)
    provider_market_data_imbalance_runtime_telemetry.add_argument("--no-require-provider-scaleup-ready", action="store_true")
    provider_market_data_imbalance_runtime_telemetry.add_argument("--no-require-runtime-telemetry-ready", action="store_true")
    provider_market_data_imbalance_runtime_telemetry.add_argument("--no-use-launch-pipeline-broker-inputs", action="store_true")
    provider_market_data_imbalance_runtime_telemetry.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_runtime_telemetry.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_runtime_telemetry.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_runtime_guard = sub.add_parser(
        "monitor-provider-market-data-imbalance-runtime-guard",
        help="Run the runtime guard from provider imbalance telemetry and emit provider actions.",
    )
    provider_market_data_imbalance_runtime_guard.add_argument("--runtime-telemetry", required=True)
    provider_market_data_imbalance_runtime_guard.add_argument("--out", required=True)
    provider_market_data_imbalance_runtime_guard.add_argument("--as-of-ts-ns", type=float, default=None)
    provider_market_data_imbalance_runtime_guard.add_argument("--max-telemetry-age-ns", type=float, default=None)
    provider_market_data_imbalance_runtime_guard.add_argument(
        "--no-require-provider-runtime-telemetry-ready",
        action="store_true",
    )
    provider_market_data_imbalance_runtime_guard.add_argument("--require-runtime-guard-continue", action="store_true")
    provider_market_data_imbalance_runtime_guard.add_argument("--fail-on-halt", action="store_true")
    provider_market_data_imbalance_runtime_guard.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_runtime_guard.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_runtime_guard.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_runtime_session = sub.add_parser(
        "monitor-provider-market-data-imbalance-runtime-session",
        help="Run provider imbalance runtime session monitoring from provider guard output.",
    )
    provider_market_data_imbalance_runtime_session.add_argument("--runtime-guard", required=True)
    provider_market_data_imbalance_runtime_session.add_argument("--out", required=True)
    provider_market_data_imbalance_runtime_session.add_argument("--export", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--upload-pack", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--reconciliation", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--instrument-metadata", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--pnl", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--open-orders", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--positions", default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--snapshot-ts-ns", type=float, default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--as-of-ts-ns", type=float, default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--max-telemetry-age-ns", type=float, default=None)
    provider_market_data_imbalance_runtime_session.add_argument("--skip-halt-response", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--allow-missing-flatten-prices", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--default-order-type", default="LIMIT")
    provider_market_data_imbalance_runtime_session.add_argument("--default-time-in-force", default="DAY")
    provider_market_data_imbalance_runtime_session.add_argument("--no-require-provider-runtime-guard-ready", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--require-runtime-session-continue", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--no-require-halt-response-ready", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--no-use-provider-runtime-telemetry-inputs", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--fail-on-halt", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_runtime_session.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_broker_readiness = sub.add_parser(
        "review-provider-market-data-imbalance-broker-readiness",
        help="Gate provider imbalance runtime-session evidence for broker cutover readiness.",
    )
    provider_market_data_imbalance_broker_readiness.add_argument("--runtime-session", required=True)
    provider_market_data_imbalance_broker_readiness.add_argument("--out", required=True)
    provider_market_data_imbalance_broker_readiness.add_argument("--schema-audit", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--order-export", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--mapping-draft", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--mapped-orders", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--upload-pack", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--halt-export", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--reconciliation", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--resume-gate", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--dispatch-roundtrip", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--vendor-market-data-batch", default=None)
    provider_market_data_imbalance_broker_readiness.add_argument("--adapter", default="")
    provider_market_data_imbalance_broker_readiness.add_argument("--expected-market", default="")
    provider_market_data_imbalance_broker_readiness.add_argument(
        "--expected-vendor-data-kind",
        default="ticks",
        choices=["ticks", "chain"],
    )
    provider_market_data_imbalance_broker_readiness.add_argument("--require-reviewed-schema", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-schema-audit", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--skip-order-export", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-mapping-draft", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-mapped-orders", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--skip-upload-pack", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-halt-export", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-reconciliation", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--skip-runtime-session", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-resume-gate", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-route-readiness", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--require-dispatch-roundtrip", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--allow-adapter-mismatch", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument(
        "--no-require-provider-runtime-session-ready",
        action="store_true",
    )
    provider_market_data_imbalance_broker_readiness.add_argument(
        "--no-require-broker-readiness-ready",
        action="store_true",
    )
    provider_market_data_imbalance_broker_readiness.add_argument(
        "--no-use-provider-runtime-session-inputs",
        action="store_true",
    )
    provider_market_data_imbalance_broker_readiness.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_broker_readiness.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_cutover = sub.add_parser(
        "review-provider-market-data-imbalance-cutover",
        help="Gate provider imbalance broker-readiness evidence for cutover and route-enable handoff.",
    )
    provider_market_data_imbalance_cutover.add_argument("--broker-readiness", required=True)
    provider_market_data_imbalance_cutover.add_argument("--out", required=True)
    provider_market_data_imbalance_cutover.add_argument("--scaleup", default=None)
    provider_market_data_imbalance_cutover.add_argument("--nested-broker-readiness", default=None)
    provider_market_data_imbalance_cutover.add_argument("--runtime-session", default=None)
    provider_market_data_imbalance_cutover.add_argument("--operator-review", default=None)
    provider_market_data_imbalance_cutover.add_argument(
        "--target-mode",
        default="",
        choices=["", "paper", "shadow", "live_dryrun"],
    )
    provider_market_data_imbalance_cutover.add_argument("--allow-unready-provider-broker-readiness", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--allow-unready-cutover", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--allow-unready-scaleup", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--allow-missing-broker-readiness", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--allow-missing-runtime-session", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--allow-runtime-guard-halt", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--require-route-readiness", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--allow-missing-route-readiness", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--require-resume-gate", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--require-dispatch-roundtrip", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--require-operator-approval", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--require-operator-identity-ack", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--require-operator-limits-ack", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--no-use-provider-broker-readiness-inputs", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--max-failed-scaleup-checks", type=int, default=0)
    provider_market_data_imbalance_cutover.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_cutover.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_route_enable = sub.add_parser(
        "review-provider-market-data-imbalance-route-enable",
        help="Gate provider imbalance cutover evidence for route enable and broker dispatch planning.",
    )
    provider_market_data_imbalance_route_enable.add_argument("--provider-cutover", required=True)
    provider_market_data_imbalance_route_enable.add_argument("--out", required=True)
    provider_market_data_imbalance_route_enable.add_argument("--cutover", default=None)
    provider_market_data_imbalance_route_enable.add_argument("--upload-pack", default=None)
    provider_market_data_imbalance_route_enable.add_argument("--order-export", default=None)
    provider_market_data_imbalance_route_enable.add_argument(
        "--target-mode",
        default="",
        choices=["", "paper", "shadow", "live_dryrun"],
    )
    provider_market_data_imbalance_route_enable.add_argument(
        "--allow-unready-provider-cutover",
        action="store_true",
    )
    provider_market_data_imbalance_route_enable.add_argument("--allow-unready-route-enable", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--allow-unready-cutover", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--allow-unready-upload", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--require-order-export", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--require-route-readiness", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--require-dispatch-roundtrip", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--allow-adapter-mismatch", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--no-use-provider-cutover-inputs", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--min-orders", type=int, default=1)
    provider_market_data_imbalance_route_enable.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_route_enable.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_broker_dispatch = sub.add_parser(
        "plan-provider-market-data-imbalance-broker-dispatch",
        help="Plan provider imbalance broker dispatch from a provider route-enable wrapper.",
    )
    provider_market_data_imbalance_broker_dispatch.add_argument("--provider-route-enable", required=True)
    provider_market_data_imbalance_broker_dispatch.add_argument("--out", required=True)
    provider_market_data_imbalance_broker_dispatch.add_argument("--route-enable", default=None)
    provider_market_data_imbalance_broker_dispatch.add_argument("--upload-pack", default=None)
    provider_market_data_imbalance_broker_dispatch.add_argument("--upload-orders", default=None)
    provider_market_data_imbalance_broker_dispatch.add_argument(
        "--target-mode",
        default="",
        choices=["", "paper", "shadow", "live_dryrun"],
    )
    provider_market_data_imbalance_broker_dispatch.add_argument(
        "--allow-unready-provider-route-enable",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch.add_argument(
        "--allow-unready-broker-dispatch",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch.add_argument("--allow-disabled-route", action="store_true")
    provider_market_data_imbalance_broker_dispatch.add_argument("--allow-non-dry-run", action="store_true")
    provider_market_data_imbalance_broker_dispatch.add_argument("--require-route-readiness", action="store_true")
    provider_market_data_imbalance_broker_dispatch.add_argument("--require-dispatch-roundtrip", action="store_true")
    provider_market_data_imbalance_broker_dispatch.add_argument(
        "--no-use-provider-route-enable-inputs",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch.add_argument("--min-orders", type=int, default=1)
    provider_market_data_imbalance_broker_dispatch.add_argument("--max-orders", type=int, default=None)
    provider_market_data_imbalance_broker_dispatch.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_broker_dispatch.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_broker_dispatch.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_broker_dispatch_send = sub.add_parser(
        "prepare-provider-market-data-imbalance-broker-dispatch-send",
        help="Prepare a provider imbalance non-submitting broker dispatch send packet.",
    )
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--provider-broker-dispatch", required=True)
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--out", required=True)
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--broker-dispatch", default=None)
    provider_market_data_imbalance_broker_dispatch_send.add_argument(
        "--target-mode",
        default="",
        choices=["", "paper", "shadow", "live_dryrun"],
    )
    provider_market_data_imbalance_broker_dispatch_send.add_argument(
        "--allow-unready-provider-broker-dispatch",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_send.add_argument(
        "--allow-unready-broker-dispatch-send",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--allow-unready-dispatch", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--allow-unarmed-dispatch", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--allow-non-dry-run", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--require-route-readiness", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--require-dispatch-roundtrip", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument(
        "--no-use-provider-broker-dispatch-inputs",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--max-requests", type=int, default=None)
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_broker_dispatch_send.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_broker_dispatch_ack = sub.add_parser(
        "reconcile-provider-market-data-imbalance-broker-dispatch",
        help="Reconcile provider imbalance broker dispatch acknowledgements.",
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--provider-broker-dispatch-send", required=True)
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--acks", required=True)
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--out", required=True)
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--broker-dispatch", default=None)
    provider_market_data_imbalance_broker_dispatch_ack.add_argument(
        "--allow-unready-provider-broker-dispatch-send",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument(
        "--allow-failed-broker-dispatch-ack",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--allow-unready-dispatch", action="store_true")
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--allow-missing-acks", action="store_true")
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--allow-rejections", action="store_true")
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--require-route-readiness", action="store_true")
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--require-dispatch-roundtrip", action="store_true")
    provider_ack_send_lineage = (
        provider_market_data_imbalance_broker_dispatch_ack.add_mutually_exclusive_group()
    )
    provider_ack_send_lineage.add_argument(
        "--require-send-packet",
        action="store_true",
        default=True,
        help="Require the complete current broker send packet (default).",
    )
    provider_ack_send_lineage.add_argument(
        "--allow-legacy-send-lineage",
        dest="require_send_packet",
        action="store_false",
        help="Allow audited legacy acknowledgement input without send lineage.",
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument(
        "--lineage-migration-audit",
        default=None,
        help="Current exact-source migration audit required by the legacy override.",
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument(
        "--no-use-provider-broker-dispatch-send-inputs",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument(
        "--max-duplicate-ack-orders",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--max-unmatched-acks", type=int, default=0)
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_imbalance_broker_dispatch_ack.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_broker_dispatch_roundtrip = sub.add_parser(
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
        help="Review provider imbalance broker dispatch send/ack round-trip proof.",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--provider-broker-dispatch-ack",
        required=True,
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--out", required=True)
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--broker-dispatch", default=None)
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--broker-dispatch-send", default=None)
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--broker-dispatch-ack", default=None)
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--allow-unready-provider-broker-dispatch-ack",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--allow-failed-broker-dispatch-roundtrip",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--target-mode",
        default="",
        choices=["", "paper", "shadow", "live_dryrun"],
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--allow-unready-dispatch",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--allow-unready-send", action="store_true")
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--allow-failed-ack", action="store_true")
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--allow-identity-mismatch",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--allow-submission-enabled",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--allow-missing-request-acks",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--allow-rejections", action="store_true")
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--require-route-readiness",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--require-dispatch-roundtrip",
        action="store_true",
    )
    provider_roundtrip_ack_lineage = (
        provider_market_data_imbalance_broker_dispatch_roundtrip.add_mutually_exclusive_group()
    )
    provider_roundtrip_ack_lineage.add_argument(
        "--require-ack-lineage",
        action="store_true",
        default=True,
        help="Require complete current acknowledgement lineage (default).",
    )
    provider_roundtrip_ack_lineage.add_argument(
        "--allow-legacy-ack-lineage",
        dest="require_ack_lineage",
        action="store_false",
        help="Allow an audited legacy acknowledgement without strict lineage.",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--lineage-migration-audit",
        default=None,
        help="Current exact-source migration audit required by the legacy override.",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--no-use-provider-broker-dispatch-ack-inputs",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--max-duplicate-ack-orders",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--max-unmatched-acks", type=int, default=0)
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--max-missing-request-acks",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--max-total-failed-component-checks",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_market_data_imbalance_broker_dispatch_roundtrip.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_imbalance_broker_rehearsal_certificate = sub.add_parser(
        "certify-provider-market-data-imbalance-broker-rehearsal",
        help="Issue a content-addressed, non-submitting certificate for a provider broker rehearsal.",
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--provider-broker-dispatch-roundtrip",
        required=True,
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument("--out", required=True)
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--require-sealed-provider-receipts",
        action="store_true",
    )
    certificate_ack_lineage = (
        provider_market_data_imbalance_broker_rehearsal_certificate.add_mutually_exclusive_group()
    )
    certificate_ack_lineage.add_argument(
        "--require-ack-lineage",
        action="store_true",
        default=True,
        help="Require complete current acknowledgement lineage (default).",
    )
    certificate_ack_lineage.add_argument(
        "--allow-legacy-ack-lineage",
        dest="require_ack_lineage",
        action="store_false",
        help="Allow an audited legacy rehearsal without strict acknowledgement lineage.",
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--lineage-migration-audit",
        default=None,
        help="Current exact-source migration audit required by the legacy override.",
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--allow-recorded-dirty-git",
        action="store_true",
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--max-manifests",
        type=int,
        default=64,
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_market_data_imbalance_broker_rehearsal_certificate.add_argument(
        "--fail-on-actions",
        action="store_true",
    )

    provider_market_data_imbalance_release_review = sub.add_parser(
        "prepare-provider-market-data-imbalance-release-review",
        help=(
            "Prepare a non-submitting live-dry-run operator review packet "
            "from verified provider strategy evidence."
        ),
    )
    provider_market_data_imbalance_release_review.add_argument(
        "--strategy-evidence",
        required=True,
    )
    provider_market_data_imbalance_release_review.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_release_review.add_argument(
        "--max-dependencies",
        type=int,
        default=1024,
    )
    provider_market_data_imbalance_release_review.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_release_review.add_argument(
        "--fail-on-actions",
        action="store_true",
    )
    verify_provider_market_data_imbalance_release_review_parser = (
        sub.add_parser(
            "verify-provider-market-data-imbalance-release-review",
            help=(
                "Reopen a provider release-review packet and its verified "
                "strategy-evidence source."
            ),
        )
    )
    verify_provider_market_data_imbalance_release_review_parser.add_argument(
        "--release-review",
        required=True,
    )
    verify_provider_market_data_imbalance_release_review_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_release_decision = sub.add_parser(
        "finalize-provider-market-data-imbalance-release-decision",
        help=(
            "Seal a separate operator decision against a current provider "
            "live-dry-run release-review packet."
        ),
    )
    provider_market_data_imbalance_release_decision.add_argument(
        "--release-review",
        required=True,
    )
    provider_market_data_imbalance_release_decision.add_argument(
        "--operator-decision",
        required=True,
    )
    provider_market_data_imbalance_release_decision.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_release_decision.add_argument(
        "--max-dependencies",
        type=int,
        default=2048,
    )
    provider_market_data_imbalance_release_decision.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    verify_provider_market_data_imbalance_release_decision_parser = (
        sub.add_parser(
            "verify-provider-market-data-imbalance-release-decision",
            help=(
                "Reopen a sealed provider release decision, its operator "
                "record, and the complete retained release-review proof graph."
            ),
        )
    )
    verify_provider_market_data_imbalance_release_decision_parser.add_argument(
        "--release-decision",
        required=True,
    )
    verify_provider_market_data_imbalance_release_decision_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

    provider_market_data_imbalance_live_dryrun_handoff = sub.add_parser(
        "prepare-provider-market-data-imbalance-live-dryrun-handoff",
        help=(
            "Prepare a non-submitting controlled live-dry-run handoff from "
            "an approved release decision and credential-free runtime controls."
        ),
    )
    provider_market_data_imbalance_live_dryrun_handoff.add_argument(
        "--release-decision",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_handoff.add_argument(
        "--runtime-controls",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_handoff.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_handoff.add_argument(
        "--max-dependencies",
        type=int,
        default=4096,
    )
    provider_market_data_imbalance_live_dryrun_handoff.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    verify_provider_market_data_imbalance_live_dryrun_handoff_parser = (
        sub.add_parser(
            "verify-provider-market-data-imbalance-live-dryrun-handoff",
            help=(
                "Reopen a controlled live-dry-run handoff and its complete "
                "approved-decision, controls, rollback, and retained proof graph."
            ),
        )
    )
    verify_provider_market_data_imbalance_live_dryrun_handoff_parser.add_argument(
        "--handoff",
        required=True,
    )
    verify_provider_market_data_imbalance_live_dryrun_handoff_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight = (
        sub.add_parser(
            "preflight-provider-market-data-imbalance-live-dryrun-runtime",
            help=(
                "Probe credential-safe provider connectivity from a verified "
                "live-dry-run handoff and emit a non-submitting launch receipt."
            ),
        )
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--handoff",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--runtime-profile",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--backend",
        default="",
        help=(
            "Trusted module:function connectivity backend. Defaults to the "
            "provider-specific or shared connectivity-backend environment variable."
        ),
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--max-dependencies",
        type=int,
        default=8192,
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--max-connectivity-latency-ms",
        type=float,
        default=5000.0,
    )
    provider_market_data_imbalance_live_dryrun_runtime_preflight.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight_parser = (
        sub.add_parser(
            "verify-provider-market-data-imbalance-live-dryrun-runtime-preflight",
            help=(
                "Reopen a provider connectivity preflight receipt and its "
                "verified handoff/profile proof graph without rerunning connectivity."
            ),
        )
    )
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight_parser.add_argument(
        "--preflight",
        required=True,
    )
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher = (
        sub.add_parser(
            "launch-provider-market-data-imbalance-live-dryrun-simulated-runtime",
            help=(
                "Run a bounded deterministic market-data-only simulation from "
                "a current ready runtime preflight and emit a terminal receipt."
            ),
        )
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--preflight",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--events",
        type=int,
        default=100,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--interval-ms",
        type=int,
        default=100,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--start-offset-seconds",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--symbol",
        default="NIFTY-SIM",
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--base-mid-price",
        type=float,
        default=25_000.0,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--spread",
        type=float,
        default=0.05,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--quantity",
        type=int,
        default=100,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--price-step",
        type=float,
        default=0.05,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--simulate-fault",
        choices=("none", "invalid_quote", "non_monotonic_timestamp"),
        default="none",
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--fault-at-event",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--max-dependencies",
        type=int,
        default=16_384,
    )
    provider_market_data_imbalance_live_dryrun_runtime_launcher.add_argument(
        "--fail-on-halt",
        action="store_true",
    )
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher_parser = (
        sub.add_parser(
            "verify-provider-market-data-imbalance-live-dryrun-runtime-launcher",
            help=(
                "Reopen bounded simulated runtime telemetry and its current "
                "preflight/handoff proof graph without rerunning the session."
            ),
        )
    )
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher_parser.add_argument(
        "--launcher",
        required=True,
    )
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_live_dryrun_shadow = sub.add_parser(
        "evaluate-provider-market-data-imbalance-live-dryrun-shadow",
        help=(
            "Evaluate deterministic microprice signals and non-routable "
            "shadow intents from a verified completed runtime launcher."
        ),
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--launcher",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--lot-size",
        type=int,
        default=1,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--intent-quantity-lots",
        type=int,
        default=1,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--tick-size",
        type=float,
        default=0.05,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--entry-imbalance",
        type=float,
        default=0.6,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--exit-imbalance",
        type=float,
        default=0.15,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--min-microprice-edge-ticks",
        type=float,
        default=0.25,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--max-spread-ticks",
        type=float,
        default=2.0,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--min-depth",
        type=int,
        default=1,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--hold-ns",
        type=int,
        default=500_000_000,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--cooloff-ns",
        type=int,
        default=0,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--max-dependencies",
        type=int,
        default=32_768,
    )
    provider_market_data_imbalance_live_dryrun_shadow.add_argument(
        "--fail-on-halt",
        action="store_true",
    )
    verify_provider_market_data_imbalance_live_dryrun_shadow_parser = (
        sub.add_parser(
            "verify-provider-market-data-imbalance-live-dryrun-shadow-evaluation",
            help=(
                "Reopen shadow features, non-routable intents, retained limits, "
                "and the complete launcher proof graph without reevaluating sources."
            ),
        )
    )
    verify_provider_market_data_imbalance_live_dryrun_shadow_parser.add_argument(
        "--shadow",
        required=True,
    )
    verify_provider_market_data_imbalance_live_dryrun_shadow_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration = (
        sub.add_parser(
            "calibrate-provider-market-data-imbalance-live-dryrun-shadow",
            help=(
                "Measure deterministic shadow markouts, adverse selection, "
                "and externally-unvalidated India reference cost hurdles."
            ),
        )
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--shadow",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--out",
        required=True,
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--horizons-ns",
        nargs="+",
        type=int,
        default=[0, 250_000_000, 500_000_000],
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--max-horizon-overshoot-ns",
        type=int,
        default=250_000_000,
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--min-covered-observations-per-horizon",
        type=int,
        default=1,
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--min-coverage-ratio",
        type=float,
        default=0.5,
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--max-dependencies",
        type=int,
        default=32_768,
    )
    provider_market_data_imbalance_live_dryrun_shadow_calibration.add_argument(
        "--fail-on-incomplete",
        action="store_true",
    )
    verify_provider_shadow_calibration_parser = sub.add_parser(
        "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration",
        help=(
            "Reconstruct shadow markouts and cost sensitivity from the current "
            "non-authorizing shadow proof graph."
        ),
    )
    verify_provider_shadow_calibration_parser.add_argument(
        "--calibration",
        required=True,
    )
    verify_provider_shadow_calibration_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_shadow_calibration_stability = sub.add_parser(
        "compare-provider-market-data-imbalance-live-dryrun-shadow-calibrations",
        help=(
            "Compare verified completed shadow calibrations without enabling "
            "promotion, routing, or submission."
        ),
    )
    provider_shadow_calibration_stability.add_argument(
        "--calibration",
        nargs="+",
        required=True,
    )
    provider_shadow_calibration_stability.add_argument("--out", required=True)
    provider_shadow_calibration_stability.add_argument(
        "--min-sessions",
        type=int,
        default=2,
    )
    provider_shadow_calibration_stability.add_argument(
        "--min-session-coverage-ratio",
        type=float,
        default=0.5,
    )
    provider_shadow_calibration_stability.add_argument(
        "--max-horizon-coverage-range",
        type=float,
        default=0.25,
    )
    provider_shadow_calibration_stability.add_argument(
        "--max-directional-mid-range-ticks",
        type=float,
        default=2.0,
    )
    provider_shadow_calibration_stability.add_argument(
        "--allow-directional-sign-change",
        action="store_true",
    )
    provider_shadow_calibration_stability.add_argument(
        "--max-adverse-selection-rate-range",
        type=float,
        default=0.25,
    )
    provider_shadow_calibration_stability.add_argument(
        "--max-cost-break-even-rate-range",
        type=float,
        default=0.25,
    )
    provider_shadow_calibration_stability.add_argument(
        "--max-round-trip-cost-range-ticks",
        type=float,
        default=0.25,
    )
    provider_shadow_calibration_stability.add_argument(
        "--max-dependencies",
        type=int,
        default=65_536,
    )
    provider_shadow_calibration_stability.add_argument(
        "--fail-on-unstable",
        action="store_true",
    )
    verify_provider_shadow_calibration_stability_parser = sub.add_parser(
        "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration-stability",
        help=(
            "Reconstruct a non-authorizing multi-session shadow calibration "
            "stability cohort."
        ),
    )
    verify_provider_shadow_calibration_stability_parser.add_argument(
        "--stability",
        required=True,
    )
    verify_provider_shadow_calibration_stability_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

    provider_broker_lineage_migration = sub.add_parser(
        "audit-provider-market-data-imbalance-broker-lineage-migration",
        help=(
            "Audit archived provider broker proofs for strict-lineage "
            "migration and legacy-override policy."
        ),
    )
    provider_broker_lineage_migration.add_argument(
        "--roots",
        nargs="+",
        required=True,
    )
    provider_broker_lineage_migration.add_argument("--out", required=True)
    provider_broker_lineage_migration.add_argument(
        "--no-recursive",
        action="store_true",
    )
    provider_broker_lineage_migration.add_argument(
        "--max-bundles",
        type=int,
        default=1000,
    )
    provider_broker_lineage_migration.add_argument(
        "--max-blocked-bundles",
        type=int,
        default=0,
    )
    provider_broker_lineage_migration.add_argument(
        "--min-strict-ready-coverage",
        type=float,
        default=1.0,
    )
    provider_broker_lineage_migration.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_broker_lineage_migration.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_broker_lineage_migration.add_argument(
        "--fail-on-actions",
        action="store_true",
    )

    provider_broker_lineage_audit_usage = sub.add_parser(
        "review-provider-market-data-imbalance-broker-lineage-audit-usage",
        help=(
            "Review retained provider proofs for current strict lineage or "
            "current exact-source legacy migration-audit coverage."
        ),
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--roots",
        nargs="+",
        required=True,
    )
    provider_broker_lineage_audit_usage.add_argument("--out", required=True)
    provider_broker_lineage_audit_usage.add_argument(
        "--no-recursive",
        action="store_true",
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--max-bundles",
        type=int,
        default=1000,
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--max-unaudited-legacy-bundles",
        type=int,
        default=0,
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--max-drifted-audit-bundles",
        type=int,
        default=0,
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--max-strict-with-audit-bundles",
        type=int,
        default=0,
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_broker_lineage_audit_usage.add_argument(
        "--fail-on-actions",
        action="store_true",
    )

    provider_broker_lineage_refresh_convergence = sub.add_parser(
        "verify-provider-market-data-imbalance-broker-lineage-refresh",
        help=(
            "Verify that planned provider strict-lineage refresh outputs "
            "converge and close their audit-usage blockers."
        ),
    )
    provider_broker_lineage_refresh_convergence.add_argument(
        "--audit-usage",
        required=True,
    )
    provider_broker_lineage_refresh_convergence.add_argument(
        "--out",
        required=True,
    )
    provider_broker_lineage_refresh_convergence.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_broker_lineage_refresh_convergence.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_broker_lineage_refresh_convergence.add_argument(
        "--fail-on-actions",
        action="store_true",
    )

    provider_broker_active_lineage = sub.add_parser(
        "index-provider-market-data-imbalance-broker-active-lineage",
        help=(
            "Index converged strict provider proofs as selectable and retain "
            "their legacy originals for audit only."
        ),
    )
    provider_broker_active_lineage.add_argument(
        "--convergence",
        required=True,
    )
    provider_broker_active_lineage.add_argument("--out", required=True)
    provider_broker_active_lineage.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_broker_active_lineage.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_broker_active_lineage.add_argument(
        "--fail-on-actions",
        action="store_true",
    )

    provider_active_lineage_chain = sub.add_parser(
        "audit-provider-market-data-imbalance-active-lineage-chain",
        help=(
            "Audit one provider rehearsal certificate across the complete "
            "route-readiness-to-certificate active-lineage chain."
        ),
    )
    provider_active_lineage_chain.add_argument("--certificate", required=True)
    provider_active_lineage_chain.add_argument("--out", required=True)
    provider_active_lineage_chain.add_argument(
        "--max-manifests",
        type=int,
        default=256,
    )
    provider_active_lineage_chain.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    provider_active_lineage_chain.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    provider_active_lineage_chain.add_argument(
        "--fail-on-actions",
        action="store_true",
    )

    provider_market_data_capture = sub.add_parser(
        "review-provider-market-data-capture",
        help="Review a provider-captured normalized CSV against a provider client packet.",
    )
    provider_market_data_capture.add_argument("--client-packet", required=True)
    provider_market_data_capture.add_argument("--capture", required=True)
    provider_market_data_capture.add_argument("--out", required=True)
    provider_market_data_capture.add_argument("--min-rows", type=int, default=1)
    provider_market_data_capture.add_argument("--max-missing-required-columns", type=int, default=0)
    provider_market_data_capture.add_argument("--max-null-required-cells", type=int, default=0)
    provider_market_data_capture.add_argument("--no-require-monotonic-ts", action="store_true")
    provider_market_data_capture.add_argument("--expected-market", default="")
    provider_market_data_capture.add_argument("--expected-kind", default="")
    provider_market_data_capture.add_argument("--pipeline-output-dir", default="")
    provider_market_data_capture.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_capture.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_capture.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_pipeline = sub.add_parser(
        "pipeline-provider-market-data",
        help="Run provider capture review and normalized vendor market-data pipeline in one root.",
    )
    provider_market_data_pipeline.add_argument("--client-packet", required=True)
    provider_market_data_pipeline.add_argument("--capture", required=True)
    provider_market_data_pipeline.add_argument("--out", required=True)
    provider_market_data_pipeline.add_argument("--min-capture-rows", type=int, default=1)
    provider_market_data_pipeline.add_argument("--max-missing-required-columns", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-null-required-cells", type=int, default=0)
    provider_market_data_pipeline.add_argument("--no-require-monotonic-ts", action="store_true")
    provider_market_data_pipeline.add_argument("--expected-market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(provider_market_data_pipeline)
    provider_market_data_pipeline.add_argument("--expected-kind", default="ticks")
    provider_market_data_pipeline.add_argument("--sample-rows", type=int, default=1000)
    provider_market_data_pipeline.add_argument("--tick-size", type=float, default=None)
    provider_market_data_pipeline.add_argument("--max-quote-spread-ticks", type=float, default=None)
    provider_market_data_pipeline.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    provider_market_data_pipeline.add_argument("--strike-step", type=float, default=None)
    provider_market_data_pipeline.add_argument("--timestamp-unit", default="datetime")
    provider_market_data_pipeline.add_argument("--timestamp-tz", default=None)
    provider_market_data_pipeline.add_argument("--pipeline-min-rows", type=int, default=1)
    provider_market_data_pipeline.add_argument("--max-null-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-nonfinite-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-nonintegral-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-duplicate-tick-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-integer-overflow-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-nonmonotonic-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-crossed-quote-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-nonpositive-quote-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-nonpositive-strike-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-nonpositive-depth-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-invalid-trade-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-off-tick-price-rows", type=int, default=None)
    provider_market_data_pipeline.add_argument("--max-wide-spread-rows", type=int, default=None)
    provider_market_data_pipeline.add_argument("--max-stale-bbo-rows", type=int, default=None)
    provider_market_data_pipeline.add_argument("--max-off-grid-strike-rows", type=int, default=None)
    provider_market_data_pipeline.add_argument("--max-non-trading-day-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-out-of-session-rows", type=int, default=0)
    provider_market_data_pipeline.add_argument("--max-p99-gap-ns", type=float, default=None)
    provider_market_data_pipeline.add_argument("--max-median-spread-ticks", type=float, default=None)
    provider_market_data_pipeline.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_pipeline.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_pipeline.add_argument("--fail-on-actions", action="store_true")

    provider_market_data_batch = sub.add_parser(
        "pipeline-provider-market-data-batch",
        help="Run provider capture roots for multiple sessions and compare nested data readiness.",
    )
    provider_market_data_batch.add_argument("--client-packet", required=True)
    provider_market_data_batch.add_argument("--capture", nargs="+", required=True)
    provider_market_data_batch.add_argument("--out", required=True)
    provider_market_data_batch.add_argument("--label", action="append", dest="labels")
    provider_market_data_batch.add_argument("--min-capture-rows", type=int, default=1)
    provider_market_data_batch.add_argument("--max-missing-required-columns", type=int, default=0)
    provider_market_data_batch.add_argument("--max-null-required-cells", type=int, default=0)
    provider_market_data_batch.add_argument("--no-require-monotonic-ts", action="store_true")
    provider_market_data_batch.add_argument("--expected-market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(provider_market_data_batch)
    provider_market_data_batch.add_argument("--expected-kind", default="ticks")
    provider_market_data_batch.add_argument("--sample-rows", type=int, default=1000)
    provider_market_data_batch.add_argument("--tick-size", type=float, default=None)
    provider_market_data_batch.add_argument("--max-quote-spread-ticks", type=float, default=None)
    provider_market_data_batch.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    provider_market_data_batch.add_argument("--strike-step", type=float, default=None)
    provider_market_data_batch.add_argument("--timestamp-unit", default="datetime")
    provider_market_data_batch.add_argument("--timestamp-tz", default=None)
    provider_market_data_batch.add_argument("--pipeline-min-rows", type=int, default=1)
    provider_market_data_batch.add_argument("--max-null-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-nonfinite-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-nonintegral-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-duplicate-tick-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-integer-overflow-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-nonmonotonic-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-crossed-quote-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-nonpositive-quote-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-nonpositive-strike-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-nonpositive-depth-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-invalid-trade-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-off-tick-price-rows", type=int, default=None)
    provider_market_data_batch.add_argument("--max-wide-spread-rows", type=int, default=None)
    provider_market_data_batch.add_argument("--max-stale-bbo-rows", type=int, default=None)
    provider_market_data_batch.add_argument("--max-off-grid-strike-rows", type=int, default=None)
    provider_market_data_batch.add_argument("--max-non-trading-day-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-out-of-session-rows", type=int, default=0)
    provider_market_data_batch.add_argument("--max-p99-gap-ns", type=float, default=None)
    provider_market_data_batch.add_argument("--max-median-spread-ticks", type=float, default=None)
    provider_market_data_batch.add_argument("--min-datasets", type=int, default=None)
    provider_market_data_batch.add_argument("--min-ready-datasets", type=int, default=None)
    provider_market_data_batch.add_argument("--min-ready-rate", type=float, default=1.0)
    provider_market_data_batch.add_argument("--max-total-failed-checks", type=int, default=0)
    provider_market_data_batch.add_argument("--min-unique-source-files", type=int, default=None)
    provider_market_data_batch.add_argument("--min-source-file-fingerprint-coverage", type=float, default=1.0)
    provider_market_data_batch.add_argument("--min-mapping-coverage", type=float, default=1.0)
    provider_market_data_batch.add_argument("--fail-on-breach", action="store_true")
    provider_market_data_batch.add_argument("--fail-on-blocked-actions", action="store_true")
    provider_market_data_batch.add_argument("--fail-on-actions", action="store_true")

    vendor_market_data = sub.add_parser(
        "pipeline-vendor-market-data",
        help="Run vendor CSV intake, normalization, diagnostics, and data readiness for ticks or chains.",
    )
    vendor_market_data.add_argument("--input", required=True)
    vendor_market_data.add_argument("--out", required=True)
    vendor_mapping_source = vendor_market_data.add_mutually_exclusive_group()
    vendor_mapping_source.add_argument("--mapping", default=None)
    vendor_mapping_source.add_argument(
        "--mapping-review",
        default=None,
        help="Verified approved mapping-review directory bound to this exact input file.",
    )
    vendor_mapping_source.add_argument(
        "--mapping-application",
        default=None,
        help="Verified target mapping-application directory bound to this exact input file.",
    )
    vendor_market_data.add_argument("--adapter", default="arrow_money")
    vendor_market_data.add_argument("--kind", default="ticks", choices=["ticks", "chain"])
    vendor_market_data.add_argument("--output-file", default=None)
    vendor_market_data.add_argument("--sample-rows", type=int, default=1000)
    vendor_market_data.add_argument("--min-mapping-coverage", type=float, default=1.0)
    vendor_market_data.add_argument("--timestamp-unit", default="ns")
    vendor_market_data.add_argument("--timestamp-tz", default=None)
    vendor_market_data.add_argument("--market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(vendor_market_data)
    vendor_market_data.add_argument(
        "--expiry-cycle",
        choices=["weekly", "monthly"],
        default=None,
        help=(
            "For chain data, validate expiries against the current NSE rule "
            "and supplied market calendar."
        ),
    )
    vendor_market_data.add_argument(
        "--underlying",
        default=None,
        help="NSE index symbol for authority-backed contract lot-size validation.",
    )
    vendor_market_data.add_argument(
        "--lot-size",
        type=int,
        default=None,
        help="Declared contract lot size to validate for every chain expiry.",
    )
    vendor_market_data.add_argument("--no-filter-session", action="store_true")
    vendor_market_data.add_argument("--tick-size", type=float, default=None)
    vendor_market_data.add_argument("--max-quote-spread-ticks", type=float, default=None)
    vendor_market_data.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    vendor_market_data.add_argument("--strike-step", type=float, default=None)
    vendor_market_data.add_argument("--allow-missing-required", action="store_true")
    vendor_market_data.add_argument("--min-rows", type=int, default=1)
    vendor_market_data.add_argument("--max-null-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-nonfinite-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-nonintegral-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-duplicate-tick-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-integer-overflow-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-nonmonotonic-rows", type=int, default=0)
    vendor_market_data.add_argument("--min-chain-expiry-snapshots", type=int, default=1)
    vendor_market_data.add_argument("--min-chain-snapshots-per-expiry", type=int, default=1)
    vendor_market_data.add_argument("--min-chain-snapshot-strikes", type=int, default=1)
    vendor_market_data.add_argument("--max-crossed-quote-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-nonpositive-quote-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-nonpositive-strike-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-nonpositive-depth-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-invalid-trade-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-off-tick-price-rows", type=int, default=None)
    vendor_market_data.add_argument("--max-wide-spread-rows", type=int, default=None)
    vendor_market_data.add_argument("--max-stale-bbo-rows", type=int, default=None)
    vendor_market_data.add_argument("--max-off-grid-strike-rows", type=int, default=None)
    vendor_market_data.add_argument("--max-non-trading-day-rows", type=int, default=0)
    vendor_market_data.add_argument("--max-out-of-session-rows", type=int, default=0)
    vendor_market_data.add_argument(
        "--max-unparseable-contract-expiry-rows",
        type=int,
        default=0,
    )
    vendor_market_data.add_argument(
        "--max-expired-contract-rows",
        type=int,
        default=0,
    )
    vendor_market_data.add_argument(
        "--max-duplicate-contract-key-rows",
        type=int,
        default=0,
    )
    vendor_market_data.add_argument(
        "--max-conflicting-contract-key-rows",
        type=int,
        default=0,
    )
    vendor_market_data.add_argument("--max-p99-gap-ns", type=float, default=None)
    vendor_market_data.add_argument("--max-median-spread-ticks", type=float, default=None)
    vendor_market_data.add_argument("--max-chain-snapshot-p99-gap-ns", type=float, default=None)
    vendor_market_data.add_argument("--fail-on-breach", action="store_true")
    vendor_market_data.add_argument("--fail-on-blocked-actions", action="store_true")
    vendor_market_data.add_argument("--fail-on-actions", action="store_true")

    vendor_market_data_batch = sub.add_parser(
        "pipeline-vendor-market-data-batch",
        help="Onboard multiple vendor CSV days and compare data readiness before walk-forward research.",
    )
    vendor_market_data_batch.add_argument("--input", nargs="+", required=True)
    vendor_market_data_batch.add_argument("--out", required=True)
    vendor_market_data_batch.add_argument("--label", action="append", dest="labels")
    vendor_batch_mapping_source = (
        vendor_market_data_batch.add_mutually_exclusive_group()
    )
    vendor_batch_mapping_source.add_argument("--mapping", default=None)
    vendor_batch_mapping_source.add_argument(
        "--mapping-application",
        action="append",
        dest="mapping_applications",
        help="Repeat once per input, in input order, with a distinct verified target application.",
    )
    vendor_market_data_batch.add_argument("--adapter", default="arrow_money")
    vendor_market_data_batch.add_argument("--kind", default="ticks", choices=["ticks", "chain"])
    vendor_market_data_batch.add_argument("--output-file", default=None)
    vendor_market_data_batch.add_argument("--sample-rows", type=int, default=1000)
    vendor_market_data_batch.add_argument("--min-mapping-coverage", type=float, default=1.0)
    vendor_market_data_batch.add_argument("--timestamp-unit", default="ns")
    vendor_market_data_batch.add_argument("--timestamp-tz", default=None)
    vendor_market_data_batch.add_argument("--market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(vendor_market_data_batch)
    vendor_market_data_batch.add_argument(
        "--expiry-cycle",
        choices=["weekly", "monthly"],
        default=None,
        help=(
            "For chain data, validate expiries against the current NSE rule "
            "and supplied market calendar."
        ),
    )
    vendor_market_data_batch.add_argument(
        "--underlying",
        default=None,
        help="NSE index symbol for authority-backed contract lot-size validation.",
    )
    vendor_market_data_batch.add_argument(
        "--lot-size",
        type=int,
        default=None,
        help="Declared contract lot size to validate for every chain expiry.",
    )
    vendor_market_data_batch.add_argument("--no-filter-session", action="store_true")
    vendor_market_data_batch.add_argument("--tick-size", type=float, default=None)
    vendor_market_data_batch.add_argument("--max-quote-spread-ticks", type=float, default=None)
    vendor_market_data_batch.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    vendor_market_data_batch.add_argument("--strike-step", type=float, default=None)
    vendor_market_data_batch.add_argument("--allow-missing-required", action="store_true")
    vendor_market_data_batch.add_argument("--min-rows", type=int, default=1)
    vendor_market_data_batch.add_argument("--max-null-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-nonfinite-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-nonintegral-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-duplicate-tick-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-integer-overflow-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-nonmonotonic-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--min-chain-expiry-snapshots", type=int, default=1)
    vendor_market_data_batch.add_argument("--min-chain-snapshots-per-expiry", type=int, default=1)
    vendor_market_data_batch.add_argument("--min-chain-snapshot-strikes", type=int, default=1)
    vendor_market_data_batch.add_argument("--max-crossed-quote-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-nonpositive-quote-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-nonpositive-strike-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-nonpositive-depth-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-invalid-trade-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-off-tick-price-rows", type=int, default=None)
    vendor_market_data_batch.add_argument("--max-wide-spread-rows", type=int, default=None)
    vendor_market_data_batch.add_argument("--max-stale-bbo-rows", type=int, default=None)
    vendor_market_data_batch.add_argument("--max-off-grid-strike-rows", type=int, default=None)
    vendor_market_data_batch.add_argument("--max-non-trading-day-rows", type=int, default=0)
    vendor_market_data_batch.add_argument("--max-out-of-session-rows", type=int, default=0)
    vendor_market_data_batch.add_argument(
        "--max-unparseable-contract-expiry-rows",
        type=int,
        default=0,
    )
    vendor_market_data_batch.add_argument(
        "--max-expired-contract-rows",
        type=int,
        default=0,
    )
    vendor_market_data_batch.add_argument(
        "--max-duplicate-contract-key-rows",
        type=int,
        default=0,
    )
    vendor_market_data_batch.add_argument(
        "--max-conflicting-contract-key-rows",
        type=int,
        default=0,
    )
    vendor_market_data_batch.add_argument("--max-p99-gap-ns", type=float, default=None)
    vendor_market_data_batch.add_argument("--max-median-spread-ticks", type=float, default=None)
    vendor_market_data_batch.add_argument("--max-chain-snapshot-p99-gap-ns", type=float, default=None)
    vendor_market_data_batch.add_argument("--min-datasets", type=int, default=None)
    vendor_market_data_batch.add_argument("--min-ready-datasets", type=int, default=None)
    vendor_market_data_batch.add_argument("--min-ready-rate", type=float, default=1.0)
    vendor_market_data_batch.add_argument("--max-total-failed-checks", type=int, default=0)
    vendor_market_data_batch.add_argument("--min-unique-source-files", type=int, default=None)
    vendor_market_data_batch.add_argument("--min-source-file-fingerprint-coverage", type=float, default=None)
    vendor_market_data_batch.add_argument("--fail-on-breach", action="store_true")
    vendor_market_data_batch.add_argument("--fail-on-blocked-actions", action="store_true")
    vendor_market_data_batch.add_argument("--fail-on-actions", action="store_true")

    broker_vendor_data_readiness = sub.add_parser(
        "pipeline-broker-vendor-readiness",
        help="Run vendor market-data batch onboarding and feed the proof into broker readiness.",
    )
    broker_vendor_data_readiness.add_argument("--input", nargs="+", required=True)
    broker_vendor_data_readiness.add_argument("--out", required=True)
    broker_vendor_data_readiness.add_argument("--label", action="append", dest="labels")
    broker_vendor_mapping_source = (
        broker_vendor_data_readiness.add_mutually_exclusive_group()
    )
    broker_vendor_mapping_source.add_argument("--mapping", default=None)
    broker_vendor_mapping_source.add_argument(
        "--mapping-application",
        action="append",
        dest="mapping_applications",
        help="Repeat once per input, in input order, with a distinct verified target application.",
    )
    broker_vendor_data_readiness.add_argument("--adapter", default="arrow_money")
    broker_vendor_data_readiness.add_argument("--kind", default="ticks", choices=["ticks", "chain"])
    broker_vendor_data_readiness.add_argument("--output-file", default=None)
    broker_vendor_data_readiness.add_argument("--sample-rows", type=int, default=1000)
    broker_vendor_data_readiness.add_argument("--min-mapping-coverage", type=float, default=1.0)
    broker_vendor_data_readiness.add_argument("--timestamp-unit", default="ns")
    broker_vendor_data_readiness.add_argument("--timestamp-tz", default=None)
    broker_vendor_data_readiness.add_argument("--market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(broker_vendor_data_readiness)
    broker_vendor_data_readiness.add_argument(
        "--expiry-cycle",
        choices=["weekly", "monthly"],
        default=None,
        help=(
            "For chain data, validate expiries and declared lot size "
            "against pinned NSE authorities."
        ),
    )
    broker_vendor_data_readiness.add_argument(
        "--underlying",
        default=None,
        help="NSE index symbol for authority-backed contract lot-size validation.",
    )
    broker_vendor_data_readiness.add_argument(
        "--lot-size",
        type=int,
        default=None,
        help="Declared contract lot size to validate for every chain expiry.",
    )
    broker_vendor_data_readiness.add_argument("--no-filter-session", action="store_true")
    broker_vendor_data_readiness.add_argument("--tick-size", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--max-quote-spread-ticks", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--strike-step", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--allow-missing-required", action="store_true")
    broker_vendor_data_readiness.add_argument("--min-rows", type=int, default=1)
    broker_vendor_data_readiness.add_argument("--max-null-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-nonfinite-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-nonintegral-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-duplicate-tick-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-integer-overflow-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-nonmonotonic-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--min-chain-expiry-snapshots", type=int, default=1)
    broker_vendor_data_readiness.add_argument("--min-chain-snapshots-per-expiry", type=int, default=1)
    broker_vendor_data_readiness.add_argument("--min-chain-snapshot-strikes", type=int, default=1)
    broker_vendor_data_readiness.add_argument("--max-crossed-quote-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-nonpositive-quote-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-nonpositive-strike-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-nonpositive-depth-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-invalid-trade-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-off-tick-price-rows", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--max-wide-spread-rows", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--max-stale-bbo-rows", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--max-off-grid-strike-rows", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--max-non-trading-day-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--max-out-of-session-rows", type=int, default=0)
    broker_vendor_data_readiness.add_argument(
        "--max-unparseable-contract-expiry-rows",
        type=int,
        default=0,
    )
    broker_vendor_data_readiness.add_argument(
        "--max-expired-contract-rows",
        type=int,
        default=0,
    )
    broker_vendor_data_readiness.add_argument(
        "--max-duplicate-contract-key-rows",
        type=int,
        default=0,
    )
    broker_vendor_data_readiness.add_argument(
        "--max-conflicting-contract-key-rows",
        type=int,
        default=0,
    )
    broker_vendor_data_readiness.add_argument("--max-p99-gap-ns", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--max-median-spread-ticks", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--max-chain-snapshot-p99-gap-ns", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--min-datasets", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--min-ready-datasets", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--min-ready-rate", type=float, default=1.0)
    broker_vendor_data_readiness.add_argument("--max-total-failed-checks", type=int, default=0)
    broker_vendor_data_readiness.add_argument("--min-unique-source-files", type=int, default=None)
    broker_vendor_data_readiness.add_argument("--min-source-file-fingerprint-coverage", type=float, default=None)
    broker_vendor_data_readiness.add_argument("--schema-audit", default=None)
    broker_vendor_data_readiness.add_argument("--order-export", default=None)
    broker_vendor_data_readiness.add_argument("--mapping-draft", default=None)
    broker_vendor_data_readiness.add_argument("--mapped-orders", default=None)
    broker_vendor_data_readiness.add_argument("--upload-pack", default=None)
    broker_vendor_data_readiness.add_argument("--halt-export", default=None)
    broker_vendor_data_readiness.add_argument("--reconciliation", default=None)
    broker_vendor_data_readiness.add_argument("--runtime-session", default=None)
    broker_vendor_data_readiness.add_argument("--resume-gate", default=None)
    broker_vendor_data_readiness.add_argument("--dispatch-roundtrip", default=None)
    broker_vendor_data_readiness.add_argument("--allow-placeholder-schema", action="store_true")
    broker_vendor_data_readiness.add_argument("--allow-adapter-mismatch", action="store_true")
    broker_vendor_data_readiness.add_argument("--skip-schema-audit", action="store_true")
    broker_vendor_data_readiness.add_argument("--skip-order-export", action="store_true")
    broker_vendor_data_readiness.add_argument("--skip-upload-pack", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-mapping-draft", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-mapped-orders", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-halt-export", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-reconciliation", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-runtime-session", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-resume-gate", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-route-readiness", action="store_true")
    broker_vendor_data_readiness.add_argument("--require-dispatch-roundtrip", action="store_true")
    broker_vendor_data_readiness.add_argument("--fail-on-breach", action="store_true")
    broker_vendor_data_readiness.add_argument("--fail-on-blocked-actions", action="store_true")
    broker_vendor_data_readiness.add_argument("--fail-on-actions", action="store_true")

    diag_ticks = sub.add_parser("diagnose-ticks", help="Run data-quality diagnostics for top-of-book ticks.")
    diag_ticks.add_argument("--ticks", required=True)
    diag_ticks.add_argument("--out", required=True)
    diag_ticks.add_argument("--tick-size", type=float, default=None)
    diag_ticks.add_argument("--max-quote-spread-ticks", type=float, default=None)
    diag_ticks.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    diag_ticks.add_argument("--market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(diag_ticks)
    diag_ticks.add_argument("--no-filter-session", action="store_true")

    diag_chain = sub.add_parser("diagnose-chain", help="Run data-quality diagnostics for option-chain snapshots.")
    diag_chain.add_argument("--chain", required=True)
    diag_chain.add_argument("--out", required=True)
    diag_chain.add_argument("--tick-size", type=float, default=None)
    diag_chain.add_argument("--max-quote-spread-ticks", type=float, default=None)
    diag_chain.add_argument("--max-unchanged-bbo-ns", type=int, default=None)
    diag_chain.add_argument("--strike-step", type=float, default=None)
    diag_chain.add_argument("--market", default="india_nse_index_derivatives")
    _add_market_calendar_arg(diag_chain)
    diag_chain.add_argument(
        "--expiry-cycle",
        choices=["weekly", "monthly"],
        default=None,
        help=(
            "Validate chain expiries against the current NSE rule and "
            "supplied market calendar."
        ),
    )
    diag_chain.add_argument(
        "--underlying",
        default=None,
        help="NSE index symbol for authority-backed contract lot-size validation.",
    )
    diag_chain.add_argument(
        "--lot-size",
        type=int,
        default=None,
        help="Declared contract lot size to validate for every chain expiry.",
    )
    diag_chain.add_argument("--no-filter-session", action="store_true")

    data_readiness = sub.add_parser("review-data-readiness", help="Gate vendor/normalized market data before research runs.")
    data_readiness.add_argument("--out", required=True)
    data_readiness.add_argument("--market-calendar-report", default=None)
    data_readiness.add_argument("--vendor-intake", default=None)
    data_readiness.add_argument("--schema-audit", default=None)
    data_readiness.add_argument("--mapped-data", default=None)
    data_readiness.add_argument("--tick-diagnostics", default=None)
    data_readiness.add_argument("--chain-diagnostics", default=None)
    data_readiness.add_argument("--market-profile", default=None)
    data_readiness.add_argument("--market-portability", default=None)
    data_readiness.add_argument("--instrument-metadata", default=None)
    data_readiness.add_argument("--require-vendor-intake", action="store_true")
    data_readiness.add_argument("--require-market-calendar", action="store_true")
    data_readiness.add_argument("--require-schema-audit", action="store_true")
    data_readiness.add_argument("--require-mapped-data", action="store_true")
    data_readiness.add_argument(
        "--require-reviewed-mapping-normalization",
        action="store_true",
    )
    data_readiness.add_argument(
        "--require-target-application-normalization",
        action="store_true",
    )
    data_readiness.add_argument("--skip-tick-diagnostics", action="store_true")
    data_readiness.add_argument("--require-chain-diagnostics", action="store_true")
    data_readiness.add_argument(
        "--require-contract-expiry-validation",
        action="store_true",
    )
    data_readiness.add_argument(
        "--require-contract-lot-validation",
        action="store_true",
    )
    data_readiness.add_argument("--require-market-profile", action="store_true")
    data_readiness.add_argument("--require-explicit-fee-model", action="store_true")
    data_readiness.add_argument("--require-market-portability", action="store_true")
    data_readiness.add_argument("--require-instrument-metadata", action="store_true")
    data_readiness.add_argument("--expected-strategy", default=None)
    data_readiness.add_argument("--expected-market", default=None)
    data_readiness.add_argument("--expected-adapter", default=None)
    data_readiness.add_argument("--expected-vendor-data-kind", default=None)
    data_readiness.add_argument("--min-tick-rows", type=int, default=1)
    data_readiness.add_argument("--min-chain-rows", type=int, default=1)
    data_readiness.add_argument("--min-chain-expiries", type=int, default=1)
    data_readiness.add_argument("--min-chain-strikes", type=int, default=1)
    data_readiness.add_argument("--min-chain-expiry-snapshots", type=int, default=1)
    data_readiness.add_argument("--min-chain-snapshots-per-expiry", type=int, default=1)
    data_readiness.add_argument("--min-chain-snapshot-strikes", type=int, default=1)
    data_readiness.add_argument("--max-null-rows", type=int, default=0)
    data_readiness.add_argument("--max-nonfinite-rows", type=int, default=0)
    data_readiness.add_argument("--max-nonintegral-rows", type=int, default=0)
    data_readiness.add_argument("--max-duplicate-tick-rows", type=int, default=0)
    data_readiness.add_argument("--max-integer-overflow-rows", type=int, default=0)
    data_readiness.add_argument("--max-nonmonotonic-rows", type=int, default=0)
    data_readiness.add_argument("--max-crossed-quote-rows", type=int, default=0)
    data_readiness.add_argument("--max-nonpositive-quote-rows", type=int, default=0)
    data_readiness.add_argument("--max-nonpositive-strike-rows", type=int, default=0)
    data_readiness.add_argument("--max-nonpositive-depth-rows", type=int, default=0)
    data_readiness.add_argument("--max-invalid-trade-rows", type=int, default=0)
    data_readiness.add_argument("--max-off-tick-price-rows", type=int, default=None)
    data_readiness.add_argument("--max-wide-spread-rows", type=int, default=None)
    data_readiness.add_argument("--max-stale-bbo-rows", type=int, default=None)
    data_readiness.add_argument("--max-off-grid-strike-rows", type=int, default=None)
    data_readiness.add_argument("--max-non-trading-day-rows", type=int, default=0)
    data_readiness.add_argument("--max-out-of-session-rows", type=int, default=0)
    data_readiness.add_argument(
        "--max-unparseable-contract-expiry-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-expired-contract-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-duplicate-contract-key-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-conflicting-contract-key-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-invalid-contract-expiry-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-uncovered-contract-expiry-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-invalid-contract-lot-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument(
        "--max-uncovered-contract-lot-rows",
        type=int,
        default=0,
    )
    data_readiness.add_argument("--max-tick-p99-gap-ns", type=float, default=None)
    data_readiness.add_argument("--max-tick-median-spread-ticks", type=float, default=None)
    data_readiness.add_argument("--max-chain-median-spread-ticks", type=float, default=None)
    data_readiness.add_argument("--max-chain-snapshot-p99-gap-ns", type=float, default=None)
    data_readiness.add_argument("--fail-on-breach", action="store_true")
    data_readiness.add_argument("--fail-on-blocked-actions", action="store_true")
    data_readiness.add_argument("--fail-on-actions", action="store_true")

    data_readiness_verify = sub.add_parser(
        "verify-data-readiness-report",
        help=(
            "Reconstruct a data-readiness report from its manifest-bound "
            "inputs and verify every retained artifact."
        ),
    )
    data_readiness_verify.add_argument("--report", required=True)
    data_readiness_verify.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

    data_readiness_compare = sub.add_parser(
        "compare-data-readiness",
        help="Compare multiple data-readiness runs before walk-forward research.",
    )
    data_readiness_compare.add_argument("--readiness", nargs="+", required=True)
    data_readiness_compare.add_argument("--out", required=True)
    data_readiness_compare.add_argument("--label", action="append", dest="labels")
    data_readiness_compare.add_argument("--min-datasets", type=int, default=1)
    data_readiness_compare.add_argument("--min-ready-datasets", type=int, default=None)
    data_readiness_compare.add_argument("--min-ready-rate", type=float, default=1.0)
    data_readiness_compare.add_argument("--max-total-failed-checks", type=int, default=0)
    data_readiness_compare.add_argument("--min-unique-source-files", type=int, default=None)
    data_readiness_compare.add_argument("--min-source-file-fingerprint-coverage", type=float, default=None)
    data_readiness_compare.add_argument("--min-mapping-coverage", type=float, default=None)
    data_readiness_compare.add_argument("--require-market-calendar", action="store_true")
    data_readiness_compare.add_argument(
        "--require-consistent-market-calendar",
        action="store_true",
    )
    data_readiness_compare.add_argument("--fail-on-breach", action="store_true")
    data_readiness_compare.add_argument("--fail-on-blocked-actions", action="store_true")
    data_readiness_compare.add_argument("--fail-on-actions", action="store_true")

    data_readiness_comparison_verify = sub.add_parser(
        "verify-data-readiness-comparison",
        help=(
            "Reconstruct a multi-day data-readiness comparison from its "
            "manifest-bound daily reports."
        ),
    )
    data_readiness_comparison_verify.add_argument(
        "--report",
        required=True,
    )
    data_readiness_comparison_verify.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

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

    market_calendar = sub.add_parser(
        "market-calendar-report",
        help="Validate and fingerprint a versioned exchange calendar.",
    )
    market_calendar.add_argument("--calendar", required=True)
    market_calendar.add_argument("--out", required=True)
    market_calendar.add_argument("--market", default=None)

    market_calendar_verify = sub.add_parser(
        "verify-market-calendar-report",
        help=(
            "Reconstruct a market-calendar report and verify its retained "
            "source and artifacts."
        ),
    )
    market_calendar_verify.add_argument("--report", required=True)
    market_calendar_verify.add_argument("--fail-on-breach", action="store_true")

    market_calendar_build = sub.add_parser(
        "build-market-calendar",
        help=(
            "Compile a strict versioned market calendar from an "
            "operator-supplied sessions CSV."
        ),
    )
    market_calendar_build.add_argument("--sessions", required=True)
    market_calendar_build.add_argument("--calendar-id", required=True)
    market_calendar_build.add_argument("--market", required=True)
    market_calendar_build.add_argument("--valid-from", required=True)
    market_calendar_build.add_argument("--valid-to", required=True)
    market_calendar_build.add_argument("--publisher", required=True)
    market_calendar_build.add_argument("--source-url", required=True)
    market_calendar_build.add_argument("--published-date", required=True)
    market_calendar_build.add_argument(
        "--authority-source",
        default=None,
        help=(
            "Optional raw authority snapshot used to prove the normalized "
            "sessions CSV."
        ),
    )
    market_calendar_build.add_argument(
        "--authority-source-schema",
        default="",
        help=(
            "Authority parser contract; currently supported: "
            f"{NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA}."
        ),
    )
    market_calendar_build.add_argument("--out", required=True)

    portability = sub.add_parser(
        "market-portability-report",
        help="Export strategy portability across market profiles.",
    )
    portability.add_argument("--out", required=True)
    portability.add_argument("--market", action="append", dest="markets")
    portability.add_argument("--strategy", action="append", dest="strategies")
    portability.add_argument("--explicit-fee-model", action="store_true")
    portability.add_argument("--fail-on-breach", action="store_true")
    portability.add_argument("--fail-on-gaps", action="store_true")
    portability.add_argument("--fail-on-blocked-actions", action="store_true")
    portability.add_argument("--fail-on-actions", action="store_true")

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

    proof_verify = sub.add_parser(
        "verify-proof-report",
        help=(
            "Reconstruct a proof report from its manifest-bound replay "
            "directories."
        ),
    )
    proof_verify.add_argument("--report", required=True)
    proof_verify.add_argument("--fail-on-breach", action="store_true")

    catalog = sub.add_parser("catalog-runs", help="Build an experiment catalog from manifest-bearing run folders.")
    catalog.add_argument("--roots", nargs="+", required=True)
    catalog.add_argument("--out", required=True)
    catalog.add_argument("--provider-broker-active-lineage-index")
    catalog.add_argument(
        "--provider-active-lineage-chain-audit",
        action="append",
        dest="provider_active_lineage_chain_audits",
    )
    catalog.add_argument("--fail-on-actions", action="store_true")
    catalog.add_argument("--fail-on-blocked-actions", action="store_true")
    catalog.add_argument("--fail-on-catalog-gaps", action="store_true")
    catalog.add_argument("--fail-on-placeholder-schema", action="store_true")
    catalog.add_argument("--fail-on-blocked-placeholder-schema", action="store_true")
    catalog.add_argument("--fail-on-broker-roundtrip-portfolio-breach", action="store_true")
    catalog.add_argument("--require-broker-roundtrip-portfolio-safe", action="store_true")
    catalog.add_argument("--fail-on-broker-roundtrip-portfolio-concentration-breach", action="store_true")
    catalog.add_argument("--require-broker-roundtrip-portfolio-concentration-ok", action="store_true")
    catalog.add_argument("--fail-on-broker-roundtrip-resume-route-breach", action="store_true")
    catalog.add_argument("--require-broker-roundtrip-resume-route-ready", action="store_true")
    catalog.add_argument("--fail-on-provider-broker-roundtrip-synthetic-sidecar-breach", action="store_true")
    catalog.add_argument("--require-provider-broker-roundtrip-synthetic-sidecar-ready", action="store_true")
    catalog.add_argument(
        "--fail-on-provider-lineage-selection-blocks",
        action="store_true",
    )

    evidence = sub.add_parser("review-strategy-evidence", help="Gate strategy evidence from an experiment catalog.")
    evidence.add_argument("--catalog", required=True)
    evidence.add_argument("--out", required=True)
    evidence.add_argument("--profile", default=None)
    evidence.add_argument("--required-run-type", action="append", dest="required_run_types")
    evidence.add_argument("--min-passed-per-type", type=int, default=1)
    evidence.add_argument("--allow-dirty-git", action="store_true")
    evidence.add_argument("--require-same-git-commit", action="store_true")
    evidence.add_argument("--require-same-strategy", action="store_true")
    evidence.add_argument("--require-same-market", action="store_true")
    evidence.add_argument("--expected-strategy", default=None)
    evidence.add_argument("--expected-market", default=None)
    evidence.add_argument("--require-file-inputs", action="store_true")
    evidence.add_argument("--allow-non-file-inputs", action="store_true")
    evidence.add_argument("--fail-on-placeholder-schema", action="store_true")
    evidence.add_argument("--fail-on-blocked-placeholder-schema", action="store_true")
    evidence.add_argument("--fail-on-broker-roundtrip-portfolio-breach", action="store_true")
    evidence.add_argument("--require-broker-roundtrip-portfolio-safe", action="store_true")
    evidence.add_argument("--fail-on-broker-roundtrip-portfolio-concentration-breach", action="store_true")
    evidence.add_argument("--require-broker-roundtrip-portfolio-concentration-ok", action="store_true")
    evidence.add_argument("--fail-on-broker-roundtrip-resume-route-breach", action="store_true")
    evidence.add_argument("--require-broker-roundtrip-resume-route-ready", action="store_true")
    evidence.add_argument("--fail-on-provider-broker-roundtrip-synthetic-sidecar-breach", action="store_true")
    evidence.add_argument("--require-provider-broker-roundtrip-synthetic-sidecar-ready", action="store_true")
    provider_lineage_selection = evidence.add_mutually_exclusive_group()
    provider_lineage_selection.add_argument(
        "--require-provider-lineage-selection",
        dest="require_provider_lineage_selection",
        action="store_true",
        help=(
            "Require passed selectable active-lineage proofs for provider "
            "acknowledgement, round-trip, and certificate evidence."
        ),
    )
    provider_lineage_selection.add_argument(
        "--allow-ineligible-provider-lineage-for-audit",
        dest="require_provider_lineage_selection",
        action="store_false",
        help=(
            "Audit/reproduction only: inspect retained or unindexed provider "
            "lineage without producing launch-ready evidence."
        ),
    )
    evidence.set_defaults(require_provider_lineage_selection=None)
    evidence.add_argument("--fail-on-breach", action="store_true")

    verify_evidence = sub.add_parser(
        "verify-strategy-evidence",
        help=(
            "Reopen a completed strategy-evidence review and verify its "
            "manifest-bound sources and retained provider proofs."
        ),
    )
    verify_evidence.add_argument("--evidence", required=True)
    verify_evidence.add_argument("--fail-on-breach", action="store_true")

    scorecard = sub.add_parser(
        "score-strategy-readiness",
        help="Rank strategy evidence profiles from an experiment catalog.",
    )
    scorecard.add_argument("--catalog", required=True)
    scorecard.add_argument("--out", required=True)
    scorecard.add_argument("--profile", action="append", dest="profiles")
    scorecard.add_argument("--market", default=None)
    scorecard.add_argument("--ops-strategy", default=None)
    scorecard.add_argument("--allow-dirty-git", action="store_true")
    scorecard.add_argument("--require-file-inputs", action="store_true")
    scorecard.add_argument("--research-family", default=None)
    scorecard.add_argument("--require-research-family", action="store_true")
    scorecard.add_argument("--fail-on-breach", action="store_true")
    scorecard.add_argument("--fail-on-blocked-actions", action="store_true")
    scorecard.add_argument("--fail-on-actions", action="store_true")

    strategy_portfolio = sub.add_parser(
        "allocate-strategy-portfolio",
        help="Allocate paper/shadow capital across ready strategy scorecard profiles.",
    )
    strategy_portfolio.add_argument("--scorecard", required=True)
    strategy_portfolio.add_argument("--out", required=True)
    strategy_portfolio.add_argument("--total-capital", type=float, default=1_000_000.0)
    strategy_portfolio.add_argument("--capital-currency", default="INR")
    strategy_portfolio.add_argument("--reserve-weight", type=float, default=0.10)
    strategy_portfolio.add_argument("--max-profile-weight", type=float, default=0.40)
    strategy_portfolio.add_argument("--min-readiness-score", type=float, default=1.0)
    strategy_portfolio.add_argument("--min-strategy-count", type=int, default=1)
    strategy_portfolio.add_argument("--min-market-count", type=int, default=1)
    strategy_portfolio.add_argument("--max-strategy-weight", type=float, default=None)
    strategy_portfolio.add_argument("--max-market-weight", type=float, default=None)
    strategy_portfolio.add_argument("--allow-unready", action="store_true")
    strategy_portfolio.add_argument(
        "--require-scorecard-manifest",
        action="store_true",
        help=(
            "Require a current strategy-scorecard manifest even when the CSV "
            "does not carry registered research-family proof."
        ),
    )
    strategy_portfolio.add_argument("--include-profile", action="append", dest="include_profiles")
    strategy_portfolio.add_argument("--exclude-profile", action="append", dest="exclude_profiles")
    strategy_portfolio.add_argument("--fail-on-breach", action="store_true")
    strategy_portfolio.add_argument("--fail-on-blocked-actions", action="store_true")
    strategy_portfolio.add_argument("--fail-on-actions", action="store_true")

    route_readiness = sub.add_parser(
        "review-route-readiness",
        help="Combine portability plus strategy/ops evidence into route readiness.",
    )
    route_readiness.add_argument("--portability", required=True)
    route_readiness.add_argument("--strategy-evidence", action="append", dest="strategy_evidence")
    route_readiness.add_argument("--ops-evidence", action="append", dest="ops_evidence")
    route_readiness.add_argument("--out", required=True)
    route_readiness.add_argument("--allow-non-file-ops-inputs", action="store_true")
    route_readiness.add_argument("--fail-on-breach", action="store_true")
    route_readiness.add_argument("--fail-on-blocked-actions", action="store_true")
    route_readiness.add_argument("--fail-on-actions", action="store_true")

    leadlag_sweep = sub.add_parser("sweep-leadlag", help="Run lead-lag replay robustness sweep.")
    leadlag_sweep.add_argument("--leader", required=True)
    leadlag_sweep.add_argument("--laggard", required=True)
    leadlag_sweep.add_argument("--out", required=True)
    leadlag_sweep.add_argument("--no-filter-session", action="store_true")
    leadlag_sweep.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
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
    _add_generic_cost_args(leadlag_sweep)

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

    parity_promotion = sub.add_parser(
        "promote-parity-candidate",
        help="Promote passed parity scan/audit/sweep evidence into a launch-compatible candidate.",
    )
    parity_promotion.add_argument("--scan", required=True)
    parity_promotion.add_argument("--edge-audit", required=True)
    parity_promotion.add_argument("--sweep", required=True)
    parity_promotion.add_argument("--out", required=True)
    parity_promotion.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    parity_promotion.add_argument("--allow-unpassed-edge", action="store_true")
    parity_promotion.add_argument("--allow-empty-sweep-pass", action="store_true")
    parity_promotion.add_argument("--min-total-opportunities", type=int, default=1)
    parity_promotion.add_argument("--min-best-net-edge", type=float, default=0.0)
    parity_promotion.add_argument("--min-candidate-net-edge", type=float, default=0.0)
    parity_promotion.add_argument("--min-candidate-persistence-ticks", type=float, default=0.0)
    parity_promotion.add_argument("--min-sweep-pass-rate", type=float, default=0.0)
    parity_promotion.add_argument("--min-passed-scenarios", type=int, default=1)
    parity_promotion.add_argument("--fail-on-breach", action="store_true")

    parity_orders = sub.add_parser(
        "plan-parity-orders",
        help="Create broker-neutral multi-leg paper/shadow order templates from a promoted parity/box candidate.",
    )
    parity_orders.add_argument("--promotion", required=True)
    parity_orders.add_argument("--out", required=True)
    parity_orders.add_argument("--symbol-prefix", default="NIFTY")
    parity_orders.add_argument("--future-instrument-id", default="NIFTY_FUT")
    parity_orders.add_argument("--direction", default=None)
    parity_orders.add_argument("--expiry", default=None)
    parity_orders.add_argument("--strike", type=float, default=None)
    parity_orders.add_argument("--low-strike", type=float, default=None)
    parity_orders.add_argument("--high-strike", type=float, default=None)
    parity_orders.add_argument("--qty", type=int, default=None)
    parity_orders.add_argument("--call-price", type=float, default=None)
    parity_orders.add_argument("--put-price", type=float, default=None)
    parity_orders.add_argument("--future-price", type=float, default=None)
    parity_orders.add_argument("--low-call-price", type=float, default=None)
    parity_orders.add_argument("--low-put-price", type=float, default=None)
    parity_orders.add_argument("--high-call-price", type=float, default=None)
    parity_orders.add_argument("--high-put-price", type=float, default=None)
    parity_orders.add_argument("--price-offset-ticks", type=float, default=0.0)
    parity_orders.add_argument("--tick-size", type=float, default=0.05)
    parity_orders.add_argument("--max-order-qty", type=int, default=None)
    parity_orders.add_argument("--max-notional", type=float, default=None)
    parity_orders.add_argument("--price-band-pct", type=float, default=None)
    parity_orders.add_argument("--output-file", default="parity_order_candidates.csv")
    parity_orders.add_argument("--allow-unready-promotion", action="store_true")
    parity_orders.add_argument("--fail-on-breach", action="store_true")

    parity_launch_pipeline = sub.add_parser(
        "pipeline-parity-launch",
        help="Run promoted parity/box candidate through order plan, staging, launch, export, and upload pack.",
    )
    parity_launch_pipeline.add_argument("--promotion", required=True)
    parity_launch_pipeline.add_argument("--out", required=True)
    parity_launch_pipeline.add_argument("--adapter", default="arrow_money")
    parity_launch_pipeline.add_argument("--mode", default="shadow", choices=["paper", "shadow"])
    parity_launch_pipeline.add_argument("--route-tag", default=None)
    parity_launch_pipeline.add_argument("--symbol-prefix", default="NIFTY")
    parity_launch_pipeline.add_argument("--future-instrument-id", default="NIFTY_FUT")
    parity_launch_pipeline.add_argument("--direction", default=None)
    parity_launch_pipeline.add_argument("--expiry", default=None)
    parity_launch_pipeline.add_argument("--strike", type=float, default=None)
    parity_launch_pipeline.add_argument("--low-strike", type=float, default=None)
    parity_launch_pipeline.add_argument("--high-strike", type=float, default=None)
    parity_launch_pipeline.add_argument("--qty", type=int, default=None)
    parity_launch_pipeline.add_argument("--call-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--put-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--future-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--low-call-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--low-put-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--high-call-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--high-put-price", type=float, default=None)
    parity_launch_pipeline.add_argument("--price-offset-ticks", type=float, default=0.0)
    parity_launch_pipeline.add_argument("--tick-size", type=float, default=0.05)
    parity_launch_pipeline.add_argument("--max-order-qty", type=int, default=None)
    parity_launch_pipeline.add_argument("--max-notional", type=float, default=None)
    parity_launch_pipeline.add_argument("--price-band-pct", type=float, default=None)
    parity_launch_pipeline.add_argument("--max-orders", type=int, default=None)
    parity_launch_pipeline.add_argument("--contract-multiplier", type=float, default=1.0)
    parity_launch_pipeline.add_argument("--product", default="MIS")
    parity_launch_pipeline.add_argument("--exchange", default="NFO")
    parity_launch_pipeline.add_argument("--broker-schema-audit", default=None)
    parity_launch_pipeline.add_argument("--broker-mapping-draft", default=None)
    parity_launch_pipeline.add_argument("--broker-mapped-orders", default=None)
    parity_launch_pipeline.add_argument("--broker-halt-export", default=None)
    parity_launch_pipeline.add_argument("--broker-reconciliation", default=None)
    parity_launch_pipeline.add_argument("--broker-runtime-session", default=None)
    parity_launch_pipeline.add_argument("--broker-vendor-data-readiness", default=None)
    parity_launch_pipeline.add_argument("--require-broker-schema-audit", action="store_true")
    parity_launch_pipeline.add_argument("--require-broker-mapping-draft", action="store_true")
    parity_launch_pipeline.add_argument("--require-broker-mapped-orders", action="store_true")
    parity_launch_pipeline.add_argument("--require-broker-halt-export", action="store_true")
    parity_launch_pipeline.add_argument("--require-broker-reconciliation", action="store_true")
    parity_launch_pipeline.add_argument("--require-broker-runtime-session", action="store_true")
    parity_launch_pipeline.add_argument("--allow-placeholder-schema", action="store_true")
    parity_launch_pipeline.add_argument("--fail-on-breach", action="store_true")

    surface_mm_sweep = sub.add_parser("sweep-surface-mm", help="Run surface MM replay robustness sweep.")
    surface_mm_sweep.add_argument("--quotes", required=True)
    surface_mm_sweep.add_argument("--chain", required=True)
    surface_mm_sweep.add_argument("--out", required=True)
    surface_mm_sweep.add_argument("--no-filter-session", action="store_true")
    surface_mm_sweep.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
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
    surface_mm_sweep.add_argument("--quote-risk-review", default=None)
    surface_mm_sweep.add_argument("--require-quote-risk-review", action="store_true")
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

    walkforward_split_audit = sub.add_parser(
        "audit-walkforward-splits",
        help="Audit past-only expanding temporal splits with purge and embargo evidence.",
    )
    walkforward_split_audit.add_argument("--labels", required=True)
    walkforward_split_audit.add_argument("--out", required=True)
    walkforward_split_audit.add_argument("--time-col", default="ts")
    walkforward_split_audit.add_argument("--label-end-col", default="label_end_ts")
    walkforward_split_audit.add_argument("--n-splits", type=int, default=3)
    walkforward_split_audit.add_argument("--embargo-ns", type=int, default=0)
    walkforward_split_audit.add_argument("--test-size", type=int, default=None)
    walkforward_split_audit.add_argument("--min-train-rows", type=int, default=1)
    walkforward_split_audit.add_argument("--min-test-rows", type=int, default=1)
    walkforward_split_audit.add_argument("--fail-on-breach", action="store_true")
    walkforward_split_audit.add_argument("--fail-on-blocked-actions", action="store_true")
    walkforward_split_audit.add_argument("--fail-on-actions", action="store_true")

    robust_selection = sub.add_parser(
        "pipeline-robust-selection",
        help="Compare multi-period sweeps, audit selection overfit, and gate promotion.",
    )
    robust_selection.add_argument("--sweeps", nargs="+", required=True)
    robust_selection.add_argument("--out", required=True)
    robust_selection.add_argument("--label", action="append", dest="labels")
    robust_selection.add_argument("--group-cols", nargs="+", default=None)
    robust_selection.add_argument("--strategy", default="generic")
    robust_selection.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    robust_selection.add_argument("--research-registration", default=None)
    robust_selection.add_argument("--registered-study-label", default=None)
    robust_selection.add_argument(
        "--require-research-registration",
        action="store_true",
    )
    robust_selection.add_argument("--walkforward-split-audit", default=None)
    robust_selection.add_argument(
        "--require-walkforward-split-audit",
        action="store_true",
    )
    robust_selection.add_argument("--research-launch-matrix", default=None)
    robust_selection.add_argument("--research-launch-contract-id", default=None)
    robust_selection.add_argument(
        "--require-research-launch-contract",
        action="store_true",
    )
    robust_selection.add_argument(
        "--research-launch-execution-receipt",
        default=None,
    )
    robust_selection.add_argument(
        "--require-research-launch-execution-receipt",
        action="store_true",
    )
    robust_selection.add_argument("--min-selection-pass-rate", type=float, default=1.0)
    robust_selection.add_argument("--min-selection-sweeps", type=int, default=None)
    robust_selection.add_argument("--min-selection-median-net-pnl", type=float, default=0.0)
    robust_selection.add_argument("--max-selection-worst-drawdown", type=float, default=None)
    robust_selection.add_argument("--score-column", default="")
    robust_selection.add_argument("--max-partitions", type=int, default=12)
    robust_selection.add_argument("--min-partitions", type=int, default=4)
    robust_selection.add_argument("--min-scenarios", type=int, default=3)
    robust_selection.add_argument("--max-probability-overfit", type=float, default=0.25)
    robust_selection.add_argument("--min-median-oos-score", type=float, default=0.0)
    robust_selection.add_argument("--min-oos-positive-rate", type=float, default=0.5)
    robust_selection.add_argument("--min-median-rank-correlation", type=float, default=0.0)
    robust_selection.add_argument("--max-median-degradation", type=float, default=None)
    robust_selection.add_argument("--min-candidate-selection-rate", type=float, default=0.25)
    robust_selection.add_argument("--max-candidate-overfit-rate", type=float, default=0.25)
    robust_selection.add_argument("--min-candidate-oos-positive-rate", type=float, default=0.5)
    robust_selection.add_argument(
        "--significance-bootstrap-samples",
        type=int,
        default=10_000,
    )
    robust_selection.add_argument(
        "--significance-confidence-level",
        type=float,
        default=0.95,
    )
    robust_selection.add_argument("--significance-random-seed", type=int, default=1729)
    robust_selection.add_argument("--significance-zero-tolerance", type=float, default=0.0)
    robust_selection.add_argument("--min-significance-observations", type=int, default=6)
    robust_selection.add_argument(
        "--min-significance-nonzero-observations",
        type=int,
        default=6,
    )
    robust_selection.add_argument(
        "--min-significance-positive-rate",
        type=float,
        default=0.5,
    )
    robust_selection.add_argument(
        "--max-significance-adjusted-sign-pvalue",
        type=float,
        default=0.1,
    )
    robust_selection.add_argument(
        "--min-significance-bootstrap-probability-positive",
        type=float,
        default=0.95,
    )
    robust_selection.add_argument(
        "--min-significance-bootstrap-mean-lower",
        type=float,
        default=0.0,
    )
    robust_selection.add_argument("--holdout-sweeps", type=int, default=3)
    robust_selection.add_argument("--min-holdout-coverage-rate", type=float, default=1.0)
    robust_selection.add_argument("--min-holdout-proof-pass-rate", type=float, default=1.0)
    robust_selection.add_argument("--min-holdout-mean-score", type=float, default=0.0)
    robust_selection.add_argument("--min-holdout-median-score", type=float, default=0.0)
    robust_selection.add_argument("--min-holdout-worst-score", type=float, default=0.0)
    robust_selection.add_argument("--min-holdout-mean-net-pnl", type=float, default=0.0)
    robust_selection.add_argument("--min-holdout-worst-net-pnl", type=float, default=0.0)
    robust_selection.add_argument("--min-holdout-fills-per-sweep", type=float, default=1.0)
    robust_selection.add_argument("--max-holdout-worst-drawdown", type=float, default=None)
    robust_selection.add_argument("--min-promotion-pass-rate", type=float, default=1.0)
    robust_selection.add_argument("--min-promotion-sweeps", type=int, default=1)
    robust_selection.add_argument("--min-promotion-median-net-pnl", type=float, default=0.0)
    robust_selection.add_argument("--min-promotion-min-net-pnl", type=float, default=None)
    robust_selection.add_argument("--max-promotion-worst-drawdown", type=float, default=None)
    robust_selection.add_argument("--min-promotion-median-fills", type=float, default=1.0)
    robust_selection.add_argument(
        "--max-promotion-runs-with-losing-regimes",
        type=int,
        default=None,
    )
    robust_selection.add_argument("--max-promotion-otr", type=float, default=None)
    robust_selection.add_argument("--min-promotion-maker-share", type=float, default=None)
    robust_selection.add_argument("--min-promotion-markout-mean", type=float, default=None)
    robust_selection.add_argument("--fail-on-breach", action="store_true")
    robust_selection.add_argument("--fail-on-actions", action="store_true")

    backtest_overfit = sub.add_parser(
        "audit-backtest-overfit",
        help="Measure CSCV-style parameter-selection overfit across sweep periods.",
    )
    backtest_overfit.add_argument("--selection", required=True)
    backtest_overfit.add_argument("--out", required=True)
    backtest_overfit.add_argument("--split-column", default="sweep")
    backtest_overfit.add_argument("--score-column", default="")
    backtest_overfit.add_argument("--scenario-columns", nargs="+", default=None)
    backtest_overfit.add_argument("--max-partitions", type=int, default=12)
    backtest_overfit.add_argument("--allow-missing-selection-manifest", action="store_true")
    backtest_overfit.add_argument("--min-partitions", type=int, default=4)
    backtest_overfit.add_argument("--min-scenarios", type=int, default=3)
    backtest_overfit.add_argument("--max-probability-overfit", type=float, default=0.25)
    backtest_overfit.add_argument("--min-median-oos-score", type=float, default=0.0)
    backtest_overfit.add_argument("--min-oos-positive-rate", type=float, default=0.5)
    backtest_overfit.add_argument("--min-median-rank-correlation", type=float, default=0.0)
    backtest_overfit.add_argument("--max-median-degradation", type=float, default=None)
    backtest_overfit.add_argument("--min-candidate-selection-rate", type=float, default=0.25)
    backtest_overfit.add_argument("--max-candidate-overfit-rate", type=float, default=0.25)
    backtest_overfit.add_argument("--min-candidate-oos-positive-rate", type=float, default=0.5)
    backtest_overfit.add_argument("--fail-on-breach", action="store_true")
    backtest_overfit.add_argument("--fail-on-blocked-actions", action="store_true")
    backtest_overfit.add_argument("--fail-on-actions", action="store_true")

    backtest_significance = sub.add_parser(
        "audit-backtest-significance",
        help="Test selected-candidate significance across overfit audit partitions.",
    )
    backtest_significance.add_argument("--overfit-audit", required=True)
    backtest_significance.add_argument("--out", required=True)
    backtest_significance.add_argument("--bootstrap-samples", type=int, default=10_000)
    backtest_significance.add_argument("--confidence-level", type=float, default=0.95)
    backtest_significance.add_argument("--random-seed", type=int, default=1729)
    backtest_significance.add_argument("--zero-tolerance", type=float, default=0.0)
    backtest_significance.add_argument(
        "--allow-missing-overfit-manifest",
        action="store_true",
    )
    backtest_significance.add_argument("--min-observations", type=int, default=6)
    backtest_significance.add_argument("--min-nonzero-observations", type=int, default=6)
    backtest_significance.add_argument("--min-positive-rate", type=float, default=0.5)
    backtest_significance.add_argument(
        "--max-adjusted-sign-pvalue",
        type=float,
        default=0.1,
    )
    backtest_significance.add_argument(
        "--min-bootstrap-probability-positive",
        type=float,
        default=0.95,
    )
    backtest_significance.add_argument(
        "--min-bootstrap-mean-lower",
        type=float,
        default=0.0,
    )
    backtest_significance.add_argument("--allow-failed-overfit", action="store_true")
    backtest_significance.add_argument("--fail-on-breach", action="store_true")
    backtest_significance.add_argument("--fail-on-blocked-actions", action="store_true")
    backtest_significance.add_argument("--fail-on-actions", action="store_true")

    backtest_holdout = sub.add_parser(
        "audit-backtest-holdout",
        help="Evaluate a frozen selection on manifest-bound chronological holdouts.",
    )
    backtest_holdout.add_argument("--selection", required=True)
    backtest_holdout.add_argument("--holdout-sweeps", nargs="+", required=True)
    backtest_holdout.add_argument("--out", required=True)
    backtest_holdout.add_argument("--label", action="append", dest="labels")
    backtest_holdout.add_argument("--group-cols", nargs="+", required=True)
    backtest_holdout.add_argument("--score-column", default="")
    backtest_holdout.add_argument("--proof-column", default="proof_passed")
    backtest_holdout.add_argument(
        "--allow-missing-selection-manifest",
        action="store_true",
    )
    backtest_holdout.add_argument(
        "--allow-missing-sweep-manifests",
        action="store_true",
    )
    backtest_holdout.add_argument("--allow-failed-selection", action="store_true")
    backtest_holdout.add_argument("--min-sweeps", type=int, default=3)
    backtest_holdout.add_argument("--min-candidate-coverage-rate", type=float, default=1.0)
    backtest_holdout.add_argument("--min-proof-pass-rate", type=float, default=1.0)
    backtest_holdout.add_argument("--min-mean-score", type=float, default=0.0)
    backtest_holdout.add_argument("--min-median-score", type=float, default=0.0)
    backtest_holdout.add_argument("--min-worst-score", type=float, default=0.0)
    backtest_holdout.add_argument("--min-mean-net-pnl", type=float, default=0.0)
    backtest_holdout.add_argument("--min-worst-net-pnl", type=float, default=0.0)
    backtest_holdout.add_argument("--min-fills-per-sweep", type=float, default=1.0)
    backtest_holdout.add_argument("--max-worst-drawdown", type=float, default=None)
    backtest_holdout.add_argument("--fail-on-breach", action="store_true")
    backtest_holdout.add_argument("--fail-on-blocked-actions", action="store_true")
    backtest_holdout.add_argument("--fail-on-actions", action="store_true")

    research_family_registration = sub.add_parser(
        "register-research-family",
        help="Fingerprint a planned research family before study outcomes exist.",
    )
    research_family_registration.add_argument("--plan", required=True)
    research_family_registration.add_argument("--out", required=True)
    research_family_registration.add_argument("--family-id", required=True)
    research_family_registration.add_argument("--min-studies", type=int, default=2)
    research_family_registration.add_argument(
        "--min-development-sweeps",
        type=int,
        default=6,
    )
    research_family_registration.add_argument(
        "--min-holdout-sweeps",
        type=int,
        default=3,
    )
    research_family_registration.add_argument("--fail-on-breach", action="store_true")
    research_family_registration.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    research_family_registration.add_argument("--fail-on-actions", action="store_true")

    research_family_launch = sub.add_parser(
        "plan-research-family-launches",
        help="Build immutable robust-study launch contracts and closure coverage.",
    )
    research_family_launch.add_argument("--registration", required=True)
    research_family_launch.add_argument("--out", required=True)
    research_family_launch.add_argument("--abandonments", default=None)
    research_family_launch.add_argument(
        "--attest-abandonments",
        action="store_true",
    )
    research_family_launch.add_argument("--fail-on-breach", action="store_true")
    research_family_launch.add_argument(
        "--fail-on-blocked-actions",
        action="store_true",
    )
    research_family_launch.add_argument("--fail-on-actions", action="store_true")

    run_research_family_study = sub.add_parser(
        "run-research-family-study",
        help="Execute one current immutable registered-study launch contract.",
    )
    run_research_family_study.add_argument("--launch-matrix", required=True)
    run_research_family_study.add_argument("--contract-id", required=True)
    run_research_family_study.add_argument("--retry-of-attempt-id", default=None)
    run_research_family_study.add_argument("--retry-reason", default=None)
    run_research_family_study.add_argument("--attest-retry", action="store_true")

    recover_research_family_outcome = sub.add_parser(
        "recover-research-family-study-outcome",
        help="Attest and finalize an unfinalized result-bearing launch attempt.",
    )
    recover_research_family_outcome.add_argument("--launch-matrix", required=True)
    recover_research_family_outcome.add_argument("--attempt-id", required=True)
    recover_research_family_outcome.add_argument(
        "--exit-status",
        type=int,
        required=True,
    )
    recover_research_family_outcome.add_argument("--recovery-reason", required=True)
    recover_research_family_outcome.add_argument(
        "--attest-recovery",
        action="store_true",
    )

    research_family = sub.add_parser(
        "audit-research-family",
        help="Apply family-wise correction across declared robust candidate studies.",
    )
    research_family.add_argument("--studies", nargs="+", required=True)
    research_family.add_argument("--out", required=True)
    research_family.add_argument("--family-id", required=True)
    research_family.add_argument("--label", action="append", dest="labels")
    research_family.add_argument("--attest-complete-family", action="store_true")
    research_family.add_argument("--registration", default=None)
    research_family.add_argument("--launch-matrix", default=None)
    research_family.add_argument(
        "--require-prospective-registration",
        action="store_true",
    )
    research_family.add_argument(
        "--require-launch-coverage",
        action="store_true",
    )
    research_family.add_argument(
        "--allow-missing-study-manifests",
        action="store_true",
    )
    research_family.add_argument("--min-studies", type=int, default=2)
    research_family.add_argument(
        "--max-holm-adjusted-pvalue",
        type=float,
        default=0.1,
    )
    research_family.add_argument("--min-family-candidates", type=int, default=1)
    research_family.add_argument("--fail-on-breach", action="store_true")
    research_family.add_argument("--fail-on-blocked-actions", action="store_true")
    research_family.add_argument("--fail-on-actions", action="store_true")

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
    promote.add_argument("--overfit-audit", default=None)
    promote.add_argument("--require-overfit-audit", action="store_true")
    promote.add_argument("--significance-audit", default=None)
    promote.add_argument("--require-significance-audit", action="store_true")
    promote.add_argument("--holdout-audit", default=None)
    promote.add_argument("--require-holdout-audit", action="store_true")
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
    launch.add_argument("--require-quote-risk-review", action="store_true")
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
    upload_pack.add_argument("--fail-on-blocked-actions", action="store_true")
    upload_pack.add_argument("--fail-on-actions", action="store_true")

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
    mapping_draft.add_argument("--fail-on-blocked-actions", action="store_true")
    mapping_draft.add_argument("--fail-on-actions", action="store_true")

    vendor_intake = sub.add_parser(
        "intake-vendor-csv",
        help="Profile an unknown vendor CSV and draft a normalized data mapping.",
    )
    vendor_intake.add_argument("--sample", required=True)
    vendor_intake.add_argument("--out", required=True)
    vendor_intake.add_argument("--adapter", default="arrow_money")
    vendor_intake.add_argument("--kind", default="auto")
    vendor_intake.add_argument("--sample-rows", type=int, default=1000)
    vendor_intake.add_argument("--min-mapping-coverage", type=float, default=1.0)
    vendor_intake.add_argument("--output-mapping-file", default="vendor_mapping_draft.csv")
    vendor_intake.add_argument("--fail-on-breach", action="store_true")
    vendor_intake.add_argument("--fail-on-blocked-actions", action="store_true")
    vendor_intake.add_argument("--fail-on-actions", action="store_true")
    verify_vendor_intake = sub.add_parser(
        "verify-vendor-csv-intake",
        help="Reconstruct a write-once vendor CSV intake and verify its source is current.",
    )
    verify_vendor_intake.add_argument("--intake", required=True)
    verify_vendor_intake.add_argument("--fail-on-breach", action="store_true")
    vendor_mapping_review = sub.add_parser(
        "review-vendor-mapping",
        help="Seal an operator-attested mapping against a current vendor CSV intake.",
    )
    vendor_mapping_review.add_argument("--intake", required=True)
    vendor_mapping_review.add_argument("--mapping", required=True)
    vendor_mapping_review.add_argument("--decision", required=True)
    vendor_mapping_review.add_argument("--out", required=True)
    vendor_mapping_review.add_argument(
        "--output-mapping-file",
        default="reviewed_vendor_mapping.csv",
    )
    vendor_mapping_review.add_argument("--fail-on-rejected", action="store_true")
    verify_vendor_mapping_review_parser = sub.add_parser(
        "verify-vendor-mapping-review",
        help="Reconstruct a sealed vendor mapping review and verify all retained inputs.",
    )
    verify_vendor_mapping_review_parser.add_argument("--review", required=True)
    verify_vendor_mapping_review_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    vendor_mapping_scope_review = sub.add_parser(
        "review-vendor-mapping-scope",
        help="Seal an operator decision for exact-header mapping reuse.",
    )
    vendor_mapping_scope_review.add_argument("--review", required=True)
    vendor_mapping_scope_review.add_argument("--decision", required=True)
    vendor_mapping_scope_review.add_argument("--out", required=True)
    vendor_mapping_scope_review.add_argument(
        "--output-mapping-file",
        default="scope_approved_vendor_mapping.csv",
    )
    vendor_mapping_scope_review.add_argument("--fail-on-rejected", action="store_true")
    verify_vendor_mapping_scope_review_parser = sub.add_parser(
        "verify-vendor-mapping-scope-review",
        help="Reconstruct an exact-header mapping scope review and retained approval.",
    )
    verify_vendor_mapping_scope_review_parser.add_argument(
        "--scope-review",
        required=True,
    )
    verify_vendor_mapping_scope_review_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )
    vendor_mapping_application = sub.add_parser(
        "apply-vendor-mapping-scope",
        help="Bind an approved exact-header mapping scope to a target intake.",
    )
    vendor_mapping_application.add_argument("--scope-review", required=True)
    vendor_mapping_application.add_argument("--intake", required=True)
    vendor_mapping_application.add_argument("--out", required=True)
    vendor_mapping_application.add_argument(
        "--output-mapping-file",
        default="target_applied_vendor_mapping.csv",
    )
    vendor_mapping_application.add_argument("--fail-on-breach", action="store_true")
    verify_vendor_mapping_application_parser = sub.add_parser(
        "verify-vendor-mapping-application",
        help="Reconstruct a target-bound exact-header mapping application.",
    )
    verify_vendor_mapping_application_parser.add_argument(
        "--application",
        required=True,
    )
    verify_vendor_mapping_application_parser.add_argument(
        "--fail-on-breach",
        action="store_true",
    )

    mapped_export = sub.add_parser("map-broker-orders", help="Map broker-neutral orders into a vendor CSV shape.")
    mapped_export.add_argument("--export", required=True)
    mapped_export.add_argument("--mapping", required=True)
    mapped_export.add_argument("--out", required=True)
    mapped_export.add_argument("--adapter", default="normalized")
    mapped_export.add_argument("--output-file", default="mapped_broker_orders.csv")
    mapped_export.add_argument("--allow-missing-required", action="store_true")
    mapped_export.add_argument("--fail-on-breach", action="store_true")
    mapped_export.add_argument("--fail-on-blocked-actions", action="store_true")
    mapped_export.add_argument("--fail-on-actions", action="store_true")

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
    reconcile.add_argument("--fail-on-blocked-actions", action="store_true")
    reconcile.add_argument("--fail-on-actions", action="store_true")

    broker_readiness = sub.add_parser("review-broker-readiness", help="Gate broker integration evidence before paper/shadow routing.")
    broker_readiness.add_argument("--out", required=True)
    broker_readiness.add_argument("--adapter", default="arrow_money")
    broker_readiness.add_argument("--schema-audit", default=None)
    broker_readiness.add_argument("--order-export", default=None)
    broker_readiness.add_argument("--mapping-draft", default=None)
    broker_readiness.add_argument("--mapped-orders", default=None)
    broker_readiness.add_argument("--upload-pack", default=None)
    broker_readiness.add_argument("--halt-export", default=None)
    broker_readiness.add_argument("--reconciliation", default=None)
    broker_readiness.add_argument("--runtime-session", default=None)
    broker_readiness.add_argument("--resume-gate", default=None)
    broker_readiness.add_argument("--dispatch-roundtrip", default=None)
    broker_readiness.add_argument("--vendor-market-data-batch", default=None)
    broker_readiness.add_argument("--expected-market", default="")
    broker_readiness.add_argument("--expected-vendor-data-kind", default="", choices=["", "ticks", "chain"])
    broker_readiness.add_argument("--allow-placeholder-schema", action="store_true")
    broker_readiness.add_argument("--allow-adapter-mismatch", action="store_true")
    broker_readiness.add_argument("--skip-schema-audit", action="store_true")
    broker_readiness.add_argument("--skip-order-export", action="store_true")
    broker_readiness.add_argument("--skip-upload-pack", action="store_true")
    broker_readiness.add_argument("--require-mapping-draft", action="store_true")
    broker_readiness.add_argument("--require-mapped-orders", action="store_true")
    broker_readiness.add_argument("--require-halt-export", action="store_true")
    broker_readiness.add_argument("--require-reconciliation", action="store_true")
    broker_readiness.add_argument("--require-runtime-session", action="store_true")
    broker_readiness.add_argument("--require-resume-gate", action="store_true")
    broker_readiness.add_argument("--require-route-readiness", action="store_true")
    broker_readiness.add_argument("--require-dispatch-roundtrip", action="store_true")
    broker_readiness.add_argument("--fail-on-breach", action="store_true")
    broker_readiness.add_argument("--fail-on-blocked-actions", action="store_true")
    broker_readiness.add_argument("--fail-on-actions", action="store_true")

    shadow_session = sub.add_parser("shadow-session-report", help="Gate a full paper/shadow session after reconciliation.")
    shadow_session.add_argument("--launch", required=True)
    shadow_session.add_argument("--export", required=True)
    shadow_session.add_argument("--reconciliation", required=True)
    shadow_session.add_argument("--runtime-session", default=None)
    shadow_session.add_argument("--broker-readiness", default=None)
    shadow_session.add_argument("--out", required=True)
    shadow_session.add_argument("--allow-unready-launch", action="store_true")
    shadow_session.add_argument("--allow-unready-export", action="store_true")
    shadow_session.add_argument("--allow-failed-reconciliation", action="store_true")
    shadow_session.add_argument("--require-runtime-session", action="store_true")
    shadow_session.add_argument("--require-broker-readiness", action="store_true")
    shadow_session.add_argument("--allow-runtime-guard-halt", action="store_true")
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
    shadow_compare.add_argument("--max-runtime-halted-sessions", type=int, default=0)
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
    scaleup.add_argument("--data-readiness", default=None)
    scaleup.add_argument("--data-readiness-comparison", default=None)
    scaleup.add_argument("--strategy-portfolio", default=None)
    scaleup.add_argument("--route-readiness", default=None)
    scaleup.add_argument("--broker-readiness", default=None)
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
    scaleup.add_argument("--max-telemetry-age-ns", type=float, default=None)
    scaleup.add_argument("--max-lifecycle-orders", type=int, default=None)
    scaleup.add_argument("--max-replace-orders", type=int, default=None)
    scaleup.add_argument("--max-open-order-count", type=int, default=None)
    scaleup.add_argument("--max-open-order-qty", type=float, default=None)
    scaleup.add_argument("--max-open-order-notional", type=float, default=None)
    scaleup.add_argument("--max-open-order-age-ns", type=float, default=None)
    scaleup.add_argument("--max-gross-position-qty", type=float, default=None)
    scaleup.add_argument("--max-abs-net-position-qty", type=float, default=None)
    scaleup.add_argument("--max-orders-per-session", type=int, default=None)
    scaleup.add_argument("--max-session-notional", type=float, default=None)
    scaleup.add_argument("--max-gross-notional", type=float, default=None)
    scaleup.add_argument("--max-abs-net-delta", type=float, default=None)
    scaleup.add_argument("--max-abs-net-vega", type=float, default=None)
    scaleup.add_argument("--stop-loss", type=float, default=None)
    scaleup.add_argument("--allowed-adapter", action="append", dest="allowed_adapters")
    scaleup.add_argument("--require-proof-refresh", action="store_true")
    scaleup.add_argument("--require-instrument-metadata", action="store_true")
    scaleup.add_argument("--require-data-readiness", action="store_true")
    scaleup.add_argument("--require-data-readiness-comparison", action="store_true")
    scaleup.add_argument("--require-strategy-portfolio", action="store_true")
    scaleup.add_argument("--require-route-readiness", action="store_true")
    scaleup.add_argument("--require-broker-readiness", action="store_true")
    scaleup.add_argument("--require-resume-gate", action="store_true")
    scaleup.add_argument("--require-dispatch-roundtrip", action="store_true")
    scaleup.add_argument("--min-instrument-parse-coverage", type=float, default=1.0)
    scaleup.add_argument("--expected-strategy", default=None)
    scaleup.add_argument("--expected-market", default=None)
    scaleup.add_argument("--fail-on-breach", action="store_true")

    runtime_telemetry = sub.add_parser("build-runtime-telemetry", help="Build a guard-ready runtime telemetry snapshot.")
    runtime_telemetry.add_argument("--scaleup", required=True)
    runtime_telemetry.add_argument("--out", required=True)
    runtime_telemetry.add_argument("--export", default=None)
    runtime_telemetry.add_argument("--upload-pack", default=None)
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
    runtime_guard.add_argument("--as-of-ts-ns", type=float, default=None)
    runtime_guard.add_argument("--max-telemetry-age-ns", type=float, default=None)
    runtime_guard.add_argument("--fail-on-halt", action="store_true")
    runtime_guard.add_argument("--fail-on-blocked-actions", action="store_true")
    runtime_guard.add_argument("--fail-on-actions", action="store_true")

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
    halt_response.add_argument("--fail-on-blocked-actions", action="store_true")
    halt_response.add_argument("--fail-on-actions", action="store_true")

    runtime_session = sub.add_parser(
        "monitor-runtime-session",
        help="Build telemetry, evaluate the scale-up guard, and prepare halt response when needed.",
    )
    runtime_session.add_argument("--scaleup", required=True)
    runtime_session.add_argument("--out", required=True)
    runtime_session.add_argument("--export", default=None)
    runtime_session.add_argument("--upload-pack", default=None)
    runtime_session.add_argument("--reconciliation", default=None)
    runtime_session.add_argument("--instrument-metadata", default=None)
    runtime_session.add_argument("--pnl", default=None)
    runtime_session.add_argument("--open-orders", default=None)
    runtime_session.add_argument("--positions", default=None)
    runtime_session.add_argument("--snapshot-ts-ns", type=float, default=None)
    runtime_session.add_argument("--as-of-ts-ns", type=float, default=None)
    runtime_session.add_argument("--max-telemetry-age-ns", type=float, default=None)
    runtime_session.add_argument("--skip-halt-response", action="store_true")
    runtime_session.add_argument("--allow-missing-flatten-prices", action="store_true")
    runtime_session.add_argument("--default-order-type", default="LIMIT")
    runtime_session.add_argument("--default-time-in-force", default="DAY")
    runtime_session.add_argument("--fail-on-breach", action="store_true")
    runtime_session.add_argument("--fail-on-blocked-actions", action="store_true")
    runtime_session.add_argument("--fail-on-actions", action="store_true")

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
    halt_export.add_argument("--fail-on-blocked-actions", action="store_true")
    halt_export.add_argument("--fail-on-actions", action="store_true")

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
    halt_execution.add_argument("--fail-on-blocked-actions", action="store_true")
    halt_execution.add_argument("--fail-on-actions", action="store_true")

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
    halt_incident.add_argument("--fail-on-blocked-actions", action="store_true")
    halt_incident.add_argument("--fail-on-actions", action="store_true")

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
    resume_gate.add_argument("--require-operator-trigger-ack", action="store_true")
    resume_gate.add_argument("--max-failed-scaleup-checks", type=int, default=0)
    resume_gate.add_argument("--fail-on-breach", action="store_true")
    resume_gate.add_argument("--fail-on-blocked-actions", action="store_true")
    resume_gate.add_argument("--fail-on-actions", action="store_true")

    cutover_gate = sub.add_parser("review-cutover-gate", help="Authorize final paper/shadow/live-dryrun cutover.")
    cutover_gate.add_argument("--scaleup", required=True)
    cutover_gate.add_argument("--broker-readiness", required=True)
    cutover_gate.add_argument("--out", required=True)
    cutover_gate.add_argument("--runtime-session", default=None)
    cutover_gate.add_argument("--operator-review", default=None)
    cutover_gate.add_argument("--target-mode", default="live_dryrun", choices=["paper", "shadow", "live_dryrun"])
    cutover_gate.add_argument("--allow-unready-scaleup", action="store_true")
    cutover_gate.add_argument("--allow-missing-broker-readiness", action="store_true")
    cutover_gate.add_argument("--allow-missing-runtime-session", action="store_true")
    cutover_gate.add_argument("--allow-runtime-guard-halt", action="store_true")
    cutover_gate.add_argument("--require-route-readiness", action="store_true")
    cutover_gate.add_argument("--require-resume-gate", action="store_true")
    cutover_gate.add_argument("--require-dispatch-roundtrip", action="store_true")
    cutover_gate.add_argument("--allow-missing-operator-approval", action="store_true")
    cutover_gate.add_argument("--allow-missing-operator-identity-ack", action="store_true")
    cutover_gate.add_argument("--allow-missing-operator-limits-ack", action="store_true")
    cutover_gate.add_argument("--max-failed-scaleup-checks", type=int, default=0)
    cutover_gate.add_argument("--fail-on-breach", action="store_true")
    cutover_gate.add_argument("--fail-on-blocked-actions", action="store_true")
    cutover_gate.add_argument("--fail-on-actions", action="store_true")

    route_enable = sub.add_parser("review-route-enable", help="Build a broker route-enable packet after cutover.")
    route_enable.add_argument("--cutover", required=True)
    route_enable.add_argument("--upload-pack", required=True)
    route_enable.add_argument("--out", required=True)
    route_enable.add_argument("--order-export", default=None)
    route_enable.add_argument("--target-mode", default="live_dryrun", choices=["paper", "shadow", "live_dryrun"])
    route_enable.add_argument("--allow-unready-cutover", action="store_true")
    route_enable.add_argument("--allow-unready-upload", action="store_true")
    route_enable.add_argument("--require-order-export", action="store_true")
    route_enable.add_argument("--require-route-readiness", action="store_true")
    route_enable.add_argument("--require-dispatch-roundtrip", action="store_true")
    route_enable.add_argument("--allow-adapter-mismatch", action="store_true")
    route_enable.add_argument("--min-orders", type=int, default=1)
    route_enable.add_argument("--fail-on-breach", action="store_true")
    route_enable.add_argument("--fail-on-blocked-actions", action="store_true")
    route_enable.add_argument("--fail-on-actions", action="store_true")

    broker_dispatch = sub.add_parser("plan-broker-dispatch", help="Create a dry-run broker dispatch plan.")
    broker_dispatch.add_argument("--route-enable", required=True)
    broker_dispatch.add_argument("--upload-pack", required=True)
    broker_dispatch.add_argument("--out", required=True)
    broker_dispatch.add_argument("--upload-orders", default=None)
    broker_dispatch.add_argument("--target-mode", default="live_dryrun", choices=["paper", "shadow", "live_dryrun"])
    broker_dispatch.add_argument("--allow-disabled-route", action="store_true")
    broker_dispatch.add_argument("--allow-non-dry-run", action="store_true")
    broker_dispatch.add_argument("--require-route-readiness", action="store_true")
    broker_dispatch.add_argument("--require-dispatch-roundtrip", action="store_true")
    broker_dispatch.add_argument("--min-orders", type=int, default=1)
    broker_dispatch.add_argument("--max-orders", type=int, default=None)
    broker_dispatch.add_argument("--fail-on-breach", action="store_true")
    broker_dispatch.add_argument("--fail-on-blocked-actions", action="store_true")
    broker_dispatch.add_argument("--fail-on-actions", action="store_true")

    dispatch_send = sub.add_parser(
        "prepare-broker-dispatch-send",
        help="Prepare a non-submitting dry-run broker dispatch send packet.",
    )
    dispatch_send.add_argument("--dispatch", required=True)
    dispatch_send.add_argument("--out", required=True)
    dispatch_send.add_argument("--target-mode", default="live_dryrun", choices=["paper", "shadow", "live_dryrun"])
    dispatch_send.add_argument("--allow-unready-dispatch", action="store_true")
    dispatch_send.add_argument("--allow-unarmed-dispatch", action="store_true")
    dispatch_send.add_argument("--allow-non-dry-run", action="store_true")
    dispatch_send.add_argument("--require-route-readiness", action="store_true")
    dispatch_send.add_argument("--require-dispatch-roundtrip", action="store_true")
    dispatch_send.add_argument("--max-requests", type=int, default=None)
    dispatch_send.add_argument("--fail-on-breach", action="store_true")
    dispatch_send.add_argument("--fail-on-blocked-actions", action="store_true")
    dispatch_send.add_argument("--fail-on-actions", action="store_true")

    dispatch_ack = sub.add_parser(
        "reconcile-broker-dispatch",
        help="Reconcile broker acknowledgements for a dispatch batch.",
    )
    dispatch_ack.add_argument("--dispatch", required=True)
    dispatch_ack.add_argument("--send", default=None)
    dispatch_ack.add_argument("--acks", required=True)
    dispatch_ack.add_argument("--out", required=True)
    dispatch_ack.add_argument("--allow-unready-dispatch", action="store_true")
    dispatch_ack.add_argument("--allow-missing-acks", action="store_true")
    dispatch_ack.add_argument("--allow-rejections", action="store_true")
    dispatch_ack.add_argument("--require-route-readiness", action="store_true")
    dispatch_ack.add_argument("--require-dispatch-roundtrip", action="store_true")
    dispatch_ack.add_argument("--require-send-packet", action="store_true")
    dispatch_ack.add_argument("--max-duplicate-ack-orders", type=int, default=0)
    dispatch_ack.add_argument("--max-unmatched-acks", type=int, default=0)
    dispatch_ack.add_argument("--fail-on-breach", action="store_true")
    dispatch_ack.add_argument("--fail-on-blocked-actions", action="store_true")
    dispatch_ack.add_argument("--fail-on-actions", action="store_true")

    dispatch_roundtrip = sub.add_parser(
        "review-broker-dispatch-roundtrip",
        help="Review dispatch, send-packet, and acknowledgement evidence as one broker dry-run proof.",
    )
    dispatch_roundtrip.add_argument("--dispatch", required=True)
    dispatch_roundtrip.add_argument("--send", required=True)
    dispatch_roundtrip.add_argument("--ack", required=True)
    dispatch_roundtrip.add_argument("--out", required=True)
    dispatch_roundtrip.add_argument("--target-mode", default="live_dryrun", choices=["paper", "shadow", "live_dryrun"])
    dispatch_roundtrip.add_argument("--allow-unready-dispatch", action="store_true")
    dispatch_roundtrip.add_argument("--allow-unready-send", action="store_true")
    dispatch_roundtrip.add_argument("--allow-failed-ack", action="store_true")
    dispatch_roundtrip.add_argument("--allow-identity-mismatch", action="store_true")
    dispatch_roundtrip.add_argument("--allow-submission-enabled", action="store_true")
    dispatch_roundtrip.add_argument("--allow-missing-request-acks", action="store_true")
    dispatch_roundtrip.add_argument("--allow-rejections", action="store_true")
    dispatch_roundtrip.add_argument("--require-route-readiness", action="store_true")
    dispatch_roundtrip.add_argument("--require-dispatch-roundtrip", action="store_true")
    dispatch_roundtrip.add_argument("--require-ack-lineage", action="store_true")
    dispatch_roundtrip.add_argument("--max-duplicate-ack-orders", type=int, default=0)
    dispatch_roundtrip.add_argument("--max-unmatched-acks", type=int, default=0)
    dispatch_roundtrip.add_argument("--max-missing-request-acks", type=int, default=0)
    dispatch_roundtrip.add_argument("--max-total-failed-component-checks", type=int, default=0)
    dispatch_roundtrip.add_argument("--fail-on-breach", action="store_true")
    dispatch_roundtrip.add_argument("--fail-on-blocked-actions", action="store_true")
    dispatch_roundtrip.add_argument("--fail-on-actions", action="store_true")

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
    surface_quote.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
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

    surface_quality = sub.add_parser(
        "review-surface-quality",
        help="Check whether surface theo values beat current mids against future chain mids.",
    )
    surface_quality.add_argument("--quotes", required=True)
    surface_quality.add_argument("--chain", required=True)
    surface_quality.add_argument("--out", required=True)
    surface_quality.add_argument("--horizon-ns", nargs="+", required=True, type=int)
    surface_quality.add_argument("--no-filter-session", action="store_true")
    surface_quality.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    surface_quality.add_argument("--strategy", default="surface_mm")
    surface_quality.add_argument("--min-observations", type=int, default=1)
    surface_quality.add_argument("--min-instruments", type=int, default=1)
    surface_quality.add_argument("--min-mae-improvement", type=float, default=0.0)
    surface_quality.add_argument("--min-relative-mae-improvement", type=float, default=None)
    surface_quality.add_argument("--min-improvement-rate", type=float, default=None)
    surface_quality.add_argument("--max-theo-mae", type=float, default=None)
    surface_quality.add_argument("--fail-on-breach", action="store_true")

    surface_pipeline = sub.add_parser(
        "pipeline-surface-mm-research",
        help="Run surface quote generation, review, sweep proof, selection, and promotion.",
    )
    surface_pipeline.add_argument("--chain", required=True)
    surface_pipeline.add_argument("--futures", required=True)
    surface_pipeline.add_argument("--out", required=True)
    surface_pipeline.add_argument("--data-readiness-comparison", default=None)
    surface_pipeline.add_argument("--require-data-readiness-comparison", action="store_true")
    surface_pipeline.add_argument("--market-portability", default=None)
    surface_pipeline.add_argument("--require-market-portability", action="store_true")
    surface_pipeline.add_argument("--no-filter-session", action="store_true")
    surface_pipeline.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    surface_pipeline.add_argument("--asof-latency-ns", type=int, default=0)
    surface_pipeline.add_argument("--tte-years", type=float, default=30 / 365)
    surface_pipeline.add_argument("--tick-size", type=float, default=0.05)
    surface_pipeline.add_argument("--lot-size", type=int, default=75)
    surface_pipeline.add_argument("--quote-lots", type=int, default=1)
    surface_pipeline.add_argument("--edge-ticks", type=float, default=2.0)
    surface_pipeline.add_argument("--inventory-skew-ticks-per-lot", type=float, default=0.5)
    surface_pipeline.add_argument("--max-market-spread-ticks", type=float, default=None)
    surface_pipeline.add_argument("--max-quotes-per-snapshot", type=int, default=None)
    surface_pipeline.add_argument("--max-snapshots", type=int, default=None)
    surface_pipeline.add_argument("--surface-quality-horizon-ns", nargs="+", default=None, type=int)
    surface_pipeline.add_argument("--require-surface-quality", action="store_true")
    surface_pipeline.add_argument("--min-surface-quality-observations", type=int, default=1)
    surface_pipeline.add_argument("--min-surface-quality-instruments", type=int, default=1)
    surface_pipeline.add_argument("--min-surface-quality-mae-improvement", type=float, default=0.0)
    surface_pipeline.add_argument("--min-surface-quality-relative-improvement", type=float, default=None)
    surface_pipeline.add_argument("--min-surface-quality-improvement-rate", type=float, default=None)
    surface_pipeline.add_argument("--max-surface-quality-theo-mae", type=float, default=None)
    surface_pipeline.add_argument("--min-quotes", type=int, default=1)
    surface_pipeline.add_argument("--min-instruments", type=int, default=1)
    surface_pipeline.add_argument("--max-marketable-quotes", type=int, default=0)
    surface_pipeline.add_argument("--min-quote-edge", type=float, default=0.0)
    surface_pipeline.add_argument("--min-bid-share", type=float, default=0.25)
    surface_pipeline.add_argument("--max-bid-share", type=float, default=0.75)
    surface_pipeline.add_argument("--max-quotes-per-instrument", type=int, default=None)
    surface_pipeline.add_argument("--quote-ttl-ns", nargs="+", required=True, type=int)
    surface_pipeline.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    surface_pipeline.add_argument("--fill-depth-fraction", nargs="+", required=True, type=float)
    surface_pipeline.add_argument("--markout-horizon-ns", nargs="+", default=[1_000_000_000], type=int)
    surface_pipeline.add_argument("--contract-multiplier", type=float, default=1.0)
    surface_pipeline.add_argument("--max-quotes", type=int, default=None)
    surface_pipeline.add_argument("--min-net-pnl", type=float, default=0.0)
    surface_pipeline.add_argument("--min-fills", type=int, default=1)
    surface_pipeline.add_argument("--max-drawdown", type=float, default=None)
    surface_pipeline.add_argument("--max-otr", type=float, default=None)
    surface_pipeline.add_argument("--min-maker-share", type=float, default=1.0)
    surface_pipeline.add_argument("--min-markout-mean", type=float, default=None)
    surface_pipeline.add_argument("--min-selection-pass-rate", type=float, default=1.0)
    surface_pipeline.add_argument("--min-selection-sweeps", type=int, default=1)
    surface_pipeline.add_argument("--min-selection-median-net-pnl", type=float, default=0.0)
    surface_pipeline.add_argument("--max-selection-worst-drawdown", type=float, default=None)
    surface_pipeline.add_argument("--min-promotion-pass-rate", type=float, default=1.0)
    surface_pipeline.add_argument("--min-promotion-sweeps", type=int, default=1)
    surface_pipeline.add_argument("--min-promotion-median-net-pnl", type=float, default=0.0)
    surface_pipeline.add_argument("--min-promotion-median-fills", type=float, default=1.0)
    surface_pipeline.add_argument("--fail-on-breach", action="store_true")

    surface_launch_pipeline = sub.add_parser(
        "pipeline-surface-mm-launch",
        help="Run a promoted surface-MM pipeline through staging, launch, export, upload, and broker readiness.",
    )
    surface_launch_pipeline.add_argument("--surface-pipeline", required=True)
    surface_launch_pipeline.add_argument("--out", required=True)
    surface_launch_pipeline.add_argument("--adapter", default="arrow_money")
    surface_launch_pipeline.add_argument("--mode", default="shadow", choices=["paper", "shadow"])
    surface_launch_pipeline.add_argument("--route-tag", default=None)
    surface_launch_pipeline.add_argument("--expected-strategy", default="surface_mm")
    surface_launch_pipeline.add_argument("--expected-market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    surface_launch_pipeline.add_argument("--allow-unready-surface-pipeline", action="store_true")
    surface_launch_pipeline.add_argument("--max-order-qty", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-notional", type=float, default=None)
    surface_launch_pipeline.add_argument("--price-band-pct", type=float, default=None)
    surface_launch_pipeline.add_argument("--max-orders", type=int, default=None)
    surface_launch_pipeline.add_argument("--contract-multiplier", type=float, default=1.0)
    surface_launch_pipeline.add_argument("--quote-ttl-ns", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-quote-order-messages", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-active-quotes", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-quote-replaces", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-quote-cancels", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-quote-messages-per-snapshot", type=int, default=None)
    surface_launch_pipeline.add_argument("--expected-quote-fills", type=int, default=None)
    surface_launch_pipeline.add_argument("--max-quote-otr", type=float, default=None)
    surface_launch_pipeline.add_argument("--product", default="MIS")
    surface_launch_pipeline.add_argument("--exchange", default="NFO")
    surface_launch_pipeline.add_argument("--broker-schema-audit", default=None)
    surface_launch_pipeline.add_argument("--broker-mapping-draft", default=None)
    surface_launch_pipeline.add_argument("--broker-mapped-orders", default=None)
    surface_launch_pipeline.add_argument("--broker-halt-export", default=None)
    surface_launch_pipeline.add_argument("--broker-reconciliation", default=None)
    surface_launch_pipeline.add_argument("--broker-runtime-session", default=None)
    surface_launch_pipeline.add_argument("--broker-vendor-data-readiness", default=None)
    surface_launch_pipeline.add_argument("--require-broker-schema-audit", action="store_true")
    surface_launch_pipeline.add_argument("--require-broker-mapping-draft", action="store_true")
    surface_launch_pipeline.add_argument("--require-broker-mapped-orders", action="store_true")
    surface_launch_pipeline.add_argument("--require-broker-halt-export", action="store_true")
    surface_launch_pipeline.add_argument("--require-broker-reconciliation", action="store_true")
    surface_launch_pipeline.add_argument("--require-broker-runtime-session", action="store_true")
    surface_launch_pipeline.add_argument("--allow-placeholder-schema", action="store_true")
    surface_launch_pipeline.add_argument("--fail-on-breach", action="store_true")

    quote_review = sub.add_parser("review-quotes", help="Review generated surface quotes for MM risk hygiene.")
    quote_review.add_argument("--quotes", required=True)
    quote_review.add_argument("--out", required=True)
    quote_review.add_argument("--strategy", default="surface_mm")
    quote_review.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    quote_review.add_argument("--min-quotes", type=int, default=1)
    quote_review.add_argument("--min-instruments", type=int, default=1)
    quote_review.add_argument("--max-marketable-quotes", type=int, default=0)
    quote_review.add_argument("--min-quote-edge", type=float, default=0.0)
    quote_review.add_argument("--min-bid-share", type=float, default=0.25)
    quote_review.add_argument("--max-bid-share", type=float, default=0.75)
    quote_review.add_argument("--max-market-spread-ticks", type=float, default=None)
    quote_review.add_argument("--max-quotes-per-instrument", type=int, default=None)
    quote_review.add_argument("--data-readiness-comparison", default=None)
    quote_review.add_argument("--require-data-readiness-comparison", action="store_true")
    quote_review.add_argument("--fail-on-breach", action="store_true")

    quote_lifecycle = sub.add_parser(
        "plan-quote-lifecycle",
        help="Convert surface quote snapshots into OTR-aware submit/replace/cancel actions.",
    )
    quote_lifecycle.add_argument("--quotes", required=True)
    quote_lifecycle.add_argument("--out", required=True)
    quote_lifecycle.add_argument("--quote-risk-review", default=None)
    quote_lifecycle.add_argument("--require-quote-risk-review", action="store_true")
    quote_lifecycle.add_argument("--surface-quality-review", default=None)
    quote_lifecycle.add_argument("--require-surface-quality", action="store_true")
    quote_lifecycle.add_argument("--quote-ttl-ns", type=int, default=None)
    quote_lifecycle.add_argument("--max-order-messages", type=int, default=None)
    quote_lifecycle.add_argument("--max-active-quotes", type=int, default=None)
    quote_lifecycle.add_argument("--max-replaces", type=int, default=None)
    quote_lifecycle.add_argument("--max-cancels", type=int, default=None)
    quote_lifecycle.add_argument("--max-messages-per-snapshot", type=int, default=None)
    quote_lifecycle.add_argument("--expected-fills", type=int, default=None)
    quote_lifecycle.add_argument("--max-order-to-trade-ratio", type=float, default=None)
    quote_lifecycle.add_argument("--no-final-cancel", action="store_true")
    quote_lifecycle.add_argument("--fail-on-breach", action="store_true")

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
    surface_mm.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
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
    surface_mm.add_argument("--quote-risk-review", default=None)
    surface_mm.add_argument("--require-quote-risk-review", action="store_true")

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
    order_stage.add_argument("--quote-risk-review", default=None)
    order_stage.add_argument("--require-quote-risk-review", action="store_true")
    order_stage.add_argument("--surface-quality-review", default=None)
    order_stage.add_argument("--require-surface-quality", action="store_true")
    order_stage.add_argument("--fail-on-reject", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "scan-parity-box":
        result = run_scan(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            market=args.market,
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
            strategy=args.strategy,
            market=args.market,
            thresholds=LeadLagEdgeThresholds(
                min_events=args.min_events,
                min_abs_correlation=args.min_abs_correlation,
                min_correlation_samples=args.min_correlation_samples,
                min_update_rate=args.min_update_rate,
                max_median_update_ns=args.max_median_update_ns,
                min_best_latency_net_pnl=args.min_best_latency_net_pnl,
                min_best_latency_fills=args.min_best_latency_fills,
                min_profitable_latency_ns=args.min_profitable_latency_ns,
                min_best_latency_fill_rate=args.min_best_latency_fill_rate,
                min_best_latency_avg_net_edge=args.min_best_latency_avg_net_edge,
                max_best_latency_cost_drag_ratio=(
                    args.max_best_latency_cost_drag_ratio
                ),
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
            market=args.market,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            trigger_ticks=replay_params["trigger_ticks"],
            qty=args.qty,
            feed_latency_us=args.feed_latency_us,
            order_latency_us=replay_params["order_latency_us"],
            **_generic_cost_kwargs(args),
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "walkforward-leadlag-replay":
        result = write_leadlag_replay_walkforward(
            args.leaders,
            args.laggards,
            output_dir=args.out,
            labels=args.labels,
            candidate_config=args.candidate_config,
            timestamp_unit=args.timestamp_unit,
            timestamp_tz=args.timestamp_tz,
            filter_session=not args.no_filter_session,
            market=args.market,
            lot_size=args.lot_size,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            trigger_ticks=args.trigger_ticks,
            qty=args.qty,
            flat_after_ns=args.flat_after_ns,
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
            thresholds=LeadLagReplayWalkForwardThresholds(
                min_folds=args.min_folds if args.min_folds is not None else len(args.leaders),
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "promote-leadlag-candidate":
        result = write_leadlag_candidate_promotion(
            args.walkforward,
            output_dir=args.out,
            thresholds=LeadLagCandidatePromotionThresholds(
                require_walkforward_passed=not args.allow_unpassed_walkforward,
                require_candidate_ready=not args.allow_unready_candidate,
                require_edge_audit_bound=not args.allow_unbound_edge_audit,
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "plan-leadlag-orders":
        result = write_leadlag_order_plan(
            args.promotion,
            output_dir=args.out,
            config=LeadLagOrderPlanConfig(
                laggard_instrument_id=args.laggard_instrument_id,
                require_promotion_ready=not args.allow_unready_promotion,
                require_edge_audit_bound=not args.allow_unbound_edge_audit,
                qty=args.qty,
                reference_price=args.reference_price,
                buy_limit_price=args.buy_limit_price,
                sell_limit_price=args.sell_limit_price,
                entry_offset_ticks=args.entry_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                output_filename=args.output_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pipeline-leadlag-launch":
        result = write_leadlag_launch_pipeline(
            args.promotion,
            output_dir=args.out,
            config=LeadLagLaunchPipelineConfig(
                adapter=args.adapter,
                mode=args.mode,
                route_tag=args.route_tag,
                laggard_instrument_id=args.laggard_instrument_id,
                qty=args.qty,
                reference_price=args.reference_price,
                buy_limit_price=args.buy_limit_price,
                sell_limit_price=args.sell_limit_price,
                entry_offset_ticks=args.entry_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                product=args.product,
                exchange=args.exchange,
                require_reviewed_schema=not args.allow_placeholder_schema,
                broker_schema_audit_dir=args.broker_schema_audit,
                broker_mapping_draft_dir=args.broker_mapping_draft,
                broker_mapped_orders_dir=args.broker_mapped_orders,
                broker_halt_export_dir=args.broker_halt_export,
                broker_reconciliation_dir=args.broker_reconciliation,
                broker_runtime_session_dir=args.broker_runtime_session,
                broker_vendor_data_readiness_dir=args.broker_vendor_data_readiness,
                require_broker_schema_audit=args.require_broker_schema_audit,
                require_broker_mapping_draft=args.require_broker_mapping_draft,
                require_broker_mapped_orders=args.require_broker_mapped_orders,
                require_broker_halt_export=args.require_broker_halt_export,
                require_broker_reconciliation=args.require_broker_reconciliation,
                require_broker_runtime_session=args.require_broker_runtime_session,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
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
    if args.command == "plan-imbalance-orders":
        result = write_imbalance_order_plan(
            args.promotion,
            output_dir=args.out,
            config=ImbalanceOrderPlanConfig(
                instrument_id=args.instrument_id,
                require_promotion_ready=not args.allow_unready_promotion,
                qty=args.qty,
                reference_price=args.reference_price,
                buy_limit_price=args.buy_limit_price,
                sell_limit_price=args.sell_limit_price,
                entry_offset_ticks=args.entry_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                output_filename=args.output_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pipeline-imbalance-launch":
        result = write_imbalance_launch_pipeline(
            args.promotion,
            output_dir=args.out,
            config=ImbalanceLaunchPipelineConfig(
                adapter=args.adapter,
                mode=args.mode,
                route_tag=args.route_tag,
                instrument_id=args.instrument_id,
                qty=args.qty,
                reference_price=args.reference_price,
                buy_limit_price=args.buy_limit_price,
                sell_limit_price=args.sell_limit_price,
                entry_offset_ticks=args.entry_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                product=args.product,
                exchange=args.exchange,
                require_reviewed_schema=not args.allow_placeholder_schema,
                broker_schema_audit_dir=args.broker_schema_audit,
                broker_mapping_draft_dir=args.broker_mapping_draft,
                broker_mapped_orders_dir=args.broker_mapped_orders,
                broker_halt_export_dir=args.broker_halt_export,
                broker_reconciliation_dir=args.broker_reconciliation,
                broker_runtime_session_dir=args.broker_runtime_session,
                broker_vendor_data_readiness_dir=args.broker_vendor_data_readiness,
                require_broker_schema_audit=args.require_broker_schema_audit,
                require_broker_mapping_draft=args.require_broker_mapping_draft,
                require_broker_mapped_orders=args.require_broker_mapped_orders,
                require_broker_halt_export=args.require_broker_halt_export,
                require_broker_reconciliation=args.require_broker_reconciliation,
                require_broker_runtime_session=args.require_broker_runtime_session,
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
            data_readiness_comparison_dir=args.data_readiness_comparison,
            require_data_readiness_comparison=args.require_data_readiness_comparison,
            market_portability_dir=args.market_portability,
            require_market_portability=args.require_market_portability,
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
            data_readiness_comparison_dir=args.data_readiness_comparison,
            require_data_readiness_comparison=args.require_data_readiness_comparison,
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
                broker_schema_audit_dir=args.broker_schema_audit,
                broker_mapping_draft_dir=args.broker_mapping_draft,
                broker_mapped_orders_dir=args.broker_mapped_orders,
                broker_halt_export_dir=args.broker_halt_export,
                broker_reconciliation_dir=args.broker_reconciliation,
                broker_runtime_session_dir=args.broker_runtime_session,
                broker_vendor_data_readiness_dir=args.broker_vendor_data_readiness,
                require_broker_schema_audit=args.require_broker_schema_audit,
                require_broker_mapping_draft=args.require_broker_mapping_draft,
                require_broker_mapped_orders=args.require_broker_mapped_orders,
                require_broker_halt_export=args.require_broker_halt_export,
                require_broker_reconciliation=args.require_broker_reconciliation,
                require_broker_runtime_session=args.require_broker_runtime_session,
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
                expected_market=args.market,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "verify-proof-refresh-report":
        result = verify_proof_refresh_report(args.report)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "inputs_current": result.inputs_current,
                    "artifacts_consistent": (
                        result.artifacts_consistent
                    ),
                    "non_authorizing": result.non_authorizing,
                    "baseline_proof_verified": (
                        result.baseline_proof_verified
                    ),
                    "latest_proof_provided": (
                        result.latest_proof_provided
                    ),
                    "latest_proof_verified": (
                        result.latest_proof_verified
                    ),
                    "report": str(result.output_dir),
                    "manifest_path": str(result.manifest_path),
                    "manifest_artifact_count": (
                        result.manifest_artifact_count
                    ),
                    "manifest_artifact_match_count": (
                        result.manifest_artifact_match_count
                    ),
                    "manifest_input_fingerprint_count": (
                        result.manifest_input_fingerprint_count
                    ),
                    "manifest_input_fingerprint_match_count": (
                        result.manifest_input_fingerprint_match_count
                    ),
                    "error": result.error,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.verified else 0
    if args.command == "audit-adapter-schema":
        result = write_adapter_schema_audit(
            args.sample,
            output_dir=args.out,
            adapter=args.adapter,
            kind=args.kind,
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int(
                (action_queue["queue_status"].astype(str) == "blocked").sum()
            )
        if args.fail_on_missing and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
                market_calendar_path=args.market_calendar,
                require_all_mapped=not args.allow_missing_required,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "normalize-reviewed-mapped-data":
        result = write_reviewed_mapped_data_normalization(
            args.review,
            output_dir=args.out,
            config=ReviewedMappedDataConfig(
                output_filename=args.output_file,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                filter_session=not args.no_filter_session,
                market=args.market,
                market_calendar_path=args.market_calendar,
                require_all_mapped=not args.allow_missing_required,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                (result.action_queue["queue_status"].astype(str) == "blocked").sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "verify-reviewed-mapped-data":
        result = verify_reviewed_mapped_data_normalization(args.normalization)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "blocked": result.blocked,
                    "manifest_current": result.manifest_current,
                    "mapping_review_current": result.mapping_review_current,
                    "source_current": result.source_current,
                    "reviewed_mapping_current": result.reviewed_mapping_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "normalization_only": result.normalization_only,
                    "non_routing": result.non_routing,
                    "normalization_dir": str(result.output_dir),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach and not (result.verified and result.ready)
            else 0
        )
    if args.command == "normalize-applied-vendor-mapping":
        result = write_applied_mapped_data_normalization(
            args.application,
            output_dir=args.out,
            config=AppliedMappedDataConfig(
                output_filename=args.output_file,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                filter_session=not args.no_filter_session,
                market=args.market,
                market_calendar_path=args.market_calendar,
                require_all_mapped=not args.allow_missing_required,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                (result.action_queue["queue_status"].astype(str) == "blocked").sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "verify-applied-vendor-mapping-normalization":
        result = verify_applied_mapped_data_normalization(args.normalization)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "blocked": result.blocked,
                    "manifest_current": result.manifest_current,
                    "mapping_application_current": (
                        result.mapping_application_current
                    ),
                    "source_current": result.source_current,
                    "applied_mapping_current": result.applied_mapping_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "target_bound": result.target_bound,
                    "normalization_only": result.normalization_only,
                    "non_routing": result.non_routing,
                    "normalization_dir": str(result.output_dir),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach and not (result.verified and result.ready)
            else 0
        )
    if args.command == "plan-market-data-source":
        result = write_market_data_source_plan(
            args.out,
            config=MarketDataSourceConfig(
                provider=args.provider,
                adapter=args.adapter,
                kind=args.kind,
                transport=args.transport,
                source_uri=args.source_uri,
                market=args.market,
                exchange=args.exchange,
                session_timezone=args.session_timezone,
                session_open=args.session_open,
                session_close=args.session_close,
                auth_env_vars=tuple(args.auth_envs or ()),
                label=args.label,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-market-data-fetch":
        result = write_market_data_fetch_plan(
            args.source_plan,
            args.out,
            config=MarketDataFetchConfig(
                symbols=tuple(args.symbols or ()),
                window_start=args.window_start,
                window_end=args.window_end,
                poll_interval_ms=args.poll_interval_ms,
                max_latency_ms=args.max_latency_ms,
                expected_market=args.expected_market,
                output_filename=args.output_file,
                dry_run=True,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-provider-market-data-fetcher":
        result = write_provider_market_data_fetcher_plan(
            args.fetch_plan,
            args.out,
            config=ProviderMarketDataFetcherConfig(
                require_env_present=args.require_env_present,
                connect_timeout_ms=args.connect_timeout_ms,
                read_timeout_ms=args.read_timeout_ms,
                heartbeat_timeout_ms=args.heartbeat_timeout_ms,
                max_reconnects=args.max_reconnects,
                batch_size=args.batch_size,
                dry_run=True,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "prepare-provider-market-data-client":
        result = write_provider_market_data_client_plan(
            args.fetcher_plan,
            args.out,
            config=ProviderMarketDataClientConfig(
                require_env_present=args.require_env_present,
                session_label=args.session_label,
                max_clock_skew_ms=args.max_clock_skew_ms,
                max_local_buffer_rows=args.max_local_buffer_rows,
                dry_run=True,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-provider-market-data-live-session":
        result = write_provider_market_data_live_session_plan(
            args.client_packet,
            args.out,
            config=ProviderMarketDataLiveSessionConfig(
                trade_date=args.trade_date,
                windows=tuple(args.windows) if args.windows else ProviderMarketDataLiveSessionConfig(
                    trade_date=args.trade_date
                ).windows,
                capture_dir=args.capture_dir,
                batch_output_dir=args.batch_output_dir,
                min_capture_rows=args.min_capture_rows,
                pipeline_min_rows=args.pipeline_min_rows,
                tick_size=args.tick_size,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
                require_env_present=args.require_env_present,
                allow_weekend=args.allow_weekend,
                market_calendar_path=args.market_calendar or "",
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "preflight-provider-market-data-live-session":
        result = write_provider_market_data_live_session_preflight(
            args.live_session_packet,
            args.out,
            config=ProviderMarketDataLivePreflightConfig(
                require_env_present=args.require_env_present,
                now_iso=args.now_iso,
                allow_existing_captures=args.allow_existing_captures,
                allow_existing_batch=args.allow_existing_batch,
                require_before_last_window=not args.no_require_before_last_window,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "bundle-provider-market-data-live-capture":
        result = write_provider_market_data_live_capture_bundle(
            args.live_session_packet,
            args.out,
            config=ProviderMarketDataLiveCaptureBundleConfig(
                preflight_config_path=args.preflight_config,
                adapter_command_template=args.adapter_command_template,
                ingest_output_dir=args.ingest_output_dir,
                require_preflight_ready=not args.no_require_preflight_ready,
                require_env_present=args.require_env_present,
                allow_existing_captures=args.allow_existing_captures,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "rehearse-provider-market-data-live-capture":
        result = write_provider_market_data_live_rehearsal(
            args.capture_bundle,
            args.out,
            config=ProviderMarketDataLiveRehearsalConfig(
                rows_per_window=args.rows_per_window,
                base_price=args.base_price,
                tick_size=args.tick_size,
                overwrite_captures=args.overwrite_captures,
                run_ingest=not args.no_run_ingest,
                ingest_output_dir=args.ingest_output_dir,
                ingest_min_capture_rows=args.ingest_min_capture_rows,
                ingest_pipeline_min_rows=args.ingest_pipeline_min_rows,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "ingest-provider-market-data-live-session":
        result = write_provider_market_data_live_session_ingest(
            args.live_session_packet,
            args.out,
            config=ProviderMarketDataLiveIngestConfig(
                capture_bundle_path=args.capture_bundle,
                batch_output_dir=args.batch_output_dir,
                min_capture_rows=args.min_capture_rows,
                pipeline_min_rows=args.pipeline_min_rows,
                tick_size=args.tick_size,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-live-evidence":
        result = write_provider_market_data_live_evidence_review(
            args.live_ingest_dir,
            args.out,
            config=ProviderMarketDataLiveEvidenceConfig(
                allow_synthetic_rehearsal=args.allow_synthetic_rehearsal,
                require_ingest_ready=not args.no_require_ingest_ready,
                require_batch_ready=not args.no_require_batch_ready,
                require_manifest=not args.no_require_manifest,
                min_capture_rows=args.min_capture_rows,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "handoff-provider-market-data-research":
        result = write_provider_market_data_research_handoff(
            args.live_evidence_dir,
            args.out,
            config=ProviderMarketDataResearchHandoffConfig(
                strategies=(
                    tuple(args.strategies)
                    if args.strategies
                    else ProviderMarketDataResearchHandoffConfig().strategies
                ),
                require_research_ready=not args.no_require_research_ready,
                allow_synthetic_smoke=args.allow_synthetic_smoke,
                min_tick_folds=args.min_tick_folds,
                tick_size=args.tick_size,
                market=args.market,
                instrument_id=args.instrument_id,
                output_root=args.output_root,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "run-provider-market-data-imbalance-research":
        result = write_provider_market_data_imbalance_research(
            args.live_evidence_dir,
            args.out,
            config=ProviderMarketDataImbalanceResearchConfig(
                require_research_ready=not args.no_require_research_ready,
                allow_synthetic_smoke=args.allow_synthetic_smoke,
                min_tick_folds=args.min_tick_folds,
                tick_size=args.tick_size,
                market=args.market,
                instrument_id=args.instrument_id,
                instrument_kind=args.instrument_kind,
                lot_size=args.lot_size,
                qty=args.qty,
                entry_imbalance_values=tuple(args.entry_imbalance),
                min_microprice_edge_ticks_values=tuple(args.min_microprice_edge_ticks),
                forward_horizon_ns_values=tuple(args.forward_horizon_ns),
                max_spread_ticks=args.max_spread_ticks,
                min_depth=args.min_depth,
                min_signals=args.min_signals,
                min_direction_count=args.min_direction_count,
                min_mean_forward_edge_ticks=args.min_mean_forward_edge_ticks,
                min_win_rate=args.min_win_rate,
                min_median_forward_edge_ticks=args.min_median_forward_edge_ticks,
                filter_session=not args.no_filter_session,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                min_passed_configs=args.min_passed_configs,
                min_best_usable_signals=args.min_best_usable_signals,
                min_best_mean_forward_edge_ticks=args.min_best_mean_forward_edge_ticks,
                min_best_win_rate=args.min_best_win_rate,
                min_selection_sweeps=args.min_selection_sweeps,
                min_selection_pass_rate=args.min_selection_pass_rate,
                min_selection_median_usable_signals=args.min_selection_median_usable_signals,
                min_selection_median_mean_forward_edge_ticks=args.min_selection_median_mean_forward_edge_ticks,
                min_selection_min_win_rate=args.min_selection_min_win_rate,
                min_selection_median_robust_score=args.min_selection_median_robust_score,
                min_edge_folds=args.min_edge_folds,
                min_passed_edge_sweeps=args.min_passed_edge_sweeps,
                allow_unselected=args.allow_unselected,
                exit_imbalance=args.exit_imbalance,
                cooloff_ns=args.cooloff_ns,
                feed_latency_us=args.feed_latency_us,
                order_latency_us=args.order_latency_us,
                max_position_lots=args.max_position_lots,
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_markout_mean=args.min_markout_mean,
                min_replay_folds=args.min_replay_folds,
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_total_fills=args.min_total_fills,
                min_total_net_pnl=args.min_total_net_pnl,
                max_worst_drawdown=args.max_worst_drawdown,
                min_median_markout_mean=args.min_median_markout_mean,
                **_generic_cost_override_kwargs(args),
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-evidence":
        result = write_provider_market_data_imbalance_evidence_review(
            args.provider_research_dir,
            args.out,
            config=ProviderMarketDataImbalanceEvidenceConfig(
                require_provider_research_ready=not args.no_require_provider_research_ready,
                require_strategy_evidence_ready=not args.no_require_strategy_evidence_ready,
                allow_dirty_git=args.allow_dirty_git,
                require_same_git_commit=args.require_same_git_commit,
                require_same_strategy=not args.no_require_same_strategy,
                require_same_market=not args.no_require_same_market,
                expected_market=args.expected_market,
                min_passed_per_type=args.min_passed_per_type,
                require_file_inputs=args.require_file_inputs,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "pipeline-provider-market-data-imbalance-launch":
        result = write_provider_market_data_imbalance_launch_packet(
            args.provider_evidence_dir,
            args.out,
            config=ProviderMarketDataImbalanceLaunchConfig(
                require_provider_evidence_ready=not args.no_require_provider_evidence_ready,
                require_launch_ready=not args.no_require_launch_ready,
                adapter=args.adapter,
                mode=args.mode,
                route_tag=args.route_tag,
                instrument_id=args.instrument_id,
                qty=args.qty,
                reference_price=args.reference_price,
                buy_limit_price=args.buy_limit_price,
                sell_limit_price=args.sell_limit_price,
                entry_offset_ticks=args.entry_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                product=args.product,
                exchange=args.exchange,
                require_reviewed_schema=not args.allow_placeholder_schema,
                broker_schema_audit_dir=args.broker_schema_audit,
                broker_mapping_draft_dir=args.broker_mapping_draft,
                broker_mapped_orders_dir=args.broker_mapped_orders,
                broker_halt_export_dir=args.broker_halt_export,
                broker_reconciliation_dir=args.broker_reconciliation,
                broker_runtime_session_dir=args.broker_runtime_session,
                broker_vendor_data_readiness_dir=args.broker_vendor_data_readiness,
                require_broker_schema_audit=args.require_broker_schema_audit,
                require_broker_mapping_draft=args.require_broker_mapping_draft,
                require_broker_mapped_orders=args.require_broker_mapped_orders,
                require_broker_halt_export=args.require_broker_halt_export,
                require_broker_reconciliation=args.require_broker_reconciliation,
                require_broker_runtime_session=args.require_broker_runtime_session,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-launch-evidence":
        result = write_provider_market_data_imbalance_launch_evidence_review(
            args.provider_launch_dir,
            args.out,
            config=ProviderMarketDataImbalanceLaunchEvidenceConfig(
                require_provider_launch_ready=not args.no_require_provider_launch_ready,
                require_strategy_evidence_ready=not args.no_require_strategy_evidence_ready,
                allow_dirty_git=args.allow_dirty_git,
                require_same_git_commit=args.require_same_git_commit,
                require_same_strategy=not args.no_require_same_strategy,
                require_same_market=not args.no_require_same_market,
                expected_market=args.expected_market,
                min_passed_per_type=args.min_passed_per_type,
                require_file_inputs=args.require_file_inputs,
                require_no_placeholder_schema=args.require_no_placeholder_schema,
                require_no_blocked_placeholder_schema=args.require_no_blocked_placeholder_schema,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "score-provider-market-data-imbalance-readiness":
        result = write_provider_market_data_imbalance_scorecard(
            args.provider_launch_evidence_dir,
            args.out,
            config=ProviderMarketDataImbalanceScorecardConfig(
                require_launch_evidence_ready=not args.no_require_launch_evidence_ready,
                require_scorecard_ready=not args.no_require_scorecard_ready,
                allow_dirty_git=args.allow_dirty_git,
                expected_market=args.market,
                require_file_inputs=args.require_file_inputs,
                research_family_path=args.research_family or "",
                require_research_family=args.require_research_family,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-route-readiness":
        result = write_provider_market_data_imbalance_route_readiness(
            args.provider_launch_evidence_dir,
            args.out,
            market_portability_dir=args.market_portability,
            strategy_evidence_dir=args.strategy_evidence,
            ops_evidence_dirs=tuple(args.ops_evidence or ()),
            config=ProviderMarketDataImbalanceRouteReadinessConfig(
                require_provider_launch_evidence_ready=not args.no_require_provider_launch_evidence_ready,
                require_route_readiness_ready=not args.no_require_route_readiness_ready,
                use_provider_launch_evidence_inputs=not args.no_provider_launch_evidence_inputs,
                market=args.market,
                strategy=args.strategy,
                require_ops_file_inputs=not args.allow_non_file_ops_inputs,
                build_market_portability=not args.no_build_market_portability,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-provider-market-data-imbalance-scaleup":
        result = write_provider_market_data_imbalance_scaleup_plan(
            args.scorecard,
            args.shadow_comparison,
            args.out,
            order_exposure_dir=args.order_exposure,
            proof_refresh_dir=args.proof_refresh,
            instrument_metadata_dir=args.instrument_metadata,
            data_readiness_dir=args.data_readiness,
            data_readiness_comparison_dir=args.data_readiness_comparison,
            strategy_portfolio_dir=args.strategy_portfolio,
            route_readiness_dir=args.route_readiness,
            broker_readiness_dir=args.broker_readiness,
            config=ProviderMarketDataImbalanceScaleupConfig(
                require_scorecard_ready=not args.no_require_scorecard_ready,
                require_scaleup_ready=not args.no_require_scaleup_ready,
            ),
            thresholds=_scaleup_thresholds_from_args(args),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "build-provider-market-data-imbalance-runtime-telemetry":
        result = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
            args.scaleup,
            args.out,
            export_dir=args.export,
            upload_pack_dir=args.upload_pack,
            reconciliation_dir=args.reconciliation,
            instrument_metadata_dir=args.instrument_metadata,
            pnl_path=args.pnl,
            open_orders_path=args.open_orders,
            positions_path=args.positions,
            snapshot_ts_ns=args.snapshot_ts_ns,
            config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(
                require_provider_scaleup_ready=not args.no_require_provider_scaleup_ready,
                require_runtime_telemetry_ready=not args.no_require_runtime_telemetry_ready,
                use_launch_pipeline_broker_inputs=not args.no_use_launch_pipeline_broker_inputs,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "monitor-provider-market-data-imbalance-runtime-guard":
        result = write_provider_market_data_imbalance_runtime_guard(
            args.runtime_telemetry,
            args.out,
            as_of_ts_ns=args.as_of_ts_ns,
            max_telemetry_age_ns=args.max_telemetry_age_ns,
            config=ProviderMarketDataImbalanceRuntimeGuardConfig(
                require_provider_runtime_telemetry_ready=not args.no_require_provider_runtime_telemetry_ready,
                require_runtime_guard_continue=args.require_runtime_guard_continue,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_halt and result.halted:
            return 2
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "monitor-provider-market-data-imbalance-runtime-session":
        result = write_provider_market_data_imbalance_runtime_session(
            args.runtime_guard,
            args.out,
            export_dir=args.export,
            upload_pack_dir=args.upload_pack,
            reconciliation_dir=args.reconciliation,
            instrument_metadata_dir=args.instrument_metadata,
            pnl_path=args.pnl,
            open_orders_path=args.open_orders,
            positions_path=args.positions,
            snapshot_ts_ns=args.snapshot_ts_ns,
            as_of_ts_ns=args.as_of_ts_ns,
            max_telemetry_age_ns=args.max_telemetry_age_ns,
            plan_halt_response=not args.skip_halt_response,
            halt_response_config=HaltResponseConfig(
                require_guard_halt=True,
                require_flatten_prices=not args.allow_missing_flatten_prices,
                default_order_type=args.default_order_type,
                default_time_in_force=args.default_time_in_force,
            ),
            config=ProviderMarketDataImbalanceRuntimeSessionConfig(
                require_provider_runtime_guard_ready=not args.no_require_provider_runtime_guard_ready,
                require_runtime_session_continue=args.require_runtime_session_continue,
                require_halt_response_ready=not args.no_require_halt_response_ready,
                use_provider_runtime_telemetry_inputs=not args.no_use_provider_runtime_telemetry_inputs,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_halt and result.halted:
            return 2
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-broker-readiness":
        result = write_provider_market_data_imbalance_broker_readiness(
            args.runtime_session,
            args.out,
            schema_audit_dir=args.schema_audit,
            order_export_dir=args.order_export,
            mapping_draft_dir=args.mapping_draft,
            mapped_orders_dir=args.mapped_orders,
            upload_pack_dir=args.upload_pack,
            halt_export_dir=args.halt_export,
            reconciliation_dir=args.reconciliation,
            resume_dir=args.resume_gate,
            dispatch_roundtrip_dir=args.dispatch_roundtrip,
            vendor_market_data_batch_dir=args.vendor_market_data_batch,
            config=ProviderMarketDataImbalanceBrokerReadinessConfig(
                require_provider_runtime_session_ready=not args.no_require_provider_runtime_session_ready,
                require_broker_readiness_ready=not args.no_require_broker_readiness_ready,
                use_provider_runtime_session_inputs=not args.no_use_provider_runtime_session_inputs,
                adapter=args.adapter,
                expected_market=args.expected_market,
                expected_vendor_data_kind=args.expected_vendor_data_kind,
                require_reviewed_schema=args.require_reviewed_schema,
                require_schema_audit=args.require_schema_audit,
                require_order_export=not args.skip_order_export,
                require_mapping_draft=args.require_mapping_draft,
                require_mapped_orders=args.require_mapped_orders,
                require_upload_pack=not args.skip_upload_pack,
                require_halt_export=args.require_halt_export,
                require_reconciliation=args.require_reconciliation,
                require_runtime_session=not args.skip_runtime_session,
                require_resume_gate=args.require_resume_gate,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_adapter_match=not args.allow_adapter_mismatch,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-cutover":
        result = write_provider_market_data_imbalance_cutover(
            args.broker_readiness,
            args.out,
            scaleup_dir=args.scaleup,
            broker_readiness_dir=args.nested_broker_readiness,
            runtime_session_dir=args.runtime_session,
            operator_review_path=args.operator_review,
            config=ProviderMarketDataImbalanceCutoverConfig(
                require_provider_broker_readiness_ready=not args.allow_unready_provider_broker_readiness,
                require_cutover_ready=not args.allow_unready_cutover,
                use_provider_broker_readiness_inputs=not args.no_use_provider_broker_readiness_inputs,
                target_mode=args.target_mode,
                require_scaleup_ready=not args.allow_unready_scaleup,
                require_broker_readiness=not args.allow_missing_broker_readiness,
                require_runtime_session=not args.allow_missing_runtime_session,
                require_runtime_guard_continue=not args.allow_runtime_guard_halt,
                require_route_readiness=args.require_route_readiness or not args.allow_missing_route_readiness,
                require_resume_gate=args.require_resume_gate,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_operator_approval=args.require_operator_approval,
                require_operator_identity_ack=args.require_operator_identity_ack,
                require_operator_limits_ack=args.require_operator_limits_ack,
                max_failed_scaleup_checks=args.max_failed_scaleup_checks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-route-enable":
        result = write_provider_market_data_imbalance_route_enable(
            args.provider_cutover,
            args.out,
            cutover_dir=args.cutover,
            upload_pack_dir=args.upload_pack,
            order_export_dir=args.order_export,
            config=ProviderMarketDataImbalanceRouteEnableConfig(
                require_provider_cutover_ready=not args.allow_unready_provider_cutover,
                require_route_enable_ready=not args.allow_unready_route_enable,
                use_provider_cutover_inputs=not args.no_use_provider_cutover_inputs,
                target_mode=args.target_mode,
                require_cutover_ready=not args.allow_unready_cutover,
                require_upload_ready=not args.allow_unready_upload,
                require_order_export_ready=args.require_order_export,
                require_adapter_match=not args.allow_adapter_mismatch,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                min_orders=args.min_orders,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-provider-market-data-imbalance-broker-dispatch":
        result = write_provider_market_data_imbalance_broker_dispatch(
            args.provider_route_enable,
            args.out,
            route_enable_dir=args.route_enable,
            upload_pack_dir=args.upload_pack,
            upload_orders_path=args.upload_orders,
            config=ProviderMarketDataImbalanceBrokerDispatchConfig(
                require_provider_route_enable_ready=not args.allow_unready_provider_route_enable,
                require_broker_dispatch_ready=not args.allow_unready_broker_dispatch,
                use_provider_route_enable_inputs=not args.no_use_provider_route_enable_inputs,
                target_mode=args.target_mode,
                require_route_enabled=not args.allow_disabled_route,
                require_dry_run=not args.allow_non_dry_run,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                min_orders=args.min_orders,
                max_orders=args.max_orders,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "prepare-provider-market-data-imbalance-broker-dispatch-send":
        result = write_provider_market_data_imbalance_broker_dispatch_send(
            args.provider_broker_dispatch,
            args.out,
            broker_dispatch_dir=args.broker_dispatch,
            config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(
                require_provider_broker_dispatch_ready=not args.allow_unready_provider_broker_dispatch,
                require_broker_dispatch_send_ready=not args.allow_unready_broker_dispatch_send,
                use_provider_broker_dispatch_inputs=not args.no_use_provider_broker_dispatch_inputs,
                target_mode=args.target_mode,
                require_dispatch_ready=not args.allow_unready_dispatch,
                require_armed_dispatch=not args.allow_unarmed_dispatch,
                require_dry_run=not args.allow_non_dry_run,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                max_requests=args.max_requests,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "reconcile-provider-market-data-imbalance-broker-dispatch":
        lineage_migration_audit = _validated_provider_legacy_lineage_audit(
            strict_lineage=args.require_send_packet,
            audit_dir=args.lineage_migration_audit,
            source_path=args.provider_broker_dispatch_send,
            source_role="provider_send",
            legacy_flag="--allow-legacy-send-lineage",
        )
        result = write_provider_market_data_imbalance_broker_dispatch_ack(
            args.provider_broker_dispatch_send,
            args.acks,
            args.out,
            broker_dispatch_dir=args.broker_dispatch,
            config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(
                require_provider_broker_dispatch_send_ready=not args.allow_unready_provider_broker_dispatch_send,
                require_broker_dispatch_ack_passed=not args.allow_failed_broker_dispatch_ack,
                use_provider_broker_dispatch_send_inputs=not args.no_use_provider_broker_dispatch_send_inputs,
                require_dispatch_ready=not args.allow_unready_dispatch,
                require_all_acked=not args.allow_missing_acks,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_send_packet=args.require_send_packet,
                lineage_migration_audit_dir=lineage_migration_audit,
                allow_rejections=args.allow_rejections,
                max_duplicate_ack_orders=args.max_duplicate_ack_orders,
                max_unmatched_acks=args.max_unmatched_acks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-imbalance-broker-dispatch-roundtrip":
        lineage_migration_audit = _validated_provider_legacy_lineage_audit(
            strict_lineage=args.require_ack_lineage,
            audit_dir=args.lineage_migration_audit,
            source_path=args.provider_broker_dispatch_ack,
            source_role="provider_ack",
            legacy_flag="--allow-legacy-ack-lineage",
        )
        result = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
            args.provider_broker_dispatch_ack,
            args.out,
            broker_dispatch_dir=args.broker_dispatch,
            broker_dispatch_send_dir=args.broker_dispatch_send,
            broker_dispatch_ack_dir=args.broker_dispatch_ack,
            config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(
                require_provider_broker_dispatch_ack_passed=not args.allow_unready_provider_broker_dispatch_ack,
                require_broker_dispatch_roundtrip_passed=not args.allow_failed_broker_dispatch_roundtrip,
                use_provider_broker_dispatch_ack_inputs=not args.no_use_provider_broker_dispatch_ack_inputs,
                target_mode=args.target_mode,
                require_dispatch_ready=not args.allow_unready_dispatch,
                require_send_ready=not args.allow_unready_send,
                require_ack_passed=not args.allow_failed_ack,
                require_identity_match=not args.allow_identity_mismatch,
                require_submission_disabled=not args.allow_submission_enabled,
                require_all_requests_acked=not args.allow_missing_request_acks,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_ack_lineage=args.require_ack_lineage,
                lineage_migration_audit_dir=lineage_migration_audit,
                allow_rejections=args.allow_rejections,
                max_duplicate_ack_orders=args.max_duplicate_ack_orders,
                max_unmatched_acks=args.max_unmatched_acks,
                max_missing_request_acks=args.max_missing_request_acks,
                max_total_failed_component_checks=args.max_total_failed_component_checks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "certify-provider-market-data-imbalance-broker-rehearsal":
        lineage_migration_audit = _validated_provider_legacy_lineage_audit(
            strict_lineage=args.require_ack_lineage,
            audit_dir=args.lineage_migration_audit,
            source_path=args.provider_broker_dispatch_roundtrip,
            source_role="provider_roundtrip",
            legacy_flag="--allow-legacy-ack-lineage",
        )
        result = write_provider_market_data_imbalance_broker_rehearsal_certificate(
            args.provider_broker_dispatch_roundtrip,
            args.out,
            config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
                require_clean_recorded_git=not args.allow_recorded_dirty_git,
                require_sealed_provider_receipts=args.require_sealed_provider_receipts,
                require_ack_lineage=args.require_ack_lineage,
                lineage_migration_audit_dir=lineage_migration_audit,
                max_manifest_count=args.max_manifests,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "prepare-provider-market-data-imbalance-release-review":
        result = write_provider_market_data_imbalance_release_review(
            args.strategy_evidence,
            args.out,
            config=ProviderMarketDataImbalanceReleaseReviewConfig(
                max_dependency_count=args.max_dependencies,
            ),
        )
        print(result.summary.to_string(index=False))
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_actions and not result.action_queue.empty:
            return 2
        return 0
    if args.command == "verify-provider-market-data-imbalance-release-review":
        result = verify_provider_market_data_imbalance_release_review(
            args.release_review
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "source_current": result.source_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "operator_approval_pending": (
                        result.operator_approval_pending
                    ),
                    "release_review_dir": str(result.output_dir),
                    "strategy_evidence_dir": (
                        ""
                        if result.strategy_evidence_dir is None
                        else str(result.strategy_evidence_dir)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "finalize-provider-market-data-imbalance-release-decision"
    ):
        result = write_provider_market_data_imbalance_release_decision(
            args.release_review,
            args.operator_decision,
            args.out,
            config=ProviderMarketDataImbalanceReleaseDecisionConfig(
                max_dependency_count=args.max_dependencies,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-release-decision"
    ):
        result = verify_provider_market_data_imbalance_release_decision(
            args.release_decision
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "sealed": result.sealed,
                    "approved": result.approved,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "release_review_current": (
                        result.release_review_current
                    ),
                    "operator_decision_current": (
                        result.operator_decision_current
                    ),
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "release_decision_dir": str(result.output_dir),
                    "release_review_dir": (
                        ""
                        if result.release_review_dir is None
                        else str(result.release_review_dir)
                    ),
                    "operator_decision_path": (
                        ""
                        if result.operator_decision_path is None
                        else str(result.operator_decision_path)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "prepare-provider-market-data-imbalance-live-dryrun-handoff"
    ):
        result = write_provider_market_data_imbalance_live_dryrun_handoff(
            args.release_decision,
            args.runtime_controls,
            args.out,
            config=ProviderMarketDataImbalanceLiveDryrunHandoffConfig(
                max_dependency_count=args.max_dependencies,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-live-dryrun-handoff"
    ):
        result = verify_provider_market_data_imbalance_live_dryrun_handoff(
            args.handoff
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "release_decision_current": result.release_decision_current,
                    "runtime_controls_current": result.runtime_controls_current,
                    "rollback_runbook_current": result.rollback_runbook_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "handoff_dir": str(result.output_dir),
                    "release_decision_dir": (
                        ""
                        if result.release_decision_dir is None
                        else str(result.release_decision_dir)
                    ),
                    "runtime_controls_path": (
                        ""
                        if result.runtime_controls_path is None
                        else str(result.runtime_controls_path)
                    ),
                    "rollback_runbook_path": (
                        ""
                        if result.rollback_runbook_path is None
                        else str(result.rollback_runbook_path)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "preflight-provider-market-data-imbalance-live-dryrun-runtime"
    ):
        result = (
            write_provider_market_data_imbalance_live_dryrun_runtime_preflight(
                args.handoff,
                args.runtime_profile,
                args.out,
                config=(
                    ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig(
                        max_dependency_count=args.max_dependencies,
                        max_connectivity_latency_ms=(
                            args.max_connectivity_latency_ms
                        ),
                    )
                ),
                backend_entrypoint=args.backend,
            )
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-live-dryrun-runtime-preflight"
    ):
        result = (
            verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
                args.preflight
            )
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "handoff_current": result.handoff_current,
                    "runtime_profile_current": result.runtime_profile_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "credential_safe": result.credential_safe,
                    "non_authorizing": result.non_authorizing,
                    "preflight_dir": str(result.output_dir),
                    "handoff_dir": (
                        ""
                        if result.handoff_dir is None
                        else str(result.handoff_dir)
                    ),
                    "runtime_profile_path": (
                        ""
                        if result.runtime_profile_path is None
                        else str(result.runtime_profile_path)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.ready else 0
    if (
        args.command
        == "launch-provider-market-data-imbalance-live-dryrun-simulated-runtime"
    ):
        result = (
            write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
                args.preflight,
                args.out,
                config=(
                    ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
                        event_count=args.events,
                        interval_ms=args.interval_ms,
                        start_offset_seconds=args.start_offset_seconds,
                        symbol=args.symbol,
                        base_mid_price=args.base_mid_price,
                        spread=args.spread,
                        quantity=args.quantity,
                        price_step=args.price_step,
                        fault_mode=args.simulate_fault,
                        fault_at_event=args.fault_at_event,
                        max_dependency_count=args.max_dependencies,
                    )
                ),
            )
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_halt and not result.completed else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-live-dryrun-runtime-launcher"
    ):
        result = (
            verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
                args.launcher
            )
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "completed": result.completed,
                    "halted": result.halted,
                    "manifest_current": result.manifest_current,
                    "preflight_current": result.preflight_current,
                    "handoff_current": result.handoff_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "simulation_only": result.simulation_only,
                    "non_authorizing": result.non_authorizing,
                    "launcher_dir": str(result.output_dir),
                    "preflight_dir": (
                        ""
                        if result.preflight_dir is None
                        else str(result.preflight_dir)
                    ),
                    "handoff_dir": (
                        ""
                        if result.handoff_dir is None
                        else str(result.handoff_dir)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.completed)
            else 0
        )
    if (
        args.command
        == "evaluate-provider-market-data-imbalance-live-dryrun-shadow"
    ):
        result = (
            write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
                args.launcher,
                args.out,
                config=ProviderMarketDataImbalanceLiveDryrunShadowConfig(
                    lot_size=args.lot_size,
                    intent_quantity_lots=args.intent_quantity_lots,
                    tick_size=args.tick_size,
                    entry_imbalance=args.entry_imbalance,
                    exit_imbalance=args.exit_imbalance,
                    min_microprice_edge_ticks=(
                        args.min_microprice_edge_ticks
                    ),
                    max_spread_ticks=args.max_spread_ticks,
                    min_depth=args.min_depth,
                    hold_ns=args.hold_ns,
                    cooloff_ns=args.cooloff_ns,
                    terminal_flatten=True,
                    max_dependency_count=args.max_dependencies,
                ),
            )
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_halt and not result.completed else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-live-dryrun-shadow-evaluation"
    ):
        result = (
            verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
                args.shadow
            )
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "completed": result.completed,
                    "halted": result.halted,
                    "manifest_current": result.manifest_current,
                    "launcher_current": result.launcher_current,
                    "handoff_current": result.handoff_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "shadow_only": result.shadow_only,
                    "non_authorizing": result.non_authorizing,
                    "shadow_dir": str(result.output_dir),
                    "launcher_dir": (
                        ""
                        if result.launcher_dir is None
                        else str(result.launcher_dir)
                    ),
                    "handoff_dir": (
                        ""
                        if result.handoff_dir is None
                        else str(result.handoff_dir)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.completed)
            else 0
        )
    if (
        args.command
        == "calibrate-provider-market-data-imbalance-live-dryrun-shadow"
    ):
        result = (
            write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
                args.shadow,
                args.out,
                config=(
                    ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig(
                        horizons_ns=tuple(args.horizons_ns),
                        max_horizon_overshoot_ns=(
                            args.max_horizon_overshoot_ns
                        ),
                        min_covered_observations_per_horizon=(
                            args.min_covered_observations_per_horizon
                        ),
                        min_coverage_ratio=args.min_coverage_ratio,
                        max_dependency_count=args.max_dependencies,
                    )
                ),
            )
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_incomplete and not result.completed else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration"
    ):
        result = (
            verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
                args.calibration
            )
        )
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "completed": result.completed,
                    "insufficient": result.insufficient,
                    "manifest_current": result.manifest_current,
                    "shadow_current": result.shadow_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "calibration_only": result.calibration_only,
                    "non_authorizing": result.non_authorizing,
                    "calibration_dir": str(result.output_dir),
                    "shadow_dir": (
                        ""
                        if result.shadow_dir is None
                        else str(result.shadow_dir)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.completed)
            else 0
        )
    if (
        args.command
        == "compare-provider-market-data-imbalance-live-dryrun-shadow-calibrations"
    ):
        result = write_provider_shadow_calibration_stability(
            args.calibration,
            args.out,
            config=ProviderShadowCalibrationStabilityConfig(
                min_sessions=args.min_sessions,
                min_session_coverage_ratio=(
                    args.min_session_coverage_ratio
                ),
                max_horizon_coverage_range=(
                    args.max_horizon_coverage_range
                ),
                max_directional_mid_range_ticks=(
                    args.max_directional_mid_range_ticks
                ),
                require_directional_sign_consistency=(
                    not args.allow_directional_sign_change
                ),
                max_adverse_selection_rate_range=(
                    args.max_adverse_selection_rate_range
                ),
                max_cost_break_even_rate_range=(
                    args.max_cost_break_even_rate_range
                ),
                max_round_trip_cost_range_ticks=(
                    args.max_round_trip_cost_range_ticks
                ),
                max_dependency_count=args.max_dependencies,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_unstable and not result.stable else 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration-stability"
    ):
        result = verify_provider_shadow_calibration_stability(args.stability)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "stable": result.stable,
                    "unstable": result.unstable,
                    "manifest_current": result.manifest_current,
                    "calibrations_current": result.calibrations_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "stability_evidence_only": (
                        result.stability_evidence_only
                    ),
                    "non_authorizing": result.non_authorizing,
                    "stability_dir": str(result.output_dir),
                    "calibration_dirs": [
                        str(path) for path in result.calibration_dirs
                    ],
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.stable)
            else 0
        )
    if (
        args.command
        == "audit-provider-market-data-imbalance-broker-lineage-migration"
    ):
        result = write_provider_broker_lineage_migration_audit(
            args.roots,
            args.out,
            config=ProviderBrokerLineageMigrationConfig(
                recursive=not args.no_recursive,
                max_bundles=args.max_bundles,
                max_blocked_bundles=args.max_blocked_bundles,
                min_strict_ready_coverage=args.min_strict_ready_coverage,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                (
                    result.action_queue["queue_status"].astype(str)
                    == "blocked"
                ).sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if (
        args.command
        == "review-provider-market-data-imbalance-broker-lineage-audit-usage"
    ):
        result = write_provider_broker_lineage_audit_usage_review(
            args.roots,
            args.out,
            config=ProviderBrokerLineageAuditUsageConfig(
                recursive=not args.no_recursive,
                max_bundles=args.max_bundles,
                max_unaudited_legacy_bundles=(
                    args.max_unaudited_legacy_bundles
                ),
                max_drifted_audit_bundles=(
                    args.max_drifted_audit_bundles
                ),
                max_strict_with_audit_bundles=(
                    args.max_strict_with_audit_bundles
                ),
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                (
                    result.action_queue["queue_status"].astype(str)
                    == "blocked"
                ).sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if (
        args.command
        == "verify-provider-market-data-imbalance-broker-lineage-refresh"
    ):
        result = write_provider_broker_lineage_refresh_convergence(
            args.audit_usage,
            args.out,
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                result.action_queue["queue_status"]
                .astype(str)
                .eq("blocked")
                .sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if (
        args.command
        == "index-provider-market-data-imbalance-broker-active-lineage"
    ):
        result = write_provider_broker_active_lineage_index(
            args.convergence,
            args.out,
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                result.action_queue["queue_status"]
                .astype(str)
                .eq("blocked")
                .sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if (
        args.command
        == "audit-provider-market-data-imbalance-active-lineage-chain"
    ):
        result = write_provider_market_data_imbalance_active_lineage_chain_audit(
            args.certificate,
            args.out,
            config=ProviderMarketDataImbalanceActiveLineageChainConfig(
                max_manifest_count=args.max_manifests,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = 0
        if not result.action_queue.empty:
            blocked_actions = int(
                result.action_queue["queue_status"]
                .astype(str)
                .eq("blocked")
                .sum()
            )
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-provider-market-data-capture":
        result = write_provider_market_data_capture_review(
            args.client_packet,
            args.capture,
            args.out,
            config=ProviderMarketDataCaptureConfig(
                min_rows=args.min_rows,
                max_missing_required_columns=args.max_missing_required_columns,
                max_null_required_cells=args.max_null_required_cells,
                require_monotonic_ts=not args.no_require_monotonic_ts,
                expected_market=args.expected_market,
                expected_kind=args.expected_kind,
                pipeline_output_dir=args.pipeline_output_dir,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "pipeline-provider-market-data":
        result = write_provider_market_data_pipeline(
            args.client_packet,
            args.capture,
            output_dir=args.out,
            config=ProviderMarketDataPipelineConfig(
                min_capture_rows=args.min_capture_rows,
                max_missing_required_columns=args.max_missing_required_columns,
                max_null_required_cells=args.max_null_required_cells,
                require_monotonic_ts=not args.no_require_monotonic_ts,
                expected_market=args.expected_market,
                market_calendar_path=args.market_calendar,
                expected_kind=args.expected_kind,
                sample_rows=args.sample_rows,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                strike_step=args.strike_step,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                pipeline_min_rows=args.pipeline_min_rows,
                max_null_rows=args.max_null_rows,
                max_nonfinite_rows=args.max_nonfinite_rows,
                max_nonintegral_rows=args.max_nonintegral_rows,
                max_duplicate_tick_rows=args.max_duplicate_tick_rows,
                max_integer_overflow_rows=args.max_integer_overflow_rows,
                max_nonmonotonic_rows=args.max_nonmonotonic_rows,
                max_crossed_quote_rows=args.max_crossed_quote_rows,
                max_nonpositive_quote_rows=args.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=args.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=args.max_nonpositive_depth_rows,
                max_invalid_trade_rows=args.max_invalid_trade_rows,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_wide_spread_rows=args.max_wide_spread_rows,
                max_stale_bbo_rows=args.max_stale_bbo_rows,
                max_off_grid_strike_rows=args.max_off_grid_strike_rows,
                max_non_trading_day_rows=args.max_non_trading_day_rows,
                max_out_of_session_rows=args.max_out_of_session_rows,
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "pipeline-provider-market-data-batch":
        result = write_provider_market_data_batch_pipeline(
            args.client_packet,
            args.capture,
            output_dir=args.out,
            labels=args.labels,
            config=ProviderMarketDataBatchConfig(
                min_capture_rows=args.min_capture_rows,
                max_missing_required_columns=args.max_missing_required_columns,
                max_null_required_cells=args.max_null_required_cells,
                require_monotonic_ts=not args.no_require_monotonic_ts,
                expected_market=args.expected_market,
                market_calendar_path=args.market_calendar,
                expected_kind=args.expected_kind,
                sample_rows=args.sample_rows,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                strike_step=args.strike_step,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                pipeline_min_rows=args.pipeline_min_rows,
                max_null_rows=args.max_null_rows,
                max_nonfinite_rows=args.max_nonfinite_rows,
                max_nonintegral_rows=args.max_nonintegral_rows,
                max_duplicate_tick_rows=args.max_duplicate_tick_rows,
                max_integer_overflow_rows=args.max_integer_overflow_rows,
                max_nonmonotonic_rows=args.max_nonmonotonic_rows,
                max_crossed_quote_rows=args.max_crossed_quote_rows,
                max_nonpositive_quote_rows=args.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=args.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=args.max_nonpositive_depth_rows,
                max_invalid_trade_rows=args.max_invalid_trade_rows,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_wide_spread_rows=args.max_wide_spread_rows,
                max_stale_bbo_rows=args.max_stale_bbo_rows,
                max_off_grid_strike_rows=args.max_off_grid_strike_rows,
                max_non_trading_day_rows=args.max_non_trading_day_rows,
                max_out_of_session_rows=args.max_out_of_session_rows,
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
                min_datasets=args.min_datasets,
                min_ready_datasets=args.min_ready_datasets,
                min_ready_rate=args.min_ready_rate,
                max_total_failed_checks=args.max_total_failed_checks,
                min_unique_source_files=args.min_unique_source_files,
                min_source_file_fingerprint_coverage=args.min_source_file_fingerprint_coverage,
                min_mapping_coverage=args.min_mapping_coverage,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "pipeline-vendor-market-data":
        result = write_vendor_market_data_pipeline(
            args.input,
            output_dir=args.out,
            mapping_path=args.mapping,
            mapping_review_dir=args.mapping_review,
            mapping_application_dir=args.mapping_application,
            config=VendorMarketDataPipelineConfig(
                adapter=args.adapter,
                kind=args.kind,
                sample_rows=args.sample_rows,
                min_mapping_coverage=args.min_mapping_coverage,
                output_filename=args.output_file,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                filter_session=not args.no_filter_session,
                market=args.market,
                market_calendar_path=args.market_calendar,
                expiry_cycle=args.expiry_cycle,
                underlying=args.underlying,
                lot_size=args.lot_size,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                strike_step=args.strike_step,
                require_all_mapped=not args.allow_missing_required,
                min_rows=args.min_rows,
                max_null_rows=args.max_null_rows,
                max_nonfinite_rows=args.max_nonfinite_rows,
                max_nonintegral_rows=args.max_nonintegral_rows,
                max_duplicate_tick_rows=args.max_duplicate_tick_rows,
                max_integer_overflow_rows=args.max_integer_overflow_rows,
                max_nonmonotonic_rows=args.max_nonmonotonic_rows,
                min_chain_expiry_snapshots=args.min_chain_expiry_snapshots,
                min_chain_snapshots_per_expiry=(
                    args.min_chain_snapshots_per_expiry
                ),
                min_chain_snapshot_strikes=args.min_chain_snapshot_strikes,
                max_crossed_quote_rows=args.max_crossed_quote_rows,
                max_nonpositive_quote_rows=args.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=args.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=args.max_nonpositive_depth_rows,
                max_invalid_trade_rows=args.max_invalid_trade_rows,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_wide_spread_rows=args.max_wide_spread_rows,
                max_stale_bbo_rows=args.max_stale_bbo_rows,
                max_off_grid_strike_rows=args.max_off_grid_strike_rows,
                max_non_trading_day_rows=args.max_non_trading_day_rows,
                max_out_of_session_rows=args.max_out_of_session_rows,
                max_unparseable_contract_expiry_rows=(
                    args.max_unparseable_contract_expiry_rows
                ),
                max_expired_contract_rows=args.max_expired_contract_rows,
                max_duplicate_contract_key_rows=(
                    args.max_duplicate_contract_key_rows
                ),
                max_conflicting_contract_key_rows=(
                    args.max_conflicting_contract_key_rows
                ),
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
                max_chain_snapshot_p99_gap_ns=(
                    args.max_chain_snapshot_p99_gap_ns
                ),
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "pipeline-vendor-market-data-batch":
        input_count = len(args.input)
        result = write_vendor_market_data_batch_pipeline(
            args.input,
            output_dir=args.out,
            labels=args.labels,
            mapping_path=args.mapping,
            mapping_application_dirs=args.mapping_applications,
            config=VendorMarketDataPipelineConfig(
                adapter=args.adapter,
                kind=args.kind,
                sample_rows=args.sample_rows,
                min_mapping_coverage=args.min_mapping_coverage,
                output_filename=args.output_file,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                filter_session=not args.no_filter_session,
                market=args.market,
                market_calendar_path=args.market_calendar,
                expiry_cycle=args.expiry_cycle,
                underlying=args.underlying,
                lot_size=args.lot_size,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                strike_step=args.strike_step,
                require_all_mapped=not args.allow_missing_required,
                min_rows=args.min_rows,
                max_null_rows=args.max_null_rows,
                max_nonfinite_rows=args.max_nonfinite_rows,
                max_nonintegral_rows=args.max_nonintegral_rows,
                max_duplicate_tick_rows=args.max_duplicate_tick_rows,
                max_integer_overflow_rows=args.max_integer_overflow_rows,
                max_nonmonotonic_rows=args.max_nonmonotonic_rows,
                min_chain_expiry_snapshots=args.min_chain_expiry_snapshots,
                min_chain_snapshots_per_expiry=(
                    args.min_chain_snapshots_per_expiry
                ),
                min_chain_snapshot_strikes=args.min_chain_snapshot_strikes,
                max_crossed_quote_rows=args.max_crossed_quote_rows,
                max_nonpositive_quote_rows=args.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=args.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=args.max_nonpositive_depth_rows,
                max_invalid_trade_rows=args.max_invalid_trade_rows,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_wide_spread_rows=args.max_wide_spread_rows,
                max_stale_bbo_rows=args.max_stale_bbo_rows,
                max_off_grid_strike_rows=args.max_off_grid_strike_rows,
                max_non_trading_day_rows=args.max_non_trading_day_rows,
                max_out_of_session_rows=args.max_out_of_session_rows,
                max_unparseable_contract_expiry_rows=(
                    args.max_unparseable_contract_expiry_rows
                ),
                max_expired_contract_rows=args.max_expired_contract_rows,
                max_duplicate_contract_key_rows=(
                    args.max_duplicate_contract_key_rows
                ),
                max_conflicting_contract_key_rows=(
                    args.max_conflicting_contract_key_rows
                ),
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
                max_chain_snapshot_p99_gap_ns=(
                    args.max_chain_snapshot_p99_gap_ns
                ),
            ),
            comparison_thresholds=DataReadinessComparisonThresholds(
                min_datasets=args.min_datasets if args.min_datasets is not None else input_count,
                min_ready_datasets=args.min_ready_datasets
                if args.min_ready_datasets is not None
                else input_count,
                min_ready_rate=args.min_ready_rate,
                max_total_failed_checks=args.max_total_failed_checks,
                min_unique_source_files=args.min_unique_source_files
                if args.min_unique_source_files is not None
                else input_count,
                min_source_file_fingerprint_coverage=args.min_source_file_fingerprint_coverage
                if args.min_source_file_fingerprint_coverage is not None
                else 1.0,
                min_mapping_coverage=args.min_mapping_coverage,
                require_market_calendar=bool(args.market_calendar),
                require_consistent_market_calendar=bool(args.market_calendar),
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "pipeline-broker-vendor-readiness":
        input_count = len(args.input)
        result = write_broker_vendor_data_readiness_pipeline(
            args.input,
            output_dir=args.out,
            labels=args.labels,
            mapping_path=args.mapping,
            mapping_application_dirs=args.mapping_applications,
            schema_audit_dir=args.schema_audit,
            order_export_dir=args.order_export,
            mapping_draft_dir=args.mapping_draft,
            mapped_orders_dir=args.mapped_orders,
            upload_pack_dir=args.upload_pack,
            halt_export_dir=args.halt_export,
            reconciliation_dir=args.reconciliation,
            runtime_session_dir=args.runtime_session,
            resume_dir=args.resume_gate,
            dispatch_roundtrip_dir=args.dispatch_roundtrip,
            config=BrokerVendorDataReadinessConfig(
                adapter=args.adapter,
                kind=args.kind,
                sample_rows=args.sample_rows,
                min_mapping_coverage=args.min_mapping_coverage,
                output_filename=args.output_file,
                timestamp_unit=args.timestamp_unit,
                timestamp_tz=args.timestamp_tz,
                filter_session=not args.no_filter_session,
                market=args.market,
                market_calendar_path=args.market_calendar,
                expiry_cycle=args.expiry_cycle,
                underlying=args.underlying,
                lot_size=args.lot_size,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                strike_step=args.strike_step,
                require_all_mapped=not args.allow_missing_required,
                min_rows=args.min_rows,
                max_null_rows=args.max_null_rows,
                max_nonfinite_rows=args.max_nonfinite_rows,
                max_nonintegral_rows=args.max_nonintegral_rows,
                max_duplicate_tick_rows=args.max_duplicate_tick_rows,
                max_integer_overflow_rows=args.max_integer_overflow_rows,
                max_nonmonotonic_rows=args.max_nonmonotonic_rows,
                min_chain_expiry_snapshots=args.min_chain_expiry_snapshots,
                min_chain_snapshots_per_expiry=(
                    args.min_chain_snapshots_per_expiry
                ),
                min_chain_snapshot_strikes=args.min_chain_snapshot_strikes,
                max_crossed_quote_rows=args.max_crossed_quote_rows,
                max_nonpositive_quote_rows=args.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=args.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=args.max_nonpositive_depth_rows,
                max_invalid_trade_rows=args.max_invalid_trade_rows,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_wide_spread_rows=args.max_wide_spread_rows,
                max_stale_bbo_rows=args.max_stale_bbo_rows,
                max_off_grid_strike_rows=args.max_off_grid_strike_rows,
                max_non_trading_day_rows=args.max_non_trading_day_rows,
                max_out_of_session_rows=args.max_out_of_session_rows,
                max_unparseable_contract_expiry_rows=(
                    args.max_unparseable_contract_expiry_rows
                ),
                max_expired_contract_rows=args.max_expired_contract_rows,
                max_duplicate_contract_key_rows=(
                    args.max_duplicate_contract_key_rows
                ),
                max_conflicting_contract_key_rows=(
                    args.max_conflicting_contract_key_rows
                ),
                max_p99_gap_ns=args.max_p99_gap_ns,
                max_median_spread_ticks=args.max_median_spread_ticks,
                max_chain_snapshot_p99_gap_ns=(
                    args.max_chain_snapshot_p99_gap_ns
                ),
            ),
            comparison_thresholds=DataReadinessComparisonThresholds(
                min_datasets=args.min_datasets if args.min_datasets is not None else input_count,
                min_ready_datasets=args.min_ready_datasets
                if args.min_ready_datasets is not None
                else input_count,
                min_ready_rate=args.min_ready_rate,
                max_total_failed_checks=args.max_total_failed_checks,
                min_unique_source_files=args.min_unique_source_files
                if args.min_unique_source_files is not None
                else input_count,
                min_source_file_fingerprint_coverage=args.min_source_file_fingerprint_coverage
                if args.min_source_file_fingerprint_coverage is not None
                else 1.0,
                min_mapping_coverage=args.min_mapping_coverage,
                require_market_calendar=bool(args.market_calendar),
                require_consistent_market_calendar=bool(args.market_calendar),
            ),
            broker_thresholds=BrokerReadinessThresholds(
                adapter=args.adapter,
                expected_market=args.market,
                expected_vendor_data_kind=args.kind,
                require_reviewed_schema=not args.allow_placeholder_schema,
                require_schema_audit=not args.skip_schema_audit,
                require_order_export=not args.skip_order_export,
                require_mapping_draft=args.require_mapping_draft,
                require_mapped_orders=args.require_mapped_orders,
                require_upload_pack=not args.skip_upload_pack,
                require_halt_export=args.require_halt_export,
                require_reconciliation=args.require_reconciliation,
                require_runtime_session=args.require_runtime_session,
                require_resume_gate=args.require_resume_gate,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_adapter_match=not args.allow_adapter_mismatch,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "diagnose-ticks":
        ticks = load_tick_csv(
            args.ticks,
            filter_session=not args.no_filter_session,
            market=args.market,
            market_calendar=args.market_calendar,
        ).data
        result = write_diagnostics(
            tick_diagnostics(
                ticks,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                market=args.market,
                market_calendar=args.market_calendar,
            ),
            args.out,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "diagnose-chain":
        chain = load_option_chain_csv(
            args.chain,
            filter_session=not args.no_filter_session,
            market=args.market,
            market_calendar=args.market_calendar,
        ).data
        result = write_diagnostics(
            chain_diagnostics(
                chain,
                tick_size=args.tick_size,
                max_quote_spread_ticks=args.max_quote_spread_ticks,
                max_unchanged_bbo_ns=args.max_unchanged_bbo_ns,
                strike_step=args.strike_step,
                market=args.market,
                market_calendar=args.market_calendar,
                expiry_cycle=args.expiry_cycle,
                underlying=args.underlying,
                lot_size=args.lot_size,
            ),
            args.out,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "review-data-readiness":
        result = write_data_readiness_report(
            output_dir=args.out,
            market_calendar_dir=args.market_calendar_report,
            vendor_intake_dir=args.vendor_intake,
            schema_audit_dir=args.schema_audit,
            mapped_data_dir=args.mapped_data,
            tick_diagnostics_dir=args.tick_diagnostics,
            chain_diagnostics_dir=args.chain_diagnostics,
            market_profile_dir=args.market_profile,
            market_portability_dir=args.market_portability,
            instrument_metadata_dir=args.instrument_metadata,
            thresholds=DataReadinessThresholds(
                require_market_calendar=args.require_market_calendar,
                require_vendor_intake=args.require_vendor_intake,
                require_schema_audit=args.require_schema_audit,
                require_mapped_data=args.require_mapped_data,
                require_reviewed_mapping_normalization=(
                    args.require_reviewed_mapping_normalization
                ),
                require_target_application_normalization=(
                    args.require_target_application_normalization
                ),
                require_tick_diagnostics=not args.skip_tick_diagnostics,
                require_chain_diagnostics=args.require_chain_diagnostics,
                require_contract_expiry_validation=(
                    args.require_contract_expiry_validation
                ),
                require_contract_lot_validation=(
                    args.require_contract_lot_validation
                ),
                require_market_profile=args.require_market_profile,
                require_explicit_fee_model=args.require_explicit_fee_model,
                require_market_portability=args.require_market_portability,
                require_instrument_metadata=args.require_instrument_metadata,
                expected_strategy=args.expected_strategy,
                expected_market=args.expected_market,
                expected_adapter=args.expected_adapter,
                expected_vendor_data_kind=args.expected_vendor_data_kind,
                min_tick_rows=args.min_tick_rows,
                min_chain_rows=args.min_chain_rows,
                min_chain_expiries=args.min_chain_expiries,
                min_chain_strikes=args.min_chain_strikes,
                min_chain_expiry_snapshots=(
                    args.min_chain_expiry_snapshots
                ),
                min_chain_snapshots_per_expiry=(
                    args.min_chain_snapshots_per_expiry
                ),
                min_chain_snapshot_strikes=(
                    args.min_chain_snapshot_strikes
                ),
                max_null_rows=args.max_null_rows,
                max_nonfinite_rows=args.max_nonfinite_rows,
                max_nonintegral_rows=args.max_nonintegral_rows,
                max_duplicate_tick_rows=args.max_duplicate_tick_rows,
                max_integer_overflow_rows=args.max_integer_overflow_rows,
                max_nonmonotonic_rows=args.max_nonmonotonic_rows,
                max_crossed_quote_rows=args.max_crossed_quote_rows,
                max_nonpositive_quote_rows=args.max_nonpositive_quote_rows,
                max_nonpositive_strike_rows=args.max_nonpositive_strike_rows,
                max_nonpositive_depth_rows=args.max_nonpositive_depth_rows,
                max_invalid_trade_rows=args.max_invalid_trade_rows,
                max_off_tick_price_rows=args.max_off_tick_price_rows,
                max_wide_spread_rows=args.max_wide_spread_rows,
                max_stale_bbo_rows=args.max_stale_bbo_rows,
                max_off_grid_strike_rows=args.max_off_grid_strike_rows,
                max_non_trading_day_rows=args.max_non_trading_day_rows,
                max_out_of_session_rows=args.max_out_of_session_rows,
                max_unparseable_contract_expiry_rows=(
                    args.max_unparseable_contract_expiry_rows
                ),
                max_expired_contract_rows=args.max_expired_contract_rows,
                max_duplicate_contract_key_rows=(
                    args.max_duplicate_contract_key_rows
                ),
                max_conflicting_contract_key_rows=(
                    args.max_conflicting_contract_key_rows
                ),
                max_invalid_contract_expiry_rows=(
                    args.max_invalid_contract_expiry_rows
                ),
                max_uncovered_contract_expiry_rows=(
                    args.max_uncovered_contract_expiry_rows
                ),
                max_invalid_contract_lot_rows=(
                    args.max_invalid_contract_lot_rows
                ),
                max_uncovered_contract_lot_rows=(
                    args.max_uncovered_contract_lot_rows
                ),
                max_tick_p99_gap_ns=args.max_tick_p99_gap_ns,
                max_tick_median_spread_ticks=args.max_tick_median_spread_ticks,
                max_chain_median_spread_ticks=args.max_chain_median_spread_ticks,
                max_chain_snapshot_p99_gap_ns=(
                    args.max_chain_snapshot_p99_gap_ns
                ),
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "verify-data-readiness-report":
        result = verify_data_readiness_report(args.report)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "inputs_current": result.inputs_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "report_dir": str(result.output_dir),
                    "manifest_path": str(result.manifest_path),
                    "manifest_artifact_count": (
                        result.manifest_artifact_count
                    ),
                    "manifest_artifact_match_count": (
                        result.manifest_artifact_match_count
                    ),
                    "manifest_input_fingerprint_count": (
                        result.manifest_input_fingerprint_count
                    ),
                    "manifest_input_fingerprint_match_count": (
                        result.manifest_input_fingerprint_match_count
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.verified else 0
    if args.command == "compare-data-readiness":
        result = write_data_readiness_comparison(
            args.readiness,
            output_dir=args.out,
            labels=args.labels,
            thresholds=DataReadinessComparisonThresholds(
                min_datasets=args.min_datasets,
                min_ready_datasets=args.min_ready_datasets,
                min_ready_rate=args.min_ready_rate,
                max_total_failed_checks=args.max_total_failed_checks,
                min_unique_source_files=args.min_unique_source_files,
                min_source_file_fingerprint_coverage=args.min_source_file_fingerprint_coverage,
                min_mapping_coverage=args.min_mapping_coverage,
                require_market_calendar=args.require_market_calendar,
                require_consistent_market_calendar=(
                    args.require_consistent_market_calendar
                ),
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.accepted:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "verify-data-readiness-comparison":
        result = verify_data_readiness_comparison(args.report)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "accepted": result.accepted,
                    "manifest_current": result.manifest_current,
                    "inputs_current": result.inputs_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "report_dir": str(result.output_dir),
                    "manifest_path": str(result.manifest_path),
                    "manifest_artifact_count": (
                        result.manifest_artifact_count
                    ),
                    "manifest_artifact_match_count": (
                        result.manifest_artifact_match_count
                    ),
                    "manifest_input_fingerprint_count": (
                        result.manifest_input_fingerprint_count
                    ),
                    "manifest_input_fingerprint_match_count": (
                        result.manifest_input_fingerprint_match_count
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.verified else 0
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
    if args.command == "market-calendar-report":
        result = write_market_calendar_report(
            args.calendar,
            args.out,
            expected_market=args.market,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "verify-market-calendar-report":
        result = verify_market_calendar_report(args.report)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "source_current": result.source_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "compiled_from_sessions": result.compiled_from_sessions,
                    "report_dir": str(result.output_dir),
                    "manifest_path": str(result.manifest_path),
                    "source_path": (
                        ""
                        if result.source_path is None
                        else str(result.source_path)
                    ),
                    "authority_source_path": (
                        ""
                        if result.authority_source_path is None
                        else str(result.authority_source_path)
                    ),
                    "authority_source_current": (
                        result.authority_source_current
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.ready)
            else 0
        )
    if args.command == "build-market-calendar":
        result = write_market_calendar_from_sessions(
            args.sessions,
            args.out,
            calendar_id=args.calendar_id,
            market=args.market,
            valid_from=args.valid_from,
            valid_to=args.valid_to,
            publisher=args.publisher,
            source_url=args.source_url,
            published_date=args.published_date,
            authority_source_path=args.authority_source,
            authority_source_schema=args.authority_source_schema,
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
        return _market_portability_exit_code(
            result,
            fail_on_breach=args.fail_on_breach,
            fail_on_gaps=args.fail_on_gaps,
            fail_on_actions=args.fail_on_actions,
            fail_on_blocked_actions=args.fail_on_blocked_actions,
        )
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
    if args.command == "verify-proof-report":
        result = verify_proof_report(args.report)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "passed": result.passed,
                    "manifest_current": result.manifest_current,
                    "inputs_current": result.inputs_current,
                    "replay_manifests_current": (
                        result.replay_manifests_current
                    ),
                    "artifacts_consistent": result.artifacts_consistent,
                    "non_authorizing": result.non_authorizing,
                    "report": str(result.output_dir),
                    "manifest_path": str(result.manifest_path),
                    "manifest_artifact_count": (
                        result.manifest_artifact_count
                    ),
                    "manifest_artifact_match_count": (
                        result.manifest_artifact_match_count
                    ),
                    "manifest_input_fingerprint_count": (
                        result.manifest_input_fingerprint_count
                    ),
                    "manifest_input_fingerprint_match_count": (
                        result.manifest_input_fingerprint_match_count
                    ),
                    "replay_manifest_count": result.replay_manifest_count,
                    "replay_manifest_current_count": (
                        result.replay_manifest_current_count
                    ),
                    "error": result.error,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.verified else 0
    if args.command == "catalog-runs":
        result = write_experiment_catalog(
            args.roots,
            output_dir=args.out,
            provider_broker_active_lineage_index=(
                args.provider_broker_active_lineage_index
            ),
            provider_active_lineage_chain_audits=(
                args.provider_active_lineage_chain_audits
            ),
        )
        print(result.summary.to_string(index=False))
        return _catalog_exit_code(
            result,
            fail_on_actions=args.fail_on_actions,
            fail_on_blocked_actions=args.fail_on_blocked_actions,
            fail_on_catalog_gaps=args.fail_on_catalog_gaps,
            fail_on_placeholder_schema=args.fail_on_placeholder_schema,
            fail_on_blocked_placeholder_schema=args.fail_on_blocked_placeholder_schema,
            fail_on_broker_roundtrip_portfolio_breach=args.fail_on_broker_roundtrip_portfolio_breach,
            require_broker_roundtrip_portfolio_safe=args.require_broker_roundtrip_portfolio_safe,
            fail_on_broker_roundtrip_portfolio_concentration_breach=(
                args.fail_on_broker_roundtrip_portfolio_concentration_breach
            ),
            require_broker_roundtrip_portfolio_concentration_ok=(
                args.require_broker_roundtrip_portfolio_concentration_ok
            ),
            fail_on_broker_roundtrip_resume_route_breach=args.fail_on_broker_roundtrip_resume_route_breach,
            require_broker_roundtrip_resume_route_ready=args.require_broker_roundtrip_resume_route_ready,
            fail_on_provider_broker_roundtrip_synthetic_sidecar_breach=(
                args.fail_on_provider_broker_roundtrip_synthetic_sidecar_breach
            ),
            require_provider_broker_roundtrip_synthetic_sidecar_ready=(
                args.require_provider_broker_roundtrip_synthetic_sidecar_ready
            ),
            fail_on_provider_lineage_selection_blocks=(
                args.fail_on_provider_lineage_selection_blocks
            ),
        )
    if args.command == "review-strategy-evidence":
        required_run_types = (
            tuple(args.required_run_types) if args.required_run_types else evidence_profile_run_types(args.profile)
        )
        is_ops_launch_profile = tuple(required_run_types) in {
            evidence_profile_run_types("ops_launch"),
            evidence_profile_run_types("provider_imbalance_ops_launch"),
        }
        is_provider_imbalance_ops_launch_profile = (
            tuple(required_run_types) == evidence_profile_run_types("provider_imbalance_ops_launch")
        )
        result = write_strategy_evidence_review(
            args.catalog,
            output_dir=args.out,
            thresholds=EvidenceThresholds(
                required_run_types=required_run_types,
                min_passed_per_type=args.min_passed_per_type,
                allow_dirty_git=args.allow_dirty_git,
                require_same_git_commit=args.require_same_git_commit,
                require_same_strategy=args.require_same_strategy,
                require_same_market=args.require_same_market,
                expected_strategy=args.expected_strategy,
                expected_market=args.expected_market,
                require_file_inputs=args.require_file_inputs
                or (is_ops_launch_profile and not args.allow_non_file_inputs),
                require_no_placeholder_schema=args.fail_on_placeholder_schema,
                require_no_blocked_placeholder_schema=args.fail_on_blocked_placeholder_schema
                or is_ops_launch_profile,
                require_broker_roundtrip_portfolio_safe=args.require_broker_roundtrip_portfolio_safe
                or is_ops_launch_profile,
                fail_on_broker_roundtrip_portfolio_breach=args.fail_on_broker_roundtrip_portfolio_breach
                or is_ops_launch_profile,
                require_broker_roundtrip_portfolio_concentration_ok=(
                    args.require_broker_roundtrip_portfolio_concentration_ok or is_ops_launch_profile
                ),
                fail_on_broker_roundtrip_portfolio_concentration_breach=(
                    args.fail_on_broker_roundtrip_portfolio_concentration_breach or is_ops_launch_profile
                ),
                require_broker_roundtrip_resume_route_ready=(
                    args.require_broker_roundtrip_resume_route_ready or is_ops_launch_profile
                ),
                fail_on_broker_roundtrip_resume_route_breach=(
                    args.fail_on_broker_roundtrip_resume_route_breach or is_ops_launch_profile
                ),
                require_provider_broker_roundtrip_synthetic_sidecar_ready=(
                    args.require_provider_broker_roundtrip_synthetic_sidecar_ready
                    or is_provider_imbalance_ops_launch_profile
                ),
                fail_on_provider_broker_roundtrip_synthetic_sidecar_breach=(
                    args.fail_on_provider_broker_roundtrip_synthetic_sidecar_breach
                    or is_provider_imbalance_ops_launch_profile
                ),
                require_provider_lineage_selection=(
                    args.require_provider_lineage_selection
                ),
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "verify-strategy-evidence":
        result = verify_strategy_evidence_review(args.evidence)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "source_current": result.source_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "manifest_input_contract_current": (
                        result.manifest_input_contract_current
                    ),
                    "provider_retained_proofs_current": (
                        result.provider_retained_proofs_current
                    ),
                    "non_authorizing": result.non_authorizing,
                    "evidence_dir": str(result.output_dir),
                    "catalog_path": (
                        "" if result.catalog_path is None else str(result.catalog_path)
                    ),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "score-strategy-readiness":
        result = write_strategy_scorecard(
            args.catalog,
            output_dir=args.out,
            research_family_path=args.research_family,
            thresholds=StrategyScorecardThresholds(
                profiles=tuple(args.profiles) if args.profiles else StrategyScorecardThresholds().profiles,
                expected_market=args.market,
                expected_ops_strategy=args.ops_strategy,
                allow_dirty_git=args.allow_dirty_git,
                require_file_inputs=args.require_file_inputs,
                require_research_family=args.require_research_family,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "allocate-strategy-portfolio":
        result = write_strategy_portfolio_allocations(
            args.scorecard,
            output_dir=args.out,
            config=StrategyPortfolioConfig(
                total_capital=args.total_capital,
                capital_currency=args.capital_currency,
                reserve_weight=args.reserve_weight,
                max_profile_weight=args.max_profile_weight,
                min_readiness_score=args.min_readiness_score,
                require_ready=not args.allow_unready,
                include_profiles=tuple(args.include_profiles or ()),
                exclude_profiles=tuple(args.exclude_profiles or ()),
                min_strategy_count=args.min_strategy_count,
                min_market_count=args.min_market_count,
                max_strategy_weight=args.max_strategy_weight,
                max_market_weight=args.max_market_weight,
                require_scorecard_manifest=args.require_scorecard_manifest,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-route-readiness":
        result = write_route_readiness_review(
            args.out,
            market_portability=args.portability,
            strategy_evidence=tuple(args.strategy_evidence or ()),
            ops_evidence=tuple(args.ops_evidence or ()),
            require_ops_file_inputs=not args.allow_non_file_ops_inputs,
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "sweep-leadlag":
        result = run_leadlag_sweep(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            trigger_ticks_values=args.trigger_ticks,
            feed_latency_us_values=args.feed_latency_us,
            order_latency_us_values=args.order_latency_us,
            filter_session=not args.no_filter_session,
            market=args.market,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            qty=args.qty,
            flat_after_ns=args.flat_after_ns,
            cooloff_ns=args.cooloff_ns,
            **_generic_cost_kwargs(args),
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
    if args.command == "promote-parity-candidate":
        result = write_parity_candidate_promotion(
            args.scan,
            edge_audit_dir=args.edge_audit,
            sweep_dir=args.sweep,
            output_dir=args.out,
            market=args.market,
            thresholds=ParityCandidatePromotionThresholds(
                require_edge_passed=not args.allow_unpassed_edge,
                require_sweep_passed_scenario=not args.allow_empty_sweep_pass,
                min_total_opportunities=args.min_total_opportunities,
                min_best_net_edge=args.min_best_net_edge,
                min_candidate_net_edge=args.min_candidate_net_edge,
                min_candidate_persistence_ticks=args.min_candidate_persistence_ticks,
                min_sweep_pass_rate=args.min_sweep_pass_rate,
                min_passed_scenarios=args.min_passed_scenarios,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "plan-parity-orders":
        result = write_parity_order_plan(
            args.promotion,
            output_dir=args.out,
            config=ParityOrderPlanConfig(
                symbol_prefix=args.symbol_prefix,
                future_instrument_id=args.future_instrument_id,
                require_promotion_ready=not args.allow_unready_promotion,
                direction=args.direction,
                expiry=args.expiry,
                strike=args.strike,
                low_strike=args.low_strike,
                high_strike=args.high_strike,
                qty=args.qty,
                call_price=args.call_price,
                put_price=args.put_price,
                future_price=args.future_price,
                low_call_price=args.low_call_price,
                low_put_price=args.low_put_price,
                high_call_price=args.high_call_price,
                high_put_price=args.high_put_price,
                price_offset_ticks=args.price_offset_ticks,
                tick_size=args.tick_size,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                output_filename=args.output_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pipeline-parity-launch":
        result = write_parity_launch_pipeline(
            args.promotion,
            output_dir=args.out,
            config=ParityLaunchPipelineConfig(
                adapter=args.adapter,
                mode=args.mode,
                route_tag=args.route_tag,
                symbol_prefix=args.symbol_prefix,
                future_instrument_id=args.future_instrument_id,
                direction=args.direction,
                expiry=args.expiry,
                strike=args.strike,
                low_strike=args.low_strike,
                high_strike=args.high_strike,
                qty=args.qty,
                call_price=args.call_price,
                put_price=args.put_price,
                future_price=args.future_price,
                low_call_price=args.low_call_price,
                low_put_price=args.low_put_price,
                high_call_price=args.high_call_price,
                high_put_price=args.high_put_price,
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
                broker_schema_audit_dir=args.broker_schema_audit,
                broker_mapping_draft_dir=args.broker_mapping_draft,
                broker_mapped_orders_dir=args.broker_mapped_orders,
                broker_halt_export_dir=args.broker_halt_export,
                broker_reconciliation_dir=args.broker_reconciliation,
                broker_runtime_session_dir=args.broker_runtime_session,
                broker_vendor_data_readiness_dir=args.broker_vendor_data_readiness,
                require_broker_schema_audit=args.require_broker_schema_audit,
                require_broker_mapping_draft=args.require_broker_mapping_draft,
                require_broker_mapped_orders=args.require_broker_mapped_orders,
                require_broker_halt_export=args.require_broker_halt_export,
                require_broker_reconciliation=args.require_broker_reconciliation,
                require_broker_runtime_session=args.require_broker_runtime_session,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
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
            market=args.market,
            lot_size=args.lot_size,
            option_tick=args.option_tick,
            contract_multiplier=args.contract_multiplier,
            max_quotes=args.max_quotes,
            quote_risk_review_dir=args.quote_risk_review,
            require_quote_risk_review=args.require_quote_risk_review,
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
        return 2 if (args.fail_on_breach or args.require_quote_risk_review) and not result.proof.passed else 0
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
    if args.command == "pipeline-robust-selection":
        result = write_robust_selection_pipeline(
            args.sweeps,
            output_dir=args.out,
            labels=args.labels,
            group_cols=args.group_cols,
            strategy=args.strategy,
            market=args.market,
            research_registration_path=args.research_registration,
            registered_study_label=args.registered_study_label,
            require_research_registration=args.require_research_registration,
            walkforward_split_audit_path=args.walkforward_split_audit,
            require_walkforward_split_audit=(
                args.require_walkforward_split_audit
            ),
            research_launch_matrix_path=args.research_launch_matrix,
            research_launch_contract_id=args.research_launch_contract_id,
            require_research_launch_contract=(
                args.require_research_launch_contract
            ),
            research_launch_execution_receipt_path=(
                args.research_launch_execution_receipt
            ),
            require_research_launch_execution_receipt=(
                args.require_research_launch_execution_receipt
            ),
            selection_min_pass_rate=args.min_selection_pass_rate,
            selection_min_sweeps=args.min_selection_sweeps,
            selection_min_median_net_pnl=args.min_selection_median_net_pnl,
            selection_max_worst_drawdown=args.max_selection_worst_drawdown,
            overfit_config=BacktestOverfitConfig(
                score_column=args.score_column,
                max_partitions=args.max_partitions,
                require_selection_manifest=True,
            ),
            overfit_thresholds=BacktestOverfitThresholds(
                min_partitions=args.min_partitions,
                min_scenarios=args.min_scenarios,
                max_probability_overfit=args.max_probability_overfit,
                min_median_oos_score=args.min_median_oos_score,
                min_oos_positive_rate=args.min_oos_positive_rate,
                min_median_rank_correlation=args.min_median_rank_correlation,
                max_median_degradation=args.max_median_degradation,
                min_candidate_selection_rate=args.min_candidate_selection_rate,
                max_candidate_overfit_rate=args.max_candidate_overfit_rate,
                min_candidate_oos_positive_rate=args.min_candidate_oos_positive_rate,
            ),
            significance_config=BacktestSignificanceConfig(
                bootstrap_samples=args.significance_bootstrap_samples,
                confidence_level=args.significance_confidence_level,
                random_seed=args.significance_random_seed,
                zero_tolerance=args.significance_zero_tolerance,
                require_overfit_manifest=True,
            ),
            significance_thresholds=BacktestSignificanceThresholds(
                min_observations=args.min_significance_observations,
                min_nonzero_observations=(
                    args.min_significance_nonzero_observations
                ),
                min_positive_rate=args.min_significance_positive_rate,
                max_adjusted_sign_pvalue=(
                    args.max_significance_adjusted_sign_pvalue
                ),
                min_bootstrap_probability_positive=(
                    args.min_significance_bootstrap_probability_positive
                ),
                min_bootstrap_mean_lower=(
                    args.min_significance_bootstrap_mean_lower
                ),
                require_overfit_passed=True,
            ),
            holdout_sweeps=args.holdout_sweeps,
            holdout_thresholds=BacktestHoldoutThresholds(
                min_sweeps=args.holdout_sweeps,
                min_candidate_coverage_rate=args.min_holdout_coverage_rate,
                min_proof_pass_rate=args.min_holdout_proof_pass_rate,
                min_mean_score=args.min_holdout_mean_score,
                min_median_score=args.min_holdout_median_score,
                min_worst_score=args.min_holdout_worst_score,
                min_mean_net_pnl=args.min_holdout_mean_net_pnl,
                min_worst_net_pnl=args.min_holdout_worst_net_pnl,
                min_fills_per_sweep=args.min_holdout_fills_per_sweep,
                max_worst_drawdown=args.max_holdout_worst_drawdown,
                require_selection_passed=True,
            ),
            promotion_thresholds=PromotionThresholds(
                min_pass_rate=args.min_promotion_pass_rate,
                min_sweeps=args.min_promotion_sweeps,
                min_median_net_pnl=args.min_promotion_median_net_pnl,
                min_min_net_pnl=args.min_promotion_min_net_pnl,
                max_worst_drawdown=args.max_promotion_worst_drawdown,
                min_median_fills=args.min_promotion_median_fills,
                max_runs_with_losing_regimes=(
                    args.max_promotion_runs_with_losing_regimes
                ),
                max_otr=args.max_promotion_otr,
                min_maker_share=args.min_promotion_maker_share,
                min_markout_mean=args.min_promotion_markout_mean,
                require_overfit_audit=True,
                require_significance_audit=True,
                require_holdout_audit=True,
            ),
        )
        print(result.summary.to_string(index=False))
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_actions and not result.action_queue.empty:
            return 2
        return 0
    if args.command == "audit-walkforward-splits":
        result = write_walk_forward_split_audit(
            args.labels,
            output_dir=args.out,
            config=WalkForwardSplitAuditConfig(
                time_col=args.time_col,
                label_end_col=args.label_end_col,
                n_splits=args.n_splits,
                embargo_ns=args.embargo_ns,
                test_size=args.test_size,
            ),
            thresholds=WalkForwardSplitAuditThresholds(
                min_train_rows=args.min_train_rows,
                min_test_rows=args.min_test_rows,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and action_count > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "audit-backtest-overfit":
        result = write_backtest_overfit_audit(
            args.selection,
            output_dir=args.out,
            config=BacktestOverfitConfig(
                split_column=args.split_column,
                score_column=args.score_column,
                scenario_columns=tuple(args.scenario_columns or ()),
                max_partitions=args.max_partitions,
                require_selection_manifest=not args.allow_missing_selection_manifest,
            ),
            thresholds=BacktestOverfitThresholds(
                min_partitions=args.min_partitions,
                min_scenarios=args.min_scenarios,
                max_probability_overfit=args.max_probability_overfit,
                min_median_oos_score=args.min_median_oos_score,
                min_oos_positive_rate=args.min_oos_positive_rate,
                min_median_rank_correlation=args.min_median_rank_correlation,
                max_median_degradation=args.max_median_degradation,
                min_candidate_selection_rate=args.min_candidate_selection_rate,
                max_candidate_overfit_rate=args.max_candidate_overfit_rate,
                min_candidate_oos_positive_rate=args.min_candidate_oos_positive_rate,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        blocked_actions = int(
            result.action_queue.get("queue_status", []).astype(str).eq("blocked").sum()
        ) if not result.action_queue.empty else 0
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "audit-backtest-significance":
        result = write_backtest_significance_audit(
            args.overfit_audit,
            output_dir=args.out,
            config=BacktestSignificanceConfig(
                bootstrap_samples=args.bootstrap_samples,
                confidence_level=args.confidence_level,
                random_seed=args.random_seed,
                zero_tolerance=args.zero_tolerance,
                require_overfit_manifest=not args.allow_missing_overfit_manifest,
            ),
            thresholds=BacktestSignificanceThresholds(
                min_observations=args.min_observations,
                min_nonzero_observations=args.min_nonzero_observations,
                min_positive_rate=args.min_positive_rate,
                max_adjusted_sign_pvalue=args.max_adjusted_sign_pvalue,
                min_bootstrap_probability_positive=(
                    args.min_bootstrap_probability_positive
                ),
                min_bootstrap_mean_lower=args.min_bootstrap_mean_lower,
                require_overfit_passed=not args.allow_failed_overfit,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and action_count > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "audit-backtest-holdout":
        result = write_backtest_holdout_audit(
            args.selection,
            args.holdout_sweeps,
            output_dir=args.out,
            labels=args.labels,
            config=BacktestHoldoutConfig(
                group_columns=tuple(args.group_cols),
                score_column=args.score_column,
                proof_column=args.proof_column,
                require_selection_manifest=(
                    not args.allow_missing_selection_manifest
                ),
                require_sweep_manifests=not args.allow_missing_sweep_manifests,
            ),
            thresholds=BacktestHoldoutThresholds(
                min_sweeps=args.min_sweeps,
                min_candidate_coverage_rate=args.min_candidate_coverage_rate,
                min_proof_pass_rate=args.min_proof_pass_rate,
                min_mean_score=args.min_mean_score,
                min_median_score=args.min_median_score,
                min_worst_score=args.min_worst_score,
                min_mean_net_pnl=args.min_mean_net_pnl,
                min_worst_net_pnl=args.min_worst_net_pnl,
                min_fills_per_sweep=args.min_fills_per_sweep,
                max_worst_drawdown=args.max_worst_drawdown,
                require_selection_passed=not args.allow_failed_selection,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and action_count > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "register-research-family":
        result = write_research_family_registration(
            args.plan,
            output_dir=args.out,
            family_id=args.family_id,
            thresholds=ResearchFamilyRegistrationThresholds(
                min_studies=args.min_studies,
                min_development_sweeps=args.min_development_sweeps,
                min_holdout_sweeps=args.min_holdout_sweeps,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and action_count > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-research-family-launches":
        result = write_research_family_launch_matrix(
            args.registration,
            output_dir=args.out,
            abandonment_path=args.abandonments,
            attest_abandonments=args.attest_abandonments,
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and action_count > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "run-research-family-study":
        contract = load_research_family_launch_contract(
            args.launch_matrix,
            args.contract_id,
        )
        if not contract.ready:
            print("launch contract is not current and ready")
            return 2
        if contract.argv[:4] != [
            "python",
            "-m",
            "hft_cli",
            "pipeline-robust-selection",
        ]:
            raise ValueError("launch contract does not target robust selection")
        try:
            receipt = write_research_family_launch_execution_receipt(
                contract,
                retry_of_attempt_id=args.retry_of_attempt_id,
                retry_reason=args.retry_reason,
                attest_retry=args.attest_retry,
            )
        except (OSError, ValueError) as exc:
            print(f"launch dispatch blocked: {exc}")
            return 2
        dispatch_argv = [
            *contract.argv,
            "--research-launch-execution-receipt",
            str(receipt.path),
        ]
        try:
            status = main(dispatch_argv[3:])
        except BaseException as exc:
            try:
                write_research_family_launch_attempt_outcome(
                    receipt,
                    exit_status=1,
                    execution_completed=False,
                    exception_type=type(exc).__name__,
                )
            except (OSError, ValueError) as outcome_exc:
                print(f"launch outcome finalization failed: {outcome_exc}")
            raise
        try:
            outcome = write_research_family_launch_attempt_outcome(
                receipt,
                exit_status=status,
                execution_completed=True,
            )
        except (OSError, ValueError) as exc:
            print(f"launch outcome finalization failed: {exc}")
            return 2
        if status == 0 and outcome.outcome_status != "completed_ready":
            print(
                "launch outcome is inconsistent with a successful executor status"
            )
            return 2
        return status
    if args.command == "recover-research-family-study-outcome":
        try:
            outcome = recover_research_family_launch_attempt_outcome(
                args.launch_matrix,
                args.attempt_id,
                exit_status=args.exit_status,
                recovery_reason=args.recovery_reason,
                attest_recovery=args.attest_recovery,
            )
        except (OSError, ValueError) as exc:
            print(f"launch outcome recovery blocked: {exc}")
            return 2
        print(
            f"recovered outcome {outcome.outcome_id} "
            f"as {outcome.outcome_status}"
        )
        return 0
    if args.command == "audit-research-family":
        result = write_research_family_audit(
            args.studies,
            output_dir=args.out,
            labels=args.labels,
            registration_path=args.registration,
            launch_matrix_path=args.launch_matrix,
            config=ResearchFamilyConfig(
                family_id=args.family_id,
                declaration_complete_attested=args.attest_complete_family,
                require_study_manifests=(
                    not args.allow_missing_study_manifests
                ),
                require_source_ready=True,
                require_holdout_passed=True,
                require_prospective_registration=(
                    args.require_prospective_registration
                ),
                require_launch_coverage=args.require_launch_coverage,
            ),
            thresholds=ResearchFamilyThresholds(
                min_studies=args.min_studies,
                max_holm_adjusted_pvalue=args.max_holm_adjusted_pvalue,
                min_family_candidates=args.min_family_candidates,
            ),
        )
        print(result.summary.to_string(index=False))
        action_count = int(len(result.action_queue))
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and action_count > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "promote-scenario":
        result = write_promotion_report(
            args.selection,
            output_dir=args.out,
            overfit_audit_path=args.overfit_audit,
            significance_audit_path=args.significance_audit,
            holdout_audit_path=args.holdout_audit,
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
                require_overfit_audit=args.require_overfit_audit,
                require_significance_audit=args.require_significance_audit,
                require_holdout_audit=args.require_holdout_audit,
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
                require_quote_risk_review=args.require_quote_risk_review,
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_unmapped and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "intake-vendor-csv":
        result = write_vendor_csv_intake_report(
            args.sample,
            output_dir=args.out,
            config=VendorCsvIntakeConfig(
                adapter=args.adapter,
                kind=args.kind,
                sample_rows=args.sample_rows,
                min_mapping_coverage=args.min_mapping_coverage,
                output_mapping_file=args.output_mapping_file,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "verify-vendor-csv-intake":
        result = verify_vendor_csv_intake_report(args.intake)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "blocked": result.blocked,
                    "manifest_current": result.manifest_current,
                    "source_current": result.source_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "intake_only": result.intake_only,
                    "non_authorizing": result.non_authorizing,
                    "intake_dir": str(result.output_dir),
                    "source_path": "" if result.source_path is None else str(result.source_path),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.ready)
            else 0
        )
    if args.command == "review-vendor-mapping":
        result = write_vendor_mapping_review(
            args.intake,
            args.mapping,
            args.decision,
            args.out,
            config=VendorMappingReviewConfig(
                output_mapping_file=args.output_mapping_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_rejected and not result.approved else 0
    if args.command == "verify-vendor-mapping-review":
        result = verify_vendor_mapping_review(args.review)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "sealed": result.sealed,
                    "approved": result.approved,
                    "rejected": result.rejected,
                    "manifest_current": result.manifest_current,
                    "intake_current": result.intake_current,
                    "mapping_candidate_current": result.mapping_candidate_current,
                    "operator_decision_current": result.operator_decision_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "normalization_only": result.normalization_only,
                    "non_routing": result.non_routing,
                    "review_dir": str(result.output_dir),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.approved)
            else 0
        )
    if args.command == "review-vendor-mapping-scope":
        result = write_vendor_mapping_scope_review(
            args.review,
            args.decision,
            args.out,
            config=VendorMappingScopeReviewConfig(
                output_mapping_file=args.output_mapping_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_rejected and not result.approved else 0
    if args.command == "verify-vendor-mapping-scope-review":
        result = verify_vendor_mapping_scope_review(args.scope_review)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "sealed": result.sealed,
                    "approved": result.approved,
                    "rejected": result.rejected,
                    "manifest_current": result.manifest_current,
                    "mapping_review_current": result.mapping_review_current,
                    "operator_decision_current": result.operator_decision_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "application_only": result.application_only,
                    "non_routing": result.non_routing,
                    "scope_review_dir": str(result.output_dir),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return (
            2
            if args.fail_on_breach
            and not (result.verified and result.approved)
            else 0
        )
    if args.command == "apply-vendor-mapping-scope":
        result = write_vendor_mapping_application(
            args.scope_review,
            args.intake,
            args.out,
            config=VendorMappingApplicationConfig(
                output_mapping_file=args.output_mapping_file,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "verify-vendor-mapping-application":
        result = verify_vendor_mapping_application(args.application)
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "ready": result.ready,
                    "manifest_current": result.manifest_current,
                    "scope_review_current": result.scope_review_current,
                    "target_intake_current": result.target_intake_current,
                    "target_source_current": result.target_source_current,
                    "artifacts_consistent": result.artifacts_consistent,
                    "target_bound": result.target_bound,
                    "application_only": result.application_only,
                    "non_routing": result.non_routing,
                    "application_dir": str(result.output_dir),
                    "error": result.error,
                },
                sort_keys=True,
            )
        )
        return 2 if args.fail_on_breach and not result.verified else 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-broker-readiness":
        result = write_broker_readiness_report(
            output_dir=args.out,
            schema_audit_dir=args.schema_audit,
            order_export_dir=args.order_export,
            mapping_draft_dir=args.mapping_draft,
            mapped_orders_dir=args.mapped_orders,
            upload_pack_dir=args.upload_pack,
            halt_export_dir=args.halt_export,
            reconciliation_dir=args.reconciliation,
            runtime_session_dir=args.runtime_session,
            resume_dir=args.resume_gate,
            dispatch_roundtrip_dir=args.dispatch_roundtrip,
            vendor_market_data_batch_dir=args.vendor_market_data_batch,
            thresholds=BrokerReadinessThresholds(
                adapter=args.adapter,
                expected_market=args.expected_market,
                expected_vendor_data_kind=args.expected_vendor_data_kind,
                require_reviewed_schema=not args.allow_placeholder_schema,
                require_schema_audit=not args.skip_schema_audit,
                require_order_export=not args.skip_order_export,
                require_mapping_draft=args.require_mapping_draft,
                require_mapped_orders=args.require_mapped_orders,
                require_upload_pack=not args.skip_upload_pack,
                require_halt_export=args.require_halt_export,
                require_reconciliation=args.require_reconciliation,
                require_runtime_session=args.require_runtime_session,
                require_resume_gate=args.require_resume_gate,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_adapter_match=not args.allow_adapter_mismatch,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "shadow-session-report":
        result = write_shadow_session_report(
            launch_dir=args.launch,
            export_dir=args.export,
            reconciliation_dir=args.reconciliation,
            output_dir=args.out,
            runtime_session_dir=args.runtime_session,
            broker_readiness_dir=args.broker_readiness,
            thresholds=ShadowSessionThresholds(
                require_launch_ready=not args.allow_unready_launch,
                require_export_ready=not args.allow_unready_export,
                require_reconciliation_passed=not args.allow_failed_reconciliation,
                require_runtime_session=args.require_runtime_session,
                require_runtime_guard_continue=not args.allow_runtime_guard_halt,
                require_broker_readiness=args.require_broker_readiness,
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
                max_runtime_halted_sessions=args.max_runtime_halted_sessions,
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
            data_readiness_dir=args.data_readiness,
            data_readiness_comparison_dir=args.data_readiness_comparison,
            strategy_portfolio_dir=args.strategy_portfolio,
            route_readiness_dir=args.route_readiness,
            broker_readiness_dir=args.broker_readiness,
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
                max_telemetry_age_ns=args.max_telemetry_age_ns,
                max_lifecycle_orders=args.max_lifecycle_orders,
                max_replace_orders=args.max_replace_orders,
                max_open_order_count=args.max_open_order_count,
                max_open_order_qty=args.max_open_order_qty,
                max_open_order_notional=args.max_open_order_notional,
                max_open_order_age_ns=args.max_open_order_age_ns,
                max_gross_position_qty=args.max_gross_position_qty,
                max_abs_net_position_qty=args.max_abs_net_position_qty,
                max_orders_per_session=args.max_orders_per_session,
                max_session_notional=args.max_session_notional,
                max_gross_notional=args.max_gross_notional,
                max_abs_net_delta=args.max_abs_net_delta,
                max_abs_net_vega=args.max_abs_net_vega,
                stop_loss=args.stop_loss,
                allowed_adapters=tuple(args.allowed_adapters or ()),
                require_proof_refresh=args.require_proof_refresh,
                require_instrument_metadata=args.require_instrument_metadata,
                require_data_readiness=args.require_data_readiness,
                require_data_readiness_comparison=args.require_data_readiness_comparison,
                require_strategy_portfolio=args.require_strategy_portfolio,
                require_route_readiness=args.require_route_readiness,
                require_broker_readiness=args.require_broker_readiness,
                require_resume_gate=args.require_resume_gate,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                min_instrument_parse_coverage=args.min_instrument_parse_coverage,
                expected_strategy=args.expected_strategy,
                expected_market=args.expected_market,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "build-runtime-telemetry":
        result = write_runtime_telemetry_snapshot(
            scaleup_dir=args.scaleup,
            output_dir=args.out,
            export_dir=args.export,
            upload_pack_dir=args.upload_pack,
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
            as_of_ts_ns=args.as_of_ts_ns,
            max_telemetry_age_ns=args.max_telemetry_age_ns,
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_halt and result.halted:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "monitor-runtime-session":
        result = write_runtime_session_monitor(
            scaleup_dir=args.scaleup,
            output_dir=args.out,
            export_dir=args.export,
            upload_pack_dir=args.upload_pack,
            reconciliation_dir=args.reconciliation,
            instrument_metadata_dir=args.instrument_metadata,
            pnl_path=args.pnl,
            open_orders_path=args.open_orders,
            positions_path=args.positions,
            snapshot_ts_ns=args.snapshot_ts_ns,
            as_of_ts_ns=args.as_of_ts_ns,
            max_telemetry_age_ns=args.max_telemetry_age_ns,
            plan_halt_response=not args.skip_halt_response,
            halt_response_config=HaltResponseConfig(
                require_guard_halt=True,
                require_flatten_prices=not args.allow_missing_flatten_prices,
                default_order_type=args.default_order_type,
                default_time_in_force=args.default_time_in_force,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
                require_operator_guard_trigger_ack=args.require_operator_trigger_ack,
                max_failed_scaleup_checks=args.max_failed_scaleup_checks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-cutover-gate":
        result = write_cutover_gate_report(
            scaleup_dir=args.scaleup,
            broker_readiness_dir=args.broker_readiness,
            runtime_session_dir=args.runtime_session,
            operator_review_path=args.operator_review,
            output_dir=args.out,
            thresholds=CutoverGateThresholds(
                target_mode=args.target_mode,
                require_scaleup_ready=not args.allow_unready_scaleup,
                require_broker_readiness=not args.allow_missing_broker_readiness,
                require_runtime_session=not args.allow_missing_runtime_session,
                require_runtime_guard_continue=not args.allow_runtime_guard_halt,
                require_route_readiness=args.require_route_readiness,
                require_resume_gate=args.require_resume_gate,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_operator_approval=not args.allow_missing_operator_approval,
                require_operator_identity_ack=not args.allow_missing_operator_identity_ack,
                require_operator_limits_ack=not args.allow_missing_operator_limits_ack,
                max_failed_scaleup_checks=args.max_failed_scaleup_checks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-route-enable":
        result = write_route_enable_packet(
            cutover_dir=args.cutover,
            upload_pack_dir=args.upload_pack,
            order_export_dir=args.order_export,
            output_dir=args.out,
            thresholds=RouteEnableThresholds(
                target_mode=args.target_mode,
                require_cutover_ready=not args.allow_unready_cutover,
                require_upload_ready=not args.allow_unready_upload,
                require_order_export_ready=args.require_order_export,
                require_adapter_match=not args.allow_adapter_mismatch,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                min_orders=args.min_orders,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "plan-broker-dispatch":
        result = write_broker_dispatch_plan(
            route_enable_dir=args.route_enable,
            upload_pack_dir=args.upload_pack,
            upload_orders_path=args.upload_orders,
            output_dir=args.out,
            thresholds=BrokerDispatchThresholds(
                target_mode=args.target_mode,
                require_route_enabled=not args.allow_disabled_route,
                require_dry_run=not args.allow_non_dry_run,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                min_orders=args.min_orders,
                max_orders=args.max_orders,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "prepare-broker-dispatch-send":
        result = write_broker_dispatch_send_packet(
            dispatch_dir=args.dispatch,
            output_dir=args.out,
            thresholds=BrokerDispatchSendThresholds(
                target_mode=args.target_mode,
                require_dispatch_ready=not args.allow_unready_dispatch,
                require_armed_dispatch=not args.allow_unarmed_dispatch,
                require_dry_run=not args.allow_non_dry_run,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                max_requests=args.max_requests,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.ready:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "reconcile-broker-dispatch":
        result = write_broker_dispatch_acknowledgements(
            dispatch_dir=args.dispatch,
            send_dir=args.send,
            acks_path=args.acks,
            output_dir=args.out,
            thresholds=BrokerDispatchAckThresholds(
                require_dispatch_ready=not args.allow_unready_dispatch,
                require_all_acked=not args.allow_missing_acks,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_send_packet=args.require_send_packet,
                allow_rejections=args.allow_rejections,
                max_duplicate_ack_orders=args.max_duplicate_ack_orders,
                max_unmatched_acks=args.max_unmatched_acks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
    if args.command == "review-broker-dispatch-roundtrip":
        result = write_broker_dispatch_roundtrip(
            dispatch_dir=args.dispatch,
            send_dir=args.send,
            ack_dir=args.ack,
            output_dir=args.out,
            thresholds=BrokerDispatchRoundTripThresholds(
                target_mode=args.target_mode,
                require_dispatch_ready=not args.allow_unready_dispatch,
                require_send_ready=not args.allow_unready_send,
                require_ack_passed=not args.allow_failed_ack,
                require_identity_match=not args.allow_identity_mismatch,
                require_submission_disabled=not args.allow_submission_enabled,
                require_all_requests_acked=not args.allow_missing_request_acks,
                require_route_readiness=args.require_route_readiness,
                require_dispatch_roundtrip=args.require_dispatch_roundtrip,
                require_ack_lineage=args.require_ack_lineage,
                allow_rejections=args.allow_rejections,
                max_duplicate_ack_orders=args.max_duplicate_ack_orders,
                max_unmatched_acks=args.max_unmatched_acks,
                max_missing_request_acks=args.max_missing_request_acks,
                max_total_failed_component_checks=args.max_total_failed_component_checks,
            ),
        )
        print(result.summary.to_string(index=False))
        action_queue = result.action_queue
        action_count = 0 if action_queue is None else int(len(action_queue))
        blocked_actions = 0
        if action_queue is not None and not action_queue.empty:
            blocked_actions = int((action_queue["queue_status"].astype(str) == "blocked").sum())
        if args.fail_on_breach and not result.passed:
            return 2
        if args.fail_on_blocked_actions and blocked_actions > 0:
            return 2
        if args.fail_on_actions and action_count > 0:
            return 2
        return 0
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
    if args.command == "review-surface-quality":
        result = write_surface_quality_report(
            args.quotes,
            args.chain,
            output_dir=args.out,
            horizons_ns=args.horizon_ns,
            thresholds=SurfaceQualityThresholds(
                min_observations=args.min_observations,
                min_instruments=args.min_instruments,
                min_mae_improvement=args.min_mae_improvement,
                min_relative_mae_improvement=args.min_relative_mae_improvement,
                min_improvement_rate=args.min_improvement_rate,
                max_theo_mae=args.max_theo_mae,
            ),
            filter_session=not args.no_filter_session,
            market=args.market,
            strategy=args.strategy,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "pipeline-surface-mm-research":
        result = write_surface_mm_research_pipeline(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            data_readiness_comparison_dir=args.data_readiness_comparison,
            require_data_readiness_comparison=args.require_data_readiness_comparison,
            market_portability_dir=args.market_portability,
            require_market_portability=args.require_market_portability,
            filter_session=not args.no_filter_session,
            market=args.market,
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
            surface_quality_horizon_ns_values=args.surface_quality_horizon_ns,
            require_surface_quality=args.require_surface_quality,
            surface_quality_thresholds=SurfaceQualityThresholds(
                min_observations=args.min_surface_quality_observations,
                min_instruments=args.min_surface_quality_instruments,
                min_mae_improvement=args.min_surface_quality_mae_improvement,
                min_relative_mae_improvement=args.min_surface_quality_relative_improvement,
                min_improvement_rate=args.min_surface_quality_improvement_rate,
                max_theo_mae=args.max_surface_quality_theo_mae,
            ),
            quote_risk_thresholds=QuoteRiskThresholds(
                min_quotes=args.min_quotes,
                min_instruments=args.min_instruments,
                max_marketable_quotes=args.max_marketable_quotes,
                min_quote_edge=args.min_quote_edge,
                min_bid_share=args.min_bid_share,
                max_bid_share=args.max_bid_share,
                max_market_spread_ticks=args.max_market_spread_ticks,
                max_quotes_per_instrument=args.max_quotes_per_instrument,
            ),
            quote_ttl_ns_values=args.quote_ttl_ns,
            order_latency_us_values=args.order_latency_us,
            fill_depth_fraction_values=args.fill_depth_fraction,
            markout_horizon_ns_values=args.markout_horizon_ns,
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
            min_selection_pass_rate=args.min_selection_pass_rate,
            min_selection_sweeps=args.min_selection_sweeps,
            min_selection_median_net_pnl=args.min_selection_median_net_pnl,
            max_selection_worst_drawdown=args.max_selection_worst_drawdown,
            promotion_thresholds=PromotionThresholds(
                min_pass_rate=args.min_promotion_pass_rate,
                min_sweeps=args.min_promotion_sweeps,
                min_median_net_pnl=args.min_promotion_median_net_pnl,
                min_median_fills=args.min_promotion_median_fills,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
    if args.command == "pipeline-surface-mm-launch":
        result = write_surface_mm_launch_pipeline(
            args.surface_pipeline,
            output_dir=args.out,
            config=SurfaceMMLaunchPipelineConfig(
                adapter=args.adapter,
                mode=args.mode,
                route_tag=args.route_tag,
                expected_strategy=args.expected_strategy,
                expected_market=args.expected_market,
                require_surface_pipeline_ready=not args.allow_unready_surface_pipeline,
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                quote_ttl_ns=args.quote_ttl_ns,
                max_quote_order_messages=args.max_quote_order_messages,
                max_active_quotes=args.max_active_quotes,
                max_quote_replaces=args.max_quote_replaces,
                max_quote_cancels=args.max_quote_cancels,
                max_quote_messages_per_snapshot=args.max_quote_messages_per_snapshot,
                expected_quote_fills=args.expected_quote_fills,
                max_quote_otr=args.max_quote_otr,
                product=args.product,
                exchange=args.exchange,
                require_reviewed_schema=not args.allow_placeholder_schema,
                broker_schema_audit_dir=args.broker_schema_audit,
                broker_mapping_draft_dir=args.broker_mapping_draft,
                broker_mapped_orders_dir=args.broker_mapped_orders,
                broker_halt_export_dir=args.broker_halt_export,
                broker_reconciliation_dir=args.broker_reconciliation,
                broker_runtime_session_dir=args.broker_runtime_session,
                broker_vendor_data_readiness_dir=args.broker_vendor_data_readiness,
                require_broker_schema_audit=args.require_broker_schema_audit,
                require_broker_mapping_draft=args.require_broker_mapping_draft,
                require_broker_mapped_orders=args.require_broker_mapped_orders,
                require_broker_halt_export=args.require_broker_halt_export,
                require_broker_reconciliation=args.require_broker_reconciliation,
                require_broker_runtime_session=args.require_broker_runtime_session,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.ready else 0
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
            data_readiness_comparison_dir=args.data_readiness_comparison,
            require_data_readiness_comparison=args.require_data_readiness_comparison,
            strategy=args.strategy,
            market=args.market,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "plan-quote-lifecycle":
        result = write_quote_lifecycle_plan(
            args.quotes,
            output_dir=args.out,
            thresholds=QuoteLifecycleThresholds(
                quote_ttl_ns=args.quote_ttl_ns,
                max_order_messages=args.max_order_messages,
                max_active_quotes=args.max_active_quotes,
                max_replaces=args.max_replaces,
                max_cancels=args.max_cancels,
                max_messages_per_snapshot=args.max_messages_per_snapshot,
                expected_fills=args.expected_fills,
                max_order_to_trade_ratio=args.max_order_to_trade_ratio,
                final_cancel=not args.no_final_cancel,
            ),
            quote_risk_review_dir=args.quote_risk_review,
            require_quote_risk_review=args.require_quote_risk_review,
            surface_quality_review_dir=args.surface_quality_review,
            require_surface_quality=args.require_surface_quality,
        )
        print(result.summary.to_string(index=False))
        return (
            2
            if (args.fail_on_breach or args.require_quote_risk_review or args.require_surface_quality)
            and not result.ready
            else 0
        )
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
            market=args.market,
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
            quote_risk_review_dir=args.quote_risk_review,
            require_quote_risk_review=args.require_quote_risk_review,
        )
        print(result.summary.to_string(index=False))
        preflight_blocked = bool(result.summary.iloc[0].get("preflight_blocked", False)) if not result.summary.empty else False
        return 2 if preflight_blocked else 0
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
            quote_risk_review_dir=args.quote_risk_review,
            require_quote_risk_review=args.require_quote_risk_review,
            surface_quality_review_dir=args.surface_quality_review,
            require_surface_quality=args.require_surface_quality,
        )
        print(result.summary.to_string(index=False))
        return (
            2
            if (args.fail_on_reject or args.require_quote_risk_review or args.require_surface_quality)
            and not result.passed
            else 0
        )
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


def _validated_provider_legacy_lineage_audit(
    *,
    strict_lineage: bool,
    audit_dir: str | None,
    source_path: str,
    source_role: str,
    legacy_flag: str,
) -> str:
    if strict_lineage:
        if audit_dir:
            raise ValueError(
                "--lineage-migration-audit is only valid with "
                f"{legacy_flag}"
            )
        return ""
    if not audit_dir:
        raise ValueError(
            f"--lineage-migration-audit is required with {legacy_flag}"
        )
    verification = verify_provider_broker_lineage_migration_audit(
        audit_dir,
        source_path=source_path,
        source_role=source_role,
    )
    if not verification.ready:
        raise ValueError(
            "lineage migration audit rejected legacy source: "
            f"{verification.error}"
        )
    return str(verification.audit_dir)


if __name__ == "__main__":
    raise SystemExit(main())
