import pandas as pd

from hft_cli import main
from reports.data_readiness import (
    DataReadinessThresholds,
    evaluate_data_readiness,
    write_data_readiness_report,
)
from reports.market_portability import (
    MarketPortabilityReportConfig,
    build_market_portability_report,
    write_market_portability_report,
)


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
            }
        ]
    )


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


def test_data_readiness_accepts_clean_tick_diagnostics():
    report = evaluate_data_readiness(tick_diagnostic_summary=tick_summary())

    assert report.ready
    assert report.summary.iloc[0]["recommendation"] == "feed_strategy_research"
    assert set(report.checks["passed"]) == {True}


def test_data_readiness_fails_on_bad_tick_diagnostics():
    report = evaluate_data_readiness(
        tick_diagnostic_summary=tick_summary(crossed_quote_rows=1, out_of_session_rows=1),
        thresholds=DataReadinessThresholds(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"tick_crossed_quote_rows", "tick_out_of_session_rows"} <= failed


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
    assert "vendor_intake_ready" in failed
    assert int(item["failed_checks"]) == 1


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
    tick_dir.mkdir()
    tick_summary().to_csv(tick_dir / "diagnostic_summary.csv", index=False)

    report = write_data_readiness_report(output_dir=out_dir, tick_diagnostics_dir=tick_dir)

    assert report.ready
    assert report.output_dir == out_dir
    assert (out_dir / "data_readiness_items.csv").exists()
    assert (out_dir / "data_readiness_checks.csv").exists()
    assert (out_dir / "data_readiness_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_data_readiness_can_fail_on_missing_required_tick_diagnostics(tmp_path):
    out_dir = tmp_path / "data_readiness"

    code = main(["review-data-readiness", "--out", str(out_dir), "--fail-on-breach"])

    summary = pd.read_csv(out_dir / "data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "tick_diagnostics_provided" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "vendor_intake_provided" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
