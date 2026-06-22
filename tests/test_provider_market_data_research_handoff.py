import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan
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
from reports.provider_market_data_research_handoff import (
    ProviderMarketDataResearchHandoffConfig,
    write_provider_market_data_research_handoff,
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
            min_capture_rows=2,
            pipeline_min_rows=2,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )


def _write_capture(path: str | Path, day: str, *, base: float):
    capture = Path(path)
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        f"{day} 09:15:00,{base:.2f},{base + 0.05:.2f},75,150,{base + 0.05:.2f},75\n"
        f"{day} 09:15:01,{base + 0.05:.2f},{base + 0.10:.2f},100,125,{base + 0.05:.2f},50\n",
        encoding="utf-8",
    )


def _write_expected_captures(live_packet_path):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    for idx, window in enumerate(packet["capture_windows"]):
        _write_capture(window["capture_path"], "2026-06-23", base=100.0 + idx)


def _write_real_ingest(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    _write_expected_captures(live_packet)
    return write_provider_market_data_live_session_ingest(live_packet, tmp_path / "live_ingest")


def _write_real_evidence(tmp_path):
    ingest = _write_real_ingest(tmp_path)
    return write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )


def _write_rehearsal_ingest(tmp_path):
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
    return write_provider_market_data_live_rehearsal(
        bundle.output_dir / "provider_market_data_live_capture_bundle.json",
        tmp_path / "rehearsal",
        config=ProviderMarketDataLiveRehearsalConfig(
            rows_per_window=3,
            ingest_output_dir=str(tmp_path / "rehearsal_ingest"),
            ingest_min_capture_rows=2,
            ingest_pipeline_min_rows=2,
        ),
    )


def _write_synthetic_smoke_evidence(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)
    return write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(
            allow_synthetic_rehearsal=True,
            min_capture_rows=2,
        ),
    )


def test_provider_market_data_research_handoff_builds_imbalance_commands_from_live_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    out_dir = tmp_path / "handoff"

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        out_dir,
        config=ProviderMarketDataResearchHandoffConfig(
            output_root=str(tmp_path / "research"),
            min_tick_folds=2,
            tick_size=0.05,
        ),
    )

    summary = report.summary.iloc[0]
    commands = pd.read_csv(out_dir / "provider_market_data_research_handoff_commands.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_research_handoff_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary["research_ready"])
    assert summary["dataset_count"] == 2
    assert summary["ready_command_count"] == 2
    assert set(commands["run_type"]) == {"imbalance_edge_walkforward", "imbalance_replay_walkforward"}
    assert commands["command"].str.contains("walkforward-imbalance-edge").any()
    assert commands["command"].str.contains("candidate_config.json", regex=False).any()
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "walkforward-imbalance-edge"
    assert "walkforward-imbalance-edge" in action_queue.loc[0, "next_gate_help_command"]
    assert manifest["run_type"] == "provider_market_data_research_handoff"


def test_provider_market_data_research_handoff_blocks_synthetic_smoke_evidence(tmp_path):
    evidence = _write_synthetic_smoke_evidence(tmp_path)

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(output_root=str(tmp_path / "research")),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert evidence.ready
    assert not bool(evidence.summary.iloc[0]["research_ready"])
    assert not report.ready
    assert not bool(summary["research_ready"])
    assert "live_evidence_research_ready" in failed
    assert "synthetic_rehearsal_absent" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-live-evidence"


def test_provider_market_data_research_handoff_blocks_unsupported_strategy(tmp_path):
    evidence = _write_real_evidence(tmp_path)

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(
            strategies=("leadlag",),
            output_root=str(tmp_path / "research"),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    command = report.commands.iloc[0]
    assert not report.ready
    assert "requested_strategies_supported" in failed
    assert command["queue_status"] == "blocked"
    assert command["next_gate"] == "walkforward-leadlag-replay"
    assert "leader/laggard" in command["reason"]


def test_cli_provider_market_data_research_handoff_accepts_live_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    out_dir = tmp_path / "cli_handoff"

    code = main(
        [
            "handoff-provider-market-data-research",
            "--live-evidence-dir",
            str(evidence.output_dir),
            "--out",
            str(out_dir),
            "--output-root",
            str(tmp_path / "research"),
            "--min-tick-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_research_handoff_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "ready_command_count"]) == 2
