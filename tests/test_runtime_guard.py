import json

import pandas as pd

from hft_cli import main
from reports.manifest import write_experiment_manifest
from reports.runtime_guard import evaluate_runtime_guard, write_runtime_guard_report


def leadlag_lineage(prefix=""):
    fields = {
        "leadlag_edge_lineage_required": True,
        "leadlag_edge_lineage_ready": True,
        "leadlag_lineage_bound_stages": 5,
        "leadlag_lineage_required_stages": 5,
        "leadlag_lineage_selected_stage_count": 5,
        "leadlag_lineage_selected_run_dirs": ";".join(
            [
                "edge-audit",
                "replay-walkforward",
                "promotion",
                "order-plan",
                "launch-pipeline",
            ]
        ),
        "leadlag_measurement_manifest_sha256": "1" * 64,
        "leadlag_edge_candidate_manifest_sha256": "2" * 64,
        "leadlag_edge_lineage_contract_version": "leadlag_edge_lineage/v1",
        "leadlag_edge_lineage_contract_sha256": "3" * 64,
        "leadlag_edge_latency_budget_ns": 5_000.0,
        "leadlag_total_replay_latency_ns": 3_000.0,
        "leadlag_edge_latency_headroom_ns": 2_000.0,
    }
    return {f"{prefix}{field}": value for field, value in fields.items()}


def path_tail(value):
    return str(value).replace("\\", "/")


def scaleup_config(
    require_proof_refresh=False,
    require_broker_resume_gate=False,
    require_broker_route_readiness=False,
    require_strategy_portfolio=False,
    **overrides,
):
    config = {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "identity": {
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "expected_strategy": "lead_lag_taker",
            "expected_market": "india_nse_index_derivatives",
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
            "max_worst_adverse_slippage": 0.05,
        },
    }
    if require_proof_refresh:
        config["proof_freshness"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "mixed_identity": False,
            "proof_source": "latest",
            "fresh_proof_required": True,
        }
    if require_broker_resume_gate:
        broker_readiness = config.setdefault(
            "broker_readiness",
            {"required": True, "provided": True, "ready": True},
        )
        broker_readiness.update({"required": True, "provided": True, "ready": True})
        broker_readiness["resume_gate"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "incident_strategy": "lead_lag_taker",
            "incident_market": "india_nse_index_derivatives",
            "proof_refresh_ready": True,
            "proof_refresh_strategy": "lead_lag_taker",
            "proof_refresh_market": "india_nse_index_derivatives",
        }
    if require_broker_route_readiness:
        broker_readiness = config.setdefault(
            "broker_readiness",
            {"required": True, "provided": True, "ready": True},
        )
        broker_readiness.update({"required": True, "provided": True, "ready": True})
        broker_readiness["route_readiness"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "route_ready_pairs": 1,
            "gap_pairs": 0,
            "recommendation": "scale_up_with_controls",
            "ops_launch_controls_ready": True,
            "ops_launch_control_failures": "",
            "ops_broker_roundtrip_portfolio_safe_runs": 1,
            "ops_broker_roundtrip_portfolio_breach_runs": 0,
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
        }
    if require_strategy_portfolio:
        config["strategy_portfolio"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "deployment_mode": "paper_shadow",
            "allocation_mode": "readiness_weighted",
            "capital_currency": "INR",
            "min_strategy_count": 2,
            "min_market_count": 1,
            "max_strategy_weight": 0.60,
            "max_market_weight": 0.90,
            "allocated_strategy_count": 2,
            "allocated_market_count": 1,
            "top_strategy_by_weight": "lead_lag_taker",
            "top_market_by_weight": "india_nse_index_derivatives",
            "max_strategy_allocation_weight": 0.45,
            "max_market_allocation_weight": 0.90,
            "selected_profile": "leadlag",
            "selected_strategy": "lead_lag_taker",
            "selected_market": "india_nse_index_derivatives",
            "selected_eligible": True,
            "selected_allocation_weight": 0.0012,
            "selected_allocation_notional": 1200.0,
            "notional_cap_applied": True,
            **leadlag_lineage(),
        }
        config["limits"]["pre_portfolio_max_notional_per_session"] = 3000.0
        config["limits"]["max_notional_per_session"] = 1200.0
    config.update(overrides)
    return config


def write_scaleup_bundle(root, config):
    root.mkdir(parents=True, exist_ok=True)
    payload = json.loads(json.dumps(config))
    ready = bool(payload.get("ready", False))
    payload["authorizes_submission"] = False
    payload["failed_check_count"] = 0 if ready else 1
    limits = payload.get("limits", {}) or {}
    core = {
        "ready": ready,
        "authorizes_submission": False,
        "target_mode": payload.get("target_mode", ""),
        "strategy": payload.get("strategy", ""),
        "market": payload.get("market", ""),
        "scenario_key": payload.get("scenario_key", ""),
        "adapter": payload.get("adapter", ""),
        "max_orders_per_session": limits.get("max_orders_per_session", 0),
        "max_notional_per_session": limits.get("max_notional_per_session", 0.0),
        "pre_portfolio_max_notional_per_session": limits.get(
            "pre_portfolio_max_notional_per_session",
            limits.get("max_notional_per_session", 0.0),
        ),
    }
    (root / "scaleup_config.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame([core]).to_csv(root / "scaleup_summary.csv", index=False)
    pd.DataFrame([core]).to_csv(root / "scaleup_plan.csv", index=False)
    pd.DataFrame(
        [
            {
                "check": "scaleup_ready",
                "passed": ready,
                "reason": "" if ready else "blocked",
            }
        ]
    ).to_csv(root / "scaleup_checks.csv", index=False)
    source = root.parent / f"{root.name}_source.csv"
    pd.DataFrame([{"source": "fixture"}]).to_csv(source, index=False)
    write_experiment_manifest(
        root,
        run_type="scaleup_plan",
        inputs={"source": source},
        extra={"ready": ready, "authorizes_submission": False},
    )
    return payload


def instrument_metadata_config():
    return {
        "required": True,
        "provided": True,
        "passed": True,
        "parse_coverage": 1.0,
        "min_parse_coverage": 1.0,
        "unparsed_instruments": 0,
    }


def telemetry(**overrides):
    row = {
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "orders_sent": 4,
        "session_notional": 40_000.0,
        "realized_pnl": -500.0,
        "total_failed_component_checks": 0,
        "unmatched_fills": 0,
        "mismatched_orders": 0,
        "overfilled_orders": 0,
        "worst_adverse_slippage": 0.02,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_runtime_guard_continues_when_telemetry_is_inside_limits():
    report = evaluate_runtime_guard(scaleup_config(), telemetry())

    assert not report.halted
    assert report.summary.iloc[0]["guard_action"] == "continue"
    assert report.summary.iloc[0]["target_mode"] == "shadow"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.config is not None
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert set(report.checks["passed"]) == {True}
    assert report.metrics.iloc[0]["max_orders_per_session"] == 10


def test_runtime_guard_halts_on_strategy_or_market_mismatch():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(strategy="imbalance", market="us_equities_regular"),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"strategy_match", "market_match"} <= failed
    summary = report.summary.iloc[0]
    assert summary["strategy"] == "imbalance"
    assert summary["market"] == "us_equities_regular"


def test_runtime_guard_halts_on_limit_and_kill_switch_breaches():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(
            orders_sent=11,
            realized_pnl=-5_500.0,
            unmatched_fills=1,
            worst_adverse_slippage=0.08,
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"orders_sent", "realized_pnl", "unmatched_fills", "worst_adverse_slippage"} <= failed
    summary = report.summary.iloc[0]
    assert "orders_sent" in summary["failed_check_names"].split(";")
    assert summary["first_failed_reason"].startswith("orders_sent:")
    assert "worst_adverse_slippage:" in summary["failed_check_reasons"]
    assert int(summary["action_queue_count"]) >= 1
    assert int(summary["ready_action_count"]) >= 1
    assert summary["next_gate"] == "plan-halt-response"
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "queue_status"] == "ready"
    assert report.action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli plan-halt-response --help"
    assert report.config is not None
    assert report.config["primary_action"]["next_gate"] == "plan-halt-response"


def test_runtime_guard_halts_on_manual_halt_flag():
    report = evaluate_runtime_guard(scaleup_config(manual_halt=True), telemetry())

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "manual_halt" in failed


def test_runtime_guard_continues_when_telemetry_is_fresh():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(snapshot_ts_ns=1_000),
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    assert not report.halted
    row = report.metrics.iloc[0]
    assert row["runtime_telemetry_age_ns"] == 500.0
    assert row["max_telemetry_age_ns"] == 1_000.0


def test_runtime_guard_halts_when_telemetry_is_stale():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(snapshot_ts_ns=1_000),
        as_of_ts_ns=2_500,
        max_telemetry_age_ns=1_000,
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_telemetry_age_ns" in failed


def test_runtime_guard_halts_on_open_order_and_position_breaches():
    config = scaleup_config()
    config["kill_switches"].update(
        {
            "max_open_order_count": 1,
            "max_open_order_qty": 50,
            "max_open_order_notional": 400,
            "max_open_order_age_ns": 500,
            "max_gross_position_qty": 100,
            "max_abs_net_position_qty": 25,
            "max_gross_notional": 1_000,
            "max_abs_net_delta": 40,
            "max_abs_net_vega": 600,
        }
    )

    report = evaluate_runtime_guard(
        config,
        telemetry(
            open_order_count=2,
            open_order_qty=75,
            open_order_notional=500,
            oldest_open_order_age_ns=1_000,
            gross_position_qty=150,
            abs_net_position_qty=50,
            gross_position_notional=1_250,
            abs_net_delta=50,
            abs_net_vega=700,
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "open_order_count",
        "open_order_qty",
        "open_order_notional",
        "oldest_open_order_age_ns",
        "gross_position_qty",
        "abs_net_position_qty",
        "gross_position_notional",
        "abs_net_delta",
        "abs_net_vega",
    } <= failed


def test_runtime_guard_halts_on_lifecycle_and_replace_breaches():
    config = scaleup_config()
    config["kill_switches"].update({"max_lifecycle_orders": 2, "max_replace_orders": 0})

    report = evaluate_runtime_guard(config, telemetry(lifecycle_orders=3, replace_orders=1))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"lifecycle_orders", "replace_orders"} <= failed


def test_runtime_guard_continues_within_open_order_and_position_limits():
    config = scaleup_config()
    config["kill_switches"].update(
        {
            "max_open_order_count": 2,
            "max_open_order_qty": 100,
            "max_open_order_notional": 1_000,
            "max_open_order_age_ns": 2_000,
            "max_gross_position_qty": 200,
            "max_abs_net_position_qty": 75,
            "max_gross_notional": 2_000,
            "max_abs_net_delta": 75,
            "max_abs_net_vega": 800,
        }
    )

    report = evaluate_runtime_guard(
        config,
        telemetry(
            open_order_count=1,
            open_order_qty=50,
            open_order_notional=500,
            oldest_open_order_age_ns=1_000,
            gross_position_qty=100,
            abs_net_position_qty=25,
            gross_position_notional=1_250,
            abs_net_delta=50,
            abs_net_vega=700,
        ),
    )

    assert not report.halted
    assert set(report.checks["passed"]) == {True}


def test_runtime_guard_uses_legacy_limits_for_delta_and_vega():
    config = scaleup_config()
    config["limits"].update({"max_abs_net_delta": 40, "max_abs_net_vega": 600})

    report = evaluate_runtime_guard(config, telemetry(abs_net_delta=50, abs_net_vega=700))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"abs_net_delta", "abs_net_vega"} <= failed


def test_runtime_guard_uses_legacy_limit_for_gross_notional():
    config = scaleup_config()
    config["limits"]["max_gross_notional"] = 1_000

    report = evaluate_runtime_guard(config, telemetry(gross_position_notional=1_250))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "gross_position_notional" in failed


def test_runtime_guard_uses_scaleup_config_telemetry_age_limit():
    config = scaleup_config()
    config["kill_switches"]["max_telemetry_age_ns"] = 1_000

    report = evaluate_runtime_guard(
        config,
        telemetry(snapshot_ts_ns=1_000),
        as_of_ts_ns=2_500,
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_telemetry_age_ns" in failed
    assert report.metrics.iloc[0]["max_telemetry_age_ns"] == 1_000.0


def test_runtime_guard_halts_when_required_instrument_metadata_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(instrument_metadata=instrument_metadata_config()),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_instrument_metadata_provided" in failed


def test_runtime_guard_continues_when_required_instrument_metadata_is_present():
    report = evaluate_runtime_guard(
        scaleup_config(instrument_metadata=instrument_metadata_config()),
        telemetry(
            instrument_metadata_provided=True,
            instrument_metadata_passed=True,
            instrument_parse_coverage=1.0,
            min_instrument_parse_coverage=1.0,
            unparsed_instruments=0,
        ),
    )

    assert not report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed == set()


def test_runtime_guard_halts_when_required_proof_refresh_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(require_proof_refresh=True),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_proof_refresh_provided",
        "runtime_proof_refresh_ready",
        "runtime_proof_refresh_strategy_matches",
        "runtime_proof_refresh_market_matches",
    } <= failed


def test_runtime_guard_continues_with_required_proof_refresh_evidence():
    report = evaluate_runtime_guard(
        scaleup_config(require_proof_refresh=True),
        telemetry(
            proof_refresh_provided=True,
            proof_refresh_ready=True,
            proof_refresh_strategy="leadlag",
            proof_refresh_market="india_nse_index_derivatives",
            proof_refresh_mixed_identity=False,
        ),
    )

    assert not report.halted
    assert set(report.checks.loc[~report.checks["passed"].astype(bool), "check"]) == set()
    assert bool(report.summary.iloc[0]["proof_refresh_ready"])


def test_runtime_guard_halts_when_required_broker_resume_gate_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(require_broker_resume_gate=True),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_broker_resume_gate_provided",
        "runtime_broker_resume_gate_ready",
        "runtime_broker_resume_strategy_matches",
        "runtime_broker_resume_market_matches",
        "runtime_broker_resume_proof_refresh_ready",
        "runtime_broker_resume_proof_refresh_strategy_matches",
        "runtime_broker_resume_proof_refresh_market_matches",
    } <= failed


def test_runtime_guard_continues_with_required_broker_resume_gate_evidence():
    report = evaluate_runtime_guard(
        scaleup_config(require_broker_resume_gate=True),
        telemetry(
            broker_resume_gate_provided=True,
            broker_resume_gate_ready=True,
            broker_resume_strategy="leadlag",
            broker_resume_market="india_nse_index_derivatives",
            broker_resume_proof_refresh_ready=True,
            broker_resume_proof_refresh_strategy="lead_lag_taker",
            broker_resume_proof_refresh_market="india_nse_index_derivatives",
        ),
    )

    assert not report.halted
    assert set(report.checks.loc[~report.checks["passed"].astype(bool), "check"]) == set()
    summary = report.summary.iloc[0]
    assert bool(summary["broker_resume_gate_ready"])
    assert summary["broker_resume_strategy"] == "lead_lag_taker"
    assert summary["broker_resume_proof_refresh_market"] == "india_nse_index_derivatives"


def test_runtime_guard_halts_when_required_broker_route_readiness_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(require_broker_route_readiness=True),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_broker_route_readiness_provided",
        "runtime_broker_route_readiness_ready",
        "runtime_broker_route_readiness_strategy_matches",
        "runtime_broker_route_readiness_market_matches",
        "runtime_broker_route_readiness_route_ready_pairs",
        "runtime_broker_route_readiness_ops_launch_controls_ready",
        "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
    } <= failed


def test_runtime_guard_continues_with_required_broker_route_readiness_evidence():
    report = evaluate_runtime_guard(
        scaleup_config(require_broker_route_readiness=True),
        telemetry(
            broker_route_readiness_provided=True,
            broker_route_readiness_ready=True,
            broker_route_readiness_strategy="leadlag",
            broker_route_readiness_market="india_nse_index_derivatives",
            broker_route_readiness_route_ready_pairs=1,
            broker_route_readiness_gap_pairs=0,
            broker_route_readiness_recommendation="scale_up_with_controls",
            broker_route_readiness_ops_launch_controls_ready=True,
            broker_route_readiness_ops_launch_control_failures="",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
        ),
    )

    assert not report.halted
    assert set(report.checks.loc[~report.checks["passed"].astype(bool), "check"]) == set()
    row = report.metrics.iloc[0]
    summary = report.summary.iloc[0]
    assert row["scaleup_broker_route_readiness_route_ready_pairs"] == 1
    assert row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"] == 1
    assert bool(summary["broker_route_readiness_ready"])
    assert summary["broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["broker_route_readiness_recommendation"] == "scale_up_with_controls"
    assert report.config["broker_route_readiness"]["ops_launch_controls_ready"]


def test_runtime_guard_continues_with_required_strategy_portfolio_allocation():
    report = evaluate_runtime_guard(
        scaleup_config(require_strategy_portfolio=True),
        telemetry(
            session_notional=1_000.0,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_strategy="leadlag",
            strategy_portfolio_selected_market="india_nse_index_derivatives",
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
            strategy_portfolio_notional_cap_applied=True,
            strategy_portfolio_selected_profile="leadlag",
            **leadlag_lineage("strategy_portfolio_"),
        ),
    )

    assert not report.halted
    row = report.metrics.iloc[0]
    summary = report.summary.iloc[0]
    assert row["scaleup_strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert row["runtime_strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert row["scaleup_strategy_portfolio_allocated_strategy_count"] == 2
    assert row["runtime_strategy_portfolio_allocated_strategy_count"] == 2
    assert row["runtime_strategy_portfolio_top_strategy_by_weight"] == "lead_lag_taker"
    assert row["runtime_strategy_portfolio_max_strategy_allocation_weight"] == 0.45
    assert summary["strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert summary["strategy_portfolio_allocated_strategy_count"] == 2
    assert summary["strategy_portfolio_top_strategy_by_weight"] == "lead_lag_taker"
    assert report.config["strategy_portfolio"]["allocated_strategy_count"] == 2
    assert report.config["strategy_portfolio"]["max_strategy_allocation_weight"] == 0.45
    assert bool(
        summary["strategy_portfolio_leadlag_edge_lineage_matches_scaleup"]
    )
    assert summary["strategy_portfolio_leadlag_edge_lineage_contract_sha256"] == (
        "3" * 64
    )
    assert report.config["strategy_portfolio"][
        "leadlag_edge_lineage_contract_version"
    ] == "leadlag_edge_lineage/v1"
    assert bool(summary["strategy_portfolio_notional_cap_applied"])


def test_runtime_guard_halts_when_strategy_portfolio_allocation_is_breached():
    report = evaluate_runtime_guard(
        scaleup_config(require_strategy_portfolio=True),
        telemetry(
            session_notional=1_500.0,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_strategy="leadlag",
            strategy_portfolio_selected_market="india_nse_index_derivatives",
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
            strategy_portfolio_notional_cap_applied=True,
            strategy_portfolio_selected_profile="leadlag",
            **leadlag_lineage("strategy_portfolio_"),
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "session_notional" in failed
    assert "strategy_portfolio_session_notional" in failed
    assert report.summary.iloc[0]["strategy_portfolio_selected_allocation_notional"] == 1200.0


def test_runtime_guard_halts_when_telemetry_drops_required_leadlag_lineage():
    report = evaluate_runtime_guard(
        scaleup_config(require_strategy_portfolio=True),
        telemetry(
            session_notional=1_000.0,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_profile="leadlag",
            strategy_portfolio_selected_strategy="leadlag",
            strategy_portfolio_selected_market="india_nse_index_derivatives",
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
            strategy_portfolio_notional_cap_applied=True,
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_strategy_portfolio_leadlag_edge_lineage_required",
        "runtime_strategy_portfolio_leadlag_edge_lineage_ready",
    } <= failed


def test_runtime_guard_halts_when_leadlag_contract_hash_differs_from_scaleup():
    runtime_lineage = leadlag_lineage("strategy_portfolio_")
    runtime_lineage[
        "strategy_portfolio_leadlag_edge_lineage_contract_sha256"
    ] = "f" * 64
    report = evaluate_runtime_guard(
        scaleup_config(require_strategy_portfolio=True),
        telemetry(
            session_notional=1_000.0,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_profile="leadlag",
            strategy_portfolio_selected_strategy="leadlag",
            strategy_portfolio_selected_market="india_nse_index_derivatives",
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
            strategy_portfolio_notional_cap_applied=True,
            **runtime_lineage,
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "runtime_strategy_portfolio_leadlag_edge_lineage_contract_sha256_matches_scaleup"
        in failed
    )
    assert not bool(
        report.summary.iloc[0][
            "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
        ]
    )


def test_runtime_guard_halts_on_bad_strategy_portfolio_identity():
    config = scaleup_config(require_strategy_portfolio=True)
    config["strategy_portfolio"].update(
        {
            "ready": False,
            "selected_strategy": "surface_mm",
            "selected_market": "us_options_regular",
            "selected_eligible": False,
            "selected_allocation_notional": 0.0,
        }
    )

    report = evaluate_runtime_guard(config, telemetry(session_notional=0.0))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_strategy_portfolio_ready",
        "scaleup_strategy_portfolio_allocation_eligible",
        "scaleup_strategy_portfolio_strategy_matches",
        "scaleup_strategy_portfolio_market_matches",
        "scaleup_strategy_portfolio_allocation_notional",
    } <= failed


def test_write_runtime_guard_outputs_artifacts(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry().to_csv(telemetry_path, index=False)

    report = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry_path,
        output_dir=out_dir,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "runtime_guard_metrics.csv").exists()
    assert (out_dir / "runtime_guard_checks.csv").exists()
    assert (out_dir / "runtime_guard_summary.csv").exists()
    assert (out_dir / "runtime_guard_action_queue.csv").exists()
    assert (out_dir / "runtime_guard_config.json").exists()
    assert (out_dir / "runtime_guard_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    saved_summary = pd.read_csv(out_dir / "runtime_guard_summary.csv")
    assert int(saved_summary.loc[0, "action_queue_count"]) == 0
    saved_config = json.loads((out_dir / "runtime_guard_config.json").read_text(encoding="utf-8"))
    assert saved_config["action_queue_count"] == 0
    assert saved_config["next_actions"] == []
    assert (out_dir / "runtime_guard_runbook.md").read_text(encoding="utf-8").startswith(
        "# Runtime Guard Runbook"
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert any(path.endswith("runtime_guard_action_queue.csv") for path in artifact_paths)
    assert any(path.endswith("runtime_guard_config.json") for path in artifact_paths)
    assert any(path.endswith("runtime_guard_runbook.md") for path in artifact_paths)
    assert manifest["extra"]["scaleup_provenance_gate_passed"]
    assert not manifest["extra"]["authorizes_submission"]
    assert not saved_config["authorizes_submission"]


def test_runtime_guard_halts_when_scaleup_inputs_drift_after_telemetry(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    telemetry_dir = tmp_path / "telemetry"
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry().to_csv(telemetry_dir.with_suffix(".csv"), index=False)
    source = tmp_path / "scaleup_source.csv"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry_dir.with_suffix(".csv"),
        output_dir=tmp_path / "guard_drifted",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert report.halted
    assert {
        "scaleup_manifest_current",
        "scaleup_provenance_gate_passed",
    } <= failed


def test_runtime_guard_rejects_scaleup_or_telemetry_output_collision(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    telemetry_dir = tmp_path / "telemetry"
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry_dir.mkdir()
    telemetry().to_csv(telemetry_dir / "runtime_telemetry.csv", index=False)

    for output_dir in (scaleup_dir, telemetry_dir):
        try:
            write_runtime_guard_report(
                scaleup_dir=scaleup_dir,
                telemetry_path=telemetry_dir,
                output_dir=output_dir,
            )
        except ValueError as exc:
            assert "must not overwrite" in str(exc)
        else:
            raise AssertionError("runtime guard output collision was not rejected")


def test_cli_runtime_guard_can_fail_on_halt(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry(orders_sent=12).to_csv(telemetry_path, index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_path),
            "--out",
            str(out_dir),
            "--fail-on-halt",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_guard_summary.csv")
    queue = pd.read_csv(out_dir / "runtime_guard_action_queue.csv")
    saved_config = json.loads((out_dir / "runtime_guard_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert summary.loc[0, "guard_action"] == "halt"
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "ready_action_count"]) == 1
    assert queue.loc[0, "check"] == "orders_sent"
    assert queue.loc[0, "component"] == "runtime_limits"
    assert queue.loc[0, "next_gate"] == "plan-halt-response"
    assert saved_config["ready_actions"][0]["check"] == "orders_sent"


def test_cli_runtime_guard_can_fail_on_actions(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry(orders_sent=12).to_csv(telemetry_path, index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_path),
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )

    queue = pd.read_csv(out_dir / "runtime_guard_action_queue.csv")
    assert code == 2
    assert len(queue) == 1
    assert queue.loc[0, "next_gate"] == "plan-halt-response"


def test_cli_runtime_guard_reads_runtime_telemetry_output_dir(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    telemetry_dir = tmp_path / "telemetry"
    out_dir = tmp_path / "guard"
    scaleup_dir.mkdir()
    telemetry_dir.mkdir()
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry().to_csv(telemetry_dir / "runtime_telemetry.csv", index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_dir),
            "--out",
            str(out_dir),
            "--fail-on-halt",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_guard_summary.csv")
    assert code == 0
    assert summary.loc[0, "guard_action"] == "continue"


def test_cli_runtime_guard_can_fail_on_stale_telemetry(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    write_scaleup_bundle(scaleup_dir, scaleup_config())
    telemetry(snapshot_ts_ns=1_000).to_csv(telemetry_path, index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_path),
            "--out",
            str(out_dir),
            "--as-of-ts-ns",
            "3000",
            "--max-telemetry-age-ns",
            "1000",
            "--fail-on-halt",
        ]
    )

    checks = pd.read_csv(out_dir / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_telemetry_age_ns" in failed
