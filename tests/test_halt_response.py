import json

import pandas as pd
import pytest

from hft_cli import main
from reports.halt_response import evaluate_halt_response, write_halt_response_plan
from reports.manifest import verify_experiment_manifest, write_experiment_manifest


def path_tail(value):
    return str(value).replace("\\", "/")


def guard_summary(action="halt"):
    return pd.DataFrame(
        [
            {
                "guard_action": action,
                "halted": action == "halt",
                "failed_checks": 1 if action == "halt" else 0,
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "proof_refresh_required": True,
                "proof_refresh_provided": True,
                "proof_refresh_ready": True,
                "proof_refresh_strategy": "lead_lag_taker",
                "proof_refresh_market": "india_nse_index_derivatives",
                "proof_refresh_mixed_identity": False,
                "proof_source": "latest",
                "broker_route_readiness_required": True,
                "broker_route_readiness_provided": True,
                "broker_route_readiness_ready": True,
                "broker_route_readiness_strategy": "lead_lag_taker",
                "broker_route_readiness_market": "india_nse_index_derivatives",
                "broker_route_readiness_route_ready_pairs": 1,
                "broker_route_readiness_gap_pairs": 0,
                "broker_route_readiness_recommendation": "scale_up_with_controls",
                "broker_route_readiness_ops_launch_controls_ready": True,
                "broker_route_readiness_ops_launch_control_failures": "",
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": 1,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": 0,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
                "scaleup_manifest_required": True,
                "scaleup_manifest_provided": True,
                "scaleup_manifest_current": False,
                "scaleup_manifest_run_type": "scaleup_plan",
                "scaleup_manifest_path": "/research/scaleup/manifest.json",
                "scaleup_manifest_sha256": "scaleup-manifest-hash",
                "scaleup_manifest_error": "input_drift",
                "scaleup_contract_consistent": True,
                "scaleup_non_authorizing": True,
                "scaleup_source_ready": True,
                "scaleup_provenance_gate_passed": False,
                "scaleup_dependency_count": 7,
                "scaleup_research_family_bound": True,
                "scaleup_research_family_provenance_current": False,
                "scaleup_research_family_id": "prospective_family",
                "scaleup_research_family_registration_id": "registration-1",
                "scaleup_research_family_manifest_sha256": "family-manifest-hash",
                "runtime_telemetry_scaleup_provenance_carried": True,
                "runtime_telemetry_scaleup_provenance_gate_passed": True,
                "runtime_telemetry_scaleup_manifest_sha256": "scaleup-manifest-hash",
                "runtime_telemetry_scaleup_manifest_matches_current": True,
                "runtime_telemetry_research_family_bound": True,
                "runtime_telemetry_research_family_provenance_current": True,
                "runtime_telemetry_research_family_id": "prospective_family",
                "runtime_telemetry_research_family_registration_id": "registration-1",
                "runtime_telemetry_research_family_manifest_sha256": "family-manifest-hash",
                "runtime_telemetry_research_family_matches_current": False,
                "runtime_telemetry_lineage_matches_current": False,
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "recommendation": "stop_routing_and_investigate" if action == "halt" else "continue_with_controls",
            }
        ]
    )


def guard_checks():
    return pd.DataFrame(
        [
            {
                "check": "orders_sent",
                "value": 11,
                "operator": "<=",
                "threshold": 10,
                "passed": False,
                "reason": "orders_sent 11 failed <= 10",
            }
        ]
    )


def open_orders():
    return pd.DataFrame(
        [
            {
                "client_order_id": "STG-1",
                "broker_order_id": "ARW-1",
                "instrument_id": "NIFTY_C_22000",
                "side": 1,
                "qty": 75,
                "filled_qty": 25,
                "status": "PARTIAL",
            },
            {
                "client_order_id": "STG-2",
                "broker_order_id": "ARW-2",
                "instrument_id": "NIFTY_P_22000",
                "side": -1,
                "qty": 75,
                "filled_qty": 75,
                "status": "filled",
            },
        ]
    )


def positions():
    return pd.DataFrame(
        [
            {"instrument_id": "NIFTY_C_22000", "net_qty": 75, "market_bid": 11.2, "market_ask": 11.5},
            {"instrument_id": "NIFTY_P_22000", "net_qty": -50, "market_bid": 8.9, "market_ask": 9.1},
        ]
    )


def test_halt_response_builds_cancel_and_flatten_actions():
    report = evaluate_halt_response(
        guard_summary(),
        guard_checks(),
        open_orders=open_orders(),
        positions=positions(),
    )

    assert report.ready
    assert len(report.cancel_orders) == 1
    assert len(report.flatten_orders) == 2
    assert report.cancel_orders.iloc[0]["open_qty"] == 50
    assert report.cancel_orders.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.cancel_orders.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.cancel_orders.iloc[0]["proof_refresh_strategy"] == "lead_lag_taker"
    assert bool(report.cancel_orders.iloc[0]["proof_refresh_ready"])
    assert report.cancel_orders.iloc[0]["proof_source"] == "latest"
    assert report.cancel_orders.iloc[0]["broker_route_readiness_strategy"] == "lead_lag_taker"
    assert bool(report.cancel_orders.iloc[0]["broker_route_readiness_ready"])
    assert int(report.cancel_orders.iloc[0]["broker_route_readiness_gap_pairs"]) == 0
    assert bool(report.cancel_orders.iloc[0]["broker_route_readiness_ops_launch_controls_ready"])
    assert report.cancel_orders.iloc[0]["scaleup_manifest_sha256"] == "scaleup-manifest-hash"
    assert report.cancel_orders.iloc[0]["scaleup_research_family_id"] == "prospective_family"
    assert not bool(report.cancel_orders.iloc[0]["scaleup_provenance_gate_passed"])
    assert not bool(report.cancel_orders.iloc[0]["runtime_telemetry_lineage_matches_current"])
    assert report.cancel_orders.iloc[0]["guard_failed_check_names"] == "orders_sent"
    assert report.cancel_orders.iloc[0]["guard_first_failed_reason"].startswith("orders_sent:")
    assert report.flatten_orders["side_text"].tolist() == ["SELL", "BUY"]
    assert report.flatten_orders["strategy"].tolist() == ["lead_lag_taker", "lead_lag_taker"]
    assert report.flatten_orders["market"].tolist() == ["india_nse_index_derivatives", "india_nse_index_derivatives"]
    assert report.flatten_orders["proof_refresh_market"].tolist() == [
        "india_nse_index_derivatives",
        "india_nse_index_derivatives",
    ]
    assert report.flatten_orders["broker_route_readiness_market"].tolist() == [
        "india_nse_index_derivatives",
        "india_nse_index_derivatives",
    ]
    assert report.flatten_orders["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"].tolist() == [
        1,
        1,
    ]
    assert report.flatten_orders["scaleup_research_family_manifest_sha256"].tolist() == [
        "family-manifest-hash",
        "family-manifest-hash",
    ]
    assert report.flatten_orders["price"].tolist() == [11.2, 9.1]
    assert report.flatten_orders["guard_failed_check_names"].tolist() == ["orders_sent", "orders_sent"]
    assert report.summary.iloc[0]["recommendation"] == "submit_cancel_and_flatten"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert bool(report.summary.iloc[0]["proof_refresh_required"])
    assert bool(report.summary.iloc[0]["proof_refresh_provided"])
    assert bool(report.summary.iloc[0]["proof_refresh_ready"])
    assert report.summary.iloc[0]["proof_refresh_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["proof_refresh_market"] == "india_nse_index_derivatives"
    assert not bool(report.summary.iloc[0]["proof_refresh_mixed_identity"])
    assert report.summary.iloc[0]["proof_source"] == "latest"
    assert bool(report.summary.iloc[0]["broker_route_readiness_required"])
    assert bool(report.summary.iloc[0]["broker_route_readiness_provided"])
    assert bool(report.summary.iloc[0]["broker_route_readiness_ready"])
    assert report.summary.iloc[0]["broker_route_readiness_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["broker_route_readiness_market"] == "india_nse_index_derivatives"
    assert int(report.summary.iloc[0]["broker_route_readiness_route_ready_pairs"]) == 1
    assert int(report.summary.iloc[0]["broker_route_readiness_gap_pairs"]) == 0
    assert bool(report.summary.iloc[0]["broker_route_readiness_ops_launch_controls_ready"])
    assert int(report.summary.iloc[0]["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    assert (
        int(report.summary.iloc[0]["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"])
        == 1
    )
    assert report.summary.iloc[0]["guard_failed_check_names"] == "orders_sent"
    assert report.summary.iloc[0]["guard_first_failed_reason"].startswith("orders_sent:")
    assert report.summary.iloc[0]["scaleup_research_family_id"] == "prospective_family"
    assert not bool(report.summary.iloc[0]["runtime_telemetry_lineage_matches_current"])
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert report.summary.iloc[0]["failed_check_names"] == ""
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert int(report.summary.iloc[0]["blocked_action_count"]) == 0
    assert report.summary.iloc[0]["next_gate"] == ""
    assert report.summary.iloc[0]["primary_action_status"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.config["guard_failed_checks"] == ["orders_sent"]
    assert report.config["failed_check_count"] == 0
    assert report.config["failed_checks"] == []
    assert report.config["primary_blocker"] == {}
    assert report.config["action_queue_count"] == 0
    assert report.config["next_gate"] == ""
    assert report.config["primary_action"] == {}
    assert report.config["next_actions"] == []
    assert report.config["blocked_actions"] == []
    assert report.config["strategy"] == "lead_lag_taker"
    assert report.config["market"] == "india_nse_index_derivatives"
    assert not report.config["authorizes_submission"]
    assert report.config["scaleup_provenance"]["scaleup_manifest_sha256"] == "scaleup-manifest-hash"
    assert not report.config["scaleup_provenance"]["scaleup_provenance_gate_passed"]
    assert report.config["runtime_telemetry_lineage"]["runtime_telemetry_research_family_id"] == (
        "prospective_family"
    )
    assert not report.config["runtime_telemetry_lineage"]["runtime_telemetry_lineage_matches_current"]
    assert report.config["proof_freshness"] == {
        "required": True,
        "provided": True,
        "ready": True,
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "mixed_identity": False,
        "proof_source": "latest",
    }
    assert report.config["broker_route_readiness"] == {
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


def test_halt_response_fails_when_guard_not_halted_by_default():
    report = evaluate_halt_response(guard_summary("continue"))

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed == {"guard_halted"}
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] == "guard_halted"
    assert not report.config["primary_blocker"]["passed"]
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "component"] == "runtime_guard"
    assert report.action_queue.loc[0, "next_gate"] == "monitor-scaleup-guard"
    assert report.config["primary_action"]["check"] == "guard_halted"
    assert report.summary.iloc[0]["primary_blocker_check"] == "guard_halted"
    assert report.summary.iloc[0]["next_gate"] == "monitor-scaleup-guard"


def test_write_halt_response_plan_outputs_artifacts(tmp_path):
    guard_dir = tmp_path / "guard"
    out_dir = tmp_path / "response"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    guard_dir.mkdir()
    guard_summary().to_csv(guard_dir / "runtime_guard_summary.csv", index=False)
    guard_checks().to_csv(guard_dir / "runtime_guard_checks.csv", index=False)
    guard_source = tmp_path / "guard_source.csv"
    pd.DataFrame([{"source": "scaleup"}]).to_csv(guard_source, index=False)
    write_experiment_manifest(
        guard_dir,
        run_type="runtime_guard",
        inputs={"scaleup_dependency": guard_source},
        extra={"authorizes_submission": False},
    )
    open_orders().to_csv(open_orders_path, index=False)
    positions().to_csv(positions_path, index=False)

    report = write_halt_response_plan(
        guard_dir=guard_dir,
        output_dir=out_dir,
        open_orders_path=open_orders_path,
        positions_path=positions_path,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "halt_cancel_orders.csv").exists()
    assert (out_dir / "halt_flatten_orders.csv").exists()
    assert (out_dir / "halt_response_checks.csv").exists()
    assert (out_dir / "halt_response_summary.csv").exists()
    assert (out_dir / "halt_response_action_queue.csv").exists()
    assert (out_dir / "halt_response_runbook.md").exists()
    assert (out_dir / "halt_response_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    saved_config = json.loads((out_dir / "halt_response_config.json").read_text(encoding="utf-8"))
    assert saved_config["guard_failed_checks"] == ["orders_sent"]
    assert saved_config["failed_check_count"] == 0
    assert saved_config["primary_blocker"] == {}
    assert saved_config["action_queue_count"] == 0
    assert saved_config["next_actions"] == []
    assert saved_config["proof_freshness"]["strategy"] == "lead_lag_taker"
    assert saved_config["proof_freshness"]["ready"]
    assert not saved_config["authorizes_submission"]
    assert saved_config["scaleup_provenance"]["scaleup_manifest_sha256"] == "scaleup-manifest-hash"
    saved_summary = pd.read_csv(out_dir / "halt_response_summary.csv")
    assert saved_summary.loc[0, "guard_failed_check_names"] == "orders_sent"
    assert saved_summary.loc[0, "proof_refresh_strategy"] == "lead_lag_taker"
    assert bool(saved_summary.loc[0, "proof_refresh_ready"])
    assert int(saved_summary.loc[0, "action_queue_count"]) == 0
    assert (out_dir / "halt_response_runbook.md").read_text(encoding="utf-8").startswith(
        "# Halt Response Runbook"
    )
    runbook = (out_dir / "halt_response_runbook.md").read_text(encoding="utf-8")
    assert "Research family: prospective_family" in runbook
    assert "Submission authorization: no" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "guard_summary",
        "guard_checks",
        "guard_manifest",
        "guard_dependencies",
        "open_orders",
        "positions",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["guard_summary"]["path"]).endswith(
        "/guard/runtime_guard_summary.csv"
    )
    assert path_tail(manifest["inputs"]["guard_checks"]["path"]).endswith(
        "/guard/runtime_guard_checks.csv"
    )
    assert path_tail(manifest["inputs"]["open_orders"]["path"]).endswith("/open_orders.csv")
    assert path_tail(manifest["inputs"]["positions"]["path"]).endswith("/positions.csv")
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert any(path.endswith("halt_response_action_queue.csv") for path in artifact_paths)
    assert any(path.endswith("halt_response_runbook.md") for path in artifact_paths)
    assert manifest["extra"]["scaleup_research_family_id"] == "prospective_family"
    assert not manifest["extra"]["authorizes_submission"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="halt_response_plan",
        require_input_fingerprints=True,
    ).passed
    guard_source.write_text("source\nchanged\n", encoding="utf-8")
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="halt_response_plan",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_halt_response_rejects_guard_output_collision(tmp_path):
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()
    guard_summary().to_csv(guard_dir / "runtime_guard_summary.csv", index=False)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_halt_response_plan(guard_dir=guard_dir, output_dir=guard_dir)


def test_cli_halt_response_can_fail_on_missing_flatten_price(tmp_path):
    guard_dir = tmp_path / "guard"
    out_dir = tmp_path / "response"
    positions_path = tmp_path / "positions.csv"
    guard_dir.mkdir()
    guard_summary().to_csv(guard_dir / "runtime_guard_summary.csv", index=False)
    pd.DataFrame([{"instrument_id": "NIFTY_C_22000", "net_qty": 75}]).to_csv(positions_path, index=False)

    code = main(
        [
            "plan-halt-response",
            "--guard",
            str(guard_dir),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "halt_response_summary.csv")
    queue = pd.read_csv(out_dir / "halt_response_action_queue.csv")
    saved_config = json.loads((out_dir / "halt_response_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert int(summary.loc[0, "failed_checks"]) == 1
    assert int(summary.loc[0, "failed_check_count"]) == 1
    assert summary.loc[0, "failed_check_names"] == "flatten_prices_available"
    assert summary.loc[0, "primary_blocker_check"] == "flatten_prices_available"
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert summary.loc[0, "next_gate"] == "plan-halt-response"
    assert queue.loc[0, "component"] == "flatten_price_inputs"
    assert queue.loc[0, "check"] == "flatten_prices_available"
    assert queue.loc[0, "next_gate"] == "plan-halt-response"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli plan-halt-response --help"
    assert saved_config["primary_action"]["check"] == "flatten_prices_available"
    assert saved_config["blocked_actions"][0]["component"] == "flatten_price_inputs"
    assert "flatten_prices_available" in (out_dir / "halt_response_runbook.md").read_text(encoding="utf-8")


def test_cli_halt_response_can_fail_on_actions(tmp_path):
    guard_dir = tmp_path / "guard"
    out_dir = tmp_path / "response"
    positions_path = tmp_path / "positions.csv"
    guard_dir.mkdir()
    guard_summary().to_csv(guard_dir / "runtime_guard_summary.csv", index=False)
    pd.DataFrame([{"instrument_id": "NIFTY_C_22000", "net_qty": 75}]).to_csv(positions_path, index=False)

    code = main(
        [
            "plan-halt-response",
            "--guard",
            str(guard_dir),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )

    queue = pd.read_csv(out_dir / "halt_response_action_queue.csv")
    assert code == 2
    assert len(queue) == 1
    assert queue.loc[0, "check"] == "flatten_prices_available"
