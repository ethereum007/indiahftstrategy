import hashlib
import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan
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
from reports.provider_market_data_live_bundle import (
    ProviderMarketDataLiveCaptureBundleConfig,
    write_provider_market_data_live_capture_bundle,
)
from reports.provider_market_data_live_evidence import (
    ProviderMarketDataLiveEvidenceConfig,
    write_provider_market_data_live_evidence_review,
)
from reports.provider_market_data_live_ingest import (
    ProviderMarketDataLiveIngestConfig,
    write_provider_market_data_live_session_ingest,
)
from reports.provider_market_data_live_preflight import (
    ProviderMarketDataLivePreflightConfig,
    write_provider_market_data_live_session_preflight,
)
from reports.provider_market_data_live_rehearsal import (
    ProviderMarketDataLiveRehearsalConfig,
    write_provider_market_data_live_rehearsal,
)
from reports.provider_market_data_live_session import (
    ProviderMarketDataLiveSessionConfig,
    write_provider_market_data_live_session_plan,
)


def _imbalance_ticks(day: str):
    return pd.DataFrame(
        [
            {
                "ts": f"{day} 09:15:00.000000",
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 900,
                "ask_qty": 100,
                "last": 100.05,
                "last_qty": 75,
            },
            {
                "ts": f"{day} 09:15:00.000100",
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 900,
                "ask_qty": 100,
                "last": 100.05,
                "last_qty": 75,
            },
            {
                "ts": f"{day} 09:15:00.000200",
                "bid": 100.30,
                "ask": 100.35,
                "bid_qty": 100,
                "ask_qty": 900,
                "last": 100.30,
                "last_qty": 50,
            },
            {
                "ts": f"{day} 09:15:00.000300",
                "bid": 100.30,
                "ask": 100.35,
                "bid_qty": 100,
                "ask_qty": 900,
                "last": 100.30,
                "last_qty": 50,
            },
            {
                "ts": f"{day} 09:15:00.000400",
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 500,
                "ask_qty": 500,
                "last": 100.05,
                "last_qty": 25,
            },
        ]
    )


def _write_client_packet(tmp_path):
    source_report = write_market_data_source_plan(
        tmp_path / "source",
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind="ticks",
            transport="websocket",
            source_uri="wss://feed.arrow.money/market-data/nse",
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )
    fetch_report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / "fetch",
        config=MarketDataFetchConfig(symbols=("NIFTY-I", "BANKNIFTY-I")),
    )
    fetcher_report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / "fetcher",
    )
    client_report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / "client",
    )
    return client_report.output_dir / "provider_market_data_client_packet.json"


def _write_live_plan(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    return write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_plan",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:45", "close=14:45-15:15"),
            capture_dir=str(tmp_path / "captures"),
            batch_output_dir=str(tmp_path / "batch"),
            min_capture_rows=5,
            pipeline_min_rows=5,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )


def _write_expected_imbalance_captures(live_packet_path):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    days = ["2026-06-23", "2026-06-24"]
    for idx, window in enumerate(packet["capture_windows"]):
        path = Path(window["capture_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        _imbalance_ticks(days[idx]).to_csv(path, index=False)


def _write_real_evidence(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    _write_expected_imbalance_captures(live_packet)
    ingest = write_provider_market_data_live_session_ingest(live_packet, tmp_path / "live_ingest")
    return write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=5),
    )


def _write_bundle_linked_real_evidence(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    preflight = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )
    bundle = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            ingest_output_dir=str(tmp_path / "live_ingest"),
        ),
    )
    bundle_path = bundle.output_dir / "provider_market_data_live_capture_bundle.json"
    _write_expected_imbalance_captures(live_packet)
    ingest = write_provider_market_data_live_session_ingest(
        live_packet,
        tmp_path / "live_ingest",
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )
    evidence = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=5),
    )
    return evidence, bundle_path


def _mutate_json(path, mutator):
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    mutator(payload)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _write_synthetic_smoke_evidence(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    preflight = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )
    bundle = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            ingest_output_dir=str(tmp_path / "rehearsal_ingest"),
        ),
    )
    rehearsal = write_provider_market_data_live_rehearsal(
        bundle.output_dir / "provider_market_data_live_capture_bundle.json",
        tmp_path / "rehearsal",
        config=ProviderMarketDataLiveRehearsalConfig(
            rows_per_window=5,
            ingest_output_dir=str(tmp_path / "rehearsal_ingest"),
            ingest_min_capture_rows=5,
            ingest_pipeline_min_rows=5,
        ),
    )
    return write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(
            allow_synthetic_rehearsal=True,
            min_capture_rows=5,
        ),
    )


def _passing_config():
    return ProviderMarketDataImbalanceResearchConfig(
        entry_imbalance_values=(0.6, 0.7),
        min_microprice_edge_ticks_values=(0.25,),
        forward_horizon_ns_values=(100_000,),
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=0.5,
        timestamp_unit="datetime",
        timestamp_tz="Asia/Kolkata",
        cooloff_ns=100_000,
        min_selection_median_usable_signals=2,
        min_total_fills=2,
    )


def _write_ready_provider_imbalance_launch_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    return write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        tmp_path / "provider_imbalance_launch_evidence",
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )


def _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path):
    evidence, bundle_path = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    launch_evidence = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        tmp_path / "provider_imbalance_launch_evidence",
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )
    return launch_evidence, bundle_path


def _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence, *, accepted=True):
    launch_evidence_summary = pd.read_csv(
        launch_evidence.output_dir / "provider_market_data_imbalance_launch_evidence_summary.csv"
    )
    provider_launch_dir = Path(launch_evidence_summary.loc[0, "provider_launch_dir"])
    launch_summary = pd.read_csv(provider_launch_dir / "imbalance_launch_pipeline" / "03_launch" / "launch_summary.csv")
    out_dir = tmp_path / "provider_imbalance_shadow_comparison"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "accepted": accepted,
                "session_count": 2,
                "accepted_sessions": 2 if accepted else 1,
                "acceptance_rate": 1.0 if accepted else 0.5,
                "scenario_count": 1,
                "scenario_key": launch_summary.loc[0, "scenario_key"],
                "median_order_fill_rate": 1.0,
                "worst_order_fill_rate": 1.0,
                "total_failed_component_checks": 0 if accepted else 1,
                "total_unmatched_fills": 0,
                "total_mismatched_orders": 0,
                "total_overfilled_orders": 0,
                "worst_adverse_slippage": 0.0,
            }
        ]
    ).to_csv(out_dir / "shadow_session_comparison_summary.csv", index=False)
    return out_dir


def _write_ready_ops_launch_evidence(tmp_path, *, evidence_profile="provider_imbalance_ops_launch"):
    out_dir = tmp_path / f"{evidence_profile}_evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": True,
                "failed_checks": 0,
                "recommendation": "eligible_for_live_dryrun_route_review",
                "evidence_profile": evidence_profile,
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "require_file_inputs": True,
                "input_file_count": 3,
                "input_directory_count": 0,
                "input_other_count": 0,
                "input_unfingerprinted_count": 0,
                "source_path": str(out_dir / "strategy_evidence_summary.csv"),
                "require_no_blocked_placeholder_schema": True,
                "placeholder_schema_blocked_runs": 0,
                "require_broker_roundtrip_portfolio_safe": True,
                "fail_on_broker_roundtrip_portfolio_breach": True,
                "broker_roundtrip_portfolio_safe_runs": 1,
                "broker_roundtrip_portfolio_breach_runs": 0,
                "require_broker_roundtrip_portfolio_concentration_ok": True,
                "fail_on_broker_roundtrip_portfolio_concentration_breach": True,
                "broker_roundtrip_portfolio_concentration_ok_runs": 1,
                "broker_roundtrip_portfolio_concentration_breach_runs": 0,
                "require_broker_roundtrip_resume_route_ready": True,
                "fail_on_broker_roundtrip_resume_route_breach": True,
                "broker_roundtrip_resume_route_ready_runs": 1,
                "broker_roundtrip_resume_route_breach_runs": 0,
                "broker_roundtrip_resume_route_gap_breach_runs": 0,
                "broker_roundtrip_resume_route_launch_control_breach_runs": 0,
                "broker_roundtrip_resume_route_portfolio_breach_runs": 0,
                "broker_roundtrip_resume_route_concentration_breach_runs": 0,
            }
        ]
    ).to_csv(out_dir / "strategy_evidence_summary.csv", index=False)
    return out_dir


def _write_ready_provider_imbalance_runtime_telemetry(tmp_path, *, snapshot_ts_ns=1_000_000):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    return write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=snapshot_ts_ns,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )


def _write_ready_provider_imbalance_runtime_guard(tmp_path, *, snapshot_ts_ns=1_000_000, as_of_ts_ns=1_000_000):
    runtime_telemetry = _write_ready_provider_imbalance_runtime_telemetry(
        tmp_path,
        snapshot_ts_ns=snapshot_ts_ns,
    )
    return write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=as_of_ts_ns,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )


def _write_ready_provider_imbalance_runtime_session(
    tmp_path,
    *,
    snapshot_ts_ns=1_000_000,
    as_of_ts_ns=1_000_000,
):
    runtime_guard = _write_ready_provider_imbalance_runtime_guard(
        tmp_path,
        snapshot_ts_ns=snapshot_ts_ns,
        as_of_ts_ns=as_of_ts_ns,
    )
    return write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=as_of_ts_ns,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )


def _write_ready_provider_imbalance_broker_readiness(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    return write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )


def _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup_with_route",
        route_readiness_dir=route_readiness.output_dir,
    )
    telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry_with_route",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    guard = write_provider_market_data_imbalance_runtime_guard(
        telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard_with_route",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    session = write_provider_market_data_imbalance_runtime_session(
        guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session_with_route",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness_with_route",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    return write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover_with_route",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )


def _write_ready_provider_imbalance_route_enable(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    return write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )


def _write_ready_provider_imbalance_broker_dispatch(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    return write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )


def _write_ready_provider_imbalance_broker_dispatch_send(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    return write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )


def _write_provider_imbalance_accepted_ack_file(provider_send, output_path):
    requests = pd.read_csv(provider_send.output_dir / "broker_dispatch_send" / "broker_dispatch_send_requests.csv")
    rows = []
    for index, row in requests.reset_index(drop=True).iterrows():
        rows.append(
            {
                "dispatch_order_id": row["dispatch_order_id"],
                "source_order_id": row["source_order_id"],
                "route_dispatch_roundtrip_batch_id": row.get("route_dispatch_roundtrip_batch_id", ""),
                "status": "accepted",
                "broker_order_id": f"BRK-{index + 1:06d}",
                "ack_ts_ns": 2_000_000 + index,
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def _vendor_market_data_batch_config():
    return {
        "provided": True,
        "ready": True,
        "adapter": "arrow_money",
        "kind": "ticks",
        "manifest_run_type": "vendor_market_data_batch_pipeline",
        "market": "india_nse_index_derivatives",
        "dataset_count": 2,
        "ready_datasets": 2,
        "failed_datasets": 0,
        "ready_rate": 1.0,
        "unique_source_files": 2,
        "source_file_fingerprint_coverage": 1.0,
        "min_mapping_coverage": 1.0,
        "unique_header_fingerprints": 1,
        "unique_mapping_drafts": 1,
        "mapping_sources": "vendor_intake_draft",
        "comparison": {
            "accepted": True,
            "failed_checks": 0,
        },
        "datasets": [
            {
                "dataset": "nifty_day1",
                "ready": True,
                "source_file_sha256": "a" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "vendor_intake_draft",
            },
            {
                "dataset": "nifty_day2",
                "ready": True,
                "source_file_sha256": "d" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "vendor_intake_draft",
            },
        ],
    }


def _inject_nested_roundtrip_vendor_market_data_batch(provider_ack):
    ack_summary = pd.read_csv(
        provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ).iloc[0]
    nested_vendor_configs = [
        (
            Path(ack_summary["broker_dispatch_dir"]) / "broker_dispatch_config.json",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        (
            Path(ack_summary["provider_broker_dispatch_send_dir"])
            / "broker_dispatch_send"
            / "broker_dispatch_send_config.json",
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        (
            Path(ack_summary["broker_dispatch_ack_dir"]) / "broker_dispatch_ack_config.json",
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
    ]
    for config_path, key in nested_vendor_configs:
        nested_config = json.loads(config_path.read_text(encoding="utf-8"))
        nested_config[key] = _vendor_market_data_batch_config()
        config_path.write_text(
            json.dumps(nested_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    acks_path = _write_provider_imbalance_accepted_ack_file(provider_send, tmp_path / "provider_imbalance_acks.csv")
    return write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )


def _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    return write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )


def _write_ready_provider_imbalance_broker_dispatch_roundtrip_with_vendor_batch(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    _inject_nested_roundtrip_vendor_market_data_batch(provider_ack)
    return write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip_with_vendor_batch",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )


def test_provider_market_data_imbalance_research_runs_pipeline_from_live_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    out_dir = tmp_path / "provider_imbalance_research"

    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        out_dir,
        config=_passing_config(),
    )

    summary = report.summary.iloc[0]
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_research_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "provider_market_data_imbalance_research_config.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary["handoff_ready"])
    assert bool(summary["pipeline_ready"])
    assert bool(summary["candidate_ready"])
    assert bool(summary["edge_passed"])
    assert bool(summary["replay_passed"])
    assert bool(summary["promotion_ready"])
    assert summary["dataset_count"] == 2
    assert summary["next_gate"] == "catalog-runs"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "catalog-runs"
    assert config["imbalance_research"]["ready"]
    assert manifest["run_type"] == "provider_market_data_imbalance_research"
    assert (out_dir / "research_handoff" / "provider_market_data_research_handoff_summary.csv").exists()
    assert (out_dir / "imbalance_research" / "imbalance_pipeline_summary.csv").exists()
    assert (out_dir / "imbalance_research" / "promotion" / "promotion_summary.csv").exists()


def test_provider_market_data_imbalance_research_carries_capture_bundle_provenance(tmp_path):
    evidence, bundle_path = _write_bundle_linked_real_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    out_dir = tmp_path / "provider_imbalance_research"

    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        out_dir,
        config=_passing_config(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_research_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_research_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["capture_bundle"]["source_credential_env_template_sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["research_handoff"]["summary"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["research_handoff"]["summary"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["research_handoff"]["summary"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["research_handoff"]["summary"]["source_live_fetch_contract_available"] is True
    assert config["research_handoff"]["summary"]["exchange"] == "NFO"
    assert config["research_handoff"]["summary"]["capture_bundle_metadata_matches_session"] is True
    assert config["research_handoff"]["summary"]["adapter_contract_provider"] == "arrow_money"
    assert config["research_handoff"]["summary"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["research_handoff"]["summary"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["research_handoff"]["summary"]["provider_profile_matches_bundle"] is True
    assert config["research_handoff"]["summary"]["provider_capture_command_count"] == 2
    assert config["research_handoff"]["summary"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook


def test_provider_market_data_imbalance_research_blocks_missing_adapter_execution_contract(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    evidence_config_path = evidence.output_dir / "provider_market_data_live_evidence_config.json"
    manifest_path = evidence.output_dir / "manifest.json"
    _mutate_json(
        evidence_config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )
    _mutate_json(
        manifest_path,
        lambda payload: (
            payload["extra"].pop("adapter_execution_contract", None),
            payload["extra"]["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert report.pipeline is None
    assert "provider_research_handoff_ready" in failed
    assert "provider_research_handoff_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "provider_handoff_regenerate_live_evidence_with_adapter_execution_contract"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-live-evidence"


def test_provider_market_data_imbalance_research_blocks_missing_provider_profile(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    evidence_config_path = evidence.output_dir / "provider_market_data_live_evidence_config.json"
    manifest_path = evidence.output_dir / "manifest.json"
    _mutate_json(
        evidence_config_path,
        lambda payload: payload.pop("provider_profile", None),
    )
    _mutate_json(
        manifest_path,
        lambda payload: payload["extra"].pop("provider_profile", None),
    )

    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert report.pipeline is None
    assert "provider_research_handoff_ready" in failed
    assert "provider_research_handoff_provider_profile_carried" in failed
    assert "provider_research_handoff_provider_profile_matches_session" in failed
    assert "provider_research_handoff_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "provider_handoff_regenerate_live_evidence_with_provider_profile"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-live-evidence"


def test_provider_market_data_imbalance_research_blocks_synthetic_smoke_evidence(tmp_path):
    evidence = _write_synthetic_smoke_evidence(tmp_path)
    out_dir = tmp_path / "provider_imbalance_research"

    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        out_dir,
        config=_passing_config(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_research_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_research_runbook.md").read_text(encoding="utf-8")
    assert evidence.ready
    assert not bool(evidence.summary.iloc[0]["research_ready"])
    assert not report.ready
    assert report.pipeline is None
    assert bool(summary["synthetic_sidecar_proof_ready"])
    assert summary["synthetic_sidecar_count"] == 2
    assert summary["synthetic_sidecar_readable_count"] == 2
    assert summary["synthetic_sidecar_adapter_command_hash_count"] == 2
    assert summary["synthetic_sidecar_capture_env_template_match_count"] == 2
    assert summary["synthetic_sidecar_adapter_handoff_match_count"] == 2
    assert summary["synthetic_sidecar_source_env_template_match_count"] == 2
    assert summary["synthetic_sidecar_live_fetch_contract_count"] == 2
    assert summary["synthetic_sidecar_adapter_execution_contract_safe_count"] == 2
    assert summary["synthetic_sidecar_invariant_count"] == 2
    assert config["synthetic_sidecar_proof"]["ready"] is True
    assert config["synthetic_sidecar_proof"]["synthetic_sidecar_count"] == 2
    assert config["research_handoff"]["summary"]["synthetic_sidecar_proof_ready"] is True
    assert manifest["extra"]["synthetic_sidecar_proof"]["ready"] is True
    assert "Synthetic sidecar proof: yes" in runbook
    assert "provider_research_handoff_ready" in failed
    assert "provider_research_handoff_research_ready" in failed
    assert "provider_research_handoff_synthetic_sidecar_proof_ready" not in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-live-evidence"
    assert not (out_dir / "imbalance_research" / "imbalance_pipeline_summary.csv").exists()


def test_provider_market_data_imbalance_research_blocks_missing_synthetic_sidecar_proof(tmp_path):
    evidence = _write_synthetic_smoke_evidence(tmp_path)
    _mutate_json(
        evidence.output_dir / "provider_market_data_live_evidence_config.json",
        lambda payload: payload.pop("synthetic_sidecar_proof", None),
    )
    _mutate_json(
        evidence.output_dir / "manifest.json",
        lambda payload: payload["extra"].pop("synthetic_sidecar_proof", None),
    )
    out_dir = tmp_path / "provider_imbalance_research"

    config = _passing_config()
    config = ProviderMarketDataImbalanceResearchConfig(
        **{
            **config.__dict__,
            "require_research_ready": False,
            "allow_synthetic_smoke": True,
        }
    )
    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        out_dir,
        config=config,
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert report.pipeline is None
    assert not bool(summary["synthetic_sidecar_proof_ready"])
    assert summary["synthetic_sidecar_count"] == 0
    assert "provider_research_handoff_ready" in failed
    assert "provider_research_handoff_synthetic_sidecar_proof_carried" in failed
    assert "provider_research_handoff_synthetic_sidecar_proof_ready" in failed
    assert "provider_research_handoff_research_ready" not in failed
    assert report.action_queue.loc[0, "action"] == (
        "provider_handoff_regenerate_live_evidence_with_synthetic_sidecar_proof"
    )
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-live-evidence"
    assert not (out_dir / "imbalance_research" / "imbalance_pipeline_summary.csv").exists()


def test_cli_provider_market_data_imbalance_research_accepts_live_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_research"

    code = main(
        [
            "run-provider-market-data-imbalance-research",
            "--live-evidence-dir",
            str(evidence.output_dir),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "0.7",
            "--min-microprice-edge-ticks",
            "0.25",
            "--forward-horizon-ns",
            "100000",
            "--min-signals",
            "2",
            "--min-direction-count",
            "2",
            "--min-mean-forward-edge-ticks",
            "1.0",
            "--min-win-rate",
            "0.5",
            "--timestamp-unit",
            "datetime",
            "--timestamp-tz",
            "Asia/Kolkata",
            "--cooloff-ns",
            "100000",
            "--min-selection-median-usable-signals",
            "2",
            "--min-total-fills",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_research_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "candidate_ready"])


def test_provider_market_data_imbalance_evidence_reviews_ready_research_profile(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    out_dir = tmp_path / "provider_imbalance_evidence"

    report = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )

    summary = report.summary.iloc[0]
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_evidence_action_queue.csv")
    strategy_summary = pd.read_csv(out_dir / "strategy_evidence" / "strategy_evidence_summary.csv")
    items = pd.read_csv(out_dir / "strategy_evidence" / "strategy_evidence_items.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary["provider_research_ready"])
    assert bool(summary["strategy_evidence_ready"])
    assert summary["evidence_profile"] == "provider_imbalance_research"
    assert summary["next_gate"] == "pipeline-imbalance-launch"
    assert strategy_summary.loc[0, "evidence_profile"] == "provider_imbalance_research"
    assert set(items["required_run_type"]) == {
        "provider_market_data_research_handoff",
        "imbalance_edge_walkforward",
        "imbalance_replay_walkforward",
        "promotion_report",
        "imbalance_research_pipeline",
        "provider_market_data_imbalance_research",
    }
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "pipeline-imbalance-launch"
    assert manifest["run_type"] == "provider_market_data_imbalance_evidence_review"


def test_provider_market_data_imbalance_evidence_carries_capture_bundle_provenance(tmp_path):
    evidence, bundle_path = _write_bundle_linked_real_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    out_dir = tmp_path / "provider_imbalance_evidence"

    report = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_evidence_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_evidence_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["capture_bundle"]["source_credential_env_template_sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_research"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_research"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_research"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_research"]["source_live_fetch_contract_available"] is True
    assert config["provider_research"]["exchange"] == "NFO"
    assert config["provider_research"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_research"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_research"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_research"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_research"]["provider_profile_matches_bundle"] is True
    assert config["provider_research"]["provider_capture_command_count"] == 2
    assert config["provider_research"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook


def test_provider_market_data_imbalance_evidence_blocks_missing_adapter_execution_contract(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    summary_path = research.output_dir / "provider_market_data_imbalance_research_summary.csv"
    research_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        research_summary.loc[0, column] = ""
    research_summary.loc[0, "adapter_contract_values_stored"] = True
    research_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    research_summary.to_csv(summary_path, index=False)
    config_path = research.output_dir / "provider_market_data_imbalance_research_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_research_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "rerun_provider_imbalance_research"
    assert report.action_queue.loc[0, "next_gate"] == "run-provider-market-data-imbalance-research"


def test_provider_market_data_imbalance_evidence_blocks_missing_provider_profile(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    summary_path = research.output_dir / "provider_market_data_imbalance_research_summary.csv"
    research_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        research_summary.loc[0, column] = ""
    research_summary.loc[0, "provider_profile_matches_session"] = False
    research_summary.loc[0, "provider_profile_matches_bundle"] = False
    research_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    research_summary.to_csv(summary_path, index=False)
    config_path = research.output_dir / "provider_market_data_imbalance_research_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("provider_profile", None),
            payload["capture_bundle"].pop("capture_bundle_provider_profile", None),
        ),
    )

    report = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_research_provider_profile_carried" in failed
    assert "provider_research_provider_profile_matches_session" in failed
    assert "provider_research_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "rerun_provider_imbalance_research"
    assert report.action_queue.loc[0, "next_gate"] == "run-provider-market-data-imbalance-research"


def test_provider_market_data_imbalance_evidence_blocks_unready_research(tmp_path):
    smoke = _write_synthetic_smoke_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        smoke.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )

    report = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not research.ready
    assert not report.ready
    assert "provider_imbalance_research_ready" in failed
    assert "strategy_evidence_review_ready" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "run-provider-market-data-imbalance-research"


def test_cli_provider_market_data_imbalance_evidence_accepts_ready_research(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    out_dir = tmp_path / "cli_provider_imbalance_evidence"

    code = main(
        [
            "review-provider-market-data-imbalance-evidence",
            "--provider-research-dir",
            str(research.output_dir),
            "--out",
            str(out_dir),
            "--allow-dirty-git",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_evidence_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "pipeline-imbalance-launch"


def test_provider_market_data_imbalance_launch_builds_from_ready_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    out_dir = tmp_path / "provider_imbalance_launch"

    report = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_launch_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_launch_action_queue.csv")
    launch_summary = pd.read_csv(out_dir / "imbalance_launch_pipeline" / "imbalance_launch_pipeline_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "provider_evidence_ready"])
    assert bool(summary.loc[0, "launch_pipeline_ready"])
    assert summary.loc[0, "strategy"] == "imbalance"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "next_gate"] == "review-strategy-evidence"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "review-strategy-evidence"
    assert bool(launch_summary.loc[0, "ready"])
    assert manifest["run_type"] == "provider_market_data_imbalance_launch_packet"
    assert "imbalance_launch_pipeline" in manifest["inputs"]


def test_provider_market_data_imbalance_launch_carries_capture_bundle_provenance(tmp_path):
    evidence, bundle_path = _write_bundle_linked_real_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    out_dir = tmp_path / "provider_imbalance_launch"

    report = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_launch_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_launch_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["capture_bundle"]["source_credential_env_template_sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_evidence"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_evidence"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_evidence"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_evidence"]["source_live_fetch_contract_available"] is True
    assert config["provider_evidence"]["exchange"] == "NFO"
    assert config["provider_evidence"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_evidence"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_evidence"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_evidence"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_evidence"]["provider_profile_matches_bundle"] is True
    assert config["provider_evidence"]["provider_capture_command_count"] == 2
    assert config["provider_evidence"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook


def test_provider_market_data_imbalance_launch_blocks_missing_adapter_execution_contract(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    summary_path = review.output_dir / "provider_market_data_imbalance_evidence_summary.csv"
    evidence_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        evidence_summary.loc[0, column] = ""
    evidence_summary.loc[0, "adapter_contract_values_stored"] = True
    evidence_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    evidence_summary.to_csv(summary_path, index=False)
    config_path = review.output_dir / "provider_market_data_imbalance_evidence_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    out_dir = tmp_path / "provider_imbalance_launch"
    report = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchConfig(require_reviewed_schema=False, reference_price=100.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert report.launch is None
    assert "provider_evidence_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "review_provider_imbalance_evidence"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-evidence"
    assert not (out_dir / "imbalance_launch_pipeline" / "imbalance_launch_pipeline_summary.csv").exists()


def test_provider_market_data_imbalance_launch_blocks_missing_provider_profile(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    summary_path = review.output_dir / "provider_market_data_imbalance_evidence_summary.csv"
    evidence_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        evidence_summary.loc[0, column] = ""
    evidence_summary.loc[0, "provider_profile_matches_session"] = False
    evidence_summary.loc[0, "provider_profile_matches_bundle"] = False
    evidence_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    evidence_summary.to_csv(summary_path, index=False)
    config_path = review.output_dir / "provider_market_data_imbalance_evidence_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("provider_profile", None),
            payload.pop("live_session_provider_profile", None),
            payload["capture_bundle"].pop("capture_bundle_provider_profile", None),
            payload["capture_bundle"].pop("provider_profile", None),
        ),
    )

    out_dir = tmp_path / "provider_imbalance_launch"
    report = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchConfig(require_reviewed_schema=False, reference_price=100.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert report.launch is None
    assert "provider_evidence_provider_profile_carried" in failed
    assert "provider_evidence_provider_profile_matches_session" in failed
    assert "provider_evidence_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "review_provider_imbalance_evidence"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-evidence"
    assert not (out_dir / "imbalance_launch_pipeline" / "imbalance_launch_pipeline_summary.csv").exists()


def test_provider_market_data_imbalance_launch_blocks_unready_evidence(tmp_path):
    smoke = _write_synthetic_smoke_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        smoke.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )

    report = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(require_reviewed_schema=False, reference_price=100.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert not report.ready
    assert "provider_imbalance_evidence_ready" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-evidence"


def test_cli_provider_market_data_imbalance_launch_accepts_ready_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    out_dir = tmp_path / "cli_provider_imbalance_launch"

    code = main(
        [
            "pipeline-provider-market-data-imbalance-launch",
            "--provider-evidence-dir",
            str(review.output_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--route-tag",
            "imbalance_shadow",
            "--instrument-id",
            "NIFTY-I",
            "--reference-price",
            "100",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--max-orders",
            "2",
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_launch_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "review-strategy-evidence"


def test_provider_market_data_imbalance_launch_evidence_reviews_full_imbalance_profile(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    out_dir = tmp_path / "provider_imbalance_launch_evidence"

    report = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_launch_evidence_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_launch_evidence_action_queue.csv")
    strategy_summary = pd.read_csv(out_dir / "strategy_evidence" / "strategy_evidence_summary.csv")
    items = pd.read_csv(out_dir / "strategy_evidence" / "strategy_evidence_items.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "provider_launch_ready"])
    assert bool(summary.loc[0, "strategy_evidence_ready"])
    assert summary.loc[0, "evidence_profile"] == "imbalance"
    assert summary.loc[0, "next_gate"] == "score-strategy-readiness"
    assert strategy_summary.loc[0, "evidence_profile"] == "imbalance"
    assert set(items["required_run_type"]) == {
        "imbalance_edge_walkforward",
        "imbalance_replay_walkforward",
        "promotion_report",
        "imbalance_research_pipeline",
        "imbalance_order_plan",
        "imbalance_launch_pipeline",
    }
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "score-strategy-readiness"
    assert manifest["run_type"] == "provider_market_data_imbalance_launch_evidence_review"


def test_provider_market_data_imbalance_launch_evidence_carries_capture_bundle_provenance(tmp_path):
    evidence, bundle_path = _write_bundle_linked_real_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    out_dir = tmp_path / "provider_imbalance_launch_evidence"

    report = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_launch_evidence_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_launch_evidence_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["capture_bundle"]["source_credential_env_template_sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_launch"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_launch"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_launch"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_launch"]["source_live_fetch_contract_available"] is True
    assert config["provider_launch"]["exchange"] == "NFO"
    assert config["provider_launch"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_launch"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_launch"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_launch"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_launch"]["provider_profile_matches_bundle"] is True
    assert config["provider_launch"]["provider_capture_command_count"] == 2
    assert config["provider_launch"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook


def test_provider_market_data_imbalance_launch_evidence_blocks_missing_adapter_execution_contract(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    summary_path = launch.output_dir / "provider_market_data_imbalance_launch_summary.csv"
    launch_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        launch_summary.loc[0, column] = ""
    launch_summary.loc[0, "adapter_contract_values_stored"] = True
    launch_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    launch_summary.to_csv(summary_path, index=False)
    config_path = launch.output_dir / "provider_market_data_imbalance_launch_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )
    out_dir = tmp_path / "provider_imbalance_launch_evidence"

    report = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_launch_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "build_provider_imbalance_launch_packet"
    assert report.action_queue.loc[0, "next_gate"] == "pipeline-provider-market-data-imbalance-launch"


def test_provider_market_data_imbalance_launch_evidence_blocks_missing_provider_profile(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    summary_path = launch.output_dir / "provider_market_data_imbalance_launch_summary.csv"
    launch_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        launch_summary.loc[0, column] = ""
    launch_summary.loc[0, "provider_profile_matches_session"] = False
    launch_summary.loc[0, "provider_profile_matches_bundle"] = False
    launch_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    launch_summary.to_csv(summary_path, index=False)
    config_path = launch.output_dir / "provider_market_data_imbalance_launch_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("provider_profile", None),
            payload.pop("live_session_provider_profile", None),
            payload["capture_bundle"].pop("capture_bundle_provider_profile", None),
            payload["capture_bundle"].pop("provider_profile", None),
        ),
    )
    out_dir = tmp_path / "provider_imbalance_launch_evidence"

    report = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_launch_provider_profile_carried" in failed
    assert "provider_launch_provider_profile_matches_session" in failed
    assert "provider_launch_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "build_provider_imbalance_launch_packet"
    assert report.action_queue.loc[0, "next_gate"] == "pipeline-provider-market-data-imbalance-launch"


def test_provider_market_data_imbalance_launch_evidence_blocks_unready_launch(tmp_path):
    smoke = _write_synthetic_smoke_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        smoke.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(require_reviewed_schema=False, reference_price=100.0),
    )

    report = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        tmp_path / "provider_imbalance_launch_evidence",
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not launch.ready
    assert not report.ready
    assert "provider_imbalance_launch_ready" in failed
    assert "strategy_evidence_review_ready" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "pipeline-provider-market-data-imbalance-launch"


def test_cli_provider_market_data_imbalance_launch_evidence_accepts_ready_launch(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(
            require_reviewed_schema=False,
            adapter="arrow_money",
            route_tag="imbalance_shadow",
            instrument_id="NIFTY-I",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000.0,
            max_orders=2,
        ),
    )
    out_dir = tmp_path / "cli_provider_imbalance_launch_evidence"

    code = main(
        [
            "review-provider-market-data-imbalance-launch-evidence",
            "--provider-launch-dir",
            str(launch.output_dir),
            "--out",
            str(out_dir),
            "--allow-dirty-git",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_launch_evidence_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "score-strategy-readiness"


def test_provider_market_data_imbalance_scorecard_accepts_ready_launch_evidence(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    out_dir = tmp_path / "provider_imbalance_scorecard"

    report = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_scorecard_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_scorecard_action_queue.csv")
    scorecard = pd.read_csv(out_dir / "scorecard" / "strategy_scorecard.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "launch_evidence_ready"])
    assert bool(summary.loc[0, "scorecard_ready"])
    assert summary.loc[0, "profile"] == "imbalance"
    assert summary.loc[0, "strategy"] == "imbalance"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "readiness_score"] == 1.0
    assert summary.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"
    assert scorecard.loc[0, "profile"] == "imbalance"
    assert bool(scorecard.loc[0, "ready"])
    assert manifest["run_type"] == "provider_market_data_imbalance_scorecard"


def test_provider_market_data_imbalance_scorecard_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    out_dir = tmp_path / "provider_imbalance_scorecard"

    report = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_scorecard_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_scorecard_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_launch_evidence"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_launch_evidence"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_launch_evidence"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["provider_launch_evidence"]["source_live_fetch_contract_available"] is True
    assert config["provider_launch_evidence"]["exchange"] == "NFO"
    assert config["provider_launch_evidence"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_launch_evidence"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_launch_evidence"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_launch_evidence"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_launch_evidence"]["provider_profile_matches_bundle"] is True
    assert config["provider_launch_evidence"]["provider_capture_command_count"] == 2
    assert config["provider_launch_evidence"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook


def test_provider_market_data_imbalance_scorecard_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    summary_path = launch_evidence.output_dir / "provider_market_data_imbalance_launch_evidence_summary.csv"
    evidence_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        evidence_summary.loc[0, column] = ""
    evidence_summary.loc[0, "adapter_contract_values_stored"] = True
    evidence_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    evidence_summary.to_csv(summary_path, index=False)
    config_path = launch_evidence.output_dir / "provider_market_data_imbalance_launch_evidence_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )
    out_dir = tmp_path / "provider_imbalance_scorecard"

    report = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "launch_evidence_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "review_full_provider_imbalance_launch_evidence"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-launch-evidence"


def test_provider_market_data_imbalance_scorecard_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    summary_path = launch_evidence.output_dir / "provider_market_data_imbalance_launch_evidence_summary.csv"
    evidence_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        evidence_summary.loc[0, column] = ""
    evidence_summary.loc[0, "provider_profile_matches_session"] = False
    evidence_summary.loc[0, "provider_profile_matches_bundle"] = False
    evidence_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    evidence_summary.to_csv(summary_path, index=False)
    config_path = launch_evidence.output_dir / "provider_market_data_imbalance_launch_evidence_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("provider_profile", None),
            payload.pop("live_session_provider_profile", None),
            payload["capture_bundle"].pop("capture_bundle_provider_profile", None),
            payload["capture_bundle"].pop("provider_profile", None),
        ),
    )
    out_dir = tmp_path / "provider_imbalance_scorecard"

    report = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "launch_evidence_provider_profile_carried" in failed
    assert "launch_evidence_provider_profile_matches_session" in failed
    assert "launch_evidence_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "review_full_provider_imbalance_launch_evidence"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-launch-evidence"


def test_provider_market_data_imbalance_scorecard_blocks_unready_launch_evidence(tmp_path):
    smoke = _write_synthetic_smoke_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        smoke.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(require_reviewed_schema=False, reference_price=100.0),
    )
    launch_evidence = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        tmp_path / "provider_imbalance_launch_evidence",
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )

    report = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not launch_evidence.ready
    assert not report.ready
    assert "provider_imbalance_launch_evidence_ready" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-launch-evidence"


def test_cli_provider_market_data_imbalance_scorecard_accepts_ready_launch_evidence(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_scorecard"

    code = main(
        [
            "score-provider-market-data-imbalance-readiness",
            "--provider-launch-evidence-dir",
            str(launch_evidence.output_dir),
            "--out",
            str(out_dir),
            "--allow-dirty-git",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_scorecard_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"


def test_provider_market_data_imbalance_route_readiness_blocks_missing_ops_evidence(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    out_dir = tmp_path / "provider_imbalance_route_readiness"

    report = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_readiness_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_route_readiness_action_queue.csv")
    route_summary = pd.read_csv(out_dir / "route_readiness" / "route_readiness_summary.csv")
    route_pairs = pd.read_csv(out_dir / "route_readiness" / "route_readiness_pairs.csv")
    provider_portability_config = json.loads(
        (out_dir / "provider_market_data_imbalance_market_portability_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    provider_ops_gate = (
        "review-strategy-evidence --profile provider_market_data_imbalance_ops_launch --require-file-inputs"
    )
    assert not report.ready
    assert "route_readiness_ready" in failed
    assert bool(summary.loc[0, "provider_launch_evidence_ready"])
    assert not bool(summary.loc[0, "route_readiness_ready"])
    assert summary.loc[0, "next_gate"] == provider_ops_gate
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "next_gate"] == provider_ops_gate
    assert not bool(route_summary.loc[0, "ready"])
    assert route_summary.loc[0, "next_gate"] == provider_ops_gate
    assert route_pairs.loc[0, "ops_evidence_profile"] == "provider_imbalance_ops_launch"
    assert route_pairs.loc[0, "next_gate"] == provider_ops_gate
    assert provider_portability_config["ready_pairs"][0]["ops_evidence_profile"] == "provider_imbalance_ops_launch"
    assert provider_portability_config["ready_pairs"][0]["ops_evidence_gate"] == provider_ops_gate
    assert manifest["run_type"] == "provider_market_data_imbalance_route_readiness"
    assert "market_portability" in manifest["inputs"]
    assert manifest["inputs"]["market_portability_config"]["path"].endswith(
        "provider_market_data_imbalance_market_portability_config.json"
    )
    assert "route_readiness" in manifest["inputs"]


def test_provider_market_data_imbalance_route_readiness_accepts_ready_ops_evidence(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    out_dir = tmp_path / "provider_imbalance_route_readiness"

    report = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        out_dir,
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_readiness_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_route_readiness_action_queue.csv")
    route_summary = pd.read_csv(out_dir / "route_readiness" / "route_readiness_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "provider_launch_evidence_ready"])
    assert bool(summary.loc[0, "route_readiness_ready"])
    assert summary.loc[0, "strategy"] == "microprice_imbalance"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert int(summary.loc[0, "route_ready_pairs"]) == 1
    assert int(summary.loc[0, "gap_pairs"]) == 0
    assert summary.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"
    assert bool(route_summary.loc[0, "ready"])
    assert manifest["run_type"] == "provider_market_data_imbalance_route_readiness"
    assert "strategy_evidence" in manifest["inputs"]
    assert "ops_evidence_1" in manifest["inputs"]


def test_cli_provider_market_data_imbalance_route_readiness_accepts_ready_ops_evidence(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_route_readiness"

    code = main(
        [
            "review-provider-market-data-imbalance-route-readiness",
            "--provider-launch-evidence-dir",
            str(launch_evidence.output_dir),
            "--ops-evidence",
            str(ops_evidence),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_readiness_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"


def test_provider_market_data_imbalance_scaleup_plans_from_ready_scorecard(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    out_dir = tmp_path / "provider_imbalance_scaleup"

    report = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        out_dir,
        config=ProviderMarketDataImbalanceScaleupConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_scaleup_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_scaleup_action_queue.csv")
    scaleup_summary = pd.read_csv(out_dir / "scaleup" / "scaleup_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "scorecard_ready"])
    assert bool(summary.loc[0, "scaleup_ready"])
    assert summary.loc[0, "strategy"] == "imbalance"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "next_gate"] == "build-provider-market-data-imbalance-runtime-telemetry"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "build-provider-market-data-imbalance-runtime-telemetry"
    assert bool(scaleup_summary.loc[0, "ready"])
    assert scaleup_summary.loc[0, "strategy"] == "imbalance"
    assert manifest["run_type"] == "provider_market_data_imbalance_scaleup_plan"
    assert "scaleup" in manifest["inputs"]


def test_provider_market_data_imbalance_scaleup_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    out_dir = tmp_path / "provider_imbalance_scaleup"

    report = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        out_dir,
        config=ProviderMarketDataImbalanceScaleupConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_scaleup_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["scorecard"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["scorecard"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["scorecard"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["scorecard"]["source_live_fetch_contract_available"] is True
    assert config["scorecard"]["exchange"] == "NFO"
    assert config["scorecard"]["capture_bundle_metadata_matches_session"] is True
    assert config["scorecard"]["adapter_contract_provider"] == "arrow_money"
    assert config["scorecard"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["scorecard"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["scorecard"]["provider_profile_matches_bundle"] is True
    assert config["scorecard"]["provider_capture_command_count"] == 2
    assert config["scorecard"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_scaleup_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    summary_path = scorecard.output_dir / "provider_market_data_imbalance_scorecard_summary.csv"
    scorecard_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        scorecard_summary.loc[0, column] = ""
    scorecard_summary.loc[0, "adapter_contract_values_stored"] = True
    scorecard_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    scorecard_summary.to_csv(summary_path, index=False)
    config_path = scorecard.output_dir / "provider_market_data_imbalance_scorecard_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    out_dir = tmp_path / "provider_imbalance_scaleup"

    report = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        out_dir,
        config=ProviderMarketDataImbalanceScaleupConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "scorecard_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "score_provider_imbalance_readiness"
    assert report.action_queue.loc[0, "next_gate"] == "score-provider-market-data-imbalance-readiness"


def test_provider_market_data_imbalance_scaleup_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    summary_path = scorecard.output_dir / "provider_market_data_imbalance_scorecard_summary.csv"
    scorecard_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        scorecard_summary.loc[0, column] = ""
    scorecard_summary.loc[0, "provider_profile_matches_session"] = False
    scorecard_summary.loc[0, "provider_profile_matches_bundle"] = False
    scorecard_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    scorecard_summary.to_csv(summary_path, index=False)

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract", {})
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle", {})
        if isinstance(bundle, dict):
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract", {})
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(
        scorecard.output_dir / "provider_market_data_imbalance_scorecard_config.json",
        remove_provider_profile,
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    out_dir = tmp_path / "provider_imbalance_scaleup"

    report = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        out_dir,
        config=ProviderMarketDataImbalanceScaleupConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "scorecard_provider_profile_carried" in failed
    assert "scorecard_provider_profile_matches_session" in failed
    assert "scorecard_provider_profile_matches_bundle" in failed
    assert "scorecard_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "score_provider_imbalance_readiness"
    assert report.action_queue.loc[0, "next_gate"] == "score-provider-market-data-imbalance-readiness"


def test_provider_market_data_imbalance_scaleup_accepts_provider_route_readiness_root(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    out_dir = tmp_path / "provider_imbalance_scaleup"

    report = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        out_dir,
        route_readiness_dir=route_readiness.output_dir,
        config=ProviderMarketDataImbalanceScaleupConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_scaleup_summary.csv")
    scaleup_summary = pd.read_csv(out_dir / "scaleup" / "scaleup_summary.csv")
    config = json.loads((out_dir / "provider_market_data_imbalance_scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    nested_route_dir = route_readiness.output_dir / "route_readiness"
    assert report.ready
    assert Path(summary.loc[0, "route_readiness_dir"]) == nested_route_dir
    assert Path(summary.loc[0, "provider_route_readiness_wrapper_dir"]) == route_readiness.output_dir
    assert bool(summary.loc[0, "route_readiness_provided"])
    assert bool(summary.loc[0, "route_readiness_ready"])
    assert int(summary.loc[0, "route_readiness_route_ready_pairs"]) == 1
    assert int(summary.loc[0, "route_readiness_gap_pairs"]) == 0
    assert bool(summary.loc[0, "route_readiness_ops_launch_controls_present"])
    assert bool(scaleup_summary.loc[0, "route_readiness_provided"])
    assert bool(scaleup_summary.loc[0, "route_readiness_ready"])
    assert int(scaleup_summary.loc[0, "route_readiness_gap_pairs"]) == 0
    assert config["route_readiness_inputs"]["route_readiness_dir"] == str(nested_route_dir)
    assert config["route_readiness_inputs"]["provider_route_readiness_wrapper_dir"] == str(route_readiness.output_dir)
    assert "provider_route_readiness_wrapper" in manifest["inputs"]


def test_provider_market_data_imbalance_scaleup_blocks_unready_scorecard(tmp_path):
    smoke = _write_synthetic_smoke_evidence(tmp_path)
    research = write_provider_market_data_imbalance_research(
        smoke.output_dir,
        tmp_path / "provider_imbalance_research",
        config=_passing_config(),
    )
    review = write_provider_market_data_imbalance_evidence_review(
        research.output_dir,
        tmp_path / "provider_imbalance_evidence",
        config=ProviderMarketDataImbalanceEvidenceConfig(allow_dirty_git=True),
    )
    launch = write_provider_market_data_imbalance_launch_packet(
        review.output_dir,
        tmp_path / "provider_imbalance_launch",
        config=ProviderMarketDataImbalanceLaunchConfig(require_reviewed_schema=False, reference_price=100.0),
    )
    launch_evidence = write_provider_market_data_imbalance_launch_evidence_review(
        launch.output_dir,
        tmp_path / "provider_imbalance_launch_evidence",
        config=ProviderMarketDataImbalanceLaunchEvidenceConfig(allow_dirty_git=True),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow_dir = tmp_path / "provider_imbalance_shadow_comparison"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    report = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow_dir,
        tmp_path / "provider_imbalance_scaleup",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not scorecard.ready
    assert not report.ready
    assert "provider_imbalance_scorecard_ready" in failed
    assert "shadow_comparison_summary_readable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "score-provider-market-data-imbalance-readiness"
    assert not (report.output_dir / "scaleup" / "scaleup_summary.csv").exists()


def test_cli_provider_market_data_imbalance_scaleup_accepts_ready_scorecard(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    out_dir = tmp_path / "cli_provider_imbalance_scaleup"

    code = main(
        [
            "plan-provider-market-data-imbalance-scaleup",
            "--scorecard",
            str(scorecard.output_dir),
            "--shadow-comparison",
            str(shadow),
            "--out",
            str(out_dir),
            "--allowed-adapter",
            "arrow_money",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_scaleup_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "build-provider-market-data-imbalance-runtime-telemetry"


def test_provider_market_data_imbalance_runtime_telemetry_builds_from_ready_scaleup(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    out_dir = tmp_path / "provider_imbalance_runtime_telemetry"

    report = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        out_dir,
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_telemetry_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_telemetry_action_queue.csv")
    runtime_summary = pd.read_csv(out_dir / "runtime_telemetry" / "runtime_telemetry_summary.csv")
    sources = pd.read_csv(out_dir / "runtime_telemetry" / "runtime_telemetry_sources.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "provider_scaleup_ready"])
    assert bool(summary.loc[0, "runtime_telemetry_ready"])
    assert summary.loc[0, "strategy"] == "imbalance"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-guard"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-guard"
    assert bool(runtime_summary.loc[0, "ready"])
    assert runtime_summary.loc[0, "strategy"] == "imbalance"
    assert bool(sources.loc[sources["source"] == "export_summary", "provided"].iloc[0])
    assert bool(sources.loc[sources["source"] == "upload_summary", "provided"].iloc[0])
    assert manifest["run_type"] == "provider_market_data_imbalance_runtime_telemetry_snapshot"
    assert "runtime_telemetry" in manifest["inputs"]


def test_provider_market_data_imbalance_runtime_telemetry_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    out_dir = tmp_path / "provider_imbalance_runtime_telemetry"

    report = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        out_dir,
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_runtime_telemetry_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_runtime_telemetry_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_scaleup"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_scaleup"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_scaleup"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_scaleup"]["source_live_fetch_contract_available"] is True
    assert config["provider_scaleup"]["exchange"] == "NFO"
    assert config["provider_scaleup"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_scaleup"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_scaleup"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_scaleup"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_scaleup"]["provider_profile_matches_bundle"] is True
    assert config["provider_scaleup"]["provider_capture_command_count"] == 2
    assert config["provider_scaleup"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_runtime_telemetry_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    summary_path = scaleup.output_dir / "provider_market_data_imbalance_scaleup_summary.csv"
    scaleup_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        scaleup_summary.loc[0, column] = ""
    scaleup_summary.loc[0, "adapter_contract_values_stored"] = True
    scaleup_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    scaleup_summary.to_csv(summary_path, index=False)
    config_path = scaleup.output_dir / "provider_market_data_imbalance_scaleup_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )
    out_dir = tmp_path / "provider_imbalance_runtime_telemetry"

    report = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        out_dir,
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_scaleup_adapter_execution_contract_carried" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_scaleup"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"


def test_provider_market_data_imbalance_runtime_telemetry_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    summary_path = scaleup.output_dir / "provider_market_data_imbalance_scaleup_summary.csv"
    scaleup_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        scaleup_summary.loc[0, column] = ""
    scaleup_summary.loc[0, "provider_profile_matches_session"] = False
    scaleup_summary.loc[0, "provider_profile_matches_bundle"] = False
    scaleup_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    scaleup_summary.to_csv(summary_path, index=False)

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract", {})
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle", {})
        if isinstance(bundle, dict):
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract", {})
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(
        scaleup.output_dir / "provider_market_data_imbalance_scaleup_config.json",
        remove_provider_profile,
    )
    out_dir = tmp_path / "provider_imbalance_runtime_telemetry"

    report = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        out_dir,
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_scaleup_provider_profile_carried" in failed
    assert "provider_scaleup_provider_profile_matches_session" in failed
    assert "provider_scaleup_provider_profile_matches_bundle" in failed
    assert "provider_scaleup_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_scaleup"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"


def test_provider_market_data_imbalance_runtime_telemetry_blocks_unready_scaleup(tmp_path):
    scaleup_dir = tmp_path / "provider_imbalance_scaleup"
    scaleup_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "scaleup_ready": False,
                "scaleup_dir": "",
                "launch_pipeline_dir": "",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(scaleup_dir / "provider_market_data_imbalance_scaleup_summary.csv", index=False)

    report = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_imbalance_scaleup_ready" in failed
    assert "nested_scaleup_config_exists" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-scaleup"
    assert not (report.output_dir / "runtime_telemetry" / "runtime_telemetry_summary.csv").exists()


def test_cli_provider_market_data_imbalance_runtime_telemetry_accepts_ready_scaleup(tmp_path):
    launch_evidence = _write_ready_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    out_dir = tmp_path / "cli_provider_imbalance_runtime_telemetry"

    code = main(
        [
            "build-provider-market-data-imbalance-runtime-telemetry",
            "--scaleup",
            str(scaleup.output_dir),
            "--out",
            str(out_dir),
            "--snapshot-ts-ns",
            "1000000",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_telemetry_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-guard"


def test_provider_market_data_imbalance_runtime_guard_monitors_ready_telemetry(tmp_path):
    runtime_telemetry = _write_ready_provider_imbalance_runtime_telemetry(tmp_path)
    out_dir = tmp_path / "provider_imbalance_runtime_guard"

    report = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        out_dir,
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_guard_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_guard_action_queue.csv")
    guard_summary = pd.read_csv(out_dir / "runtime_guard" / "runtime_guard_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert not report.halted
    assert bool(summary.loc[0, "provider_runtime_telemetry_ready"])
    assert bool(summary.loc[0, "runtime_guard_evaluated"])
    assert bool(summary.loc[0, "runtime_guard_continue"])
    assert summary.loc[0, "guard_action"] == "continue"
    assert summary.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-session"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-session"
    assert guard_summary.loc[0, "guard_action"] == "continue"
    assert manifest["run_type"] == "provider_market_data_imbalance_runtime_guard"
    assert "runtime_guard" in manifest["inputs"]


def test_provider_market_data_imbalance_runtime_guard_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_runtime_guard"

    report = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        out_dir,
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_runtime_guard_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_runtime_guard_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert not report.halted
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["provider_runtime_telemetry"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_runtime_telemetry"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_runtime_telemetry"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["provider_runtime_telemetry"]["source_live_fetch_contract_available"] is True
    assert config["provider_runtime_telemetry"]["exchange"] == "NFO"
    assert config["provider_runtime_telemetry"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_runtime_telemetry"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_runtime_telemetry"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_runtime_telemetry"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_runtime_telemetry"]["provider_profile_matches_bundle"] is True
    assert config["provider_runtime_telemetry"]["provider_capture_command_count"] == 2
    assert config["provider_runtime_telemetry"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_runtime_guard_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    summary_path = runtime_telemetry.output_dir / "provider_market_data_imbalance_runtime_telemetry_summary.csv"
    provider_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        provider_summary.loc[0, column] = ""
    provider_summary.loc[0, "adapter_contract_values_stored"] = True
    provider_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    provider_summary.to_csv(summary_path, index=False)
    config_path = runtime_telemetry.output_dir / "provider_market_data_imbalance_runtime_telemetry_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_runtime_telemetry_adapter_execution_contract_carried" in failed
    assert "provider_runtime_telemetry_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_runtime_telemetry"
    assert report.action_queue.loc[0, "next_gate"] == "build-provider-market-data-imbalance-runtime-telemetry"


def test_provider_market_data_imbalance_runtime_guard_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    summary_path = runtime_telemetry.output_dir / "provider_market_data_imbalance_runtime_telemetry_summary.csv"
    provider_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        provider_summary.loc[0, column] = ""
    provider_summary.loc[0, "provider_profile_matches_session"] = False
    provider_summary.loc[0, "provider_profile_matches_bundle"] = False
    provider_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    provider_summary.to_csv(summary_path, index=False)

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract", {})
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle", {})
        if isinstance(bundle, dict):
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract", {})
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(
        runtime_telemetry.output_dir / "provider_market_data_imbalance_runtime_telemetry_config.json",
        remove_provider_profile,
    )

    report = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_runtime_telemetry_provider_profile_carried" in failed
    assert "provider_runtime_telemetry_provider_profile_matches_session" in failed
    assert "provider_runtime_telemetry_provider_profile_matches_bundle" in failed
    assert "provider_runtime_telemetry_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_runtime_telemetry"
    assert report.action_queue.loc[0, "next_gate"] == "build-provider-market-data-imbalance-runtime-telemetry"


def test_provider_market_data_imbalance_runtime_guard_blocks_unready_telemetry(tmp_path):
    telemetry_dir = tmp_path / "provider_imbalance_runtime_telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "runtime_telemetry_ready": False,
                "scaleup_dir": "",
                "runtime_telemetry_dir": "",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(telemetry_dir / "provider_market_data_imbalance_runtime_telemetry_summary.csv", index=False)

    report = write_provider_market_data_imbalance_runtime_guard(
        telemetry_dir,
        tmp_path / "provider_imbalance_runtime_guard",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_runtime_telemetry_ready" in failed
    assert "nested_scaleup_config_exists" in failed
    assert "runtime_telemetry_csv_exists" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "build-provider-market-data-imbalance-runtime-telemetry"
    assert not (report.output_dir / "runtime_guard" / "runtime_guard_summary.csv").exists()


def test_provider_market_data_imbalance_runtime_guard_surfaces_guard_halts(tmp_path):
    runtime_telemetry = _write_ready_provider_imbalance_runtime_telemetry(tmp_path, snapshot_ts_ns=1_000_000)
    out_dir = tmp_path / "provider_imbalance_runtime_guard"

    report = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        out_dir,
        as_of_ts_ns=1_000_002,
        max_telemetry_age_ns=1,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_guard_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_guard_action_queue.csv")
    guard_checks = pd.read_csv(out_dir / "runtime_guard" / "runtime_guard_checks.csv")
    failed_guard_checks = set(guard_checks.loc[~guard_checks["passed"].astype(bool), "check"])
    assert report.ready
    assert report.halted
    assert summary.loc[0, "guard_action"] == "halt"
    assert summary.loc[0, "next_gate"] == "plan-halt-response"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "action"] == "execute_provider_imbalance_halt_response"
    assert "runtime_telemetry_age_ns" in failed_guard_checks


def test_cli_provider_market_data_imbalance_runtime_guard_accepts_ready_telemetry(tmp_path):
    runtime_telemetry = _write_ready_provider_imbalance_runtime_telemetry(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_runtime_guard"

    code = main(
        [
            "monitor-provider-market-data-imbalance-runtime-guard",
            "--runtime-telemetry",
            str(runtime_telemetry.output_dir),
            "--out",
            str(out_dir),
            "--as-of-ts-ns",
            "1000000",
            "--fail-on-breach",
            "--fail-on-halt",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_guard_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "guard_action"] == "continue"
    assert summary.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-session"


def test_provider_market_data_imbalance_runtime_session_monitors_ready_guard(tmp_path):
    runtime_guard = _write_ready_provider_imbalance_runtime_guard(tmp_path)
    out_dir = tmp_path / "provider_imbalance_runtime_session"

    report = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        out_dir,
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_session_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_session_action_queue.csv")
    session_summary = pd.read_csv(out_dir / "runtime_session" / "runtime_session_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert not report.halted
    assert bool(summary.loc[0, "provider_runtime_guard_ready"])
    assert bool(summary.loc[0, "runtime_session_evaluated"])
    assert bool(summary.loc[0, "runtime_session_continue"])
    assert summary.loc[0, "guard_action"] == "continue"
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"
    assert bool(session_summary.loc[0, "ready"])
    assert session_summary.loc[0, "strategy"] == "imbalance"
    assert manifest["run_type"] == "provider_market_data_imbalance_runtime_session"
    assert "runtime_session" in manifest["inputs"]


def test_provider_market_data_imbalance_runtime_session_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_runtime_session"

    report = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        out_dir,
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_runtime_session_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_runtime_session_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert not report.halted
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_runtime_guard"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_runtime_guard"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_runtime_guard"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_runtime_guard"]["source_live_fetch_contract_available"] is True
    assert config["provider_runtime_guard"]["exchange"] == "NFO"
    assert config["provider_runtime_guard"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_runtime_guard"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_runtime_guard"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_runtime_guard"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_runtime_guard"]["provider_profile_matches_bundle"] is True
    assert config["provider_runtime_guard"]["provider_capture_command_count"] == 2
    assert config["provider_runtime_guard"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_runtime_session_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    summary_path = runtime_guard.output_dir / "provider_market_data_imbalance_runtime_guard_summary.csv"
    guard_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        guard_summary.loc[0, column] = ""
    guard_summary.loc[0, "adapter_contract_values_stored"] = True
    guard_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    guard_summary.to_csv(summary_path, index=False)
    config_path = runtime_guard.output_dir / "provider_market_data_imbalance_runtime_guard_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_runtime_guard_adapter_execution_contract_carried" in failed
    assert "provider_runtime_guard_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_runtime_guard"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-guard"


def test_provider_market_data_imbalance_runtime_session_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    summary_path = runtime_guard.output_dir / "provider_market_data_imbalance_runtime_guard_summary.csv"
    guard_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        guard_summary.loc[0, column] = ""
    guard_summary.loc[0, "provider_profile_matches_session"] = False
    guard_summary.loc[0, "provider_profile_matches_bundle"] = False
    guard_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    guard_summary.to_csv(summary_path, index=False)
    config_path = runtime_guard.output_dir / "provider_market_data_imbalance_runtime_guard_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_runtime_guard_provider_profile_carried" in failed
    assert "provider_runtime_guard_provider_profile_matches_session" in failed
    assert "provider_runtime_guard_provider_profile_matches_bundle" in failed
    assert "provider_runtime_guard_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_runtime_guard"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-guard"


def test_provider_market_data_imbalance_runtime_session_blocks_unready_guard(tmp_path):
    guard_dir = tmp_path / "provider_imbalance_runtime_guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "provider_runtime_telemetry_dir": "",
                "scaleup_dir": "",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(guard_dir / "provider_market_data_imbalance_runtime_guard_summary.csv", index=False)
    (guard_dir / "provider_market_data_imbalance_runtime_guard_config.json").write_text(
        json.dumps({"summary": {}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_runtime_session(
        guard_dir,
        tmp_path / "provider_imbalance_runtime_session",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_runtime_guard_ready" in failed
    assert "provider_runtime_telemetry_dir_exists" in failed
    assert "nested_scaleup_config_exists" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-guard"
    assert not (report.output_dir / "runtime_session" / "runtime_session_summary.csv").exists()


def test_cli_provider_market_data_imbalance_runtime_session_accepts_ready_guard(tmp_path):
    runtime_guard = _write_ready_provider_imbalance_runtime_guard(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_runtime_session"

    code = main(
        [
            "monitor-provider-market-data-imbalance-runtime-session",
            "--runtime-guard",
            str(runtime_guard.output_dir),
            "--out",
            str(out_dir),
            "--as-of-ts-ns",
            "1000000",
            "--fail-on-breach",
            "--fail-on-halt",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_runtime_session_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "guard_action"] == "continue"
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"


def test_provider_market_data_imbalance_broker_readiness_reviews_ready_session(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    out_dir = tmp_path / "provider_imbalance_broker_readiness"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_action_queue.csv")
    broker_summary = pd.read_csv(out_dir / "broker_readiness" / "broker_readiness_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "provider_runtime_session_ready"])
    assert bool(summary.loc[0, "broker_readiness_ready"])
    assert bool(broker_summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"
    assert manifest["run_type"] == "provider_market_data_imbalance_broker_readiness"
    assert "broker_readiness" in manifest["inputs"]
    assert "runtime_session" in manifest["inputs"]
    assert "order_export" in manifest["inputs"]
    assert "upload_pack" in manifest["inputs"]


def test_provider_market_data_imbalance_broker_readiness_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_broker_readiness"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_readiness_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_runtime_session"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_runtime_session"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["provider_runtime_session"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_runtime_session"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_runtime_session"]["source_live_fetch_contract_available"] is True
    assert config["provider_runtime_session"]["exchange"] == "NFO"
    assert config["provider_runtime_session"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_runtime_session"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_runtime_session"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_runtime_session"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_runtime_session"]["provider_profile_matches_bundle"] is True
    assert config["provider_runtime_session"]["provider_capture_command_count"] == 2
    assert config["provider_runtime_session"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_broker_readiness_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    summary_path = runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_summary.csv"
    session_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        session_summary.loc[0, column] = ""
    session_summary.loc[0, "adapter_contract_values_stored"] = True
    session_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    session_summary.to_csv(summary_path, index=False)
    config_path = runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_runtime_session_adapter_execution_contract_carried" in failed
    assert "provider_runtime_session_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_runtime_session"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-session"


def test_provider_market_data_imbalance_broker_readiness_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    summary_path = runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_summary.csv"
    session_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        session_summary.loc[0, column] = ""
    session_summary.loc[0, "provider_profile_matches_session"] = False
    session_summary.loc[0, "provider_profile_matches_bundle"] = False
    session_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    session_summary.to_csv(summary_path, index=False)
    config_path = runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_runtime_session_provider_profile_carried" in failed
    assert "provider_runtime_session_provider_profile_matches_session" in failed
    assert "provider_runtime_session_provider_profile_matches_bundle" in failed
    assert "provider_runtime_session_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_runtime_session"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-session"


def test_provider_market_data_imbalance_broker_readiness_carries_roundtrip_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
        route_readiness_dir=route_readiness.output_dir,
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    cutover = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )
    route_enable = write_provider_market_data_imbalance_route_enable(
        cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )
    broker_dispatch = write_provider_market_data_imbalance_broker_dispatch(
        route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )
    provider_send = write_provider_market_data_imbalance_broker_dispatch_send(
        broker_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_acks.csv",
    )
    provider_ack = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )
    provider_roundtrip = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_roundtrip"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_readiness_runbook.md").read_text(
        encoding="utf-8"
    )
    checks = report.checks.set_index("check")
    assert not report.ready
    assert bool(checks.loc["broker_readiness_runnable", "passed"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert len(summary["dispatch_roundtrip_capture_env_template_sha256"]) == 64
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert len(summary["dispatch_roundtrip_adapter_handoff_sha256"]) == 64
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_source_session_close_local"] == "15:30:00"
    assert summary["dispatch_roundtrip_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_market_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert len(summary["dispatch_roundtrip_provider_profile_sha256"]) == 64
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert (
        summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert (
        summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert bool(checks.loc["dispatch_roundtrip_capture_bundle_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_capture_env_template_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_handoff_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_exchange_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_source_session_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_market_session_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_capture_bundle_exchange_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_capture_bundle_source_session_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_capture_bundle_market_session_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_source_credential_env_template_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_source_credential_env_template_sha256_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_next_gate_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_command_template_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_exchange_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_market_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_session_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_execution_contract_matches_evidence", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_execution_contract_matches_runtime_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_provider_profile_matches_evidence", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_matches_runtime_session", "passed"])
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_transport"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        config["dispatch_roundtrip_provenance"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_session"] is True
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_bundle"] is True
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"] is True
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
        is True
    )
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert (
        config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"][
        "provider_capture_commands_match_runtime_session"
    ]
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {summary['provider_profile_sha256']}" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_broker_readiness_blocks_roundtrip_adapter_contract_mismatch(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    summary_path = provider_roundtrip.output_dir / (
        "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(summary_path)
    roundtrip_summary.loc[0, "capture_bundle_provided"] = True
    for column, value in (
        ("adapter_contract_provider", "irage"),
        ("adapter_contract_transport", "rest"),
        ("adapter_contract_market", "india_nse_index_derivatives"),
        ("adapter_contract_exchange", "NFO"),
        ("adapter_contract_values_stored", False),
        ("adapter_contract_metadata_matches_evidence", True),
    ):
        for candidate in (column, f"dispatch_roundtrip_{column}"):
            if candidate in roundtrip_summary.columns:
                roundtrip_summary.loc[0, candidate] = value
    roundtrip_summary.to_csv(summary_path, index=False)
    config_path = provider_roundtrip.output_dir / (
        "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    _mutate_json(
        config_path,
        lambda payload: (
            payload["adapter_execution_contract"].update({"provider": "irage", "transport": "rest"}),
            payload["capture_bundle"]["adapter_execution_contract"].update(
                {"provider": "irage", "transport": "rest"}
            ),
        ),
    )

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "irage"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_roundtrip"
    assert report.action_queue.loc[0, "next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )


def test_provider_market_data_imbalance_broker_readiness_blocks_missing_roundtrip_adapter_contract(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    summary_path = provider_roundtrip.output_dir / (
        "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(summary_path)
    roundtrip_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        for candidate in (column, f"dispatch_roundtrip_{column}"):
            if candidate in roundtrip_summary.columns:
                roundtrip_summary.loc[0, candidate] = ""
    for column, value in (
        ("adapter_contract_values_stored", True),
        ("adapter_contract_metadata_matches_evidence", False),
    ):
        for candidate in (column, f"dispatch_roundtrip_{column}"):
            if candidate in roundtrip_summary.columns:
                roundtrip_summary.loc[0, candidate] = value
    roundtrip_summary.to_csv(summary_path, index=False)
    config_path = provider_roundtrip.output_dir / (
        "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_roundtrip"
    assert report.action_queue.loc[0, "next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )


def test_provider_market_data_imbalance_broker_readiness_blocks_missing_roundtrip_provider_profile(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    summary_path = provider_roundtrip.output_dir / (
        "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(summary_path)
    roundtrip_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        for candidate in (column, f"dispatch_roundtrip_{column}"):
            if candidate in roundtrip_summary.columns:
                roundtrip_summary[candidate] = roundtrip_summary[candidate].astype("object")
                roundtrip_summary.loc[0, candidate] = ""
    for column in (
        "provider_profile_matches_session",
        "provider_profile_matches_bundle",
        "adapter_contract_provider_profile_matches_evidence",
    ):
        for candidate in (column, f"dispatch_roundtrip_{column}"):
            if candidate in roundtrip_summary.columns:
                roundtrip_summary.loc[0, candidate] = False
    roundtrip_summary.to_csv(summary_path, index=False)
    config_path = provider_roundtrip.output_dir / (
        "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)
        provenance = payload.get("dispatch_roundtrip_provenance")
        if isinstance(provenance, dict):
            provenance.pop("provider_profile", None)
            provenance.pop("live_session_provider_profile", None)
            provenance.pop("capture_bundle_provider_profile", None)
            provenance_contract = provenance.get("adapter_execution_contract")
            if isinstance(provenance_contract, dict):
                provenance_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "dispatch_roundtrip_provider_profile_carried" in failed
    assert "dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_roundtrip"
    assert report.action_queue.loc[0, "next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )


def test_provider_market_data_imbalance_broker_readiness_accepts_provider_dispatch_roundtrip_root(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_provider_roundtrip"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_summary.csv")
    broker_summary = pd.read_csv(out_dir / "broker_readiness" / "broker_readiness_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    nested_roundtrip_dir = provider_roundtrip.output_dir / "broker_dispatch_roundtrip"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "broker_readiness_ready" in failed
    assert bool(summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "dispatch_roundtrip_ready"])
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-readiness"
    assert summary.loc[0, "next_gate_help_command"] == (
        "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    )
    assert Path(summary.loc[0, "provider_dispatch_roundtrip_dir"]) == provider_roundtrip.output_dir
    assert Path(summary.loc[0, "dispatch_roundtrip_dir"]) == nested_roundtrip_dir
    assert bool(broker_summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(broker_summary.loc[0, "dispatch_roundtrip_ready"])
    assert bool(report.checks.set_index("check").loc["broker_readiness_runnable", "passed"])
    assert config["broker_inputs"]["provider_dispatch_roundtrip_dir"] == str(provider_roundtrip.output_dir)
    assert config["broker_inputs"]["dispatch_roundtrip_dir"] == str(nested_roundtrip_dir)
    assert manifest["inputs"]["provider_dispatch_roundtrip"]["path"] == str(provider_roundtrip.output_dir)
    assert manifest["inputs"]["dispatch_roundtrip"]["path"] == str(nested_roundtrip_dir)


def test_provider_market_data_imbalance_broker_readiness_reads_roundtrip_provenance_command_arrays(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    config_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    roundtrip_config = json.loads(config_path.read_text(encoding="utf-8"))
    nested_provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command_template": "nested-only-provider-command",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command_template": "nested-only-provider-verify-command",
        },
    ]
    provenance = roundtrip_config.setdefault("dispatch_roundtrip_provenance", {})
    provenance["provider_capture_commands"] = nested_provider_capture_commands
    provenance["capture_bundle_provider_capture_commands"] = nested_provider_capture_commands
    roundtrip_config.pop("provider_capture_commands", None)
    roundtrip_config.pop("capture_bundle_provider_capture_commands", None)
    capture_bundle = roundtrip_config.get("capture_bundle", {})
    if isinstance(capture_bundle, dict):
        capture_bundle.pop("provider_capture_commands", None)
        capture_bundle.pop("capture_bundle_provider_capture_commands", None)
    config_path.write_text(
        json.dumps(roundtrip_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_readiness_roundtrip_command_array_fallback"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_consistent", "passed"])
    assert (
        config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["command_template"]
        == "nested-only-provider-command"
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][1]["command_template"]
        == "nested-only-provider-verify-command"
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["command_template"]
        == "nested-only-provider-command"
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][1]["command_template"]
        == "nested-only-provider-verify-command"
    )
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0][
            "command_template"
        ]
        == "nested-only-provider-command"
    )


def test_provider_market_data_imbalance_broker_readiness_blocks_roundtrip_capture_bundle_mismatch(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    runtime_bundle = tmp_path / "runtime_capture_bundle.json"
    roundtrip_bundle = tmp_path / "roundtrip_capture_bundle.json"
    runtime_bundle.write_text("{}", encoding="utf-8")
    roundtrip_bundle.write_text("{}", encoding="utf-8")

    session_summary_path = (
        runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_summary.csv"
    )
    session_summary = pd.read_csv(session_summary_path)
    session_summary["capture_bundle_path"] = str(runtime_bundle)
    session_summary["capture_bundle_provided"] = True
    session_summary["capture_bundle_exists"] = True
    session_summary["capture_bundle_ready"] = True
    session_summary.to_csv(session_summary_path, index=False)

    roundtrip_summary_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(roundtrip_summary_path)
    roundtrip_summary["dispatch_roundtrip_capture_bundle_path"] = str(roundtrip_bundle)
    roundtrip_summary["dispatch_roundtrip_capture_bundle_provided"] = True
    roundtrip_summary["dispatch_roundtrip_capture_bundle_exists"] = True
    roundtrip_summary["dispatch_roundtrip_capture_bundle_ready"] = True
    roundtrip_summary.to_csv(roundtrip_summary_path, index=False)
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_capture_mismatch"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    checks = report.checks.set_index("check")
    assert not report.ready
    assert not bool(checks.loc["dispatch_roundtrip_capture_bundle_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_capture_env_template_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_handoff_consistent", "passed"])
    assert not bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert report.action_queue.iloc[0]["next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )
    assert report.action_queue.iloc[0]["action"] == "repair_provider_imbalance_broker_dispatch_roundtrip"


def test_provider_market_data_imbalance_broker_readiness_blocks_roundtrip_source_mismatch(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    runtime_source = tmp_path / "runtime_source_credentials.env"
    roundtrip_source = tmp_path / "roundtrip_source_credentials.env"
    runtime_source.write_text("IRAGE_CLIENT_ID=runtime\n", encoding="utf-8")
    roundtrip_source.write_text("IRAGE_CLIENT_ID=roundtrip\n", encoding="utf-8")

    session_summary_path = (
        runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_summary.csv"
    )
    session_summary = pd.read_csv(session_summary_path)
    session_summary["source_credential_env_template_path"] = str(runtime_source)
    session_summary["source_credential_env_template_exists"] = True
    session_summary["source_credential_env_template_sha256"] = "a" * 64
    session_summary["source_live_fetch_contract_available"] = True
    session_summary["source_live_fetch_contract_next_gate"] = "provider_fetcher"
    session_summary["source_live_fetch_contract_command_template"] = "python -m hft_cli fetch-provider-live-data"
    session_summary.to_csv(session_summary_path, index=False)

    roundtrip_summary_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(roundtrip_summary_path)
    roundtrip_summary["dispatch_roundtrip_source_credential_env_template_path"] = str(roundtrip_source)
    roundtrip_summary["dispatch_roundtrip_source_credential_env_template_exists"] = True
    roundtrip_summary["dispatch_roundtrip_source_credential_env_template_sha256"] = "a" * 64
    roundtrip_summary["dispatch_roundtrip_source_live_fetch_contract_available"] = True
    roundtrip_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"] = "provider_fetcher"
    roundtrip_summary["dispatch_roundtrip_source_live_fetch_contract_command_template"] = (
        "python -m hft_cli fetch-provider-live-data"
    )
    roundtrip_summary.to_csv(roundtrip_summary_path, index=False)
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_source_mismatch"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    checks = report.checks.set_index("check")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert not bool(checks.loc["dispatch_roundtrip_source_credential_env_template_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_source_credential_env_template_sha256_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_next_gate_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_live_fetch_contract_command_template_consistent", "passed"])
    assert not bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert not bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert not config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert not config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert not manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert report.action_queue.iloc[0]["next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )
    assert report.action_queue.iloc[0]["action"] == "repair_provider_imbalance_broker_dispatch_roundtrip"


def test_provider_market_data_imbalance_broker_readiness_blocks_roundtrip_session_metadata_mismatch(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)

    session_summary_path = (
        runtime_session.output_dir / "provider_market_data_imbalance_runtime_session_summary.csv"
    )
    session_summary = pd.read_csv(session_summary_path)
    session_summary["source_live_fetch_contract_exchange"] = "NFO"
    session_summary["source_live_fetch_contract_market"] = "india_nse_index_derivatives"
    session_summary["source_live_fetch_contract_session_timezone"] = "Asia/Kolkata"
    session_summary["source_live_fetch_contract_session_open_local"] = "09:15:00"
    session_summary["source_live_fetch_contract_session_close_local"] = "15:30:00"
    session_summary.to_csv(session_summary_path, index=False)

    roundtrip_summary_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(roundtrip_summary_path)
    roundtrip_summary["dispatch_roundtrip_exchange"] = "BFO"
    roundtrip_summary["dispatch_roundtrip_source_session_open_local"] = "09:16:00"
    roundtrip_summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] = "BFO"
    roundtrip_summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] = "09:16:00"
    roundtrip_summary.to_csv(roundtrip_summary_path, index=False)
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_session_metadata_mismatch"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    checks = report.checks.set_index("check")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert not bool(checks.loc["dispatch_roundtrip_exchange_consistent", "passed"])
    assert not bool(checks.loc["dispatch_roundtrip_source_session_consistent", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_market_session_consistent", "passed"])
    assert not bool(checks.loc["dispatch_roundtrip_live_fetch_contract_exchange_consistent", "passed"])
    assert not bool(checks.loc["dispatch_roundtrip_live_fetch_contract_session_consistent", "passed"])
    assert summary["dispatch_roundtrip_exchange"] == "BFO"
    assert not bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert not bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert not bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert not bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert not bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert not bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert not config["dispatch_roundtrip_provenance"]["exchange_matches_session"]
    assert not config["dispatch_roundtrip_provenance"]["source_session_matches_session"]
    assert not config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert not config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert not config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session_matches_session"]
    assert not manifest["extra"]["dispatch_roundtrip_exchange_matches_session"]
    assert not manifest["extra"]["dispatch_roundtrip_source_session_matches_session"]
    assert not manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert not manifest["extra"]["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"]
    assert not manifest["extra"]["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"]
    assert report.action_queue.iloc[0]["next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )
    assert report.action_queue.iloc[0]["action"] == "repair_provider_imbalance_broker_dispatch_roundtrip"


def test_provider_market_data_imbalance_broker_readiness_surfaces_roundtrip_vendor_batch(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip_with_vendor_batch(tmp_path)
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_vendor_batch"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_summary.csv")
    broker_summary = pd.read_csv(out_dir / "broker_readiness" / "broker_readiness_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    runbook = (out_dir / "provider_market_data_imbalance_broker_readiness_runbook.md").read_text(
        encoding="utf-8"
    )

    assert not report.ready
    assert "dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert bool(broker_summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert not config["dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["provided"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["adapter"] == "arrow_money"
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert "- Broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_readiness_preserves_roundtrip_upstream_vendor_batch(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()

    roundtrip_summary_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(roundtrip_summary_path)
    roundtrip_summary["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_market"] = (
        "india_nse_index_derivatives"
    )
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    roundtrip_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    roundtrip_summary.to_csv(roundtrip_summary_path, index=False)

    roundtrip_config_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    roundtrip_config = json.loads(roundtrip_config_path.read_text(encoding="utf-8"))
    roundtrip_config["upstream_dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    roundtrip_config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    roundtrip_config_path.write_text(
        json.dumps(roundtrip_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_readiness_runbook.md").read_text(
        encoding="utf-8"
    )

    assert not report.ready
    assert bool(report.checks.set_index("check").loc["broker_readiness_runnable", "passed"])
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_readiness_preserves_upstream_roundtrip(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    provider_roundtrip = _write_ready_provider_imbalance_broker_dispatch_roundtrip(tmp_path)
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    upstream_nested_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"passed": True, "ready": True}]).to_csv(
        upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )

    roundtrip_summary_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    roundtrip_summary = pd.read_csv(roundtrip_summary_path)
    roundtrip_summary["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    roundtrip_summary["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    roundtrip_summary["upstream_dispatch_roundtrip_provided"] = True
    roundtrip_summary["upstream_dispatch_roundtrip_ready"] = True
    roundtrip_summary["upstream_dispatch_roundtrip_failed_checks"] = 0
    roundtrip_summary.to_csv(roundtrip_summary_path, index=False)

    roundtrip_config_path = (
        provider_roundtrip.output_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    roundtrip_config = json.loads(roundtrip_config_path.read_text(encoding="utf-8"))
    roundtrip_inputs = roundtrip_config.setdefault("broker_dispatch_roundtrip_inputs", {})
    roundtrip_inputs["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    roundtrip_inputs["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    roundtrip_config_path.write_text(
        json.dumps(roundtrip_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "provider_imbalance_broker_readiness_with_upstream_roundtrip"
    report = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        out_dir,
        dispatch_roundtrip_dir=provider_roundtrip.output_dir,
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(require_dispatch_roundtrip=True),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_readiness_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert not report.ready
    assert bool(report.checks.set_index("check").loc["broker_readiness_runnable", "passed"])
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(upstream_provider_dir)
    assert config["broker_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert Path(manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"]) == upstream_provider_dir.resolve()
    assert Path(manifest["inputs"]["upstream_dispatch_roundtrip"]["path"]) == upstream_nested_dir.resolve()


def test_provider_market_data_imbalance_broker_readiness_blocks_unready_session(tmp_path):
    session_dir = tmp_path / "provider_imbalance_runtime_session"
    session_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "runtime_session_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(session_dir / "provider_market_data_imbalance_runtime_session_summary.csv", index=False)
    (session_dir / "provider_market_data_imbalance_runtime_session_config.json").write_text(
        json.dumps({"runtime_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_broker_readiness(
        session_dir,
        tmp_path / "provider_imbalance_broker_readiness",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_runtime_session_ready" in failed
    assert "nested_runtime_session_summary_exists" in failed
    assert "order_export_input_resolved" in failed
    assert "upload_pack_input_resolved" in failed
    assert "broker_readiness_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-provider-market-data-imbalance-runtime-session"
    assert not (report.output_dir / "broker_readiness" / "broker_readiness_summary.csv").exists()


def test_cli_provider_market_data_imbalance_broker_readiness_accepts_ready_session(tmp_path):
    runtime_session = _write_ready_provider_imbalance_runtime_session(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_broker_readiness"

    code = main(
        [
            "review-provider-market-data-imbalance-broker-readiness",
            "--runtime-session",
            str(runtime_session.output_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_readiness_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_readiness_ready"])
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"


def test_provider_market_data_imbalance_cutover_blocks_missing_route_proof(tmp_path):
    broker_readiness = _write_ready_provider_imbalance_broker_readiness(tmp_path)
    out_dir = tmp_path / "provider_imbalance_cutover"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_action_queue.csv")
    cutover_summary = pd.read_csv(out_dir / "cutover" / "cutover_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert bool(summary.loc[0, "provider_broker_readiness_ready"])
    assert not bool(summary.loc[0, "cutover_ready"])
    assert not bool(cutover_summary.loc[0, "ready"])
    assert "cutover_ready" in failed
    assert summary.loc[0, "next_gate"] == "review-route-readiness"
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "next_gate"] == "review-route-readiness"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert manifest["run_type"] == "provider_market_data_imbalance_cutover"
    assert "cutover" in manifest["inputs"]
    assert "scaleup" in manifest["inputs"]
    assert "broker_readiness" in manifest["inputs"]
    assert "runtime_session" in manifest["inputs"]


def test_provider_market_data_imbalance_cutover_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_cutover"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_cutover_runbook.md").read_text(encoding="utf-8")
    assert not report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert summary["source_live_fetch_contract_exchange"] == "NFO"
    assert summary["source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert not bool(summary["adapter_contract_values_stored"])
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["transport"] == "websocket"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["capture_bundle"]["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_metadata_matches_evidence"] is True
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["provider_broker_readiness"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_broker_readiness"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["provider_broker_readiness"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_broker_readiness"]["exchange"] == "NFO"
    assert config["provider_broker_readiness"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_broker_readiness"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_broker_readiness"]["source_live_fetch_contract_available"] is True
    assert config["provider_broker_readiness"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_broker_readiness"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_broker_readiness"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_broker_readiness"]["provider_profile_matches_bundle"] is True
    assert config["provider_broker_readiness"]["provider_capture_command_count"] == 2
    assert config["provider_broker_readiness"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["metadata_matches_session"] is True
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"] == summary[
        "provider_profile_sha256"
    ]
    assert manifest["extra"]["adapter_contract_metadata_matches_evidence"] is True
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert "Exchange: NFO" in runbook
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_cutover_blocks_missing_adapter_execution_contract(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    summary_path = broker_readiness.output_dir / "provider_market_data_imbalance_broker_readiness_summary.csv"
    broker_summary = pd.read_csv(summary_path)
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        broker_summary.loc[0, column] = ""
    broker_summary.loc[0, "adapter_contract_values_stored"] = True
    broker_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    broker_summary.to_csv(summary_path, index=False)
    config_path = broker_readiness.output_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_broker_readiness_adapter_execution_contract_carried" in failed
    assert "provider_broker_readiness_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_readiness"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"


def test_provider_market_data_imbalance_cutover_blocks_missing_provider_profile(tmp_path):
    launch_evidence, _ = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    summary_path = broker_readiness.output_dir / "provider_market_data_imbalance_broker_readiness_summary.csv"
    broker_summary = pd.read_csv(summary_path)
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        broker_summary.loc[0, column] = ""
    broker_summary.loc[0, "provider_profile_matches_session"] = False
    broker_summary.loc[0, "provider_profile_matches_bundle"] = False
    broker_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    broker_summary.to_csv(summary_path, index=False)
    config_path = broker_readiness.output_dir / "provider_market_data_imbalance_broker_readiness_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_broker_readiness_provider_profile_carried" in failed
    assert "provider_broker_readiness_provider_profile_matches_session" in failed
    assert "provider_broker_readiness_provider_profile_matches_bundle" in failed
    assert "provider_broker_readiness_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_readiness"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"


def test_provider_market_data_imbalance_cutover_carries_roundtrip_capture_bundle_provenance(tmp_path):
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }
    provider_profile_sha256 = "c" * 64
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_with_roundtrip_provenance"
    broker_readiness_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "capture_bundle_path": str(bundle_path),
                "capture_bundle_provided": True,
                "capture_bundle_exists": True,
                "capture_bundle_ready": True,
                "capture_env_template_path": str(env_template_path),
                "capture_env_template_provided": True,
                "capture_env_template_exists": True,
                "adapter_handoff_path": str(adapter_handoff_path),
                "adapter_handoff_provided": True,
                "adapter_handoff_exists": True,
                "source_credential_env_template_path": str(source_env_template_path),
                "source_credential_env_template_exists": True,
                "source_credential_env_template_sha256": "a" * 64,
                "source_live_fetch_contract_available": True,
                "source_live_fetch_contract_next_gate": "provider_fetcher",
                "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
                "provider_capture_command_count": 2,
                "provider_capture_command_providers": "arrow_money",
                "provider_capture_command_transports": "websocket",
                "capture_bundle_provider_capture_command_count": 2,
                "capture_bundle_provider_capture_command_missing_count": 0,
                "capture_bundle_provider_capture_commands_match_session": True,
                "adapter_contract_provider": "arrow_money",
                "adapter_contract_transport": "websocket",
                "adapter_contract_market": "india_nse_index_derivatives",
                "adapter_contract_exchange": "NFO",
                "adapter_contract_values_stored": False,
                "adapter_contract_metadata_matches_evidence": True,
                "provider_profile_sha256": provider_profile_sha256,
                "provider_profile_adapter": "arrow_money",
                "provider_profile_auth_required": True,
                "provider_profile_transports": "file;rest;websocket",
                "provider_profile_capabilities": "live_ticks;market_depth",
                "capture_bundle_provider_profile_sha256": provider_profile_sha256,
                "provider_profile_matches_session": True,
                "provider_profile_matches_bundle": True,
                "adapter_contract_provider_profile_sha256": provider_profile_sha256,
                "adapter_contract_provider_profile_matches_evidence": True,
                "dispatch_roundtrip_exchange": "NFO",
                "dispatch_roundtrip_source_session_timezone": "Asia/Kolkata",
                "dispatch_roundtrip_source_session_open_local": "09:15:00",
                "dispatch_roundtrip_source_session_close_local": "15:30:00",
                "dispatch_roundtrip_market_session_timezone": "Asia/Kolkata",
                "dispatch_roundtrip_market_session_open_local": "09:15",
                "dispatch_roundtrip_market_session_close_local": "15:30",
                "dispatch_roundtrip_exchange_matches_session": True,
                "dispatch_roundtrip_source_session_matches_session": True,
                "dispatch_roundtrip_market_session_matches_session": True,
                "dispatch_roundtrip_metadata_consistent": True,
                "dispatch_roundtrip_source_credential_env_template_path": str(source_env_template_path),
                "dispatch_roundtrip_source_credential_env_template_exists": True,
                "dispatch_roundtrip_source_credential_env_template_sha256": "a" * 64,
                "dispatch_roundtrip_source_credential_env_template_matches_session": True,
                "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": True,
                "dispatch_roundtrip_source_live_fetch_contract_available": True,
                "dispatch_roundtrip_source_live_fetch_contract_next_gate": "provider_fetcher",
                "dispatch_roundtrip_source_live_fetch_contract_command_template": (
                    "python -m hft_cli fetch-provider-live-data"
                ),
                "dispatch_roundtrip_source_live_fetch_contract_exchange": "NFO",
                "dispatch_roundtrip_source_live_fetch_contract_market": "india_nse_index_derivatives",
                "dispatch_roundtrip_source_live_fetch_contract_session_timezone": "Asia/Kolkata",
                "dispatch_roundtrip_source_live_fetch_contract_session_open_local": "09:15:00",
                "dispatch_roundtrip_source_live_fetch_contract_session_close_local": "15:30:00",
                "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": True,
                "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": True,
                "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session": True,
                "dispatch_roundtrip_source_live_fetch_contract_market_matches_session": True,
                "dispatch_roundtrip_source_live_fetch_contract_session_matches_session": True,
                "dispatch_roundtrip_source_provenance_consistent": True,
                "dispatch_roundtrip_capture_bundle_path": str(bundle_path),
                "dispatch_roundtrip_capture_bundle_provided": True,
                "dispatch_roundtrip_capture_bundle_exists": True,
                "dispatch_roundtrip_capture_bundle_ready": True,
                "dispatch_roundtrip_capture_bundle_exchange": "NFO",
                "dispatch_roundtrip_capture_bundle_source_session_timezone": "Asia/Kolkata",
                "dispatch_roundtrip_capture_bundle_source_session_open_local": "09:15:00",
                "dispatch_roundtrip_capture_bundle_source_session_close_local": "15:30:00",
                "dispatch_roundtrip_capture_bundle_market_session_timezone": "Asia/Kolkata",
                "dispatch_roundtrip_capture_bundle_market_session_open_local": "09:15",
                "dispatch_roundtrip_capture_bundle_market_session_close_local": "15:30",
                "dispatch_roundtrip_capture_bundle_metadata_matches_session": True,
                "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session": True,
                "dispatch_roundtrip_capture_bundle_matches_session": True,
                "dispatch_roundtrip_capture_bundle_exchange_matches_session": True,
                "dispatch_roundtrip_capture_bundle_source_session_matches_session": True,
                "dispatch_roundtrip_capture_bundle_market_session_matches_session": True,
                "dispatch_roundtrip_provider_capture_command_count": 2,
                "dispatch_roundtrip_provider_capture_command_providers": "arrow_money",
                "dispatch_roundtrip_provider_capture_command_transports": "websocket",
                "dispatch_roundtrip_capture_bundle_provider_capture_command_count": 2,
                "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": 0,
                "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": True,
                "dispatch_roundtrip_provider_capture_commands_match_runtime_session": True,
                "dispatch_roundtrip_adapter_contract_provider": "arrow_money",
                "dispatch_roundtrip_adapter_contract_transport": "websocket",
                "dispatch_roundtrip_adapter_contract_market": "india_nse_index_derivatives",
                "dispatch_roundtrip_adapter_contract_exchange": "NFO",
                "dispatch_roundtrip_adapter_contract_values_stored": False,
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": True,
                "dispatch_roundtrip_adapter_contract_matches_runtime_session": True,
                "dispatch_roundtrip_provider_profile_sha256": provider_profile_sha256,
                "dispatch_roundtrip_provider_profile_adapter": "arrow_money",
                "dispatch_roundtrip_provider_profile_auth_required": True,
                "dispatch_roundtrip_provider_profile_transports": "file;rest;websocket",
                "dispatch_roundtrip_provider_profile_capabilities": "live_ticks;market_depth",
                "dispatch_roundtrip_capture_bundle_provider_profile_sha256": provider_profile_sha256,
                "dispatch_roundtrip_provider_profile_matches_session": True,
                "dispatch_roundtrip_provider_profile_matches_bundle": True,
                "dispatch_roundtrip_adapter_contract_provider_profile_sha256": provider_profile_sha256,
                "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence": True,
                "dispatch_roundtrip_provider_profile_matches_runtime_session": True,
                "dispatch_roundtrip_capture_env_template_path": str(env_template_path),
                "dispatch_roundtrip_capture_env_template_provided": True,
                "dispatch_roundtrip_capture_env_template_exists": True,
                "dispatch_roundtrip_capture_env_template_sha256": env_template_sha256,
                "dispatch_roundtrip_capture_env_template_matches_session": True,
                "dispatch_roundtrip_adapter_handoff_path": str(adapter_handoff_path),
                "dispatch_roundtrip_adapter_handoff_provided": True,
                "dispatch_roundtrip_adapter_handoff_exists": True,
                "dispatch_roundtrip_adapter_handoff_sha256": adapter_handoff_sha256,
                "dispatch_roundtrip_adapter_handoff_matches_session": True,
                "dispatch_roundtrip_capture_provenance_consistent": True,
                "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                "dispatch_roundtrip_provided": True,
                "dispatch_roundtrip_ready": True,
                "dispatch_roundtrip_failed_checks": 0,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "broker_inputs": {
                    "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                    "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                },
                "provider_runtime_session": {"scaleup_dir": ""},
                "provider_capture_commands": provider_capture_commands,
                "capture_bundle_provider_capture_commands": provider_capture_commands,
                "adapter_execution_contract": {
                    "provider": "arrow_money",
                    "transport": "websocket",
                    "market": "india_nse_index_derivatives",
                    "exchange": "NFO",
                    "provider_profile_sha256": provider_profile_sha256,
                    "values_stored": False,
                },
                "provider_profile": provider_profile,
                "live_session_provider_profile": provider_profile,
                "capture_bundle": {
                    "provider_capture_commands": provider_capture_commands,
                    "capture_bundle_provider_capture_commands": provider_capture_commands,
                    "capture_bundle_provider_profile": provider_profile,
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "provider_profile_sha256": provider_profile_sha256,
                        "values_stored": False,
                    },
                },
                "dispatch_roundtrip_provenance": {
                    "provider_capture_command_count": 2,
                    "provider_capture_command_providers": "arrow_money",
                    "provider_capture_command_transports": "websocket",
                    "capture_bundle_provider_capture_command_count": 2,
                    "capture_bundle_provider_capture_command_missing_count": 0,
                    "capture_bundle_provider_capture_commands_match_session": True,
                    "provider_capture_commands": provider_capture_commands,
                    "capture_bundle_provider_capture_commands": provider_capture_commands,
                    "provider_capture_commands_match_runtime_session": True,
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "values_stored": False,
                    },
                    "adapter_contract_provider": "arrow_money",
                    "adapter_contract_transport": "websocket",
                    "adapter_contract_market": "india_nse_index_derivatives",
                    "adapter_contract_exchange": "NFO",
                    "adapter_contract_values_stored": False,
                    "adapter_contract_metadata_matches_evidence": True,
                    "adapter_contract_matches_runtime_session": True,
                    "provider_profile": provider_profile,
                    "live_session_provider_profile": provider_profile,
                    "capture_bundle_provider_profile": provider_profile,
                    "provider_profile_sha256": provider_profile_sha256,
                    "provider_profile_matches_session": True,
                    "provider_profile_matches_bundle": True,
                    "provider_profile_matches_runtime_session": True,
                    "adapter_contract_provider_profile_sha256": provider_profile_sha256,
                    "adapter_contract_provider_profile_matches_evidence": True,
                    "capture_bundle_path": str(bundle_path),
                    "capture_env_template_path": str(env_template_path),
                    "capture_env_template_sha256": env_template_sha256,
                    "adapter_handoff_path": str(adapter_handoff_path),
                    "adapter_handoff_sha256": adapter_handoff_sha256,
                    "consistent_with_runtime_session": True,
                    "source_credential_env_template_path": str(source_env_template_path),
                    "source_credential_env_template_sha256": "a" * 64,
                    "source_credential_env_template_matches_session": True,
                    "source_credential_env_template_sha256_matches_session": True,
                    "source_live_fetch_contract_available": True,
                    "source_live_fetch_contract_next_gate": "provider_fetcher",
                    "source_live_fetch_contract_command_template": (
                        "python -m hft_cli fetch-provider-live-data"
                    ),
                    "source_live_fetch_contract_next_gate_matches_session": True,
                    "source_live_fetch_contract_command_template_matches_session": True,
                    "source_provenance_consistent_with_runtime_session": True,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_cutover_with_roundtrip_provenance"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_cutover_runbook.md").read_text(encoding="utf-8")
    checks = report.checks.set_index("check")
    assert not report.ready
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert len(summary["dispatch_roundtrip_capture_env_template_sha256"]) == 64
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert len(summary["dispatch_roundtrip_adapter_handoff_sha256"]) == 64
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_execution_contract_matches_evidence", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_execution_contract_matches_runtime_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_adapter_provider_profile_matches_evidence", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_profile_matches_runtime_session", "passed"])
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_transport"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_sha256"] == provider_profile_sha256
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_bundle"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert (
        config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert config["provider_broker_readiness"]["dispatch_roundtrip_adapter_handoff_path"] == str(
        adapter_handoff_path
    )
    assert (
        config["provider_broker_readiness"]["dispatch_roundtrip_adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["provider_broker_readiness"]["dispatch_roundtrip_source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"][
        "provider_capture_commands_match_runtime_session"
    ]
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_cutover_blocks_missing_roundtrip_adapter_contract(tmp_path):
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_missing_roundtrip_adapter"
    broker_readiness_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ready": True,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "capture_bundle_provided": True,
                "provider_capture_command_count": 2,
                "provider_capture_command_providers": "arrow_money",
                "provider_capture_command_transports": "websocket",
                "capture_bundle_provider_capture_command_count": 2,
                "capture_bundle_provider_capture_command_missing_count": 0,
                "capture_bundle_provider_capture_commands_match_session": True,
                "adapter_contract_provider": "arrow_money",
                "adapter_contract_transport": "websocket",
                "adapter_contract_market": "india_nse_index_derivatives",
                "adapter_contract_exchange": "NFO",
                "adapter_contract_values_stored": False,
                "adapter_contract_metadata_matches_evidence": True,
                "dispatch_roundtrip_capture_bundle_provided": True,
                "dispatch_roundtrip_provider_capture_command_count": 2,
                "dispatch_roundtrip_provider_capture_command_providers": "arrow_money",
                "dispatch_roundtrip_provider_capture_command_transports": "websocket",
                "dispatch_roundtrip_capture_bundle_provider_capture_command_count": 2,
                "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": 0,
                "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": True,
                "dispatch_roundtrip_provider_capture_commands_match_runtime_session": True,
                "dispatch_roundtrip_adapter_contract_provider": "",
                "dispatch_roundtrip_adapter_contract_transport": "",
                "dispatch_roundtrip_adapter_contract_market": "",
                "dispatch_roundtrip_adapter_contract_exchange": "",
                "dispatch_roundtrip_adapter_contract_values_stored": True,
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": False,
                "dispatch_roundtrip_adapter_contract_matches_runtime_session": False,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "provider_runtime_session": {"scaleup_dir": ""},
                "adapter_execution_contract": {
                    "provider": "arrow_money",
                    "transport": "websocket",
                    "market": "india_nse_index_derivatives",
                    "exchange": "NFO",
                    "values_stored": False,
                },
                "capture_bundle": {
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "values_stored": False,
                    },
                },
                "dispatch_roundtrip_provenance": {
                    "capture_bundle_provided": True,
                    "provider_capture_command_count": 2,
                    "provider_capture_command_providers": "arrow_money",
                    "provider_capture_command_transports": "websocket",
                    "capture_bundle_provider_capture_command_count": 2,
                    "capture_bundle_provider_capture_command_missing_count": 0,
                    "capture_bundle_provider_capture_commands_match_session": True,
                    "provider_capture_commands_match_runtime_session": True,
                    "adapter_contract_values_stored": True,
                    "adapter_contract_metadata_matches_evidence": False,
                    "adapter_contract_matches_runtime_session": False,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_readiness"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"


def test_provider_market_data_imbalance_cutover_blocks_missing_roundtrip_provider_profile(tmp_path):
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_missing_roundtrip_provider_profile"
    broker_readiness_dir.mkdir(parents=True)
    provider_profile_sha256 = "e" * 64
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    pd.DataFrame(
        [
            {
                "ready": True,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "capture_bundle_provided": True,
                "provider_capture_command_count": 2,
                "provider_capture_command_providers": "arrow_money",
                "provider_capture_command_transports": "websocket",
                "capture_bundle_provider_capture_command_count": 2,
                "capture_bundle_provider_capture_command_missing_count": 0,
                "capture_bundle_provider_capture_commands_match_session": True,
                "adapter_contract_provider": "arrow_money",
                "adapter_contract_transport": "websocket",
                "adapter_contract_market": "india_nse_index_derivatives",
                "adapter_contract_exchange": "NFO",
                "adapter_contract_values_stored": False,
                "adapter_contract_metadata_matches_evidence": True,
                "provider_profile_sha256": provider_profile_sha256,
                "provider_profile_adapter": "arrow_money",
                "provider_profile_auth_required": True,
                "provider_profile_transports": "file;rest;websocket",
                "provider_profile_capabilities": "live_ticks;market_depth",
                "capture_bundle_provider_profile_sha256": provider_profile_sha256,
                "provider_profile_matches_session": True,
                "provider_profile_matches_bundle": True,
                "adapter_contract_provider_profile_sha256": provider_profile_sha256,
                "adapter_contract_provider_profile_matches_evidence": True,
                "dispatch_roundtrip_capture_bundle_provided": True,
                "dispatch_roundtrip_provider_capture_command_count": 2,
                "dispatch_roundtrip_provider_capture_command_providers": "arrow_money",
                "dispatch_roundtrip_provider_capture_command_transports": "websocket",
                "dispatch_roundtrip_capture_bundle_provider_capture_command_count": 2,
                "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count": 0,
                "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session": True,
                "dispatch_roundtrip_provider_capture_commands_match_runtime_session": True,
                "dispatch_roundtrip_adapter_contract_provider": "arrow_money",
                "dispatch_roundtrip_adapter_contract_transport": "websocket",
                "dispatch_roundtrip_adapter_contract_market": "india_nse_index_derivatives",
                "dispatch_roundtrip_adapter_contract_exchange": "NFO",
                "dispatch_roundtrip_adapter_contract_values_stored": False,
                "dispatch_roundtrip_adapter_contract_metadata_matches_evidence": True,
                "dispatch_roundtrip_adapter_contract_matches_runtime_session": True,
                "dispatch_roundtrip_provider_profile_sha256": "",
                "dispatch_roundtrip_provider_profile_adapter": "",
                "dispatch_roundtrip_provider_profile_transports": "",
                "dispatch_roundtrip_provider_profile_capabilities": "",
                "dispatch_roundtrip_capture_bundle_provider_profile_sha256": "",
                "dispatch_roundtrip_provider_profile_matches_session": False,
                "dispatch_roundtrip_provider_profile_matches_bundle": False,
                "dispatch_roundtrip_adapter_contract_provider_profile_sha256": "",
                "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence": False,
                "dispatch_roundtrip_provider_profile_matches_runtime_session": False,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "provider_runtime_session": {"scaleup_dir": ""},
                "provider_profile": provider_profile,
                "live_session_provider_profile": provider_profile,
                "adapter_execution_contract": {
                    "provider": "arrow_money",
                    "transport": "websocket",
                    "market": "india_nse_index_derivatives",
                    "exchange": "NFO",
                    "provider_profile_sha256": provider_profile_sha256,
                    "values_stored": False,
                },
                "capture_bundle": {
                    "capture_bundle_provider_profile": provider_profile,
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "provider_profile_sha256": provider_profile_sha256,
                        "values_stored": False,
                    },
                },
                "dispatch_roundtrip_provenance": {
                    "capture_bundle_provided": True,
                    "provider_capture_command_count": 2,
                    "provider_capture_command_providers": "arrow_money",
                    "provider_capture_command_transports": "websocket",
                    "capture_bundle_provider_capture_command_count": 2,
                    "capture_bundle_provider_capture_command_missing_count": 0,
                    "capture_bundle_provider_capture_commands_match_session": True,
                    "provider_capture_commands_match_runtime_session": True,
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "values_stored": False,
                    },
                    "adapter_contract_provider": "arrow_money",
                    "adapter_contract_transport": "websocket",
                    "adapter_contract_market": "india_nse_index_derivatives",
                    "adapter_contract_exchange": "NFO",
                    "adapter_contract_values_stored": False,
                    "adapter_contract_metadata_matches_evidence": True,
                    "adapter_contract_matches_runtime_session": True,
                    "provider_profile_matches_session": False,
                    "provider_profile_matches_bundle": False,
                    "provider_profile_matches_runtime_session": False,
                    "adapter_contract_provider_profile_matches_evidence": False,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "dispatch_roundtrip_provider_profile_carried" in failed
    assert "dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_readiness"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"


def test_provider_market_data_imbalance_cutover_falls_back_to_roundtrip_config_provenance(tmp_path):
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    provider_profile_sha256 = "d" * 64
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }

    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_config_roundtrip_fallback"
    broker_readiness_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "dispatch_roundtrip_exchange": "",
                "dispatch_roundtrip_capture_provenance_consistent": False,
                "adapter_contract_provider": "arrow_money",
                "adapter_contract_transport": "websocket",
                "adapter_contract_market": "india_nse_index_derivatives",
                "adapter_contract_exchange": "NFO",
                "adapter_contract_values_stored": False,
                "adapter_contract_metadata_matches_evidence": True,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "provider_runtime_session": {"scaleup_dir": ""},
                "provider_capture_commands": provider_capture_commands,
                "capture_bundle_provider_capture_commands": provider_capture_commands,
                "adapter_execution_contract": {
                    "provider": "arrow_money",
                    "transport": "websocket",
                    "market": "india_nse_index_derivatives",
                    "exchange": "NFO",
                    "provider_profile_sha256": provider_profile_sha256,
                    "values_stored": False,
                },
                "provider_profile": provider_profile,
                "live_session_provider_profile": provider_profile,
                "capture_bundle": {
                    "provider_capture_commands": provider_capture_commands,
                    "capture_bundle_provider_capture_commands": provider_capture_commands,
                    "capture_bundle_provider_profile": provider_profile,
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "provider_profile_sha256": provider_profile_sha256,
                        "values_stored": False,
                    },
                },
                "dispatch_roundtrip_provenance": {
                    "exchange": "NFO",
                    "source_session": {
                        "timezone": "Asia/Kolkata",
                        "open_local": "09:15:00",
                        "close_local": "15:30:00",
                    },
                    "market_session": {
                        "timezone": "Asia/Kolkata",
                        "open_local": "09:15",
                        "close_local": "15:30",
                    },
                    "exchange_matches_session": True,
                    "source_session_matches_session": True,
                    "market_session_matches_session": True,
                    "metadata_consistent_with_runtime_session": True,
                    "provider_capture_command_count": 2,
                    "provider_capture_command_providers": "arrow_money",
                    "provider_capture_command_transports": "websocket",
                    "capture_bundle_provider_capture_command_count": 2,
                    "capture_bundle_provider_capture_command_missing_count": 0,
                    "capture_bundle_provider_capture_commands_match_session": True,
                    "provider_capture_commands_match_runtime_session": True,
                    "adapter_execution_contract": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "values_stored": False,
                    },
                    "adapter_contract_provider": "arrow_money",
                    "adapter_contract_transport": "websocket",
                    "adapter_contract_market": "india_nse_index_derivatives",
                    "adapter_contract_exchange": "NFO",
                    "adapter_contract_values_stored": False,
                    "adapter_contract_metadata_matches_evidence": True,
                    "adapter_contract_matches_runtime_session": True,
                    "provider_profile": provider_profile,
                    "live_session_provider_profile": provider_profile,
                    "capture_bundle_provider_profile": provider_profile,
                    "provider_profile_sha256": provider_profile_sha256,
                    "provider_profile_matches_session": True,
                    "provider_profile_matches_bundle": True,
                    "provider_profile_matches_runtime_session": True,
                    "adapter_contract_provider_profile_sha256": provider_profile_sha256,
                    "adapter_contract_provider_profile_matches_evidence": True,
                    "capture_bundle_path": str(bundle_path),
                    "capture_bundle_provided": True,
                    "capture_bundle_exists": True,
                    "capture_bundle_ready": True,
                    "capture_bundle_exchange": "NFO",
                    "capture_bundle_source_session": {
                        "timezone": "Asia/Kolkata",
                        "open_local": "09:15:00",
                        "close_local": "15:30:00",
                    },
                    "capture_bundle_market_session": {
                        "timezone": "Asia/Kolkata",
                        "open_local": "09:15",
                        "close_local": "15:30",
                    },
                    "capture_bundle_metadata_matches_session": True,
                    "capture_bundle_live_fetch_contract_metadata_matches_session": True,
                    "capture_bundle_matches_session": True,
                    "capture_bundle_exchange_matches_session": True,
                    "capture_bundle_source_session_matches_session": True,
                    "capture_bundle_market_session_matches_session": True,
                    "capture_env_template_path": str(env_template_path),
                    "capture_env_template_provided": True,
                    "capture_env_template_exists": True,
                    "capture_env_template_sha256": env_template_sha256,
                    "capture_env_template_matches_session": True,
                    "adapter_handoff_path": str(adapter_handoff_path),
                    "adapter_handoff_provided": True,
                    "adapter_handoff_exists": True,
                    "adapter_handoff_sha256": adapter_handoff_sha256,
                    "adapter_handoff_matches_session": True,
                    "consistent_with_runtime_session": True,
                    "source_credential_env_template_path": str(source_env_template_path),
                    "source_credential_env_template_exists": True,
                    "source_credential_env_template_sha256": "b" * 64,
                    "source_credential_env_template_matches_session": True,
                    "source_credential_env_template_sha256_matches_session": True,
                    "source_live_fetch_contract_available": True,
                    "source_live_fetch_contract_next_gate": "provider_fetcher",
                    "source_live_fetch_contract_command_template": (
                        "python -m hft_cli fetch-provider-live-data"
                    ),
                    "source_live_fetch_contract_exchange": "NFO",
                    "source_live_fetch_contract_market": "india_nse_index_derivatives",
                    "source_live_fetch_contract_session": {
                        "timezone": "Asia/Kolkata",
                        "open_local": "09:15:00",
                        "close_local": "15:30:00",
                    },
                    "source_live_fetch_contract_next_gate_matches_session": True,
                    "source_live_fetch_contract_command_template_matches_session": True,
                    "source_live_fetch_contract_exchange_matches_session": True,
                    "source_live_fetch_contract_market_matches_session": True,
                    "source_live_fetch_contract_session_matches_session": True,
                    "source_provenance_consistent_with_runtime_session": True,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_cutover_config_roundtrip_fallback"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_source_session_close_local"] == "15:30:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_profile_transports"] == "file;rest;websocket"
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["open_local"] == "09:15:00"
    assert not config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["close_local"] == "15:30:00"
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert not manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["session"]["open_local"] == "09:15:00"


def test_provider_market_data_imbalance_cutover_carries_provider_dispatch_roundtrip_paths(tmp_path):
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_with_roundtrip"
    broker_readiness_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                "dispatch_roundtrip_provided": True,
                "dispatch_roundtrip_ready": True,
                "dispatch_roundtrip_failed_checks": 0,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "broker_inputs": {
                    "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                    "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                },
                "provider_runtime_session": {"scaleup_dir": ""},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_cutover_with_roundtrip"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert Path(summary.loc[0, "provider_dispatch_roundtrip_dir"]) == provider_roundtrip_dir
    assert Path(summary.loc[0, "dispatch_roundtrip_dir"]) == nested_roundtrip_dir
    assert bool(summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "dispatch_roundtrip_failed_checks"]) == 0
    assert config["cutover_inputs"]["provider_dispatch_roundtrip_dir"] == str(provider_roundtrip_dir)
    assert config["cutover_inputs"]["dispatch_roundtrip_dir"] == str(nested_roundtrip_dir)
    assert manifest["inputs"]["provider_dispatch_roundtrip"]["path"] == str(provider_roundtrip_dir)
    assert manifest["inputs"]["dispatch_roundtrip"]["path"] == str(nested_roundtrip_dir)


def test_provider_market_data_imbalance_cutover_carries_broker_vendor_batch(tmp_path):
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_with_vendor_batch"
    broker_readiness_dir.mkdir(parents=True)
    broker_vendor = _vendor_market_data_batch_config()
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                "dispatch_roundtrip_provided": True,
                "dispatch_roundtrip_ready": True,
                "dispatch_roundtrip_failed_checks": 0,
                "dispatch_roundtrip_vendor_market_data_batch_ready": False,
                "broker_dispatch_roundtrip_vendor_market_data_batch_provided": True,
                "broker_dispatch_roundtrip_vendor_market_data_batch_ready": True,
                "broker_dispatch_roundtrip_vendor_market_data_batch_adapter": "arrow_money",
                "broker_dispatch_roundtrip_vendor_market_data_batch_kind": "ticks",
                "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type": (
                    "vendor_market_data_batch_pipeline"
                ),
                "broker_dispatch_roundtrip_vendor_market_data_batch_market": "india_nse_index_derivatives",
                "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count": 2,
                "broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files": 2,
                "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage": 1.0,
                "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted": True,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "broker_inputs": {
                    "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                    "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                },
                "provider_runtime_session": {"scaleup_dir": ""},
                "dispatch_roundtrip_vendor_market_data_batch": {
                    "provided": False,
                    "ready": False,
                    "datasets": [],
                },
                "broker_dispatch_roundtrip_vendor_market_data_batch": broker_vendor,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_cutover_with_vendor_batch"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_cutover_runbook.md").read_text(encoding="utf-8")
    assert not report.ready
    assert "dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_cutover_preserves_upstream_vendor_batch(tmp_path):
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_with_upstream_vendor_batch"
    broker_readiness_dir.mkdir(parents=True)
    broker_vendor = _vendor_market_data_batch_config()
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                "dispatch_roundtrip_provided": True,
                "dispatch_roundtrip_ready": True,
                "dispatch_roundtrip_failed_checks": 0,
                "upstream_dispatch_roundtrip_vendor_market_data_batch_ready": False,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided": True,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready": True,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter": "arrow_money",
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_kind": "ticks",
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type": (
                    "vendor_market_data_batch_pipeline"
                ),
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_market": (
                    "india_nse_index_derivatives"
                ),
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count": 2,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files": 2,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage": 1.0,
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted": True,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "broker_inputs": {
                    "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                    "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                },
                "provider_runtime_session": {"scaleup_dir": ""},
                "upstream_dispatch_roundtrip_vendor_market_data_batch": {
                    "provided": False,
                    "ready": False,
                    "datasets": [],
                },
                "upstream_broker_dispatch_roundtrip_vendor_market_data_batch": broker_vendor,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_cutover_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_cutover_runbook.md").read_text(encoding="utf-8")

    assert not report.ready
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_cutover_preserves_upstream_roundtrip(tmp_path):
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    upstream_nested_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    (upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready\ntrue\n",
        encoding="utf-8",
    )
    broker_readiness_dir = tmp_path / "provider_imbalance_broker_readiness_with_upstream_roundtrip"
    broker_readiness_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "scaleup_dir": "",
                "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                "dispatch_roundtrip_provided": True,
                "dispatch_roundtrip_ready": True,
                "dispatch_roundtrip_failed_checks": 0,
                "upstream_provider_dispatch_roundtrip_dir": str(upstream_provider_dir),
                "upstream_dispatch_roundtrip_dir": str(upstream_nested_dir),
                "upstream_dispatch_roundtrip_provided": True,
                "upstream_dispatch_roundtrip_ready": True,
                "upstream_dispatch_roundtrip_failed_checks": 0,
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_summary.csv",
        index=False,
    )
    (
        broker_readiness_dir / "provider_market_data_imbalance_broker_readiness_config.json"
    ).write_text(
        json.dumps(
            {
                "broker_inputs": {
                    "provider_dispatch_roundtrip_dir": str(provider_roundtrip_dir),
                    "dispatch_roundtrip_dir": str(nested_roundtrip_dir),
                    "upstream_provider_dispatch_roundtrip_dir": str(upstream_provider_dir),
                    "upstream_dispatch_roundtrip_dir": str(upstream_nested_dir),
                },
                "provider_runtime_session": {"scaleup_dir": ""},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_cutover_with_upstream_roundtrip"

    report = write_provider_market_data_imbalance_cutover(
        broker_readiness_dir,
        out_dir,
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_cutover_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert not report.ready
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["cutover_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(upstream_provider_dir)
    assert config["cutover_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"] == str(upstream_provider_dir)
    assert manifest["inputs"]["upstream_dispatch_roundtrip"]["path"] == str(upstream_nested_dir)


def test_provider_market_data_imbalance_cutover_blocks_unready_broker_readiness(tmp_path):
    broker_dir = tmp_path / "provider_imbalance_broker_readiness"
    broker_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_readiness_dir": "",
                "runtime_session_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(broker_dir / "provider_market_data_imbalance_broker_readiness_summary.csv", index=False)
    (broker_dir / "provider_market_data_imbalance_broker_readiness_config.json").write_text(
        json.dumps({"provider_runtime_session": {"scaleup_dir": ""}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_cutover(
        broker_dir,
        tmp_path / "provider_imbalance_cutover",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_broker_readiness_ready" in failed
    assert "nested_scaleup_config_exists" in failed
    assert "nested_broker_readiness_summary_exists" in failed
    assert "nested_runtime_session_summary_exists" in failed
    assert "cutover_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"
    assert not (report.output_dir / "cutover" / "cutover_summary.csv").exists()


def test_cli_provider_market_data_imbalance_cutover_blocks_missing_route_proof(tmp_path):
    broker_readiness = _write_ready_provider_imbalance_broker_readiness(tmp_path)
    out_dir = tmp_path / "cli_provider_imbalance_cutover"

    code = main(
        [
            "review-provider-market-data-imbalance-cutover",
            "--broker-readiness",
            str(broker_readiness.output_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_cutover_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not bool(summary.loc[0, "cutover_ready"])
    assert summary.loc[0, "next_gate"] == "review-route-readiness"


def test_provider_market_data_imbalance_route_enable_accepts_ready_cutover(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    out_dir = tmp_path / "provider_imbalance_route_enable"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_action_queue.csv")
    route_summary = pd.read_csv(out_dir / "route_enable" / "route_enable_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary.loc[0, "provider_cutover_ready"])
    assert bool(summary.loc[0, "route_enable_ready"])
    assert bool(summary.loc[0, "route_enabled"])
    assert bool(route_summary.loc[0, "ready"])
    assert summary.loc[0, "route_state"] == "enabled"
    assert int(summary.loc[0, "upload_orders"]) > 0
    assert summary.loc[0, "next_gate"] == "plan-broker-dispatch"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "plan-broker-dispatch"
    assert config["route_enable"]["ready"]
    assert manifest["run_type"] == "provider_market_data_imbalance_route_enable"
    assert "provider_cutover_dir" in manifest["inputs"]
    assert "route_enable" in manifest["inputs"]
    assert "cutover" in manifest["inputs"]
    assert "upload_pack" in manifest["inputs"]
    assert "order_export" in manifest["inputs"]


def test_provider_market_data_imbalance_route_enable_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
        route_readiness_dir=route_readiness.output_dir,
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    cutover = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_route_enable"

    report = write_provider_market_data_imbalance_route_enable(
        cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_route_enable_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["source_live_fetch_contract_exchange"] == "NFO"
    assert summary["source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert not bool(summary["adapter_contract_values_stored"])
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["transport"] == "websocket"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["capture_bundle"]["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_matches_session"] is True
    assert config["capture_bundle"]["provider_profile_matches_bundle"] is True
    assert (
        config["capture_bundle"]["adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_cutover"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_cutover"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["provider_cutover"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_cutover"]["exchange"] == "NFO"
    assert config["provider_cutover"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_cutover"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_cutover"]["source_live_fetch_contract_available"] is True
    assert config["provider_cutover"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_cutover"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_cutover"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_cutover"]["provider_profile_matches_bundle"] is True
    assert config["provider_cutover"]["provider_capture_command_count"] == 2
    assert config["provider_cutover"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["metadata_matches_session"] is True
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["adapter_contract_metadata_matches_evidence"] is True
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert "Exchange: NFO" in runbook
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_route_enable_blocks_missing_adapter_execution_contract(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(summary_path)
    cutover_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        cutover_summary.loc[0, column] = ""
    cutover_summary.loc[0, "adapter_contract_values_stored"] = True
    cutover_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    cutover_summary.to_csv(summary_path, index=False)
    config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_cutover_adapter_execution_contract_carried" in failed
    assert "provider_cutover_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_cutover"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"


def test_provider_market_data_imbalance_route_enable_blocks_missing_provider_profile(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(summary_path)
    cutover_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        cutover_summary[column] = cutover_summary[column].astype("object")
        cutover_summary.loc[0, column] = ""
    cutover_summary.loc[0, "provider_profile_matches_session"] = False
    cutover_summary.loc[0, "provider_profile_matches_bundle"] = False
    cutover_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    cutover_summary.to_csv(summary_path, index=False)

    config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_cutover_provider_profile_carried" in failed
    assert "provider_cutover_provider_profile_matches_session" in failed
    assert "provider_cutover_provider_profile_matches_bundle" in failed
    assert "provider_cutover_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_cutover"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"


def test_provider_market_data_imbalance_route_enable_blocks_missing_roundtrip_adapter_contract(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(summary_path)
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    cutover_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    cutover_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in cutover_summary.columns:
            cutover_summary[column] = cutover_summary[column].astype("object")
        cutover_summary.loc[0, column] = ""
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = True
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = False
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = False
    cutover_summary.to_csv(summary_path, index=False)

    config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"

    def _drop_roundtrip_adapter_contract(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        provenance.pop("adapter_execution_contract", None)
        for key in (
            "adapter_contract_provider",
            "adapter_contract_transport",
            "adapter_contract_market",
            "adapter_contract_exchange",
            "adapter_contract_values_stored",
            "adapter_contract_metadata_matches_evidence",
        ):
            provenance.pop(key, None)
        provenance["adapter_contract_matches_runtime_session"] = False

    _mutate_json(config_path, _drop_roundtrip_adapter_contract)

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable_missing_roundtrip_adapter_contract",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_cutover_dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "provider_cutover_dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "provider_cutover_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "component"] == "provider_cutover"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_cutover"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"


def test_provider_market_data_imbalance_route_enable_blocks_missing_roundtrip_provider_profile(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(summary_path)
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    cutover_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    cutover_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    cutover_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in cutover_summary.columns:
            cutover_summary[column] = cutover_summary[column].astype("object")
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = False
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
    ):
        if column in cutover_summary.columns:
            cutover_summary[column] = cutover_summary[column].astype("object")
        cutover_summary.loc[0, column] = ""
    cutover_summary.loc[0, "dispatch_roundtrip_provider_profile_auth_required"] = False
    cutover_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_session"] = False
    cutover_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_bundle"] = False
    cutover_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_runtime_session"] = False
    cutover_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = False
    cutover_summary.to_csv(summary_path, index=False)

    config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"

    def _drop_roundtrip_provider_profile(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        for key in (
            "provider_profile",
            "live_session_provider_profile",
            "capture_bundle_provider_profile",
            "provider_profile_sha256",
            "provider_profile_matches_session",
            "provider_profile_matches_bundle",
            "provider_profile_matches_runtime_session",
            "adapter_contract_provider_profile_sha256",
            "adapter_contract_provider_profile_matches_evidence",
        ):
            provenance.pop(key, None)
        contract = provenance.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        provenance["provider_profile_matches_session"] = False
        provenance["provider_profile_matches_bundle"] = False
        provenance["provider_profile_matches_runtime_session"] = False
        provenance["adapter_contract_provider_profile_matches_evidence"] = False

    _mutate_json(config_path, _drop_roundtrip_provider_profile)

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable_missing_roundtrip_provider_profile",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_cutover_dispatch_roundtrip_provider_profile_carried" in failed
    assert "provider_cutover_dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "provider_cutover_dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "provider_cutover_dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "provider_cutover_dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "component"] == "provider_cutover"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_cutover"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"


def test_provider_market_data_imbalance_route_enable_carries_roundtrip_capture_bundle_provenance(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    cutover_summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(cutover_summary_path)
    provider_profile_sha256 = str(cutover_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    cutover_summary["dispatch_roundtrip_capture_bundle_path"] = str(bundle_path)
    cutover_summary["dispatch_roundtrip_capture_bundle_provided"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_exists"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_ready"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_env_template_path"] = str(env_template_path)
    cutover_summary["dispatch_roundtrip_capture_env_template_provided"] = True
    cutover_summary["dispatch_roundtrip_capture_env_template_exists"] = True
    cutover_summary["dispatch_roundtrip_capture_env_template_sha256"] = env_template_sha256
    cutover_summary["dispatch_roundtrip_capture_env_template_matches_session"] = True
    cutover_summary["dispatch_roundtrip_adapter_handoff_path"] = str(adapter_handoff_path)
    cutover_summary["dispatch_roundtrip_adapter_handoff_provided"] = True
    cutover_summary["dispatch_roundtrip_adapter_handoff_exists"] = True
    cutover_summary["dispatch_roundtrip_adapter_handoff_sha256"] = adapter_handoff_sha256
    cutover_summary["dispatch_roundtrip_adapter_handoff_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_provenance_consistent"] = True
    cutover_summary["dispatch_roundtrip_exchange"] = "NFO"
    cutover_summary["dispatch_roundtrip_source_session_timezone"] = "Asia/Kolkata"
    cutover_summary["dispatch_roundtrip_source_session_open_local"] = "09:15:00"
    cutover_summary["dispatch_roundtrip_source_session_close_local"] = "15:30:00"
    cutover_summary["dispatch_roundtrip_market_session_timezone"] = "Asia/Kolkata"
    cutover_summary["dispatch_roundtrip_market_session_open_local"] = "09:15"
    cutover_summary["dispatch_roundtrip_market_session_close_local"] = "15:30"
    cutover_summary["dispatch_roundtrip_exchange_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_session_matches_session"] = True
    cutover_summary["dispatch_roundtrip_market_session_matches_session"] = True
    cutover_summary["dispatch_roundtrip_metadata_consistent"] = True
    cutover_summary["source_credential_env_template_path"] = str(source_env_template_path)
    cutover_summary["source_credential_env_template_exists"] = True
    cutover_summary["source_credential_env_template_sha256"] = "a" * 64
    cutover_summary["source_live_fetch_contract_available"] = True
    cutover_summary["source_live_fetch_contract_next_gate"] = "provider_fetcher"
    cutover_summary["source_live_fetch_contract_command_template"] = "python -m hft_cli fetch-provider-live-data"
    cutover_summary["dispatch_roundtrip_source_credential_env_template_path"] = str(source_env_template_path)
    cutover_summary["dispatch_roundtrip_source_credential_env_template_exists"] = True
    cutover_summary["dispatch_roundtrip_source_credential_env_template_sha256"] = "a" * 64
    cutover_summary["dispatch_roundtrip_source_credential_env_template_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_available"] = True
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"] = "provider_fetcher"
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_command_template"] = (
        "python -m hft_cli fetch-provider-live-data"
    )
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] = "NFO"
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_market"] = "india_nse_index_derivatives"
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_session_timezone"] = "Asia/Kolkata"
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] = "09:15:00"
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_session_close_local"] = "15:30:00"
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"] = True
    cutover_summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_exchange"] = "NFO"
    cutover_summary["dispatch_roundtrip_capture_bundle_source_session_timezone"] = "Asia/Kolkata"
    cutover_summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] = "09:15:00"
    cutover_summary["dispatch_roundtrip_capture_bundle_source_session_close_local"] = "15:30:00"
    cutover_summary["dispatch_roundtrip_capture_bundle_market_session_timezone"] = "Asia/Kolkata"
    cutover_summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] = "09:15"
    cutover_summary["dispatch_roundtrip_capture_bundle_market_session_close_local"] = "15:30"
    cutover_summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"] = True
    cutover_summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"] = True
    cutover_summary["dispatch_roundtrip_provider_capture_command_count"] = 2
    cutover_summary["dispatch_roundtrip_provider_capture_command_providers"] = "arrow_money"
    cutover_summary["dispatch_roundtrip_provider_capture_command_transports"] = "websocket"
    cutover_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    cutover_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    cutover_summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    cutover_summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    cutover_summary["dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    cutover_summary["dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    cutover_summary["dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    cutover_summary["dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    cutover_summary["dispatch_roundtrip_adapter_contract_values_stored"] = False
    cutover_summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] = provider_profile_sha256
    cutover_summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    cutover_summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = True
    cutover_summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    cutover_summary["dispatch_roundtrip_provider_profile_sha256"] = provider_profile_sha256
    cutover_summary["dispatch_roundtrip_provider_profile_adapter"] = provider_profile["adapter"]
    cutover_summary["dispatch_roundtrip_provider_profile_auth_required"] = provider_profile["auth_required"]
    cutover_summary["dispatch_roundtrip_provider_profile_transports"] = provider_profile["transports"]
    cutover_summary["dispatch_roundtrip_provider_profile_capabilities"] = provider_profile["capabilities"]
    cutover_summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] = provider_profile_sha256
    cutover_summary["dispatch_roundtrip_provider_profile_matches_session"] = True
    cutover_summary["dispatch_roundtrip_provider_profile_matches_bundle"] = True
    cutover_summary["dispatch_roundtrip_provider_profile_matches_runtime_session"] = True
    cutover_summary["dispatch_roundtrip_source_provenance_consistent"] = True
    cutover_summary.to_csv(cutover_summary_path, index=False)

    cutover_config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    cutover_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = cutover_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    cutover_config["capture_bundle"] = capture_bundle_config
    cutover_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_sha256": env_template_sha256,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_sha256": "a" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    cutover_config_path.write_text(
        json.dumps(cutover_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_route_enable_with_roundtrip_provenance"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_route_enable_runbook.md").read_text(encoding="utf-8")
    checks = report.checks.set_index("check")
    assert report.ready
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert len(summary["dispatch_roundtrip_capture_env_template_sha256"]) == 64
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert len(summary["dispatch_roundtrip_adapter_handoff_sha256"]) == 64
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(checks.loc["provider_cutover_dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(
        checks.loc["provider_cutover_dispatch_roundtrip_adapter_execution_contract_matches_evidence", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_cutover_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_cutover_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["provider_cutover_dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["provider_cutover_dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(
        checks.loc["provider_cutover_dispatch_roundtrip_adapter_provider_profile_matches_evidence", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_cutover_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_live_fetch_contract_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert (
        config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert config["provider_cutover"]["dispatch_roundtrip_adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["provider_cutover"]["dispatch_roundtrip_adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["provider_cutover"]["dispatch_roundtrip_source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"][
        "provider_capture_commands_match_runtime_session"
    ]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_route_enable_falls_back_to_roundtrip_config_provenance(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    cutover_summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(cutover_summary_path)
    provider_profile_sha256 = str(cutover_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    blank_columns = [
        "dispatch_roundtrip_exchange",
        "dispatch_roundtrip_source_session_timezone",
        "dispatch_roundtrip_source_session_open_local",
        "dispatch_roundtrip_source_session_close_local",
        "dispatch_roundtrip_market_session_timezone",
        "dispatch_roundtrip_market_session_open_local",
        "dispatch_roundtrip_market_session_close_local",
        "dispatch_roundtrip_exchange_matches_session",
        "dispatch_roundtrip_source_session_matches_session",
        "dispatch_roundtrip_market_session_matches_session",
        "dispatch_roundtrip_metadata_consistent",
        "dispatch_roundtrip_provider_capture_command_count",
        "dispatch_roundtrip_provider_capture_command_providers",
        "dispatch_roundtrip_provider_capture_command_transports",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
        "dispatch_roundtrip_adapter_contract_values_stored",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_auth_required",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_matches_session",
        "dispatch_roundtrip_provider_profile_matches_bundle",
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        "dispatch_roundtrip_capture_bundle_path",
        "dispatch_roundtrip_capture_bundle_ready",
        "dispatch_roundtrip_capture_bundle_exchange",
        "dispatch_roundtrip_capture_bundle_source_session_open_local",
        "dispatch_roundtrip_capture_bundle_market_session_open_local",
        "dispatch_roundtrip_capture_bundle_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_matches_session",
        "dispatch_roundtrip_capture_env_template_path",
        "dispatch_roundtrip_capture_env_template_sha256",
        "dispatch_roundtrip_capture_env_template_matches_session",
        "dispatch_roundtrip_adapter_handoff_path",
        "dispatch_roundtrip_adapter_handoff_sha256",
        "dispatch_roundtrip_adapter_handoff_matches_session",
        "dispatch_roundtrip_source_credential_env_template_path",
        "dispatch_roundtrip_source_credential_env_template_matches_session",
        "dispatch_roundtrip_source_live_fetch_contract_exchange",
        "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
        "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
        "dispatch_roundtrip_source_provenance_consistent",
    ]
    for column in blank_columns:
        cutover_summary[column] = ""
    cutover_summary["dispatch_roundtrip_capture_provenance_consistent"] = False
    cutover_summary.to_csv(cutover_summary_path, index=False)

    cutover_config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    cutover_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = cutover_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    cutover_config["capture_bundle"] = capture_bundle_config
    cutover_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_provided": True,
        "capture_bundle_exists": True,
        "capture_bundle_ready": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_provided": True,
        "capture_env_template_exists": True,
        "capture_env_template_sha256": env_template_sha256,
        "capture_env_template_matches_session": True,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_provided": True,
        "adapter_handoff_exists": True,
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "adapter_handoff_matches_session": True,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_exists": True,
        "source_credential_env_template_sha256": "c" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    cutover_config_path.write_text(
        json.dumps(cutover_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_route_enable_config_roundtrip_fallback"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert not config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"] == (
        provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert not manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"


def test_provider_market_data_imbalance_route_enable_carries_cutover_dispatch_roundtrip_paths(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    cutover_summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(cutover_summary_path)
    cutover_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    cutover_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    cutover_summary["dispatch_roundtrip_provided"] = True
    cutover_summary["dispatch_roundtrip_ready"] = True
    cutover_summary["dispatch_roundtrip_failed_checks"] = 0
    cutover_summary.to_csv(cutover_summary_path, index=False)
    cutover_config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    cutover_config.setdefault("cutover_inputs", {})
    cutover_config["cutover_inputs"]["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    cutover_config["cutover_inputs"]["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    cutover_config_path.write_text(
        json.dumps(cutover_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_route_enable_with_roundtrip"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert Path(summary.loc[0, "provider_dispatch_roundtrip_dir"]) == provider_roundtrip_dir
    assert Path(summary.loc[0, "dispatch_roundtrip_dir"]) == nested_roundtrip_dir
    assert bool(summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "dispatch_roundtrip_failed_checks"]) == 0
    assert config["route_enable_inputs"]["provider_dispatch_roundtrip_dir"] == str(provider_roundtrip_dir)
    assert config["route_enable_inputs"]["dispatch_roundtrip_dir"] == str(nested_roundtrip_dir)
    assert manifest["inputs"]["provider_dispatch_roundtrip"]["path"] == str(provider_roundtrip_dir)
    assert manifest["inputs"]["dispatch_roundtrip"]["path"] == str(nested_roundtrip_dir)


def test_provider_market_data_imbalance_route_enable_carries_cutover_vendor_batch(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    cutover_summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(cutover_summary_path)
    cutover_summary["dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_market"] = "india_nse_index_derivatives"
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    cutover_summary["broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    cutover_summary.to_csv(cutover_summary_path, index=False)

    cutover_config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    cutover_config["dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    cutover_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    cutover_config_path.write_text(
        json.dumps(cutover_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_route_enable_with_vendor_batch"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_route_enable_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert "dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_route_enable_preserves_upstream_vendor_batch(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    cutover_summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(cutover_summary_path)
    cutover_summary["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_market"] = (
        "india_nse_index_derivatives"
    )
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    cutover_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    cutover_summary.to_csv(cutover_summary_path, index=False)

    cutover_config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    cutover_config["upstream_dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    cutover_config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    cutover_config_path.write_text(
        json.dumps(cutover_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_route_enable_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_route_enable_runbook.md").read_text(
        encoding="utf-8"
    )

    assert report.ready
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_route_enable_preserves_upstream_roundtrip(tmp_path):
    provider_cutover = _write_ready_provider_imbalance_cutover_with_route_proof(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    upstream_nested_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    (upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready\ntrue\n",
        encoding="utf-8",
    )

    cutover_summary_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_summary.csv"
    cutover_summary = pd.read_csv(cutover_summary_path)
    cutover_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    cutover_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    cutover_summary["dispatch_roundtrip_provided"] = True
    cutover_summary["dispatch_roundtrip_ready"] = True
    cutover_summary["dispatch_roundtrip_failed_checks"] = 0
    cutover_summary["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    cutover_summary["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    cutover_summary["upstream_dispatch_roundtrip_provided"] = True
    cutover_summary["upstream_dispatch_roundtrip_ready"] = True
    cutover_summary["upstream_dispatch_roundtrip_failed_checks"] = 0
    cutover_summary.to_csv(cutover_summary_path, index=False)

    cutover_config_path = provider_cutover.output_dir / "provider_market_data_imbalance_cutover_config.json"
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    cutover_inputs = cutover_config.setdefault("cutover_inputs", {})
    cutover_inputs["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    cutover_inputs["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    cutover_inputs["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    cutover_inputs["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    cutover_config_path.write_text(
        json.dumps(cutover_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_route_enable_with_upstream_roundtrip"

    report = write_provider_market_data_imbalance_route_enable(
        provider_cutover.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_route_enable_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report.ready
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["route_enable_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(upstream_provider_dir)
    assert config["route_enable_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"] == str(upstream_provider_dir)
    assert manifest["inputs"]["upstream_dispatch_roundtrip"]["path"] == str(upstream_nested_dir)


def test_provider_market_data_imbalance_route_enable_blocks_unready_cutover(tmp_path):
    cutover_dir = tmp_path / "provider_imbalance_cutover"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "cutover_ready": False,
                "provider_broker_readiness_dir": "",
                "cutover_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(cutover_dir / "provider_market_data_imbalance_cutover_summary.csv", index=False)
    (cutover_dir / "provider_market_data_imbalance_cutover_config.json").write_text(
        json.dumps({"provider_broker_readiness_config": {"broker_inputs": {}}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_route_enable(
        cutover_dir,
        tmp_path / "provider_imbalance_route_enable",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_imbalance_cutover_ready" in failed
    assert "generic_cutover_input_resolved" in failed
    assert "upload_pack_input_resolved" in failed
    assert "route_enable_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"
    assert not (report.output_dir / "route_enable" / "route_enable_summary.csv").exists()


def test_cli_provider_market_data_imbalance_route_enable_blocks_unready_cutover(tmp_path):
    cutover_dir = tmp_path / "provider_imbalance_cutover"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "cutover_ready": False,
                "provider_broker_readiness_dir": "",
                "cutover_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(cutover_dir / "provider_market_data_imbalance_cutover_summary.csv", index=False)
    (cutover_dir / "provider_market_data_imbalance_cutover_config.json").write_text(
        json.dumps({"provider_broker_readiness_config": {"broker_inputs": {}}}, indent=2) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_provider_imbalance_route_enable"

    code = main(
        [
            "review-provider-market-data-imbalance-route-enable",
            "--provider-cutover",
            str(cutover_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_route_enable_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not bool(summary.loc[0, "route_enable_ready"])
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-cutover"


def test_provider_market_data_imbalance_broker_dispatch_accepts_ready_route_enable(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    out_dir = tmp_path / "provider_imbalance_broker_dispatch"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_action_queue.csv")
    dispatch_summary = pd.read_csv(out_dir / "broker_dispatch" / "broker_dispatch_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    assert report.ready
    assert bool(summary.loc[0, "provider_route_enable_ready"])
    assert bool(summary.loc[0, "broker_dispatch_ready"])
    assert bool(summary.loc[0, "route_enabled"])
    assert bool(dispatch_summary.loc[0, "ready"])
    assert summary.loc[0, "dispatch_state"] == "armed_dry_run"
    assert int(summary.loc[0, "dispatch_orders"]) > 0
    assert summary.loc[0, "next_gate"] == "prepare-broker-dispatch-send"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "prepare-broker-dispatch-send"
    assert config["broker_dispatch"]["ready"]
    assert manifest["run_type"] == "provider_market_data_imbalance_broker_dispatch"
    assert "provider_route_enable_dir" in manifest["inputs"]
    assert "route_enable" in manifest["inputs"]
    assert "upload_pack" in manifest["inputs"]
    assert "broker_dispatch" in manifest["inputs"]


def test_provider_market_data_imbalance_broker_dispatch_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
        route_readiness_dir=route_readiness.output_dir,
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    cutover = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )
    route_enable = write_provider_market_data_imbalance_route_enable(
        cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch"

    report = write_provider_market_data_imbalance_broker_dispatch(
        route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["source_live_fetch_contract_exchange"] == "NFO"
    assert summary["source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert not bool(summary["adapter_contract_values_stored"])
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["capture_bundle"]["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_matches_session"] is True
    assert config["capture_bundle"]["provider_profile_matches_bundle"] is True
    assert (
        config["capture_bundle"]["adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["transport"] == "websocket"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_route_enable"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["provider_route_enable"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["provider_route_enable"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_route_enable"]["exchange"] == "NFO"
    assert config["provider_route_enable"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_route_enable"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_route_enable"]["source_live_fetch_contract_available"] is True
    assert config["provider_route_enable"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_route_enable"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_route_enable"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_route_enable"]["provider_profile_matches_bundle"] is True
    assert config["provider_route_enable"]["provider_capture_command_count"] == 2
    assert config["provider_route_enable"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["metadata_matches_session"] is True
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["adapter_contract_metadata_matches_evidence"] is True
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert "Exchange: NFO" in runbook
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_broker_dispatch_blocks_missing_adapter_execution_contract(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(summary_path)
    route_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        route_summary.loc[0, column] = ""
    route_summary.loc[0, "adapter_contract_values_stored"] = True
    route_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    route_summary.to_csv(summary_path, index=False)
    config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_route_enable_adapter_execution_contract_carried" in failed
    assert "provider_route_enable_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_route_enable"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-enable"


def test_provider_market_data_imbalance_broker_dispatch_blocks_missing_provider_profile(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(summary_path)
    route_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        route_summary[column] = route_summary[column].astype("object")
        route_summary.loc[0, column] = ""
    route_summary.loc[0, "provider_profile_matches_session"] = False
    route_summary.loc[0, "provider_profile_matches_bundle"] = False
    route_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    route_summary.to_csv(summary_path, index=False)

    config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_route_enable_provider_profile_carried" in failed
    assert "provider_route_enable_provider_profile_matches_session" in failed
    assert "provider_route_enable_provider_profile_matches_bundle" in failed
    assert "provider_route_enable_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_route_enable"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-enable"


def test_provider_market_data_imbalance_broker_dispatch_blocks_missing_roundtrip_adapter_contract(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(summary_path)
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    route_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    route_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in route_summary.columns:
            route_summary[column] = route_summary[column].astype("object")
        route_summary.loc[0, column] = ""
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = True
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = False
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = False
    route_summary.to_csv(summary_path, index=False)

    config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"

    def _drop_roundtrip_adapter_contract(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        provenance.pop("adapter_execution_contract", None)
        for key in (
            "adapter_contract_provider",
            "adapter_contract_transport",
            "adapter_contract_market",
            "adapter_contract_exchange",
            "adapter_contract_values_stored",
            "adapter_contract_metadata_matches_evidence",
        ):
            provenance.pop(key, None)
        provenance["adapter_contract_matches_runtime_session"] = False

    _mutate_json(config_path, _drop_roundtrip_adapter_contract)

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_missing_roundtrip_adapter_contract",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_route_enable_dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "provider_route_enable_dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "provider_route_enable_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "component"] == "provider_route_enable"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_route_enable"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-enable"


def test_provider_market_data_imbalance_broker_dispatch_blocks_missing_roundtrip_provider_profile(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(summary_path)
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    route_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    route_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    route_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in route_summary.columns:
            route_summary[column] = route_summary[column].astype("object")
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = False
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
    ):
        if column in route_summary.columns:
            route_summary[column] = route_summary[column].astype("object")
        route_summary.loc[0, column] = ""
    route_summary.loc[0, "dispatch_roundtrip_provider_profile_auth_required"] = False
    route_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_session"] = False
    route_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_bundle"] = False
    route_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_runtime_session"] = False
    route_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = False
    route_summary.to_csv(summary_path, index=False)

    config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"

    def _drop_roundtrip_provider_profile(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        for key in (
            "provider_profile",
            "live_session_provider_profile",
            "capture_bundle_provider_profile",
            "provider_profile_sha256",
            "provider_profile_matches_session",
            "provider_profile_matches_bundle",
            "provider_profile_matches_runtime_session",
            "adapter_contract_provider_profile_sha256",
            "adapter_contract_provider_profile_matches_evidence",
        ):
            provenance.pop(key, None)
        contract = provenance.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        provenance["provider_profile_matches_session"] = False
        provenance["provider_profile_matches_bundle"] = False
        provenance["provider_profile_matches_runtime_session"] = False
        provenance["adapter_contract_provider_profile_matches_evidence"] = False

    _mutate_json(config_path, _drop_roundtrip_provider_profile)

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_missing_roundtrip_provider_profile",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_route_enable_dispatch_roundtrip_provider_profile_carried" in failed
    assert "provider_route_enable_dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "provider_route_enable_dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "provider_route_enable_dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "provider_route_enable_dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "component"] == "provider_route_enable"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_route_enable"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-enable"


def test_provider_market_data_imbalance_broker_dispatch_carries_roundtrip_capture_bundle_provenance(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    route_summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(route_summary_path)
    provider_profile_sha256 = str(route_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    route_summary["dispatch_roundtrip_capture_bundle_path"] = str(bundle_path)
    route_summary["dispatch_roundtrip_capture_bundle_provided"] = True
    route_summary["dispatch_roundtrip_capture_bundle_exists"] = True
    route_summary["dispatch_roundtrip_capture_bundle_ready"] = True
    route_summary["dispatch_roundtrip_capture_bundle_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_env_template_path"] = str(env_template_path)
    route_summary["dispatch_roundtrip_capture_env_template_provided"] = True
    route_summary["dispatch_roundtrip_capture_env_template_exists"] = True
    route_summary["dispatch_roundtrip_capture_env_template_sha256"] = env_template_sha256
    route_summary["dispatch_roundtrip_capture_env_template_matches_session"] = True
    route_summary["dispatch_roundtrip_adapter_handoff_path"] = str(adapter_handoff_path)
    route_summary["dispatch_roundtrip_adapter_handoff_provided"] = True
    route_summary["dispatch_roundtrip_adapter_handoff_exists"] = True
    route_summary["dispatch_roundtrip_adapter_handoff_sha256"] = adapter_handoff_sha256
    route_summary["dispatch_roundtrip_adapter_handoff_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_provenance_consistent"] = True
    route_summary["dispatch_roundtrip_exchange"] = "NFO"
    route_summary["dispatch_roundtrip_source_session_timezone"] = "Asia/Kolkata"
    route_summary["dispatch_roundtrip_source_session_open_local"] = "09:15:00"
    route_summary["dispatch_roundtrip_source_session_close_local"] = "15:30:00"
    route_summary["dispatch_roundtrip_market_session_timezone"] = "Asia/Kolkata"
    route_summary["dispatch_roundtrip_market_session_open_local"] = "09:15"
    route_summary["dispatch_roundtrip_market_session_close_local"] = "15:30"
    route_summary["dispatch_roundtrip_exchange_matches_session"] = True
    route_summary["dispatch_roundtrip_source_session_matches_session"] = True
    route_summary["dispatch_roundtrip_market_session_matches_session"] = True
    route_summary["dispatch_roundtrip_metadata_consistent"] = True
    route_summary["source_credential_env_template_path"] = str(source_env_template_path)
    route_summary["source_credential_env_template_exists"] = True
    route_summary["source_credential_env_template_sha256"] = "a" * 64
    route_summary["source_live_fetch_contract_available"] = True
    route_summary["source_live_fetch_contract_next_gate"] = "provider_fetcher"
    route_summary["source_live_fetch_contract_command_template"] = "python -m hft_cli fetch-provider-live-data"
    route_summary["dispatch_roundtrip_source_credential_env_template_path"] = str(source_env_template_path)
    route_summary["dispatch_roundtrip_source_credential_env_template_exists"] = True
    route_summary["dispatch_roundtrip_source_credential_env_template_sha256"] = "a" * 64
    route_summary["dispatch_roundtrip_source_credential_env_template_matches_session"] = True
    route_summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"] = True
    route_summary["dispatch_roundtrip_source_live_fetch_contract_available"] = True
    route_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"] = "provider_fetcher"
    route_summary["dispatch_roundtrip_source_live_fetch_contract_command_template"] = (
        "python -m hft_cli fetch-provider-live-data"
    )
    route_summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] = "NFO"
    route_summary["dispatch_roundtrip_source_live_fetch_contract_market"] = "india_nse_index_derivatives"
    route_summary["dispatch_roundtrip_source_live_fetch_contract_session_timezone"] = "Asia/Kolkata"
    route_summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] = "09:15:00"
    route_summary["dispatch_roundtrip_source_live_fetch_contract_session_close_local"] = "15:30:00"
    route_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"] = True
    route_summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"] = True
    route_summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"] = True
    route_summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"] = True
    route_summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_bundle_exchange"] = "NFO"
    route_summary["dispatch_roundtrip_capture_bundle_source_session_timezone"] = "Asia/Kolkata"
    route_summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] = "09:15:00"
    route_summary["dispatch_roundtrip_capture_bundle_source_session_close_local"] = "15:30:00"
    route_summary["dispatch_roundtrip_capture_bundle_market_session_timezone"] = "Asia/Kolkata"
    route_summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] = "09:15"
    route_summary["dispatch_roundtrip_capture_bundle_market_session_close_local"] = "15:30"
    route_summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"] = True
    route_summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"] = True
    route_summary["dispatch_roundtrip_provider_capture_command_count"] = 2
    route_summary["dispatch_roundtrip_provider_capture_command_providers"] = "arrow_money"
    route_summary["dispatch_roundtrip_provider_capture_command_transports"] = "websocket"
    route_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    route_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    route_summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    route_summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    route_summary["dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    route_summary["dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    route_summary["dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    route_summary["dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    route_summary["dispatch_roundtrip_adapter_contract_values_stored"] = False
    route_summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] = provider_profile_sha256
    route_summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    route_summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = True
    route_summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    route_summary["dispatch_roundtrip_provider_profile_sha256"] = provider_profile_sha256
    route_summary["dispatch_roundtrip_provider_profile_adapter"] = provider_profile["adapter"]
    route_summary["dispatch_roundtrip_provider_profile_auth_required"] = provider_profile["auth_required"]
    route_summary["dispatch_roundtrip_provider_profile_transports"] = provider_profile["transports"]
    route_summary["dispatch_roundtrip_provider_profile_capabilities"] = provider_profile["capabilities"]
    route_summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] = provider_profile_sha256
    route_summary["dispatch_roundtrip_provider_profile_matches_session"] = True
    route_summary["dispatch_roundtrip_provider_profile_matches_bundle"] = True
    route_summary["dispatch_roundtrip_provider_profile_matches_runtime_session"] = True
    route_summary["dispatch_roundtrip_source_provenance_consistent"] = True
    route_summary.to_csv(route_summary_path, index=False)

    route_config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    route_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = route_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    route_config["capture_bundle"] = capture_bundle_config
    route_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_sha256": env_template_sha256,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_sha256": "a" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    route_config_path.write_text(
        json.dumps(route_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_with_roundtrip_provenance"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert len(summary["dispatch_roundtrip_capture_env_template_sha256"]) == 64
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert len(summary["dispatch_roundtrip_adapter_handoff_sha256"]) == 64
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(checks.loc["provider_route_enable_dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(
        checks.loc["provider_route_enable_dispatch_roundtrip_adapter_execution_contract_matches_evidence", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_route_enable_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_route_enable_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["provider_route_enable_dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["provider_route_enable_dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(
        checks.loc["provider_route_enable_dispatch_roundtrip_adapter_provider_profile_matches_evidence", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_route_enable_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_live_fetch_contract_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert (
        config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert config["provider_route_enable"]["dispatch_roundtrip_adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["provider_route_enable"]["dispatch_roundtrip_adapter_handoff_sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert config["provider_route_enable"]["dispatch_roundtrip_source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert (
        manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"]
        == summary["dispatch_roundtrip_capture_env_template_sha256"]
    )
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"]
        == summary["dispatch_roundtrip_adapter_handoff_sha256"]
    )
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"][
        "provider_capture_commands_match_runtime_session"
    ]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_falls_back_to_roundtrip_config_provenance(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    route_summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(route_summary_path)
    provider_profile_sha256 = str(route_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    blank_columns = [
        "dispatch_roundtrip_exchange",
        "dispatch_roundtrip_source_session_timezone",
        "dispatch_roundtrip_source_session_open_local",
        "dispatch_roundtrip_source_session_close_local",
        "dispatch_roundtrip_market_session_timezone",
        "dispatch_roundtrip_market_session_open_local",
        "dispatch_roundtrip_market_session_close_local",
        "dispatch_roundtrip_exchange_matches_session",
        "dispatch_roundtrip_source_session_matches_session",
        "dispatch_roundtrip_market_session_matches_session",
        "dispatch_roundtrip_metadata_consistent",
        "dispatch_roundtrip_provider_capture_command_count",
        "dispatch_roundtrip_provider_capture_command_providers",
        "dispatch_roundtrip_provider_capture_command_transports",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
        "dispatch_roundtrip_adapter_contract_values_stored",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_auth_required",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_matches_session",
        "dispatch_roundtrip_provider_profile_matches_bundle",
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        "dispatch_roundtrip_capture_bundle_path",
        "dispatch_roundtrip_capture_bundle_ready",
        "dispatch_roundtrip_capture_bundle_exchange",
        "dispatch_roundtrip_capture_bundle_source_session_open_local",
        "dispatch_roundtrip_capture_bundle_market_session_open_local",
        "dispatch_roundtrip_capture_bundle_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_matches_session",
        "dispatch_roundtrip_capture_env_template_path",
        "dispatch_roundtrip_capture_env_template_sha256",
        "dispatch_roundtrip_capture_env_template_matches_session",
        "dispatch_roundtrip_adapter_handoff_path",
        "dispatch_roundtrip_adapter_handoff_sha256",
        "dispatch_roundtrip_adapter_handoff_matches_session",
        "dispatch_roundtrip_source_credential_env_template_path",
        "dispatch_roundtrip_source_credential_env_template_matches_session",
        "dispatch_roundtrip_source_live_fetch_contract_exchange",
        "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
        "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
        "dispatch_roundtrip_source_provenance_consistent",
    ]
    for column in blank_columns:
        route_summary[column] = ""
    route_summary["dispatch_roundtrip_capture_provenance_consistent"] = False
    route_summary.to_csv(route_summary_path, index=False)

    route_config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    route_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = route_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    route_config["capture_bundle"] = capture_bundle_config
    route_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_provided": True,
        "capture_bundle_exists": True,
        "capture_bundle_ready": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_provided": True,
        "capture_env_template_exists": True,
        "capture_env_template_sha256": env_template_sha256,
        "capture_env_template_matches_session": True,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_provided": True,
        "adapter_handoff_exists": True,
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "adapter_handoff_matches_session": True,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_exists": True,
        "source_credential_env_template_sha256": "b" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    route_config_path.write_text(
        json.dumps(route_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_config_roundtrip_fallback"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(checks.loc["provider_route_enable_dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(
        checks.loc["provider_route_enable_dispatch_roundtrip_adapter_execution_contract_matches_evidence", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_route_enable_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert not config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0][
        "provider"
    ] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"] == (
        provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert not manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: no" in runbook


def test_provider_market_data_imbalance_broker_dispatch_carries_route_dispatch_roundtrip_paths(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    route_summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(route_summary_path)
    route_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    route_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    route_summary["dispatch_roundtrip_provided"] = True
    route_summary["dispatch_roundtrip_ready"] = True
    route_summary["dispatch_roundtrip_failed_checks"] = 0
    route_summary.to_csv(route_summary_path, index=False)
    route_config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    route_config.setdefault("route_enable_inputs", {})
    route_config["route_enable_inputs"]["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    route_config["route_enable_inputs"]["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    route_config_path.write_text(
        json.dumps(route_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_with_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert Path(summary.loc[0, "provider_dispatch_roundtrip_dir"]) == provider_roundtrip_dir
    assert Path(summary.loc[0, "dispatch_roundtrip_dir"]) == nested_roundtrip_dir
    assert bool(summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_inputs"]["provider_dispatch_roundtrip_dir"] == str(provider_roundtrip_dir)
    assert config["broker_dispatch_inputs"]["dispatch_roundtrip_dir"] == str(nested_roundtrip_dir)
    assert manifest["inputs"]["provider_dispatch_roundtrip"]["path"] == str(provider_roundtrip_dir)
    assert manifest["inputs"]["dispatch_roundtrip"]["path"] == str(nested_roundtrip_dir)


def test_provider_market_data_imbalance_broker_dispatch_carries_route_vendor_batch(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    route_summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(route_summary_path)
    route_summary["dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_market"] = "india_nse_index_derivatives"
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    route_summary["broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    route_summary.to_csv(route_summary_path, index=False)

    route_config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    route_config["dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    route_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    route_config_path.write_text(
        json.dumps(route_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_with_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert "dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_preserves_upstream_vendor_batch(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    route_summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(route_summary_path)
    route_summary["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_market"] = (
        "india_nse_index_derivatives"
    )
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    route_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    route_summary.to_csv(route_summary_path, index=False)

    route_config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    route_config["upstream_dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    route_config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    route_config_path.write_text(
        json.dumps(route_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_runbook.md").read_text(
        encoding="utf-8"
    )

    assert report.ready
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_preserves_upstream_roundtrip(tmp_path):
    provider_route_enable = _write_ready_provider_imbalance_route_enable(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    upstream_nested_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    (upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready\ntrue\n",
        encoding="utf-8",
    )

    route_summary_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_summary.csv"
    route_summary = pd.read_csv(route_summary_path)
    route_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    route_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    route_summary["dispatch_roundtrip_provided"] = True
    route_summary["dispatch_roundtrip_ready"] = True
    route_summary["dispatch_roundtrip_failed_checks"] = 0
    route_summary["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    route_summary["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    route_summary["upstream_dispatch_roundtrip_provided"] = True
    route_summary["upstream_dispatch_roundtrip_ready"] = True
    route_summary["upstream_dispatch_roundtrip_failed_checks"] = 0
    route_summary.to_csv(route_summary_path, index=False)

    route_config_path = provider_route_enable.output_dir / "provider_market_data_imbalance_route_enable_config.json"
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    route_inputs = route_config.setdefault("route_enable_inputs", {})
    route_inputs["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    route_inputs["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    route_inputs["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    route_inputs["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    route_config_path.write_text(
        json.dumps(route_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_with_upstream_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch(
        provider_route_enable.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report.ready
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(upstream_provider_dir)
    assert config["broker_dispatch_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"] == str(upstream_provider_dir)
    assert manifest["inputs"]["upstream_dispatch_roundtrip"]["path"] == str(upstream_nested_dir)


def test_provider_market_data_imbalance_broker_dispatch_blocks_unready_route_enable(tmp_path):
    route_enable_dir = tmp_path / "provider_imbalance_route_enable"
    route_enable_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "route_enabled": False,
                "route_enable_dir": "",
                "upload_pack_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(route_enable_dir / "provider_market_data_imbalance_route_enable_summary.csv", index=False)
    (route_enable_dir / "provider_market_data_imbalance_route_enable_config.json").write_text(
        json.dumps({"route_enable_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_broker_dispatch(
        route_enable_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_route_enable_ready" in failed
    assert "provider_route_enabled" in failed
    assert "generic_route_enable_input_resolved" in failed
    assert "upload_pack_input_resolved" in failed
    assert "broker_dispatch_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-enable"
    assert not (report.output_dir / "broker_dispatch" / "broker_dispatch_summary.csv").exists()


def test_cli_provider_market_data_imbalance_broker_dispatch_blocks_unready_route_enable(tmp_path):
    route_enable_dir = tmp_path / "provider_imbalance_route_enable"
    route_enable_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "route_enabled": False,
                "route_enable_dir": "",
                "upload_pack_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(route_enable_dir / "provider_market_data_imbalance_route_enable_summary.csv", index=False)
    (route_enable_dir / "provider_market_data_imbalance_route_enable_config.json").write_text(
        json.dumps({"route_enable_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_provider_imbalance_broker_dispatch"

    code = main(
        [
            "plan-provider-market-data-imbalance-broker-dispatch",
            "--provider-route-enable",
            str(route_enable_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not bool(summary.loc[0, "broker_dispatch_ready"])
    assert summary.loc[0, "next_gate"] == "review-provider-market-data-imbalance-route-enable"


def test_provider_market_data_imbalance_broker_dispatch_send_accepts_ready_dispatch(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_action_queue.csv")
    send_summary = pd.read_csv(out_dir / "broker_dispatch_send" / "broker_dispatch_send_summary.csv")
    send_requests = pd.read_csv(out_dir / "broker_dispatch_send" / "broker_dispatch_send_requests.csv")
    expected_acks = pd.read_csv(out_dir / "broker_dispatch_send" / "broker_dispatch_expected_acks.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    assert report.ready
    assert bool(summary.loc[0, "provider_broker_dispatch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_send_ready"])
    assert bool(send_summary.loc[0, "ready"])
    assert summary.loc[0, "request_state"] == "dry_run_send_packet_ready"
    assert not bool(summary.loc[0, "submission_enabled"])
    assert int(summary.loc[0, "requests"]) > 0
    assert len(send_requests) == len(expected_acks)
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "reconcile-broker-dispatch"
    assert config["broker_dispatch_send"]["ready"]
    assert manifest["run_type"] == "provider_market_data_imbalance_broker_dispatch_send"
    assert "provider_broker_dispatch_dir" in manifest["inputs"]
    assert "broker_dispatch" in manifest["inputs"]
    assert "broker_dispatch_send" in manifest["inputs"]


def test_provider_market_data_imbalance_broker_dispatch_send_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
        route_readiness_dir=route_readiness.output_dir,
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    cutover = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )
    route_enable = write_provider_market_data_imbalance_route_enable(
        cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )
    broker_dispatch = write_provider_market_data_imbalance_broker_dispatch(
        route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        broker_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_send_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["source_live_fetch_contract_exchange"] == "NFO"
    assert summary["source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert not bool(summary["adapter_contract_values_stored"])
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["capture_bundle"]["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_matches_session"] is True
    assert config["capture_bundle"]["provider_profile_matches_bundle"] is True
    assert (
        config["capture_bundle"]["adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["transport"] == "websocket"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_broker_dispatch"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["provider_broker_dispatch"]["capture_env_template_sha256"]
        == summary["capture_env_template_sha256"]
    )
    assert config["provider_broker_dispatch"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_broker_dispatch"]["exchange"] == "NFO"
    assert config["provider_broker_dispatch"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_broker_dispatch"]["source_credential_env_template_path"] == str(source_env_template_path)
    assert config["provider_broker_dispatch"]["source_live_fetch_contract_available"] is True
    assert config["provider_broker_dispatch"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_broker_dispatch"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_broker_dispatch"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_broker_dispatch"]["provider_profile_matches_bundle"] is True
    assert config["provider_broker_dispatch"]["provider_capture_command_count"] == 2
    assert config["provider_broker_dispatch"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["metadata_matches_session"] is True
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["adapter_contract_metadata_matches_evidence"] is True
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert "Exchange: NFO" in runbook
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_broker_dispatch_send_blocks_missing_adapter_execution_contract(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(summary_path)
    dispatch_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        dispatch_summary.loc[0, column] = ""
    dispatch_summary.loc[0, "adapter_contract_values_stored"] = True
    dispatch_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    dispatch_summary.to_csv(summary_path, index=False)
    config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_broker_dispatch_adapter_execution_contract_carried" in failed
    assert "provider_broker_dispatch_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_send_blocks_missing_provider_profile(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(summary_path)
    dispatch_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        dispatch_summary[column] = dispatch_summary[column].astype("object")
        dispatch_summary.loc[0, column] = ""
    dispatch_summary.loc[0, "provider_profile_matches_session"] = False
    dispatch_summary.loc[0, "provider_profile_matches_bundle"] = False
    dispatch_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    dispatch_summary.to_csv(summary_path, index=False)

    config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_broker_dispatch_provider_profile_carried" in failed
    assert "provider_broker_dispatch_provider_profile_matches_session" in failed
    assert "provider_broker_dispatch_provider_profile_matches_bundle" in failed
    assert "provider_broker_dispatch_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_send_blocks_missing_roundtrip_adapter_contract(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(summary_path)
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in dispatch_summary.columns:
            dispatch_summary[column] = dispatch_summary[column].astype("object")
        dispatch_summary.loc[0, column] = ""
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = False
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = False
    dispatch_summary.to_csv(summary_path, index=False)

    config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"

    def _drop_roundtrip_adapter_contract(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        provenance.pop("adapter_execution_contract", None)
        for key in (
            "adapter_contract_provider",
            "adapter_contract_transport",
            "adapter_contract_market",
            "adapter_contract_exchange",
            "adapter_contract_values_stored",
            "adapter_contract_metadata_matches_evidence",
        ):
            provenance.pop(key, None)
        provenance["adapter_contract_matches_runtime_session"] = False

    _mutate_json(config_path, _drop_roundtrip_adapter_contract)

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send_missing_roundtrip_adapter_contract",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "component"] == "provider_broker_dispatch"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_send_blocks_missing_roundtrip_provider_profile(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(summary_path)
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    dispatch_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = False
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
    ):
        if column in dispatch_summary.columns:
            dispatch_summary[column] = dispatch_summary[column].astype("object")
        dispatch_summary.loc[0, column] = ""
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_profile_auth_required"] = False
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_session"] = False
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_bundle"] = False
    dispatch_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_runtime_session"] = False
    dispatch_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = False
    dispatch_summary.to_csv(summary_path, index=False)

    config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"

    def _drop_roundtrip_provider_profile(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        for key in (
            "provider_profile",
            "live_session_provider_profile",
            "capture_bundle_provider_profile",
            "provider_profile_sha256",
            "provider_profile_matches_session",
            "provider_profile_matches_bundle",
            "provider_profile_matches_runtime_session",
            "adapter_contract_provider_profile_sha256",
            "adapter_contract_provider_profile_matches_evidence",
        ):
            provenance.pop(key, None)
        contract = provenance.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        provenance["provider_profile_matches_session"] = False
        provenance["provider_profile_matches_bundle"] = False
        provenance["provider_profile_matches_runtime_session"] = False
        provenance["adapter_contract_provider_profile_matches_evidence"] = False

    _mutate_json(config_path, _drop_roundtrip_provider_profile)

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send_missing_roundtrip_provider_profile",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "provider_broker_dispatch_dispatch_roundtrip_provider_profile_carried" in failed
    assert "provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "provider_broker_dispatch_dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "component"] == "provider_broker_dispatch"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_send_carries_roundtrip_capture_bundle_provenance(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    dispatch_summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(dispatch_summary_path)
    provider_profile_sha256 = str(dispatch_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    dispatch_summary["dispatch_roundtrip_capture_bundle_path"] = str(bundle_path)
    dispatch_summary["dispatch_roundtrip_capture_bundle_provided"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_exists"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_ready"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_env_template_path"] = str(env_template_path)
    dispatch_summary["dispatch_roundtrip_capture_env_template_provided"] = True
    dispatch_summary["dispatch_roundtrip_capture_env_template_exists"] = True
    dispatch_summary["dispatch_roundtrip_capture_env_template_sha256"] = env_template_sha256
    dispatch_summary["dispatch_roundtrip_capture_env_template_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_adapter_handoff_path"] = str(adapter_handoff_path)
    dispatch_summary["dispatch_roundtrip_adapter_handoff_provided"] = True
    dispatch_summary["dispatch_roundtrip_adapter_handoff_exists"] = True
    dispatch_summary["dispatch_roundtrip_adapter_handoff_sha256"] = adapter_handoff_sha256
    dispatch_summary["dispatch_roundtrip_adapter_handoff_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_provenance_consistent"] = True
    dispatch_summary["dispatch_roundtrip_exchange"] = "NFO"
    dispatch_summary["dispatch_roundtrip_source_session_timezone"] = "Asia/Kolkata"
    dispatch_summary["dispatch_roundtrip_source_session_open_local"] = "09:15:00"
    dispatch_summary["dispatch_roundtrip_source_session_close_local"] = "15:30:00"
    dispatch_summary["dispatch_roundtrip_market_session_timezone"] = "Asia/Kolkata"
    dispatch_summary["dispatch_roundtrip_market_session_open_local"] = "09:15"
    dispatch_summary["dispatch_roundtrip_market_session_close_local"] = "15:30"
    dispatch_summary["dispatch_roundtrip_exchange_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_session_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_market_session_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_metadata_consistent"] = True
    dispatch_summary["source_credential_env_template_path"] = str(source_env_template_path)
    dispatch_summary["source_credential_env_template_exists"] = True
    dispatch_summary["source_credential_env_template_sha256"] = "a" * 64
    dispatch_summary["source_live_fetch_contract_available"] = True
    dispatch_summary["source_live_fetch_contract_next_gate"] = "provider_fetcher"
    dispatch_summary["source_live_fetch_contract_command_template"] = "python -m hft_cli fetch-provider-live-data"
    dispatch_summary["dispatch_roundtrip_source_credential_env_template_path"] = str(source_env_template_path)
    dispatch_summary["dispatch_roundtrip_source_credential_env_template_exists"] = True
    dispatch_summary["dispatch_roundtrip_source_credential_env_template_sha256"] = "a" * 64
    dispatch_summary["dispatch_roundtrip_source_credential_env_template_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_available"] = True
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"] = "provider_fetcher"
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_command_template"] = (
        "python -m hft_cli fetch-provider-live-data"
    )
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] = "NFO"
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_market"] = "india_nse_index_derivatives"
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_session_timezone"] = "Asia/Kolkata"
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] = "09:15:00"
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_session_close_local"] = "15:30:00"
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_exchange"] = "NFO"
    dispatch_summary["dispatch_roundtrip_capture_bundle_source_session_timezone"] = "Asia/Kolkata"
    dispatch_summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] = "09:15:00"
    dispatch_summary["dispatch_roundtrip_capture_bundle_source_session_close_local"] = "15:30:00"
    dispatch_summary["dispatch_roundtrip_capture_bundle_market_session_timezone"] = "Asia/Kolkata"
    dispatch_summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] = "09:15"
    dispatch_summary["dispatch_roundtrip_capture_bundle_market_session_close_local"] = "15:30"
    dispatch_summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_provider_capture_command_count"] = 2
    dispatch_summary["dispatch_roundtrip_provider_capture_command_providers"] = "arrow_money"
    dispatch_summary["dispatch_roundtrip_provider_capture_command_transports"] = "websocket"
    dispatch_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    dispatch_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    dispatch_summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    dispatch_summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    dispatch_summary["dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    dispatch_summary["dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    dispatch_summary["dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    dispatch_summary["dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    dispatch_summary["dispatch_roundtrip_adapter_contract_values_stored"] = False
    dispatch_summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] = provider_profile_sha256
    dispatch_summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    dispatch_summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = True
    dispatch_summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    dispatch_summary["dispatch_roundtrip_provider_profile_sha256"] = provider_profile_sha256
    dispatch_summary["dispatch_roundtrip_provider_profile_adapter"] = provider_profile["adapter"]
    dispatch_summary["dispatch_roundtrip_provider_profile_auth_required"] = provider_profile["auth_required"]
    dispatch_summary["dispatch_roundtrip_provider_profile_transports"] = provider_profile["transports"]
    dispatch_summary["dispatch_roundtrip_provider_profile_capabilities"] = provider_profile["capabilities"]
    dispatch_summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] = provider_profile_sha256
    dispatch_summary["dispatch_roundtrip_provider_profile_matches_session"] = True
    dispatch_summary["dispatch_roundtrip_provider_profile_matches_bundle"] = True
    dispatch_summary["dispatch_roundtrip_provider_profile_matches_runtime_session"] = True
    dispatch_summary["dispatch_roundtrip_source_provenance_consistent"] = True
    dispatch_summary.to_csv(dispatch_summary_path, index=False)

    dispatch_config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    dispatch_config = json.loads(dispatch_config_path.read_text(encoding="utf-8"))
    dispatch_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = dispatch_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    dispatch_config["capture_bundle"] = capture_bundle_config
    dispatch_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_sha256": env_template_sha256,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_sha256": "a" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    dispatch_config_path.write_text(
        json.dumps(dispatch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send_with_roundtrip_provenance"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_send_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_bundle"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_live_fetch_contract_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert config["provider_broker_dispatch"]["dispatch_roundtrip_adapter_handoff_path"] == str(
        adapter_handoff_path
    )
    assert (
        config["provider_broker_dispatch"]["dispatch_roundtrip_adapter_handoff_sha256"]
        == adapter_handoff_sha256
    )
    assert config["provider_broker_dispatch"]["dispatch_roundtrip_source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"][
        "provider_capture_commands_match_runtime_session"
    ]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_send_falls_back_to_roundtrip_config_provenance(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    dispatch_summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(dispatch_summary_path)
    provider_profile_sha256 = str(dispatch_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    blank_columns = [
        "dispatch_roundtrip_exchange",
        "dispatch_roundtrip_source_session_timezone",
        "dispatch_roundtrip_source_session_open_local",
        "dispatch_roundtrip_source_session_close_local",
        "dispatch_roundtrip_market_session_timezone",
        "dispatch_roundtrip_market_session_open_local",
        "dispatch_roundtrip_market_session_close_local",
        "dispatch_roundtrip_exchange_matches_session",
        "dispatch_roundtrip_source_session_matches_session",
        "dispatch_roundtrip_market_session_matches_session",
        "dispatch_roundtrip_metadata_consistent",
        "dispatch_roundtrip_provider_capture_command_count",
        "dispatch_roundtrip_provider_capture_command_providers",
        "dispatch_roundtrip_provider_capture_command_transports",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
        "dispatch_roundtrip_adapter_contract_values_stored",
        "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_auth_required",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_matches_session",
        "dispatch_roundtrip_provider_profile_matches_bundle",
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        "dispatch_roundtrip_capture_bundle_path",
        "dispatch_roundtrip_capture_bundle_ready",
        "dispatch_roundtrip_capture_bundle_exchange",
        "dispatch_roundtrip_capture_bundle_source_session_open_local",
        "dispatch_roundtrip_capture_bundle_market_session_open_local",
        "dispatch_roundtrip_capture_bundle_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_matches_session",
        "dispatch_roundtrip_capture_env_template_path",
        "dispatch_roundtrip_capture_env_template_sha256",
        "dispatch_roundtrip_capture_env_template_matches_session",
        "dispatch_roundtrip_adapter_handoff_path",
        "dispatch_roundtrip_adapter_handoff_sha256",
        "dispatch_roundtrip_adapter_handoff_matches_session",
        "dispatch_roundtrip_source_credential_env_template_path",
        "dispatch_roundtrip_source_credential_env_template_matches_session",
        "dispatch_roundtrip_source_live_fetch_contract_exchange",
        "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
        "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
        "dispatch_roundtrip_source_provenance_consistent",
    ]
    for column in blank_columns:
        dispatch_summary[column] = ""
    dispatch_summary["dispatch_roundtrip_capture_provenance_consistent"] = False
    dispatch_summary.to_csv(dispatch_summary_path, index=False)

    dispatch_config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    dispatch_config = json.loads(dispatch_config_path.read_text(encoding="utf-8"))
    dispatch_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = dispatch_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    dispatch_config["capture_bundle"] = capture_bundle_config
    dispatch_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_provided": True,
        "capture_bundle_exists": True,
        "capture_bundle_ready": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_provided": True,
        "capture_env_template_exists": True,
        "capture_env_template_sha256": env_template_sha256,
        "capture_env_template_matches_session": True,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_provided": True,
        "adapter_handoff_exists": True,
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "adapter_handoff_matches_session": True,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_exists": True,
        "source_credential_env_template_sha256": "d" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    dispatch_config_path.write_text(
        json.dumps(dispatch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send_config_roundtrip_fallback"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_send_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_carried", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert not config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0][
        "provider"
    ] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert not manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: no" in runbook


def test_provider_market_data_imbalance_broker_dispatch_send_carries_dispatch_roundtrip_paths(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    dispatch_summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(dispatch_summary_path)
    dispatch_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    dispatch_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    dispatch_summary["dispatch_roundtrip_provided"] = True
    dispatch_summary["dispatch_roundtrip_ready"] = True
    dispatch_summary["dispatch_roundtrip_failed_checks"] = 0
    dispatch_summary.to_csv(dispatch_summary_path, index=False)
    dispatch_config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    dispatch_config = json.loads(dispatch_config_path.read_text(encoding="utf-8"))
    dispatch_config.setdefault("broker_dispatch_inputs", {})
    dispatch_config["broker_dispatch_inputs"]["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    dispatch_config["broker_dispatch_inputs"]["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    dispatch_config_path.write_text(
        json.dumps(dispatch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send_with_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert Path(summary.loc[0, "provider_dispatch_roundtrip_dir"]) == provider_roundtrip_dir
    assert Path(summary.loc[0, "dispatch_roundtrip_dir"]) == nested_roundtrip_dir
    assert bool(summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_send_inputs"]["provider_dispatch_roundtrip_dir"] == str(provider_roundtrip_dir)
    assert config["broker_dispatch_send_inputs"]["dispatch_roundtrip_dir"] == str(nested_roundtrip_dir)
    assert manifest["inputs"]["provider_dispatch_roundtrip"]["path"] == str(provider_roundtrip_dir)
    assert manifest["inputs"]["dispatch_roundtrip"]["path"] == str(nested_roundtrip_dir)


def test_provider_market_data_imbalance_broker_dispatch_send_carries_dispatch_vendor_batch(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    dispatch_summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(dispatch_summary_path)
    dispatch_summary["dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_market"] = (
        "india_nse_index_derivatives"
    )
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    dispatch_summary["broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    dispatch_summary.to_csv(dispatch_summary_path, index=False)

    dispatch_config_path = (
        provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    )
    dispatch_config = json.loads(dispatch_config_path.read_text(encoding="utf-8"))
    dispatch_config["dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    dispatch_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    dispatch_config_path.write_text(
        json.dumps(dispatch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send_with_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_send_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert "dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert not manifest["extra"]["dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert manifest["extra"]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_send_preserves_upstream_vendor_batch(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    dispatch_summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(dispatch_summary_path)
    dispatch_summary["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_market"] = (
        "india_nse_index_derivatives"
    )
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    dispatch_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    dispatch_summary.to_csv(dispatch_summary_path, index=False)

    dispatch_config_path = (
        provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    )
    dispatch_config = json.loads(dispatch_config_path.read_text(encoding="utf-8"))
    dispatch_config["upstream_dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    dispatch_config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    dispatch_config_path.write_text(
        json.dumps(dispatch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_send_runbook.md").read_text(
        encoding="utf-8"
    )

    assert report.ready
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_send_preserves_upstream_roundtrip(tmp_path):
    provider_dispatch = _write_ready_provider_imbalance_broker_dispatch(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    upstream_nested_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    (upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready\ntrue\n",
        encoding="utf-8",
    )

    dispatch_summary_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv"
    dispatch_summary = pd.read_csv(dispatch_summary_path)
    dispatch_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    dispatch_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    dispatch_summary["dispatch_roundtrip_provided"] = True
    dispatch_summary["dispatch_roundtrip_ready"] = True
    dispatch_summary["dispatch_roundtrip_failed_checks"] = 0
    dispatch_summary["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    dispatch_summary["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    dispatch_summary["upstream_dispatch_roundtrip_provided"] = True
    dispatch_summary["upstream_dispatch_roundtrip_ready"] = True
    dispatch_summary["upstream_dispatch_roundtrip_failed_checks"] = 0
    dispatch_summary.to_csv(dispatch_summary_path, index=False)

    dispatch_config_path = provider_dispatch.output_dir / "provider_market_data_imbalance_broker_dispatch_config.json"
    dispatch_config = json.loads(dispatch_config_path.read_text(encoding="utf-8"))
    dispatch_inputs = dispatch_config.setdefault("broker_dispatch_inputs", {})
    dispatch_inputs["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    dispatch_inputs["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    dispatch_inputs["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    dispatch_inputs["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    dispatch_config_path.write_text(
        json.dumps(dispatch_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_send_with_upstream_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        provider_dispatch.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report.ready
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_send_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(
        upstream_provider_dir
    )
    assert config["broker_dispatch_send_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"] == str(upstream_provider_dir)
    assert manifest["inputs"]["upstream_dispatch_roundtrip"]["path"] == str(upstream_nested_dir)


def test_provider_market_data_imbalance_broker_dispatch_send_blocks_unready_dispatch(tmp_path):
    dispatch_dir = tmp_path / "provider_imbalance_broker_dispatch"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_dispatch_ready": False,
                "broker_dispatch_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(dispatch_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv", index=False)
    (dispatch_dir / "provider_market_data_imbalance_broker_dispatch_config.json").write_text(
        json.dumps({"broker_dispatch": {}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_send(
        dispatch_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "provider_broker_dispatch_ready" in failed
    assert "provider_nested_broker_dispatch_ready" in failed
    assert "generic_broker_dispatch_input_resolved" in failed
    assert "broker_dispatch_send_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-broker-dispatch"
    assert not (report.output_dir / "broker_dispatch_send" / "broker_dispatch_send_summary.csv").exists()


def test_cli_provider_market_data_imbalance_broker_dispatch_send_blocks_unready_dispatch(tmp_path):
    dispatch_dir = tmp_path / "provider_imbalance_broker_dispatch"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_dispatch_ready": False,
                "broker_dispatch_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(dispatch_dir / "provider_market_data_imbalance_broker_dispatch_summary.csv", index=False)
    (dispatch_dir / "provider_market_data_imbalance_broker_dispatch_config.json").write_text(
        json.dumps({"broker_dispatch": {}}, indent=2) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_provider_imbalance_broker_dispatch_send"

    code = main(
        [
            "prepare-provider-market-data-imbalance-broker-dispatch-send",
            "--provider-broker-dispatch",
            str(dispatch_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not bool(summary.loc[0, "broker_dispatch_send_ready"])
    assert summary.loc[0, "next_gate"] == "plan-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_ack_accepts_ready_send(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    acks_path = _write_provider_imbalance_accepted_ack_file(provider_send, tmp_path / "provider_imbalance_acks.csv")
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_action_queue.csv")
    ack_summary = pd.read_csv(out_dir / "broker_dispatch_ack" / "broker_dispatch_ack_summary.csv")
    acknowledgements = pd.read_csv(out_dir / "broker_dispatch_ack" / "broker_dispatch_acknowledgements.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    assert report.passed
    assert bool(summary.loc[0, "provider_broker_dispatch_send_ready"])
    assert bool(summary.loc[0, "broker_dispatch_ack_passed"])
    assert bool(ack_summary.loc[0, "passed"])
    assert float(summary.loc[0, "ack_rate"]) == 1.0
    assert int(summary.loc[0, "missing_acks"]) == 0
    assert int(summary.loc[0, "rejected_orders"]) == 0
    assert bool(acknowledgements["acked"].astype(bool).all())
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    assert config["broker_dispatch_ack"]["passed"]
    assert manifest["run_type"] == "provider_market_data_imbalance_broker_dispatch_ack"
    assert "provider_broker_dispatch_send_dir" in manifest["inputs"]
    assert "broker_dispatch" in manifest["inputs"]
    assert "broker_acks" in manifest["inputs"]
    assert "broker_dispatch_ack" in manifest["inputs"]


def test_provider_market_data_imbalance_broker_dispatch_ack_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
        route_readiness_dir=route_readiness.output_dir,
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    cutover = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )
    route_enable = write_provider_market_data_imbalance_route_enable(
        cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )
    broker_dispatch = write_provider_market_data_imbalance_broker_dispatch(
        route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )
    provider_send = write_provider_market_data_imbalance_broker_dispatch_send(
        broker_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert summary["source_live_fetch_contract_exchange"] == "NFO"
    assert summary["source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert not bool(summary["adapter_contract_values_stored"])
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["capture_bundle"]["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert (
        config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_matches_session"] is True
    assert config["capture_bundle"]["provider_profile_matches_bundle"] is True
    assert (
        config["capture_bundle"]["adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["transport"] == "websocket"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["provider_broker_dispatch_send"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["provider_broker_dispatch_send"]["capture_env_template_sha256"]
        == summary["capture_env_template_sha256"]
    )
    assert config["provider_broker_dispatch_send"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_broker_dispatch_send"]["exchange"] == "NFO"
    assert config["provider_broker_dispatch_send"]["capture_bundle_metadata_matches_session"] is True
    assert config["provider_broker_dispatch_send"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_broker_dispatch_send"]["provider_profile_matches_bundle"] is True
    assert config["provider_broker_dispatch_send"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["provider_broker_dispatch_send"]["source_live_fetch_contract_available"] is True
    assert config["provider_broker_dispatch_send"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_broker_dispatch_send"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_broker_dispatch_send"]["provider_capture_command_count"] == 2
    assert config["provider_broker_dispatch_send"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["metadata_matches_session"] is True
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_contract_metadata_matches_evidence"] is True
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert "Exchange: NFO" in runbook
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_broker_dispatch_ack_blocks_missing_adapter_execution_contract(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(summary_path)
    send_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        send_summary.loc[0, column] = ""
    send_summary.loc[0, "adapter_contract_values_stored"] = True
    send_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    send_summary.to_csv(summary_path, index=False)
    config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_acks.csv",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_send_adapter_execution_contract_carried" in failed
    assert "provider_broker_dispatch_send_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_send"
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"


def test_provider_market_data_imbalance_broker_dispatch_ack_blocks_missing_provider_profile(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(summary_path)
    send_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        send_summary[column] = send_summary[column].astype("object")
        send_summary.loc[0, column] = ""
    send_summary.loc[0, "provider_profile_matches_session"] = False
    send_summary.loc[0, "provider_profile_matches_bundle"] = False
    send_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    send_summary.to_csv(summary_path, index=False)

    config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_acks.csv",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_send_provider_profile_carried" in failed
    assert "provider_broker_dispatch_send_provider_profile_matches_session" in failed
    assert "provider_broker_dispatch_send_provider_profile_matches_bundle" in failed
    assert "provider_broker_dispatch_send_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_send"
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"


def test_provider_market_data_imbalance_broker_dispatch_ack_blocks_missing_roundtrip_adapter_contract(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(summary_path)
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    send_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    send_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in send_summary.columns:
            send_summary[column] = send_summary[column].astype("object")
        send_summary.loc[0, column] = ""
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = True
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = False
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = False
    send_summary.to_csv(summary_path, index=False)

    config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"

    def _drop_roundtrip_adapter_contract(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        provenance.pop("adapter_execution_contract", None)
        for key in (
            "adapter_contract_provider",
            "adapter_contract_transport",
            "adapter_contract_market",
            "adapter_contract_exchange",
            "adapter_contract_values_stored",
            "adapter_contract_metadata_matches_evidence",
        ):
            provenance.pop(key, None)
        provenance["adapter_contract_matches_runtime_session"] = False

    _mutate_json(config_path, _drop_roundtrip_adapter_contract)
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_missing_roundtrip_adapter_contract_acks.csv",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack_missing_roundtrip_adapter_contract",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "component"] == "provider_broker_dispatch_send"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_send"
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"


def test_provider_market_data_imbalance_broker_dispatch_ack_blocks_missing_roundtrip_provider_profile(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(summary_path)
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    send_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    send_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    send_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = False
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
    ):
        if column in send_summary.columns:
            send_summary[column] = send_summary[column].astype("object")
        send_summary.loc[0, column] = ""
    send_summary.loc[0, "dispatch_roundtrip_provider_profile_auth_required"] = False
    send_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_session"] = False
    send_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_bundle"] = False
    send_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_runtime_session"] = False
    send_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = False
    send_summary.to_csv(summary_path, index=False)

    config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"

    def _drop_roundtrip_provider_profile(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        for key in (
            "provider_profile",
            "live_session_provider_profile",
            "capture_bundle_provider_profile",
            "provider_profile_sha256",
            "provider_profile_matches_session",
            "provider_profile_matches_bundle",
            "provider_profile_matches_runtime_session",
            "adapter_contract_provider_profile_sha256",
            "adapter_contract_provider_profile_matches_evidence",
        ):
            provenance.pop(key, None)
        contract = provenance.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        provenance["provider_profile_matches_session"] = False
        provenance["provider_profile_matches_bundle"] = False
        provenance["provider_profile_matches_runtime_session"] = False
        provenance["adapter_contract_provider_profile_matches_evidence"] = False

    _mutate_json(config_path, _drop_roundtrip_provider_profile)
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_missing_roundtrip_provider_profile_acks.csv",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack_missing_roundtrip_provider_profile",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_carried" in failed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "component"] == "provider_broker_dispatch_send"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_send"
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"


def test_provider_market_data_imbalance_broker_dispatch_ack_carries_roundtrip_capture_bundle_provenance(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    send_summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(send_summary_path)
    provider_profile_sha256 = str(send_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    send_summary["dispatch_roundtrip_capture_bundle_path"] = str(bundle_path)
    send_summary["dispatch_roundtrip_capture_bundle_provided"] = True
    send_summary["dispatch_roundtrip_capture_bundle_exists"] = True
    send_summary["dispatch_roundtrip_capture_bundle_ready"] = True
    send_summary["dispatch_roundtrip_capture_bundle_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_env_template_path"] = str(env_template_path)
    send_summary["dispatch_roundtrip_capture_env_template_provided"] = True
    send_summary["dispatch_roundtrip_capture_env_template_exists"] = True
    send_summary["dispatch_roundtrip_capture_env_template_sha256"] = env_template_sha256
    send_summary["dispatch_roundtrip_capture_env_template_matches_session"] = True
    send_summary["dispatch_roundtrip_adapter_handoff_path"] = str(adapter_handoff_path)
    send_summary["dispatch_roundtrip_adapter_handoff_provided"] = True
    send_summary["dispatch_roundtrip_adapter_handoff_exists"] = True
    send_summary["dispatch_roundtrip_adapter_handoff_sha256"] = adapter_handoff_sha256
    send_summary["dispatch_roundtrip_adapter_handoff_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_provenance_consistent"] = True
    send_summary["dispatch_roundtrip_exchange"] = "NFO"
    send_summary["dispatch_roundtrip_source_session_timezone"] = "Asia/Kolkata"
    send_summary["dispatch_roundtrip_source_session_open_local"] = "09:15:00"
    send_summary["dispatch_roundtrip_source_session_close_local"] = "15:30:00"
    send_summary["dispatch_roundtrip_market_session_timezone"] = "Asia/Kolkata"
    send_summary["dispatch_roundtrip_market_session_open_local"] = "09:15"
    send_summary["dispatch_roundtrip_market_session_close_local"] = "15:30"
    send_summary["dispatch_roundtrip_exchange_matches_session"] = True
    send_summary["dispatch_roundtrip_source_session_matches_session"] = True
    send_summary["dispatch_roundtrip_market_session_matches_session"] = True
    send_summary["dispatch_roundtrip_metadata_consistent"] = True
    send_summary["source_credential_env_template_path"] = str(source_env_template_path)
    send_summary["source_credential_env_template_exists"] = True
    send_summary["source_credential_env_template_sha256"] = "a" * 64
    send_summary["source_live_fetch_contract_available"] = True
    send_summary["source_live_fetch_contract_next_gate"] = "provider_fetcher"
    send_summary["source_live_fetch_contract_command_template"] = "python -m hft_cli fetch-provider-live-data"
    send_summary["dispatch_roundtrip_source_credential_env_template_path"] = str(source_env_template_path)
    send_summary["dispatch_roundtrip_source_credential_env_template_exists"] = True
    send_summary["dispatch_roundtrip_source_credential_env_template_sha256"] = "a" * 64
    send_summary["dispatch_roundtrip_source_credential_env_template_matches_session"] = True
    send_summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"] = True
    send_summary["dispatch_roundtrip_source_live_fetch_contract_available"] = True
    send_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"] = "provider_fetcher"
    send_summary["dispatch_roundtrip_source_live_fetch_contract_command_template"] = (
        "python -m hft_cli fetch-provider-live-data"
    )
    send_summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] = "NFO"
    send_summary["dispatch_roundtrip_source_live_fetch_contract_market"] = "india_nse_index_derivatives"
    send_summary["dispatch_roundtrip_source_live_fetch_contract_session_timezone"] = "Asia/Kolkata"
    send_summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] = "09:15:00"
    send_summary["dispatch_roundtrip_source_live_fetch_contract_session_close_local"] = "15:30:00"
    send_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"] = True
    send_summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"] = True
    send_summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"] = True
    send_summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"] = True
    send_summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_bundle_exchange"] = "NFO"
    send_summary["dispatch_roundtrip_capture_bundle_source_session_timezone"] = "Asia/Kolkata"
    send_summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] = "09:15:00"
    send_summary["dispatch_roundtrip_capture_bundle_source_session_close_local"] = "15:30:00"
    send_summary["dispatch_roundtrip_capture_bundle_market_session_timezone"] = "Asia/Kolkata"
    send_summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] = "09:15"
    send_summary["dispatch_roundtrip_capture_bundle_market_session_close_local"] = "15:30"
    send_summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"] = True
    send_summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"] = True
    send_summary["dispatch_roundtrip_provider_capture_command_count"] = 2
    send_summary["dispatch_roundtrip_provider_capture_command_providers"] = "arrow_money"
    send_summary["dispatch_roundtrip_provider_capture_command_transports"] = "websocket"
    send_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    send_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    send_summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    send_summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    send_summary["dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    send_summary["dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    send_summary["dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    send_summary["dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    send_summary["dispatch_roundtrip_adapter_contract_values_stored"] = False
    send_summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] = provider_profile_sha256
    send_summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    send_summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = True
    send_summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    send_summary["dispatch_roundtrip_provider_profile_sha256"] = provider_profile_sha256
    send_summary["dispatch_roundtrip_provider_profile_adapter"] = provider_profile["adapter"]
    send_summary["dispatch_roundtrip_provider_profile_auth_required"] = provider_profile["auth_required"]
    send_summary["dispatch_roundtrip_provider_profile_transports"] = provider_profile["transports"]
    send_summary["dispatch_roundtrip_provider_profile_capabilities"] = provider_profile["capabilities"]
    send_summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] = provider_profile_sha256
    send_summary["dispatch_roundtrip_provider_profile_matches_session"] = True
    send_summary["dispatch_roundtrip_provider_profile_matches_bundle"] = True
    send_summary["dispatch_roundtrip_provider_profile_matches_runtime_session"] = True
    send_summary["dispatch_roundtrip_source_provenance_consistent"] = True
    send_summary.to_csv(send_summary_path, index=False)

    send_config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    send_config = json.loads(send_config_path.read_text(encoding="utf-8"))
    send_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = send_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    send_config["capture_bundle"] = capture_bundle_config
    send_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_sha256": env_template_sha256,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "consistent_with_runtime_session": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_sha256": "a" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    send_config_path.write_text(
        json.dumps(send_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_roundtrip_provenance_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack_with_roundtrip_provenance"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_market_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_carried",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_bundle"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_live_fetch_contract_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert config["provider_broker_dispatch_send"]["dispatch_roundtrip_adapter_handoff_path"] == str(
        adapter_handoff_path
    )
    assert (
        config["provider_broker_dispatch_send"]["dispatch_roundtrip_adapter_handoff_sha256"]
        == adapter_handoff_sha256
    )
    assert config["provider_broker_dispatch_send"]["dispatch_roundtrip_source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"][
        "provider_capture_commands_match_runtime_session"
    ]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_ack_falls_back_to_roundtrip_config_provenance(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli fetch-provider-live-data --provider arrow_money",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command": "python -m hft_cli capture-provider-market-data --provider arrow_money",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    send_summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(send_summary_path)
    provider_profile_sha256 = str(send_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    blank_columns = [
        "dispatch_roundtrip_exchange",
        "dispatch_roundtrip_source_session_timezone",
        "dispatch_roundtrip_source_session_open_local",
        "dispatch_roundtrip_source_session_close_local",
        "dispatch_roundtrip_market_session_timezone",
        "dispatch_roundtrip_market_session_open_local",
        "dispatch_roundtrip_market_session_close_local",
        "dispatch_roundtrip_exchange_matches_session",
        "dispatch_roundtrip_source_session_matches_session",
        "dispatch_roundtrip_market_session_matches_session",
        "dispatch_roundtrip_metadata_consistent",
        "dispatch_roundtrip_provider_capture_command_count",
        "dispatch_roundtrip_provider_capture_command_providers",
        "dispatch_roundtrip_provider_capture_command_transports",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
        "dispatch_roundtrip_adapter_contract_values_stored",
        "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_auth_required",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_matches_session",
        "dispatch_roundtrip_provider_profile_matches_bundle",
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        "dispatch_roundtrip_capture_bundle_path",
        "dispatch_roundtrip_capture_bundle_ready",
        "dispatch_roundtrip_capture_bundle_exchange",
        "dispatch_roundtrip_capture_bundle_source_session_open_local",
        "dispatch_roundtrip_capture_bundle_market_session_open_local",
        "dispatch_roundtrip_capture_bundle_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_matches_session",
        "dispatch_roundtrip_capture_env_template_path",
        "dispatch_roundtrip_capture_env_template_sha256",
        "dispatch_roundtrip_capture_env_template_matches_session",
        "dispatch_roundtrip_adapter_handoff_path",
        "dispatch_roundtrip_adapter_handoff_sha256",
        "dispatch_roundtrip_adapter_handoff_matches_session",
        "dispatch_roundtrip_source_credential_env_template_path",
        "dispatch_roundtrip_source_credential_env_template_matches_session",
        "dispatch_roundtrip_source_live_fetch_contract_exchange",
        "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
        "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
        "dispatch_roundtrip_source_provenance_consistent",
    ]
    for column in blank_columns:
        send_summary[column] = ""
    send_summary["dispatch_roundtrip_capture_provenance_consistent"] = False
    send_summary.to_csv(send_summary_path, index=False)

    send_config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    send_config = json.loads(send_config_path.read_text(encoding="utf-8"))
    send_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = send_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    send_config["capture_bundle"] = capture_bundle_config
    send_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_provided": True,
        "capture_bundle_exists": True,
        "capture_bundle_ready": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_provided": True,
        "capture_env_template_exists": True,
        "capture_env_template_sha256": env_template_sha256,
        "capture_env_template_matches_session": True,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_provided": True,
        "adapter_handoff_exists": True,
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "adapter_handoff_matches_session": True,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_exists": True,
        "source_credential_env_template_sha256": "e" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    send_config_path.write_text(
        json.dumps(send_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_roundtrip_config_fallback_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack_config_roundtrip_fallback"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    checks = report.checks.set_index("check")
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_carried",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_session", "passed"])
    assert bool(checks.loc["provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_bundle", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_send_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert not config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0][
        "provider"
    ] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert not manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert (
        manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"]
        == "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: no" in runbook


def test_provider_market_data_imbalance_broker_dispatch_ack_carries_send_dispatch_roundtrip_paths(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    provider_roundtrip_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    nested_roundtrip_dir = provider_roundtrip_dir / "broker_dispatch_roundtrip"
    nested_roundtrip_dir.mkdir(parents=True)
    (nested_roundtrip_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready,dispatch_roundtrip_provided,dispatch_roundtrip_ready,dispatch_roundtrip_failed_checks\n"
        "true,true,true,0\n",
        encoding="utf-8",
    )
    send_summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(send_summary_path)
    send_summary["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    send_summary["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    send_summary["dispatch_roundtrip_provided"] = True
    send_summary["dispatch_roundtrip_ready"] = True
    send_summary["dispatch_roundtrip_failed_checks"] = 0
    send_summary.to_csv(send_summary_path, index=False)
    send_config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    send_config = json.loads(send_config_path.read_text(encoding="utf-8"))
    send_config.setdefault("broker_dispatch_send_inputs", {})
    send_config["broker_dispatch_send_inputs"]["provider_dispatch_roundtrip_dir"] = str(provider_roundtrip_dir)
    send_config["broker_dispatch_send_inputs"]["dispatch_roundtrip_dir"] = str(nested_roundtrip_dir)
    send_config_path.write_text(
        json.dumps(send_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_roundtrip_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack_with_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert Path(summary.loc[0, "provider_dispatch_roundtrip_dir"]) == provider_roundtrip_dir
    assert Path(summary.loc[0, "dispatch_roundtrip_dir"]) == nested_roundtrip_dir
    assert bool(summary.loc[0, "dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_ack_inputs"]["provider_dispatch_roundtrip_dir"] == str(provider_roundtrip_dir)
    assert config["broker_dispatch_ack_inputs"]["dispatch_roundtrip_dir"] == str(nested_roundtrip_dir)
    assert manifest["inputs"]["provider_dispatch_roundtrip"]["path"] == str(provider_roundtrip_dir)
    assert manifest["inputs"]["dispatch_roundtrip"]["path"] == str(nested_roundtrip_dir)


def test_provider_market_data_imbalance_broker_dispatch_ack_carries_send_vendor_batch(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    send_summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(send_summary_path)
    send_summary["dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_market"] = "india_nse_index_derivatives"
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    send_summary["broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    send_summary.to_csv(send_summary_path, index=False)

    send_config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    send_config = json.loads(send_config_path.read_text(encoding="utf-8"))
    send_config["dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    send_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    send_config_path.write_text(
        json.dumps(send_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_vendor_batch_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack_with_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert "dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert not manifest["extra"]["dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert manifest["extra"]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_ack_preserves_upstream_vendor_batch(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    upstream_broker_vendor = _vendor_market_data_batch_config()
    send_summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(send_summary_path)
    send_summary["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_market"] = (
        "india_nse_index_derivatives"
    )
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    send_summary["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    send_summary.to_csv(send_summary_path, index=False)

    send_config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    send_config = json.loads(send_config_path.read_text(encoding="utf-8"))
    send_config["upstream_dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    send_config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"] = upstream_broker_vendor
    send_config_path.write_text(
        json.dumps(send_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_upstream_vendor_batch_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert not manifest["extra"]["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_ack_preserves_upstream_roundtrip(tmp_path):
    provider_send = _write_ready_provider_imbalance_broker_dispatch_send(tmp_path)
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    upstream_nested_dir.mkdir(parents=True)
    (upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv").write_text(
        "ready\ntrue\n",
        encoding="utf-8",
    )

    send_summary_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    send_summary = pd.read_csv(send_summary_path)
    send_summary["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    send_summary["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    send_summary["upstream_dispatch_roundtrip_provided"] = True
    send_summary["upstream_dispatch_roundtrip_ready"] = True
    send_summary["upstream_dispatch_roundtrip_failed_checks"] = 0
    send_summary.to_csv(send_summary_path, index=False)

    send_config_path = provider_send.output_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    send_config = json.loads(send_config_path.read_text(encoding="utf-8"))
    send_inputs = send_config.setdefault("broker_dispatch_send_inputs", {})
    send_inputs["upstream_provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    send_inputs["upstream_dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    send_config_path.write_text(
        json.dumps(send_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_upstream_roundtrip_acks.csv",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_ack_with_upstream_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report.passed
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_ack_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(
        upstream_provider_dir
    )
    assert config["broker_dispatch_ack_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"] == str(upstream_provider_dir)
    assert manifest["inputs"]["upstream_dispatch_roundtrip"]["path"] == str(upstream_nested_dir)


def test_provider_market_data_imbalance_broker_dispatch_ack_blocks_unready_send(tmp_path):
    send_dir = tmp_path / "provider_imbalance_broker_dispatch_send"
    send_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_dispatch_send_ready": False,
                "broker_dispatch_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(send_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv", index=False)
    (send_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").write_text(
        json.dumps({"broker_dispatch_send_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_ack(
        send_dir,
        tmp_path / "missing_acks.csv",
        tmp_path / "provider_imbalance_broker_dispatch_ack",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert "provider_broker_dispatch_send_ready" in failed
    assert "provider_nested_broker_dispatch_send_ready" in failed
    assert "generic_broker_dispatch_input_resolved" in failed
    assert "broker_acks_path_exists" in failed
    assert "broker_dispatch_ack_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"
    assert not (report.output_dir / "broker_dispatch_ack" / "broker_dispatch_ack_summary.csv").exists()


def test_cli_provider_market_data_imbalance_broker_dispatch_ack_blocks_unready_send(tmp_path):
    send_dir = tmp_path / "provider_imbalance_broker_dispatch_send"
    send_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": False,
                "broker_dispatch_send_ready": False,
                "broker_dispatch_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(send_dir / "provider_market_data_imbalance_broker_dispatch_send_summary.csv", index=False)
    (send_dir / "provider_market_data_imbalance_broker_dispatch_send_config.json").write_text(
        json.dumps({"broker_dispatch_send_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_provider_imbalance_broker_dispatch_ack"

    code = main(
        [
            "reconcile-provider-market-data-imbalance-broker-dispatch",
            "--provider-broker-dispatch-send",
            str(send_dir),
            "--acks",
            str(tmp_path / "missing_acks.csv"),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert not bool(summary.loc[0, "broker_dispatch_ack_passed"])
    assert summary.loc[0, "next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_accepts_ready_ack(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_action_queue.csv")
    checks = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_checks.csv")
    roundtrip_summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip" / "broker_dispatch_roundtrip_summary.csv")
    roundtrip_orders = pd.read_csv(out_dir / "broker_dispatch_roundtrip" / "broker_dispatch_roundtrip_orders.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert report.passed
    assert bool(summary.loc[0, "provider_broker_dispatch_ack_passed"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_passed"])
    assert bool(roundtrip_summary.loc[0, "passed"])
    assert int(summary.loc[0, "missing_request_acks"]) == 0
    assert int(summary.loc[0, "rejected_orders"]) == 0
    assert bool(roundtrip_orders["acked"].astype(bool).all())
    assert checks["passed"].astype(bool).all()
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "review-provider-market-data-imbalance-broker-readiness"
    assert config["broker_dispatch_roundtrip"]["passed"]
    assert manifest["run_type"] == "provider_market_data_imbalance_broker_dispatch_roundtrip"
    assert "provider_broker_dispatch_ack_dir" in manifest["inputs"]
    assert "broker_dispatch" in manifest["inputs"]
    assert "broker_dispatch_send" in manifest["inputs"]
    assert "broker_dispatch_ack" in manifest["inputs"]
    assert "broker_dispatch_roundtrip" in manifest["inputs"]


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_carries_capture_bundle_provenance(tmp_path):
    launch_evidence, bundle_path = _write_bundle_linked_provider_imbalance_launch_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    ops_evidence = _write_ready_ops_launch_evidence(tmp_path)
    route_readiness = write_provider_market_data_imbalance_route_readiness(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_route_readiness",
        ops_evidence_dirs=(ops_evidence,),
        config=ProviderMarketDataImbalanceRouteReadinessConfig(),
    )
    scorecard = write_provider_market_data_imbalance_scorecard(
        launch_evidence.output_dir,
        tmp_path / "provider_imbalance_scorecard",
        config=ProviderMarketDataImbalanceScorecardConfig(allow_dirty_git=True),
    )
    shadow = _write_provider_imbalance_shadow_comparison(tmp_path, launch_evidence)
    scaleup = write_provider_market_data_imbalance_scaleup_plan(
        scorecard.output_dir,
        shadow,
        tmp_path / "provider_imbalance_scaleup",
        route_readiness_dir=route_readiness.output_dir,
    )
    runtime_telemetry = write_provider_market_data_imbalance_runtime_telemetry_snapshot(
        scaleup.output_dir,
        tmp_path / "provider_imbalance_runtime_telemetry",
        snapshot_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeTelemetryConfig(),
    )
    runtime_guard = write_provider_market_data_imbalance_runtime_guard(
        runtime_telemetry.output_dir,
        tmp_path / "provider_imbalance_runtime_guard",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeGuardConfig(),
    )
    runtime_session = write_provider_market_data_imbalance_runtime_session(
        runtime_guard.output_dir,
        tmp_path / "provider_imbalance_runtime_session",
        as_of_ts_ns=1_000_000,
        config=ProviderMarketDataImbalanceRuntimeSessionConfig(),
    )
    broker_readiness = write_provider_market_data_imbalance_broker_readiness(
        runtime_session.output_dir,
        tmp_path / "provider_imbalance_broker_readiness",
        config=ProviderMarketDataImbalanceBrokerReadinessConfig(),
    )
    cutover = write_provider_market_data_imbalance_cutover(
        broker_readiness.output_dir,
        tmp_path / "provider_imbalance_cutover",
        config=ProviderMarketDataImbalanceCutoverConfig(),
    )
    route_enable = write_provider_market_data_imbalance_route_enable(
        cutover.output_dir,
        tmp_path / "provider_imbalance_route_enable",
        config=ProviderMarketDataImbalanceRouteEnableConfig(),
    )
    broker_dispatch = write_provider_market_data_imbalance_broker_dispatch(
        route_enable.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch",
        config=ProviderMarketDataImbalanceBrokerDispatchConfig(),
    )
    provider_send = write_provider_market_data_imbalance_broker_dispatch_send(
        broker_dispatch.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_send",
        config=ProviderMarketDataImbalanceBrokerDispatchSendConfig(),
    )
    acks_path = _write_provider_imbalance_accepted_ack_file(
        provider_send,
        tmp_path / "provider_imbalance_acks.csv",
    )
    provider_ack = write_provider_market_data_imbalance_broker_dispatch_ack(
        provider_send.output_dir,
        acks_path,
        tmp_path / "provider_imbalance_broker_dispatch_ack",
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(),
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["source_live_fetch_contract_exchange"] == "NFO"
    assert summary["source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert not bool(summary["adapter_contract_values_stored"])
    assert bool(summary["adapter_contract_metadata_matches_evidence"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["provider_profile_matches_session"])
    assert bool(summary["provider_profile_matches_bundle"])
    assert summary["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert bool(summary["adapter_contract_provider_profile_matches_evidence"])
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["capture_bundle_provider_capture_commands_match_session"])
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["capture_bundle"]["live_fetch_contract_metadata_matches_session"] is True
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert (
        config["capture_bundle"]["source_credential_env_template_sha256"]
        == summary["source_credential_env_template_sha256"]
    )
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["capture_bundle"]["source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert (
        config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert (
        config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["provider_profile_matches_session"] is True
    assert config["capture_bundle"]["provider_profile_matches_bundle"] is True
    assert (
        config["capture_bundle"]["adapter_contract_provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert config["capture_bundle"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["transport"] == "websocket"
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["live_session_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_broker_dispatch_ack"]["exchange"] == "NFO"
    assert config["provider_broker_dispatch_ack"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert (
        config["provider_broker_dispatch_ack"]["capture_env_template_sha256"]
        == summary["capture_env_template_sha256"]
    )
    assert config["provider_broker_dispatch_ack"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["provider_broker_dispatch_ack"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["provider_broker_dispatch_ack"]["source_live_fetch_contract_available"] is True
    assert config["provider_broker_dispatch_ack"]["adapter_contract_provider"] == "arrow_money"
    assert config["provider_broker_dispatch_ack"]["adapter_contract_metadata_matches_evidence"] is True
    assert config["provider_broker_dispatch_ack"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["provider_broker_dispatch_ack"]["provider_profile_matches_bundle"] is True
    assert config["provider_broker_dispatch_ack"]["provider_capture_command_count"] == 2
    assert config["provider_broker_dispatch_ack"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["capture_bundle_provided"]
    assert manifest["extra"]["capture_env_template_exists"]
    assert manifest["extra"]["adapter_handoff_exists"]
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["metadata_matches_session"] is True
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        manifest["extra"]["adapter_execution_contract"]["provider_profile_sha256"]
        == summary["provider_profile_sha256"]
    )
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["provider_profile_matches_session"] is True
    assert manifest["extra"]["provider_profile_matches_bundle"] is True
    assert manifest["extra"]["adapter_contract_metadata_matches_evidence"] is True
    assert manifest["extra"]["adapter_contract_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["adapter_contract_provider_profile_matches_evidence"] is True
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert "Exchange: NFO" in runbook
    assert "Source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Adapter execution contract: arrow_money / websocket (evidence match: yes)" in runbook
    assert f"Provider profile: {summary['provider_profile_sha256']} (bundle match: yes)" in runbook
    assert "Provider capture commands: 2 (bundle match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_blocks_missing_adapter_execution_contract(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(summary_path)
    ack_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "adapter_contract_provider",
        "adapter_contract_transport",
        "adapter_contract_market",
        "adapter_contract_exchange",
    ):
        ack_summary.loc[0, column] = ""
    ack_summary.loc[0, "adapter_contract_values_stored"] = True
    ack_summary.loc[0, "adapter_contract_metadata_matches_evidence"] = False
    ack_summary.to_csv(summary_path, index=False)
    config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"
    _mutate_json(
        config_path,
        lambda payload: (
            payload.pop("adapter_execution_contract", None),
            payload["capture_bundle"].pop("adapter_execution_contract", None),
        ),
    )

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_ack_adapter_execution_contract_carried" in failed
    assert "provider_broker_dispatch_ack_adapter_execution_contract_matches_evidence" in failed
    assert summary["adapter_contract_provider"] == ""
    assert bool(summary["adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_ack"
    assert report.action_queue.loc[0, "next_gate"] == "reconcile-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_blocks_missing_provider_profile(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(summary_path)
    ack_summary.loc[0, "capture_bundle_provided"] = True
    for column in (
        "provider_profile_sha256",
        "provider_profile_adapter",
        "provider_profile_transports",
        "provider_profile_capabilities",
        "capture_bundle_provider_profile_sha256",
        "adapter_contract_provider_profile_sha256",
    ):
        ack_summary[column] = ack_summary[column].astype("object")
        ack_summary.loc[0, column] = ""
    ack_summary.loc[0, "provider_profile_matches_session"] = False
    ack_summary.loc[0, "provider_profile_matches_bundle"] = False
    ack_summary.loc[0, "adapter_contract_provider_profile_matches_evidence"] = False
    ack_summary.to_csv(summary_path, index=False)

    config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"

    def remove_provider_profile(payload):
        payload.pop("provider_profile", None)
        payload.pop("live_session_provider_profile", None)
        contract = payload.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        bundle = payload.get("capture_bundle")
        if isinstance(bundle, dict):
            bundle.pop("provider_profile", None)
            bundle.pop("live_session_provider_profile", None)
            bundle.pop("capture_bundle_provider_profile", None)
            bundle_contract = bundle.get("adapter_execution_contract")
            if isinstance(bundle_contract, dict):
                bundle_contract.pop("provider_profile_sha256", None)

    _mutate_json(config_path, remove_provider_profile)

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_ack_provider_profile_carried" in failed
    assert "provider_broker_dispatch_ack_provider_profile_matches_session" in failed
    assert "provider_broker_dispatch_ack_provider_profile_matches_bundle" in failed
    assert "provider_broker_dispatch_ack_adapter_provider_profile_matches_evidence" in failed
    assert summary["provider_profile_sha256"] == ""
    assert not bool(summary["provider_profile_matches_session"])
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_ack"
    assert report.action_queue.loc[0, "next_gate"] == "reconcile-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_blocks_missing_roundtrip_adapter_contract(
    tmp_path,
):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(summary_path)
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    ack_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    ack_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
    ):
        if column in ack_summary.columns:
            ack_summary[column] = ack_summary[column].astype("object")
        ack_summary.loc[0, column] = ""
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = True
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = False
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = False
    ack_summary.to_csv(summary_path, index=False)

    config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"

    def _drop_roundtrip_adapter_contract(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        provenance.pop("adapter_execution_contract", None)
        for key in (
            "adapter_contract_provider",
            "adapter_contract_transport",
            "adapter_contract_market",
            "adapter_contract_exchange",
            "adapter_contract_values_stored",
            "adapter_contract_metadata_matches_evidence",
        ):
            provenance.pop(key, None)
        provenance["adapter_contract_matches_runtime_session"] = False

    _mutate_json(config_path, _drop_roundtrip_adapter_contract)

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip_missing_roundtrip_adapter_contract",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_carried" in failed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_evidence" in failed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == ""
    assert bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert report.action_queue.loc[0, "component"] == "provider_broker_dispatch_ack"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_ack"
    assert report.action_queue.loc[0, "next_gate"] == "reconcile-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_blocks_missing_roundtrip_provider_profile(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(summary_path)
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provided"] = True
    ack_summary.loc[0, "dispatch_roundtrip_provider_capture_command_count"] = 2
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    ack_summary.loc[0, "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    ack_summary.loc[0, "dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_values_stored"] = False
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    for column in (
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
    ):
        if column in ack_summary.columns:
            ack_summary[column] = ack_summary[column].astype("object")
        ack_summary.loc[0, column] = ""
    ack_summary.loc[0, "dispatch_roundtrip_provider_profile_auth_required"] = False
    ack_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_session"] = False
    ack_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_bundle"] = False
    ack_summary.loc[0, "dispatch_roundtrip_provider_profile_matches_runtime_session"] = False
    ack_summary.loc[0, "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = False
    ack_summary.to_csv(summary_path, index=False)

    config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"

    def _drop_roundtrip_provider_profile(payload):
        provenance = payload.setdefault("dispatch_roundtrip_provenance", {})
        for key in (
            "provider_profile",
            "live_session_provider_profile",
            "capture_bundle_provider_profile",
            "provider_profile_sha256",
            "provider_profile_matches_session",
            "provider_profile_matches_bundle",
            "provider_profile_matches_runtime_session",
            "adapter_contract_provider_profile_sha256",
            "adapter_contract_provider_profile_matches_evidence",
        ):
            provenance.pop(key, None)
        contract = provenance.get("adapter_execution_contract")
        if isinstance(contract, dict):
            contract.pop("provider_profile_sha256", None)
        provenance["provider_profile_matches_session"] = False
        provenance["provider_profile_matches_bundle"] = False
        provenance["provider_profile_matches_runtime_session"] = False
        provenance["adapter_contract_provider_profile_matches_evidence"] = False

    _mutate_json(config_path, _drop_roundtrip_provider_profile)

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip_missing_roundtrip_provider_profile",
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.passed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_carried" in failed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_session" in failed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_bundle" in failed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_provider_profile_matches_evidence" in failed
    assert "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_runtime_session" in failed
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == ""
    assert not bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert report.action_queue.loc[0, "component"] == "provider_broker_dispatch_ack"
    assert report.action_queue.loc[0, "action"] == "repair_provider_imbalance_broker_dispatch_ack"
    assert report.action_queue.loc[0, "next_gate"] == "reconcile-provider-market-data-imbalance-broker-dispatch"


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_carries_roundtrip_capture_bundle_provenance(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command_template": "python -m hft_cli capture-provider --provider arrow_money --exchange NFO",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command_template": "python -m hft_cli capture-provider --provider arrow_money --exchange NFO --verify",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    ack_summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(ack_summary_path)
    provider_profile_sha256 = str(ack_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    ack_summary["dispatch_roundtrip_capture_bundle_path"] = str(bundle_path)
    ack_summary["dispatch_roundtrip_capture_bundle_provided"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_exists"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_ready"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_env_template_path"] = str(env_template_path)
    ack_summary["dispatch_roundtrip_capture_env_template_provided"] = True
    ack_summary["dispatch_roundtrip_capture_env_template_exists"] = True
    ack_summary["dispatch_roundtrip_capture_env_template_sha256"] = env_template_sha256
    ack_summary["dispatch_roundtrip_capture_env_template_matches_session"] = True
    ack_summary["dispatch_roundtrip_adapter_handoff_path"] = str(adapter_handoff_path)
    ack_summary["dispatch_roundtrip_adapter_handoff_provided"] = True
    ack_summary["dispatch_roundtrip_adapter_handoff_exists"] = True
    ack_summary["dispatch_roundtrip_adapter_handoff_sha256"] = adapter_handoff_sha256
    ack_summary["dispatch_roundtrip_adapter_handoff_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_provenance_consistent"] = True
    ack_summary["dispatch_roundtrip_exchange"] = "NFO"
    ack_summary["dispatch_roundtrip_source_session_timezone"] = "Asia/Kolkata"
    ack_summary["dispatch_roundtrip_source_session_open_local"] = "09:15:00"
    ack_summary["dispatch_roundtrip_source_session_close_local"] = "15:30:00"
    ack_summary["dispatch_roundtrip_market_session_timezone"] = "Asia/Kolkata"
    ack_summary["dispatch_roundtrip_market_session_open_local"] = "09:15"
    ack_summary["dispatch_roundtrip_market_session_close_local"] = "15:30"
    ack_summary["dispatch_roundtrip_exchange_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_session_matches_session"] = True
    ack_summary["dispatch_roundtrip_market_session_matches_session"] = True
    ack_summary["dispatch_roundtrip_metadata_consistent"] = True
    ack_summary["dispatch_roundtrip_provider_capture_command_count"] = 2
    ack_summary["dispatch_roundtrip_provider_capture_command_providers"] = "arrow_money"
    ack_summary["dispatch_roundtrip_provider_capture_command_transports"] = "websocket"
    ack_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] = 2
    ack_summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] = 0
    ack_summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"] = True
    ack_summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"] = True
    ack_summary["dispatch_roundtrip_adapter_contract_provider"] = "arrow_money"
    ack_summary["dispatch_roundtrip_adapter_contract_transport"] = "websocket"
    ack_summary["dispatch_roundtrip_adapter_contract_market"] = "india_nse_index_derivatives"
    ack_summary["dispatch_roundtrip_adapter_contract_exchange"] = "NFO"
    ack_summary["dispatch_roundtrip_adapter_contract_values_stored"] = False
    ack_summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] = provider_profile_sha256
    ack_summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"] = True
    ack_summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"] = True
    ack_summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"] = True
    ack_summary["dispatch_roundtrip_provider_profile_sha256"] = provider_profile_sha256
    ack_summary["dispatch_roundtrip_provider_profile_adapter"] = provider_profile["adapter"]
    ack_summary["dispatch_roundtrip_provider_profile_auth_required"] = provider_profile["auth_required"]
    ack_summary["dispatch_roundtrip_provider_profile_transports"] = provider_profile["transports"]
    ack_summary["dispatch_roundtrip_provider_profile_capabilities"] = provider_profile["capabilities"]
    ack_summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] = provider_profile_sha256
    ack_summary["dispatch_roundtrip_provider_profile_matches_session"] = True
    ack_summary["dispatch_roundtrip_provider_profile_matches_bundle"] = True
    ack_summary["dispatch_roundtrip_provider_profile_matches_runtime_session"] = True
    ack_summary["source_credential_env_template_path"] = str(source_env_template_path)
    ack_summary["source_credential_env_template_exists"] = True
    ack_summary["source_credential_env_template_sha256"] = "a" * 64
    ack_summary["source_live_fetch_contract_available"] = True
    ack_summary["source_live_fetch_contract_next_gate"] = "provider_fetcher"
    ack_summary["source_live_fetch_contract_command_template"] = "python -m hft_cli fetch-provider-live-data"
    ack_summary["dispatch_roundtrip_source_credential_env_template_path"] = str(source_env_template_path)
    ack_summary["dispatch_roundtrip_source_credential_env_template_exists"] = True
    ack_summary["dispatch_roundtrip_source_credential_env_template_sha256"] = "a" * 64
    ack_summary["dispatch_roundtrip_source_credential_env_template_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_available"] = True
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"] = "provider_fetcher"
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_command_template"] = (
        "python -m hft_cli fetch-provider-live-data"
    )
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] = "NFO"
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_market"] = "india_nse_index_derivatives"
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_session_timezone"] = "Asia/Kolkata"
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] = "09:15:00"
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_session_close_local"] = "15:30:00"
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_exchange"] = "NFO"
    ack_summary["dispatch_roundtrip_capture_bundle_source_session_timezone"] = "Asia/Kolkata"
    ack_summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] = "09:15:00"
    ack_summary["dispatch_roundtrip_capture_bundle_source_session_close_local"] = "15:30:00"
    ack_summary["dispatch_roundtrip_capture_bundle_market_session_timezone"] = "Asia/Kolkata"
    ack_summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] = "09:15"
    ack_summary["dispatch_roundtrip_capture_bundle_market_session_close_local"] = "15:30"
    ack_summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"] = True
    ack_summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"] = True
    ack_summary["dispatch_roundtrip_source_provenance_consistent"] = True
    ack_summary.to_csv(ack_summary_path, index=False)

    ack_config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"
    ack_config = json.loads(ack_config_path.read_text(encoding="utf-8"))
    ack_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = ack_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    ack_config["capture_bundle"] = capture_bundle_config
    ack_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_sha256": env_template_sha256,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "consistent_with_runtime_session": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_sha256": "a" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    ack_config_path.write_text(
        json.dumps(ack_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip_with_roundtrip_provenance"

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md").read_text(
        encoding="utf-8"
    )
    checks = report.checks.set_index("check")
    assert report.passed
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_carried",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(
        checks.loc["provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_session", "passed"]
    )
    assert bool(
        checks.loc["provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_bundle", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_provided"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert bool(summary["dispatch_roundtrip_capture_env_template_matches_session"])
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_market_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert "live_ticks" in summary["dispatch_roundtrip_provider_profile_capabilities"]
    assert summary["dispatch_roundtrip_capture_bundle_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert summary["dispatch_roundtrip_capture_bundle_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["dispatch_roundtrip_capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["dispatch_roundtrip_capture_bundle_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_source_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_market_session_matches_session"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_market_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_session_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert config["dispatch_roundtrip_provenance"]["market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["metadata_consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["transport"]
        == "websocket"
    )
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_bundle"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_path"] == str(env_template_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_source_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_market_session"]["open_local"] == "09:15"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_live_fetch_contract_metadata_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert config["dispatch_roundtrip_provenance"]["source_credential_env_template_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_exchange_matches_session"]
    assert config["dispatch_roundtrip_provenance"]["source_provenance_consistent_with_runtime_session"]
    assert config["provider_broker_dispatch_ack"]["dispatch_roundtrip_adapter_handoff_path"] == str(
        adapter_handoff_path
    )
    assert (
        config["provider_broker_dispatch_ack"]["dispatch_roundtrip_adapter_handoff_sha256"]
        == adapter_handoff_sha256
    )
    assert config["provider_broker_dispatch_ack"]["dispatch_roundtrip_source_credential_env_template_path"] == str(
        source_env_template_path
    )
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["inputs"]["dispatch_roundtrip_source_credential_env_template"]["path"] == str(
        source_env_template_path.resolve()
    )
    assert manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_source_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_source_credential_env_template_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_metadata_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["transport"]
        == "websocket"
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_bundle"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["exchange"] == "NFO"
    assert manifest["extra"]["dispatch_roundtrip"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip"]["provider_profile_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == (
        "arrow_money"
    )
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert str(adapter_handoff_path) in runbook
    assert "- Dispatch round-trip provenance consistent: yes" in runbook
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip source session: 09:15:00 - 15:30:00 Asia/Kolkata" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert str(source_env_template_path) in runbook
    assert "- Dispatch round-trip source provenance consistent: yes" in runbook


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_falls_back_to_roundtrip_config_provenance(
    tmp_path,
):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    bundle_path = tmp_path / "provider_market_data_capture_bundle.json"
    env_template_path = tmp_path / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = tmp_path / "provider_market_data_adapter_handoff.json"
    source_env_template_path = tmp_path / "provider_source_credentials.env"
    for path in (bundle_path, env_template_path, adapter_handoff_path, source_env_template_path):
        path.write_text("{}", encoding="utf-8")
    env_template_sha256 = hashlib.sha256(env_template_path.read_bytes()).hexdigest()
    adapter_handoff_sha256 = hashlib.sha256(adapter_handoff_path.read_bytes()).hexdigest()
    provider_capture_commands = [
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command_template": "python -m hft_cli capture-provider --provider arrow_money --exchange NFO",
        },
        {
            "provider": "arrow_money",
            "transport": "websocket",
            "command_template": "python -m hft_cli capture-provider --provider arrow_money --exchange NFO --verify",
        },
    ]
    adapter_execution_contract = {
        "provider": "arrow_money",
        "transport": "websocket",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "credential_env_template": {"ARROW_API_KEY": "${ARROW_API_KEY}"},
        "values_stored": False,
        "metadata_matches_evidence": True,
    }

    ack_summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(ack_summary_path)
    provider_profile_sha256 = str(ack_summary.loc[0, "provider_profile_sha256"])
    provider_profile = {
        "sha256": provider_profile_sha256,
        "adapter": "arrow_money",
        "auth_required": True,
        "transports": "file;rest;websocket",
        "capabilities": "live_ticks;market_depth",
    }
    adapter_execution_contract["provider_profile_sha256"] = provider_profile_sha256
    blank_columns = [
        "dispatch_roundtrip_exchange",
        "dispatch_roundtrip_source_session_timezone",
        "dispatch_roundtrip_source_session_open_local",
        "dispatch_roundtrip_source_session_close_local",
        "dispatch_roundtrip_market_session_timezone",
        "dispatch_roundtrip_market_session_open_local",
        "dispatch_roundtrip_market_session_close_local",
        "dispatch_roundtrip_exchange_matches_session",
        "dispatch_roundtrip_source_session_matches_session",
        "dispatch_roundtrip_market_session_matches_session",
        "dispatch_roundtrip_metadata_consistent",
        "dispatch_roundtrip_provider_capture_command_count",
        "dispatch_roundtrip_provider_capture_command_providers",
        "dispatch_roundtrip_provider_capture_command_transports",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count",
        "dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session",
        "dispatch_roundtrip_provider_capture_commands_match_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider",
        "dispatch_roundtrip_adapter_contract_transport",
        "dispatch_roundtrip_adapter_contract_market",
        "dispatch_roundtrip_adapter_contract_exchange",
        "dispatch_roundtrip_adapter_contract_values_stored",
        "dispatch_roundtrip_adapter_contract_metadata_matches_evidence",
        "dispatch_roundtrip_adapter_contract_matches_runtime_session",
        "dispatch_roundtrip_adapter_contract_provider_profile_sha256",
        "dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence",
        "dispatch_roundtrip_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_adapter",
        "dispatch_roundtrip_provider_profile_auth_required",
        "dispatch_roundtrip_provider_profile_transports",
        "dispatch_roundtrip_provider_profile_capabilities",
        "dispatch_roundtrip_capture_bundle_provider_profile_sha256",
        "dispatch_roundtrip_provider_profile_matches_session",
        "dispatch_roundtrip_provider_profile_matches_bundle",
        "dispatch_roundtrip_provider_profile_matches_runtime_session",
        "dispatch_roundtrip_capture_bundle_path",
        "dispatch_roundtrip_capture_bundle_ready",
        "dispatch_roundtrip_capture_bundle_exchange",
        "dispatch_roundtrip_capture_bundle_source_session_open_local",
        "dispatch_roundtrip_capture_bundle_market_session_open_local",
        "dispatch_roundtrip_capture_bundle_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_live_fetch_contract_metadata_matches_session",
        "dispatch_roundtrip_capture_bundle_matches_session",
        "dispatch_roundtrip_capture_env_template_path",
        "dispatch_roundtrip_capture_env_template_sha256",
        "dispatch_roundtrip_capture_env_template_matches_session",
        "dispatch_roundtrip_adapter_handoff_path",
        "dispatch_roundtrip_adapter_handoff_sha256",
        "dispatch_roundtrip_adapter_handoff_matches_session",
        "dispatch_roundtrip_source_credential_env_template_path",
        "dispatch_roundtrip_source_credential_env_template_matches_session",
        "dispatch_roundtrip_source_live_fetch_contract_exchange",
        "dispatch_roundtrip_source_live_fetch_contract_session_open_local",
        "dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session",
        "dispatch_roundtrip_source_provenance_consistent",
    ]
    for column in blank_columns:
        ack_summary[column] = ""
    ack_summary["dispatch_roundtrip_capture_provenance_consistent"] = False
    ack_summary.to_csv(ack_summary_path, index=False)

    ack_config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"
    ack_config = json.loads(ack_config_path.read_text(encoding="utf-8"))
    ack_config["provider_capture_commands"] = provider_capture_commands
    capture_bundle_config = ack_config.get("capture_bundle", {})
    if not isinstance(capture_bundle_config, dict):
        capture_bundle_config = {}
    capture_bundle_config["capture_bundle_provider_capture_commands"] = provider_capture_commands
    ack_config["capture_bundle"] = capture_bundle_config
    ack_config["dispatch_roundtrip_provenance"] = {
        "exchange": "NFO",
        "source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "exchange_matches_session": True,
        "source_session_matches_session": True,
        "market_session_matches_session": True,
        "metadata_consistent_with_runtime_session": True,
        "provider_capture_command_count": 2,
        "provider_capture_command_providers": "arrow_money",
        "provider_capture_command_transports": "websocket",
        "capture_bundle_provider_capture_command_count": 2,
        "capture_bundle_provider_capture_command_missing_count": 0,
        "capture_bundle_provider_capture_commands_match_session": True,
        "provider_capture_commands_match_runtime_session": True,
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_matches_runtime_session": True,
        "provider_profile": provider_profile,
        "live_session_provider_profile": provider_profile,
        "capture_bundle_provider_profile": provider_profile,
        "provider_profile_sha256": provider_profile_sha256,
        "provider_profile_matches_session": True,
        "provider_profile_matches_bundle": True,
        "provider_profile_matches_runtime_session": True,
        "adapter_contract_provider_profile_sha256": provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": True,
        "capture_bundle_path": str(bundle_path),
        "capture_bundle_provided": True,
        "capture_bundle_exists": True,
        "capture_bundle_ready": True,
        "capture_bundle_exchange": "NFO",
        "capture_bundle_source_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "capture_bundle_market_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "capture_bundle_metadata_matches_session": True,
        "capture_bundle_live_fetch_contract_metadata_matches_session": True,
        "capture_bundle_matches_session": True,
        "capture_bundle_exchange_matches_session": True,
        "capture_bundle_source_session_matches_session": True,
        "capture_bundle_market_session_matches_session": True,
        "capture_env_template_path": str(env_template_path),
        "capture_env_template_provided": True,
        "capture_env_template_exists": True,
        "capture_env_template_sha256": env_template_sha256,
        "capture_env_template_matches_session": True,
        "adapter_handoff_path": str(adapter_handoff_path),
        "adapter_handoff_provided": True,
        "adapter_handoff_exists": True,
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "adapter_handoff_matches_session": True,
        "consistent_with_runtime_session": True,
        "source_credential_env_template_path": str(source_env_template_path),
        "source_credential_env_template_exists": True,
        "source_credential_env_template_sha256": "f" * 64,
        "source_credential_env_template_matches_session": True,
        "source_credential_env_template_sha256_matches_session": True,
        "source_live_fetch_contract_available": True,
        "source_live_fetch_contract_next_gate": "provider_fetcher",
        "source_live_fetch_contract_command_template": "python -m hft_cli fetch-provider-live-data",
        "source_live_fetch_contract_exchange": "NFO",
        "source_live_fetch_contract_market": "india_nse_index_derivatives",
        "source_live_fetch_contract_session": {
            "timezone": "Asia/Kolkata",
            "open_local": "09:15:00",
            "close_local": "15:30:00",
        },
        "source_live_fetch_contract_next_gate_matches_session": True,
        "source_live_fetch_contract_command_template_matches_session": True,
        "source_live_fetch_contract_exchange_matches_session": True,
        "source_live_fetch_contract_market_matches_session": True,
        "source_live_fetch_contract_session_matches_session": True,
        "source_provenance_consistent_with_runtime_session": True,
    }
    ack_config_path.write_text(
        json.dumps(ack_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip_config_roundtrip_fallback"

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md").read_text(
        encoding="utf-8"
    )
    checks = report.checks.set_index("check")
    assert report.passed
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_carried", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_session", "passed"])
    assert bool(checks.loc["dispatch_roundtrip_provider_capture_commands_match_runtime_session", "passed"])
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_carried",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_execution_contract_matches_runtime_session",
            "passed",
        ]
    )
    assert bool(checks.loc["provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_carried", "passed"])
    assert bool(
        checks.loc["provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_session", "passed"]
    )
    assert bool(
        checks.loc["provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_bundle", "passed"]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_adapter_provider_profile_matches_evidence",
            "passed",
        ]
    )
    assert bool(
        checks.loc[
            "provider_broker_dispatch_ack_dispatch_roundtrip_provider_profile_matches_runtime_session",
            "passed",
        ]
    )
    assert summary["dispatch_roundtrip_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_metadata_consistent"])
    assert summary["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert summary["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert summary["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert bool(summary["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"])
    assert bool(summary["dispatch_roundtrip_provider_capture_commands_match_runtime_session"])
    assert summary["dispatch_roundtrip_adapter_contract_provider"] == "arrow_money"
    assert summary["dispatch_roundtrip_adapter_contract_transport"] == "websocket"
    assert summary["dispatch_roundtrip_adapter_contract_market"] == "india_nse_index_derivatives"
    assert summary["dispatch_roundtrip_adapter_contract_exchange"] == "NFO"
    assert not bool(summary["dispatch_roundtrip_adapter_contract_values_stored"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_metadata_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_adapter_contract_matches_runtime_session"])
    assert summary["dispatch_roundtrip_provider_profile_sha256"] == provider_profile_sha256
    assert summary["dispatch_roundtrip_provider_profile_adapter"] == provider_profile["adapter"]
    assert bool(summary["dispatch_roundtrip_provider_profile_auth_required"])
    assert summary["dispatch_roundtrip_provider_profile_transports"] == provider_profile["transports"]
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_session"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_bundle"])
    assert summary["dispatch_roundtrip_adapter_contract_provider_profile_sha256"] == provider_profile_sha256
    assert bool(summary["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"])
    assert bool(summary["dispatch_roundtrip_provider_profile_matches_runtime_session"])
    assert Path(summary["dispatch_roundtrip_capture_bundle_path"]) == bundle_path
    assert bool(summary["dispatch_roundtrip_capture_bundle_ready"])
    assert bool(summary["dispatch_roundtrip_capture_bundle_matches_session"])
    assert Path(summary["dispatch_roundtrip_capture_env_template_path"]) == env_template_path
    assert summary["dispatch_roundtrip_capture_env_template_sha256"] == env_template_sha256
    assert Path(summary["dispatch_roundtrip_adapter_handoff_path"]) == adapter_handoff_path
    assert summary["dispatch_roundtrip_adapter_handoff_sha256"] == adapter_handoff_sha256
    assert bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"])
    assert not bool(summary["dispatch_roundtrip_capture_provenance_consistent"])
    assert Path(summary["dispatch_roundtrip_source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["dispatch_roundtrip_source_credential_env_template_matches_session"])
    assert summary["dispatch_roundtrip_source_live_fetch_contract_exchange"] == "NFO"
    assert summary["dispatch_roundtrip_source_live_fetch_contract_session_open_local"] == "09:15:00"
    assert bool(summary["dispatch_roundtrip_source_live_fetch_contract_exchange_matches_session"])
    assert bool(summary["dispatch_roundtrip_source_provenance_consistent"])
    assert config["dispatch_roundtrip_provenance"]["exchange"] == "NFO"
    assert config["dispatch_roundtrip_provenance"]["source_session"]["close_local"] == "15:30:00"
    assert not config["dispatch_roundtrip_provenance"]["consistent_with_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_providers"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["provider_capture_command_transports"] == "websocket"
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands_match_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_capture_commands"][0]["transport"]
        == "websocket"
    )
    assert config["dispatch_roundtrip_provenance"]["provider_capture_commands_match_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["values_stored"] is False
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_execution_contract"]["provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_matches_runtime_session"]
    assert config["dispatch_roundtrip_provenance"]["provider_profile"]["sha256"] == provider_profile_sha256
    assert (
        config["dispatch_roundtrip_provenance"]["live_session_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert (
        config["dispatch_roundtrip_provenance"]["capture_bundle_provider_profile"]["sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["provider_profile_matches_runtime_session"]
    assert (
        config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert config["dispatch_roundtrip_provenance"]["adapter_contract_provider_profile_matches_evidence"]
    assert config["dispatch_roundtrip_provenance"]["capture_bundle_path"] == str(bundle_path)
    assert config["dispatch_roundtrip_provenance"]["capture_env_template_sha256"] == env_template_sha256
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["dispatch_roundtrip_provenance"]["adapter_handoff_sha256"] == adapter_handoff_sha256
    assert config["dispatch_roundtrip_provenance"]["source_live_fetch_contract_session"]["open_local"] == "09:15:00"
    assert manifest["inputs"]["dispatch_roundtrip_capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert not manifest["extra"]["dispatch_roundtrip_capture_provenance_consistent"]
    assert manifest["extra"]["dispatch_roundtrip_capture_env_template"]["sha256"] == env_template_sha256
    assert manifest["extra"]["dispatch_roundtrip_adapter_handoff"]["sha256"] == adapter_handoff_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert (
        manifest["extra"]["dispatch_roundtrip_capture_bundle_provider_capture_commands"][0]["transport"]
        == "websocket"
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip_provider_profile"]["sha256"] == provider_profile_sha256
    assert manifest["extra"]["dispatch_roundtrip_provider_profile_matches_runtime_session"]
    assert (
        manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_sha256"]
        == provider_profile_sha256
    )
    assert manifest["extra"]["dispatch_roundtrip_adapter_contract_provider_profile_matches_evidence"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["capture_bundle"]["provider_capture_commands_match_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["dispatch_roundtrip"]["adapter_contract_matches_runtime_session"]
    assert manifest["extra"]["dispatch_roundtrip"]["live_fetch_contract"]["exchange"] == "NFO"
    assert "Dispatch round-trip exchange: NFO" in runbook
    assert "Dispatch round-trip provider capture commands: 2 (runtime match: yes)" in runbook
    assert "Dispatch round-trip adapter execution contract: arrow_money / websocket" in runbook
    assert f"Dispatch round-trip provider profile: {provider_profile_sha256}" in runbook
    assert "- Dispatch round-trip provenance consistent: no" in runbook


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_carries_vendor_batch(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    _inject_nested_roundtrip_vendor_market_data_batch(provider_ack)
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip_with_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    vendor = config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.passed
    assert bool(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_preserves_ack_vendor_batch_as_upstream(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    broker_vendor = _vendor_market_data_batch_config()
    ack_summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(ack_summary_path)
    ack_summary["dispatch_roundtrip_vendor_market_data_batch_ready"] = False
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"] = True
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"] = True
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] = "arrow_money"
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_kind"] = "ticks"
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] = (
        "vendor_market_data_batch_pipeline"
    )
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_market"] = "india_nse_index_derivatives"
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"] = 2
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"] = 2
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] = 1.0
    ack_summary["broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted"] = True
    ack_summary.to_csv(ack_summary_path, index=False)

    ack_config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"
    ack_config = json.loads(ack_config_path.read_text(encoding="utf-8"))
    ack_config["dispatch_roundtrip_vendor_market_data_batch"] = {
        "provided": False,
        "ready": False,
        "datasets": [],
    }
    ack_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = broker_vendor
    ack_config_path.write_text(
        json.dumps(ack_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip_with_upstream_vendor_batch"

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.passed
    assert "upstream_dispatch_roundtrip_vendor_market_data_batch_ready" in summary.columns
    assert not bool(summary.loc[0, "upstream_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary.loc[0, "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert not bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert not config["upstream_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]
    assert config["upstream_broker_dispatch_roundtrip_vendor_market_data_batch"]["comparison"]["accepted"]
    assert manifest["extra"]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert not manifest["extra"]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert "- Upstream broker dispatch round-trip vendor batch ready: yes" in runbook
    assert "- Fresh broker dispatch round-trip vendor batch ready: no" in runbook


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_preserves_upstream_roundtrip(tmp_path):
    provider_ack = _write_ready_provider_imbalance_broker_dispatch_ack(tmp_path)
    upstream_provider_dir = tmp_path / "upstream_provider_imbalance_broker_dispatch_roundtrip"
    upstream_nested_dir = upstream_provider_dir / "broker_dispatch_roundtrip"
    upstream_nested_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"passed": True, "ready": True}]).to_csv(
        upstream_nested_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )

    ack_summary_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    ack_summary = pd.read_csv(ack_summary_path)
    ack_summary["provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    ack_summary["dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    ack_summary["dispatch_roundtrip_provided"] = True
    ack_summary["dispatch_roundtrip_ready"] = True
    ack_summary["dispatch_roundtrip_failed_checks"] = 0
    ack_summary.to_csv(ack_summary_path, index=False)

    ack_config_path = provider_ack.output_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json"
    ack_config = json.loads(ack_config_path.read_text(encoding="utf-8"))
    ack_inputs = ack_config.setdefault("broker_dispatch_ack_inputs", {})
    ack_inputs["provider_dispatch_roundtrip_dir"] = str(upstream_provider_dir)
    ack_inputs["dispatch_roundtrip_dir"] = str(upstream_nested_dir)
    ack_config_path.write_text(json.dumps(ack_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    out_dir = tmp_path / "provider_imbalance_broker_dispatch_roundtrip"
    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        provider_ack.output_dir,
        out_dir,
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(),
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    config = json.loads(
        (out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report.passed
    assert Path(summary.loc[0, "upstream_provider_dispatch_roundtrip_dir"]) == upstream_provider_dir
    assert Path(summary.loc[0, "upstream_dispatch_roundtrip_dir"]) == upstream_nested_dir
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_provided"])
    assert bool(summary.loc[0, "upstream_dispatch_roundtrip_ready"])
    assert int(summary.loc[0, "upstream_dispatch_roundtrip_failed_checks"]) == 0
    assert config["broker_dispatch_roundtrip_inputs"]["upstream_provider_dispatch_roundtrip_dir"] == str(
        upstream_provider_dir
    )
    assert config["broker_dispatch_roundtrip_inputs"]["upstream_dispatch_roundtrip_dir"] == str(upstream_nested_dir)
    assert Path(manifest["inputs"]["upstream_provider_dispatch_roundtrip"]["path"]) == upstream_provider_dir.resolve()
    assert Path(manifest["inputs"]["upstream_dispatch_roundtrip"]["path"]) == upstream_nested_dir.resolve()


def test_provider_market_data_imbalance_broker_dispatch_roundtrip_blocks_unready_ack(tmp_path):
    ack_dir = tmp_path / "provider_imbalance_broker_dispatch_ack"
    ack_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "passed": False,
                "ready": False,
                "broker_dispatch_ack_passed": False,
                "broker_dispatch_dir": "",
                "broker_dispatch_send_dir": "",
                "broker_dispatch_ack_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(ack_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv", index=False)
    (ack_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").write_text(
        json.dumps({"broker_dispatch_ack_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        ack_dir,
        tmp_path / "provider_imbalance_broker_dispatch_roundtrip",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert "provider_broker_dispatch_ack_passed" in failed
    assert "provider_nested_broker_dispatch_ack_passed" in failed
    assert "generic_broker_dispatch_input_resolved" in failed
    assert "generic_broker_dispatch_send_input_resolved" in failed
    assert "generic_broker_dispatch_ack_input_resolved" in failed
    assert "broker_dispatch_roundtrip_runnable" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "reconcile-provider-market-data-imbalance-broker-dispatch"
    assert not (report.output_dir / "broker_dispatch_roundtrip" / "broker_dispatch_roundtrip_summary.csv").exists()


def test_cli_provider_market_data_imbalance_broker_dispatch_roundtrip_blocks_unready_ack(tmp_path):
    ack_dir = tmp_path / "provider_imbalance_broker_dispatch_ack"
    ack_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "passed": False,
                "ready": False,
                "broker_dispatch_ack_passed": False,
                "broker_dispatch_dir": "",
                "broker_dispatch_send_dir": "",
                "broker_dispatch_ack_dir": "",
                "provider": "arrow_money",
                "transport": "websocket",
                "strategy": "imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "shadow",
                "adapter": "arrow_money",
            }
        ]
    ).to_csv(ack_dir / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv", index=False)
    (ack_dir / "provider_market_data_imbalance_broker_dispatch_ack_config.json").write_text(
        json.dumps({"broker_dispatch_ack_inputs": {}}, indent=2) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_provider_imbalance_broker_dispatch_roundtrip"

    code = main(
        [
            "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
            "--provider-broker-dispatch-ack",
            str(ack_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert not bool(summary.loc[0, "broker_dispatch_roundtrip_passed"])
    assert summary.loc[0, "next_gate"] == "reconcile-provider-market-data-imbalance-broker-dispatch"
