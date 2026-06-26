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


def _write_bundle_linked_real_ingest(tmp_path):
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
    _write_expected_captures(live_packet)
    ingest = write_provider_market_data_live_session_ingest(
        live_packet,
        tmp_path / "live_ingest",
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )
    return ingest, bundle_path


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


def test_provider_market_data_live_evidence_accepts_real_provider_ingest(tmp_path):
    ingest = _write_real_ingest(tmp_path)
    out_dir = tmp_path / "evidence"

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        out_dir,
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    summary = report.summary.iloc[0]
    action_queue = pd.read_csv(out_dir / "provider_market_data_live_evidence_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["research_ready"]
    assert summary["synthetic_capture_count"] == 0
    assert summary["recommendation"] == "feed_walkforward_research"
    assert action_queue.loc[0, "next_gate"] == "review-data-readiness"
    assert manifest["run_type"] == "provider_market_data_live_evidence_review"


def test_provider_market_data_live_evidence_carries_capture_bundle_provenance(tmp_path):
    ingest, bundle_path = _write_bundle_linked_real_ingest(tmp_path)
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    out_dir = tmp_path / "evidence_with_bundle"

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        out_dir,
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_live_evidence_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["research_ready"]
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert summary["capture_bundle_provided"]
    assert summary["capture_bundle_ready"]
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert summary["capture_env_template_exists"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert summary["adapter_handoff_provided"]
    assert summary["adapter_handoff_exists"]
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_exists"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())


def test_provider_market_data_live_evidence_blocks_synthetic_rehearsal_by_default(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)

    report = write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert not summary["research_ready"]
    assert summary["synthetic_capture_count"] == 2
    assert "synthetic_rehearsal_absent" in failed
    assert report.action_queue.loc[0, "next_gate"] == "provider_fetcher_live_run"


def test_provider_market_data_live_evidence_allows_rehearsal_as_smoke_only(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)

    report = write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(
            allow_synthetic_rehearsal=True,
            min_capture_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert not summary["research_ready"]
    assert summary["recommendation"] == "rehearsal_backend_smoke_only"
    assert report.action_queue.loc[0, "action"] == "replace_synthetic_captures_with_provider_live_captures"
    assert report.action_queue.loc[0, "next_gate"] == "provider_fetcher_live_run"


def test_cli_provider_market_data_live_evidence_accepts_real_provider_ingest(tmp_path):
    ingest = _write_real_ingest(tmp_path)
    out_dir = tmp_path / "cli_evidence"

    code = main(
        [
            "review-provider-market-data-live-evidence",
            "--live-ingest-dir",
            str(ingest.output_dir),
            "--out",
            str(out_dir),
            "--min-capture-rows",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_evidence_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "research_ready"])
