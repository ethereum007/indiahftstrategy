import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_capture import (
    ProviderMarketDataCaptureConfig,
    write_provider_market_data_capture_review,
)
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan


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
            symbols=("NIFTY-I",),
            window_start="2026-06-10 09:15:00" if transport == "rest" else "",
            window_end="2026-06-10 15:30:00" if transport == "rest" else "",
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


def _write_capture(path):
    path.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        "2026-06-10 09:15:00,100.0,100.05,75,150,100.05,75\n"
        "2026-06-10 09:15:01,100.05,100.10,100,125,100.05,50\n",
        encoding="utf-8",
    )
    return path


def test_provider_market_data_capture_review_accepts_normalized_ticks(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    capture = _write_capture(tmp_path / "arrow_capture.csv")
    out_dir = tmp_path / "capture_review"

    report = write_provider_market_data_capture_review(
        client_packet,
        capture,
        out_dir,
        config=ProviderMarketDataCaptureConfig(
            min_rows=2,
            expected_market="india_nse_index_derivatives",
            expected_kind="ticks",
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_capture_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "provider_market_data_capture_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["next_gate"] == "pipeline-vendor-market-data"
    assert summary["rows"] == 2
    assert summary["missing_required_column_count"] == 0
    assert config["capture"]["required_columns"] == ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
    assert config["normalized_pipeline"]["available"]
    assert "--adapter normalized" in config["normalized_pipeline"]["command"]
    assert "pipeline-vendor-market-data" in config["normalized_pipeline"]["command"]
    assert action_queue.loc[0, "action"] == "run_provider_capture_market_data_pipeline"
    assert manifest["run_type"] == "provider_market_data_capture_review"
    assert manifest["inputs"]["capture"]["sha256"] == summary["capture_file_sha256"]


def test_provider_market_data_capture_review_blocks_missing_required_column(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    capture = tmp_path / "bad_capture.csv"
    capture.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last\n"
        "2026-06-10 09:15:00,100.0,100.05,75,150,100.05\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_capture_review(client_packet, capture, tmp_path / "capture_review")

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    config = json.loads((report.output_dir / "provider_market_data_capture_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert "required_columns_present" in failed
    assert config["capture"]["missing_required_columns"] == ["last_qty"]
    assert config["blocked_actions"][0]["next_gate"] == "review-provider-market-data-capture"


def test_provider_market_data_capture_review_blocks_nonmonotonic_timestamps(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    capture = tmp_path / "bad_ts_capture.csv"
    capture.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        "2026-06-10 09:15:01,100.0,100.05,75,150,100.05,75\n"
        "2026-06-10 09:15:00,100.05,100.10,100,125,100.05,50\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_capture_review(client_packet, capture, tmp_path / "capture_review")

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "timestamp_monotonic" in failed


def test_cli_provider_market_data_capture_review_accepts_rest_capture(tmp_path):
    client_packet = _write_client_packet(tmp_path, transport="rest")
    capture = _write_capture(tmp_path / "rest_capture.csv")
    out_dir = tmp_path / "cli_capture_review"

    code = main(
        [
            "review-provider-market-data-capture",
            "--client-packet",
            str(client_packet),
            "--capture",
            str(capture),
            "--out",
            str(out_dir),
            "--min-rows",
            "2",
            "--expected-market",
            "india_nse_index_derivatives",
            "--expected-kind",
            "ticks",
            "--pipeline-output-dir",
            str(tmp_path / "pipeline_out"),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_capture_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "pipeline_output_dir"] == str(tmp_path / "pipeline_out")
    assert summary.loc[0, "next_gate"] == "pipeline-vendor-market-data"
