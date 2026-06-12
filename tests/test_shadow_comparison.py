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
                "runtime_session_provided": True,
                "runtime_guard_action": "continue",
                "runtime_guard_halted": False,
                "runtime_failed_checks": 0,
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
                "runtime_session_provided": True,
                "runtime_guard_action": "continue",
                "runtime_guard_halted": False,
                "runtime_failed_checks": 0,
                "max_adverse_slippage": 0.04,
                "avg_latency_ns": 120,
            },
        ]
    )


def write_session_dir(
    path,
    *,
    accepted=True,
    scenario_key="trigger_ticks=2",
    fill_rate=1.0,
    runtime_halted=False,
):
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
                "runtime_session_provided": True,
                "runtime_guard_action": "halt" if runtime_halted else "continue",
                "runtime_guard_halted": runtime_halted,
                "runtime_failed_checks": 1 if runtime_halted else 0,
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
    assert report.summary.iloc[0]["runtime_sessions_provided"] == 2
    assert report.summary.iloc[0]["runtime_halted_sessions"] == 0
    assert report.summary.iloc[0]["recommendation"] == "eligible_for_controlled_paper_scaleup"


def test_compare_shadow_sessions_blocks_runtime_halted_sessions():
    rows = session_rows()
    rows.loc[1, "runtime_guard_action"] = "halt"
    rows.loc[1, "runtime_guard_halted"] = True
    rows.loc[1, "runtime_failed_checks"] = 1

    report = compare_shadow_sessions(rows)

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert report.summary.iloc[0]["runtime_halted_sessions"] == 1
    assert "runtime_halted_sessions" in failed


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


def test_unified_cli_compare_shadow_sessions_fails_on_halted_runtime_session(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "cli_runtime_comparison"
    write_session_dir(day1)
    write_session_dir(day2, runtime_halted=True)

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

    summary = pd.read_csv(out_dir / "shadow_session_comparison_summary.csv")
    checks = pd.read_csv(out_dir / "shadow_session_comparison_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert int(summary.loc[0, "runtime_halted_sessions"]) == 1
    assert "runtime_halted_sessions" in failed
