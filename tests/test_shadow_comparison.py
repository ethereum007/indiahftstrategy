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
                "runtime_target_mode": "shadow",
                "runtime_strategy": "lead_lag_taker",
                "runtime_market": "india_nse_index_derivatives",
                "runtime_proof_refresh_required": True,
                "runtime_proof_refresh_provided": True,
                "runtime_proof_refresh_ready": True,
                "runtime_proof_refresh_strategy": "lead_lag_taker",
                "runtime_proof_refresh_market": "india_nse_index_derivatives",
                "runtime_proof_refresh_mixed_identity": False,
                "runtime_proof_source": "latest",
                "runtime_broker_resume_gate_required": True,
                "runtime_broker_resume_gate_provided": True,
                "runtime_broker_resume_gate_ready": True,
                "runtime_broker_resume_strategy": "lead_lag_taker",
                "runtime_broker_resume_market": "india_nse_index_derivatives",
                "runtime_broker_resume_proof_refresh_ready": True,
                "runtime_broker_resume_proof_refresh_strategy": "lead_lag_taker",
                "runtime_broker_resume_proof_refresh_market": "india_nse_index_derivatives",
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
                "runtime_target_mode": "shadow",
                "runtime_strategy": "lead_lag_taker",
                "runtime_market": "india_nse_index_derivatives",
                "runtime_proof_refresh_required": True,
                "runtime_proof_refresh_provided": True,
                "runtime_proof_refresh_ready": True,
                "runtime_proof_refresh_strategy": "lead_lag_taker",
                "runtime_proof_refresh_market": "india_nse_index_derivatives",
                "runtime_proof_refresh_mixed_identity": False,
                "runtime_proof_source": "latest",
                "runtime_broker_resume_gate_required": True,
                "runtime_broker_resume_gate_provided": True,
                "runtime_broker_resume_gate_ready": True,
                "runtime_broker_resume_strategy": "lead_lag_taker",
                "runtime_broker_resume_market": "india_nse_index_derivatives",
                "runtime_broker_resume_proof_refresh_ready": True,
                "runtime_broker_resume_proof_refresh_strategy": "lead_lag_taker",
                "runtime_broker_resume_proof_refresh_market": "india_nse_index_derivatives",
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
    runtime_strategy="lead_lag_taker",
    runtime_market="india_nse_index_derivatives",
    proof_refresh_required=True,
    proof_refresh_ready=True,
    proof_refresh_strategy="lead_lag_taker",
    proof_refresh_market="india_nse_index_derivatives",
    proof_refresh_mixed_identity=False,
    broker_resume_required=True,
    broker_resume_ready=True,
    broker_resume_strategy="lead_lag_taker",
    broker_resume_market="india_nse_index_derivatives",
    broker_resume_proof_refresh_ready=True,
    broker_resume_proof_refresh_strategy="lead_lag_taker",
    broker_resume_proof_refresh_market="india_nse_index_derivatives",
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
                "strategy": runtime_strategy,
                "market": runtime_market,
                "runtime_target_mode": "shadow",
                "runtime_strategy": runtime_strategy,
                "runtime_market": runtime_market,
                "runtime_proof_refresh_required": proof_refresh_required,
                "runtime_proof_refresh_provided": proof_refresh_required,
                "runtime_proof_refresh_ready": proof_refresh_ready,
                "runtime_proof_refresh_strategy": proof_refresh_strategy,
                "runtime_proof_refresh_market": proof_refresh_market,
                "runtime_proof_refresh_mixed_identity": proof_refresh_mixed_identity,
                "runtime_proof_source": "latest" if proof_refresh_required else "",
                "runtime_broker_resume_gate_required": broker_resume_required,
                "runtime_broker_resume_gate_provided": broker_resume_required,
                "runtime_broker_resume_gate_ready": broker_resume_ready,
                "runtime_broker_resume_strategy": broker_resume_strategy,
                "runtime_broker_resume_market": broker_resume_market,
                "runtime_broker_resume_proof_refresh_ready": broker_resume_proof_refresh_ready,
                "runtime_broker_resume_proof_refresh_strategy": broker_resume_proof_refresh_strategy,
                "runtime_broker_resume_proof_refresh_market": broker_resume_proof_refresh_market,
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
                "runtime_target_mode": "shadow",
                "runtime_strategy": runtime_strategy,
                "runtime_market": runtime_market,
                "runtime_proof_refresh_required": proof_refresh_required,
                "runtime_proof_refresh_provided": proof_refresh_required,
                "runtime_proof_refresh_ready": proof_refresh_ready,
                "runtime_proof_refresh_strategy": proof_refresh_strategy,
                "runtime_proof_refresh_market": proof_refresh_market,
                "runtime_proof_refresh_mixed_identity": proof_refresh_mixed_identity,
                "runtime_proof_source": "latest" if proof_refresh_required else "",
                "runtime_broker_resume_gate_required": broker_resume_required,
                "runtime_broker_resume_gate_provided": broker_resume_required,
                "runtime_broker_resume_gate_ready": broker_resume_ready,
                "runtime_broker_resume_strategy": broker_resume_strategy,
                "runtime_broker_resume_market": broker_resume_market,
                "runtime_broker_resume_proof_refresh_ready": broker_resume_proof_refresh_ready,
                "runtime_broker_resume_proof_refresh_strategy": broker_resume_proof_refresh_strategy,
                "runtime_broker_resume_proof_refresh_market": broker_resume_proof_refresh_market,
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
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["runtime_sessions_provided"] == 2
    assert report.summary.iloc[0]["accepted_runtime_sessions"] == 2
    assert report.summary.iloc[0]["runtime_halted_sessions"] == 0
    assert report.summary.iloc[0]["runtime_proof_refresh_sessions"] == 2
    assert report.summary.iloc[0]["proof_refresh_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["proof_refresh_market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["runtime_broker_resume_sessions"] == 2
    assert report.summary.iloc[0]["broker_resume_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["broker_resume_proof_refresh_market"] == "india_nse_index_derivatives"
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


def test_compare_shadow_sessions_blocks_mixed_runtime_identity():
    rows = session_rows()
    rows.loc[1, "runtime_strategy"] = "imbalance"
    rows.loc[1, "runtime_market"] = "us_equities_regular"

    report = compare_shadow_sessions(rows)

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {"same_runtime_strategy", "same_runtime_market"} <= failed
    assert int(report.summary.iloc[0]["strategy_count"]) == 2
    assert int(report.summary.iloc[0]["market_count"]) == 2


def test_compare_shadow_sessions_blocks_bad_runtime_proof_refresh_evidence():
    rows = session_rows()
    rows.loc[1, "runtime_proof_refresh_ready"] = False
    rows.loc[1, "runtime_proof_refresh_strategy"] = "surface_mm"
    rows.loc[1, "runtime_proof_refresh_market"] = "us_options_regular"
    rows.loc[1, "runtime_proof_refresh_mixed_identity"] = True

    report = compare_shadow_sessions(rows)

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {
        "runtime_proof_refresh_ready",
        "runtime_proof_refresh_identity_consistent",
        "same_runtime_proof_refresh_strategy",
        "same_runtime_proof_refresh_market",
    } <= failed
    assert int(report.summary.iloc[0]["runtime_proof_refresh_ready_sessions"]) == 1
    assert int(report.summary.iloc[0]["proof_refresh_strategy_count"]) == 2


def test_compare_shadow_sessions_blocks_bad_runtime_broker_resume_evidence():
    rows = session_rows()
    rows.loc[1, "runtime_broker_resume_gate_ready"] = False
    rows.loc[1, "runtime_broker_resume_strategy"] = "surface_mm"
    rows.loc[1, "runtime_broker_resume_market"] = "us_options_regular"
    rows.loc[1, "runtime_broker_resume_proof_refresh_ready"] = False
    rows.loc[1, "runtime_broker_resume_proof_refresh_strategy"] = "surface_mm"
    rows.loc[1, "runtime_broker_resume_proof_refresh_market"] = "us_options_regular"

    report = compare_shadow_sessions(rows)

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {
        "runtime_broker_resume_ready",
        "runtime_broker_resume_proof_refresh_ready",
        "same_runtime_broker_resume_strategy",
        "same_runtime_broker_resume_market",
        "same_runtime_broker_resume_proof_refresh_strategy",
        "same_runtime_broker_resume_proof_refresh_market",
    } <= failed
    assert int(report.summary.iloc[0]["runtime_broker_resume_ready_sessions"]) == 1
    assert int(report.summary.iloc[0]["broker_resume_proof_refresh_strategy_count"]) == 2


def test_write_shadow_session_comparison_carries_runtime_proof_refresh_evidence(tmp_path):
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

    runs = pd.read_csv(out_dir / "shadow_session_runs.csv")
    summary = pd.read_csv(out_dir / "shadow_session_comparison_summary.csv")
    assert report.accepted
    assert "runtime_proof_refresh_strategy" in runs.columns
    assert "runtime_broker_resume_proof_refresh_strategy" in runs.columns
    assert summary.loc[0, "proof_refresh_strategy"] == "lead_lag_taker"
    assert summary.loc[0, "broker_resume_proof_refresh_strategy"] == "lead_lag_taker"
    assert int(summary.loc[0, "runtime_proof_refresh_sessions"]) == 2
    assert int(summary.loc[0, "runtime_broker_resume_sessions"]) == 2


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
