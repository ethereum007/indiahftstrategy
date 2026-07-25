import json
from pathlib import Path

import pandas as pd
import pytest

from adapters.applied_mapped_data import AppliedMappedDataReport
from adapters.reviewed_mapped_data import ReviewedMappedDataReport
from adapters.vendor_intake import VendorCsvIntakeConfig, write_vendor_csv_intake_report
from adapters.vendor_mapping_application import write_vendor_mapping_application
from adapters.vendor_mapping_review import write_vendor_mapping_review
from hft_cli import main
from reports.manifest import file_sha256
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
    write_vendor_market_data_pipeline,
)
from tests.test_vendor_mapping_application import (
    _mapping_scope,
    _normal_ticks,
    _opaque_ticks,
    _target_intake,
)
from tests.test_market_calendar import _calendar_path


def vendor_ticks(day: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "exchange_ts": f"{day} 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            },
            {
                "exchange_ts": f"{day} 09:15:01",
                "best_bid": 100.05,
                "best_ask": 100.10,
                "bid_size": 150,
                "ask_size": 75,
                "last_px": 100.10,
                "last_size": 75,
            },
        ]
    )


def approved_mapping_review(
    tmp_path: Path,
    label: str = "reviewed",
    *,
    opaque_columns: bool = False,
) -> tuple[Path, Path]:
    source_path = tmp_path / f"{label}_ticks.csv"
    intake_dir = tmp_path / f"{label}_review_intake"
    mapping_path = tmp_path / f"{label}_candidate_mapping.csv"
    decision_path = tmp_path / f"{label}_decision.csv"
    review_dir = tmp_path / f"{label}_mapping_review"
    if opaque_columns:
        source = pd.DataFrame(
            [
                {
                    "T": f"2026-06-10 09:15:0{second}",
                    "B": 100.0 + second * 0.05,
                    "A": 100.05 + second * 0.05,
                    "BQ": 75,
                    "AQ": 150,
                    "L": 100.05 + second * 0.05,
                    "LQ": 75,
                }
                for second in range(2)
            ]
        )
    else:
        source = vendor_ticks("2026-06-10")
    source.to_csv(source_path, index=False)
    intake = write_vendor_csv_intake_report(
        source_path,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="ticks"),
    )
    if opaque_columns:
        mapping = pd.DataFrame(
            [
                {"normalized_column": "ts", "source_column": "T"},
                {"normalized_column": "bid", "source_column": "B", "transform": "float"},
                {"normalized_column": "ask", "source_column": "A", "transform": "float"},
                {"normalized_column": "bid_qty", "source_column": "BQ", "transform": "int"},
                {"normalized_column": "ask_qty", "source_column": "AQ", "transform": "int"},
                {"normalized_column": "last", "source_column": "L", "transform": "float"},
                {"normalized_column": "last_qty", "source_column": "LQ", "transform": "int"},
            ]
        )
    else:
        mapping = intake.mapping_draft
    mapping.to_csv(mapping_path, index=False)
    pd.DataFrame(
        [
            {
                "intake_receipt_id": intake.receipt["intake_receipt_id"],
                "source_file_sha256": intake.source_profile["file_sha256"],
                "mapping_candidate_sha256": file_sha256(mapping_path),
                "adapter": "arrow_money",
                "kind": "ticks",
                "decision": "approved",
                "operator_id": "market-data-reviewer-1",
                "operator_role": "market_data_engineer",
                "reviewed_at_utc": "2026-07-14T07:00:00+00:00",
                "vendor_documentation_checked": True,
                "source_columns_confirmed": True,
                "field_semantics_confirmed": True,
                "timestamp_semantics_confirmed": True,
                "price_quantity_units_confirmed": True,
                "transform_semantics_confirmed": True,
                "notes": "Reviewed against retained vendor documentation.",
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(decision_path, index=False)
    write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )
    return review_dir, source_path


def target_mapping_application(
    tmp_path: Path,
    label: str,
    *,
    opaque_columns: bool = False,
) -> tuple[Path, Path, Path, Path]:
    scope_dir, _ = _mapping_scope(tmp_path, label, opaque=opaque_columns)
    target_frame = (
        _opaque_ticks("2026-07-15")
        if opaque_columns
        else _normal_ticks("2026-07-15")
    )
    intake_dir, source_path, _ = _target_intake(
        tmp_path,
        f"{label}_target",
        frame=target_frame,
    )
    application_dir = tmp_path / f"{label}_application"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)
    return application_dir, scope_dir, intake_dir, source_path


def target_mapping_application_batch(
    tmp_path: Path,
    label: str,
    days: list[str],
) -> tuple[list[Path], list[Path], Path]:
    scope_dir, _ = _mapping_scope(tmp_path, label)
    application_dirs = []
    source_paths = []
    for idx, day in enumerate(days, start=1):
        intake_dir, source_path, _ = _target_intake(
            tmp_path,
            f"{label}_target_{idx}",
            frame=_normal_ticks(day),
        )
        application_dir = tmp_path / f"{label}_application_{idx}"
        write_vendor_mapping_application(scope_dir, intake_dir, application_dir)
        application_dirs.append(application_dir)
        source_paths.append(source_path)
    return application_dirs, source_paths, scope_dir


def test_vendor_market_data_pipeline_onboards_tick_file(tmp_path):
    raw = vendor_ticks("2026-06-10")
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
    config = json.loads((out_dir / "vendor_market_data_pipeline_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "vendor_market_data_pipeline_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_pipeline_runbook.md").read_text(encoding="utf-8")
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert report.ready
    assert summary["normalized_rows"] == 2
    assert summary["mapping_coverage"] == 1.0
    assert summary["mapping_source"] == "vendor_intake_draft"
    assert summary["market"] == "india_nse_index_derivatives"
    assert summary["blocked_action_count"] == 0
    assert summary["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert "# Vendor Market Data Pipeline Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook
    assert summary["source_file_sha256"] == manifest["inputs"]["input"]["sha256"]
    assert len(summary["source_header_sha256"]) == 64
    assert len(summary["mapping_draft_sha256"]) == 64
    assert "vendor_intake_manifest" in manifest["inputs"]
    assert "vendor_intake_source_profile" in manifest["inputs"]
    assert "mapped_data_manifest" in manifest["inputs"]
    assert "data_readiness_manifest" in manifest["inputs"]
    assert config["ready"]
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert config["source"]["file_sha256"] == summary["source_file_sha256"]
    assert config["source"]["header_sha256"] == summary["source_header_sha256"]
    assert config["mapping"]["source"] == "vendor_intake_draft"
    assert config["mapping"]["draft_sha256"] == summary["mapping_draft_sha256"]
    assert config["data_readiness"]["ready"]
    assert config["data_readiness"]["thresholds"]["min_tick_rows"] == 2
    assert config["data_readiness"]["thresholds"]["expected_adapter"] == "arrow_money"
    assert config["data_readiness"]["thresholds"]["expected_vendor_data_kind"] == "ticks"
    assert config["component_manifests"]["vendor_intake"].endswith("manifest.json")
    assert components.loc["vendor_intake", "ready"]
    assert components.loc["data_readiness", "ready"]
    assert (out_dir / "01_vendor_intake" / "vendor_mapping_draft.csv").exists()
    assert (out_dir / "02_normalized" / "normalized_ticks.csv").exists()
    assert (out_dir / "03_diagnostics" / "diagnostic_summary.csv").exists()
    assert (out_dir / "04_data_readiness" / "data_readiness_summary.csv").exists()
    assert "vendor_market_data_pipeline_action_queue.csv" in artifact_paths
    assert "vendor_market_data_pipeline_runbook.md" in artifact_paths
    assert manifest["run_type"] == "vendor_market_data_pipeline"

    ready_code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(tmp_path / "pipeline_cli_ready"),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert ready_code == 0


def test_vendor_pipeline_binds_market_calendar_evidence(tmp_path):
    raw_path = tmp_path / "arrow_ticks.csv"
    out_dir = tmp_path / "calendar_pipeline"
    calendar_path = _calendar_path(tmp_path)
    vendor_ticks("2026-06-09").to_csv(raw_path, index=False)

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
            market_calendar_path=str(calendar_path),
        ),
    )
    summary = report.summary.iloc[0]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    readiness_summary = pd.read_csv(
        out_dir / "04_data_readiness" / "data_readiness_summary.csv"
    ).iloc[0]
    readiness_config = json.loads(
        (out_dir / "04_data_readiness" / "data_readiness_config.json").read_text(
            encoding="utf-8"
        )
    )

    assert report.ready
    assert summary["market_calendar_id"] == "nse-fo-test-2026-06"
    assert summary["market_calendar_sha256"] == file_sha256(calendar_path)
    assert manifest["inputs"]["market_calendar"]["sha256"] == file_sha256(
        calendar_path
    )
    assert config["market_calendar"]["provided"] is True
    assert config["market_calendar"]["sha256"] == file_sha256(calendar_path)
    assert (out_dir / "00_market_calendar" / "manifest.json").exists()
    assert bool(readiness_summary["require_market_calendar"])
    assert readiness_summary["market_calendar_id"] == "nse-fo-test-2026-06"
    assert readiness_summary["market_calendar_sha256"] == file_sha256(
        calendar_path
    )
    assert readiness_config["market_calendar"]["binding_components"] == [
        "mapped_data",
        "tick_diagnostics",
    ]


def test_vendor_market_data_pipeline_gates_filtered_session_quarantine(tmp_path):
    out_of_session = vendor_ticks("2026-06-12").iloc[[0]].copy()
    out_of_session["exchange_ts"] = "2026-06-12 08:00:00"
    valid = vendor_ticks("2026-06-12").iloc[[0]].copy()
    valid["exchange_ts"] = "2026-06-12 10:00:00"
    weekend = vendor_ticks("2026-06-13").iloc[[0]].copy()
    weekend["exchange_ts"] = "2026-06-13 10:00:00"
    raw = pd.concat([out_of_session, valid, weekend], ignore_index=True)
    raw_path = tmp_path / "session_contaminated_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=tmp_path / "blocked_pipeline",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["quarantined_rows"]) == 2
    assert int(mapped_summary["dropped_non_trading_day_rows"]) == 1
    assert int(mapped_summary["dropped_out_of_session_rows"]) == 1
    assert {
        "mapped_data_dropped_non_trading_day_rows",
        "mapped_data_dropped_out_of_session_rows",
    } <= failed

    allowed_dir = tmp_path / "allowed_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-non-trading-day-rows",
            "1",
            "--max-out-of-session-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert code == 0
    assert allowed_config["data_readiness"]["thresholds"][
        "max_non_trading_day_rows"
    ] == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_out_of_session_rows"
    ] == 1


def test_vendor_market_data_pipeline_gates_null_required_rows(tmp_path):
    raw = vendor_ticks("2026-06-12")
    raw.loc[1, "best_bid"] = pd.NA
    raw_path = tmp_path / "null_quote_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_null_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            require_all_mapped=False,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_null_rows"]) == 1
    assert int(blocked.summary.loc[0, "dropped_null_rows"]) == 1
    assert "mapped_data_dropped_null_rows" in failed
    assert blocked_config["normalized"]["dropped_null_rows"] == 1
    assert "- Null required-field rows: 1" in blocked_runbook

    allowed_dir = tmp_path / "allowed_null_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--allow-missing-required",
            "--max-null-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_null_rows"]) == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_null_rows"
    ] == 1


def test_vendor_market_data_pipeline_gates_nonfinite_numeric_rows(tmp_path):
    raw = vendor_ticks("2026-06-12")
    raw.loc[1, "best_bid"] = float("inf")
    raw_path = tmp_path / "nonfinite_quote_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_nonfinite_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_nonfinite_rows"]) == 1
    assert int(blocked.summary.loc[0, "dropped_nonfinite_rows"]) == 1
    assert "mapped_data_dropped_nonfinite_rows" in failed
    assert blocked_config["normalized"]["dropped_nonfinite_rows"] == 1
    assert "- Non-finite numeric rows: 1" in blocked_runbook

    allowed_dir = tmp_path / "allowed_nonfinite_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-nonfinite-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_nonfinite_rows"]) == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_nonfinite_rows"
    ] == 1


def test_vendor_market_data_pipeline_gates_nonintegral_integer_fields(tmp_path):
    raw = vendor_ticks("2026-06-12")
    raw["bid_size"] = raw["bid_size"].astype("float64")
    raw.loc[1, "bid_size"] = 75.5
    raw_path = tmp_path / "fractional_depth_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_nonintegral_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_nonintegral_rows"]) == 1
    assert int(blocked.summary.loc[0, "dropped_nonintegral_rows"]) == 1
    assert "mapped_data_dropped_nonintegral_rows" in failed
    assert blocked_config["normalized"]["dropped_nonintegral_rows"] == 1
    assert "- Non-integral integer-field rows: 1" in blocked_runbook

    allowed_dir = tmp_path / "allowed_nonintegral_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-nonintegral-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_nonintegral_rows"]) == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_nonintegral_rows"
    ] == 1


def test_vendor_market_data_pipeline_gates_duplicate_tick_packets(tmp_path):
    raw = vendor_ticks("2026-06-12")
    raw = pd.concat(
        [raw.iloc[[0]], raw.iloc[[0]], raw.iloc[[1]]],
        ignore_index=True,
    )
    raw_path = tmp_path / "duplicate_tick_packets.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_duplicate_tick_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_duplicate_rows"]) == 1
    assert int(blocked.summary.loc[0, "dropped_duplicate_rows"]) == 1
    assert "mapped_data_dropped_duplicate_tick_rows" in failed
    assert blocked_config["normalized"]["dropped_duplicate_rows"] == 1
    assert "- Duplicate tick packets: 1" in blocked_runbook

    allowed_dir = tmp_path / "allowed_duplicate_tick_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-duplicate-tick-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_duplicate_rows"]) == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_duplicate_tick_rows"
    ] == 1


def test_vendor_market_data_pipeline_gates_packets_below_timestamp_high_water(
    tmp_path,
):
    raw = pd.concat(
        [
            vendor_ticks("2026-06-12").iloc[[0]],
            vendor_ticks("2026-06-12").iloc[[0]],
            vendor_ticks("2026-06-12").iloc[[1]],
            vendor_ticks("2026-06-12").iloc[[1]],
        ],
        ignore_index=True,
    )
    raw["exchange_ts"] = [
        "2026-06-12 09:15:03",
        "2026-06-12 09:15:00",
        "2026-06-12 09:15:01",
        "2026-06-12 09:15:04",
    ]
    raw["best_bid"] = [100.15, 100.0, 100.05, 100.20]
    raw["best_ask"] = [100.20, 100.05, 100.10, 100.25]
    raw_path = tmp_path / "nonmonotonic_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_nonmonotonic_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_nonmonotonic_rows"]) == 2
    assert int(blocked.summary.loc[0, "dropped_nonmonotonic_rows"]) == 2
    assert "mapped_data_dropped_nonmonotonic_rows" in failed
    assert blocked_config["normalized"]["dropped_nonmonotonic_rows"] == 2
    assert "- Nonmonotonic tick packets: 2" in blocked_runbook

    allowed_dir = tmp_path / "allowed_nonmonotonic_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-nonmonotonic-rows",
            "2",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_nonmonotonic_rows"]) == 2
    assert allowed_config["data_readiness"]["thresholds"][
        "max_nonmonotonic_rows"
    ] == 2


def test_vendor_market_data_pipeline_gates_nonpositive_tick_depth(tmp_path):
    raw = pd.concat(
        [
            vendor_ticks("2026-06-12"),
            vendor_ticks("2026-06-12").iloc[[0]],
        ],
        ignore_index=True,
    )
    raw.loc[0, "bid_size"] = 0
    raw.loc[1, "ask_size"] = -1
    raw.loc[2, "exchange_ts"] = "2026-06-12 09:15:02"
    raw_path = tmp_path / "nonpositive_depth_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_nonpositive_depth_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_negative_depth_rows"]) == 2
    assert int(blocked.summary.loc[0, "dropped_negative_depth_rows"]) == 2
    assert "mapped_data_dropped_negative_depth_rows" in failed
    assert blocked_config["normalized"]["dropped_negative_depth_rows"] == 2
    assert "- Nonpositive depth rows: 2" in blocked_runbook

    allowed_dir = tmp_path / "allowed_nonpositive_depth_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-nonpositive-depth-rows",
            "2",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_negative_depth_rows"]) == 2
    assert allowed_config["data_readiness"]["thresholds"][
        "max_nonpositive_depth_rows"
    ] == 2


def test_vendor_market_data_pipeline_gates_invalid_trade_rows(tmp_path):
    raw = pd.concat(
        [
            vendor_ticks("2026-06-12"),
            vendor_ticks("2026-06-12").iloc[[0]],
        ],
        ignore_index=True,
    )
    raw.loc[0, "last_px"] = 0
    raw.loc[1, "last_size"] = -1
    raw.loc[2, "exchange_ts"] = "2026-06-12 09:15:02"
    raw_path = tmp_path / "invalid_trade_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_invalid_trade_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_invalid_trade_rows"]) == 2
    assert int(blocked.summary.loc[0, "dropped_invalid_trade_rows"]) == 2
    assert "mapped_data_dropped_invalid_trade_rows" in failed
    assert blocked_config["normalized"]["dropped_invalid_trade_rows"] == 2
    assert "- Invalid trade rows: 2" in blocked_runbook

    allowed_dir = tmp_path / "allowed_invalid_trade_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-invalid-trade-rows",
            "2",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_invalid_trade_rows"]) == 2
    assert allowed_config["data_readiness"]["thresholds"][
        "max_invalid_trade_rows"
    ] == 2


def test_vendor_market_data_pipeline_gates_off_tick_prices(tmp_path):
    raw = vendor_ticks("2026-06-12")
    raw.loc[1, "best_ask"] = 100.07
    raw_path = tmp_path / "off_tick_prices.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_off_tick_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            max_off_tick_price_rows=0,
        ),
    )

    diagnostic_summary = blocked.diagnostics.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert bool(diagnostic_summary["price_grid_validation_enabled"])
    assert diagnostic_summary["price_grid_tick_size"] == pytest.approx(0.05)
    assert int(diagnostic_summary["off_tick_price_rows"]) == 1
    assert int(blocked.summary.loc[0, "off_tick_price_rows"]) == 1
    assert "tick_off_tick_price_rows" in failed
    assert blocked_config["diagnostics"]["price_grid_validation_enabled"]
    assert blocked_config["diagnostics"]["price_grid_tick_size"] == pytest.approx(
        0.05
    )
    assert blocked_config["diagnostics"]["off_tick_price_rows"] == 1
    assert "- Off-tick price rows: 1" in blocked_runbook

    allowed_dir = tmp_path / "allowed_off_tick_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-off-tick-price-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["off_tick_price_rows"]) == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_off_tick_price_rows"
    ] == 1


def test_vendor_market_data_pipeline_gates_integer_overflow_rows(tmp_path):
    raw = vendor_ticks("2026-06-12")
    raw["bid_size"] = raw["bid_size"].astype("object")
    raw.loc[1, "bid_size"] = 10**30
    raw_path = tmp_path / "overflow_depth_ticks.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_integer_overflow_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert int(mapped_summary["dropped_integer_overflow_rows"]) == 1
    assert int(blocked.summary.loc[0, "dropped_integer_overflow_rows"]) == 1
    assert "mapped_data_dropped_integer_overflow_rows" in failed
    assert blocked_config["normalized"]["dropped_integer_overflow_rows"] == 1
    assert "- Integer-overflow rows: 1" in blocked_runbook

    allowed_dir = tmp_path / "allowed_integer_overflow_pipeline"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-integer-overflow-rows",
            "1",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_summary = pd.read_csv(
        allowed_dir / "vendor_market_data_pipeline_summary.csv"
    ).iloc[0]

    assert code == 0
    assert bool(allowed_summary["ready"])
    assert int(allowed_summary["dropped_integer_overflow_rows"]) == 1
    assert allowed_config["data_readiness"]["thresholds"][
        "max_integer_overflow_rows"
    ] == 1


def test_vendor_market_data_pipeline_uses_exact_approved_mapping_review(tmp_path):
    review_dir, raw_path = approved_mapping_review(tmp_path)
    out_dir = tmp_path / "reviewed_pipeline"

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        mapping_review_dir=review_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    readiness_summary = report.readiness.summary.iloc[0]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "vendor_market_data_pipeline_config.json").read_text(encoding="utf-8")
    )
    assert report.ready
    assert isinstance(report.mapped_data, ReviewedMappedDataReport)
    assert summary["mapping_source"] == "verified_approved_review"
    assert summary["mapping_review_path"] == str(review_dir.resolve())
    assert summary["mapping_review_id"]
    assert len(summary["mapping_review_sha256"]) == 64
    assert bool(readiness_summary["require_reviewed_mapping_normalization"])
    assert bool(readiness_summary["mapped_data_review_bound"])
    assert bool(readiness_summary["mapped_data_mapping_review_verified"])
    assert bool(readiness_summary["mapped_data_mapping_review_approved"])
    assert "mapping_review" in manifest["inputs"]
    assert "mapping_review_manifest" in manifest["inputs"]
    assert "mapping_review_receipt" in manifest["inputs"]
    assert config["mapping"]["source"] == "verified_approved_review"
    assert config["mapping"]["review_path"] == str(review_dir.resolve())
    assert config["data_readiness"]["thresholds"][
        "require_reviewed_mapping_normalization"
    ]

    cli_out = tmp_path / "reviewed_pipeline_cli"
    assert (
        main(
            [
                "pipeline-vendor-market-data",
                "--input",
                str(raw_path),
                "--out",
                str(cli_out),
                "--mapping-review",
                str(review_dir),
                "--timestamp-unit",
                "datetime",
                "--tick-size",
                "0.05",
                "--min-rows",
                "2",
                "--fail-on-breach",
            ]
        )
        == 0
    )


def test_vendor_market_data_pipeline_rejects_ambiguous_or_mismatched_review_inputs(tmp_path):
    review_dir, raw_path = approved_mapping_review(tmp_path, "binding")
    mapping_path = review_dir / "reviewed_vendor_mapping.csv"
    mutual_out = tmp_path / "mutual_out"
    with pytest.raises(ValueError, match="mutually exclusive"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=mutual_out,
            mapping_path=mapping_path,
            mapping_review_dir=review_dir,
        )
    assert not mutual_out.exists()

    other_source = tmp_path / "other_ticks.csv"
    vendor_ticks("2026-06-11").to_csv(other_source, index=False)
    source_out = tmp_path / "source_mismatch_out"
    with pytest.raises(ValueError, match="exact source"):
        write_vendor_market_data_pipeline(
            other_source,
            output_dir=source_out,
            mapping_review_dir=review_dir,
        )
    assert not source_out.exists()

    adapter_out = tmp_path / "adapter_mismatch_out"
    with pytest.raises(ValueError, match="adapter does not match"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=adapter_out,
            mapping_review_dir=review_dir,
            config=VendorMarketDataPipelineConfig(adapter="irage"),
        )
    assert not adapter_out.exists()

    kind_out = tmp_path / "kind_mismatch_out"
    with pytest.raises(ValueError, match="kind does not match"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=kind_out,
            mapping_review_dir=review_dir,
            config=VendorMarketDataPipelineConfig(kind="chain"),
        )
    assert not kind_out.exists()


def test_vendor_market_data_pipeline_uses_verified_target_application(tmp_path):
    application_dir, scope_dir, intake_dir, raw_path = target_mapping_application(
        tmp_path,
        "pipeline_target",
    )
    out_dir = tmp_path / "target_application_pipeline"

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        mapping_application_dir=application_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=1,
        ),
    )

    summary = report.summary.iloc[0]
    mapped_summary = report.mapped_data.summary.iloc[0]
    readiness_summary = report.readiness.summary.iloc[0]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert report.ready
    assert isinstance(report.mapped_data, AppliedMappedDataReport)
    assert summary["mapping_source"] == "verified_target_application"
    assert summary["mapping_application_path"] == str(application_dir.resolve())
    assert summary["mapping_application_id"]
    assert len(summary["mapping_application_sha256"]) == 64
    assert summary["mapping_scope_review_path"] == str(scope_dir.resolve())
    assert summary["mapping_scope_review_id"]
    assert summary["target_intake_path"] == str(intake_dir.resolve())
    assert summary["target_intake_receipt_id"]
    assert len(summary["applied_mapping_sha256"]) == 64
    assert bool(mapped_summary["target_application_bound"])
    assert bool(mapped_summary["mapping_application_verified"])
    assert bool(readiness_summary["require_target_application_normalization"])
    assert not bool(readiness_summary["require_reviewed_mapping_normalization"])
    assert bool(readiness_summary["mapped_data_target_application_bound"])
    assert bool(readiness_summary["mapped_data_mapping_application_verified"])
    assert {
        "mapping_application",
        "mapping_application_manifest",
        "mapping_application_receipt",
        "mapping_scope_review",
        "target_intake",
        "target_source",
        "applied_mapping",
    }.issubset(manifest["inputs"])
    assert config["mapping"]["source"] == "verified_target_application"
    assert config["mapping"]["application"]["path"] == str(
        application_dir.resolve()
    )
    assert config["mapping"]["application"]["scope_review_id"] == summary[
        "mapping_scope_review_id"
    ]
    assert config["mapping"]["application"]["target_intake_receipt_id"] == summary[
        "target_intake_receipt_id"
    ]
    assert config["mapping"]["application"]["applied_mapping_sha256"] == summary[
        "applied_mapping_sha256"
    ]
    assert config["data_readiness"]["thresholds"][
        "require_target_application_normalization"
    ]

    cli_out = tmp_path / "target_application_pipeline_cli"
    assert (
        main(
            [
                "pipeline-vendor-market-data",
                "--input",
                str(raw_path),
                "--out",
                str(cli_out),
                "--mapping-application",
                str(application_dir),
                "--timestamp-unit",
                "datetime",
                "--tick-size",
                "0.05",
                "--min-rows",
                "1",
                "--fail-on-breach",
            ]
        )
        == 0
    )


def test_target_application_pipeline_accepts_blocked_opaque_intake(tmp_path):
    application_dir, _, _, raw_path = target_mapping_application(
        tmp_path,
        "opaque_target_pipeline",
        opaque_columns=True,
    )

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=tmp_path / "opaque_target_application_pipeline",
        mapping_application_dir=application_dir,
        config=VendorMarketDataPipelineConfig(
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=1,
        ),
    )

    components = report.components.set_index("component")
    readiness_items = report.readiness.items.set_index("component")
    assert not report.intake.ready
    assert report.ready
    assert bool(components.loc["vendor_intake", "ready"])
    assert components.loc["vendor_intake", "recommendation"] == (
        "accepted_by_verified_target_application"
    )
    assert bool(readiness_items.loc["vendor_intake", "ready"])
    assert len(report.mapped_data.data) == 1


def test_target_application_pipeline_rejects_substitution_collision_and_drift(tmp_path):
    application_dir, _, intake_dir, raw_path = target_mapping_application(
        tmp_path,
        "target_binding",
    )
    mapping_path = application_dir / "target_applied_vendor_mapping.csv"

    mutual_out = tmp_path / "target_mutual_out"
    with pytest.raises(ValueError, match="mutually exclusive"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=mutual_out,
            mapping_path=mapping_path,
            mapping_application_dir=application_dir,
        )
    assert not mutual_out.exists()

    other_source = tmp_path / "target_other.csv"
    _normal_ticks("2026-07-16").to_csv(other_source, index=False)
    source_out = tmp_path / "target_source_mismatch_out"
    with pytest.raises(ValueError, match="exact target source"):
        write_vendor_market_data_pipeline(
            other_source,
            output_dir=source_out,
            mapping_application_dir=application_dir,
        )
    assert not source_out.exists()

    adapter_out = tmp_path / "target_adapter_mismatch_out"
    with pytest.raises(ValueError, match="adapter does not match"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=adapter_out,
            mapping_application_dir=application_dir,
            config=VendorMarketDataPipelineConfig(adapter="irage"),
        )
    assert not adapter_out.exists()

    kind_out = tmp_path / "target_kind_mismatch_out"
    with pytest.raises(ValueError, match="kind does not match"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=kind_out,
            mapping_application_dir=application_dir,
            config=VendorMarketDataPipelineConfig(kind="chain"),
        )
    assert not kind_out.exists()

    collision_out = application_dir / "pipeline"
    with pytest.raises(ValueError, match="cannot modify mapping-application evidence"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=collision_out,
            mapping_application_dir=application_dir,
        )
    assert not collision_out.exists()

    raw_path.write_text(raw_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    stale_out = tmp_path / "target_stale_out"
    with pytest.raises(ValueError, match="verified ready target application"):
        write_vendor_market_data_pipeline(
            raw_path,
            output_dir=stale_out,
            mapping_application_dir=application_dir,
        )
    assert not stale_out.exists()
    assert intake_dir.exists()


def test_reviewed_pipeline_accepts_manual_mapping_over_blocked_inference(tmp_path):
    review_dir, raw_path = approved_mapping_review(
        tmp_path,
        "opaque",
        opaque_columns=True,
    )

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=tmp_path / "opaque_reviewed_pipeline",
        mapping_review_dir=review_dir,
        config=VendorMarketDataPipelineConfig(
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    components = report.components.set_index("component")
    readiness_items = report.readiness.items.set_index("component")
    assert not report.intake.ready
    assert report.ready
    assert bool(components.loc["vendor_intake", "ready"])
    assert components.loc["vendor_intake", "recommendation"] == (
        "accepted_by_verified_mapping_review"
    )
    assert bool(readiness_items.loc["vendor_intake", "ready"])
    assert len(report.mapped_data.data) == 2


def test_vendor_market_data_batch_pipeline_compares_clean_tick_days(tmp_path):
    day1 = tmp_path / "arrow_ticks_day1.csv"
    day2 = tmp_path / "arrow_ticks_day2.csv"
    out_dir = tmp_path / "batch"
    vendor_ticks("2026-06-10").to_csv(day1, index=False)
    vendor_ticks("2026-06-11").to_csv(day2, index=False)

    report = write_vendor_market_data_batch_pipeline(
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "vendor_market_data_batch_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "vendor_market_data_batch_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(encoding="utf-8")
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert report.ready
    assert summary["dataset_count"] == 2
    assert summary["unique_source_files"] == 2
    assert summary["source_file_fingerprint_coverage"] == 1.0
    assert summary["min_mapping_coverage"] == 1.0
    assert summary["unique_header_fingerprints"] == 1
    assert summary["unique_mapping_drafts"] == 1
    assert summary["mapping_sources"] == "vendor_intake_draft"
    assert summary["comparison_accepted"]
    assert summary["market"] == "india_nse_index_derivatives"
    assert int(summary["dropped_null_rows"]) == 0
    assert int(summary["dropped_nonfinite_rows"]) == 0
    assert int(summary["dropped_nonintegral_rows"]) == 0
    assert int(summary["dropped_duplicate_rows"]) == 0
    assert int(summary["dropped_integer_overflow_rows"]) == 0
    assert int(summary["dropped_nonmonotonic_rows"]) == 0
    assert int(summary["dropped_nonpositive_strike_rows"]) == 0
    assert int(summary["dropped_negative_depth_rows"]) == 0
    assert int(summary["dropped_invalid_trade_rows"]) == 0
    assert bool(summary["price_grid_validation_enabled"])
    assert summary["price_grid_tick_size"] == pytest.approx(0.05)
    assert int(summary["off_tick_price_rows"]) == 0
    assert summary["blocked_action_count"] == 0
    assert summary["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert "# Vendor Market Data Batch Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook
    assert "- Null required-field rows: 0" in runbook
    assert "- Non-finite numeric rows: 0" in runbook
    assert "- Non-integral integer-field rows: 0" in runbook
    assert "- Duplicate tick packets: 0" in runbook
    assert "- Integer-overflow rows: 0" in runbook
    assert "- Nonmonotonic tick packets: 0" in runbook
    assert "- Nonpositive depth rows: 0" in runbook
    assert set(report.datasets["dataset"]) == {"day1", "day2"}
    assert (report.datasets["dropped_null_rows"].astype(int) == 0).all()
    assert (report.datasets["dropped_nonfinite_rows"].astype(int) == 0).all()
    assert (report.datasets["dropped_nonintegral_rows"].astype(int) == 0).all()
    assert (report.datasets["dropped_duplicate_rows"].astype(int) == 0).all()
    assert (
        report.datasets["dropped_integer_overflow_rows"].astype(int) == 0
    ).all()
    assert (
        report.datasets["dropped_nonmonotonic_rows"].astype(int) == 0
    ).all()
    assert (
        report.datasets["dropped_nonpositive_strike_rows"].astype(int) == 0
    ).all()
    assert (
        report.datasets["dropped_negative_depth_rows"].astype(int) == 0
    ).all()
    assert (
        report.datasets["dropped_invalid_trade_rows"].astype(int) == 0
    ).all()
    assert report.datasets["price_grid_validation_enabled"].astype(bool).all()
    assert (report.datasets["off_tick_price_rows"].astype(int) == 0).all()
    assert report.datasets["source_file_sha256"].nunique() == 2
    assert report.datasets["source_header_sha256"].nunique() == 1
    assert "dataset_manifests" in manifest["inputs"]
    assert len(manifest["inputs"]["dataset_manifests"]) == 2
    assert "comparison_manifest" in manifest["inputs"]
    assert config["ready"]
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert config["dataset_count"] == 2
    assert config["dropped_null_rows"] == 0
    assert config["dropped_nonfinite_rows"] == 0
    assert config["dropped_nonintegral_rows"] == 0
    assert config["dropped_duplicate_rows"] == 0
    assert config["dropped_integer_overflow_rows"] == 0
    assert config["dropped_nonmonotonic_rows"] == 0
    assert config["dropped_nonpositive_strike_rows"] == 0
    assert config["dropped_negative_depth_rows"] == 0
    assert config["dropped_invalid_trade_rows"] == 0
    assert config["price_grid_validation_enabled"]
    assert config["price_grid_tick_size"] == pytest.approx(0.05)
    assert config["off_tick_price_rows"] == 0
    assert config["unique_source_files"] == 2
    assert config["source_file_fingerprint_coverage"] == 1.0
    assert config["min_mapping_coverage"] == 1.0
    assert config["unique_header_fingerprints"] == 1
    assert config["unique_mapping_drafts"] == 1
    assert config["comparison"]["accepted"]
    assert config["comparison"]["thresholds"]["min_datasets"] == 2
    assert config["comparison"]["thresholds"]["min_source_file_fingerprint_coverage"] == 1.0
    assert config["comparison"]["thresholds"]["min_mapping_coverage"] == 1.0
    assert len(config["datasets"]) == 2
    assert config["datasets"][0]["dropped_null_rows"] == 0
    assert config["datasets"][0]["dropped_nonfinite_rows"] == 0
    assert config["datasets"][0]["dropped_nonintegral_rows"] == 0
    assert config["datasets"][0]["dropped_duplicate_rows"] == 0
    assert config["datasets"][0]["dropped_integer_overflow_rows"] == 0
    assert config["datasets"][0]["dropped_nonmonotonic_rows"] == 0
    assert config["datasets"][0]["dropped_nonpositive_strike_rows"] == 0
    assert config["datasets"][0]["dropped_negative_depth_rows"] == 0
    assert config["datasets"][0]["dropped_invalid_trade_rows"] == 0
    assert config["datasets"][0]["price_grid_validation_enabled"]
    assert config["datasets"][0]["price_grid_tick_size"] == pytest.approx(0.05)
    assert config["datasets"][0]["off_tick_price_rows"] == 0
    assert config["datasets"][0]["data_readiness_manifest_path"].endswith("manifest.json")
    assert (out_dir / "datasets" / "day1" / "vendor_market_data_pipeline_summary.csv").exists()
    assert (out_dir / "comparison" / "data_readiness_comparison_summary.csv").exists()
    assert "vendor_market_data_batch_action_queue.csv" in artifact_paths
    assert "vendor_market_data_batch_runbook.md" in artifact_paths
    assert manifest["run_type"] == "vendor_market_data_batch_pipeline"

    ready_code = main(
        [
            "pipeline-vendor-market-data-batch",
            "--input",
            str(day1),
            str(day2),
            "--label",
            "cli_day1",
            "--label",
            "cli_day2",
            "--out",
            str(tmp_path / "batch_cli_ready"),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
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
            "--min-datasets",
            "2",
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert ready_code == 0
    cli_config = json.loads(
        (
            tmp_path
            / "batch_cli_ready"
            / "vendor_market_data_batch_config.json"
        ).read_text(encoding="utf-8")
    )
    assert cli_config["data_readiness_thresholds"]["max_null_rows"] == 2
    assert cli_config["data_readiness_thresholds"]["max_nonfinite_rows"] == 3
    assert cli_config["data_readiness_thresholds"]["max_nonintegral_rows"] == 4
    assert cli_config["data_readiness_thresholds"]["max_duplicate_tick_rows"] == 5
    assert cli_config["data_readiness_thresholds"]["max_integer_overflow_rows"] == 6
    assert cli_config["data_readiness_thresholds"]["max_nonmonotonic_rows"] == 7
    assert cli_config["data_readiness_thresholds"][
        "max_nonpositive_strike_rows"
    ] == 8


def test_vendor_market_data_batch_uses_distinct_target_applications(tmp_path):
    application_dirs, source_paths, scope_dir = target_mapping_application_batch(
        tmp_path,
        "batch_target",
        ["2026-07-15", "2026-07-16"],
    )
    out_dir = tmp_path / "target_application_batch"

    report = write_vendor_market_data_batch_pipeline(
        source_paths,
        output_dir=out_dir,
        labels=["day1", "day2"],
        mapping_application_dirs=application_dirs,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=1,
        ),
    )

    summary = report.summary.iloc[0]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads(
        (out_dir / "vendor_market_data_batch_config.json").read_text(
            encoding="utf-8"
        )
    )
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(
        encoding="utf-8"
    )
    assert report.ready
    assert summary["dataset_count"] == 2
    assert summary["mapping_sources"] == "verified_target_application"
    assert summary["mapping_application_count"] == 2
    assert summary["unique_mapping_applications"] == 2
    assert summary["target_application_coverage"] == 1.0
    assert report.datasets["mapping_application_id"].nunique() == 2
    assert set(report.datasets["mapping_application_path"]) == {
        str(path.resolve()) for path in application_dirs
    }
    assert report.datasets["mapping_scope_review_id"].nunique() == 1
    assert report.datasets["mapping_application_sha256"].str.len().eq(64).all()
    assert report.datasets["applied_mapping_sha256"].str.len().eq(64).all()
    assert "- Mapping applications: 2" in runbook
    assert "- Target-application coverage: 1.000" in runbook
    assert (
        "- Mapping source mode: per_dataset_verified_target_application"
        in runbook
    )
    assert "verified_target_application" in runbook
    assert all(
        len(manifest["inputs"][name]) == 2
        for name in (
            "mapping_applications",
            "mapping_application_manifests",
            "mapping_application_receipts",
            "mapping_scope_reviews",
            "target_intakes",
            "target_sources",
            "applied_mappings",
        )
    )
    assert manifest["parameters"]["mapping_source"] == (
        "per_dataset_verified_target_application"
    )
    assert manifest["parameters"]["readiness_thresholds"][
        "require_target_application_normalization"
    ]
    assert config["mapping_application_count"] == 2
    assert config["unique_mapping_applications"] == 2
    assert config["target_application_coverage"] == 1.0
    assert config["mapping_source_mode"] == (
        "per_dataset_verified_target_application"
    )
    assert config["data_readiness_thresholds"][
        "require_target_application_normalization"
    ]
    assert {item["mapping_application_id"] for item in config["datasets"]} == set(
        report.datasets["mapping_application_id"]
    )
    assert {item["mapping_scope_review_id"] for item in config["datasets"]} == {
        report.datasets.iloc[0]["mapping_scope_review_id"]
    }
    assert scope_dir.resolve() != out_dir.resolve()
    for label in ("day1", "day2"):
        readiness = pd.read_csv(
            out_dir
            / "datasets"
            / label
            / "04_data_readiness"
            / "data_readiness_summary.csv"
        ).iloc[0]
        assert bool(readiness["require_target_application_normalization"])
        assert bool(readiness["mapped_data_target_application_bound"])

    cli_out = tmp_path / "target_application_batch_cli"
    cli_args = [
        "pipeline-vendor-market-data-batch",
        "--input",
        *(str(path) for path in source_paths),
        "--label",
        "cli_day1",
        "--label",
        "cli_day2",
        "--out",
        str(cli_out),
    ]
    for application_dir in application_dirs:
        cli_args.extend(["--mapping-application", str(application_dir)])
    cli_args.extend(
        [
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-datasets",
            "2",
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert main(cli_args) == 0


def test_vendor_market_data_batch_rejects_invalid_application_alignment_before_output(
    tmp_path,
):
    application_dirs, source_paths, _ = target_mapping_application_batch(
        tmp_path,
        "batch_binding",
        ["2026-07-15", "2026-07-16"],
    )

    count_out = tmp_path / "batch_count_out"
    with pytest.raises(ValueError, match="one for one"):
        write_vendor_market_data_batch_pipeline(
            source_paths,
            output_dir=count_out,
            mapping_application_dirs=application_dirs[:1],
        )
    assert not count_out.exists()

    mutual_out = tmp_path / "batch_mutual_out"
    with pytest.raises(ValueError, match="mutually exclusive"):
        write_vendor_market_data_batch_pipeline(
            source_paths,
            output_dir=mutual_out,
            mapping_path=application_dirs[0] / "target_applied_vendor_mapping.csv",
            mapping_application_dirs=application_dirs,
        )
    assert not mutual_out.exists()

    swapped_out = tmp_path / "batch_swapped_out"
    with pytest.raises(ValueError, match="exact target source"):
        write_vendor_market_data_batch_pipeline(
            source_paths,
            output_dir=swapped_out,
            mapping_application_dirs=list(reversed(application_dirs)),
        )
    assert not swapped_out.exists()

    duplicate_out = tmp_path / "batch_duplicate_out"
    with pytest.raises(ValueError, match="distinct per dataset"):
        write_vendor_market_data_batch_pipeline(
            [source_paths[0], source_paths[0]],
            output_dir=duplicate_out,
            labels=["copy1", "copy2"],
            mapping_application_dirs=[application_dirs[0], application_dirs[0]],
        )
    assert not duplicate_out.exists()

    labels_out = tmp_path / "batch_labels_out"
    with pytest.raises(ValueError, match="unique dataset directories"):
        write_vendor_market_data_batch_pipeline(
            source_paths,
            output_dir=labels_out,
            labels=["day one", "day_one"],
            mapping_application_dirs=application_dirs,
        )
    assert not labels_out.exists()

    collision_out = application_dirs[0] / "batch"
    with pytest.raises(ValueError, match="cannot modify mapping-application evidence"):
        write_vendor_market_data_batch_pipeline(
            source_paths,
            output_dir=collision_out,
            mapping_application_dirs=application_dirs,
        )
    assert not collision_out.exists()


def test_vendor_market_data_batch_fails_when_inputs_reuse_same_source_file(tmp_path):
    day1 = tmp_path / "arrow_ticks_day1.csv"
    out_dir = tmp_path / "batch"
    vendor_ticks("2026-06-10").to_csv(day1, index=False)

    report = write_vendor_market_data_batch_pipeline(
        [day1, day1],
        output_dir=out_dir,
        labels=["day1", "day1_copy"],
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    checks = pd.read_csv(out_dir / "comparison" / "data_readiness_comparison_checks.csv")
    action_queue = pd.read_csv(out_dir / "vendor_market_data_batch_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "vendor_market_data_batch_config.json").read_text(encoding="utf-8"))
    summary = report.summary.iloc[0]
    assert not report.ready
    assert summary["ready_datasets"] == 2
    assert summary["unique_source_files"] == 1
    assert not summary["comparison_accepted"]
    assert summary["blocked_action_count"] > 0
    assert summary["next_gate"] == "pipeline-vendor-market-data-batch"
    assert summary["next_gate_help_command"] == "python -m hft_cli pipeline-vendor-market-data-batch --help"
    assert "unique_source_files" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "unique_source_files" in set(action_queue["check"])
    assert "pipeline-vendor-market-data-batch" in set(action_queue["next_gate"])
    assert config["blocked_action_count"] == len(action_queue)
    assert config["ready_action_count"] == 0
    assert config["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["next_gate_help_command"] == "python -m hft_cli pipeline-vendor-market-data-batch --help"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "unique_source_files"
    assert config["primary_action"]["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["ready_actions"] == []
    assert config["blocked_actions"][0]["check"] == "unique_source_files"
    assert config["blocked_actions"][0]["source"] == "comparison"
    assert config["blocked_actions"][0]["next_gate"] == "pipeline-vendor-market-data-batch"
    assert "# Vendor Market Data Batch Runbook" in runbook
    assert "- Ready: no" in runbook


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
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert set(diagnostics["scope"]) == {"overall", "expiry"}
    assert bool(pd.read_csv(out_dir / "04_data_readiness" / "data_readiness_summary.csv").loc[0, "ready"])


def test_vendor_market_data_pipeline_gates_nonmonotonic_option_chain_rows(tmp_path):
    timestamps = [
        "2026-06-10 09:15:01",
        "2026-06-10 09:15:00",
        "2026-06-10 09:15:00",
        "2026-06-10 09:15:01",
        "2026-06-10 09:15:02",
    ]
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": timestamp,
                "expiry_date": "2026-06-25",
                "strike_price": 22500 + offset * 50,
                "ce_bid": 100.0 + offset * 0.5,
                "ce_ask": 100.5 + offset * 0.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0 + offset * 0.5,
                "pe_ask": 90.5 + offset * 0.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
            for offset, timestamp in enumerate(timestamps)
        ]
    )
    raw_path = tmp_path / "irage_chain_nonmonotonic.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_chain_pipeline"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="irage",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )
    mapped_summary = blocked.mapped_data.summary.iloc[0]
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert blocked.mapped_data.ready
    assert list(blocked.mapped_data.data["ts"]) == [
        pd.Timestamp("2026-06-10 09:15:01", tz="Asia/Kolkata").value,
        pd.Timestamp("2026-06-10 09:15:01", tz="Asia/Kolkata").value,
        pd.Timestamp("2026-06-10 09:15:02", tz="Asia/Kolkata").value,
    ]
    assert int(mapped_summary["dropped_nonmonotonic_rows"]) == 2
    assert int(blocked.summary.loc[0, "dropped_nonmonotonic_rows"]) == 2
    assert "mapped_data_dropped_nonmonotonic_rows" in failed
    assert blocked_config["normalized"]["dropped_nonmonotonic_rows"] == 2
    assert "- Nonmonotonic chain rows: 2" in blocked_runbook

    allowed_dir = tmp_path / "allowed_chain_pipeline"
    allowed = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=allowed_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="irage",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
            max_nonmonotonic_rows=2,
        ),
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )

    assert allowed.ready
    assert int(allowed.summary.loc[0, "dropped_nonmonotonic_rows"]) == 2
    assert allowed_config["data_readiness"]["thresholds"][
        "max_nonmonotonic_rows"
    ] == 2


def test_vendor_market_data_pipeline_gates_nonpositive_option_strikes(tmp_path):
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": f"2026-06-10 09:15:0{offset}",
                "expiry_date": "2026-06-25",
                "strike_price": strike,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
            for offset, strike in enumerate((22500.0, 0.0, -50.0))
        ]
    )
    raw_path = tmp_path / "irage_chain_nonpositive_strikes.csv"
    raw.to_csv(raw_path, index=False)

    blocked_dir = tmp_path / "blocked_nonpositive_strikes"
    blocked = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=blocked_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="irage",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )
    failed = set(
        blocked.readiness.checks.loc[
            ~blocked.readiness.checks["passed"].astype(bool),
            "check",
        ]
    )
    blocked_config = json.loads(
        (blocked_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )
    blocked_runbook = (
        blocked_dir / "vendor_market_data_pipeline_runbook.md"
    ).read_text(encoding="utf-8")

    assert not blocked.ready
    assert list(blocked.mapped_data.data["strike"]) == [22500.0]
    assert int(
        blocked.mapped_data.summary.loc[
            0,
            "dropped_nonpositive_strike_rows",
        ]
    ) == 2
    assert int(blocked.summary.loc[0, "dropped_nonpositive_strike_rows"]) == 2
    assert "mapped_data_dropped_nonpositive_strike_rows" in failed
    assert (
        blocked_config["normalized"]["dropped_nonpositive_strike_rows"] == 2
    )
    assert "- Nonpositive strike rows: 2" in blocked_runbook

    allowed_dir = tmp_path / "allowed_nonpositive_strikes"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(allowed_dir),
            "--adapter",
            "irage",
            "--kind",
            "chain",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-nonpositive-strike-rows",
            "2",
            "--fail-on-breach",
        ]
    )
    allowed_config = json.loads(
        (allowed_dir / "vendor_market_data_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert allowed_config["ready"]
    assert allowed_config["normalized"]["dropped_nonpositive_strike_rows"] == 2
    assert allowed_config["data_readiness"]["thresholds"][
        "max_nonpositive_strike_rows"
    ] == 2


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
    action_queue = pd.read_csv(out_dir / "vendor_market_data_pipeline_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_pipeline_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "vendor_market_data_pipeline_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "blocked_action_count"] > 0
    assert str(summary.loc[0, "next_gate"])
    assert str(summary.loc[0, "next_gate_help_command"]).startswith("python -m hft_cli ")
    assert "not_ready" in set(components["status"])
    assert not action_queue.empty
    assert str(action_queue.loc[0, "next_gate_help_command"]).startswith("python -m hft_cli ")
    assert config["blocked_action_count"] == len(action_queue)
    assert config["ready_action_count"] == 0
    assert config["next_gate"] == summary.loc[0, "next_gate"]
    assert config["next_gate_help_command"] == summary.loc[0, "next_gate_help_command"]
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["next_gate"] == summary.loc[0, "next_gate"]
    assert config["primary_action"]["next_gate_help_command"] == summary.loc[0, "next_gate_help_command"]
    assert config["ready_actions"] == []
    assert config["blocked_actions"][0]["next_gate"] == summary.loc[0, "next_gate"]
    assert config["blocked_actions"][0]["next_gate_help_command"] == summary.loc[0, "next_gate_help_command"]
    assert "# Vendor Market Data Pipeline Runbook" in runbook
    assert "- Ready: no" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook
    assert (out_dir / "04_data_readiness" / "data_readiness_summary.csv").exists()

    for flag, folder_name in [
        ("--fail-on-blocked-actions", "pipeline_blocked_action_gate"),
        ("--fail-on-actions", "pipeline_any_action_gate"),
    ]:
        gated_code = main(
            [
                "pipeline-vendor-market-data",
                "--input",
                str(raw_path),
                "--out",
                str(tmp_path / folder_name),
                "--adapter",
                "arrow_money",
                "--kind",
                "ticks",
                "--timestamp-unit",
                "datetime",
                flag,
            ]
        )
        assert gated_code == 2


def test_cli_vendor_market_data_batch_fails_closed_when_comparison_threshold_misses(tmp_path):
    day1 = tmp_path / "arrow_ticks_day1.csv"
    out_dir = tmp_path / "batch"
    vendor_ticks("2026-06-10").to_csv(day1, index=False)

    code = main(
        [
            "pipeline-vendor-market-data-batch",
            "--input",
            str(day1),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-datasets",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "vendor_market_data_batch_summary.csv")
    checks = pd.read_csv(out_dir / "comparison" / "data_readiness_comparison_checks.csv")
    action_queue = pd.read_csv(out_dir / "vendor_market_data_batch_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "vendor_market_data_batch_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "blocked_action_count"] > 0
    assert summary.loc[0, "next_gate"] == "pipeline-vendor-market-data-batch"
    assert summary.loc[0, "next_gate_help_command"] == "python -m hft_cli pipeline-vendor-market-data-batch --help"
    assert "dataset_count" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "dataset_count" in set(action_queue["check"])
    assert config["blocked_action_count"] == len(action_queue)
    assert config["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "dataset_count"
    assert config["primary_action"]["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["blocked_actions"][0]["check"] == "dataset_count"
    assert config["blocked_actions"][0]["next_gate_help_command"] == (
        "python -m hft_cli pipeline-vendor-market-data-batch --help"
    )
    assert "# Vendor Market Data Batch Runbook" in runbook
    assert "- Ready: no" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook

    for flag, folder_name in [
        ("--fail-on-blocked-actions", "batch_blocked_action_gate"),
        ("--fail-on-actions", "batch_any_action_gate"),
    ]:
        gated_code = main(
            [
                "pipeline-vendor-market-data-batch",
                "--input",
                str(day1),
                "--out",
                str(tmp_path / folder_name),
                "--adapter",
                "arrow_money",
                "--kind",
                "ticks",
                "--timestamp-unit",
                "datetime",
                "--tick-size",
                "0.05",
                "--min-datasets",
                "2",
                flag,
            ]
        )
        assert gated_code == 2
