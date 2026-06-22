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
