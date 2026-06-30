import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan
from reports.provider_market_data_live_session import (
    ProviderMarketDataLiveSessionConfig,
    write_provider_market_data_live_session_plan,
)


def _write_client_packet(tmp_path, *, transport="websocket"):
    source_uri = (
        "https://api.arrow.money/market-data/nse/ticks"
        if transport == "rest"
        else "wss://feed.arrow.money/market-data/nse"
    )
    source_report = write_market_data_source_plan(
        tmp_path / f"source_{transport}",
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
            window_start="2026-06-23 09:15:00" if transport == "rest" else "",
            window_end="2026-06-23 15:30:00" if transport == "rest" else "",
        ),
    )
    fetcher_report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / f"fetcher_{transport}",
    )
    client_report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / f"client_{transport}",
    )
    return client_report.output_dir / "provider_market_data_client_packet.json"


def test_provider_market_data_live_session_plan_writes_ready_windows_and_batch_command(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    out_dir = tmp_path / "live_session"

    report = write_provider_market_data_live_session_plan(
        client_packet,
        out_dir,
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-10:00", "close=14:45-15:30"),
            capture_dir=str(tmp_path / "captures"),
            batch_output_dir=str(tmp_path / "batch"),
            min_capture_rows=2,
            pipeline_min_rows=2,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )

    summary = report.summary.iloc[0]
    windows = pd.read_csv(out_dir / "provider_market_data_live_session_windows.csv")
    packet = json.loads((out_dir / "provider_market_data_live_session_packet.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "provider_market_data_live_session_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "provider_market_data_live_session_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["trade_date"] == "2026-06-23"
    assert summary["window_count"] == 2
    assert summary["exchange"] == "NFO"
    assert summary["session_open_local"] == "09:15"
    assert summary["session_close_local"] == "15:30"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert bool(summary["source_session_matches_market_profile"])
    assert bool(summary["credential_env_template_exists"])
    assert len(summary["credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["capture_command_count"] == 2
    assert summary["capture_command_missing_count"] == 0
    assert summary["capture_command_providers"] == "arrow_money"
    assert summary["capture_command_transports"] == "websocket"
    assert "--capture" in summary["post_capture_batch_command"]
    assert "pipeline-provider-market-data-batch" in summary["post_capture_batch_command"]
    assert "--min-unique-source-files 2" in summary["post_capture_batch_command"]
    assert windows["label"].tolist() == ["open", "close"]
    assert windows["within_market_session"].astype(bool).all()
    assert windows.loc[0, "capture_command_provider"] == "arrow_money"
    assert windows.loc[0, "capture_command_transport"] == "websocket"
    assert windows.loc[0, "capture_command_endpoint"] == "wss://feed.arrow.money/market-data/nse"
    assert "provider-adapter capture" in windows.loc[0, "capture_command_template"]
    assert "--provider arrow_money" in windows.loc[0, "capture_command_template"]
    assert "--require-env ARROW_MONEY_API_KEY" in windows.loc[0, "capture_command_template"]
    assert "API_SECRET=" not in windows.loc[0, "capture_command_template"]
    assert packet["authentication"]["values_stored"] is False
    assert packet["authentication"]["env_template"]["exists"] is True
    assert packet["exchange"] == "NFO"
    assert packet["source_session"] == {
        "timezone": "Asia/Kolkata",
        "open_local": "09:15:00",
        "close_local": "15:30:00",
    }
    assert packet["market_session"]["open_local"] == "09:15"
    assert packet["live_fetch_contract"]["available"] is True
    assert packet["adapter_execution_contract"]["provider"] == "arrow_money"
    assert packet["adapter_execution_contract"]["adapter"] == "arrow_money"
    assert packet["adapter_execution_contract"]["transport"] == "websocket"
    assert packet["adapter_execution_contract"]["exchange"] == "NFO"
    assert packet["adapter_execution_contract"]["live_session_ready"] is True
    assert packet["adapter_execution_contract"]["capture_window_count"] == 2
    assert packet["adapter_execution_contract"]["capture_command_count"] == 2
    assert packet["adapter_execution_contract"]["credential_env_vars"] == [
        "ARROW_MONEY_API_KEY",
        "ARROW_MONEY_API_SECRET",
    ]
    assert packet["adapter_execution_contract"]["values_stored"] is False
    assert packet["capture_windows"][0]["label"] == "open"
    assert packet["capture_windows"][0]["capture_command_provider"] == "arrow_money"
    assert packet["capture_windows"][0]["capture_command_transport"] == "websocket"
    assert "--output" in packet["capture_windows"][0]["capture_command_template"]
    assert config["ready"]
    assert config["exchange"] == "NFO"
    assert config["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["credential_env_template"]["sha256"] == packet["authentication"]["env_template"]["sha256"]
    assert config["adapter_execution_contract"]["post_capture_batch_command"] == packet["post_capture_batch_command"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["live_fetch_contract"]["available"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_capture_commands"][0]["transport"] == "websocket"
    assert config["provider_capture_commands"][0]["required_env_vars"] == "ARROW_MONEY_API_KEY;ARROW_MONEY_API_SECRET"
    assert config["provider_capture_commands"][0]["command_base"] == "provider-adapter capture"
    assert config["primary_action"]["action"] == "run_provider_live_capture_windows"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert manifest["run_type"] == "provider_market_data_live_session_plan"
    assert manifest["inputs"]["credential_env_template"]["sha256"] == config["credential_env_template"]["sha256"]
    assert manifest["extra"]["credential_env_template"]["exists"] is True
    assert manifest["extra"]["adapter_execution_contract"]["live_session_ready"] is True
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"


def test_provider_market_data_live_session_plan_blocks_missing_runtime_env_when_required(tmp_path, monkeypatch):
    client_packet = _write_client_packet(tmp_path)
    monkeypatch.delenv("ARROW_MONEY_API_KEY", raising=False)
    monkeypatch.delenv("ARROW_MONEY_API_SECRET", raising=False)

    report = write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_session",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:30",),
            require_env_present=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "credential_env_vars_present_in_runtime" in failed
    assert report.action_queue.loc[0, "next_gate"] == "provider_credentials_runtime"


def test_provider_market_data_live_session_blocks_missing_env_template_proof(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    payload = json.loads(client_packet.read_text(encoding="utf-8"))
    payload["authentication"]["env_template"] = {"path": "", "exists": False, "sha256": ""}
    client_packet.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_session",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:30",),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "credential_env_template_carried" in failed
    assert report.config["credential_env_template"]["exists"] is False
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-client"
    assert report.action_queue.loc[0, "action"] == "regenerate_provider_client_with_credential_env_template"


def test_provider_market_data_live_session_blocks_missing_live_contract(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    payload = json.loads(client_packet.read_text(encoding="utf-8"))
    payload["live_fetch_contract"] = {"available": False, "next_gate": ""}
    client_packet.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_session",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:30",),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "source_live_fetch_contract_carried" in failed
    assert report.config["live_fetch_contract"]["available"] is False
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-client"
    assert report.action_queue.loc[0, "action"] == "regenerate_provider_client_with_source_live_fetch_contract"


def test_provider_market_data_live_session_blocks_missing_source_session_contract(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    payload = json.loads(client_packet.read_text(encoding="utf-8"))
    payload.pop("exchange", None)
    payload["session"] = {"timezone": "", "open_local": "", "close_local": ""}
    client_packet.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_session",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:30",),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {"source_exchange_carried", "source_session_contract_carried"} <= failed
    assert report.action_queue.loc[0, "next_gate"] == "prepare-provider-market-data-client"
    assert report.action_queue.loc[0, "action"] == "regenerate_provider_client_with_market_session_contract"


def test_provider_market_data_live_session_blocks_source_session_mismatch(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    payload = json.loads(client_packet.read_text(encoding="utf-8"))
    payload["session"]["open_local"] = "09:30:00"
    payload["live_fetch_contract"]["session"]["open_local"] = "09:30:00"
    client_packet.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_session",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:30",),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "source_session_matches_market_profile" in failed
    assert report.config["source_session"]["open_local"] == "09:30:00"
    assert report.action_queue.loc[0, "action"] == "regenerate_provider_client_with_market_session_contract"


def test_provider_market_data_live_session_plan_blocks_out_of_session_window(tmp_path):
    client_packet = _write_client_packet(tmp_path)

    report = write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_session",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("preopen=09:00-09:10",),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "windows_within_session" in failed
    assert not bool(report.windows.loc[0, "within_market_session"])


def test_cli_provider_market_data_live_session_accepts_rest_packet(tmp_path):
    client_packet = _write_client_packet(tmp_path, transport="rest")
    out_dir = tmp_path / "cli_live_session"

    code = main(
        [
            "plan-provider-market-data-live-session",
            "--client-packet",
            str(client_packet),
            "--out",
            str(out_dir),
            "--trade-date",
            "2026-06-23",
            "--window",
            "open=09:15-09:45",
            "--capture-dir",
            str(tmp_path / "captures"),
            "--batch-output-dir",
            str(tmp_path / "batch"),
            "--min-capture-rows",
            "2",
            "--pipeline-min-rows",
            "2",
            "--tick-size",
            "0.05",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_session_summary.csv")
    packet = json.loads((out_dir / "provider_market_data_live_session_packet.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "transport"] == "rest"
    assert packet["template_kind"] == "rest_backfill_request"
    assert packet["capture_windows"][0]["capture_command_transport"] == "rest"
    assert packet["capture_windows"][0]["capture_command_endpoint"].startswith("https://")
