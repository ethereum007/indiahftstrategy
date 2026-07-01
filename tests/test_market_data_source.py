import json

import pandas as pd

from hft_cli import main
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan


def test_market_data_source_plan_accepts_arrow_file_source(tmp_path):
    source = tmp_path / "arrow ticks.csv"
    source.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        "2026-06-10 09:15:00,100.0,100.05,75,150,100.05,75\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "source_plan"

    report = write_market_data_source_plan(
        out_dir,
        config=MarketDataSourceConfig(
            provider="arrow_money",
            adapter="arrow_money",
            kind="ticks",
            transport="file",
            source_uri=str(source),
            market="india_nse_index_derivatives",
            label="arrow_day1",
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "market_data_source_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "market_data_source_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    env_template = (out_dir / "market_data_source_env_template.env").read_text(encoding="utf-8")
    assert report.ready
    assert bool(summary["source_file_exists"])
    assert len(summary["source_file_sha256"]) == 64
    assert summary["next_gate"] == "pipeline-vendor-market-data"
    assert config["ready"]
    assert config["source"]["file_exists"]
    assert config["credentials"]["values_stored"] is False
    assert config["credentials"]["env_template_file"] == "market_data_source_env_template.env"
    assert config["normalized_pipeline"]["available"]
    assert config["live_fetch_contract"]["available"] is False
    assert "pipeline-vendor-market-data" in config["normalized_pipeline"]["command"]
    assert env_template == ""
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "action"] == "run_vendor_market_data_pipeline"
    assert manifest["run_type"] == "market_data_source_plan"
    assert manifest["inputs"]["source_file"]["sha256"] == summary["source_file_sha256"]
    assert manifest["extra"]["credential_env_template_file"] == "market_data_source_env_template.env"
    assert manifest["extra"]["provider_profile"]["provider"] == "arrow_money"
    assert len(manifest["extra"]["provider_profile"]["sha256"]) == 64
    assert "market_data_source_env_template.env" in {artifact["path"] for artifact in manifest["artifacts"]}


def test_market_data_source_plan_accepts_arrow_websocket_env_contract(tmp_path):
    out_dir = tmp_path / "source_plan"

    report = write_market_data_source_plan(
        out_dir,
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind="ticks",
            transport="websocket",
            source_uri="wss://feed.arrow.money/market-data/nse",
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "market_data_source_config.json").read_text(encoding="utf-8"))
    env_template = (out_dir / "market_data_source_env_template.env").read_text(encoding="utf-8")
    runbook = (out_dir / "market_data_source_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert summary["adapter"] == "arrow_money"
    assert summary["source_uri_kind"] == "wss"
    assert summary["exchange"] == "NFO"
    assert summary["session_timezone"] == "Asia/Kolkata"
    assert summary["session_open_local"] == "09:15:00"
    assert summary["session_close_local"] == "15:30:00"
    assert summary["auth_env_var_count"] == 2
    assert summary["credential_env_template_file"] == "market_data_source_env_template.env"
    assert bool(summary["live_fetch_contract_available"])
    assert "plan-market-data-fetch" in summary["live_fetch_contract_command"]
    assert config["normalized_pipeline"]["available"] is False
    assert config["exchange"] == "NFO"
    assert config["provider_profile"]["provider"] == "arrow_money"
    assert config["provider_profile"]["adapter"] == "arrow_money"
    assert config["provider_profile"]["transports"] == ["file", "rest", "websocket"]
    assert config["provider_profile"]["credential_env_vars"] == [
        "ARROW_MONEY_API_KEY",
        "ARROW_MONEY_API_SECRET",
    ]
    assert len(config["provider_profile"]["sha256"]) == 64
    assert config["session"] == {
        "timezone": "Asia/Kolkata",
        "open_local": "09:15:00",
        "close_local": "15:30:00",
    }
    assert config["live_fetch_contract"]["available"] is True
    assert config["live_fetch_contract"]["next_gate"] == "provider_fetcher"
    assert config["live_fetch_contract"]["required_inputs"] == ["symbol"]
    assert config["live_fetch_contract"]["exchange"] == "NFO"
    assert config["live_fetch_contract"]["provider_profile_sha256"] == config["provider_profile"]["sha256"]
    assert config["live_fetch_contract"]["session"]["timezone"] == "Asia/Kolkata"
    assert "market_data_source_config.json" in config["live_fetch_contract"]["command_template"]
    assert "ARROW_MONEY_API_KEY=\n" in env_template
    assert "ARROW_MONEY_API_SECRET=\n" in env_template
    assert "Live fetch contract command" in runbook
    assert config["next_gate"] == "provider_fetcher"
    assert config["primary_action"]["action"] == "wire_provider_market_data_fetcher"
    assert config["credentials"]["env_vars"] == ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"]
    assert config["credentials"]["env_template_entry_count"] == 2
    assert config["credentials"]["values_stored"] is False


def test_market_data_source_plan_defaults_irage_live_env_contract(tmp_path):
    out_dir = tmp_path / "source_plan"

    report = write_market_data_source_plan(
        out_dir,
        config=MarketDataSourceConfig(
            provider="irage",
            kind="ticks",
            transport="rest",
            source_uri="https://api.irage.example/market-data/nfo/ticks",
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "market_data_source_config.json").read_text(encoding="utf-8"))
    env_template = (out_dir / "market_data_source_env_template.env").read_text(encoding="utf-8")
    assert report.ready
    assert summary["provider"] == "irage"
    assert summary["adapter"] == "irage"
    assert summary["transport"] == "rest"
    assert summary["auth_env_var_count"] == 2
    assert summary["auth_env_vars"] == "IRAGE_API_KEY;IRAGE_API_SECRET"
    assert bool(summary["live_fetch_contract_available"])
    assert config["credentials"]["env_vars"] == ["IRAGE_API_KEY", "IRAGE_API_SECRET"]
    assert config["credentials"]["env_template_entry_count"] == 2
    assert config["credentials"]["values_stored"] is False
    assert config["provider_profile"]["provider"] == "irage"
    assert config["provider_profile"]["adapter"] == "irage"
    assert config["provider_profile"]["credential_env_vars"] == ["IRAGE_API_KEY", "IRAGE_API_SECRET"]
    assert "live_ticks" in config["provider_profile"]["capabilities"]
    assert len(config["provider_profile"]["sha256"]) == 64
    assert config["next_gate"] == "provider_fetcher"
    assert config["live_fetch_contract"]["required_inputs"] == ["symbol", "window_start", "window_end"]
    assert config["live_fetch_contract"]["provider_profile_sha256"] == config["provider_profile"]["sha256"]
    assert "IRAGE_API_KEY=\n" in env_template
    assert "IRAGE_API_SECRET=\n" in env_template


def test_market_data_source_plan_blocks_missing_live_credentials_and_embedded_secret(tmp_path):
    out_dir = tmp_path / "source_plan"

    report = write_market_data_source_plan(
        out_dir,
        config=MarketDataSourceConfig(
            provider="irage",
            kind="ticks",
            transport="rest",
            source_uri="https://api.irage.example/ticks?token=secret-value",
            auth_env_vars=("IRAGE_API_KEY=secret-value",),
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"auth_env_vars_are_names", "source_uri_has_no_secret_query"} <= failed
    summary = report.summary.iloc[0]
    assert "secret-value" not in summary["source_uri"]
    assert "token=%2A%2A%2A" in summary["source_uri"]
    config = json.loads((out_dir / "market_data_source_config.json").read_text(encoding="utf-8"))
    assert config["blocked_action_count"] >= 2
    assert "secret-value" not in config["source"]["uri"]


def test_market_data_source_plan_blocks_invalid_session_metadata(tmp_path):
    out_dir = tmp_path / "source_plan"

    report = write_market_data_source_plan(
        out_dir,
        config=MarketDataSourceConfig(
            provider="irage",
            kind="ticks",
            transport="websocket",
            source_uri="wss://feed.irage.example/nse",
            auth_env_vars=("IRAGE_API_KEY",),
            session_timezone="Mars/Base",
            session_open="15:30:00",
            session_close="09:15:00",
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {"session_timezone_known", "session_window_order"} <= failed
    config = json.loads((out_dir / "market_data_source_config.json").read_text(encoding="utf-8"))
    assert config["blocked_actions"][0]["action"] == "fix_market_session_metadata"


def test_cli_market_data_source_plan(tmp_path):
    source = tmp_path / "irage_ticks.csv"
    source.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        "2026-06-10 09:15:00,100.0,100.05,75,150,100.05,75\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_plan"

    code = main(
        [
            "plan-market-data-source",
            "--out",
            str(out_dir),
            "--provider",
            "irage",
            "--adapter",
            "irage",
            "--kind",
            "ticks",
            "--transport",
            "file",
            "--source-uri",
            str(source),
            "--exchange",
            "nfo",
            "--session-timezone",
            "Asia/Kolkata",
            "--session-open",
            "09:15:00",
            "--session-close",
            "15:30:00",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "market_data_source_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "provider"] == "irage"
    assert summary.loc[0, "exchange"] == "NFO"
