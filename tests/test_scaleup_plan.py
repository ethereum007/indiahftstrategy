import json

import pandas as pd

from hft_cli import main
from reports.scaleup import ScaleUpThresholds, evaluate_scaleup_plan, write_scaleup_plan


def evidence_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_checks": 0 if ready else 1,
                "recommendation": "eligible_for_shadow_scaleup_review" if ready else "evidence_incomplete",
            }
        ]
    )


def shadow_summary(accepted=True):
    return pd.DataFrame(
        [
            {
                "accepted": accepted,
                "session_count": 2,
                "accepted_sessions": 2 if accepted else 1,
                "acceptance_rate": 1.0 if accepted else 0.5,
                "scenario_count": 1,
                "scenario_key": "trigger_ticks=2",
                "median_order_fill_rate": 0.95,
                "worst_order_fill_rate": 0.9,
                "total_failed_component_checks": 0 if accepted else 1,
                "total_unmatched_fills": 0,
                "total_mismatched_orders": 0,
                "total_overfilled_orders": 0,
                "worst_adverse_slippage": 0.04,
            }
        ]
    )


def launch_summary(ready=True, adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "mode": "shadow",
                "adapter": adapter,
                "scenario_key": "trigger_ticks=2",
                "accepted_orders": 2,
                "rejected_orders": 0,
                "acceptance_rate": 1.0,
                "total_notional": 1500.0,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def exposure_summary(passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "orders": 2,
                "gross_notional": 1500.0,
                "net_delta": 50.0,
                "net_vega": 200.0,
            }
        ]
    )


def write_inputs(root, *, evidence_ready=True, shadow_accepted=True, launch_ready=True, exposure_passed=True):
    evidence = root / "evidence"
    shadow = root / "shadow"
    launch = root / "launch"
    exposure = root / "exposure"
    for path in (evidence, shadow, launch, exposure):
        path.mkdir(parents=True, exist_ok=True)
    evidence_summary(evidence_ready).to_csv(evidence / "strategy_evidence_summary.csv", index=False)
    shadow_summary(shadow_accepted).to_csv(shadow / "shadow_session_comparison_summary.csv", index=False)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    exposure_summary(exposure_passed).to_csv(exposure / "order_exposure_summary.csv", index=False)
    return evidence, shadow, launch, exposure


def test_scaleup_plan_accepts_clean_shadow_scaleup():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        order_exposure_summary=exposure_summary(True),
        thresholds=ScaleUpThresholds(
            target_mode="shadow",
            max_scale_multiplier=1.5,
            min_shadow_sessions=2,
            min_worst_order_fill_rate=0.9,
            max_worst_adverse_slippage=0.05,
            max_orders_per_session=3,
            max_session_notional=2000.0,
            max_gross_notional=2000.0,
            max_abs_net_delta=100.0,
            max_abs_net_vega=250.0,
            stop_loss=500.0,
            allowed_adapters=("arrow_money",),
        ),
    )

    assert report.ready
    plan = report.plan.iloc[0]
    assert plan["max_orders_per_session"] == 3
    assert plan["max_notional_per_session"] == 2000.0
    assert report.summary.iloc[0]["recommendation"] == "scale_up_with_controls"
    assert report.config["kill_switches"]["max_worst_adverse_slippage"] == 0.05


def test_scaleup_plan_fails_on_incomplete_evidence_and_adapter_gap():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(False),
        shadow_comparison_summary=shadow_summary(False),
        launch_summary=launch_summary(True, adapter="irage"),
        thresholds=ScaleUpThresholds(
            min_shadow_sessions=2,
            min_shadow_acceptance_rate=1.0,
            allowed_adapters=("arrow_money",),
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "evidence_ready" in failed
    assert "shadow_comparison_accepted" in failed
    assert "acceptance_rate" in failed
    assert "adapter_allowed" in failed


def test_write_scaleup_plan_outputs_artifacts(tmp_path):
    evidence, shadow, launch, exposure = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        order_exposure_dir=exposure,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(allowed_adapters=("arrow_money",), stop_loss=500.0),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert config["limits"]["stop_loss"] == 500.0
    assert (out_dir / "scaleup_plan.csv").exists()
    assert (out_dir / "scaleup_checks.csv").exists()
    assert (out_dir / "scaleup_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_scaleup_plan_can_fail_on_breach(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path, evidence_ready=False)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--allowed-adapter",
            "arrow_money",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_checks"]) == 1
