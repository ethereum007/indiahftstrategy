import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import (
    ProviderMarketDataClientConfig,
    write_provider_market_data_client_plan,
)
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan


def _write_fetcher_plan(tmp_path, *, transport="websocket"):
    source_out = tmp_path / f"source_{transport}"
    if transport == "file":
        source = tmp_path / "arrow_ticks.csv"
        source.write_text(
            "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
            "2026-06-10 09:15:00,100.0,100.05,75,150,100.05,75\n",
            encoding="utf-8",
        )
        source_report = write_market_data_source_plan(
            source_out,
            config=MarketDataSourceConfig(
                provider="arrow_money",
                adapter="arrow_money",
                kind="ticks",
                transport="file",
                source_uri=str(source),
            ),
        )
        fetch_report = write_market_data_fetch_plan(
            source_report.output_dir / "market_data_source_config.json",
            tmp_path / "fetch_file",
            config=MarketDataFetchConfig(),
        )
        return write_provider_market_data_fetcher_plan(
            fetch_report.output_dir / "market_data_fetch_config.json",
            tmp_path / "fetcher_file",
        )

    source_uri = (
        "https://api.arrow.money/market-data/nse/ticks"
        if transport == "rest"
        else "wss://feed.arrow.money/market-data/nse"
    )
    source_report = write_market_data_source_plan(
        source_out,
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind="ticks",
            transport=transport,
            source_uri=source_uri,
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )
    fetch_report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / f"fetch_{transport}",
        config=MarketDataFetchConfig(
            symbols=("NIFTY-I", "BANKNIFTY-I"),
            window_start="2026-06-10 09:15:00" if transport == "rest" else "",
            window_end="2026-06-10 15:30:00" if transport == "rest" else "",
        ),
    )
    return write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / f"fetcher_{transport}",
    )


def test_provider_market_data_client_writes_websocket_packet_and_schema(tmp_path):
    fetcher_report = _write_fetcher_plan(tmp_path)
    out_dir = tmp_path / "client"

    report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        out_dir,
        config=ProviderMarketDataClientConfig(session_label="arrow_ws_day1"),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_client_config.json").read_text(encoding="utf-8"))
    packet = json.loads((out_dir / "provider_market_data_client_packet.json").read_text(encoding="utf-8"))
    schema = pd.read_csv(out_dir / "provider_market_data_output_schema.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_client_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["packet_execution_mode"] == "dry_run"
    assert summary["next_gate"] == "provider_fetcher_live_run"
    assert packet["execution_mode"] == "dry_run"
    assert packet["template_kind"] == "websocket_subscription"
    assert packet["request"]["subscriptions"][0]["symbol"] == "NIFTY-I"
    assert packet["authentication"]["env_vars"] == ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"]
    assert packet["authentication"]["values_stored"] is False
    assert packet["output"]["schema_columns"] == ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
    assert schema["column"].tolist() == packet["output"]["schema_columns"]
    assert config["credentials"]["values_stored"] is False
    assert config["primary_action"]["action"] == "approve_provider_market_data_live_run"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert manifest["run_type"] == "provider_market_data_client_dry_run"


def test_provider_market_data_client_can_require_env_presence(tmp_path, monkeypatch):
    fetcher_report = _write_fetcher_plan(tmp_path)
    monkeypatch.delenv("ARROW_MONEY_API_KEY", raising=False)
    monkeypatch.delenv("ARROW_MONEY_API_SECRET", raising=False)

    missing = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / "client_missing_env",
        config=ProviderMarketDataClientConfig(require_env_present=True),
    )
    failed = set(missing.checks.loc[~missing.checks["passed"].astype(bool), "check"])
    assert not missing.ready
    assert "credential_env_vars_present_in_runtime" in failed

    monkeypatch.setenv("ARROW_MONEY_API_KEY", "not-written-to-artifacts")
    monkeypatch.setenv("ARROW_MONEY_API_SECRET", "not-written-to-artifacts")
    ready = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / "client_ready_env",
        config=ProviderMarketDataClientConfig(require_env_present=True),
    )
    artifact = json.loads((ready.output_dir / "provider_market_data_client_config.json").read_text(encoding="utf-8"))
    packet = json.loads((ready.output_dir / "provider_market_data_client_packet.json").read_text(encoding="utf-8"))
    assert ready.ready
    assert artifact["credentials"]["env_presence"] == {
        "ARROW_MONEY_API_KEY": True,
        "ARROW_MONEY_API_SECRET": True,
    }
    assert "not-written-to-artifacts" not in json.dumps(artifact)
    assert "not-written-to-artifacts" not in json.dumps(packet)


def test_provider_market_data_client_blocks_unready_fetcher_plan(tmp_path):
    fetcher_report = _write_fetcher_plan(tmp_path, transport="file")

    report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / "client",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads((report.output_dir / "provider_market_data_client_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert "fetcher_plan_ready" in failed
    assert config["blocked_actions"][0]["next_gate"] == "plan-provider-market-data-fetcher"


def test_cli_provider_market_data_client_accepts_rest_fetcher_plan(tmp_path):
    fetcher_report = _write_fetcher_plan(tmp_path, transport="rest")
    out_dir = tmp_path / "cli_client"

    code = main(
        [
            "prepare-provider-market-data-client",
            "--fetcher-plan",
            str(fetcher_report.output_dir / "provider_market_data_fetcher_config.json"),
            "--out",
            str(out_dir),
            "--session-label",
            "arrow_rest_backfill_day1",
            "--max-clock-skew-ms",
            "100",
            "--max-local-buffer-rows",
            "50000",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_client_summary.csv")
    packet = json.loads((out_dir / "provider_market_data_client_packet.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "template_kind"] == "rest_backfill_request"
    assert packet["request"]["method"] == "GET"
    assert packet["request"]["query"]["window_start"] == "2026-06-10 09:15:00"
