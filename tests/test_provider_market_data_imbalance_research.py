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
from reports.provider_market_data_live_ingest import write_provider_market_data_live_session_ingest
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


def _write_ready_ops_launch_evidence(tmp_path):
    out_dir = tmp_path / "ops_launch_evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": True,
                "failed_checks": 0,
                "recommendation": "eligible_for_live_dryrun_route_review",
                "evidence_profile": "ops_launch",
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


def test_provider_market_data_imbalance_research_blocks_synthetic_smoke_evidence(tmp_path):
    evidence = _write_synthetic_smoke_evidence(tmp_path)
    out_dir = tmp_path / "provider_imbalance_research"

    report = write_provider_market_data_imbalance_research(
        evidence.output_dir,
        out_dir,
        config=_passing_config(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert evidence.ready
    assert not bool(evidence.summary.iloc[0]["research_ready"])
    assert not report.ready
    assert report.pipeline is None
    assert "provider_research_handoff_ready" in failed
    assert "provider_research_handoff_research_ready" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
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
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "route_readiness_ready" in failed
    assert bool(summary.loc[0, "provider_launch_evidence_ready"])
    assert not bool(summary.loc[0, "route_readiness_ready"])
    assert summary.loc[0, "next_gate"] == "review-strategy-evidence --profile ops_launch --require-file-inputs"
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "next_gate"] == (
        "review-strategy-evidence --profile ops_launch --require-file-inputs"
    )
    assert not bool(route_summary.loc[0, "ready"])
    assert manifest["run_type"] == "provider_market_data_imbalance_route_readiness"
    assert "market_portability" in manifest["inputs"]
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
