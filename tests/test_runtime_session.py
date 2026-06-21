import json

import pandas as pd

from hft_cli import main
from reports.runtime_session import write_runtime_session_monitor


def path_tail(value):
    return str(value).replace("\\", "/")


def scaleup_config(
    require_proof_refresh=False,
    require_broker_resume_gate=False,
    require_broker_route_readiness=False,
    require_strategy_portfolio=False,
    **kill_switch_overrides,
):
    kill_switches = {
        "max_total_failed_component_checks": 0,
        "max_total_unmatched_fills": 0,
        "max_total_mismatched_orders": 0,
        "max_total_overfilled_orders": 0,
        "max_worst_adverse_slippage": 0.05,
        "max_open_order_count": 2,
        "max_open_order_qty": 100,
        "max_gross_position_qty": 200,
        "max_abs_net_position_qty": 100,
    }
    kill_switches.update(kill_switch_overrides)
    config = {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "strategy": "surface_mm",
        "market": "india_nse_index_derivatives",
        "scenario_key": "surface_mm:demo",
        "adapter": "arrow_money",
        "identity": {
            "strategy": "surface_mm",
            "market": "india_nse_index_derivatives",
            "expected_strategy": "surface_mm",
            "expected_market": "india_nse_index_derivatives",
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": kill_switches,
    }
    if require_proof_refresh:
        config["proof_freshness"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "surface_mm",
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
            "strategy": "surface_mm",
            "market": "india_nse_index_derivatives",
            "incident_strategy": "surface_mm",
            "incident_market": "india_nse_index_derivatives",
            "proof_refresh_ready": True,
            "proof_refresh_strategy": "surface_mm",
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
            "strategy": "surface_mm",
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
        config["limits"]["pre_portfolio_max_notional_per_session"] = 100_000.0
        config["limits"]["max_notional_per_session"] = 1200.0
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
            "top_strategy_by_weight": "surface_mm",
            "top_market_by_weight": "india_nse_index_derivatives",
            "max_strategy_allocation_weight": 0.45,
            "max_market_allocation_weight": 0.90,
            "selected_profile": "surface-mm-demo",
            "selected_strategy": "surface_mm",
            "selected_market": "india_nse_index_derivatives",
            "selected_eligible": True,
            "selected_allocation_weight": 0.0012,
            "selected_allocation_notional": 1200.0,
            "notional_cap_applied": True,
        }
    return config


def write_scaleup_dir(path, config=None):
    path.mkdir()
    (path / "scaleup_config.json").write_text(
        json.dumps(config or scaleup_config(), indent=2) + "\n",
        encoding="utf-8",
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
                "limit_price": 10.0,
                "created_ts_ns": 1_000,
                "status": "PARTIAL",
            }
        ]
    )


def positions():
    return pd.DataFrame(
        [
            {
                "instrument_id": "NIFTY_C_22000",
                "net_qty": 75,
                "unit_delta": 0.75,
                "unit_vega": 12.0,
                "market_bid": 11.2,
                "market_ask": 11.5,
            },
        ]
    )


def upload_summary():
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": "arrow_money",
                "orders": 4,
                "lifecycle_orders": 3,
                "replace_orders": 2,
                "failed_checks": 0,
            }
        ]
    )


def test_runtime_session_monitor_continues_when_guard_passes(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir)

    report = write_runtime_session_monitor(
        scaleup_dir=scaleup_dir,
        output_dir=out_dir,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    assert report.ready
    assert (out_dir / "01_telemetry" / "runtime_telemetry.csv").exists()
    assert (out_dir / "02_guard" / "runtime_guard_summary.csv").exists()
    assert not (out_dir / "03_halt_response").exists()
    assert (out_dir / "runtime_session_steps.csv").exists()
    assert (out_dir / "runtime_session_summary.csv").exists()
    assert (out_dir / "runtime_session_action_queue.csv").exists()
    assert (out_dir / "runtime_session_config.json").exists()
    assert (out_dir / "runtime_session_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    assert report.summary.loc[0, "guard_action"] == "continue"
    assert report.summary.loc[0, "target_mode"] == "shadow"
    assert report.summary.loc[0, "strategy"] == "surface_mm"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert int(report.summary.loc[0, "action_queue_count"]) == 0
    assert int(report.summary.loc[0, "blocked_action_count"]) == 0
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.config is not None
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.steps["step"].tolist() == ["telemetry", "runtime_guard"]
    assert set(report.steps["strategy"]) == {"surface_mm"}
    assert set(report.steps["market"]) == {"india_nse_index_derivatives"}
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "scaleup",
        "telemetry",
        "telemetry_sources",
        "telemetry_checks",
        "telemetry_summary",
        "telemetry_manifest",
        "guard_metrics",
        "guard_checks",
        "guard_summary",
        "guard_manifest",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["scaleup"]["path"]).endswith("/scaleup/scaleup_config.json")
    assert path_tail(manifest["inputs"]["telemetry"]["path"]).endswith(
        "/session/01_telemetry/runtime_telemetry.csv"
    )
    assert path_tail(manifest["inputs"]["guard_summary"]["path"]).endswith(
        "/session/02_guard/runtime_guard_summary.csv"
    )
    assert "halt_response_summary" not in manifest["inputs"]
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert any(path.endswith("runtime_session_action_queue.csv") for path in artifact_paths)
    assert any(path.endswith("runtime_session_config.json") for path in artifact_paths)
    assert any(path.endswith("runtime_session_runbook.md") for path in artifact_paths)


def test_runtime_session_monitor_carries_proof_refresh_state(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir, scaleup_config(require_proof_refresh=True))

    report = write_runtime_session_monitor(
        scaleup_dir=scaleup_dir,
        output_dir=out_dir,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(summary["proof_refresh_required"])
    assert bool(summary["proof_refresh_provided"])
    assert bool(summary["proof_refresh_ready"])
    assert summary["proof_refresh_strategy"] == "surface_mm"
    assert summary["proof_refresh_market"] == "india_nse_index_derivatives"
    assert not bool(summary["proof_refresh_mixed_identity"])
    assert summary["proof_source"] == "latest"
    assert set(report.steps["proof_refresh_strategy"]) == {"surface_mm"}
    assert set(report.steps["proof_refresh_market"]) == {"india_nse_index_derivatives"}


def test_runtime_session_monitor_carries_broker_resume_gate_state(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir, scaleup_config(require_broker_resume_gate=True))

    report = write_runtime_session_monitor(
        scaleup_dir=scaleup_dir,
        output_dir=out_dir,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(summary["broker_resume_gate_required"])
    assert bool(summary["broker_resume_gate_provided"])
    assert bool(summary["broker_resume_gate_ready"])
    assert summary["broker_resume_strategy"] == "surface_mm"
    assert summary["broker_resume_market"] == "india_nse_index_derivatives"
    assert bool(summary["broker_resume_proof_refresh_ready"])
    assert summary["broker_resume_proof_refresh_strategy"] == "surface_mm"
    assert set(report.steps["broker_resume_strategy"]) == {"surface_mm"}
    assert set(report.steps["broker_resume_proof_refresh_market"]) == {"india_nse_index_derivatives"}


def test_runtime_session_monitor_carries_broker_route_readiness_state(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir, scaleup_config(require_broker_route_readiness=True))

    report = write_runtime_session_monitor(
        scaleup_dir=scaleup_dir,
        output_dir=out_dir,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(summary["broker_route_readiness_required"])
    assert bool(summary["broker_route_readiness_provided"])
    assert bool(summary["broker_route_readiness_ready"])
    assert summary["broker_route_readiness_strategy"] == "surface_mm"
    assert summary["broker_route_readiness_market"] == "india_nse_index_derivatives"
    assert summary["broker_route_readiness_route_ready_pairs"] == 1
    assert summary["broker_route_readiness_gap_pairs"] == 0
    assert bool(summary["broker_route_readiness_ops_launch_controls_ready"])
    assert summary["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"] == 1
    assert summary["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"] == 1
    assert set(report.steps["broker_route_readiness_strategy"]) == {"surface_mm"}
    assert set(report.steps["broker_route_readiness_gap_pairs"]) == {0}
    assert report.config["broker_route_readiness"]["ops_launch_controls_ready"]
    assert report.config["broker_route_readiness"]["ops_broker_roundtrip_portfolio_safe_runs"] == 1


def test_runtime_session_monitor_carries_strategy_portfolio_allocation(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir, scaleup_config(require_strategy_portfolio=True))

    report = write_runtime_session_monitor(
        scaleup_dir=scaleup_dir,
        output_dir=out_dir,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(summary["strategy_portfolio_required"])
    assert bool(summary["strategy_portfolio_provided"])
    assert bool(summary["strategy_portfolio_ready"])
    assert summary["strategy_portfolio_deployment_mode"] == "paper_shadow"
    assert summary["strategy_portfolio_allocation_mode"] == "readiness_weighted"
    assert summary["strategy_portfolio_capital_currency"] == "INR"
    assert summary["strategy_portfolio_selected_profile"] == "surface-mm-demo"
    assert summary["strategy_portfolio_selected_strategy"] == "surface_mm"
    assert summary["strategy_portfolio_selected_market"] == "india_nse_index_derivatives"
    assert bool(summary["strategy_portfolio_selected_eligible"])
    assert summary["strategy_portfolio_selected_allocation_weight"] == 0.0012
    assert summary["strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert bool(summary["strategy_portfolio_notional_cap_applied"])
    assert summary["strategy_portfolio_allocated_strategy_count"] == 2
    assert summary["strategy_portfolio_allocated_market_count"] == 1
    assert summary["strategy_portfolio_top_strategy_by_weight"] == "surface_mm"
    assert summary["strategy_portfolio_max_strategy_allocation_weight"] == 0.45
    assert summary["pre_portfolio_max_notional_per_session"] == 100_000.0
    assert set(report.steps["strategy_portfolio_selected_strategy"]) == {"surface_mm"}
    assert set(report.steps["strategy_portfolio_selected_market"]) == {"india_nse_index_derivatives"}
    assert set(report.steps["strategy_portfolio_selected_allocation_notional"]) == {1200.0}
    assert set(report.steps["strategy_portfolio_allocated_strategy_count"]) == {2}
    assert set(report.steps["strategy_portfolio_top_strategy_by_weight"]) == {"surface_mm"}


def test_cli_runtime_session_monitor_builds_halt_response_on_guard_halt(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_open_order_count=0))
    open_orders().to_csv(open_orders_path, index=False)
    positions().to_csv(positions_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--open-orders",
            str(open_orders_path),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_session_summary.csv")
    steps = pd.read_csv(out_dir / "runtime_session_steps.csv")
    response = pd.read_csv(out_dir / "03_halt_response" / "halt_response_summary.csv")
    queue = pd.read_csv(out_dir / "runtime_session_action_queue.csv")
    config = json.loads((out_dir / "runtime_session_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "halt_response_created"])
    assert bool(summary.loc[0, "halt_response_ready"])
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "ready_action_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert summary.loc[0, "next_gate"] == "export-halt-response"
    assert summary.loc[0, "target_mode"] == "shadow"
    assert summary.loc[0, "strategy"] == "surface_mm"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "guard_failed_check_names"] == "open_order_count"
    assert queue.loc[0, "queue_status"] == "ready"
    assert queue.loc[0, "component"] == "halt_response"
    assert queue.loc[0, "check"] == "guard_halted"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli export-halt-response --help"
    assert config["primary_action"]["check"] == "guard_halted"
    assert config["ready_actions"][0]["next_gate"] == "export-halt-response"
    assert steps.loc[1, "failed_check_names"] == "open_order_count"
    assert set(steps["strategy"]) == {"surface_mm"}
    assert set(steps["market"]) == {"india_nse_index_derivatives"}
    assert response.loc[0, "guard_failed_check_names"] == "open_order_count"
    assert summary.loc[0, "recommendation"] == "stop_routing_and_execute_halt_response"
    assert steps["step"].tolist() == ["telemetry", "runtime_guard", "halt_response"]
    assert response.loc[0, "recommendation"] == "submit_cancel_and_flatten"
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "open_orders",
        "positions",
        "halt_cancel_orders",
        "halt_flatten_orders",
        "halt_response_checks",
        "halt_response_summary",
        "halt_response_action_queue",
        "halt_response_runbook",
        "halt_response_config",
        "halt_response_manifest",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["open_orders"]["path"]).endswith("/open_orders.csv")
    assert path_tail(manifest["inputs"]["positions"]["path"]).endswith("/positions.csv")
    assert path_tail(manifest["inputs"]["halt_response_summary"]["path"]).endswith(
        "/session/03_halt_response/halt_response_summary.csv"
    )
    assert "guard_halted" in (out_dir / "runtime_session_runbook.md").read_text(encoding="utf-8")


def test_cli_runtime_session_monitor_can_fail_on_actions(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_open_order_count=0))
    open_orders().to_csv(open_orders_path, index=False)
    positions().to_csv(positions_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--open-orders",
            str(open_orders_path),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )

    queue = pd.read_csv(out_dir / "runtime_session_action_queue.csv")
    assert code == 2
    assert len(queue) == 1
    assert queue.loc[0, "queue_status"] == "ready"
    assert queue.loc[0, "next_gate"] == "export-halt-response"


def test_cli_runtime_session_monitor_halts_on_open_order_notional_limit(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    open_orders_path = tmp_path / "open_orders.csv"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_open_order_notional=400))
    open_orders().to_csv(open_orders_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--open-orders",
            str(open_orders_path),
            "--out",
            str(out_dir),
            "--skip-halt-response",
            "--fail-on-breach",
        ]
    )

    telemetry = pd.read_csv(out_dir / "01_telemetry" / "runtime_telemetry.csv")
    checks = pd.read_csv(out_dir / "02_guard" / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert telemetry.loc[0, "open_order_notional"] == 500.0
    assert "open_order_notional" in failed


def test_cli_runtime_session_monitor_halts_on_stale_open_order(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    open_orders_path = tmp_path / "open_orders.csv"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_open_order_age_ns=500))
    open_orders().to_csv(open_orders_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--open-orders",
            str(open_orders_path),
            "--snapshot-ts-ns",
            "2000",
            "--out",
            str(out_dir),
            "--skip-halt-response",
            "--fail-on-breach",
        ]
    )

    telemetry = pd.read_csv(out_dir / "01_telemetry" / "runtime_telemetry.csv")
    checks = pd.read_csv(out_dir / "02_guard" / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert telemetry.loc[0, "oldest_open_order_age_ns"] == 1_000.0
    assert "oldest_open_order_age_ns" in failed


def test_cli_runtime_session_monitor_halts_on_upload_pack_replace_limit(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_replace_orders=1))
    upload_dir.mkdir()
    upload_summary().to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--skip-halt-response",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_session_summary.csv")
    telemetry = pd.read_csv(out_dir / "01_telemetry" / "runtime_telemetry.csv")
    checks = pd.read_csv(out_dir / "02_guard" / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(telemetry.loc[0, "replace_orders"]) == 2
    assert "replace_orders" in failed
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(manifest["inputs"]["upload_pack"]["path"]).endswith(
        "/upload/broker_upload_summary.csv"
    )


def test_cli_runtime_session_monitor_halts_on_live_greek_limit(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    positions_path = tmp_path / "positions.csv"
    write_scaleup_dir(
        scaleup_dir,
        scaleup_config(max_gross_notional=500, max_abs_net_delta=40, max_abs_net_vega=500),
    )
    positions().to_csv(positions_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--skip-halt-response",
            "--fail-on-breach",
        ]
    )

    telemetry = pd.read_csv(out_dir / "01_telemetry" / "runtime_telemetry.csv")
    checks = pd.read_csv(out_dir / "02_guard" / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert telemetry.loc[0, "gross_position_notional"] == 851.25
    assert telemetry.loc[0, "abs_net_delta"] == 56.25
    assert telemetry.loc[0, "abs_net_vega"] == 900.0
    assert {"gross_position_notional", "abs_net_delta", "abs_net_vega"} <= failed
