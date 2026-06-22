import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan
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


def _first_capture_path(live_packet_path):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    return Path(packet["capture_windows"][0]["capture_path"])


def test_provider_market_data_live_preflight_accepts_ready_future_session(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    out_dir = tmp_path / "preflight"

    report = write_provider_market_data_live_session_preflight(
        live_packet,
        out_dir,
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )

    summary = report.summary.iloc[0]
    action_queue = pd.read_csv(out_dir / "provider_market_data_live_preflight_action_queue.csv")
    config = json.loads((out_dir / "provider_market_data_live_preflight_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["timing_status"] == "before_first_window"
    assert summary["expected_capture_count"] == 2
    assert summary["existing_capture_count"] == 0
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "action"] == "run_provider_live_capture_windows"
    assert config["ready"]
    assert config["primary_action"]["next_gate"] == "provider_fetcher_live_run"
    assert config["environment"]["values_stored"] is False
    assert "ARROW_MONEY_API_KEY" in config["session_packet"]["authentication"]["env_vars"]
    assert sorted(config["session_packet"]["authentication"].keys()) == [
        "env_presence",
        "env_vars",
        "injection",
        "values_stored",
    ]
    assert manifest["run_type"] == "provider_market_data_live_preflight"


def test_provider_market_data_live_preflight_blocks_existing_capture_collision(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    capture = _first_capture_path(live_packet)
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text("ts,bid,ask,bid_qty,ask_qty,last,last_qty\n", encoding="utf-8")

    report = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )

    summary = report.summary.iloc[0]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert summary["existing_capture_count"] == 1
    assert "capture_files_do_not_already_exist" in failed
    assert report.action_queue.loc[0, "next_gate"] == "preflight-provider-market-data-live-session"


def test_provider_market_data_live_preflight_blocks_missing_runtime_env_when_required(tmp_path, monkeypatch):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    monkeypatch.delenv("ARROW_MONEY_API_KEY", raising=False)
    monkeypatch.delenv("ARROW_MONEY_API_SECRET", raising=False)

    report = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(
            now_iso="2026-06-23T08:45:00+05:30",
            require_env_present=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "credential_env_vars_present_in_runtime" in failed
    assert report.action_queue.loc[0, "next_gate"] == "provider_credentials_runtime"


def test_cli_provider_market_data_live_preflight_accepts_session_packet(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    out_dir = tmp_path / "cli_preflight"

    code = main(
        [
            "preflight-provider-market-data-live-session",
            "--live-session-packet",
            str(live_packet),
            "--out",
            str(out_dir),
            "--now-iso",
            "2026-06-23T08:45:00+05:30",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_preflight_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "timing_status"] == "before_first_window"
