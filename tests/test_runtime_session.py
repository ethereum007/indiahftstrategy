import json

import pandas as pd
import pytest

from hft_cli import main
from reports.manifest import file_sha256, verify_experiment_manifest, write_experiment_manifest
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
    payload = json.loads(json.dumps(config or scaleup_config()))
    payload["authorizes_submission"] = False
    payload["failed_check_count"] = 0
    portfolio = payload.get("strategy_portfolio", {}) or {}
    portfolio_inputs = {}
    if portfolio.get("required") or portfolio.get("provided"):
        portfolio_dir = path.parent / f"{path.name}_portfolio"
        portfolio_dir.mkdir()
        allocation = {
            "profile": portfolio["selected_profile"],
            "strategy": portfolio["selected_strategy"],
            "market": portfolio["selected_market"],
            "eligible": True,
            "allocation_weight": portfolio["selected_allocation_weight"],
            "allocation_notional": portfolio["selected_allocation_notional"],
            "scorecard_manifest_sha256": "",
            "research_family_enabled": False,
            "research_family_id": "",
            "research_family_registration_id": "",
            "research_family_manifest_sha256": "",
            "research_family_matched_study_label": "",
            "authorizes_submission": False,
        }
        portfolio_summary = {
            "ready": True,
            "deployment_mode": portfolio["deployment_mode"],
            "allocation_mode": portfolio["allocation_mode"],
            "capital_currency": portfolio["capital_currency"],
            "total_capital": 1_000_000.0,
            "allocated_weight": portfolio["selected_allocation_weight"],
            "allocated_notional": portfolio["selected_allocation_notional"],
            "allocated_strategy_count": portfolio["allocated_strategy_count"],
            "allocated_market_count": portfolio["allocated_market_count"],
            "scorecard_manifest_required": False,
            "scorecard_manifest_current": False,
            "scorecard_manifest_sha256": "",
            "scorecard_contract_consistent": True,
            "scorecard_non_authorizing": True,
            "scorecard_provenance_gate_passed": True,
            "research_family_bound": False,
            "research_family_provenance_current": False,
            "research_family_id": "",
            "research_family_registration_id": "",
            "research_family_path": "",
            "research_family_manifest_sha256": "",
            "authorizes_submission": False,
        }
        pd.DataFrame([allocation]).to_csv(
            portfolio_dir / "strategy_portfolio_allocations.csv",
            index=False,
        )
        pd.DataFrame(
            [{"check": "portfolio_ready", "passed": True, "reason": ""}]
        ).to_csv(portfolio_dir / "strategy_portfolio_checks.csv", index=False)
        pd.DataFrame([portfolio_summary]).to_csv(
            portfolio_dir / "strategy_portfolio_summary.csv",
            index=False,
        )
        pd.DataFrame(columns=["priority"]).to_csv(
            portfolio_dir / "strategy_portfolio_action_queue.csv",
            index=False,
        )
        portfolio_config = {
            "schema_version": 1,
            "ready": True,
            "authorizes_submission": False,
            "summary": portfolio_summary,
            "allocations": [allocation],
            "allocation_count": 1,
            "scorecard_provenance": {
                "manifest_required": False,
                "manifest_current": False,
                "manifest_sha256": "",
                "contract_consistent": True,
                "non_authorizing": True,
                "gate_passed": True,
            },
            "scorecard_manifest_required": False,
            "scorecard_manifest_current": False,
            "scorecard_manifest_sha256": "",
            "research_family_bound": False,
            "research_family_provenance_current": False,
            "research_family_id": "",
            "research_family_registration_id": "",
            "research_family_path": "",
            "research_family_manifest_sha256": "",
        }
        (portfolio_dir / "strategy_portfolio_config.json").write_text(
            json.dumps(portfolio_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (portfolio_dir / "strategy_portfolio_runbook.md").write_text(
            "# Strategy Portfolio Fixture\n",
            encoding="utf-8",
        )
        portfolio_source = path.parent / f"{path.name}_portfolio_source.csv"
        pd.DataFrame([{"source": "fixture"}]).to_csv(portfolio_source, index=False)
        write_experiment_manifest(
            portfolio_dir,
            run_type="strategy_portfolio_allocation",
            inputs={"scorecard": portfolio_source},
            extra={
                "ready": True,
                "research_family_bound": False,
                "authorizes_submission": False,
            },
        )
        portfolio.update(
            {
                "manifest_required": True,
                "manifest_provided": True,
                "manifest_current": True,
                "manifest_sha256": file_sha256(portfolio_dir / "manifest.json"),
                "manifest_error": "",
                "contract_consistent": True,
                "contract_error": "",
                "non_authorizing": True,
                "provenance_gate_passed": True,
                "dependency_count": 1,
                "scorecard_provenance": portfolio_config["scorecard_provenance"],
                "research_family": {
                    "bound": False,
                    "provenance_current": False,
                    "family_id": "",
                    "registration_id": "",
                    "path": "",
                    "manifest_sha256": "",
                },
            }
        )
        payload["strategy_portfolio"] = portfolio
        portfolio_inputs = {
            "strategy_portfolio": portfolio_dir / "strategy_portfolio_summary.csv",
            "strategy_portfolio_allocations": portfolio_dir / "strategy_portfolio_allocations.csv",
            "strategy_portfolio_manifest": portfolio_dir / "manifest.json",
        }
    (path / "scaleup_config.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    limits = payload["limits"]
    row = {
        "ready": True,
        "authorizes_submission": False,
        "target_mode": payload["target_mode"],
        "strategy": payload["strategy"],
        "market": payload["market"],
        "scenario_key": payload["scenario_key"],
        "adapter": payload["adapter"],
        "max_orders_per_session": limits["max_orders_per_session"],
        "max_notional_per_session": limits["max_notional_per_session"],
        "pre_portfolio_max_notional_per_session": limits.get(
            "pre_portfolio_max_notional_per_session",
            limits["max_notional_per_session"],
        ),
    }
    if portfolio:
        row.update(
            {
                "strategy_portfolio_required": portfolio.get("required", False),
                "strategy_portfolio_provided": portfolio.get("provided", False),
                "strategy_portfolio_manifest_required": portfolio.get("manifest_required", False),
                "strategy_portfolio_manifest_provided": portfolio.get("manifest_provided", False),
                "strategy_portfolio_manifest_current": portfolio.get("manifest_current", False),
                "strategy_portfolio_manifest_sha256": portfolio.get("manifest_sha256", ""),
                "strategy_portfolio_contract_consistent": portfolio.get("contract_consistent", False),
                "strategy_portfolio_non_authorizing": portfolio.get("non_authorizing", False),
                "strategy_portfolio_provenance_gate_passed": portfolio.get("provenance_gate_passed", False),
                "strategy_portfolio_scorecard_manifest_required": portfolio.get("scorecard_provenance", {}).get("manifest_required", False),
                "strategy_portfolio_scorecard_manifest_current": portfolio.get("scorecard_provenance", {}).get("manifest_current", False),
                "strategy_portfolio_scorecard_manifest_sha256": portfolio.get("scorecard_provenance", {}).get("manifest_sha256", ""),
                "strategy_portfolio_scorecard_contract_consistent": portfolio.get("scorecard_provenance", {}).get("contract_consistent", False),
                "strategy_portfolio_scorecard_non_authorizing": portfolio.get("scorecard_provenance", {}).get("non_authorizing", False),
                "strategy_portfolio_scorecard_provenance_gate_passed": portfolio.get("scorecard_provenance", {}).get("gate_passed", False),
                "strategy_portfolio_research_family_bound": False,
                "strategy_portfolio_research_family_provenance_current": False,
                "strategy_portfolio_research_family_id": "",
                "strategy_portfolio_research_family_registration_id": "",
                "strategy_portfolio_research_family_manifest_sha256": "",
            }
        )
    pd.DataFrame([row]).to_csv(path / "scaleup_summary.csv", index=False)
    pd.DataFrame([row]).to_csv(path / "scaleup_plan.csv", index=False)
    pd.DataFrame([{"check": "scaleup_ready", "passed": True, "reason": ""}]).to_csv(
        path / "scaleup_checks.csv",
        index=False,
    )
    source = path.parent / f"{path.name}_source.csv"
    pd.DataFrame([{"source": "fixture"}]).to_csv(source, index=False)
    manifest_extra = {
        "ready": True,
        "strategy_portfolio_manifest_required": portfolio.get("manifest_required", False),
        "strategy_portfolio_manifest_current": portfolio.get("manifest_current", False),
        "strategy_portfolio_manifest_sha256": portfolio.get("manifest_sha256", ""),
        "research_family_bound": False,
        "research_family_id": "",
        "research_family_registration_id": "",
        "research_family_manifest_sha256": "",
        "authorizes_submission": False,
    }
    write_experiment_manifest(
        path,
        run_type="scaleup_plan",
        inputs={"source": source, **portfolio_inputs},
        extra=manifest_extra,
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
    scaleup_manifest_sha256 = file_sha256(scaleup_dir / "manifest.json")
    assert report.summary.loc[0, "scaleup_manifest_sha256"] == scaleup_manifest_sha256
    assert bool(report.summary.loc[0, "scaleup_provenance_gate_passed"])
    assert bool(report.summary.loc[0, "runtime_telemetry_lineage_matches_current"])
    assert set(report.steps["scaleup_manifest_sha256"]) == {scaleup_manifest_sha256}
    assert not report.config["authorizes_submission"]
    assert report.config["scaleup_provenance"]["scaleup_manifest_sha256"] == scaleup_manifest_sha256
    assert report.config["runtime_telemetry_lineage"]["runtime_telemetry_lineage_matches_current"]
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
        "scaleup_manifest",
        "scaleup_dependencies",
        "telemetry_dependencies",
        "guard_dependencies",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["scaleup"]["path"]).endswith("/scaleup/scaleup_config.json")
    assert path_tail(manifest["inputs"]["telemetry"]["path"]).endswith(
        "/session/01_telemetry/runtime_telemetry.csv"
    )
    assert path_tail(manifest["inputs"]["guard_summary"]["path"]).endswith(
        "/session/02_guard/runtime_guard_summary.csv"
    )
    assert "halt_response_summary" not in manifest["inputs"]
    assert manifest["extra"]["scaleup_manifest_sha256"] == scaleup_manifest_sha256
    assert manifest["extra"]["runtime_telemetry_lineage_matches_current"]
    assert not manifest["extra"]["authorizes_submission"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="runtime_session_monitor",
        require_input_fingerprints=True,
    ).passed
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
    portfolio_manifest_sha256 = file_sha256(tmp_path / "scaleup_portfolio" / "manifest.json")
    assert summary["scaleup_strategy_portfolio_manifest_sha256"] == portfolio_manifest_sha256
    assert bool(summary["runtime_telemetry_strategy_portfolio_matches_current"])
    assert set(report.steps["scaleup_strategy_portfolio_manifest_sha256"]) == {
        portfolio_manifest_sha256
    }
    assert report.config["scaleup_provenance"]["scaleup_strategy_portfolio_manifest_sha256"] == (
        portfolio_manifest_sha256
    )


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
    cancel_orders = pd.read_csv(out_dir / "03_halt_response" / "halt_cancel_orders.csv")
    flatten_orders = pd.read_csv(out_dir / "03_halt_response" / "halt_flatten_orders.csv")
    queue = pd.read_csv(out_dir / "runtime_session_action_queue.csv")
    config = json.loads((out_dir / "runtime_session_config.json").read_text(encoding="utf-8"))
    halt_config = json.loads(
        (out_dir / "03_halt_response" / "halt_response_config.json").read_text(encoding="utf-8")
    )
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
    scaleup_manifest_sha256 = file_sha256(scaleup_dir / "manifest.json")
    assert summary.loc[0, "scaleup_manifest_sha256"] == scaleup_manifest_sha256
    assert response.loc[0, "scaleup_manifest_sha256"] == scaleup_manifest_sha256
    assert set(steps["scaleup_manifest_sha256"]) == {scaleup_manifest_sha256}
    assert set(cancel_orders["scaleup_manifest_sha256"]) == {scaleup_manifest_sha256}
    assert set(flatten_orders["scaleup_manifest_sha256"]) == {scaleup_manifest_sha256}
    assert not config["authorizes_submission"]
    assert not halt_config["authorizes_submission"]
    assert config["runtime_telemetry_lineage"]["runtime_telemetry_lineage_matches_current"]
    assert halt_config["runtime_telemetry_lineage"]["runtime_telemetry_lineage_matches_current"]
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
        "halt_response_dependencies",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["open_orders"]["path"]).endswith("/open_orders.csv")
    assert path_tail(manifest["inputs"]["positions"]["path"]).endswith("/positions.csv")
    assert path_tail(manifest["inputs"]["halt_response_summary"]["path"]).endswith(
        "/session/03_halt_response/halt_response_summary.csv"
    )
    halt_manifest = json.loads(
        (out_dir / "03_halt_response" / "manifest.json").read_text(encoding="utf-8")
    )
    assert halt_manifest["extra"]["scaleup_manifest_sha256"] == scaleup_manifest_sha256
    assert not halt_manifest["extra"]["authorizes_submission"]
    assert "guard_halted" in (out_dir / "runtime_session_runbook.md").read_text(encoding="utf-8")


def test_runtime_session_rejects_scaleup_output_collision(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    write_scaleup_dir(scaleup_dir)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_runtime_session_monitor(
            scaleup_dir=scaleup_dir,
            output_dir=scaleup_dir,
            snapshot_ts_ns=1_000,
            as_of_ts_ns=1_500,
        )


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
