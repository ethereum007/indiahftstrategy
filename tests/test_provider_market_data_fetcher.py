import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_fetcher import (
    ProviderMarketDataFetcherConfig,
    write_provider_market_data_fetcher_plan,
)


def _write_source_and_fetch_plan(tmp_path, *, transport="websocket"):
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
        return write_market_data_fetch_plan(
            source_report.output_dir / "market_data_source_config.json",
            tmp_path / "fetch_file",
            config=MarketDataFetchConfig(),
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
    return write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / f"fetch_{transport}",
        config=MarketDataFetchConfig(
            symbols=("NIFTY-I", "BANKNIFTY-I"),
            window_start="2026-06-10 09:15:00" if transport == "rest" else "",
            window_end="2026-06-10 15:30:00" if transport == "rest" else "",
        ),
    )


def test_provider_market_data_fetcher_writes_websocket_template(tmp_path):
    fetch_report = _write_source_and_fetch_plan(tmp_path)
    out_dir = tmp_path / "provider_fetcher"

    report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        out_dir,
        config=ProviderMarketDataFetcherConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_fetcher_config.json").read_text(encoding="utf-8"))
    template = json.loads((out_dir / "provider_market_data_request_template.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "provider_market_data_fetcher_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["template_kind"] == "websocket_subscription"
    assert summary["next_gate"] == "provider_fetcher_client"
    assert template["transport"] == "websocket"
    assert template["authentication"]["env_vars"] == ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"]
    assert template["authentication"]["values_stored"] is False
    assert template["subscriptions"][0]["symbol"] == "NIFTY-I"
    assert config["credentials"]["values_stored"] is False
    assert config["primary_action"]["action"] == "review_provider_fetcher_request_template"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert manifest["run_type"] == "provider_market_data_fetcher_plan"


def test_provider_market_data_fetcher_can_require_env_presence(tmp_path, monkeypatch):
    fetch_report = _write_source_and_fetch_plan(tmp_path)
    monkeypatch.delenv("ARROW_MONEY_API_KEY", raising=False)
    monkeypatch.delenv("ARROW_MONEY_API_SECRET", raising=False)

    missing = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / "provider_fetcher_missing_env",
        config=ProviderMarketDataFetcherConfig(require_env_present=True),
    )
    failed = set(missing.checks.loc[~missing.checks["passed"].astype(bool), "check"])
    assert not missing.ready
    assert "credential_env_vars_present_in_runtime" in failed

    monkeypatch.setenv("ARROW_MONEY_API_KEY", "not-written-to-artifacts")
    monkeypatch.setenv("ARROW_MONEY_API_SECRET", "not-written-to-artifacts")
    ready = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / "provider_fetcher_ready_env",
        config=ProviderMarketDataFetcherConfig(require_env_present=True),
    )
    artifact = json.loads(
        (ready.output_dir / "provider_market_data_fetcher_config.json").read_text(encoding="utf-8")
    )
    assert ready.ready
    assert artifact["credentials"]["env_presence"] == {
        "ARROW_MONEY_API_KEY": True,
        "ARROW_MONEY_API_SECRET": True,
    }
    assert "not-written-to-artifacts" not in json.dumps(artifact)


def test_provider_market_data_fetcher_blocks_file_fetch_plan(tmp_path):
    fetch_report = _write_source_and_fetch_plan(tmp_path, transport="file")

    report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / "provider_fetcher",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads(
        (report.output_dir / "provider_market_data_fetcher_config.json").read_text(encoding="utf-8")
    )
    assert not report.ready
    assert "transport_is_live" in failed
    assert config["blocked_actions"][0]["next_gate"] == "plan-market-data-fetch"


def test_cli_provider_market_data_fetcher_accepts_rest_fetch_plan(tmp_path):
    fetch_report = _write_source_and_fetch_plan(tmp_path, transport="rest")
    out_dir = tmp_path / "cli_provider_fetcher"

    code = main(
        [
            "plan-provider-market-data-fetcher",
            "--fetch-plan",
            str(fetch_report.output_dir / "market_data_fetch_config.json"),
            "--out",
            str(out_dir),
            "--connect-timeout-ms",
            "2500",
            "--read-timeout-ms",
            "750",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_fetcher_summary.csv")
    template = json.loads((out_dir / "provider_market_data_request_template.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "template_kind"] == "rest_backfill_request"
    assert template["method"] == "GET"
    assert template["query"]["window_start"] == "2026-06-10 09:15:00"
