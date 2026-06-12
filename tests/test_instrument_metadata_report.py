import pandas as pd

from hft_cli import main
from reports.instrument_metadata import (
    InstrumentMetadataConfig,
    build_instrument_metadata_report,
    write_instrument_metadata_report,
)


def instruments():
    return pd.DataFrame(
        [
            {"instrument_id": "NIFTY24JUN22500CE"},
            {"instrument_id": "SPY250620P00500000"},
            {"instrument_id": "NIFTY_20260610_100C"},
            {"instrument_id": "NIFTY24JUN22500CE"},
        ]
    )


def test_instrument_metadata_report_parses_unique_cross_market_symbols():
    report = build_instrument_metadata_report(instruments())

    metadata = report.metadata.set_index("instrument_id")
    assert report.passed
    assert report.summary.loc[0, "instruments"] == 3
    assert report.summary.loc[0, "parse_coverage"] == 1.0
    assert metadata.loc["NIFTY24JUN22500CE", "symbol_format"] == "nse_compact_option"
    assert metadata.loc["SPY250620P00500000", "underlying"] == "SPY"
    assert metadata.loc["NIFTY_20260610_100C", "expiry"] == "2026-06-10"


def test_instrument_metadata_report_flags_unparsed_symbols():
    frame = pd.concat([instruments(), pd.DataFrame([{"instrument_id": "MYSTERY"}])], ignore_index=True)

    report = build_instrument_metadata_report(
        frame,
        config=InstrumentMetadataConfig(min_parse_coverage=1.0),
    )

    assert not report.passed
    assert report.gaps["instrument_id"].tolist() == ["MYSTERY"]
    assert report.gaps.loc[0, "reason"] == "unsupported_option_symbol_format"
    assert report.summary.loc[0, "parse_coverage"] == 0.75


def test_write_instrument_metadata_report_outputs_files_and_manifest(tmp_path):
    input_path = tmp_path / "orders.csv"
    out_dir = tmp_path / "metadata"
    instruments().to_csv(input_path, index=False)

    report = write_instrument_metadata_report(input_path, output_dir=out_dir)

    assert report.output_dir == out_dir
    assert (out_dir / "instrument_metadata.csv").exists()
    assert (out_dir / "instrument_metadata_gaps.csv").exists()
    assert (out_dir / "instrument_metadata_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_instrument_metadata_report_fails_on_unparsed(tmp_path):
    input_path = tmp_path / "orders.csv"
    out_dir = tmp_path / "metadata"
    pd.DataFrame([{"instrument_id": "MYSTERY"}]).to_csv(input_path, index=False)

    code = main(
        [
            "instrument-metadata-report",
            "--input",
            str(input_path),
            "--out",
            str(out_dir),
            "--fail-on-unparsed",
        ]
    )

    summary = pd.read_csv(out_dir / "instrument_metadata_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
