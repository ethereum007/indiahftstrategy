import json

import pandas as pd

from adapters.vendor_intake import VendorCsvIntakeConfig, profile_vendor_csv, write_vendor_csv_intake_report
from hft_cli import main


def test_vendor_intake_detects_tick_file_and_drafts_mapping():
    sample = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            }
        ]
    )

    report = profile_vendor_csv(
        sample,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="auto"),
    )

    summary = report.summary.iloc[0]
    mapping = report.mapping_draft.set_index("normalized_column")
    assert report.ready
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert summary["best_kind"] == "ticks"
    assert summary["mapping_coverage"] == 1.0
    assert int(summary["failed_check_count"]) == 0
    assert int(summary["blocked_action_count"]) == 0
    assert summary["next_gate"] == ""
    assert summary["failed_check_names"] == ""
    assert summary["primary_blocker_check"] == ""
    assert mapping.loc["ts", "source_column"] == "exchange_ts"
    assert mapping.loc["bid", "source_column"] == "best_bid"
    assert mapping.loc["ask_qty", "transform"] == "int"


def test_vendor_intake_fails_closed_for_incomplete_tick_sample():
    sample = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
            }
        ]
    )

    report = profile_vendor_csv(
        sample,
        config=VendorCsvIntakeConfig(adapter="irage", kind="ticks"),
    )

    summary = report.summary.iloc[0]
    action_queue = report.action_queue
    assert not report.ready
    assert action_queue is not None
    assert int(len(action_queue)) == 4
    assert summary["best_kind"] == "ticks"
    assert int(summary["unmapped_required_columns"]) == 4
    assert int(summary["failed_check_count"]) == 4
    assert int(summary["blocked_action_count"]) == 4
    assert summary["next_gate"] == "intake-vendor-csv"
    assert summary["next_gate_help_command"] == "python -m hft_cli intake-vendor-csv --help"
    assert summary["primary_action_status"] == "blocked"
    assert summary["failed_check_names"].split(";")[0] == "unmapped_required:bid_qty"
    assert summary["first_failed_reason"] == "bid_qty normalized column is not mapped to a source column"
    assert summary["primary_blocker_check"] == "unmapped_required:bid_qty"
    assert summary["primary_blocker_value"] == "bid_qty"
    assert summary["primary_blocker_operator"] == "mapped"
    assert summary["primary_blocker_threshold"] == "source_column"
    assert summary["primary_blocker_reason"] == "bid_qty normalized column is not mapped to a source column"
    assert "bid_qty" in summary["unmapped_normalized_columns"]
    assert action_queue.loc[0, "check"] == "unmapped_required:bid_qty"
    assert action_queue.loc[0, "next_gate"] == "intake-vendor-csv"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli intake-vendor-csv --help"


def test_write_vendor_intake_outputs_manifest_and_fill_mapping(tmp_path):
    sample = pd.DataFrame(
        [
            {
                "ClOrdID": "STG-1",
                "Symbol": "NIFTY24JUN22500CE",
                "FillTime": "2026-06-10 09:16:00",
                "BuySell": "BUY",
                "FilledQty": 75,
                "FillPx": 10.5,
            }
        ]
    )
    sample_path = tmp_path / "arrow_fills.csv"
    out_dir = tmp_path / "intake"
    sample.to_csv(sample_path, index=False)

    report = write_vendor_csv_intake_report(
        sample_path,
        output_dir=out_dir,
        config=VendorCsvIntakeConfig(adapter="arrow_money"),
    )

    summary = pd.read_csv(out_dir / "vendor_intake_summary.csv")
    action_queue = pd.read_csv(out_dir / "vendor_intake_action_queue.csv")
    mapping = pd.read_csv(out_dir / "vendor_mapping_draft.csv")
    source_profile = json.loads((out_dir / "vendor_intake_source_profile.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "vendor_intake_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "vendor_intake_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert report.ready
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert summary.loc[0, "best_kind"] == "fills"
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert set(mapping["normalized_column"]) == {"client_order_id", "instrument_id", "ts_fill_ns", "side", "qty", "price"}
    assert manifest["run_type"] == "vendor_csv_intake"
    assert source_profile["file_sha256"] == manifest["inputs"]["sample"]["sha256"]
    assert source_profile["header_columns"] == list(sample.columns)
    assert len(source_profile["header_sha256"]) == 64
    assert summary.loc[0, "source_header_sha256"] == source_profile["header_sha256"]
    assert summary.loc[0, "mapping_draft_sha256"] == source_profile["mapping_draft_sha256"]
    assert manifest["extra"]["source_profile"]["header_sha256"] == source_profile["header_sha256"]
    assert config["ready"]
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["mapping"]["draft_sha256"] == source_profile["mapping_draft_sha256"]
    assert "# Vendor CSV Intake Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "vendor_intake_action_queue.csv" in artifact_paths
    assert "vendor_intake_config.json" in artifact_paths
    assert "vendor_intake_runbook.md" in artifact_paths


def test_vendor_intake_fails_closed_when_auto_kind_is_ambiguous():
    sample = pd.DataFrame(
        [
            {
                "client_order_id": "STG-1",
                "instrument_id": "NIFTY24JUN22500CE",
                "ts_sent_ns": 1_780_000_000_000_000_000,
                "ts_fill_ns": 1_780_000_001_000_000_000,
                "side": "BUY",
                "qty": 75,
                "price": 10.5,
            }
        ]
    )

    report = profile_vendor_csv(
        sample,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="auto"),
    )

    summary = report.summary.iloc[0]
    action_queue = report.action_queue
    assert not report.ready
    assert action_queue is not None
    assert len(action_queue) == 1
    assert bool(summary["selected_kind_ambiguous"])
    assert summary["kind_selection"] == "ambiguous"
    assert set(summary["ambiguous_kinds"].split(";")) == {"orders", "fills"}
    ambiguous_kinds = summary["ambiguous_kinds"]
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "ambiguous_kind_selection"
    assert summary["first_failed_reason"] == f"auto kind selection is ambiguous: {ambiguous_kinds}"
    assert summary["primary_blocker_check"] == "ambiguous_kind_selection"
    assert summary["primary_blocker_value"] == ambiguous_kinds
    assert summary["primary_blocker_operator"] == "unique_kind"
    assert summary["primary_blocker_threshold"] == "required"
    assert summary["primary_blocker_reason"] == f"auto kind selection is ambiguous: {ambiguous_kinds}"
    assert summary["recommendation"] == "set_vendor_kind_explicitly_before_normalizing"
    assert summary["next_gate"] == "intake-vendor-csv"
    assert action_queue.loc[0, "check"] == "ambiguous_kind_selection"
    assert action_queue.loc[0, "reason"] == f"auto kind selection is ambiguous: {ambiguous_kinds}"


def test_vendor_intake_allows_explicit_kind_for_ambiguous_order_fill_file():
    sample = pd.DataFrame(
        [
            {
                "client_order_id": "STG-1",
                "instrument_id": "NIFTY24JUN22500CE",
                "ts_sent_ns": 1_780_000_000_000_000_000,
                "ts_fill_ns": 1_780_000_001_000_000_000,
                "side": "BUY",
                "qty": 75,
                "price": 10.5,
            }
        ]
    )

    report = profile_vendor_csv(
        sample,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="orders"),
    )

    summary = report.summary.iloc[0]
    mapping = report.mapping_draft.set_index("normalized_column")
    assert report.ready
    assert summary["best_kind"] == "orders"
    assert summary["kind_selection"] == "explicit"
    assert not bool(summary["selected_kind_ambiguous"])
    assert mapping.loc["ts_sent_ns", "source_column"] == "ts_sent_ns"


def test_cli_vendor_intake_can_fail_on_incomplete_mapping(tmp_path):
    sample = pd.DataFrame([{"exchange_ts": "2026-06-10 09:15:00", "best_bid": 100.0}])
    sample_path = tmp_path / "partial_ticks.csv"
    out_dir = tmp_path / "intake"
    sample.to_csv(sample_path, index=False)

    code = main(
        [
            "intake-vendor-csv",
            "--sample",
            str(sample_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "vendor_intake_summary.csv")
    action_queue = pd.read_csv(out_dir / "vendor_intake_action_queue.csv")
    config = json.loads((out_dir / "vendor_intake_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "unmapped_required_columns"]) == 5
    assert int(summary.loc[0, "failed_check_count"]) == 5
    assert int(summary.loc[0, "blocked_action_count"]) == 5
    assert summary.loc[0, "next_gate"] == "intake-vendor-csv"
    assert summary.loc[0, "failed_check_names"].split(";")[0] == "unmapped_required:ask"
    assert summary.loc[0, "primary_blocker_check"] == "unmapped_required:ask"
    assert summary.loc[0, "primary_blocker_reason"] == "ask normalized column is not mapped to a source column"
    assert len(action_queue) == 5
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "check"] == "unmapped_required:ask"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli intake-vendor-csv --help"
    assert config["blocked_action_count"] == 5
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "unmapped_required:ask"
    assert config["blocked_actions"][0]["next_gate"] == "intake-vendor-csv"
