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
    assert bool(summary["credential_env_template_exists"])
    assert len(summary["credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert template["transport"] == "websocket"
    assert template["exchange"] == "NFO"
    assert template["session"]["timezone"] == "Asia/Kolkata"
    assert template["authentication"]["env_vars"] == ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"]
    assert template["authentication"]["env_template"]["exists"] is True
    assert len(template["authentication"]["env_template"]["sha256"]) == 64
    assert template["authentication"]["values_stored"] is False
    assert template["subscriptions"][0]["symbol"] == "NIFTY-I"
    assert template["subscriptions"][0]["exchange"] == "NFO"
    assert template["adapter_execution_contract"]["provider"] == "arrow_money"
    assert template["adapter_execution_contract"]["adapter"] == "arrow_money"
    assert template["adapter_execution_contract"]["transport"] == "websocket"
    assert template["adapter_execution_contract"]["credential_env_vars"] == [
        "ARROW_MONEY_API_KEY",
        "ARROW_MONEY_API_SECRET",
    ]
    assert template["adapter_execution_contract"]["credential_env_template"]["sha256"] == (
        template["authentication"]["env_template"]["sha256"]
    )
    assert template["adapter_execution_contract"]["output_filename"] == "provider_market_data.csv"
    assert template["adapter_execution_contract"]["values_stored"] is False
    assert config["credentials"]["values_stored"] is False
    assert config["credentials"]["env_template"]["sha256"] == template["authentication"]["env_template"]["sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["fetch_plan"]["credential_env_template"]["sha256"] == config["credentials"]["env_template"]["sha256"]
    assert config["fetch_plan"]["live_fetch_contract"]["available"] is True
    assert config["primary_action"]["action"] == "review_provider_fetcher_request_template"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert manifest["run_type"] == "provider_market_data_fetcher_plan"
    assert manifest["inputs"]["credential_env_template"]["sha256"] == config["credentials"]["env_template"]["sha256"]
    assert manifest["extra"]["credential_env_template"]["exists"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"


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


def test_provider_market_data_fetcher_blocks_missing_fetch_env_template_proof(tmp_path):
    fetch_report = _write_source_and_fetch_plan(tmp_path)
    fetch_config_path = fetch_report.output_dir / "market_data_fetch_config.json"
    payload = json.loads(fetch_config_path.read_text(encoding="utf-8"))
    payload["credentials"]["env_template"] = {"path": "", "exists": False, "sha256": ""}
    fetch_config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_provider_market_data_fetcher_plan(
        fetch_config_path,
        tmp_path / "provider_fetcher_missing_env_template",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads(
        (report.output_dir / "provider_market_data_fetcher_config.json").read_text(encoding="utf-8")
    )
    assert not report.ready
    assert "credential_env_template_carried" in failed
    assert config["credentials"]["env_template"]["exists"] is False
    assert config["blocked_actions"][0]["next_gate"] == "plan-market-data-fetch"
    assert config["blocked_actions"][0]["action"] == "regenerate_fetch_plan_with_credential_env_template"


def test_provider_market_data_fetcher_blocks_missing_source_live_contract(tmp_path):
    fetch_report = _write_source_and_fetch_plan(tmp_path)
    fetch_config_path = fetch_report.output_dir / "market_data_fetch_config.json"
    payload = json.loads(fetch_config_path.read_text(encoding="utf-8"))
    payload["source_plan"]["live_fetch_contract"] = {"available": False, "next_gate": ""}
    fetch_config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_provider_market_data_fetcher_plan(
        fetch_config_path,
        tmp_path / "provider_fetcher_missing_live_contract",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads(
        (report.output_dir / "provider_market_data_fetcher_config.json").read_text(encoding="utf-8")
    )
    assert not report.ready
    assert "source_live_fetch_contract_carried" in failed
    assert config["fetch_plan"]["live_fetch_contract"]["available"] is False
    assert config["blocked_actions"][0]["next_gate"] == "plan-market-data-fetch"
    assert config["blocked_actions"][0]["action"] == "regenerate_fetch_plan_with_source_live_fetch_contract"


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
    assert template["adapter_execution_contract"]["transport"] == "rest"
    assert template["adapter_execution_contract"]["mode"] == "provider_rest_backfill"
