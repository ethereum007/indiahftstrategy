import json

import pandas as pd

from adapters.schema_audit import audit_adapter_schema
from hft_cli import main


TICK_COLUMNS = ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]


def test_adapter_schema_audit_accepts_normalized_ticks_with_extra_columns():
    audit = audit_adapter_schema(
        pd.DataFrame(columns=[*TICK_COLUMNS, "venue_code"]),
        adapter="normalized",
        kind="ticks",
    )

    summary = audit.summary.iloc[0]
    assert audit.passed
    assert summary["adapter_schema_status"] == "native_normalized"
    assert summary["required_columns"] == len(TICK_COLUMNS)
    assert summary["missing_required_columns"] == 0
    assert summary["failed_check_count"] == 0
    assert summary["failed_check_names"] == ""
    assert summary["primary_blocker_check"] == ""
    assert summary["extra_columns"] == 1
    assert summary["extra_source_columns"] == "venue_code"
    assert int(summary["action_queue_count"]) == 1
    assert int(summary["blocked_action_count"]) == 0
    assert int(summary["review_action_count"]) == 1
    assert set(audit.template["status"]) == {"mapped"}
    assert audit.action_queue is not None
    assert len(audit.action_queue) == 1
    assert audit.action_queue.loc[0, "queue_status"] == "review"
    assert audit.action_queue.loc[0, "check"] == "extra_column:venue_code"
    checklist = audit.checklist.set_index("check_name")
    assert bool(checklist.loc["required_columns_present", "passed"])
    assert bool(checklist.loc["vendor_schema_reviewed", "passed"])
    assert checklist.loc["extra_columns_classified", "status"] == "review"


def test_adapter_schema_audit_reports_missing_required_columns():
    audit = audit_adapter_schema(
        pd.DataFrame(columns=["ts", "bid", "ask", "bid_qty", "ask_qty"]),
        adapter="normalized",
        kind="tick",
    )

    summary = audit.summary.iloc[0]
    assert not audit.passed
    assert summary["missing_required_columns"] == 2
    assert summary["missing_source_columns"] == "last;last_qty"
    assert summary["failed_check_count"] == 2
    assert summary["failed_check_names"] == "missing_required:last;missing_required:last_qty"
    assert summary["first_failed_reason"] == "last source column is missing for last"
    assert summary["primary_blocker_check"] == "missing_required:last"
    assert summary["primary_blocker_value"] == "last"
    assert summary["primary_blocker_operator"] == "present"
    assert summary["primary_blocker_threshold"] == "required"
    assert summary["primary_blocker_reason"] == "last source column is missing for last"
    assert int(summary["action_queue_count"]) == 2
    assert int(summary["blocked_action_count"]) == 2
    assert summary["next_gate"] == "audit-adapter-schema"
    assert (audit.template["status"] == "missing").sum() == 2
    assert audit.action_queue is not None
    assert list(audit.action_queue["check"]) == ["missing_required:last", "missing_required:last_qty"]
    assert set(audit.action_queue["queue_status"]) == {"blocked"}


def test_adapter_schema_audit_matches_case_insensitive_headers():
    audit = audit_adapter_schema(
        pd.DataFrame(columns=[column.upper() for column in TICK_COLUMNS]),
        adapter="normalized",
        kind="top-of-book",
    )

    assert audit.passed
    assert set(audit.columns["match_type"]) == {"case_insensitive"}
    assert audit.columns["matched_source_column"].tolist() == [column.upper() for column in TICK_COLUMNS]


def test_cli_adapter_schema_audit_writes_outputs_and_fails_on_missing(tmp_path):
    sample = tmp_path / "arrow_fills_sample.csv"
    out_dir = tmp_path / "schema_audit"
    pd.DataFrame(
        columns=["client_order_id", "instrument_id", "ts_fill_ns", "side", "qty", "broker_ref"]
    ).to_csv(sample, index=False)

    code = main(
        [
            "audit-adapter-schema",
            "--sample",
            str(sample),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "fills",
            "--fail-on-missing",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "adapter_schema_summary.csv")
    template = pd.read_csv(out_dir / "adapter_mapping_template.csv")
    checklist = pd.read_csv(out_dir / "adapter_schema_review_checklist.csv")
    action_queue = pd.read_csv(out_dir / "adapter_schema_action_queue.csv")
    config = json.loads((out_dir / "adapter_schema_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "adapter_schema_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert code == 2
    assert summary.loc[0, "adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert int(summary.loc[0, "missing_required_columns"]) == 1
    assert int(summary.loc[0, "failed_check_count"]) == 1
    assert int(summary.loc[0, "action_queue_count"]) == 3
    assert int(summary.loc[0, "blocked_action_count"]) == 2
    assert int(summary.loc[0, "review_action_count"]) == 1
    assert summary.loc[0, "next_gate"] == "audit-adapter-schema"
    assert summary.loc[0, "next_gate_help_command"] == "python -m hft_cli audit-adapter-schema --help"
    assert summary.loc[0, "primary_action_status"] == "blocked"
    assert summary.loc[0, "failed_check_names"] == "missing_required:price"
    assert summary.loc[0, "primary_blocker_check"] == "missing_required:price"
    assert summary.loc[0, "primary_blocker_reason"] == "price source column is missing for price"
    assert summary.loc[0, "missing_source_columns"] == "price"
    assert "broker_ref" in summary.loc[0, "extra_source_columns"]
    assert "missing" in set(template["status"])
    checks = checklist.set_index("check_name")
    assert not bool(checks.loc["required_columns_present", "passed"])
    assert checks.loc["required_columns_present", "status"] == "blocked"
    assert not bool(checks.loc["vendor_schema_reviewed", "passed"])
    assert checks.loc["vendor_schema_reviewed", "status"] == "blocked"
    assert checks.loc["extra_columns_classified", "status"] == "review"
    assert set(action_queue["check"]) == {
        "missing_required:price",
        "vendor_schema_reviewed",
        "extra_column:broker_ref",
    }
    assert action_queue.loc[0, "check"] == "missing_required:price"
    assert action_queue.loc[0, "next_gate"] == "audit-adapter-schema"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli audit-adapter-schema --help"
    assert config["blocked_action_count"] == 2
    assert config["review_action_count"] == 1
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "missing_required:price"
    assert config["blocked_actions"][0]["next_gate"] == "audit-adapter-schema"
    assert config["review_actions"][0]["check"] == "extra_column:broker_ref"
    assert "# Adapter Schema Audit Runbook" in runbook
    assert "- Required columns present: no" in runbook
    assert "missing_required:price" in runbook
    assert (out_dir / "adapter_schema_columns.csv").exists()
    assert (out_dir / "adapter_schema_review_checklist.csv").exists()
    assert (out_dir / "adapter_schema_action_queue.csv").exists()
    assert (out_dir / "adapter_schema_config.json").exists()
    assert (out_dir / "adapter_schema_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    assert "adapter_schema_action_queue.csv" in artifact_paths
    assert "adapter_schema_config.json" in artifact_paths
    assert "adapter_schema_runbook.md" in artifact_paths


def test_cli_adapter_schema_audit_can_fail_on_review_actions(tmp_path):
    sample = tmp_path / "normalized_ticks_extra.csv"
    out_dir = tmp_path / "schema_audit"
    pd.DataFrame(columns=[*TICK_COLUMNS, "venue_code"]).to_csv(sample, index=False)

    code = main(
        [
            "audit-adapter-schema",
            "--sample",
            str(sample),
            "--out",
            str(out_dir),
            "--adapter",
            "normalized",
            "--kind",
            "ticks",
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "adapter_schema_summary.csv")
    action_queue = pd.read_csv(out_dir / "adapter_schema_action_queue.csv")
    assert code == 2
    assert bool(summary.loc[0, "all_required_present"])
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert int(summary.loc[0, "review_action_count"]) == 1
    assert action_queue.loc[0, "queue_status"] == "review"
    assert action_queue.loc[0, "check"] == "extra_column:venue_code"
