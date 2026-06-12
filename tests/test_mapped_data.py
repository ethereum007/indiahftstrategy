import json

import pandas as pd

from adapters.mapped_data import MappedDataConfig, normalize_mapped_data
from hft_cli import main


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def tick_mapping():
    return pd.DataFrame(
        [
            {"normalized_column": "ts", "source_column": "exchange_ts"},
            {"normalized_column": "bid", "source_column": "best_bid", "transform": "float"},
            {"normalized_column": "ask", "source_column": "best_ask", "transform": "float"},
            {"normalized_column": "bid_qty", "source_column": "bid_size", "transform": "int"},
            {"normalized_column": "ask_qty", "source_column": "ask_size", "transform": "int"},
            {"normalized_column": "last", "source_column": "last_px", "transform": "float"},
            {"normalized_column": "last_qty", "source_column": "last_size", "transform": "int"},
        ]
    )


def test_normalize_mapped_tick_data_uses_reviewed_vendor_mapping():
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": ns_ist("2026-06-10 09:15:00"),
                "best_bid": "100.00",
                "best_ask": "100.05",
                "bid_size": "75",
                "ask_size": "150",
                "last_px": "100.05",
                "last_size": "75",
            }
        ]
    )

    report = normalize_mapped_data(
        raw,
        tick_mapping(),
        config=MappedDataConfig(adapter="arrow_money", kind="ticks"),
    )

    assert report.ready
    assert report.data.loc[0, "bid"] == 100.0
    assert int(report.data.loc[0, "ask_qty"]) == 150
    assert "regime" in report.data.columns
    assert int(report.summary.loc[0, "mapped_columns"]) == 7


def test_normalize_mapped_data_fails_closed_for_missing_required_source():
    mapping = tick_mapping()
    mapping.loc[mapping["normalized_column"] == "ask_qty", "source_column"] = "missing_ask_size"
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": ns_ist("2026-06-10 09:15:00"),
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            }
        ]
    )

    report = normalize_mapped_data(
        raw,
        mapping,
        config=MappedDataConfig(adapter="irage", kind="ticks"),
    )

    assert not report.ready
    assert report.data.empty
    assert int(report.summary.loc[0, "failed_mappings"]) == 1
    failed = report.checks.loc[~report.checks["passed"].astype(bool)].iloc[0]
    assert failed["normalized_column"] == "ask_qty"


def test_cli_normalize_mapped_data_writes_normalized_fill_artifacts(tmp_path):
    vendor_fills = pd.DataFrame(
        [
            {
                "ClOrdID": "STG-1",
                "Symbol": "NIFTY24JUN22500CE",
                "FillTime": 100,
                "BuySell": "BUY",
                "FilledQty": 75,
                "FillPx": 10.5,
            },
            {
                "ClOrdID": "STG-2",
                "Symbol": "NIFTY24JUN22500PE",
                "FillTime": 200,
                "BuySell": "SELL",
                "FilledQty": 75,
                "FillPx": 11.0,
            },
        ]
    )
    mapping = pd.DataFrame(
        [
            {"normalized_column": "client_order_id", "source_column": "ClOrdID", "transform": "string"},
            {"normalized_column": "instrument_id", "source_column": "Symbol", "transform": "string"},
            {"normalized_column": "ts_fill_ns", "source_column": "FillTime"},
            {"normalized_column": "side", "source_column": "BuySell"},
            {"normalized_column": "qty", "source_column": "FilledQty", "transform": "int"},
            {"normalized_column": "price", "source_column": "FillPx", "transform": "float"},
        ]
    )
    raw_path = tmp_path / "vendor_fills.csv"
    mapping_path = tmp_path / "fills_mapping.csv"
    out_dir = tmp_path / "normalized_fills"
    vendor_fills.to_csv(raw_path, index=False)
    mapping.to_csv(mapping_path, index=False)

    code = main(
        [
            "normalize-mapped-data",
            "--input",
            str(raw_path),
            "--mapping",
            str(mapping_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "fills",
            "--output-file",
            "normalized_fills.csv",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "mapped_data_summary.csv")
    normalized = pd.read_csv(out_dir / "normalized_fills.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "output_rows"]) == 2
    assert normalized["side"].tolist() == [1, -1]
    assert manifest["run_type"] == "mapped_data_normalization"
