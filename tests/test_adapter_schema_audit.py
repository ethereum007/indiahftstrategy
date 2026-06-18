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
    assert set(audit.template["status"]) == {"mapped"}
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
    assert (audit.template["status"] == "missing").sum() == 2


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
        ]
    )

    summary = pd.read_csv(out_dir / "adapter_schema_summary.csv")
    template = pd.read_csv(out_dir / "adapter_mapping_template.csv")
    checklist = pd.read_csv(out_dir / "adapter_schema_review_checklist.csv")
    assert code == 2
    assert summary.loc[0, "adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert int(summary.loc[0, "missing_required_columns"]) == 1
    assert int(summary.loc[0, "failed_check_count"]) == 1
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
    assert (out_dir / "adapter_schema_columns.csv").exists()
    assert (out_dir / "adapter_schema_review_checklist.csv").exists()
    assert (out_dir / "manifest.json").exists()
