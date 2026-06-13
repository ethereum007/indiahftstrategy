import json

import pandas as pd

from hft_cli import main
from reports.resume import ResumeGateThresholds, evaluate_resume_gate, write_resume_gate_report


def incident_summary(
    passed=True,
    scenario_key="trigger_ticks=2",
    adapter="arrow_money",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "incident_status": "halt_completed" if passed else "halt_incomplete",
                "strategy": strategy,
                "market": market,
                "scenario_key": scenario_key,
                "adapter": adapter,
                "guard_failed_check_names": "open_order_count" if passed else "halt_execution_passed",
                "guard_first_failed_reason": "open_order_count: limit breached" if passed else "execution incomplete",
                "failed_checks": 0 if passed else 1,
                "recommendation": "resume_only_after_new_scaleup_review" if passed else "keep_trading_disabled",
            }
        ]
    )


def scaleup_summary(
    ready=True,
    scenario_key="trigger_ticks=2",
    adapter="arrow_money",
    target_mode="shadow",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": target_mode,
                "strategy": strategy,
                "market": market,
                "scenario_key": scenario_key,
                "adapter": adapter,
                "max_orders_per_session": 10,
                "max_notional_per_session": 100_000.0,
                "failed_checks": 0 if ready else 1,
                "recommendation": "scale_up_with_controls" if ready else "do_not_scale",
            }
        ]
    )


def scaleup_config(
    scenario_key="trigger_ticks=2",
    adapter="arrow_money",
    target_mode="shadow",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
):
    return {
        "schema_version": 1,
        "ready": True,
        "target_mode": target_mode,
        "strategy": strategy,
        "market": market,
        "scenario_key": scenario_key,
        "adapter": adapter,
        "identity": {
            "strategy": strategy,
            "market": market,
            "expected_strategy": strategy,
            "expected_market": market,
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "max_scale_multiplier": 1.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": {
            "max_total_failed_component_checks": 0,
            "max_total_unmatched_fills": 0,
            "max_total_mismatched_orders": 0,
            "max_total_overfilled_orders": 0,
            "max_lifecycle_orders": 20,
            "max_replace_orders": 5,
            "max_open_order_notional": 1_000.0,
            "max_open_order_age_ns": 5_000_000_000.0,
            "max_gross_notional": 2_000.0,
            "max_abs_net_delta": 100.0,
            "max_abs_net_vega": 250.0,
            "max_worst_adverse_slippage": 0.05,
        },
    }


def scaleup_checks():
    return pd.DataFrame([{"check": "scaleup_ready", "passed": True, "reason": ""}])


def operator_review(approved=True, guard_failed_check_names="open_order_count"):
    row = {"reviewer": "ops", "approved": approved, "reason": "incident closed"}
    if guard_failed_check_names is not None:
        row["guard_failed_check_names"] = guard_failed_check_names
    return pd.DataFrame([row])


def write_inputs(root, *, incident_passed=True, scaleup_ready=True, target_mode="shadow"):
    incident = root / "incident"
    scaleup = root / "scaleup"
    incident.mkdir(parents=True, exist_ok=True)
    scaleup.mkdir(parents=True, exist_ok=True)
    incident_summary(incident_passed).to_csv(incident / "halt_incident_summary.csv", index=False)
    scaleup_summary(scaleup_ready, target_mode=target_mode).to_csv(scaleup / "scaleup_summary.csv", index=False)
    scaleup_checks().to_csv(scaleup / "scaleup_checks.csv", index=False)
    (scaleup / "scaleup_config.json").write_text(
        json.dumps(scaleup_config(target_mode=target_mode), indent=2) + "\n",
        encoding="utf-8",
    )
    return incident, scaleup


def test_resume_gate_authorizes_clean_incident_and_scaleup():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(),
        scaleup_checks=scaleup_checks(),
        scaleup_config=scaleup_config(),
    )

    assert report.ready
    assert report.authorization.iloc[0]["max_orders_per_session"] == 10
    assert report.authorization.iloc[0]["max_lifecycle_orders"] == 20
    assert report.authorization.iloc[0]["max_replace_orders"] == 5
    assert report.authorization.iloc[0]["max_open_order_notional"] == 1_000.0
    assert report.authorization.iloc[0]["max_open_order_age_ns"] == 5_000_000_000.0
    assert report.authorization.iloc[0]["max_gross_notional"] == 2_000.0
    assert report.authorization.iloc[0]["max_abs_net_delta"] == 100.0
    assert report.authorization.iloc[0]["max_abs_net_vega"] == 250.0
    assert report.authorization.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.authorization.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.authorization.iloc[0]["incident_guard_failed_check_names"] == "open_order_count"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["incident_guard_failed_check_names"] == "open_order_count"
    assert report.summary.iloc[0]["incident_guard_first_failed_reason"] == "open_order_count: limit breached"
    assert report.summary.iloc[0]["recommendation"] == "resume_with_scaleup_controls"
    assert report.config["incident"]["guard_failed_check_names"] == "open_order_count"
    assert report.config["identity"]["strategy"] == "lead_lag_taker"
    assert report.config["identity"]["incident_market"] == "india_nse_index_derivatives"
    assert report.config["ready"]


def test_resume_gate_blocks_scenario_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(scenario_key="trigger_ticks=2"),
        scaleup_summary=scaleup_summary(scenario_key="trigger_ticks=3"),
        scaleup_config=scaleup_config(scenario_key="trigger_ticks=3"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "scenario_match" in failed


def test_resume_gate_blocks_strategy_and_market_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(strategy="leadlag", market="india_nse_index_derivatives"),
        scaleup_summary=scaleup_summary(strategy="imbalance", market="us_equities_regular"),
        scaleup_config=scaleup_config(strategy="imbalance", market="us_equities_regular"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"strategy_match", "market_match"} <= failed


def test_resume_gate_can_require_operator_trigger_acknowledgment():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        operator_review=operator_review(guard_failed_check_names="open_order_count"),
        thresholds=ResumeGateThresholds(require_operator_guard_trigger_ack=True),
    )

    assert report.ready

    blocked = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        operator_review=operator_review(guard_failed_check_names="orders_sent"),
        thresholds=ResumeGateThresholds(require_operator_guard_trigger_ack=True),
    )

    assert not blocked.ready
    failed = set(blocked.checks.loc[~blocked.checks["passed"].astype(bool), "check"])
    assert "operator_guard_trigger_ack" in failed


def test_resume_gate_live_dryrun_requires_operator_review_and_trigger_ack():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(target_mode="live_dryrun"),
        scaleup_config=scaleup_config(target_mode="live_dryrun"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"operator_approved", "operator_guard_trigger_ack"} <= failed
    assert report.summary.iloc[0]["operator_approval_required"]
    assert report.summary.iloc[0]["operator_guard_trigger_ack_required"]
    assert report.config["operator_review"]["approval_required"]
    assert report.config["operator_review"]["guard_trigger_ack_required"]


def test_resume_gate_live_dryrun_config_fails_closed_when_summary_omits_mode():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary().drop(columns=["target_mode"]),
        scaleup_config=scaleup_config(target_mode="live_dryrun"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"operator_approved", "operator_guard_trigger_ack"} <= failed
    assert report.summary.iloc[0]["operator_approval_required"]
    assert report.summary.iloc[0]["operator_guard_trigger_ack_required"]


def test_resume_gate_live_dryrun_accepts_operator_trigger_ack():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(target_mode="live_dryrun"),
        scaleup_config=scaleup_config(target_mode="live_dryrun"),
        operator_review=operator_review(approved=True, guard_failed_check_names="open_order_count"),
    )

    assert report.ready
    assert report.summary.iloc[0]["target_mode"] == "live_dryrun"
    assert report.summary.iloc[0]["operator_approval_required"]
    assert report.summary.iloc[0]["operator_guard_trigger_ack_required"]


def test_write_resume_gate_outputs_artifacts(tmp_path):
    incident, scaleup = write_inputs(tmp_path)
    out_dir = tmp_path / "resume"
    review_path = tmp_path / "operator_review.csv"
    operator_review().to_csv(review_path, index=False)

    report = write_resume_gate_report(
        incident_dir=incident,
        scaleup_dir=scaleup,
        operator_review_path=review_path,
        output_dir=out_dir,
        thresholds=ResumeGateThresholds(require_operator_approval=True),
    )

    assert report.output_dir == out_dir
    assert report.ready
    assert (out_dir / "resume_authorization.csv").exists()
    assert (out_dir / "resume_checks.csv").exists()
    assert (out_dir / "resume_summary.csv").exists()
    assert (out_dir / "resume_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    saved_summary = pd.read_csv(out_dir / "resume_summary.csv")
    assert saved_summary.loc[0, "incident_guard_failed_check_names"] == "open_order_count"


def test_cli_resume_gate_fails_when_operator_approval_required(tmp_path):
    incident, scaleup = write_inputs(tmp_path)
    out_dir = tmp_path / "resume"

    code = main(
        [
            "review-resume-gate",
            "--incident",
            str(incident),
            "--scaleup",
            str(scaleup),
            "--out",
            str(out_dir),
            "--require-operator-approval",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "resume_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])


def test_cli_resume_gate_fails_when_operator_trigger_ack_missing(tmp_path):
    incident, scaleup = write_inputs(tmp_path)
    out_dir = tmp_path / "resume"
    review_path = tmp_path / "operator_review.csv"
    operator_review(guard_failed_check_names=None).to_csv(review_path, index=False)

    code = main(
        [
            "review-resume-gate",
            "--incident",
            str(incident),
            "--scaleup",
            str(scaleup),
            "--operator-review",
            str(review_path),
            "--out",
            str(out_dir),
            "--require-operator-trigger-ack",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "resume_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "operator_guard_trigger_ack" in failed


def test_cli_resume_gate_live_dryrun_requires_operator_review(tmp_path):
    incident, scaleup = write_inputs(tmp_path, target_mode="live_dryrun")
    out_dir = tmp_path / "resume"

    code = main(
        [
            "review-resume-gate",
            "--incident",
            str(incident),
            "--scaleup",
            str(scaleup),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "resume_summary.csv")
    checks = pd.read_csv(out_dir / "resume_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {"operator_approved", "operator_guard_trigger_ack"} <= failed
