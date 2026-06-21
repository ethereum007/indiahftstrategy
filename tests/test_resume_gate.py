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
    proof_strategy=None,
    proof_market=None,
    proof_ready=True,
    route_strategy=None,
    route_market=None,
    route_ready=True,
    route_ready_pairs=1,
    route_gap_pairs=0,
    route_ops_launch_controls_ready=True,
    route_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    proof_strategy = strategy if proof_strategy is None else proof_strategy
    proof_market = market if proof_market is None else proof_market
    route_strategy = strategy if route_strategy is None else route_strategy
    route_market = market if route_market is None else route_market
    route_recommendation = "route_ready" if route_ready and route_gap_pairs == 0 else "complete_route_readiness_gaps"
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "incident_status": "halt_completed" if passed else "halt_incomplete",
                "strategy": strategy,
                "market": market,
                "proof_refresh_required": True,
                "proof_refresh_provided": True,
                "proof_refresh_ready": proof_ready,
                "proof_refresh_strategy": proof_strategy,
                "proof_refresh_market": proof_market,
                "proof_refresh_mixed_identity": False,
                "proof_source": "latest",
                "broker_route_readiness_required": True,
                "broker_route_readiness_provided": True,
                "broker_route_readiness_ready": route_ready,
                "broker_route_readiness_strategy": route_strategy,
                "broker_route_readiness_market": route_market,
                "broker_route_readiness_route_ready_pairs": route_ready_pairs,
                "broker_route_readiness_gap_pairs": route_gap_pairs,
                "broker_route_readiness_recommendation": route_recommendation,
                "broker_route_readiness_ops_launch_controls_ready": route_ops_launch_controls_ready,
                "broker_route_readiness_ops_launch_control_failures": (
                    "" if route_ops_launch_controls_ready else "ops_launch_control_failed"
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    route_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
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
    proof_strategy=None,
    proof_market=None,
    proof_ready=True,
    proof_mixed_identity=False,
    route_strategy=None,
    route_market=None,
    route_ready=True,
    route_ready_pairs=1,
    route_gap_pairs=0,
    route_ops_launch_controls_ready=True,
    route_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    proof_strategy = strategy if proof_strategy is None else proof_strategy
    proof_market = market if proof_market is None else proof_market
    route_strategy = strategy if route_strategy is None else route_strategy
    route_market = market if route_market is None else route_market
    route_recommendation = "route_ready" if route_ready and route_gap_pairs == 0 else "complete_route_readiness_gaps"
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": target_mode,
                "strategy": strategy,
                "market": market,
                "proof_refresh_provided": True,
                "proof_refresh_ready": proof_ready,
                "proof_refresh_strategy": proof_strategy,
                "proof_refresh_market": proof_market,
                "proof_refresh_mixed_identity": proof_mixed_identity,
                "proof_source": "latest",
                "broker_route_readiness_provided": True,
                "broker_route_readiness_ready": route_ready,
                "broker_route_readiness_strategy": route_strategy,
                "broker_route_readiness_market": route_market,
                "broker_route_readiness_route_ready_pairs": route_ready_pairs,
                "broker_route_readiness_gap_pairs": route_gap_pairs,
                "broker_route_readiness_recommendation": route_recommendation,
                "broker_route_readiness_ops_launch_controls_ready": route_ops_launch_controls_ready,
                "broker_route_readiness_ops_launch_control_failures": (
                    "" if route_ops_launch_controls_ready else "ops_launch_control_failed"
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    route_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
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
    proof_strategy=None,
    proof_market=None,
    proof_ready=True,
    proof_mixed_identity=False,
    route_strategy=None,
    route_market=None,
    route_ready=True,
    route_ready_pairs=1,
    route_gap_pairs=0,
    route_ops_launch_controls_ready=True,
    route_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    proof_strategy = strategy if proof_strategy is None else proof_strategy
    proof_market = market if proof_market is None else proof_market
    route_strategy = strategy if route_strategy is None else route_strategy
    route_market = market if route_market is None else route_market
    route_recommendation = "route_ready" if route_ready and route_gap_pairs == 0 else "complete_route_readiness_gaps"
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
        "proof_freshness": {
            "required": True,
            "provided": True,
            "ready": proof_ready,
            "strategy": proof_strategy,
            "market": proof_market,
            "mixed_identity": proof_mixed_identity,
            "proof_source": "latest",
            "fresh_proof_required": False,
            "recommendation": "reuse_latest_calibrated_proof",
        },
        "broker_readiness": {
            "required": True,
            "provided": True,
            "ready": route_ready,
            "route_readiness": {
                "required": True,
                "provided": True,
                "ready": route_ready,
                "strategy": route_strategy,
                "market": route_market,
                "route_ready_pairs": route_ready_pairs,
                "gap_pairs": route_gap_pairs,
                "recommendation": route_recommendation,
                "ops_launch_controls_ready": route_ops_launch_controls_ready,
                "ops_launch_control_failures": (
                    "" if route_ops_launch_controls_ready else "ops_launch_control_failed"
                ),
                "ops_broker_roundtrip_portfolio_safe_runs": (
                    route_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "ops_broker_roundtrip_portfolio_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
            },
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


def path_tail(value):
    return str(value).replace("\\", "/")


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
    assert report.authorization.iloc[0]["proof_refresh_strategy"] == "lead_lag_taker"
    assert report.authorization.iloc[0]["proof_refresh_market"] == "india_nse_index_derivatives"
    assert report.authorization.iloc[0]["incident_proof_refresh_strategy"] == "lead_lag_taker"
    assert bool(report.authorization.iloc[0]["broker_route_readiness_ready"])
    assert report.authorization.iloc[0]["broker_route_readiness_strategy"] == "lead_lag_taker"
    assert report.authorization.iloc[0]["broker_route_readiness_market"] == "india_nse_index_derivatives"
    assert bool(report.authorization.iloc[0]["incident_broker_route_readiness_ready"])
    assert report.authorization.iloc[0]["incident_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(report.authorization.iloc[0]["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert bool(report.summary.iloc[0]["proof_refresh_ready"])
    assert report.summary.iloc[0]["proof_refresh_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["incident_proof_refresh_market"] == "india_nse_index_derivatives"
    assert bool(report.summary.iloc[0]["broker_route_readiness_ready"])
    assert report.summary.iloc[0]["broker_route_readiness_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["incident_broker_route_readiness_market"] == "india_nse_index_derivatives"
    assert int(report.summary.iloc[0]["broker_route_readiness_gap_pairs"]) == 0
    assert report.summary.iloc[0]["incident_guard_failed_check_names"] == "open_order_count"
    assert report.summary.iloc[0]["incident_guard_first_failed_reason"] == "open_order_count: limit breached"
    assert report.summary.iloc[0]["recommendation"] == "resume_with_scaleup_controls"
    assert report.config["incident"]["guard_failed_check_names"] == "open_order_count"
    assert report.config["identity"]["strategy"] == "lead_lag_taker"
    assert report.config["identity"]["incident_market"] == "india_nse_index_derivatives"
    assert report.config["proof_freshness"]["strategy"] == "lead_lag_taker"
    assert report.config["proof_freshness"]["incident"]["market"] == "india_nse_index_derivatives"
    assert report.config["broker_route_readiness"]["ready"]
    assert report.config["broker_route_readiness"]["strategy"] == "lead_lag_taker"
    assert report.config["broker_route_readiness"]["incident"]["market"] == "india_nse_index_derivatives"
    assert report.config["broker_route_readiness"]["ops_broker_roundtrip_portfolio_safe_runs"] == 1
    assert report.config["broker_route_readiness"][
        "ops_broker_roundtrip_portfolio_concentration_ok_runs"
    ] == 1
    assert report.config["ready"]
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.action_queue is not None
    assert report.action_queue.empty


def test_resume_gate_blocks_scenario_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(scenario_key="trigger_ticks=2"),
        scaleup_summary=scaleup_summary(scenario_key="trigger_ticks=3"),
        scaleup_config=scaleup_config(scenario_key="trigger_ticks=3"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "scenario_match" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]


def test_resume_gate_blocks_strategy_and_market_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(strategy="leadlag", market="india_nse_index_derivatives"),
        scaleup_summary=scaleup_summary(strategy="imbalance", market="us_equities_regular"),
        scaleup_config=scaleup_config(strategy="imbalance", market="us_equities_regular"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"strategy_match", "market_match"} <= failed


def test_resume_gate_blocks_proof_refresh_identity_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(
            proof_strategy="surface_mm",
            proof_market="us_options_regular",
        ),
        scaleup_config=scaleup_config(
            proof_strategy="surface_mm",
            proof_market="us_options_regular",
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"proof_refresh_strategy_match", "proof_refresh_market_match"} <= failed
    assert report.authorization.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.authorization.iloc[0]["proof_refresh_strategy"] == "surface_mm"


def test_resume_gate_blocks_broker_route_readiness_identity_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(
            route_strategy="surface_mm",
            route_market="us_options_regular",
        ),
        scaleup_config=scaleup_config(
            route_strategy="surface_mm",
            route_market="us_options_regular",
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"broker_route_readiness_strategy_match", "broker_route_readiness_market_match"} <= failed
    route_rows = report.action_queue.loc[
        report.action_queue["check"].isin(
            ["broker_route_readiness_strategy_match", "broker_route_readiness_market_match"]
        )
    ]
    assert set(route_rows["component"]) == {"broker_route_readiness"}
    assert set(route_rows["next_gate"]) == {"review-route-readiness"}


def test_resume_gate_blocks_stale_broker_route_readiness_ops():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(
            route_ready=False,
            route_gap_pairs=2,
            route_ops_launch_controls_ready=False,
            route_ops_broker_roundtrip_portfolio_safe_runs=0,
            route_ops_broker_roundtrip_portfolio_breach_runs=1,
            route_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            route_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        scaleup_config=scaleup_config(
            route_ready=False,
            route_gap_pairs=2,
            route_ops_launch_controls_ready=False,
            route_ops_broker_roundtrip_portfolio_safe_runs=0,
            route_ops_broker_roundtrip_portfolio_breach_runs=1,
            route_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            route_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_route_readiness_ready",
        "broker_route_readiness_gap_pairs",
        "broker_route_readiness_ops_launch_controls_ready",
        "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    route_queue = report.action_queue.loc[
        report.action_queue["check"].str.startswith("broker_route_readiness")
    ]
    assert not route_queue.empty
    assert set(route_queue["next_gate"]) == {"review-route-readiness"}


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
    assert (out_dir / "resume_action_queue.csv").exists()
    assert (out_dir / "resume_config.json").exists()
    assert (out_dir / "resume_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "incident_summary",
        "scaleup_summary",
        "scaleup_config",
        "scaleup_checks",
        "operator_review",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["incident_summary"]["path"]).endswith(
        "/incident/halt_incident_summary.csv"
    )
    assert path_tail(manifest["inputs"]["scaleup_summary"]["path"]).endswith("/scaleup/scaleup_summary.csv")
    assert path_tail(manifest["inputs"]["scaleup_config"]["path"]).endswith("/scaleup/scaleup_config.json")
    assert path_tail(manifest["inputs"]["scaleup_checks"]["path"]).endswith("/scaleup/scaleup_checks.csv")
    assert path_tail(manifest["inputs"]["operator_review"]["path"]).endswith("/operator_review.csv")
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert any(path.endswith("resume_action_queue.csv") for path in artifact_paths)
    assert any(path.endswith("resume_runbook.md") for path in artifact_paths)
    saved_summary = pd.read_csv(out_dir / "resume_summary.csv")
    assert saved_summary.loc[0, "incident_guard_failed_check_names"] == "open_order_count"
    assert saved_summary.loc[0, "proof_refresh_strategy"] == "lead_lag_taker"
    assert bool(saved_summary.loc[0, "proof_refresh_ready"])
    assert saved_summary.loc[0, "broker_route_readiness_strategy"] == "lead_lag_taker"
    assert bool(saved_summary.loc[0, "broker_route_readiness_ready"])
    assert int(saved_summary.loc[0, "broker_route_readiness_gap_pairs"]) == 0
    assert int(saved_summary.loc[0, "action_queue_count"]) == 0
    assert (out_dir / "resume_runbook.md").read_text(encoding="utf-8").startswith("# Resume Gate Runbook")


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
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "resume_summary.csv")
    queue = pd.read_csv(out_dir / "resume_action_queue.csv")
    config = json.loads((out_dir / "resume_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert queue.loc[0, "component"] == "operator_review"
    assert queue.loc[0, "check"] == "operator_approved"
    assert queue.loc[0, "next_gate"] == "review-resume-gate"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli review-resume-gate --help"
    assert config["primary_action"]["check"] == "operator_approved"
    assert "operator_approved" in (out_dir / "resume_runbook.md").read_text(encoding="utf-8")


def test_cli_resume_gate_can_fail_on_actions(tmp_path):
    incident, scaleup = write_inputs(tmp_path, scaleup_ready=False)
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
            "--allow-unready-scaleup",
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "resume_summary.csv")
    queue = pd.read_csv(out_dir / "resume_action_queue.csv")
    assert code == 2
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert queue.loc[0, "check"] == "scaleup_failed_checks"
    assert queue.loc[0, "component"] == "scaleup_plan"
    assert queue.loc[0, "next_gate"] == "plan-scaleup"


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
