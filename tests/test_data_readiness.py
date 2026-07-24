import json

import pandas as pd

from hft_cli import main
from reports.data_readiness import (
    DATA_READINESS_REQUIRED_ARTIFACTS,
    DATA_READINESS_RUN_TYPE,
    DataReadinessThresholds,
    evaluate_data_readiness,
    verify_data_readiness_report,
    write_data_readiness_report,
)
from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.market_portability import (
    MarketPortabilityReportConfig,
    build_market_portability_report,
    write_market_portability_report,
)
from reports.market_calendar import write_market_calendar_report


def tick_summary(**overrides):
    row = {
        "rows": 100,
        "start_ts": 1_000,
        "end_ts": 2_000,
        "nonmonotonic_rows": 0,
        "crossed_quote_rows": 0,
        "nonpositive_quote_rows": 0,
        "nonpositive_depth_rows": 0,
        "out_of_session_rows": 0,
        "median_gap_ns": 1_000.0,
        "p99_gap_ns": 2_000.0,
        "median_spread_ticks": 1.0,
        "scope": "overall",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def chain_summary(**overrides):
    overall = {
        "rows": 200,
        "expiries": 2,
        "strikes": 20,
        "expiry_snapshots": 20,
        "min_snapshots_per_expiry": 10,
        "min_snapshot_strikes": 10,
        "p99_snapshot_gap_ns": 2_000.0,
        "crossed_quote_rows": 0,
        "nonpositive_quote_rows": 0,
        "nonpositive_depth_rows": 0,
        "out_of_session_rows": 0,
        "scope": "overall",
    }
    overall.update(overrides)
    expiry = {
        "rows": 100,
        "strikes": 10,
        "median_call_spread_ticks": 2.0,
        "median_put_spread_ticks": 2.5,
        "scope": "expiry",
    }
    return pd.DataFrame([overall, expiry])


def schema_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "adapter": "arrow_money",
                "kind": "ticks",
                "all_required_present": ready,
                "missing_required_columns": 0 if ready else 1,
            }
        ]
    )


def mapped_data_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": "arrow_money",
                "kind": "ticks",
                "input_rows": 100,
                "output_rows": 100 if ready else 0,
                "failed_mappings": 0 if ready else 1,
                "quarantined_rows": 0,
                "dropped_null_rows": 0,
                "dropped_nonfinite_rows": 0,
                "dropped_nonintegral_rows": 0,
                "dropped_duplicate_rows": 0,
                "dropped_crossed_quote_rows": 0,
                "dropped_nonpositive_quote_rows": 0,
                "dropped_nonmonotonic_rows": 0,
                "dropped_negative_depth_rows": 0,
                "dropped_non_trading_day_rows": 0,
                "dropped_out_of_session_rows": 0,
            }
        ]
    )


def reviewed_mapped_data_summary(ready=True):
    summary = mapped_data_summary(ready)
    summary["review_bound"] = True
    summary["mapping_review_verified"] = True
    summary["mapping_review_approved"] = True
    summary["mapping_review_id"] = "mapping-review-123"
    summary["mapping_review_sha256"] = "a" * 64
    summary["source_file_sha256"] = "b" * 64
    summary["reviewed_mapping_sha256"] = "c" * 64
    summary["operator_approved_mapping_required"] = True
    summary["reviewed_normalization_only"] = True
    summary["authorizes_strategy_research"] = False
    summary["authorizes_routing"] = False
    summary["authorizes_submission"] = False
    return summary


def vendor_intake_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": "arrow_money",
                "best_kind": "ticks",
                "sampled_rows": 100,
                "source_columns": 7,
                "required_columns": 7,
                "mapped_columns": 7 if ready else 6,
                "unmapped_required_columns": 0 if ready else 1,
                "mapping_coverage": 1.0 if ready else 6 / 7,
                "recommendation": "review_mapping_then_normalize" if ready else "complete_vendor_mapping_before_research",
            }
        ]
    )


def market_profile_summary(explicit_fee_model=True):
    return pd.DataFrame(
        [
            {
                "markets": 1,
                "countries": 1,
                "currencies": 1,
                "cost_examples": 1 if explicit_fee_model else 0,
                "explicit_fee_model": explicit_fee_model,
            }
        ]
    )


def instrument_metadata_summary(passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "instruments": 2,
                "parsed_instruments": 2 if passed else 1,
                "unparsed_instruments": 0 if passed else 1,
                "parse_coverage": 1.0 if passed else 0.5,
            }
        ]
    )


def market_calendar_summary(**overrides):
    row = {
        "ready": True,
        "market": "india_nse_index_derivatives",
        "market_calendar_provided": True,
        "market_calendar_policy": "versioned_exchange_calendar_v1",
        "market_calendar_id": "nse-fo-test-2026-06",
        "market_calendar_sha256": "e" * 64,
        "market_calendar_valid_from": "2026-06-01",
        "market_calendar_valid_to": "2026-06-30",
        "failed_checks": 0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def market_calendar_path(tmp_path):
    path = tmp_path / "nse_calendar.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calendar_id": "nse-fo-test-2026-06",
                "market": "india_nse_index_derivatives",
                "timezone": "Asia/Kolkata",
                "valid_from": "2026-06-01",
                "valid_to": "2026-06-30",
                "provenance": {
                    "publisher": "test-exchange",
                    "source_url": "https://example.test/calendar",
                    "published_date": "2026-05-01",
                },
                "sessions": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def calendar_bound(frame, **overrides):
    result = frame.copy()
    values = market_calendar_summary(**overrides).iloc[0]
    for column in (
        "market",
        "market_calendar_provided",
        "market_calendar_policy",
        "market_calendar_id",
        "market_calendar_sha256",
        "market_calendar_valid_from",
        "market_calendar_valid_to",
    ):
        result[column] = values[column]
    return result


def calendar_report_bound(frame, calendar):
    result = frame.copy()
    values = calendar.iloc[0]
    for column in (
        "market",
        "market_calendar_provided",
        "market_calendar_policy",
        "market_calendar_id",
        "market_calendar_sha256",
        "market_calendar_valid_from",
        "market_calendar_valid_to",
    ):
        result[column] = values[column]
    return result


def reseal_data_readiness_report(path):
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    write_experiment_manifest(
        path,
        run_type=manifest["run_type"],
        parameters=manifest["parameters"],
        inputs={
            name: value["path"]
            for name, value in manifest["inputs"].items()
        },
        extra=manifest["extra"],
    )


def test_data_readiness_accepts_clean_tick_diagnostics():
    report = evaluate_data_readiness(tick_diagnostic_summary=tick_summary())

    assert report.ready
    assert report.summary.iloc[0]["recommendation"] == "feed_strategy_research"
    assert set(report.checks["passed"]) == {True}


def test_data_readiness_requires_and_binds_market_calendar_evidence():
    report = evaluate_data_readiness(
        market_calendar_summary=market_calendar_summary(),
        mapped_data_summary=calendar_bound(mapped_data_summary()),
        tick_diagnostic_summary=calendar_bound(tick_summary()),
        thresholds=DataReadinessThresholds(
            require_market_calendar=True,
            require_mapped_data=True,
            expected_market="india_nse_index_derivatives",
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert summary["market_calendar_id"] == "nse-fo-test-2026-06"
    assert summary["market_calendar_sha256"] == "e" * 64
    assert summary["market_calendar_binding_components"] == (
        "mapped_data;tick_diagnostics"
    )
    assert int(summary["market_calendar_binding_count"]) == 2
    assert set(report.checks["passed"]) == {True}


def test_data_readiness_rejects_calendar_fingerprint_drift():
    report = evaluate_data_readiness(
        market_calendar_summary=market_calendar_summary(),
        mapped_data_summary=calendar_bound(mapped_data_summary()),
        tick_diagnostic_summary=calendar_bound(
            tick_summary(),
            market_calendar_sha256="f" * 64,
        ),
        thresholds=DataReadinessThresholds(
            require_market_calendar=True,
            require_mapped_data=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert "tick_diagnostics_market_calendar_sha256_matches" in failed
    assert report.action_queue is not None
    action = report.action_queue.set_index("check").loc[
        "tick_diagnostics_market_calendar_sha256_matches"
    ]
    assert action["next_gate"] == "diagnose-ticks"


def test_data_readiness_routes_missing_calendar_to_calendar_report():
    report = evaluate_data_readiness(
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(require_market_calendar=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert "market_calendar_provided" in failed
    assert "tick_diagnostics_market_calendar_provided" in failed
    assert report.summary.loc[0, "next_gate"] == "market-calendar-report"


def test_cli_data_readiness_requires_calendar_report_and_bindings(tmp_path):
    calendar_dir = tmp_path / "calendar"
    mapped_dir = tmp_path / "mapped"
    diagnostics_dir = tmp_path / "diagnostics"
    out_dir = tmp_path / "readiness"
    mapped_dir.mkdir()
    diagnostics_dir.mkdir()
    write_market_calendar_report(
        market_calendar_path(tmp_path),
        calendar_dir,
        expected_market="india_nse_index_derivatives",
    )
    calendar = pd.read_csv(calendar_dir / "market_calendar_summary.csv")
    calendar_report_bound(mapped_data_summary(), calendar).to_csv(
        mapped_dir / "mapped_data_summary.csv",
        index=False,
    )
    calendar_report_bound(tick_summary(), calendar).to_csv(
        diagnostics_dir / "diagnostic_summary.csv",
        index=False,
    )

    code = main(
        [
            "review-data-readiness",
            "--out",
            str(out_dir),
            "--market-calendar-report",
            str(calendar_dir),
            "--mapped-data",
            str(mapped_dir),
            "--tick-diagnostics",
            str(diagnostics_dir),
            "--require-market-calendar",
            "--require-mapped-data",
            "--max-null-rows",
            "2",
            "--max-nonfinite-rows",
            "3",
            "--max-nonintegral-rows",
            "4",
            "--max-duplicate-tick-rows",
            "5",
            "--fail-on-breach",
        ]
    )

    assert code == 0
    config = json.loads(
        (out_dir / "data_readiness_config.json").read_text(encoding="utf-8")
    )
    assert config["market_calendar"]["required"] is True
    assert config["market_calendar"]["binding_count"] == 2
    assert config["market_calendar"]["report_verified"] is True
    assert config["thresholds"]["max_null_rows"] == 2
    assert config["thresholds"]["max_nonfinite_rows"] == 3
    assert config["thresholds"]["max_nonintegral_rows"] == 4
    assert config["thresholds"]["max_duplicate_tick_rows"] == 5


def test_data_readiness_rejects_loose_market_calendar_summary(tmp_path):
    calendar_dir = tmp_path / "loose_calendar"
    calendar_dir.mkdir()
    market_calendar_summary().to_csv(
        calendar_dir / "market_calendar_summary.csv",
        index=False,
    )

    report = write_data_readiness_report(
        output_dir=tmp_path / "readiness",
        market_calendar_dir=calendar_dir,
        thresholds=DataReadinessThresholds(
            require_market_calendar=True,
            require_tick_diagnostics=False,
        ),
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert "market_calendar_report_verified" in failed
    assert "market_calendar_report_manifest_current" in failed
    assert (
        report.summary.loc[0, "market_calendar_report_verification_error"]
        == "manifest_missing"
    )
    assert report.summary.loc[0, "next_gate"] == "market-calendar-report"


def test_data_readiness_fails_on_bad_tick_diagnostics():
    report = evaluate_data_readiness(
        tick_diagnostic_summary=tick_summary(crossed_quote_rows=1, out_of_session_rows=1),
        thresholds=DataReadinessThresholds(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"tick_crossed_quote_rows", "tick_out_of_session_rows"} <= failed
    assert report.action_queue is not None
    queue = report.action_queue.set_index("check")
    assert queue.loc["tick_crossed_quote_rows", "next_gate"] == "diagnose-ticks"
    assert queue.loc["tick_crossed_quote_rows", "next_gate_help_command"] == "python -m hft_cli diagnose-ticks --help"
    assert report.summary.loc[0, "next_gate"] == "diagnose-ticks"


def test_data_readiness_fails_on_filtered_mapped_data_quarantine():
    mapped = mapped_data_summary()
    mapped.loc[0, "dropped_null_rows"] = 1
    mapped.loc[0, "dropped_nonfinite_rows"] = 1
    mapped.loc[0, "dropped_nonintegral_rows"] = 1
    mapped.loc[0, "dropped_duplicate_rows"] = 1
    mapped.loc[0, "dropped_non_trading_day_rows"] = 1
    mapped.loc[0, "dropped_out_of_session_rows"] = 1

    report = evaluate_data_readiness(
        mapped_data_summary=mapped,
        tick_diagnostic_summary=tick_summary(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {
        "mapped_data_dropped_null_rows",
        "mapped_data_dropped_nonfinite_rows",
        "mapped_data_dropped_nonintegral_rows",
        "mapped_data_dropped_duplicate_tick_rows",
        "mapped_data_dropped_non_trading_day_rows",
        "mapped_data_dropped_out_of_session_rows",
    } <= failed
    assert report.summary.loc[0, "next_gate"] == "normalize-mapped-data"


def test_data_readiness_can_require_vendor_fee_and_metadata_evidence():
    report = evaluate_data_readiness(
        vendor_intake_summary=vendor_intake_summary(True),
        schema_audit_summary=schema_summary(True),
        mapped_data_summary=mapped_data_summary(True),
        tick_diagnostic_summary=tick_summary(),
        chain_diagnostic_summary=chain_summary(),
        market_profile_summary=market_profile_summary(True),
        instrument_metadata_summary=instrument_metadata_summary(True),
        thresholds=DataReadinessThresholds(
            require_vendor_intake=True,
            require_schema_audit=True,
            require_mapped_data=True,
            require_chain_diagnostics=True,
            require_market_profile=True,
            require_explicit_fee_model=True,
            require_instrument_metadata=True,
            max_chain_median_spread_ticks=3.0,
        ),
    )

    assert report.ready
    assert int(report.summary.iloc[0]["required_components"]) == 7
    assert report.items.set_index("component").loc["vendor_intake", "ready"]


def test_data_readiness_accepts_review_bound_mapping_normalization():
    report = evaluate_data_readiness(
        mapped_data_summary=reviewed_mapped_data_summary(),
        thresholds=DataReadinessThresholds(
            require_reviewed_mapping_normalization=True,
            require_tick_diagnostics=False,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(summary["require_reviewed_mapping_normalization"])
    assert bool(summary["mapped_data_review_bound"])
    assert bool(summary["mapped_data_mapping_review_verified"])
    assert bool(summary["mapped_data_mapping_review_approved"])
    assert summary["mapped_data_mapping_review_id"] == "mapping-review-123"
    assert summary["mapped_data_mapping_review_sha256"] == "a" * 64
    assert summary["mapped_data_source_file_sha256"] == "b" * 64
    assert summary["mapped_data_reviewed_mapping_sha256"] == "c" * 64
    assert report.action_queue is not None
    assert report.action_queue.empty


def test_data_readiness_rejects_loose_normalization_when_review_is_required():
    report = evaluate_data_readiness(
        mapped_data_summary=mapped_data_summary(),
        thresholds=DataReadinessThresholds(
            require_reviewed_mapping_normalization=True,
            require_tick_diagnostics=False,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "mapped_data_review_bound",
        "mapped_data_mapping_review_verified",
        "mapped_data_mapping_review_approved",
        "mapped_data_mapping_review_id_present",
        "mapped_data_reviewed_mapping_sha256_present",
    } <= failed
    assert report.action_queue is not None
    assert set(report.action_queue["next_gate"]) == {"normalize-reviewed-mapped-data"}
    assert set(report.action_queue["next_gate_help_command"]) == {
        "python -m hft_cli normalize-reviewed-mapped-data --help"
    }


def test_data_readiness_routes_missing_strict_mapping_evidence_to_reviewed_normalization():
    report = evaluate_data_readiness(
        thresholds=DataReadinessThresholds(
            require_reviewed_mapping_normalization=True,
            require_tick_diagnostics=False,
        ),
    )

    assert not report.ready
    assert report.action_queue is not None
    assert report.summary.loc[0, "next_gate"] == "normalize-reviewed-mapped-data"
    assert set(report.action_queue["next_gate"]) == {"normalize-reviewed-mapped-data"}
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "mapped_data_reviewed_normalization_provided" in failed


def test_data_readiness_rejects_invalid_safety_claims_and_source_mismatch():
    mapped = reviewed_mapped_data_summary()
    mapped["authorizes_routing"] = pd.Series(["unknown"], dtype=object)
    intake = vendor_intake_summary()
    intake.loc[0, "source_file_sha256"] = "d" * 64

    report = evaluate_data_readiness(
        vendor_intake_summary=intake,
        mapped_data_summary=mapped,
        thresholds=DataReadinessThresholds(
            require_vendor_intake=True,
            require_reviewed_mapping_normalization=True,
            require_tick_diagnostics=False,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "mapped_data_authorizes_routing",
        "mapped_data_vendor_source_consistency",
    } <= failed
    assert report.action_queue is not None
    assert set(report.action_queue["next_gate"]) == {"normalize-reviewed-mapped-data"}


def test_data_readiness_can_require_market_portability_pair():
    portability = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("microprice_imbalance",),
            explicit_fee_model=True,
        )
    )

    report = evaluate_data_readiness(
        tick_diagnostic_summary=tick_summary(),
        market_portability_config=portability.config,
        thresholds=DataReadinessThresholds(
            require_market_portability=True,
            expected_strategy="microprice_imbalance",
            expected_market="us_equities_regular",
        ),
    )

    checks = report.checks.set_index("check")
    items = report.items.set_index("component")
    assert report.ready
    assert bool(items.loc["market_portability", "ready"])
    assert bool(checks.loc["market_portability_pair_ready", "passed"])
    assert report.summary.loc[0, "expected_market"] == "us_equities_regular"


def test_data_readiness_fails_on_unready_vendor_intake():
    report = evaluate_data_readiness(
        vendor_intake_summary=vendor_intake_summary(False),
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(require_vendor_intake=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    item = report.items.set_index("component").loc["vendor_intake"]
    summary = report.summary.iloc[0]
    assert "vendor_intake_ready" in failed
    assert int(item["failed_checks"]) == 1
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "vendor_intake_ready"
    assert summary["first_failed_reason"] == "vendor_intake is not ready"
    assert summary["primary_blocker_check"] == "vendor_intake_ready"
    assert summary["primary_blocker_value"] == "False"
    assert summary["primary_blocker_operator"] == "is"
    assert summary["primary_blocker_threshold"] == "True"
    assert summary["primary_blocker_reason"] == "vendor_intake is not ready"


def test_data_readiness_exposes_ambiguous_vendor_intake_kind():
    ambiguous_intake = vendor_intake_summary(False)
    ambiguous_intake.loc[0, "unmapped_required_columns"] = 0
    ambiguous_intake.loc[0, "kind_selection"] = "ambiguous"
    ambiguous_intake.loc[0, "selected_kind_ambiguous"] = True
    ambiguous_intake.loc[0, "ambiguous_kinds"] = "orders;fills"
    ambiguous_intake.loc[0, "recommendation"] = "set_vendor_kind_explicitly_before_normalizing"

    report = evaluate_data_readiness(
        vendor_intake_summary=ambiguous_intake,
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(require_vendor_intake=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    item = report.items.set_index("component").loc["vendor_intake"]
    summary = report.summary.iloc[0]
    assert not report.ready
    assert {"vendor_intake_ready", "vendor_intake_kind_unambiguous"} <= failed
    assert int(item["failed_checks"]) == 1
    assert item["kind_selection"] == "ambiguous"
    assert bool(item["selected_kind_ambiguous"])
    assert item["ambiguous_kinds"] == "orders;fills"
    assert item["recommendation"] == "set_vendor_kind_explicitly"
    assert bool(summary["vendor_intake_selected_kind_ambiguous"])
    assert summary["vendor_intake_ambiguous_kinds"] == "orders;fills"
    assert report.action_queue is not None
    queue = report.action_queue.set_index("check")
    assert queue.loc["vendor_intake_kind_unambiguous", "next_gate"] == "intake-vendor-csv"
    assert queue.loc["vendor_intake_kind_unambiguous", "recommendation"] == "set_vendor_kind_explicitly"


def test_data_readiness_carries_vendor_intake_fingerprints():
    intake = vendor_intake_summary(True)
    intake.loc[0, "source_file_sha256"] = "a" * 64
    intake.loc[0, "source_file_size_bytes"] = 1234
    intake.loc[0, "source_header_sha256"] = "b" * 64
    intake.loc[0, "mapping_draft_sha256"] = "c" * 64
    intake.loc[0, "mapping_coverage"] = 0.99

    report = evaluate_data_readiness(
        vendor_intake_summary=intake,
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(require_vendor_intake=True),
    )

    item = report.items.set_index("component").loc["vendor_intake"]
    summary = report.summary.iloc[0]
    assert report.ready
    assert item["source_file_sha256"] == "a" * 64
    assert int(item["source_file_size_bytes"]) == 1234
    assert item["source_header_sha256"] == "b" * 64
    assert item["mapping_draft_sha256"] == "c" * 64
    assert item["mapping_coverage"] == 0.99
    assert summary["vendor_intake_source_file_sha256"] == "a" * 64
    assert int(summary["vendor_intake_source_file_size_bytes"]) == 1234
    assert summary["vendor_intake_source_header_sha256"] == "b" * 64
    assert summary["vendor_intake_mapping_draft_sha256"] == "c" * 64
    assert summary["vendor_intake_mapping_coverage"] == 0.99


def test_data_readiness_blocks_mismatched_vendor_intake_kind():
    fill_intake = vendor_intake_summary(True)
    fill_intake.loc[0, "best_kind"] = "fills"

    report = evaluate_data_readiness(
        vendor_intake_summary=fill_intake,
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(
            require_vendor_intake=True,
            expected_vendor_data_kind="ticks",
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "vendor_intake_kind_matches" in failed
    assert summary["expected_vendor_data_kind"] == "ticks"
    assert summary["vendor_intake_kind"] == "fills"


def test_data_readiness_blocks_mixed_vendor_adapters():
    intake = vendor_intake_summary(True)
    mapped = mapped_data_summary(True)
    mapped.loc[0, "adapter"] = "irage"

    report = evaluate_data_readiness(
        vendor_intake_summary=intake,
        mapped_data_summary=mapped,
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(
            require_vendor_intake=True,
            require_mapped_data=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "data_adapter_consistency" in failed
    assert summary["data_adapters"] == "arrow_money;irage"
    assert int(summary["data_adapter_count"]) == 2


def test_data_readiness_blocks_mixed_data_kinds():
    intake = vendor_intake_summary(True)
    mapped = mapped_data_summary(True)
    mapped.loc[0, "kind"] = "chain"

    report = evaluate_data_readiness(
        vendor_intake_summary=intake,
        mapped_data_summary=mapped,
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(
            require_vendor_intake=True,
            require_mapped_data=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "data_kind_consistency" in failed
    assert summary["data_kinds"] == "chain;ticks"
    assert int(summary["data_kind_count"]) == 2


def test_data_readiness_checks_expected_kind_for_mapped_data():
    mapped = mapped_data_summary(True)
    mapped.loc[0, "kind"] = "fills"

    report = evaluate_data_readiness(
        mapped_data_summary=mapped,
        tick_diagnostic_summary=tick_summary(),
        thresholds=DataReadinessThresholds(
            require_mapped_data=True,
            expected_vendor_data_kind="ticks",
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "mapped_data_kind_matches" in failed
    assert summary["expected_vendor_data_kind"] == "ticks"
    assert summary["data_kinds"] == "fills"


def test_data_readiness_blocks_nonportable_expected_pair():
    portability = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("microprice_imbalance",),
        )
    )

    report = evaluate_data_readiness(
        tick_diagnostic_summary=tick_summary(),
        market_portability_config=portability.config,
        thresholds=DataReadinessThresholds(
            require_market_portability=True,
            expected_strategy="microprice_imbalance",
            expected_market="us_equities_regular",
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    item = report.items.set_index("component").loc["market_portability"]
    assert not report.ready
    assert {"market_portability_ready", "market_portability_pair_ready"} <= failed
    assert int(item["failed_checks"]) == 1
    assert report.action_queue is not None
    queue = report.action_queue.set_index("check")
    assert queue.loc["market_portability_pair_ready", "next_gate"] == "market-portability-report"
    assert queue.loc["market_portability_pair_ready", "next_gate_help_command"] == (
        "python -m hft_cli market-portability-report --help"
    )


def test_data_readiness_fails_on_chain_coverage_and_spread_gaps():
    report = evaluate_data_readiness(
        tick_diagnostic_summary=tick_summary(),
        chain_diagnostic_summary=chain_summary(expiries=0, strikes=0),
        thresholds=DataReadinessThresholds(
            require_chain_diagnostics=True,
            min_chain_expiries=1,
            min_chain_strikes=1,
            max_chain_median_spread_ticks=1.0,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"chain_expiries", "chain_strikes", "chain_median_spread_ticks"} <= failed


def test_write_data_readiness_outputs_artifacts(tmp_path):
    tick_dir = tmp_path / "tick_diag"
    out_dir = tmp_path / "data_readiness"
    blocked_gate_dir = tmp_path / "data_readiness_blocked_gate"
    action_gate_dir = tmp_path / "data_readiness_action_gate"
    tick_dir.mkdir()
    tick_summary().to_csv(tick_dir / "diagnostic_summary.csv", index=False)

    report = write_data_readiness_report(output_dir=out_dir, tick_diagnostics_dir=tick_dir)

    assert report.ready
    assert report.output_dir == out_dir
    assert (out_dir / "data_readiness_items.csv").exists()
    assert (out_dir / "data_readiness_checks.csv").exists()
    assert (out_dir / "data_readiness_summary.csv").exists()
    assert (out_dir / "data_readiness_action_queue.csv").exists()
    assert (out_dir / "data_readiness_config.json").exists()
    assert (out_dir / "data_readiness_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "data_readiness_action_queue.csv")
    config = json.loads((out_dir / "data_readiness_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "data_readiness_runbook.md").read_text(encoding="utf-8")
    saved_summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert int(saved_summary.loc[0, "failed_check_count"]) == 0
    assert pd.isna(saved_summary.loc[0, "primary_blocker_check"])
    assert config["ready"]
    assert config["non_authorizing"]
    assert not config["authorizes_routing"]
    assert not config["authorizes_submission"]
    assert config["component_counts"]["failed_checks"] == 0
    assert config["failed_check_count"] == 0
    assert config["failed_checks"] == []
    assert config["first_failed_reason"] == ""
    assert config["primary_blocker"] == {}
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert "# Data Readiness Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "- Non-authorizing: yes" in runbook
    assert "- Authorizes routing: no" in runbook
    assert "- Authorizes submission: no" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "data_readiness_action_queue.csv" in artifact_paths
    assert "data_readiness_config.json" in artifact_paths
    assert "data_readiness_runbook.md" in artifact_paths
    verification = verify_data_readiness_report(out_dir)
    assert verification.verified
    assert verification.ready
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert (
        main(
            [
                "verify-data-readiness-report",
                "--report",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )

    blocked_gate_code = main(
        [
            "review-data-readiness",
            "--out",
            str(blocked_gate_dir),
            "--tick-diagnostics",
            str(tick_dir),
            "--fail-on-blocked-actions",
        ]
    )
    action_gate_code = main(
        [
            "review-data-readiness",
            "--out",
            str(action_gate_dir),
            "--tick-diagnostics",
            str(tick_dir),
            "--fail-on-actions",
        ]
    )
    assert blocked_gate_code == 0
    assert action_gate_code == 0


def test_data_readiness_verifier_rejects_resealed_semantic_tamper(
    tmp_path,
):
    tick_dir = tmp_path / "tick_diag"
    out_dir = tmp_path / "data_readiness"
    tick_dir.mkdir()
    tick_summary().to_csv(
        tick_dir / "diagnostic_summary.csv",
        index=False,
    )
    write_data_readiness_report(
        output_dir=out_dir,
        tick_diagnostics_dir=tick_dir,
    )
    manifest_path = out_dir / "manifest.json"
    summary_path = out_dir / "data_readiness_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "authorizes_routing"] = True
    summary.to_csv(summary_path, index=False)
    reseal_data_readiness_report(out_dir)

    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_RUN_TYPE,
        required_artifacts=DATA_READINESS_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    verification = verify_data_readiness_report(out_dir)

    assert integrity.passed
    assert verification.manifest_current
    assert verification.inputs_current
    assert not verification.artifacts_consistent
    assert not verification.non_authorizing
    assert not verification.verified
    assert verification.error == (
        "data-readiness artifacts do not reconstruct from inputs"
    )
    assert (
        main(
            [
                "verify-data-readiness-report",
                "--report",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_data_readiness_verifier_rejects_resealed_extra_artifact(
    tmp_path,
):
    tick_dir = tmp_path / "tick_diag"
    out_dir = tmp_path / "data_readiness"
    tick_dir.mkdir()
    tick_summary().to_csv(
        tick_dir / "diagnostic_summary.csv",
        index=False,
    )
    write_data_readiness_report(
        output_dir=out_dir,
        tick_diagnostics_dir=tick_dir,
    )
    (out_dir / "unexpected_order_payload.csv").write_text(
        "instrument_id,side,qty\nNIFTY_TEST,BUY,1\n",
        encoding="utf-8",
    )
    reseal_data_readiness_report(out_dir)

    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type=DATA_READINESS_RUN_TYPE,
        required_artifacts=DATA_READINESS_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    verification = verify_data_readiness_report(out_dir)

    assert integrity.passed
    assert integrity.artifact_count == 7
    assert verification.manifest_current
    assert not verification.artifacts_consistent
    assert not verification.verified


def test_cli_data_readiness_can_fail_on_missing_required_tick_diagnostics(tmp_path):
    out_dir = tmp_path / "data_readiness"
    blocked_gate_dir = tmp_path / "data_readiness_blocked_gate"
    action_gate_dir = tmp_path / "data_readiness_action_gate"

    code = main(["review-data-readiness", "--out", str(out_dir), "--fail-on-breach"])

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_checks.csv")
    queue = pd.read_csv(out_dir / "data_readiness_action_queue.csv")
    config = json.loads((out_dir / "data_readiness_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "data_readiness_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "next_gate"] == "diagnose-ticks"
    assert summary.loc[0, "next_gate_help_command"] == "python -m hft_cli diagnose-ticks --help"
    assert "tick_diagnostics_provided" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "failed_check_count"]) == 2
    assert summary.loc[0, "failed_check_names"] == "tick_diagnostics_provided;tick_diagnostics_ready"
    assert summary.loc[0, "first_failed_reason"] == "tick_diagnostics summary is required but missing"
    assert summary.loc[0, "primary_blocker_check"] == "tick_diagnostics_provided"
    assert not bool(summary.loc[0, "primary_blocker_value"])
    assert summary.loc[0, "primary_blocker_operator"] == "is"
    assert bool(summary.loc[0, "primary_blocker_threshold"])
    assert summary.loc[0, "primary_blocker_reason"] == "tick_diagnostics summary is required but missing"
    assert not config["ready"]
    assert config["failed_check_count"] == 2
    assert config["failed_checks"] == ["tick_diagnostics_provided", "tick_diagnostics_ready"]
    assert config["first_failed_reason"] == "tick_diagnostics summary is required but missing"
    assert config["primary_blocker"]["check"] == "tick_diagnostics_provided"
    assert config["primary_blocker"]["operator"] == "is"
    assert config["primary_blocker"]["threshold"] is True
    assert config["primary_blocker"]["reason"] == "tick_diagnostics summary is required but missing"
    assert config["blocked_action_count"] == len(queue)
    assert config["ready_action_count"] == 0
    assert config["next_gate"] == queue.loc[0, "next_gate"]
    assert config["next_gate_help_command"] == queue.loc[0, "next_gate_help_command"]
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == queue.loc[0, "check"]
    assert config["primary_action"]["next_gate"] == "diagnose-ticks"
    assert config["ready_actions"] == []
    assert {item["check"] for item in config["next_actions"]} == set(queue["check"])
    assert {item["check"] for item in config["blocked_actions"]} == set(queue["check"])
    assert queue.loc[0, "next_gate"] == "diagnose-ticks"
    assert "`diagnose-ticks`" in runbook

    blocked_gate_code = main(
        [
            "review-data-readiness",
            "--out",
            str(blocked_gate_dir),
            "--fail-on-blocked-actions",
        ]
    )
    action_gate_code = main(
        [
            "review-data-readiness",
            "--out",
            str(action_gate_dir),
            "--fail-on-actions",
        ]
    )
    assert blocked_gate_code == 2
    assert action_gate_code == 2


def test_cli_data_readiness_can_require_vendor_intake(tmp_path):
    tick_dir = tmp_path / "tick_diag"
    out_dir = tmp_path / "data_readiness"
    tick_dir.mkdir()
    tick_summary().to_csv(tick_dir / "diagnostic_summary.csv", index=False)

    code = main(
        [
            "review-data-readiness",
            "--out",
            str(out_dir),
            "--tick-diagnostics",
            str(tick_dir),
            "--require-vendor-intake",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_checks.csv")
    queue = pd.read_csv(out_dir / "data_readiness_action_queue.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "vendor_intake_provided" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "intake-vendor-csv" in set(queue["next_gate"])


def test_cli_data_readiness_can_require_review_bound_normalization(tmp_path):
    mapped_dir = tmp_path / "reviewed_mapped_data"
    out_dir = tmp_path / "reviewed_data_readiness"
    mapped_dir.mkdir()
    reviewed_mapped_data_summary().to_csv(
        mapped_dir / "mapped_data_summary.csv",
        index=False,
    )

    code = main(
        [
            "review-data-readiness",
            "--out",
            str(out_dir),
            "--mapped-data",
            str(mapped_dir),
            "--require-reviewed-mapping-normalization",
            "--skip-tick-diagnostics",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "require_reviewed_mapping_normalization"])
    assert bool(summary.loc[0, "mapped_data_review_bound"])


def test_cli_data_readiness_can_require_vendor_intake_kind(tmp_path):
    tick_dir = tmp_path / "tick_diag"
    intake_dir = tmp_path / "intake"
    out_dir = tmp_path / "data_readiness"
    tick_dir.mkdir()
    intake_dir.mkdir()
    tick_summary().to_csv(tick_dir / "diagnostic_summary.csv", index=False)
    intake = vendor_intake_summary(True)
    intake.loc[0, "best_kind"] = "fills"
    intake.to_csv(intake_dir / "vendor_intake_summary.csv", index=False)

    code = main(
        [
            "review-data-readiness",
            "--out",
            str(out_dir),
            "--tick-diagnostics",
            str(tick_dir),
            "--vendor-intake",
            str(intake_dir),
            "--require-vendor-intake",
            "--expected-vendor-data-kind",
            "ticks",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "vendor_intake_kind"] == "fills"
    assert "vendor_intake_kind_matches" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_data_readiness_can_require_expected_adapter(tmp_path):
    tick_dir = tmp_path / "tick_diag"
    intake_dir = tmp_path / "intake"
    out_dir = tmp_path / "data_readiness"
    tick_dir.mkdir()
    intake_dir.mkdir()
    tick_summary().to_csv(tick_dir / "diagnostic_summary.csv", index=False)
    intake = vendor_intake_summary(True)
    intake.loc[0, "adapter"] = "irage"
    intake.to_csv(intake_dir / "vendor_intake_summary.csv", index=False)

    code = main(
        [
            "review-data-readiness",
            "--out",
            str(out_dir),
            "--tick-diagnostics",
            str(tick_dir),
            "--vendor-intake",
            str(intake_dir),
            "--require-vendor-intake",
            "--expected-adapter",
            "arrow_money",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "expected_adapter"] == "arrow_money"
    assert summary.loc[0, "data_adapters"] == "irage"
    assert "vendor_intake_adapter_matches" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_data_readiness_can_require_market_portability_pair(tmp_path):
    tick_dir = tmp_path / "tick_diag"
    portability_dir = tmp_path / "portability"
    out_dir = tmp_path / "data_readiness"
    tick_dir.mkdir()
    tick_summary().to_csv(tick_dir / "diagnostic_summary.csv", index=False)
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("microprice_imbalance",),
        ),
    )

    code = main(
        [
            "review-data-readiness",
            "--out",
            str(out_dir),
            "--tick-diagnostics",
            str(tick_dir),
            "--market-portability",
            str(portability_dir),
            "--require-market-portability",
            "--expected-strategy",
            "microprice_imbalance",
            "--expected-market",
            "us_equities_regular",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "market_portability_pair_ready" in set(checks.loc[~checks["passed"].astype(bool), "check"])
