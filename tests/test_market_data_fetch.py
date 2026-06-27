import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan


def _write_source_plan(tmp_path, *, transport="websocket", market="india_nse_index_derivatives"):
    out_dir = tmp_path / f"source_{transport}"
    if transport == "file":
        source = tmp_path / "arrow_ticks.csv"
        source.write_text(
            "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
            "2026-06-10 09:15:00,100.0,100.05,75,150,100.05,75\n",
            encoding="utf-8",
        )
        return write_market_data_source_plan(
            out_dir,
            config=MarketDataSourceConfig(
                provider="arrow_money",
                adapter="arrow_money",
                kind="ticks",
                transport="file",
                source_uri=str(source),
                market=market,
            ),
        )
    source_uri = (
        "https://api.arrow.money/market-data/nse/ticks"
        if transport == "rest"
        else "wss://feed.arrow.money/market-data/nse"
    )
    return write_market_data_source_plan(
        out_dir,
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind="ticks",
            transport=transport,
            source_uri=source_uri,
            market=market,
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )


def test_market_data_fetch_plan_accepts_arrow_websocket_source(tmp_path):
    source_report = _write_source_plan(tmp_path)
    out_dir = tmp_path / "fetch_plan"

    report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        out_dir,
        config=MarketDataFetchConfig(
            symbols=("NIFTY-I", "BANKNIFTY-I"),
            max_latency_ms=150,
            expected_market="india_nse_index_derivatives",
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "market_data_fetch_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "market_data_fetch_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["mode"] == "provider_websocket_capture"
    assert summary["next_gate"] == "provider_fetcher"
    assert summary["credential_env_var_count"] == 2
    assert summary["credential_env_template_file"] == "market_data_source_env_template.env"
    assert bool(summary["credential_env_template_exists"])
    assert len(summary["credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert config["fetch"]["symbols"] == ["NIFTY-I", "BANKNIFTY-I"]
    assert config["credentials"]["values_stored"] is False
    assert config["credentials"]["env_template"]["exists"] is True
    assert len(config["credentials"]["env_template"]["sha256"]) == 64
    assert config["source_plan"]["credential_env_template"]["sha256"] == config["credentials"]["env_template"]["sha256"]
    assert config["source_plan"]["live_fetch_contract"]["available"] is True
    assert "plan-market-data-fetch" in config["source_plan"]["live_fetch_contract"]["command_template"]
    assert config["primary_action"]["action"] == "execute_provider_websocket_capture"
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "provider_fetcher"
    assert manifest["run_type"] == "market_data_fetch_plan"
    assert manifest["inputs"]["source_plan"]["sha256"]
    assert manifest["inputs"]["credential_env_template"]["sha256"] == config["credentials"]["env_template"]["sha256"]
    assert manifest["extra"]["credential_env_template"]["exists"] is True


def test_market_data_fetch_plan_blocks_live_source_without_symbols(tmp_path):
    source_report = _write_source_plan(tmp_path)
    out_dir = tmp_path / "fetch_plan"

    report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        out_dir,
        config=MarketDataFetchConfig(symbols=()),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads((out_dir / "market_data_fetch_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert "live_symbols_present" in failed
    assert config["blocked_actions"][0]["next_gate"] == "plan-market-data-fetch"


def test_market_data_fetch_plan_blocks_missing_live_source_env_template(tmp_path):
    source_report = _write_source_plan(tmp_path)
    (source_report.output_dir / "market_data_source_env_template.env").unlink()
    out_dir = tmp_path / "fetch_plan"

    report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        out_dir,
        config=MarketDataFetchConfig(symbols=("NIFTY-I",)),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads((out_dir / "market_data_fetch_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert "credential_env_template_available" in failed
    assert config["credentials"]["env_template"]["exists"] is False
    assert config["blocked_actions"][0]["next_gate"] == "plan-market-data-source"
    assert config["blocked_actions"][0]["action"] == "regenerate_source_plan_with_credential_env_template"


def test_market_data_fetch_plan_blocks_market_mismatch(tmp_path):
    source_report = _write_source_plan(tmp_path, market="india_nse_index_derivatives")

    report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / "fetch_plan",
        config=MarketDataFetchConfig(
            symbols=("NIFTY-I",),
            expected_market="us_equities",
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "market_matches_expected" in failed


def test_market_data_fetch_plan_routes_file_source_to_vendor_pipeline(tmp_path):
    source_report = _write_source_plan(tmp_path, transport="file")
    out_dir = tmp_path / "fetch_plan"

    report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        out_dir,
        config=MarketDataFetchConfig(),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "market_data_fetch_config.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["mode"] == "file_pipeline_replay"
    assert summary["next_gate"] == "pipeline-vendor-market-data"
    assert not bool(summary["source_live_fetch_contract_available"])
    assert config["primary_action"]["action"] == "run_vendor_market_data_pipeline"
    assert config["source_plan"]["live_fetch_contract"]["available"] is False
    assert "pipeline-vendor-market-data" in config["next_gate_help_command"]


def test_cli_market_data_fetch_plan_accepts_rest_source(tmp_path):
    source_report = _write_source_plan(tmp_path, transport="rest")
    out_dir = tmp_path / "cli_fetch_plan"

    code = main(
        [
            "plan-market-data-fetch",
            "--source-plan",
            str(source_report.output_dir / "market_data_source_config.json"),
            "--out",
            str(out_dir),
            "--symbol",
            "NIFTY-I",
            "--window-start",
            "2026-06-10 09:15:00",
            "--window-end",
            "2026-06-10 15:30:00",
            "--poll-interval-ms",
            "500",
            "--max-latency-ms",
            "200",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "market_data_fetch_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "mode"] == "provider_rest_backfill"
    assert summary.loc[0, "next_gate"] == "provider_fetcher"
