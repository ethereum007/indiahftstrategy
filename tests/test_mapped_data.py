import json

import pandas as pd

from adapters.mapped_data import MappedDataConfig, normalize_mapped_data, write_mapped_data_normalization
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


def chain_mapping():
    return pd.DataFrame(
        [
            {"normalized_column": column, "source_column": column}
            for column in (
                "ts",
                "expiry",
                "strike",
                "call_bid",
                "call_ask",
                "call_bid_qty",
                "call_ask_qty",
                "put_bid",
                "put_ask",
                "put_bid_qty",
                "put_ask_qty",
            )
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
    assert int(report.summary.loc[0, "failed_check_count"]) == 0
    assert report.summary.loc[0, "failed_check_names"] == ""
    assert report.summary.loc[0, "primary_blocker_check"] == ""
    assert int(report.summary.loc[0, "action_queue_count"]) == 0
    assert report.summary.loc[0, "next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty


def test_normalize_mapped_tick_data_preserves_session_quarantine_provenance():
    rows = []
    for timestamp in (
        "2026-06-12 09:14:59",
        "2026-06-12 10:00:00",
        "2026-06-13 10:00:00",
    ):
        rows.append(
            {
                "exchange_ts": ns_ist(timestamp),
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            }
        )

    report = normalize_mapped_data(
        pd.DataFrame(rows),
        tick_mapping(),
        config=MappedDataConfig(adapter="arrow_money", kind="ticks"),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["input_rows"]) == 3
    assert int(summary["output_rows"]) == 1
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_non_trading_day_rows"]) == 1
    assert int(summary["dropped_out_of_session_rows"]) == 1


def test_normalize_mapped_tick_data_preserves_nonfinite_quarantine_provenance():
    valid = {
        "exchange_ts": ns_ist("2026-06-10 09:15:00"),
        "best_bid": 100.0,
        "best_ask": 100.05,
        "bid_size": 75,
        "ask_size": 150,
        "last_px": 100.05,
        "last_size": 75,
    }
    nonfinite_price = valid.copy()
    nonfinite_price["best_bid"] = float("inf")
    nonfinite_depth = valid.copy()
    nonfinite_depth["bid_size"] = float("inf")

    report = normalize_mapped_data(
        pd.DataFrame([valid, nonfinite_price, nonfinite_depth]),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 1
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_nonfinite_rows"]) == 2


def test_normalize_mapped_tick_data_preserves_nonintegral_quarantine_provenance():
    valid = {
        "exchange_ts": ns_ist("2026-06-10 09:15:00"),
        "best_bid": 100.0,
        "best_ask": 100.05,
        "bid_size": 75,
        "ask_size": 150,
        "last_px": 100.05,
        "last_size": 75,
    }
    fractional_depth = valid.copy()
    fractional_depth["bid_size"] = 75.5
    fractional_last_size = valid.copy()
    fractional_last_size["last_size"] = 75.5

    report = normalize_mapped_data(
        pd.DataFrame([valid, fractional_depth, fractional_last_size]),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 1
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_nonintegral_rows"]) == 2


def test_normalize_mapped_tick_data_preserves_duplicate_quarantine_provenance():
    packet = {
        "exchange_ts": ns_ist("2026-06-10 09:15:00"),
        "best_bid": 100.0,
        "best_ask": 100.05,
        "bid_size": 75,
        "ask_size": 150,
        "last_px": 100.05,
        "last_size": 75,
    }
    changed_state = packet.copy()
    changed_state["ask_size"] = 225

    report = normalize_mapped_data(
        pd.DataFrame([packet, packet.copy(), changed_state]),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 2
    assert int(summary["quarantined_rows"]) == 1
    assert int(summary["dropped_duplicate_rows"]) == 1


def test_normalize_mapped_tick_data_preserves_high_water_quarantine_provenance():
    rows = []
    for offset, timestamp in enumerate([100, 50, 75, 100, 125]):
        rows.append(
            {
                "exchange_ts": timestamp,
                "best_bid": 100.0 + offset * 0.05,
                "best_ask": 100.05 + offset * 0.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05 + offset * 0.05,
                "last_size": 75,
            }
        )

    report = normalize_mapped_data(
        pd.DataFrame(rows),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 3
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_nonmonotonic_rows"]) == 2
    assert list(report.data["ts"]) == [100, 100, 125]


def test_normalize_mapped_chain_data_preserves_high_water_quarantine_provenance():
    base = {
        "expiry": "2026-06-25",
        "call_bid": 100.0,
        "call_ask": 100.5,
        "call_bid_qty": 75,
        "call_ask_qty": 150,
        "put_bid": 90.0,
        "put_ask": 90.5,
        "put_bid_qty": 75,
        "put_ask_qty": 150,
    }
    rows = [
        {
            **base,
            "ts": timestamp,
            "strike": 22500.0 + offset * 50.0,
        }
        for offset, timestamp in enumerate([100, 50, 75, 100, 125])
    ]

    report = normalize_mapped_data(
        pd.DataFrame(rows),
        chain_mapping(),
        config=MappedDataConfig(
            adapter="irage",
            kind="chain",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 3
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_nonmonotonic_rows"]) == 2
    assert list(report.data["ts"]) == [100, 100, 125]


def test_normalize_mapped_chain_data_preserves_nonpositive_strike_provenance():
    base = {
        "expiry": "2026-06-25",
        "call_bid": 100.0,
        "call_ask": 100.5,
        "call_bid_qty": 75,
        "call_ask_qty": 150,
        "put_bid": 90.0,
        "put_ask": 90.5,
        "put_bid_qty": 75,
        "put_ask_qty": 150,
    }
    rows = [
        {**base, "ts": timestamp, "strike": strike}
        for timestamp, strike in enumerate((22500.0, 0.0, -50.0), start=1)
    ]

    report = normalize_mapped_data(
        pd.DataFrame(rows),
        chain_mapping(),
        config=MappedDataConfig(
            adapter="irage",
            kind="chain",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert list(report.data["strike"]) == [22500.0]
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_nonpositive_strike_rows"]) == 2


def test_normalize_mapped_tick_data_preserves_nonpositive_depth_provenance():
    valid = {
        "exchange_ts": 1,
        "best_bid": 100.0,
        "best_ask": 100.05,
        "bid_size": 75,
        "ask_size": 150,
        "last_px": 100.05,
        "last_size": 75,
    }
    zero_bid_depth = {**valid, "exchange_ts": 2, "bid_size": 0}
    negative_ask_depth = {**valid, "exchange_ts": 3, "ask_size": -1}

    report = normalize_mapped_data(
        pd.DataFrame([valid, zero_bid_depth, negative_ask_depth]),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 1
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_negative_depth_rows"]) == 2


def test_normalize_mapped_tick_data_preserves_invalid_trade_provenance():
    valid = {
        "exchange_ts": 1,
        "best_bid": 100.0,
        "best_ask": 100.05,
        "bid_size": 75,
        "ask_size": 150,
        "last_px": 100.05,
        "last_size": 75,
    }
    zero_last = {**valid, "exchange_ts": 2, "last_px": 0}
    negative_last_size = {**valid, "exchange_ts": 3, "last_size": -1}

    report = normalize_mapped_data(
        pd.DataFrame([valid, zero_last, negative_last_size]),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 1
    assert int(summary["quarantined_rows"]) == 2
    assert int(summary["dropped_invalid_trade_rows"]) == 2


def test_normalize_mapped_tick_data_preserves_integer_overflow_provenance():
    valid = {
        "exchange_ts": ns_ist("2026-06-10 09:15:00"),
        "best_bid": 100.0,
        "best_ask": 100.05,
        "bid_size": 75,
        "ask_size": 150,
        "last_px": 100.05,
        "last_size": 75,
    }
    overflow_depth = valid.copy()
    overflow_depth["bid_size"] = 10**30

    report = normalize_mapped_data(
        pd.DataFrame([valid, overflow_depth]),
        tick_mapping(),
        config=MappedDataConfig(
            adapter="arrow_money",
            kind="ticks",
            filter_session=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["output_rows"]) == 1
    assert int(summary["quarantined_rows"]) == 1
    assert int(summary["dropped_integer_overflow_rows"]) == 1


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
    summary = report.summary.iloc[0]
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "unmapped_required:ask_qty"
    assert summary["first_failed_reason"] == "required normalized column has no available source column or default value"
    assert summary["primary_blocker_check"] == "unmapped_required:ask_qty"
    assert summary["primary_blocker_value"] == "missing_ask_size"
    assert summary["primary_blocker_operator"] == "int"
    assert summary["primary_blocker_threshold"] == "required"
    assert summary["primary_blocker_reason"] == "required normalized column has no available source column or default value"
    assert int(summary["action_queue_count"]) == 1
    assert int(summary["blocked_action_count"]) == 1
    assert summary["next_gate"] == "normalize-mapped-data"
    assert summary["next_gate_help_command"] == "python -m hft_cli normalize-mapped-data --help"
    assert summary["primary_action_status"] == "blocked"
    failed = report.checks.loc[~report.checks["passed"].astype(bool)].iloc[0]
    assert failed["normalized_column"] == "ask_qty"
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "check"] == "unmapped_required:ask_qty"
    assert report.action_queue.loc[0, "component"] == "mapping"
    assert report.action_queue.loc[0, "actual"] == "source_missing_default_missing"


def test_normalize_mapped_data_blocks_empty_normalized_output():
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": ns_ist("2026-06-10 08:30:00"),
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
        tick_mapping(),
        config=MappedDataConfig(adapter="arrow_money", kind="ticks"),
    )

    summary = report.summary.iloc[0]
    assert not report.ready
    assert report.data.empty
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "normalized_output_empty"
    assert summary["primary_blocker_check"] == "normalized_output_empty"
    assert int(summary["action_queue_count"]) == 1
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "component"] == "normalization"
    assert report.action_queue.loc[0, "check"] == "normalized_output_empty"


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
    action_queue = pd.read_csv(out_dir / "mapped_data_action_queue.csv")
    config = json.loads((out_dir / "mapped_data_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "mapped_data_runbook.md").read_text(encoding="utf-8")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "output_rows"]) == 2
    assert int(summary.loc[0, "action_queue_count"]) == 0
    assert normalized["side"].tolist() == [1, -1]
    assert action_queue.empty
    assert config["ready"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Mapped Vendor Data Normalization Runbook" in runbook
    assert manifest["run_type"] == "mapped_data_normalization"
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "mapped_data_action_queue.csv" in artifact_paths
    assert "mapped_data_config.json" in artifact_paths
    assert "mapped_data_runbook.md" in artifact_paths


def test_cli_normalize_mapped_data_writes_scheduler_handoff_for_mapping_blocker(tmp_path):
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
    mapping = tick_mapping()
    mapping.loc[mapping["normalized_column"] == "ask_qty", "source_column"] = "missing_ask_size"
    raw_path = tmp_path / "vendor_ticks.csv"
    mapping_path = tmp_path / "tick_mapping.csv"
    out_dir = tmp_path / "blocked_normalization"
    raw.to_csv(raw_path, index=False)
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
            "irage",
            "--kind",
            "ticks",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "mapped_data_summary.csv")
    action_queue = pd.read_csv(out_dir / "mapped_data_action_queue.csv")
    config = json.loads((out_dir / "mapped_data_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "mapped_data_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "check"] == "unmapped_required:ask_qty"
    assert action_queue.loc[0, "next_gate"] == "normalize-mapped-data"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli normalize-mapped-data --help"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "unmapped_required:ask_qty"
    assert config["blocked_actions"][0]["normalized_column"] == "ask_qty"
    assert "unmapped_required:ask_qty" in runbook


def test_write_mapped_data_normalization_returns_action_queue(tmp_path):
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
    mapping = tick_mapping()
    mapping.loc[mapping["normalized_column"] == "last_qty", "source_column"] = "missing_last_size"
    raw_path = tmp_path / "vendor_ticks.csv"
    mapping_path = tmp_path / "tick_mapping.csv"
    out_dir = tmp_path / "mapped"
    raw.to_csv(raw_path, index=False)
    mapping.to_csv(mapping_path, index=False)

    report = write_mapped_data_normalization(
        raw_path,
        mapping_path,
        output_dir=out_dir,
        config=MappedDataConfig(adapter="arrow_money", kind="ticks"),
    )

    assert report.action_queue is not None
    assert report.action_queue.loc[0, "check"] == "unmapped_required:last_qty"
