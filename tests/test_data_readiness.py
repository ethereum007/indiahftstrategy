import pandas as pd

from hft_cli import main
from reports.data_readiness import (
    DataReadinessThresholds,
    evaluate_data_readiness,
    write_data_readiness_report,
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
        schema_audit_summary=schema_summary(True),
        mapped_data_summary=mapped_data_summary(True),
        tick_diagnostic_summary=tick_summary(),
        chain_diagnostic_summary=chain_summary(),
        market_profile_summary=market_profile_summary(True),
        instrument_metadata_summary=instrument_metadata_summary(True),
        thresholds=DataReadinessThresholds(
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
    assert int(report.summary.iloc[0]["required_components"]) == 6


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
