import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan
from reports.provider_market_data_pipeline import (
    ProviderMarketDataPipelineConfig,
    write_provider_market_data_pipeline,
)


def _write_client_packet(tmp_path, *, transport="websocket", kind="ticks"):
    source_uri = (
        f"https://api.arrow.money/market-data/nse/{kind}"
        if transport == "rest"
        else f"wss://feed.arrow.money/market-data/nse/{kind}"
    )
    source_report = write_market_data_source_plan(
        tmp_path / f"source_{transport}_{kind}",
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind=kind,
            transport=transport,
            source_uri=source_uri,
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )
    fetch_report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / f"fetch_{transport}_{kind}",
        config=MarketDataFetchConfig(
            symbols=("NIFTY-I",),
            window_start="2026-06-10 09:15:00" if transport == "rest" else "",
            window_end="2026-06-10 15:30:00" if transport == "rest" else "",
        ),
    )
    fetcher_report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / f"fetcher_{transport}_{kind}",
    )
    client_report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / f"client_{transport}_{kind}",
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


def _write_chain_capture(path):
    path.write_text(
        "ts,expiry,strike,call_bid,call_ask,call_bid_qty,call_ask_qty,"
        "put_bid,put_ask,put_bid_qty,put_ask_qty\n"
        "2026-06-10 09:15:00,2026-06-25,22500,100,100.5,75,150,90,90.5,75,150\n"
        "2026-06-10 09:15:01,2026-06-25,22525,99,99.5,75,150,91,91.5,75,150\n",
        encoding="utf-8",
    )
    return path


def test_provider_market_data_pipeline_runs_capture_review_and_vendor_pipeline(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    capture = _write_capture(tmp_path / "arrow_capture.csv")
    out_dir = tmp_path / "provider_root"

    report = write_provider_market_data_pipeline(
        client_packet,
        capture,
        output_dir=out_dir,
        config=ProviderMarketDataPipelineConfig(
            min_capture_rows=2,
            pipeline_min_rows=2,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )

    summary = report.summary.iloc[0]
    components = report.components.set_index("component")
    config = json.loads((out_dir / "provider_market_data_pipeline_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "provider_market_data_pipeline_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary["capture_ready"])
    assert bool(summary["vendor_pipeline_ready"])
    assert summary["next_gate"] == "review-data-readiness"
    assert components.loc["capture_review", "ready"]
    assert components.loc["vendor_market_data_pipeline", "ready"]
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "action"] == "feed_provider_market_data_to_research"
    assert config["parameters"]["timestamp_unit"] == "datetime"
    assert config["vendor_pipeline"]["ready"]
    assert manifest["run_type"] == "provider_market_data_pipeline"
    assert "vendor_pipeline_manifest" in manifest["inputs"]
    assert (out_dir / "01_capture_review" / "provider_market_data_capture_summary.csv").exists()
    assert (out_dir / "02_vendor_market_data_pipeline" / "vendor_market_data_pipeline_summary.csv").exists()
    assert (out_dir / "02_vendor_market_data_pipeline" / "04_data_readiness" / "data_readiness_summary.csv").exists()


def test_provider_market_data_pipeline_blocks_bad_capture_before_vendor_pipeline(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    capture = tmp_path / "bad_capture.csv"
    capture.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last\n"
        "2026-06-10 09:15:00,100.0,100.05,75,150,100.05\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_root"

    report = write_provider_market_data_pipeline(client_packet, capture, output_dir=out_dir)

    components = report.components.set_index("component")
    action_queue = pd.read_csv(out_dir / "provider_market_data_pipeline_action_queue.csv")
    config = json.loads((out_dir / "provider_market_data_pipeline_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert report.vendor_pipeline is None
    assert not components.loc["capture_review", "ready"]
    assert not components.loc["vendor_market_data_pipeline", "ready"]
    assert action_queue.loc[0, "component"] == "capture_review"
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert config["blocked_actions"][0]["component"] == "capture_review"
    assert not (out_dir / "02_vendor_market_data_pipeline" / "vendor_market_data_pipeline_summary.csv").exists()


def test_cli_provider_market_data_pipeline_accepts_rest_capture(tmp_path):
    client_packet = _write_client_packet(tmp_path, transport="rest")
    capture = _write_capture(tmp_path / "rest_capture.csv")
    out_dir = tmp_path / "cli_provider_root"

    code = main(
        [
            "pipeline-provider-market-data",
            "--client-packet",
            str(client_packet),
            "--capture",
            str(capture),
            "--out",
            str(out_dir),
            "--min-capture-rows",
            "2",
            "--pipeline-min-rows",
            "2",
            "--min-daily-observation-span-ns",
            "1000000000",
            "--min-daily-observations",
            "2",
            "--max-null-rows",
            "2",
            "--max-nonfinite-rows",
            "3",
            "--max-nonintegral-rows",
            "4",
            "--max-duplicate-tick-rows",
            "5",
            "--max-integer-overflow-rows",
            "6",
            "--max-nonmonotonic-rows",
            "7",
            "--max-nonpositive-strike-rows",
            "8",
            "--tick-size",
            "0.05",
            "--max-off-tick-price-rows",
            "0",
            "--max-quote-spread-ticks",
            "2",
            "--max-wide-spread-rows",
            "0",
            "--max-unchanged-bbo-ns",
            "5000000000",
            "--max-stale-bbo-rows",
            "0",
            "--max-median-spread-ticks",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_pipeline_summary.csv")
    vendor_summary = pd.read_csv(
        out_dir / "02_vendor_market_data_pipeline" / "vendor_market_data_pipeline_summary.csv"
    )
    config = json.loads(
        (out_dir / "provider_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "review-data-readiness"
    assert vendor_summary.loc[0, "adapter"] == "normalized"
    assert config["parameters"]["max_null_rows"] == 2
    assert config["parameters"]["max_nonfinite_rows"] == 3
    assert config["parameters"]["max_nonintegral_rows"] == 4
    assert config["parameters"]["max_duplicate_tick_rows"] == 5
    assert config["parameters"]["max_integer_overflow_rows"] == 6
    assert config["parameters"]["max_nonmonotonic_rows"] == 7
    assert config["parameters"]["max_nonpositive_strike_rows"] == 8
    assert config["parameters"]["max_off_tick_price_rows"] == 0
    assert config["parameters"]["max_quote_spread_ticks"] == 2.0
    assert config["parameters"]["max_wide_spread_rows"] == 0
    assert config["parameters"]["max_unchanged_bbo_ns"] == 5_000_000_000
    assert config["parameters"]["max_stale_bbo_rows"] == 0
    assert (
        config["parameters"]["min_daily_observation_span_ns"]
        == 1_000_000_000
    )
    assert config["parameters"]["min_daily_observations"] == 2
    assert int(summary.loc[0, "min_daily_observations"]) == 2
    assert bool(vendor_summary.loc[0, "quote_spread_validation_enabled"])
    assert int(vendor_summary.loc[0, "wide_spread_rows"]) == 0
    assert bool(vendor_summary.loc[0, "bbo_staleness_validation_enabled"])
    assert int(vendor_summary.loc[0, "stale_bbo_rows"]) == 0
    assert (
        int(vendor_summary.loc[0, "min_daily_observation_span_ns"])
        == 1_000_000_000
    )
    assert int(vendor_summary.loc[0, "min_daily_observations"]) == 2


def test_cli_provider_market_data_pipeline_carries_chain_strike_grid(tmp_path):
    client_packet = _write_client_packet(tmp_path, kind="chain")
    capture = _write_chain_capture(tmp_path / "chain_capture.csv")
    out_dir = tmp_path / "chain_provider_root"

    code = main(
        [
            "pipeline-provider-market-data",
            "--client-packet",
            str(client_packet),
            "--capture",
            str(capture),
            "--out",
            str(out_dir),
            "--expected-kind",
            "chain",
            "--min-capture-rows",
            "2",
            "--pipeline-min-rows",
            "2",
            "--strike-step",
            "50",
            "--max-off-grid-strike-rows",
            "1",
            "--fail-on-breach",
        ]
    )

    config = json.loads(
        (out_dir / "provider_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    vendor_summary = pd.read_csv(
        out_dir
        / "02_vendor_market_data_pipeline"
        / "vendor_market_data_pipeline_summary.csv"
    )
    assert code == 0
    assert config["parameters"]["strike_step"] == 50.0
    assert config["parameters"]["max_off_grid_strike_rows"] == 1
    assert bool(vendor_summary.loc[0, "strike_grid_validation_enabled"])
    assert int(vendor_summary.loc[0, "off_grid_strike_rows"]) == 1
