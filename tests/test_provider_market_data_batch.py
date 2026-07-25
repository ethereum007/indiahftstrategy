import json

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_batch import (
    ProviderMarketDataBatchConfig,
    write_provider_market_data_batch_pipeline,
)
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan


def _write_client_packet(tmp_path, *, kind="ticks"):
    source_report = write_market_data_source_plan(
        tmp_path / f"source_{kind}",
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind=kind,
            transport="websocket",
            source_uri=f"wss://feed.arrow.money/market-data/nse/{kind}",
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )
    fetch_report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / f"fetch_{kind}",
        config=MarketDataFetchConfig(symbols=("NIFTY-I",)),
    )
    fetcher_report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / f"fetcher_{kind}",
    )
    client_report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / f"client_{kind}",
    )
    return client_report.output_dir / "provider_market_data_client_packet.json"


def _write_capture(path, day: str, *, base: float = 100.0):
    path.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        f"{day} 09:15:00,{base:.2f},{base + 0.05:.2f},75,150,{base + 0.05:.2f},75\n"
        f"{day} 09:15:01,{base + 0.05:.2f},{base + 0.10:.2f},100,125,{base + 0.05:.2f},50\n",
        encoding="utf-8",
    )
    return path


def _write_chain_capture(path, day: str):
    path.write_text(
        "ts,expiry,strike,call_bid,call_ask,call_bid_qty,call_ask_qty,"
        "put_bid,put_ask,put_bid_qty,put_ask_qty\n"
        f"{day} 09:15:00,2026-06-25,22500,100,100.5,75,150,90,90.5,75,150\n"
        f"{day} 09:15:01,2026-06-25,22525,99,99.5,75,150,91,91.5,75,150\n",
        encoding="utf-8",
    )
    return path


def test_provider_market_data_batch_compares_clean_capture_sessions(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    day1 = _write_capture(tmp_path / "arrow_capture_day1.csv", "2026-06-10", base=100.0)
    day2 = _write_capture(tmp_path / "arrow_capture_day2.csv", "2026-06-11", base=101.0)
    out_dir = tmp_path / "provider_batch"

    report = write_provider_market_data_batch_pipeline(
        client_packet,
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        config=ProviderMarketDataBatchConfig(
            min_capture_rows=2,
            pipeline_min_rows=2,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_batch_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "provider_market_data_batch_action_queue.csv")
    assert report.ready
    assert summary["dataset_count"] == 2
    assert summary["ready_datasets"] == 2
    assert summary["unique_source_files"] == 2
    assert summary["source_file_fingerprint_coverage"] == 1.0
    assert summary["comparison_accepted"]
    assert summary["blocked_action_count"] == 0
    assert report.action_queue.empty
    assert action_queue.empty
    assert config["ready"]
    assert config["comparison"]["accepted"]
    assert config["comparison"]["thresholds"]["min_datasets"] == 2
    assert len(config["datasets"]) == 2
    assert "dataset_manifests" in manifest["inputs"]
    assert len(manifest["inputs"]["dataset_manifests"]) == 2
    assert "comparison_manifest" in manifest["inputs"]
    assert (out_dir / "captures" / "day1" / "provider_market_data_pipeline_summary.csv").exists()
    assert (out_dir / "comparison" / "data_readiness_comparison_summary.csv").exists()
    assert manifest["run_type"] == "provider_market_data_batch_pipeline"

    ready_code = main(
        [
            "pipeline-provider-market-data-batch",
            "--client-packet",
            str(client_packet),
            "--capture",
            str(day1),
            str(day2),
            "--label",
            "cli_day1",
            "--label",
            "cli_day2",
            "--out",
            str(tmp_path / "provider_batch_cli"),
            "--min-capture-rows",
            "2",
            "--pipeline-min-rows",
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
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert ready_code == 0
    cli_config = json.loads(
        (
            tmp_path
            / "provider_batch_cli"
            / "provider_market_data_batch_config.json"
        ).read_text(encoding="utf-8")
    )
    assert cli_config["parameters"]["max_null_rows"] == 2
    assert cli_config["parameters"]["max_nonfinite_rows"] == 3
    assert cli_config["parameters"]["max_nonintegral_rows"] == 4
    assert cli_config["parameters"]["max_duplicate_tick_rows"] == 5
    assert cli_config["parameters"]["max_integer_overflow_rows"] == 6
    assert cli_config["parameters"]["max_nonmonotonic_rows"] == 7
    assert cli_config["parameters"]["max_nonpositive_strike_rows"] == 8
    assert cli_config["parameters"]["max_off_tick_price_rows"] == 0
    assert cli_config["parameters"]["max_quote_spread_ticks"] == 2.0
    assert cli_config["parameters"]["max_wide_spread_rows"] == 0
    assert cli_config["parameters"]["max_unchanged_bbo_ns"] == 5_000_000_000
    assert cli_config["parameters"]["max_stale_bbo_rows"] == 0
    assert all(bool(row["ready"]) for row in cli_config["datasets"])


def test_cli_provider_market_data_batch_carries_chain_strike_grid(tmp_path):
    client_packet = _write_client_packet(tmp_path, kind="chain")
    day1 = _write_chain_capture(
        tmp_path / "chain_capture_day1.csv",
        "2026-06-10",
    )
    day2 = _write_chain_capture(
        tmp_path / "chain_capture_day2.csv",
        "2026-06-11",
    )
    out_dir = tmp_path / "chain_batch"

    code = main(
        [
            "pipeline-provider-market-data-batch",
            "--client-packet",
            str(client_packet),
            "--capture",
            str(day1),
            str(day2),
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
        (out_dir / "provider_market_data_batch_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert code == 0
    assert config["parameters"]["strike_step"] == 50.0
    assert config["parameters"]["max_off_grid_strike_rows"] == 1
    assert all(bool(row["ready"]) for row in config["datasets"])


def test_provider_market_data_batch_blocks_reused_capture_file(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    day1 = _write_capture(tmp_path / "arrow_capture_day1.csv", "2026-06-10", base=100.0)
    out_dir = tmp_path / "provider_batch"

    report = write_provider_market_data_batch_pipeline(
        client_packet,
        [day1, day1],
        output_dir=out_dir,
        labels=["day1", "day1_copy"],
        config=ProviderMarketDataBatchConfig(
            min_capture_rows=2,
            pipeline_min_rows=2,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )

    summary = report.summary.iloc[0]
    action_queue = pd.read_csv(out_dir / "provider_market_data_batch_action_queue.csv")
    config = json.loads((out_dir / "provider_market_data_batch_config.json").read_text(encoding="utf-8"))
    checks = pd.read_csv(out_dir / "comparison" / "data_readiness_comparison_checks.csv")
    assert not report.ready
    assert summary["ready_datasets"] == 2
    assert summary["unique_source_files"] == 1
    assert not summary["comparison_accepted"]
    assert summary["next_gate"] == "pipeline-provider-market-data-batch"
    assert "unique_source_files" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "unique_source_files" in set(action_queue["check"])
    assert set(action_queue["next_gate"]) == {"pipeline-provider-market-data-batch"}
    assert config["blocked_actions"][0]["check"] == "unique_source_files"
    assert config["blocked_actions"][0]["source"] == "comparison"


def test_provider_market_data_batch_blocks_bad_capture_without_ingesting_it(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    good = _write_capture(tmp_path / "arrow_capture_good.csv", "2026-06-10", base=100.0)
    bad = tmp_path / "arrow_capture_bad.csv"
    bad.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last\n"
        "2026-06-11 09:15:00,101.0,101.05,75,150,101.05\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "provider_batch"

    report = write_provider_market_data_batch_pipeline(
        client_packet,
        [good, bad],
        output_dir=out_dir,
        labels=["good", "bad"],
        config=ProviderMarketDataBatchConfig(
            min_capture_rows=1,
            pipeline_min_rows=1,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )

    datasets = report.datasets.set_index("dataset")
    action_queue = pd.read_csv(out_dir / "provider_market_data_batch_action_queue.csv")
    assert not report.ready
    assert bool(datasets.loc["good", "ready"])
    assert not bool(datasets.loc["bad", "ready"])
    assert not bool(datasets.loc["bad", "capture_ready"])
    assert "dataset_pipeline" in set(action_queue["source"])
    assert "comparison" in set(action_queue["source"])
    assert not (out_dir / "captures" / "bad" / "02_vendor_market_data_pipeline" / "vendor_market_data_pipeline_summary.csv").exists()
