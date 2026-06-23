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
from reports.provider_market_data_imbalance_scaleup import (
    ProviderMarketDataImbalanceScaleupConfig,
    write_provider_market_data_imbalance_scaleup_plan,
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
    assert summary.loc[0, "next_gate"] == "build-runtime-telemetry"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "build-runtime-telemetry"
    assert bool(scaleup_summary.loc[0, "ready"])
    assert scaleup_summary.loc[0, "strategy"] == "imbalance"
    assert manifest["run_type"] == "provider_market_data_imbalance_scaleup_plan"
    assert "scaleup" in manifest["inputs"]


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
    assert summary.loc[0, "next_gate"] == "build-runtime-telemetry"
