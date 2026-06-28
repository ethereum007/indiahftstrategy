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


def _mutate_json(path, mutator):
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    mutator(payload)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


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
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["market_session_open_local"] == "09:15"
    assert bool(summary["source_session_matches_market_session"])
    assert summary["source_credential_env_template_exists"]
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert summary["source_live_fetch_contract_available"]
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert "provider-adapter capture" in commands.loc[0, "adapter_command"]
    assert "--exchange NFO" in commands.loc[0, "adapter_command"]
    assert "ingest-provider-market-data-live-session" in summary["post_capture_ingest_command"]
    assert bundle["authentication"]["values_stored"] is False
    assert bundle["authentication"]["env_template"] == "provider_market_data_live_capture_env_template.env"
    assert bundle["authentication"]["source_env_template"]["sha256"] == summary["source_credential_env_template_sha256"]
    assert bundle["source_credential_env_template"]["exists"] is True
    assert bundle["exchange"] == "NFO"
    assert bundle["source_session"]["timezone"] == "Asia/Kolkata"
    assert bundle["market_session"]["open_local"] == "09:15"
    assert bundle["preflight"]["exchange"] == "NFO"
    assert bundle["live_fetch_contract"]["available"] is True
    assert bundle["adapter_handoff"] == "provider_market_data_adapter_handoff.json"
    assert "ARROW_MONEY_API_KEY=\n" in env_template
    assert "ARROW_MONEY_API_SECRET=\n" in env_template
    assert handoff["provider"] == "arrow_money"
    assert handoff["transport"] == "websocket"
    assert handoff["exchange"] == "NFO"
    assert handoff["source_session"]["close_local"] == "15:30:00"
    assert handoff["market_session"]["timezone"] == "Asia/Kolkata"
    assert handoff["authentication"]["values_stored"] is False
    assert handoff["authentication"]["env_vars"] == ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"]
    assert handoff["authentication"]["source_env_template"]["sha256"] == summary["source_credential_env_template_sha256"]
    assert handoff["source_credential_env_template"]["exists"] is True
    assert handoff["live_fetch_contract"]["available"] is True
    assert handoff["output"]["schema_columns"] == ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
    assert len(handoff["capture_windows"]) == 2
    assert "provider-adapter capture" in handoff["capture_windows"][0]["adapter_command"]
    assert "ingest-provider-market-data-live-session" in handoff["post_capture_ingest_command"]
    assert handoff["handoff_invariants"]["credential_values_must_not_be_persisted"]
    assert report.adapter_handoff["provider"] == "arrow_money"
    assert bundle["primary_action"]["next_gate"] == "ingest-provider-market-data-live-session"
    assert bundle["commands"][0]["queue_status"] == "ready"
    assert "provider_market_data_adapter_handoff.json" in runbook
    assert "Source credential env template" in runbook
    assert manifest["run_type"] == "provider_market_data_live_capture_bundle"
    assert manifest["extra"]["adapter_handoff_file"] == "provider_market_data_adapter_handoff.json"
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["market_session"]["open_local"] == "09:15"
    assert manifest["inputs"]["source_credential_env_template"]["sha256"] == summary["source_credential_env_template_sha256"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
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


def test_provider_market_data_live_capture_bundle_blocks_missing_preflight_env_template(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    preflight = _write_preflight(tmp_path, live_packet)
    preflight_config = _mutate_json(
        preflight.output_dir / "provider_market_data_live_preflight_config.json",
        lambda payload: (
            payload.update({"credential_env_template": {"path": "", "exists": False, "sha256": ""}}),
            payload["session_packet"]["authentication"].pop("env_template", None),
        ),
    )

    report = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "capture_bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(preflight_config_path=str(preflight_config)),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "preflight_credential_env_template_carried" in failed
    assert not bool(report.summary.iloc[0]["source_credential_env_template_exists"])
    assert report.action_queue.loc[0, "action"] == "rerun_preflight_with_credential_env_template"
    assert report.action_queue.loc[0, "next_gate"] == "preflight-provider-market-data-live-session"


def test_provider_market_data_live_capture_bundle_blocks_missing_preflight_live_fetch_contract(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    preflight = _write_preflight(tmp_path, live_packet)
    preflight_config = _mutate_json(
        preflight.output_dir / "provider_market_data_live_preflight_config.json",
        lambda payload: (
            payload.update({"live_fetch_contract": {"available": False}}),
            payload["session_packet"].pop("live_fetch_contract", None),
        ),
    )

    report = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "capture_bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(preflight_config_path=str(preflight_config)),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "preflight_live_fetch_contract_carried" in failed
    assert not bool(report.summary.iloc[0]["source_live_fetch_contract_available"])
    assert report.action_queue.loc[0, "action"] == "rerun_preflight_with_live_fetch_contract"
    assert report.action_queue.loc[0, "next_gate"] == "preflight-provider-market-data-live-session"


def test_provider_market_data_live_capture_bundle_blocks_preflight_session_mismatch(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = _live_packet(plan)
    preflight = _write_preflight(tmp_path, live_packet)
    preflight_config = _mutate_json(
        preflight.output_dir / "provider_market_data_live_preflight_config.json",
        lambda payload: payload["source_session"].update({"open_local": "09:30:00"}),
    )

    report = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "capture_bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(preflight_config_path=str(preflight_config)),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "preflight_source_session_matches_session" in failed
    assert report.summary.iloc[0]["source_session_open_local"] == "09:15:00"
    assert report.action_queue.loc[0, "action"] == "rerun_preflight_with_market_session_contract"
    assert report.action_queue.loc[0, "next_gate"] == "preflight-provider-market-data-live-session"


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
