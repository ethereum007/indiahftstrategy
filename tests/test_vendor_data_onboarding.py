import json

import pandas as pd

from hft_cli import main
from reports.vendor_data_onboarding import VendorMarketDataPipelineConfig, write_vendor_market_data_pipeline


def test_vendor_market_data_pipeline_onboards_tick_file(tmp_path):
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            },
            {
                "exchange_ts": "2026-06-10 09:15:01",
                "best_bid": 100.05,
                "best_ask": 100.10,
                "bid_size": 150,
                "ask_size": 75,
                "last_px": 100.10,
                "last_size": 75,
            },
        ]
    )
    raw_path = tmp_path / "arrow_ticks.csv"
    out_dir = tmp_path / "pipeline"
    raw.to_csv(raw_path, index=False)

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    components = report.components.set_index("component")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["normalized_rows"] == 2
    assert summary["mapping_coverage"] == 1.0
    assert components.loc["vendor_intake", "ready"]
    assert components.loc["data_readiness", "ready"]
    assert (out_dir / "01_vendor_intake" / "vendor_mapping_draft.csv").exists()
    assert (out_dir / "02_normalized" / "normalized_ticks.csv").exists()
    assert (out_dir / "03_diagnostics" / "diagnostic_summary.csv").exists()
    assert (out_dir / "04_data_readiness" / "data_readiness_summary.csv").exists()
    assert manifest["run_type"] == "vendor_market_data_pipeline"


def test_vendor_market_data_pipeline_onboards_option_chain_file(tmp_path):
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "expiry_date": "2026-06-25",
                "strike_price": 22500,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
        ]
    )
    raw_path = tmp_path / "arrow_chain.csv"
    out_dir = tmp_path / "pipeline"
    raw.to_csv(raw_path, index=False)

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    diagnostics = pd.read_csv(out_dir / "03_diagnostics" / "diagnostic_summary.csv")
    assert report.ready
    assert report.summary.loc[0, "kind"] == "chain"
    assert set(diagnostics["scope"]) == {"overall", "expiry"}
    assert bool(pd.read_csv(out_dir / "04_data_readiness" / "data_readiness_summary.csv").loc[0, "ready"])


def test_cli_vendor_market_data_pipeline_fails_closed_on_incomplete_mapping(tmp_path):
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "best_bid": 100.0,
            }
        ]
    )
    raw_path = tmp_path / "partial_ticks.csv"
    out_dir = tmp_path / "pipeline"
    raw.to_csv(raw_path, index=False)

    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "vendor_market_data_pipeline_summary.csv")
    components = pd.read_csv(out_dir / "vendor_market_data_pipeline_components.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "not_ready" in set(components["status"])
    assert (out_dir / "04_data_readiness" / "data_readiness_summary.csv").exists()
