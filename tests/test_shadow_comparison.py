import pandas as pd

from hft_cli import main
from reports.shadow_comparison import (
    ShadowComparisonThresholds,
    compare_shadow_sessions,
    write_shadow_session_comparison,
)


def session_rows():
    return pd.DataFrame(
        [
            {
                "session": "day1",
                "accepted": True,
                "scenario_key": "trigger_ticks=2",
                "mode": "shadow",
                "adapter": "arrow_money",
                "order_fill_rate": 1.0,
                "total_failed_component_checks": 0,
                "orders": 2,
                "filled_orders": 2,
                "unfilled_orders": 0,
                "mismatched_orders": 0,
                "overfilled_orders": 0,
                "unmatched_fills": 0,
                "max_adverse_slippage": 0.03,
                "avg_latency_ns": 100,
            },
            {
                "session": "day2",
                "accepted": True,
                "scenario_key": "trigger_ticks=2",
                "mode": "shadow",
                "adapter": "arrow_money",
                "order_fill_rate": 0.9,
                "total_failed_component_checks": 0,
                "orders": 2,
                "filled_orders": 2,
                "unfilled_orders": 0,
                "mismatched_orders": 0,
                "overfilled_orders": 0,
                "unmatched_fills": 0,
                "max_adverse_slippage": 0.04,
                "avg_latency_ns": 120,
            },
        ]
    )


def write_session_dir(path, *, accepted=True, scenario_key="trigger_ticks=2", fill_rate=1.0):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "accepted": accepted,
                "scenario_key": scenario_key,
                "mode": "shadow",
                "adapter": "arrow_money",
                "order_fill_rate": fill_rate,
                "failed_checks": 0 if accepted else 1,
                "recommendation": "continue_shadow_or_promote" if accepted else "hold_in_research",
            }
        ]
    ).to_csv(path / "shadow_session_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "scenario_key": scenario_key,
                "mode": "shadow",
                "adapter": "arrow_money",
                "total_failed_component_checks": 0 if accepted else 1,
                "orders": 2,
                "filled_orders": int(2 * fill_rate),
                "unfilled_orders": 2 - int(2 * fill_rate),
                "mismatched_orders": 0,
                "overfilled_orders": 0,
                "unmatched_fills": 0,
                "order_fill_rate": fill_rate,
                "max_adverse_slippage": 0.04,
                "avg_latency_ns": 100,
            }
        ]
    ).to_csv(path / "shadow_session_metrics.csv", index=False)


def test_compare_shadow_sessions_accepts_consistent_sessions():
    report = compare_shadow_sessions(
        session_rows(),
        thresholds=ShadowComparisonThresholds(
            min_sessions=2,
            min_acceptance_rate=1.0,
            min_median_order_fill_rate=0.9,
            min_worst_order_fill_rate=0.9,
            max_worst_adverse_slippage=0.05,
        ),
    )

    assert report.accepted
    assert report.summary.iloc[0]["session_count"] == 2
    assert report.summary.iloc[0]["scenario_key"] == "trigger_ticks=2"
    assert report.summary.iloc[0]["recommendation"] == "eligible_for_controlled_paper_scaleup"


def test_write_shadow_session_comparison_outputs_artifacts(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_session_dir(day1, fill_rate=1.0)
    write_session_dir(day2, fill_rate=0.9)

    report = write_shadow_session_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["2026-06-10", "2026-06-11"],
        thresholds=ShadowComparisonThresholds(min_sessions=2, min_median_order_fill_rate=0.9),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "shadow_session_runs.csv").exists()
    assert (out_dir / "shadow_session_comparison_checks.csv").exists()
    assert (out_dir / "shadow_session_comparison_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_compare_shadow_sessions_fails_on_mixed_scenarios(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "cli_comparison"
    write_session_dir(day1, scenario_key="trigger_ticks=2")
    write_session_dir(day2, scenario_key="trigger_ticks=3")

    code = main(
        [
            "compare-shadow-sessions",
            "--sessions",
            str(day1),
            str(day2),
            "--out",
            str(out_dir),
            "--min-sessions",
            "2",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "shadow_session_comparison_checks.csv").exists()
    assert (out_dir / "shadow_session_comparison_summary.csv").exists()
