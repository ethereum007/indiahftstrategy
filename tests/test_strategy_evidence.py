import json

import pandas as pd

from hft_cli import main
from reports.evidence import (
    EVIDENCE_PROFILE_RUN_TYPES,
    EvidenceThresholds,
    evidence_profile_run_types,
    evaluate_strategy_evidence,
    write_strategy_evidence_review,
)


def catalog_rows(*, dirty=False, commit="abc123", strategy="leadlag", market="india_nse_index_derivatives"):
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/proof",
                "run_type": "proof_report",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": dirty,
                "summary_status": True,
                "summary_file": "proof_summary.csv",
                "parameters_json": json.dumps({"strategy": strategy, "market": market}),
            },
            {
                "run_dir": "runs/stress",
                "run_type": "stress_report",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": dirty,
                "summary_status": True,
                "summary_file": "stress_summary.csv",
                "parameters_json": json.dumps({"strategy": strategy, "market": market}),
            },
            {
                "run_dir": "runs/promotion",
                "run_type": "promotion_report",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": dirty,
                "summary_status": True,
                "summary_file": "promotion_summary.csv",
                "summary_candidate_scenario_key": f"strategy={strategy}|market={market}|trigger_ticks=2",
                "parameters_json": json.dumps({"thresholds": {}}),
            },
        ]
    )


def leadlag_catalog_rows(*, commit="abc123", market="india_nse_index_derivatives"):
    parameters = json.dumps({"strategy": "lead_lag_taker", "market": market})
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/leadlag_edge",
                "run_type": "leadlag_edge_audit",
                "generated_at_utc": "2026-06-10T09:25:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "leadlag_edge_summary.csv",
                "summary_strategy": "lead_lag_taker",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/leadlag_walkforward",
                "run_type": "leadlag_replay_walkforward",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "leadlag_replay_walkforward_summary.csv",
                "summary_strategy": "lead_lag_taker",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/stress",
                "run_type": "stress_report",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "stress_summary.csv",
                "summary_strategy": "lead_lag_taker",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/promotion",
                "run_type": "promotion_report",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "promotion_summary.csv",
                "summary_strategy": "lead_lag_taker",
                "summary_market": market,
                "summary_candidate_scenario_key": f"strategy=lead_lag_taker|market={market}|trigger_ticks=2",
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/leadlag_orders",
                "run_type": "leadlag_order_plan",
                "generated_at_utc": "2026-06-10T09:45:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "leadlag_order_summary.csv",
                "summary_strategy": "lead_lag_taker",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/leadlag_launch_pipeline",
                "run_type": "leadlag_launch_pipeline",
                "generated_at_utc": "2026-06-10T09:50:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "leadlag_launch_pipeline_summary.csv",
                "summary_strategy": "lead_lag_taker",
                "summary_market": market,
                "parameters_json": parameters,
            },
        ]
    )


def surface_mm_catalog_rows(*, commit="abc123", market="india_nse_index_derivatives"):
    parameters = json.dumps({"strategy": "surface_mm", "market": market})
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/surface_quality",
                "run_type": "surface_quality_report",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "surface_quality_summary.csv",
                "summary_strategy": "surface_mm",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/quote_risk",
                "run_type": "quote_risk_report",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "quote_risk_summary.csv",
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/surface_mm_pipeline",
                "run_type": "surface_mm_research_pipeline",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "surface_mm_pipeline_summary.csv",
                "summary_candidate_scenario_key": f"strategy=surface_mm|market={market}|edge_ticks=2.0",
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/surface_mm_launch_pipeline",
                "run_type": "surface_mm_launch_pipeline",
                "generated_at_utc": "2026-06-10T09:45:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "surface_mm_launch_pipeline_summary.csv",
                "summary_strategy": "surface_mm",
                "summary_market": market,
                "parameters_json": parameters,
            },
        ]
    )


def imbalance_catalog_rows(*, commit="abc123", market="india_nse_index_derivatives"):
    parameters = json.dumps({"strategy": "imbalance", "market": market})
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/imbalance_edge",
                "run_type": "imbalance_edge_walkforward",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "imbalance_edge_walkforward_summary.csv",
                "summary_strategy": "imbalance",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/imbalance_replay",
                "run_type": "imbalance_replay_walkforward",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "imbalance_replay_walkforward_summary.csv",
                "summary_strategy": "imbalance",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/imbalance_promotion",
                "run_type": "promotion_report",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "promotion_summary.csv",
                "summary_strategy": "imbalance",
                "summary_market": market,
                "summary_candidate_scenario_key": f"strategy=imbalance|market={market}|entry_imbalance=0.6",
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/imbalance_pipeline",
                "run_type": "imbalance_research_pipeline",
                "generated_at_utc": "2026-06-10T09:45:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "imbalance_pipeline_summary.csv",
                "summary_strategy": "imbalance",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/imbalance_orders",
                "run_type": "imbalance_order_plan",
                "generated_at_utc": "2026-06-10T09:50:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "imbalance_order_summary.csv",
                "summary_strategy": "imbalance",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/imbalance_launch_pipeline",
                "run_type": "imbalance_launch_pipeline",
                "generated_at_utc": "2026-06-10T09:55:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "imbalance_launch_pipeline_summary.csv",
                "summary_strategy": "imbalance",
                "summary_market": market,
                "parameters_json": parameters,
            },
        ]
    )


def settlement_catalog_rows(*, commit="abc123", market="india_nse_index_derivatives"):
    parameters = json.dumps({"strategy": "settlement_convergence", "market": market})
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/settlement_walkforward",
                "run_type": "settlement_convergence_walkforward",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "settlement_convergence_walkforward_summary.csv",
                "summary_strategy": "settlement_convergence",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/settlement_promotion",
                "run_type": "promotion_report",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "promotion_summary.csv",
                "summary_strategy": "settlement_convergence",
                "summary_market": market,
                "summary_candidate_scenario_key": (
                    f"strategy=settlement_convergence|market={market}|direction=buy_underpriced"
                ),
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/settlement_orders",
                "run_type": "settlement_order_plan",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "settlement_order_summary.csv",
                "summary_strategy": "settlement_convergence",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/settlement_launch",
                "run_type": "settlement_launch_pipeline",
                "generated_at_utc": "2026-06-10T09:45:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "settlement_launch_pipeline_summary.csv",
                "summary_strategy": "settlement_convergence",
                "summary_market": market,
                "parameters_json": parameters,
            },
        ]
    )


def parity_catalog_rows(*, commit="abc123", market="india_nse_index_derivatives"):
    parameters = json.dumps({"strategy": "parity_box", "market": market})
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/parity_edge",
                "run_type": "parity_edge_audit",
                "generated_at_utc": "2026-06-10T09:25:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "parity_edge_summary.csv",
                "summary_strategy": "parity_box",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/parity_sweep",
                "run_type": "parity_sweep",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "sweep_summary.csv",
                "summary_strategy": "parity_box",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/parity_promotion",
                "run_type": "promotion_report",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "promotion_summary.csv",
                "summary_strategy": "parity_box",
                "summary_market": market,
                "summary_candidate_scenario_key": f"strategy=parity_box|market={market}|direction=buy_synthetic_sell_future",
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/parity_orders",
                "run_type": "parity_order_plan",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "parity_order_summary.csv",
                "summary_strategy": "parity_box",
                "summary_market": market,
                "parameters_json": parameters,
            },
            {
                "run_dir": "runs/parity_launch",
                "run_type": "parity_launch_pipeline",
                "generated_at_utc": "2026-06-10T09:45:00Z",
                "git_commit": commit,
                "git_dirty": False,
                "summary_status": True,
                "summary_file": "parity_launch_pipeline_summary.csv",
                "summary_strategy": "parity_box",
                "summary_market": market,
                "parameters_json": parameters,
            },
        ]
    )


def ops_launch_catalog_rows(*, commit="abc123", strategy="lead_lag_taker", market="india_nse_index_derivatives"):
    parameters = json.dumps({"strategy": strategy, "market": market})
    run_types = [
        ("scaleup_plan", "runs/scaleup", "scaleup_summary.csv"),
        ("runtime_telemetry_snapshot", "runs/runtime_telemetry", "runtime_telemetry_summary.csv"),
        ("runtime_guard", "runs/runtime_guard", "runtime_guard_summary.csv"),
        ("runtime_session_monitor", "runs/runtime_session", "runtime_session_summary.csv"),
        (
            "broker_vendor_data_readiness_pipeline",
            "runs/broker_vendor_data_readiness",
            "broker_vendor_data_readiness_summary.csv",
        ),
        ("broker_readiness", "runs/broker_readiness", "broker_readiness_summary.csv"),
        ("cutover_gate", "runs/cutover", "cutover_summary.csv"),
        ("route_enable_packet", "runs/route_enable", "route_enable_summary.csv"),
        ("broker_dispatch_plan", "runs/broker_dispatch", "broker_dispatch_summary.csv"),
        ("broker_dispatch_send_packet", "runs/broker_dispatch_send", "broker_dispatch_send_summary.csv"),
        ("broker_dispatch_ack_reconciliation", "runs/broker_dispatch_ack", "broker_dispatch_ack_summary.csv"),
        ("broker_dispatch_roundtrip", "runs/broker_dispatch_roundtrip", "broker_dispatch_roundtrip_summary.csv"),
    ]
    rows = []
    for index, (run_type, run_dir, summary_file) in enumerate(run_types):
        row = {
            "run_dir": run_dir,
            "run_type": run_type,
            "generated_at_utc": f"2026-06-10T10:{index:02d}:00Z",
            "git_commit": commit,
            "git_dirty": False,
            "summary_status": True,
            "summary_file": summary_file,
            "parameters_json": parameters,
        }
        if run_type == "broker_readiness":
            row["summary_runtime_strategy"] = strategy
            row["summary_runtime_market"] = market
        else:
            row["summary_strategy"] = strategy
            row["summary_market"] = market
        if run_type == "broker_dispatch_roundtrip":
            row["summary_dispatch_total_notional"] = 1500.0
            row["summary_strategy_portfolio_provided"] = True
            row["summary_strategy_portfolio_ready"] = True
            row["summary_strategy_portfolio_selected_allocation_notional"] = 2000.0
            row["summary_strategy_portfolio_min_strategy_count"] = 2
            row["summary_strategy_portfolio_min_market_count"] = 1
            row["summary_strategy_portfolio_max_strategy_weight"] = 0.60
            row["summary_strategy_portfolio_max_market_weight"] = 0.90
            row["summary_strategy_portfolio_allocated_strategy_count"] = 2
            row["summary_strategy_portfolio_allocated_market_count"] = 1
            row["summary_strategy_portfolio_max_strategy_allocation_weight"] = 0.45
            row["summary_strategy_portfolio_max_market_allocation_weight"] = 0.80
            row.update(_resume_route_columns("summary_route_broker_resume_broker_route_readiness"))
            row.update(
                _resume_route_columns(
                    "summary_route_broker_resume_incident_broker_route_readiness",
                    route_ready_pairs=2,
                )
            )
        rows.append(row)
    return pd.DataFrame(rows)


def provider_imbalance_ops_launch_catalog_rows(
    *,
    commit="abc123",
    strategy="imbalance",
    market="india_nse_index_derivatives",
):
    parameters = json.dumps({"strategy": strategy, "market": market})
    run_types = [
        (
            "provider_market_data_imbalance_scorecard",
            "runs/provider_imbalance_scorecard",
            "provider_market_data_imbalance_scorecard_summary.csv",
        ),
        (
            "provider_market_data_imbalance_route_readiness",
            "runs/provider_imbalance_route_readiness",
            "provider_market_data_imbalance_route_readiness_summary.csv",
        ),
        (
            "provider_market_data_imbalance_scaleup_plan",
            "runs/provider_imbalance_scaleup",
            "provider_market_data_imbalance_scaleup_summary.csv",
        ),
        (
            "provider_market_data_imbalance_runtime_telemetry_snapshot",
            "runs/provider_imbalance_runtime_telemetry",
            "provider_market_data_imbalance_runtime_telemetry_summary.csv",
        ),
        (
            "provider_market_data_imbalance_runtime_guard",
            "runs/provider_imbalance_runtime_guard",
            "provider_market_data_imbalance_runtime_guard_summary.csv",
        ),
        (
            "provider_market_data_imbalance_runtime_session",
            "runs/provider_imbalance_runtime_session",
            "provider_market_data_imbalance_runtime_session_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_readiness",
            "runs/provider_imbalance_broker_readiness",
            "provider_market_data_imbalance_broker_readiness_summary.csv",
        ),
        (
            "provider_market_data_imbalance_cutover",
            "runs/provider_imbalance_cutover",
            "provider_market_data_imbalance_cutover_summary.csv",
        ),
        (
            "provider_market_data_imbalance_route_enable",
            "runs/provider_imbalance_route_enable",
            "provider_market_data_imbalance_route_enable_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch",
            "runs/provider_imbalance_broker_dispatch",
            "provider_market_data_imbalance_broker_dispatch_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch_send",
            "runs/provider_imbalance_broker_dispatch_send",
            "provider_market_data_imbalance_broker_dispatch_send_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch_ack",
            "runs/provider_imbalance_broker_dispatch_ack",
            "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch_roundtrip",
            "runs/provider_imbalance_broker_dispatch_roundtrip",
            "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        ),
    ]
    rows = []
    for index, (run_type, run_dir, summary_file) in enumerate(run_types):
        row = {
            "run_dir": run_dir,
            "run_type": run_type,
            "generated_at_utc": f"2026-06-10T11:{index:02d}:00Z",
            "git_commit": commit,
            "git_dirty": False,
            "summary_status": True,
            "summary_file": summary_file,
            "summary_strategy": strategy,
            "summary_market": market,
            "parameters_json": parameters,
        }
        if run_type == "provider_market_data_imbalance_broker_dispatch_roundtrip":
            row["summary_dispatch_total_notional"] = 1500.0
            row["summary_strategy_portfolio_provided"] = True
            row["summary_strategy_portfolio_ready"] = True
            row["summary_strategy_portfolio_selected_allocation_notional"] = 2000.0
            row["summary_strategy_portfolio_min_strategy_count"] = 2
            row["summary_strategy_portfolio_min_market_count"] = 1
            row["summary_strategy_portfolio_max_strategy_weight"] = 0.60
            row["summary_strategy_portfolio_max_market_weight"] = 0.90
            row["summary_strategy_portfolio_allocated_strategy_count"] = 2
            row["summary_strategy_portfolio_allocated_market_count"] = 1
            row["summary_strategy_portfolio_max_strategy_allocation_weight"] = 0.45
            row["summary_strategy_portfolio_max_market_allocation_weight"] = 0.80
            row["summary_dispatch_roundtrip_synthetic_dataset_count"] = 2
            row["summary_dispatch_roundtrip_synthetic_sidecar_proof_ready"] = True
            row["summary_dispatch_roundtrip_synthetic_sidecar_count"] = 2
            row["summary_dispatch_roundtrip_synthetic_sidecar_readable_count"] = 2
            row.update(_resume_route_columns("summary_route_broker_resume_broker_route_readiness"))
            row.update(
                _resume_route_columns(
                    "summary_route_broker_resume_incident_broker_route_readiness",
                    route_ready_pairs=2,
                )
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _resume_route_columns(prefix, *, ready=True, route_ready_pairs=1, gap_pairs=0, controls_ready=True):
    return {
        f"{prefix}_required": True,
        f"{prefix}_provided": True,
        f"{prefix}_ready": ready,
        f"{prefix}_strategy": "lead_lag_taker",
        f"{prefix}_market": "india_nse_index_derivatives",
        f"{prefix}_route_ready_pairs": route_ready_pairs,
        f"{prefix}_gap_pairs": gap_pairs,
        f"{prefix}_ops_launch_controls_ready": controls_ready,
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": 1 if ready else 0,
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": 0 if ready else 1,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": 1 if ready else 0,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0 if ready else 1,
    }


def test_strategy_evidence_passes_complete_clean_catalog():
    review = evaluate_strategy_evidence(
        catalog_rows(),
        thresholds=EvidenceThresholds(require_same_git_commit=True),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == {"proof_report", "stress_report", "promotion_report"}
    assert set(review.evidence["passed"]) == {True}
    assert review.summary.iloc[0]["evidence_profile"] == "default"
    assert review.summary.iloc[0]["recommendation"] == "eligible_for_shadow_scaleup_review"


def test_strategy_evidence_fails_missing_failed_and_dirty_artifacts():
    catalog = catalog_rows(dirty=True)
    catalog = catalog.loc[catalog["run_type"] != "stress_report"].copy()
    catalog.loc[catalog["run_type"] == "promotion_report", "summary_status"] = False

    review = evaluate_strategy_evidence(catalog)

    assert not review.ready
    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert "required_run_type:stress_report" in failed
    assert "required_run_type:promotion_report" in failed
    assert "clean_git_artifacts" in failed


def test_strategy_evidence_can_require_proof_refresh_gate():
    catalog = pd.concat(
        [
            catalog_rows(),
            pd.DataFrame(
                [
                    {
                        "run_dir": "runs/proof_refresh",
                        "run_type": "proof_refresh_gate",
                        "generated_at_utc": "2026-06-10T09:45:00Z",
                        "git_commit": "abc123",
                        "git_dirty": False,
                        "summary_status": True,
                        "summary_file": "proof_refresh_summary.csv",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=("proof_report", "stress_report", "promotion_report", "proof_refresh_gate")
        ),
    )

    assert review.ready
    assert "proof_refresh_gate" in set(review.evidence["required_run_type"])
    assert review.summary.iloc[0]["evidence_profile"] == "custom"


def test_strategy_evidence_can_require_broker_readiness_gate():
    catalog = pd.concat(
        [
            catalog_rows(),
            pd.DataFrame(
                [
                    {
                        "run_dir": "runs/broker_readiness",
                        "run_type": "broker_readiness",
                        "generated_at_utc": "2026-06-10T09:50:00Z",
                        "git_commit": "abc123",
                        "git_dirty": False,
                        "summary_status": True,
                        "summary_file": "broker_readiness_summary.csv",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=("proof_report", "stress_report", "promotion_report", "broker_readiness")
        ),
    )

    assert review.ready
    assert "broker_readiness" in set(review.evidence["required_run_type"])


def test_strategy_evidence_reads_broker_runtime_identity_aliases():
    catalog = pd.concat(
        [
            catalog_rows(),
            pd.DataFrame(
                [
                    {
                        "run_dir": "runs/broker_readiness",
                        "run_type": "broker_readiness",
                        "generated_at_utc": "2026-06-10T09:50:00Z",
                        "git_commit": "abc123",
                        "git_dirty": False,
                        "summary_status": True,
                        "summary_file": "broker_readiness_summary.csv",
                        "summary_runtime_strategy": "lead_lag_taker",
                        "summary_runtime_market": "india_nse_index_derivatives",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=("proof_report", "stress_report", "promotion_report", "broker_readiness"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="leadlag",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    broker_item = review.evidence.loc[review.evidence["required_run_type"] == "broker_readiness"].iloc[0]
    assert broker_item["latest_strategy"] == "lead_lag_taker"
    assert broker_item["latest_market"] == "india_nse_index_derivatives"


def test_strategy_evidence_can_require_same_strategy_and_market():
    review = evaluate_strategy_evidence(
        catalog_rows(),
        thresholds=EvidenceThresholds(
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="lead_lag_taker",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["latest_strategy"]) == {"lead_lag_taker"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert review.summary.iloc[0]["market"] == "india_nse_index_derivatives"


def test_strategy_evidence_blocks_mixed_strategy_artifacts():
    catalog = catalog_rows()
    catalog.loc[catalog["run_type"] == "promotion_report", "summary_candidate_scenario_key"] = (
        "strategy=imbalance|market=india_nse_index_derivatives|entry_imbalance=0.6"
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(require_same_strategy=True, expected_strategy="leadlag"),
    )

    assert not review.ready
    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert {"same_strategy", "expected_strategy"} <= failed
    assert int(review.summary.iloc[0]["strategy_count"]) == 2


def test_leadlag_evidence_profile_requires_edge_walkforward_stress_promotion_identity():
    review = evaluate_strategy_evidence(
        leadlag_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("lead-lag"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="leadlag",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["leadlag"])
    assert set(review.evidence["latest_strategy"]) == {"lead_lag_taker"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["strategy"] == "lead_lag_taker"


def test_leadlag_evidence_profile_fails_without_edge_audit():
    catalog = leadlag_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "leadlag_edge_audit"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("lead_lag_taker")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:leadlag_edge_audit" in failed


def test_leadlag_evidence_profile_fails_without_replay_walkforward():
    catalog = leadlag_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "leadlag_replay_walkforward"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("leadlag")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:leadlag_replay_walkforward" in failed


def test_leadlag_evidence_profile_fails_without_order_plan():
    catalog = leadlag_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "leadlag_order_plan"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("leadlag")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:leadlag_order_plan" in failed


def test_leadlag_evidence_profile_fails_without_launch_pipeline():
    catalog = leadlag_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "leadlag_launch_pipeline"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("leadlag")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:leadlag_launch_pipeline" in failed


def test_surface_mm_evidence_profile_requires_surface_quality_and_identity():
    review = evaluate_strategy_evidence(
        surface_mm_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("surface-mm"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="surface_market_making",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["surface_mm"])
    assert set(review.evidence["latest_strategy"]) == {"surface_mm"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["strategy"] == "surface_mm"


def test_surface_mm_evidence_profile_fails_without_surface_quality():
    catalog = surface_mm_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "surface_quality_report"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("surface_mm")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:surface_quality_report" in failed


def test_surface_mm_evidence_profile_fails_without_launch_pipeline():
    catalog = surface_mm_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "surface_mm_launch_pipeline"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("surface_mm")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:surface_mm_launch_pipeline" in failed


def test_imbalance_evidence_profile_requires_walkforward_promotion_and_pipeline_identity():
    review = evaluate_strategy_evidence(
        imbalance_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("microprice-imbalance"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="microprice_imbalance",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["imbalance"])
    assert set(review.evidence["latest_strategy"]) == {"imbalance"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["strategy"] == "imbalance"


def test_imbalance_evidence_profile_fails_without_replay_walkforward():
    catalog = imbalance_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "imbalance_replay_walkforward"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("imbalance")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:imbalance_replay_walkforward" in failed


def test_imbalance_evidence_profile_fails_without_order_plan():
    catalog = imbalance_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "imbalance_order_plan"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("imbalance")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:imbalance_order_plan" in failed


def test_imbalance_evidence_profile_fails_without_launch_pipeline():
    catalog = imbalance_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "imbalance_launch_pipeline"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("imbalance")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:imbalance_launch_pipeline" in failed


def test_settlement_evidence_profile_requires_research_order_and_launch_identity():
    review = evaluate_strategy_evidence(
        settlement_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("settlement-convergence"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="settlement_convergence",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["settlement"])
    assert set(review.evidence["latest_strategy"]) == {"settlement_convergence"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["strategy"] == "settlement_convergence"


def test_settlement_evidence_profile_fails_without_launch_pipeline():
    catalog = settlement_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "settlement_launch_pipeline"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("settlement")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:settlement_launch_pipeline" in failed


def test_parity_evidence_profile_requires_sweep_order_and_launch_identity():
    review = evaluate_strategy_evidence(
        parity_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("parity-box"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="parity_box",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["parity"])
    assert set(review.evidence["latest_strategy"]) == {"parity"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["strategy"] == "parity"


def test_parity_evidence_profile_fails_without_launch_pipeline():
    catalog = parity_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "parity_launch_pipeline"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("parity")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:parity_launch_pipeline" in failed


def test_ops_launch_evidence_profile_requires_dryrun_chain_identity():
    review = evaluate_strategy_evidence(
        ops_launch_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("broker-dryrun"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="leadlag",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["ops_launch"])
    assert set(review.evidence["latest_strategy"]) == {"lead_lag_taker"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["evidence_profile"] == "ops_launch"
    assert review.summary.iloc[0]["recommendation"] == "eligible_for_live_dryrun_route_review"
    broker_item = review.evidence.loc[review.evidence["required_run_type"] == "broker_readiness"].iloc[0]
    assert broker_item["latest_strategy"] == "lead_lag_taker"
    assert broker_item["latest_market"] == "india_nse_index_derivatives"


def test_provider_imbalance_ops_launch_profile_requires_provider_chain_identity():
    review = evaluate_strategy_evidence(
        provider_imbalance_ops_launch_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("provider_market_data_imbalance_ops_launch"),
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="microprice_imbalance",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(
        EVIDENCE_PROFILE_RUN_TYPES["provider_imbalance_ops_launch"]
    )
    assert set(review.evidence["latest_strategy"]) == {"imbalance"}
    assert set(review.evidence["latest_market"]) == {"india_nse_index_derivatives"}
    assert review.summary.iloc[0]["evidence_profile"] == "provider_imbalance_ops_launch"
    assert review.summary.iloc[0]["recommendation"] == "eligible_for_live_dryrun_route_review"


def test_provider_imbalance_ops_launch_profile_fails_without_provider_roundtrip():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    catalog = catalog.loc[
        catalog["run_type"] != "provider_market_data_imbalance_broker_dispatch_roundtrip"
    ].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("provider_imbalance_live_dryrun"),
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:provider_market_data_imbalance_broker_dispatch_roundtrip" in failed
    assert review.summary.iloc[0]["evidence_profile"] == "provider_imbalance_ops_launch"


def test_provider_imbalance_ops_launch_uses_provider_roundtrip_safety_controls():
    review = evaluate_strategy_evidence(
        provider_imbalance_ops_launch_catalog_rows(),
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("provider_imbalance_ops_launch"),
            require_broker_roundtrip_portfolio_safe=True,
            fail_on_broker_roundtrip_portfolio_breach=True,
            require_broker_roundtrip_portfolio_concentration_ok=True,
            fail_on_broker_roundtrip_portfolio_concentration_breach=True,
            require_broker_roundtrip_resume_route_ready=True,
            fail_on_broker_roundtrip_resume_route_breach=True,
            require_provider_broker_roundtrip_synthetic_sidecar_ready=True,
            fail_on_provider_broker_roundtrip_synthetic_sidecar_breach=True,
        ),
    )

    assert review.ready
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_breach_runs"]) == 0
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_concentration_ok_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_concentration_breach_runs"]) == 0
    assert int(review.summary.iloc[0]["broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_resume_route_breach_runs"]) == 0
    assert int(review.summary.iloc[0]["provider_broker_roundtrip_synthetic_sidecar_ready_runs"]) == 1
    assert int(review.summary.iloc[0]["provider_broker_roundtrip_synthetic_sidecar_breach_runs"]) == 0
    assert bool(review.summary.iloc[0]["require_provider_broker_roundtrip_synthetic_sidecar_ready"])
    assert bool(review.summary.iloc[0]["fail_on_provider_broker_roundtrip_synthetic_sidecar_breach"])


def test_provider_imbalance_ops_launch_blocks_unready_provider_roundtrip_sidecar_proof():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    mask = catalog["run_type"] == "provider_market_data_imbalance_broker_dispatch_roundtrip"
    catalog.loc[mask, "summary_status"] = False
    catalog.loc[mask, "summary_dispatch_roundtrip_synthetic_sidecar_proof_ready"] = False
    catalog.loc[mask, "summary_dispatch_roundtrip_synthetic_sidecar_count"] = 1
    catalog.loc[mask, "summary_dispatch_roundtrip_synthetic_sidecar_readable_count"] = 1

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("provider_imbalance_ops_launch"),
            require_provider_broker_roundtrip_synthetic_sidecar_ready=True,
            fail_on_provider_broker_roundtrip_synthetic_sidecar_breach=True,
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:provider_market_data_imbalance_broker_dispatch_roundtrip" in failed
    assert "provider_broker_roundtrip_synthetic_sidecar_ready" in failed
    assert "provider_broker_roundtrip_synthetic_sidecar_breach" in failed
    assert int(review.summary.iloc[0]["provider_broker_roundtrip_synthetic_sidecar_ready_runs"]) == 0
    assert int(review.summary.iloc[0]["provider_broker_roundtrip_synthetic_sidecar_breach_runs"]) == 1


def test_ops_launch_evidence_profile_fails_without_cutover_gate():
    catalog = ops_launch_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "cutover_gate"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("ops_launch")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:cutover_gate" in failed
    assert review.summary.iloc[0]["evidence_profile"] == "ops_launch"
    assert review.summary.iloc[0]["recommendation"] == "ops_launch_evidence_incomplete"


def test_ops_launch_evidence_profile_fails_without_dispatch_roundtrip():
    catalog = ops_launch_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "broker_dispatch_roundtrip"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("ops_launch")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:broker_dispatch_roundtrip" in failed


def test_ops_launch_evidence_profile_fails_without_broker_vendor_data_readiness_pipeline():
    catalog = ops_launch_catalog_rows()
    catalog = catalog.loc[catalog["run_type"] != "broker_vendor_data_readiness_pipeline"].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(required_run_types=evidence_profile_run_types("ops_launch")),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "required_run_type:broker_vendor_data_readiness_pipeline" in failed


def test_strategy_evidence_can_require_file_input_provenance():
    catalog = ops_launch_catalog_rows()
    catalog["input_count"] = 2
    catalog["input_file_count"] = 2
    catalog["input_directory_count"] = 0
    catalog["input_other_count"] = 0
    catalog["input_unfingerprinted_count"] = 0
    catalog["input_hashed_count"] = 2

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_file_inputs=True,
        ),
    )

    assert review.ready
    assert int(review.summary.iloc[0]["input_file_count"]) == 24
    assert int(review.summary.iloc[0]["input_hashed_count"]) == 24
    assert bool(review.summary.iloc[0]["require_file_inputs"])
    assert set(review.evidence["latest_input_directory_count"]) == {0}

    catalog.loc[catalog["run_type"] == "runtime_session_monitor", "input_directory_count"] = 1
    catalog.loc[catalog["run_type"] == "broker_dispatch_ack_reconciliation", "input_unfingerprinted_count"] = 1

    blocked = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_file_inputs=True,
        ),
    )

    failed = set(blocked.checks.loc[~blocked.checks["passed"].astype(bool), "check"])
    assert not blocked.ready
    assert "file_fingerprinted_inputs" in failed
    assert int(blocked.summary.iloc[0]["input_directory_count"]) == 1
    assert int(blocked.summary.iloc[0]["input_unfingerprinted_count"]) == 1


def test_strategy_evidence_can_require_ops_launch_portfolio_and_schema_gates():
    catalog = ops_launch_catalog_rows()
    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_no_blocked_placeholder_schema=True,
            require_broker_roundtrip_portfolio_safe=True,
            fail_on_broker_roundtrip_portfolio_breach=True,
            require_broker_roundtrip_portfolio_concentration_ok=True,
            fail_on_broker_roundtrip_portfolio_concentration_breach=True,
        ),
    )

    assert review.ready
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_breach_runs"]) == 0
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_concentration_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_concentration_ok_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_portfolio_concentration_breach_runs"]) == 0
    assert bool(review.summary.iloc[0]["require_broker_roundtrip_portfolio_safe"])
    assert bool(review.summary.iloc[0]["fail_on_broker_roundtrip_portfolio_breach"])
    assert bool(review.summary.iloc[0]["require_broker_roundtrip_portfolio_concentration_ok"])
    assert bool(review.summary.iloc[0]["fail_on_broker_roundtrip_portfolio_concentration_breach"])

    breach = ops_launch_catalog_rows()
    mask = breach["run_type"] == "broker_dispatch_roundtrip"
    breach.loc[mask, "summary_status"] = False
    breach.loc[mask, "summary_dispatch_total_notional"] = 2500.0
    blocked = evaluate_strategy_evidence(
        breach,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_broker_roundtrip_portfolio_safe=True,
            fail_on_broker_roundtrip_portfolio_breach=True,
            require_broker_roundtrip_portfolio_concentration_ok=True,
            fail_on_broker_roundtrip_portfolio_concentration_breach=True,
        ),
    )

    failed = set(blocked.checks.loc[~blocked.checks["passed"].astype(bool), "check"])
    assert not blocked.ready
    assert {"required_run_type:broker_dispatch_roundtrip", "broker_roundtrip_portfolio_safe"} <= failed
    assert "broker_roundtrip_portfolio_breach" in failed
    assert int(blocked.summary.iloc[0]["broker_roundtrip_portfolio_breach_runs"]) == 1

    concentrated = ops_launch_catalog_rows()
    concentrated_mask = concentrated["run_type"] == "broker_dispatch_roundtrip"
    concentrated.loc[concentrated_mask, "summary_strategy_portfolio_allocated_strategy_count"] = 1
    concentrated.loc[concentrated_mask, "summary_strategy_portfolio_max_strategy_allocation_weight"] = 0.80
    concentrated_blocked = evaluate_strategy_evidence(
        concentrated,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_broker_roundtrip_portfolio_safe=True,
            fail_on_broker_roundtrip_portfolio_breach=True,
            require_broker_roundtrip_portfolio_concentration_ok=True,
            fail_on_broker_roundtrip_portfolio_concentration_breach=True,
        ),
    )

    concentrated_failed = set(
        concentrated_blocked.checks.loc[
            ~concentrated_blocked.checks["passed"].astype(bool), "check"
        ]
    )
    assert not concentrated_blocked.ready
    assert "broker_roundtrip_portfolio_concentration_ok" in concentrated_failed
    assert "broker_roundtrip_portfolio_concentration_breach" in concentrated_failed
    assert int(concentrated_blocked.summary.iloc[0]["broker_roundtrip_portfolio_concentration_breach_runs"]) == 1


def test_strategy_evidence_can_require_ops_launch_resume_route_gate():
    catalog = ops_launch_catalog_rows()
    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_broker_roundtrip_resume_route_ready=True,
            fail_on_broker_roundtrip_resume_route_breach=True,
        ),
    )

    assert review.ready
    assert bool(review.summary.iloc[0]["require_broker_roundtrip_resume_route_ready"])
    assert bool(review.summary.iloc[0]["fail_on_broker_roundtrip_resume_route_breach"])
    assert int(review.summary.iloc[0]["broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_resume_route_primary_ready_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_resume_route_incident_ready_runs"]) == 1
    assert int(review.summary.iloc[0]["broker_roundtrip_resume_route_breach_runs"]) == 0

    blocked_catalog = ops_launch_catalog_rows()
    mask = blocked_catalog["run_type"] == "broker_dispatch_roundtrip"
    prefix = "summary_route_broker_resume_broker_route_readiness"
    blocked_catalog.loc[mask, f"{prefix}_ready"] = False
    blocked_catalog.loc[mask, f"{prefix}_route_ready_pairs"] = 0
    blocked_catalog.loc[mask, f"{prefix}_gap_pairs"] = 2
    blocked_catalog.loc[mask, f"{prefix}_ops_launch_controls_ready"] = False
    blocked_catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"] = 0
    blocked_catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"] = 1
    blocked_catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"] = 0
    blocked_catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"] = 1
    blocked = evaluate_strategy_evidence(
        blocked_catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_broker_roundtrip_resume_route_ready=True,
            fail_on_broker_roundtrip_resume_route_breach=True,
        ),
    )

    failed = set(blocked.checks.loc[~blocked.checks["passed"].astype(bool), "check"])
    assert not blocked.ready
    assert "broker_roundtrip_resume_route_ready" in failed
    assert "broker_roundtrip_resume_route_breach" in failed
    assert int(blocked.summary.iloc[0]["broker_roundtrip_resume_route_breach_runs"]) == 1
    assert int(blocked.summary.iloc[0]["broker_roundtrip_resume_route_gap_breach_runs"]) == 1
    assert int(blocked.summary.iloc[0]["broker_roundtrip_resume_route_launch_control_breach_runs"]) == 1
    assert int(blocked.summary.iloc[0]["broker_roundtrip_resume_route_portfolio_breach_runs"]) == 1
    assert int(blocked.summary.iloc[0]["broker_roundtrip_resume_route_concentration_breach_runs"]) == 1


def test_strategy_evidence_blocks_unreviewed_placeholder_schema_when_required():
    catalog = ops_launch_catalog_rows()
    mask = catalog["run_type"] == "broker_readiness"
    catalog.loc[mask, "summary_adapter_schema_status"] = "placeholder_normalized_pending_vendor_schema"
    catalog.loc[mask, "summary_schema_reviewed"] = False
    catalog.loc[mask, "summary_placeholder_schema_allowed"] = False

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("ops_launch"),
            require_no_blocked_placeholder_schema=True,
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "placeholder_schema_blocked" in failed
    assert int(review.summary.iloc[0]["placeholder_schema_blocked_runs"]) == 1


def test_write_strategy_evidence_review_outputs_files_and_manifest(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "evidence"
    catalog_rows().to_csv(catalog_path, index=False)

    review = write_strategy_evidence_review(
        catalog_path,
        output_dir=out_dir,
        thresholds=EvidenceThresholds(required_run_types=("proof_report", "stress_report")),
    )

    assert review.output_dir == out_dir
    assert review.ready
    assert (out_dir / "strategy_evidence_items.csv").exists()
    assert (out_dir / "strategy_evidence_checks.csv").exists()
    assert (out_dir / "strategy_evidence_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_strategy_evidence_can_fail_on_breach(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "evidence"
    catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--required-run-type",
            "proof_report",
            "--required-run-type",
            "shadow_session_comparison",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_checks"]) == 1


def test_cli_strategy_evidence_surface_mm_profile(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "surface_mm_evidence"
    surface_mm_catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "surface_mm",
            "--require-same-strategy",
            "--expected-strategy",
            "surface_mm",
            "--require-same-market",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    items = pd.read_csv(out_dir / "strategy_evidence_items.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 0
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["surface_mm"])
    assert bool(summary.loc[0, "ready"])


def test_cli_strategy_evidence_imbalance_profile(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "imbalance_evidence"
    imbalance_catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "imbalance",
            "--require-same-strategy",
            "--expected-strategy",
            "microprice_imbalance",
            "--require-same-market",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    items = pd.read_csv(out_dir / "strategy_evidence_items.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 0
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["imbalance"])
    assert bool(summary.loc[0, "ready"])


def test_cli_strategy_evidence_settlement_profile(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "settlement_evidence"
    settlement_catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "settlement",
            "--require-same-strategy",
            "--expected-strategy",
            "settlement_convergence",
            "--require-same-market",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    items = pd.read_csv(out_dir / "strategy_evidence_items.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 0
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["settlement"])
    assert bool(summary.loc[0, "ready"])


def test_cli_strategy_evidence_leadlag_profile(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "leadlag_evidence"
    leadlag_catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "leadlag",
            "--require-same-strategy",
            "--expected-strategy",
            "lead_lag_taker",
            "--require-same-market",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    items = pd.read_csv(out_dir / "strategy_evidence_items.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 0
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["leadlag"])
    assert bool(summary.loc[0, "ready"])


def test_cli_strategy_evidence_ops_launch_profile(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "ops_launch_evidence"
    ops_launch_catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "ops_launch",
            "--require-same-strategy",
            "--expected-strategy",
            "lead_lag_taker",
            "--require-same-market",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    items = pd.read_csv(out_dir / "strategy_evidence_items.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 0
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["ops_launch"])
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "evidence_profile"] == "ops_launch"
    assert summary.loc[0, "recommendation"] == "eligible_for_live_dryrun_route_review"
    assert bool(summary.loc[0, "require_no_blocked_placeholder_schema"])
    assert bool(summary.loc[0, "require_broker_roundtrip_portfolio_safe"])
    assert bool(summary.loc[0, "fail_on_broker_roundtrip_portfolio_breach"])
    assert bool(summary.loc[0, "require_broker_roundtrip_portfolio_concentration_ok"])
    assert bool(summary.loc[0, "fail_on_broker_roundtrip_portfolio_concentration_breach"])
    assert bool(summary.loc[0, "require_broker_roundtrip_resume_route_ready"])
    assert bool(summary.loc[0, "fail_on_broker_roundtrip_resume_route_breach"])
    assert int(summary.loc[0, "broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(summary.loc[0, "broker_roundtrip_portfolio_concentration_ok_runs"]) == 1
    assert int(summary.loc[0, "broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(summary.loc[0, "broker_roundtrip_resume_route_breach_runs"]) == 0


def test_cli_strategy_evidence_provider_ops_launch_profile(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "provider_ops_launch_evidence"
    provider_imbalance_ops_launch_catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "provider_market_data_imbalance_ops_launch",
            "--require-same-strategy",
            "--expected-strategy",
            "microprice_imbalance",
            "--require-same-market",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    items = pd.read_csv(out_dir / "strategy_evidence_items.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 0
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["provider_imbalance_ops_launch"])
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "evidence_profile"] == "provider_imbalance_ops_launch"
    assert bool(summary.loc[0, "require_file_inputs"])
    assert bool(summary.loc[0, "require_no_blocked_placeholder_schema"])
    assert bool(summary.loc[0, "require_broker_roundtrip_portfolio_safe"])
    assert bool(summary.loc[0, "fail_on_broker_roundtrip_resume_route_breach"])
    assert bool(summary.loc[0, "require_provider_broker_roundtrip_synthetic_sidecar_ready"])
    assert bool(summary.loc[0, "fail_on_provider_broker_roundtrip_synthetic_sidecar_breach"])
    assert int(summary.loc[0, "broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(summary.loc[0, "broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(summary.loc[0, "provider_broker_roundtrip_synthetic_sidecar_ready_runs"]) == 1
    assert int(summary.loc[0, "provider_broker_roundtrip_synthetic_sidecar_breach_runs"]) == 0


def test_cli_strategy_evidence_provider_ops_launch_profile_blocks_sidecar_breach(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "provider_ops_launch_evidence"
    catalog = provider_imbalance_ops_launch_catalog_rows()
    mask = catalog["run_type"] == "provider_market_data_imbalance_broker_dispatch_roundtrip"
    catalog.loc[mask, "summary_status"] = False
    catalog.loc[mask, "summary_dispatch_roundtrip_synthetic_sidecar_proof_ready"] = False
    catalog.loc[mask, "summary_dispatch_roundtrip_synthetic_sidecar_count"] = 0
    catalog.loc[mask, "summary_dispatch_roundtrip_synthetic_sidecar_readable_count"] = 0
    catalog.to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "provider_market_data_imbalance_ops_launch",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "provider_broker_roundtrip_synthetic_sidecar_ready" in failed
    assert "provider_broker_roundtrip_synthetic_sidecar_breach" in failed
    assert int(summary.loc[0, "provider_broker_roundtrip_synthetic_sidecar_ready_runs"]) == 0
    assert int(summary.loc[0, "provider_broker_roundtrip_synthetic_sidecar_breach_runs"]) == 1


def test_cli_strategy_evidence_ops_launch_profile_requires_file_inputs(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "ops_launch_evidence"
    catalog = ops_launch_catalog_rows()
    catalog["input_count"] = 2
    catalog["input_file_count"] = 2
    catalog["input_directory_count"] = 0
    catalog["input_other_count"] = 0
    catalog["input_unfingerprinted_count"] = 0
    catalog["input_hashed_count"] = 2
    catalog.loc[catalog["run_type"] == "runtime_session_monitor", "input_directory_count"] = 1
    catalog.to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "ops_launch",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "file_fingerprinted_inputs" in failed
    assert bool(summary.loc[0, "require_file_inputs"])
    assert int(summary.loc[0, "input_directory_count"]) == 1


def test_cli_strategy_evidence_ops_launch_profile_blocks_portfolio_breach(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "ops_launch_evidence"
    catalog = ops_launch_catalog_rows()
    mask = catalog["run_type"] == "broker_dispatch_roundtrip"
    catalog.loc[mask, "summary_status"] = False
    catalog.loc[mask, "summary_dispatch_total_notional"] = 2500.0
    catalog.to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "ops_launch",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "broker_roundtrip_portfolio_breach" in failed
    assert "broker_roundtrip_portfolio_safe" in failed
    assert int(summary.loc[0, "broker_roundtrip_portfolio_breach_runs"]) == 1


def test_cli_strategy_evidence_ops_launch_profile_blocks_portfolio_concentration_breach(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "ops_launch_evidence"
    catalog = ops_launch_catalog_rows()
    mask = catalog["run_type"] == "broker_dispatch_roundtrip"
    catalog.loc[mask, "summary_strategy_portfolio_allocated_strategy_count"] = 1
    catalog.loc[mask, "summary_strategy_portfolio_max_strategy_allocation_weight"] = 0.80
    catalog.to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "ops_launch",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "broker_roundtrip_portfolio_concentration_ok" in failed
    assert "broker_roundtrip_portfolio_concentration_breach" in failed
    assert "broker_roundtrip_portfolio_breach" not in failed
    assert int(summary.loc[0, "broker_roundtrip_portfolio_concentration_breach_runs"]) == 1


def test_cli_strategy_evidence_ops_launch_profile_blocks_resume_route_breach(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "ops_launch_evidence"
    catalog = ops_launch_catalog_rows()
    mask = catalog["run_type"] == "broker_dispatch_roundtrip"
    prefix = "summary_route_broker_resume_broker_route_readiness"
    catalog.loc[mask, f"{prefix}_ready"] = False
    catalog.loc[mask, f"{prefix}_route_ready_pairs"] = 0
    catalog.loc[mask, f"{prefix}_gap_pairs"] = 2
    catalog.loc[mask, f"{prefix}_ops_launch_controls_ready"] = False
    catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"] = 0
    catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"] = 1
    catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"] = 0
    catalog.loc[mask, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"] = 1
    catalog.to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "ops_launch",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "broker_roundtrip_resume_route_ready" in failed
    assert "broker_roundtrip_resume_route_breach" in failed
    assert int(summary.loc[0, "broker_roundtrip_resume_route_breach_runs"]) == 1
    assert int(summary.loc[0, "broker_roundtrip_resume_route_gap_breach_runs"]) == 1


def test_cli_strategy_evidence_can_require_strategy_identity(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "evidence"
    catalog = catalog_rows()
    catalog.loc[catalog["run_type"] == "promotion_report", "summary_candidate_scenario_key"] = (
        "strategy=imbalance|market=india_nse_index_derivatives|entry_imbalance=0.6"
    )
    catalog.to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--require-same-strategy",
            "--expected-strategy",
            "leadlag",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert {"same_strategy", "expected_strategy"} <= failed
