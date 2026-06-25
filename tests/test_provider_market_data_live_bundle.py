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
from reports.provider_market_data_live_preflight import (
    ProviderMarketDataLivePreflightConfig,
    write_provider_market_data_live_session_preflight,
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


def _live_packet(plan):
    return plan.output_dir / "provider_market_data_live_session_packet.json"


def _write_preflight(tmp_path, live_packet):
    return write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )


def _first_capture_path(live_packet_path):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    return Path(packet["capture_windows"][0]["capture_path"])


def test_provider_market_data_live_capture_bundle_accepts_ready_preflight(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    preflight = _write_preflight(tmp_path, live_packet)
    out_dir = tmp_path / "capture_bundle"

    report = write_provider_market_data_live_capture_bundle(
        live_packet,
        out_dir,
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            ingest_output_dir=str(tmp_path / "live_ingest"),
        ),
    )

    summary = report.summary.iloc[0]
    commands = pd.read_csv(out_dir / "provider_market_data_live_capture_commands.csv")
    bundle = json.loads((out_dir / "provider_market_data_live_capture_bundle.json").read_text(encoding="utf-8"))
    handoff = json.loads((out_dir / "provider_market_data_adapter_handoff.json").read_text(encoding="utf-8"))
    env_template = (out_dir / "provider_market_data_live_capture_env_template.env").read_text(encoding="utf-8")
    runbook = (out_dir / "provider_market_data_live_capture_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["command_count"] == 2
    assert summary["preflight_ready"]
    assert "provider-adapter capture" in commands.loc[0, "adapter_command"]
    assert "ingest-provider-market-data-live-session" in summary["post_capture_ingest_command"]
    assert bundle["authentication"]["values_stored"] is False
    assert bundle["authentication"]["env_template"] == "provider_market_data_live_capture_env_template.env"
    assert "ARROW_MONEY_API_KEY=\n" in env_template
    assert "ARROW_MONEY_API_SECRET=\n" in env_template
    assert handoff["provider"] == "arrow_money"
    assert handoff["transport"] == "websocket"
    assert handoff["authentication"]["values_stored"] is False
    assert handoff["authentication"]["env_vars"] == ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"]
    assert handoff["output"]["schema_columns"] == ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
    assert len(handoff["capture_windows"]) == 2
    assert "provider-adapter capture" in handoff["capture_windows"][0]["adapter_command"]
    assert "ingest-provider-market-data-live-session" in handoff["post_capture_ingest_command"]
    assert handoff["handoff_invariants"]["credential_values_must_not_be_persisted"]
    assert report.adapter_handoff["provider"] == "arrow_money"
    assert bundle["primary_action"]["next_gate"] == "ingest-provider-market-data-live-session"
    assert bundle["commands"][0]["queue_status"] == "ready"
    assert "provider_market_data_adapter_handoff.json" in runbook
    assert manifest["run_type"] == "provider_market_data_live_capture_bundle"
    assert manifest["extra"]["adapter_handoff_file"] == "provider_market_data_adapter_handoff.json"
    assert "provider_market_data_live_capture_env_template.env" in {
        artifact["path"] for artifact in manifest["artifacts"]
    }
    assert "provider_market_data_adapter_handoff.json" in {artifact["path"] for artifact in manifest["artifacts"]}


def test_provider_market_data_live_capture_bundle_blocks_missing_preflight_by_default(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)

    report = write_provider_market_data_live_capture_bundle(live_packet, tmp_path / "capture_bundle")

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "preflight_config_path_provided" in failed
    assert report.action_queue.loc[0, "next_gate"] == "preflight-provider-market-data-live-session"


def test_provider_market_data_live_capture_bundle_blocks_existing_capture_collision(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    capture = _first_capture_path(live_packet)
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text("ts,bid,ask,bid_qty,ask_qty,last,last_qty\n", encoding="utf-8")
    preflight = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(
            now_iso="2026-06-23T08:45:00+05:30",
            allow_existing_captures=True,
        ),
    )

    report = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "capture_bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json")
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_files_do_not_already_exist" in failed
    assert report.summary.iloc[0]["capture_file_collision_count"] == 1


def test_cli_provider_market_data_live_capture_bundle_accepts_ready_preflight(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    preflight = _write_preflight(tmp_path, live_packet)
    out_dir = tmp_path / "cli_capture_bundle"

    code = main(
        [
            "bundle-provider-market-data-live-capture",
            "--live-session-packet",
            str(live_packet),
            "--preflight-config",
            str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            "--out",
            str(out_dir),
            "--ingest-output-dir",
            str(tmp_path / "live_ingest"),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_capture_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "command_count"] == 2
