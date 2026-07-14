import json
from types import SimpleNamespace

import pandas as pd
import pytest

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.evidence import (
    EVIDENCE_PROFILE_RUN_TYPES,
    PROVIDER_ACTIVE_LINEAGE_BUNDLE_TYPES,
    PROVIDER_ACTIVE_LINEAGE_RUN_TYPES,
    EvidenceThresholds,
    evidence_profile_run_types,
    evaluate_strategy_evidence,
    verify_strategy_evidence_review,
    write_strategy_evidence_review,
)
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.provider_market_data_imbalance_release_review import (
    verify_provider_market_data_imbalance_release_review,
    write_provider_market_data_imbalance_release_review,
)
from reports.provider_market_data_imbalance_release_decision import (
    verify_provider_market_data_imbalance_release_decision,
    write_provider_market_data_imbalance_release_decision,
)
from reports.provider_market_data_imbalance_live_dryrun_handoff import (
    verify_provider_market_data_imbalance_live_dryrun_handoff,
    write_provider_market_data_imbalance_live_dryrun_handoff,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_preflight import (
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight,
    write_provider_market_data_imbalance_live_dryrun_runtime_preflight,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher,
    write_provider_market_data_imbalance_live_dryrun_runtime_launcher,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator import (
    verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
    write_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration import (
    verify_provider_market_data_imbalance_live_dryrun_shadow_calibration,
    write_provider_market_data_imbalance_live_dryrun_shadow_calibration,
)


def _manifest_input_paths(value):
    if isinstance(value, dict):
        if value.get("kind") in {"file", "directory"} and value.get("path"):
            return value["path"]
        return {
            key: _manifest_input_paths(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_manifest_input_paths(item) for item in value]
    return value


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
        (
            "provider_market_data_imbalance_broker_rehearsal_certificate",
            "runs/provider_imbalance_broker_rehearsal_certificate",
            "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
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
        if run_type in PROVIDER_ACTIVE_LINEAGE_RUN_TYPES:
            lineage_number = PROVIDER_ACTIVE_LINEAGE_RUN_TYPES.index(run_type) + 1
            row["provider_lineage_selection_status"] = "selectable"
            row["provider_lineage_selection_eligible"] = True
            row["provider_lineage_bundle_type"] = PROVIDER_ACTIVE_LINEAGE_BUNDLE_TYPES[run_type]
            row["provider_lineage_pair_id"] = str(lineage_number) * 64
            row["provider_lineage_role"] = "active_strict"
            row["provider_lineage_counterpart_path"] = f"{run_dir}_retained"
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
        if run_type == "provider_market_data_imbalance_broker_rehearsal_certificate":
            row["summary_target_mode"] = "live_dryrun"
            row["summary_authorizes_submission"] = False
            row["summary_digitally_signed"] = False
            row["summary_certificate_sha256"] = "a" * 64
            row["provider_active_lineage_chain_audit_status"] = (
                "covered_current"
            )
            row["provider_active_lineage_chain_audit_dir"] = (
                "runs/provider_imbalance_active_lineage_chain_audit"
            )
            row[
                "provider_active_lineage_chain_audit_chain_digest_sha256"
            ] = "b" * 64
            row[
                "provider_active_lineage_chain_audit_manifest_sha256"
            ] = "c" * 64
            row[
                "provider_active_lineage_chain_audit_contract_sha256"
            ] = "d" * 64
            row[
                "provider_active_lineage_chain_audit_certificate_manifest_sha256"
            ] = "e" * 64
            row[
                "provider_active_lineage_chain_audit_selection_bound"
            ] = True
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
    assert bool(review.summary.iloc[0]["require_provider_lineage_selection"])
    assert review.summary.iloc[0]["provider_lineage_selection_policy"] == "required"
    assert int(review.summary.iloc[0]["provider_lineage_required_run_type_count"]) == 3
    assert int(review.summary.iloc[0]["provider_lineage_covered_run_type_count"]) == 3
    assert int(review.summary.iloc[0]["provider_lineage_selectable_runs"]) == 3
    assert int(review.summary.iloc[0]["provider_lineage_selected_run_count"]) == 3
    assert int(review.summary.iloc[0]["provider_lineage_selected_pair_count"]) == 3
    assert len(review.summary.iloc[0]["provider_lineage_selection_contract_sha256"]) == 64
    assert review.provider_lineage_selection["selected"].astype(bool).all()


def test_provider_imbalance_ops_launch_rejects_retained_only_rehearsal_candidate():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    mask = (
        catalog["run_type"]
        == "provider_market_data_imbalance_broker_rehearsal_certificate"
    )
    catalog.loc[mask, "provider_lineage_selection_status"] = "retained_only"
    catalog.loc[mask, "provider_lineage_selection_eligible"] = False

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types(
                "provider_imbalance_ops_launch"
            ),
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert (
        "provider_lineage_selectable:"
        "provider_market_data_imbalance_broker_rehearsal_certificate"
        in failed
    )
    assert int(review.summary.iloc[0]["provider_lineage_covered_run_type_count"]) == 2
    assert int(review.summary.iloc[0]["provider_lineage_retained_only_runs"]) == 1
    assert int(review.summary.iloc[0]["provider_lineage_selection_blocked_runs"]) == 1


def test_provider_imbalance_ops_launch_rejects_certificate_without_current_chain_audit():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    mask = (
        catalog["run_type"]
        == "provider_market_data_imbalance_broker_rehearsal_certificate"
    )
    catalog.loc[
        mask, "provider_active_lineage_chain_audit_status"
    ] = "certificate_manifest_drift"
    catalog.loc[
        mask, "provider_active_lineage_chain_audit_selection_bound"
    ] = False

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types(
                "provider_imbalance_ops_launch"
            ),
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert (
        "provider_lineage_selectable:"
        "provider_market_data_imbalance_broker_rehearsal_certificate"
        in failed
    )
    assert int(
        review.summary.iloc[0]["provider_lineage_covered_run_type_count"]
    ) == 2
    assert int(
        review.summary.iloc[0]["provider_lineage_selection_blocked_runs"]
    ) == 1


def test_provider_imbalance_ops_launch_selects_strict_siblings_alongside_archive():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    retained = catalog.loc[
        catalog["run_type"].isin(PROVIDER_ACTIVE_LINEAGE_RUN_TYPES)
    ].copy()
    retained["run_dir"] = retained["run_dir"].astype(str) + "_retained"
    retained["generated_at_utc"] = "2026-06-10T12:00:00Z"
    retained["provider_lineage_selection_status"] = "retained_only"
    retained["provider_lineage_selection_eligible"] = False
    retained["provider_lineage_role"] = "retained_original"

    combined = pd.concat([catalog, retained], ignore_index=True)
    thresholds = EvidenceThresholds(
        required_run_types=evidence_profile_run_types(
            "provider_imbalance_ops_launch"
        ),
    )
    review = evaluate_strategy_evidence(
        combined,
        thresholds=thresholds,
    )
    shuffled_review = evaluate_strategy_evidence(
        combined.sample(frac=1, random_state=7).reset_index(drop=True),
        thresholds=thresholds,
    )

    assert review.ready
    assert int(review.summary.iloc[0]["provider_lineage_selectable_runs"]) == 3
    assert int(review.summary.iloc[0]["provider_lineage_retained_only_runs"]) == 3
    assert int(review.summary.iloc[0]["provider_lineage_selection_blocked_runs"]) == 3
    provider_items = review.evidence.loc[
        review.evidence["required_run_type"].isin(PROVIDER_ACTIVE_LINEAGE_RUN_TYPES)
    ]
    assert provider_items["latest_run_dir"].str.endswith("_retained").all()
    assert (~provider_items["selected_run_dir"].str.endswith("_retained")).all()
    assert (~review.provider_lineage_selection["selected_run_dir"].str.endswith("_retained")).all()
    assert len(review.summary.iloc[0]["provider_lineage_selection_contract_sha256"]) == 64
    assert (
        review.summary.iloc[0]["provider_lineage_selection_contract_sha256"]
        == shuffled_review.summary.iloc[0]["provider_lineage_selection_contract_sha256"]
    )


def test_provider_imbalance_ops_launch_rejects_selected_lineage_without_pair_id():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    run_type = "provider_market_data_imbalance_broker_rehearsal_certificate"
    catalog.loc[catalog["run_type"] == run_type, "provider_lineage_pair_id"] = ""

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types(
                "provider_imbalance_ops_launch"
            ),
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert f"provider_lineage_identity:{run_type}" in failed
    assert "provider_lineage_unique_pair_ids" in failed
    assert "provider_lineage_selection_contract" in failed
    assert int(review.summary.iloc[0]["provider_lineage_selected_pair_count"]) == 2
    assert review.summary.iloc[0]["provider_lineage_selection_contract_sha256"] == ""


def test_provider_lineage_audit_override_remains_non_candidate():
    catalog = provider_imbalance_ops_launch_catalog_rows().drop(
        columns=[
            "provider_lineage_selection_status",
            "provider_lineage_selection_eligible",
        ]
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types(
                "provider_imbalance_ops_launch"
            ),
            require_provider_lineage_selection=False,
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert failed == {"provider_lineage_selection_audit_only"}
    assert review.summary.iloc[0]["provider_lineage_selection_policy"] == "audit_only"
    assert bool(review.summary.iloc[0]["provider_lineage_selection_audit_only"])
    assert review.summary.iloc[0]["recommendation"] == "provider_lineage_audit_only"


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


def test_provider_imbalance_ops_launch_profile_requires_rehearsal_certificate():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    catalog = catalog.loc[
        catalog["run_type"]
        != "provider_market_data_imbalance_broker_rehearsal_certificate"
    ].copy()

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("provider_imbalance_ops_launch"),
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert (
        "required_run_type:provider_market_data_imbalance_broker_rehearsal_certificate"
        in failed
    )


def test_provider_imbalance_ops_launch_profile_rejects_unsafe_rehearsal_certificate():
    catalog = provider_imbalance_ops_launch_catalog_rows()
    mask = (
        catalog["run_type"]
        == "provider_market_data_imbalance_broker_rehearsal_certificate"
    )
    catalog.loc[mask, "summary_target_mode"] = "paper"
    catalog.loc[mask, "summary_authorizes_submission"] = True
    catalog.loc[mask, "summary_certificate_sha256"] = "not-a-sha256"

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("provider_imbalance_ops_launch"),
        ),
    )

    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert not review.ready
    assert "provider_broker_rehearsal_certificate_live_dryrun" in failed
    assert "provider_broker_rehearsal_certificate_authorizing" in failed
    assert "provider_broker_rehearsal_certificate_non_authorizing" in failed
    assert "provider_broker_rehearsal_certificate_hashed" in failed


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
    assert (out_dir / "strategy_evidence_provider_lineage_selection.csv").exists()
    assert (out_dir / "manifest.json").exists()
    verification = verify_strategy_evidence_review(out_dir)
    assert verification.verified
    assert verification.ready
    assert verification.manifest_current
    assert verification.source_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert (
        main(
            [
                "verify-strategy-evidence",
                "--evidence",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )


@pytest.mark.parametrize("drift_target", ["audit", "certificate"])
def test_write_provider_strategy_evidence_seals_catalog_and_retained_proofs(
    tmp_path,
    monkeypatch,
    drift_target,
):
    proof_root = tmp_path / "proofs"
    proof_root.mkdir()
    certificate_source = proof_root / "certificate_source.csv"
    certificate_source.write_text("source\nready\n", encoding="utf-8")
    certificate_dir = proof_root / "certificate"
    certificate_dir.mkdir()
    certificate_artifact = certificate_dir / "certificate.csv"
    certificate_artifact.write_text("ready\ntrue\n", encoding="utf-8")
    certificate_json = (
        certificate_dir
        / "provider_market_data_imbalance_broker_rehearsal_certificate.json"
    )
    certificate_json.write_text(
        json.dumps(
            {
                "certificate_sha256": "a" * 64,
                "payload": {
                    "identity": {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "exchange": "NSE",
                        "adapter": "arrow_ws",
                        "strategy": "imbalance",
                        "market": "india_nse_index_derivatives",
                        "target_mode": "live_dryrun",
                    }
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        certificate_dir,
        run_type="provider_market_data_imbalance_broker_rehearsal_certificate",
        inputs={"source": certificate_source},
    )

    audit_dir = proof_root / "active_lineage_chain_audit"
    audit_dir.mkdir()
    audit_artifact = audit_dir / "audit.csv"
    audit_artifact.write_text("ready\ntrue\n", encoding="utf-8")
    write_experiment_manifest(
        audit_dir,
        run_type="provider_market_data_imbalance_active_lineage_chain_audit",
        inputs={
            "certificate": certificate_dir,
            "certificate_manifest": certificate_dir / "manifest.json",
        },
    )

    chain_digest = "b" * 64
    contract_sha256 = "d" * 64

    def verify_chain(path):
        selected_audit = path.resolve()
        audit_integrity = verify_experiment_manifest(
            selected_audit / "manifest.json",
            expected_run_type=(
                "provider_market_data_imbalance_active_lineage_chain_audit"
            ),
            require_input_fingerprints=True,
        )
        certificate_integrity = verify_experiment_manifest(
            certificate_dir / "manifest.json",
            expected_run_type=(
                "provider_market_data_imbalance_broker_rehearsal_certificate"
            ),
            require_input_fingerprints=True,
        )
        ready = bool(audit_integrity.passed and certificate_integrity.passed)
        return SimpleNamespace(
            ready=ready,
            error="" if ready else audit_integrity.error or certificate_integrity.error,
            audit_dir=selected_audit,
            certificate_dir=certificate_dir.resolve(),
            certificate_manifest_sha256=file_sha256(
                certificate_dir / "manifest.json"
            ),
            chain_digest_sha256=chain_digest,
            provider_lineage_selection_contract={"sha256": contract_sha256},
        )

    monkeypatch.setattr(
        "reports.evidence.verify_provider_market_data_imbalance_active_lineage_chain_audit",
        verify_chain,
    )

    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    catalog_path = catalog_dir / "experiment_catalog.csv"
    catalog = provider_imbalance_ops_launch_catalog_rows()
    certificate_mask = catalog["run_type"].eq(
        "provider_market_data_imbalance_broker_rehearsal_certificate"
    )
    catalog.loc[certificate_mask, "run_dir"] = str(certificate_dir.resolve())
    catalog.loc[
        certificate_mask,
        "provider_active_lineage_chain_audit_dir",
    ] = str(audit_dir.resolve())
    catalog.loc[
        certificate_mask,
        "provider_active_lineage_chain_audit_manifest_sha256",
    ] = file_sha256(audit_dir / "manifest.json")
    catalog.loc[
        certificate_mask,
        "provider_active_lineage_chain_audit_certificate_manifest_sha256",
    ] = file_sha256(certificate_dir / "manifest.json")
    catalog.loc[
        certificate_mask,
        "provider_active_lineage_chain_audit_chain_digest_sha256",
    ] = chain_digest
    catalog.loc[
        certificate_mask,
        "provider_active_lineage_chain_audit_contract_sha256",
    ] = contract_sha256
    catalog.to_csv(catalog_path, index=False)
    write_experiment_manifest(
        catalog_dir,
        run_type="experiment_catalog",
        inputs={
            "audit": audit_dir,
            "audit_manifest": audit_dir / "manifest.json",
            "certificate": certificate_dir,
            "certificate_manifest": certificate_dir / "manifest.json",
        },
    )

    out_dir = tmp_path / "evidence"
    review = write_strategy_evidence_review(
        catalog_path,
        output_dir=out_dir,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types(
                "provider_imbalance_ops_launch"
            ),
            require_provider_lineage_selection=True,
        ),
    )

    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert review.ready
    assert bool(
        review.summary.iloc[0][
            "provider_retained_proofs_directly_fingerprinted"
        ]
    )
    assert int(
        review.summary.iloc[0]["provider_retained_proof_direct_input_count"]
    ) == 4
    assert {
        "catalog",
        "source_catalog_manifest",
        "selected_provider_active_lineage_chain_audit",
        "selected_provider_active_lineage_chain_audit_manifest",
        "selected_provider_broker_rehearsal_certificate",
        "selected_provider_broker_rehearsal_certificate_manifest",
    } == set(manifest["inputs"])
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_evidence_review",
        require_input_fingerprints=True,
    ).passed
    verification = verify_strategy_evidence_review(out_dir)
    assert verification.verified
    assert verification.ready
    assert verification.provider_retained_proofs_current
    assert verification.manifest_input_contract_current
    assert verification.non_authorizing
    release_dir = tmp_path / "release_review"
    assert (
        main(
            [
                "prepare-provider-market-data-imbalance-release-review",
                "--strategy-evidence",
                str(out_dir),
                "--out",
                str(release_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    release_summary = pd.read_csv(
        release_dir
        / "provider_market_data_imbalance_release_review_summary.csv"
    ).iloc[0]
    operator_approval = pd.read_csv(
        release_dir
        / "provider_market_data_imbalance_release_review_operator_approval_template.csv"
    ).iloc[0]
    release_packet = json.loads(
        (
            release_dir
            / "provider_market_data_imbalance_release_review_packet.json"
        ).read_text(encoding="utf-8")
    )
    assert bool(release_summary["ready_for_operator_review"])
    assert bool(release_summary["strategy_evidence_verified"])
    assert bool(release_summary["strategy_evidence_ready"])
    assert release_summary["target_mode"] == "live_dryrun"
    assert release_summary["operator_approval_status"] == "pending"
    assert not bool(release_summary["operator_approved"])
    assert not bool(release_summary["release_approved"])
    assert not bool(release_summary["submission_enabled"])
    assert not bool(release_summary["broker_api_called"])
    assert not bool(release_summary["authorizes_submission"])
    assert operator_approval["decision"] == "pending"
    assert operator_approval["packet_sha256"] == release_packet["packet_sha256"]
    assert not bool(operator_approval["risk_limits_acknowledged"])
    assert not bool(operator_approval["authorizes_submission"])
    assert release_packet["status"] == "ready_for_operator_review"
    assert release_packet["safety"] == {
        "authorizes_submission": False,
        "broker_api_called": False,
        "dry_run_only": True,
        "submission_enabled": False,
    }
    release_manifest_path = release_dir / "manifest.json"
    assert verify_experiment_manifest(
        release_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_review"
        ),
        required_artifacts=(
            "provider_market_data_imbalance_release_review_summary.csv",
            "provider_market_data_imbalance_release_review_operator_approval_template.csv",
            "provider_market_data_imbalance_release_review_packet.json",
            "provider_market_data_imbalance_release_review_runbook.md",
        ),
        require_input_fingerprints=True,
    ).passed
    release_verification = (
        verify_provider_market_data_imbalance_release_review(release_dir)
    )
    assert release_verification.verified
    assert release_verification.ready
    assert release_verification.manifest_current
    assert release_verification.source_current
    assert release_verification.artifacts_consistent
    assert release_verification.non_authorizing
    assert release_verification.operator_approval_pending
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-release-review",
                "--release-review",
                str(release_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    release_catalog = catalog_experiment_runs([release_dir]).catalog.iloc[0]
    assert release_catalog["run_type"] == (
        "provider_market_data_imbalance_release_review"
    )
    assert bool(release_catalog["summary_status"])
    assert not bool(release_catalog["summary_authorizes_submission"])
    assert bool(
        release_catalog[
            "provider_release_review_verification_verified"
        ]
    )

    original_release_packet_text = (
        release_dir
        / "provider_market_data_imbalance_release_review_packet.json"
    ).read_text(encoding="utf-8")
    tampered_release_packet = json.loads(original_release_packet_text)
    tampered_release_packet["safety"]["authorizes_submission"] = True
    (
        release_dir
        / "provider_market_data_imbalance_release_review_packet.json"
    ).write_text(
        json.dumps(tampered_release_packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release_manifest = json.loads(
        release_manifest_path.read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        release_dir,
        run_type="provider_market_data_imbalance_release_review",
        parameters=release_manifest["parameters"],
        inputs=_manifest_input_paths(release_manifest["inputs"]),
        extra=release_manifest["extra"],
    )
    assert verify_experiment_manifest(
        release_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_review"
        ),
        require_input_fingerprints=True,
    ).passed
    tampered_release_verification = (
        verify_provider_market_data_imbalance_release_review(release_dir)
    )
    assert not tampered_release_verification.verified
    assert tampered_release_verification.manifest_current
    assert not tampered_release_verification.artifacts_consistent
    assert not tampered_release_verification.non_authorizing
    tampered_release_catalog = catalog_experiment_runs([release_dir])
    assert not bool(tampered_release_catalog.catalog.iloc[0]["summary_status"])
    (
        release_dir
        / "provider_market_data_imbalance_release_review_packet.json"
    ).write_text(original_release_packet_text, encoding="utf-8")
    write_experiment_manifest(
        release_dir,
        run_type="provider_market_data_imbalance_release_review",
        parameters=release_manifest["parameters"],
        inputs=_manifest_input_paths(release_manifest["inputs"]),
        extra=release_manifest["extra"],
    )
    assert verify_provider_market_data_imbalance_release_review(
        release_dir
    ).verified

    original_release_manifest_text = release_manifest_path.read_text(
        encoding="utf-8"
    )
    tampered_release_manifest = json.loads(original_release_manifest_text)
    tampered_release_manifest["extra"][
        "operator_approval_required"
    ] = False
    release_manifest_path.write_text(
        json.dumps(tampered_release_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert verify_experiment_manifest(
        release_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_review"
        ),
        require_input_fingerprints=True,
    ).passed
    metadata_tampered_release_verification = (
        verify_provider_market_data_imbalance_release_review(release_dir)
    )
    assert not metadata_tampered_release_verification.verified
    assert metadata_tampered_release_verification.manifest_current
    assert not metadata_tampered_release_verification.artifacts_consistent
    release_manifest_path.write_text(
        original_release_manifest_text,
        encoding="utf-8",
    )
    assert verify_provider_market_data_imbalance_release_review(
        release_dir
    ).verified

    approved_operator_decision_values = operator_approval.to_dict()
    approved_operator_decision_values.update(
        {
            "decision": "approved",
            "operator_id": "ops-reviewer-1",
            "operator_role": "risk_operator",
            "reviewed_at_utc": "2026-07-13T15:15:00+00:00",
            "risk_limits_acknowledged": True,
            "kill_switch_acknowledged": True,
            "rollback_plan_acknowledged": True,
            "notes": "approved for controlled live dry run",
            "authorizes_submission": False,
        }
    )
    approved_operator_decision = pd.DataFrame(
        [approved_operator_decision_values]
    )
    approved_operator_decision_path = (
        tmp_path / "approved_operator_decision.csv"
    )
    approved_operator_decision.to_csv(
        approved_operator_decision_path,
        index=False,
    )
    approved_decision_dir = tmp_path / "approved_release_decision"
    assert (
        main(
            [
                "finalize-provider-market-data-imbalance-release-decision",
                "--release-review",
                str(release_dir),
                "--operator-decision",
                str(approved_operator_decision_path),
                "--out",
                str(approved_decision_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    approved_decision_summary = pd.read_csv(
        approved_decision_dir
        / "provider_market_data_imbalance_release_decision_summary.csv"
    ).iloc[0]
    sealed_decision = json.loads(
        (
            approved_decision_dir
            / "provider_market_data_imbalance_release_decision.json"
        ).read_text(encoding="utf-8")
    )
    assert bool(approved_decision_summary["sealed"])
    assert bool(
        approved_decision_summary["approved_for_live_dryrun"]
    )
    assert approved_decision_summary["decision"] == "approved"
    assert not bool(approved_decision_summary["submission_enabled"])
    assert not bool(approved_decision_summary["broker_api_called"])
    assert not bool(approved_decision_summary["authorizes_submission"])
    assert sealed_decision["sealed"] is True
    assert sealed_decision["approved_for_live_dryrun"] is True
    assert sealed_decision["safety"] == {
        "authorizes_submission": False,
        "broker_api_called": False,
        "dry_run_only": True,
        "submission_enabled": False,
    }
    approved_decision_verification = (
        verify_provider_market_data_imbalance_release_decision(
            approved_decision_dir
        )
    )
    assert approved_decision_verification.verified
    assert approved_decision_verification.sealed
    assert approved_decision_verification.approved
    assert approved_decision_verification.ready
    assert approved_decision_verification.manifest_current
    assert approved_decision_verification.release_review_current
    assert approved_decision_verification.operator_decision_current
    assert approved_decision_verification.artifacts_consistent
    assert approved_decision_verification.non_authorizing
    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_release_decision(
            release_dir,
            approved_operator_decision_path,
            approved_decision_dir,
        )
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-release-decision",
                "--release-decision",
                str(approved_decision_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    approved_decision_catalog = catalog_experiment_runs(
        [approved_decision_dir]
    )
    approved_decision_catalog_row = (
        approved_decision_catalog.catalog.iloc[0]
    )
    assert bool(approved_decision_catalog_row["summary_status"])
    assert bool(
        approved_decision_catalog_row[
            "provider_release_decision_verification_verified"
        ]
    )
    assert bool(
        approved_decision_catalog_row[
            "provider_release_decision_verification_approved"
        ]
    )
    assert int(
        approved_decision_catalog.summary.iloc[0][
            "provider_release_decision_verification_ready_runs"
        ]
    ) == 1

    rejected_operator_decision = approved_operator_decision.copy()
    rejected_operator_decision.loc[0, "decision"] = "rejected"
    rejected_operator_decision.loc[0, "notes"] = (
        "rollback owner unavailable"
    )
    rejected_operator_decision_path = (
        tmp_path / "rejected_operator_decision.csv"
    )
    rejected_operator_decision.to_csv(
        rejected_operator_decision_path,
        index=False,
    )
    rejected_decision_dir = tmp_path / "rejected_release_decision"
    rejected_report = write_provider_market_data_imbalance_release_decision(
        release_dir,
        rejected_operator_decision_path,
        rejected_decision_dir,
    )
    assert rejected_report.sealed
    assert not rejected_report.ready
    rejected_verification = (
        verify_provider_market_data_imbalance_release_decision(
            rejected_decision_dir
        )
    )
    assert rejected_verification.verified
    assert rejected_verification.sealed
    assert not rejected_verification.approved
    assert not rejected_verification.ready
    assert rejected_verification.non_authorizing
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-release-decision",
                "--release-decision",
                str(rejected_decision_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )
    rejected_catalog = catalog_experiment_runs([rejected_decision_dir])
    assert bool(rejected_catalog.catalog.iloc[0]["summary_status"])
    assert (
        rejected_catalog.catalog.iloc[0][
            "provider_release_decision_verification_status"
        ]
        == "verified_rejected"
    )

    missing_attestation = approved_operator_decision.copy()
    missing_attestation.loc[0, "kill_switch_acknowledged"] = False
    missing_attestation_path = tmp_path / "missing_attestation.csv"
    missing_attestation.to_csv(missing_attestation_path, index=False)
    missing_attestation_dir = tmp_path / "missing_attestation_decision"
    with pytest.raises(
        ValueError,
        match="kill_switch_acknowledged",
    ):
        write_provider_market_data_imbalance_release_decision(
            release_dir,
            missing_attestation_path,
            missing_attestation_dir,
        )
    assert not missing_attestation_dir.exists()

    approved_decision_manifest_path = (
        approved_decision_dir / "manifest.json"
    )
    original_sealed_decision_text = (
        approved_decision_dir
        / "provider_market_data_imbalance_release_decision.json"
    ).read_text(encoding="utf-8")
    tampered_sealed_decision = json.loads(original_sealed_decision_text)
    tampered_sealed_decision["safety"]["authorizes_submission"] = True
    (
        approved_decision_dir
        / "provider_market_data_imbalance_release_decision.json"
    ).write_text(
        json.dumps(tampered_sealed_decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    approved_decision_manifest = json.loads(
        approved_decision_manifest_path.read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        approved_decision_dir,
        run_type=(
            "provider_market_data_imbalance_release_decision"
        ),
        parameters=approved_decision_manifest["parameters"],
        inputs=_manifest_input_paths(approved_decision_manifest["inputs"]),
        extra=approved_decision_manifest["extra"],
    )
    assert verify_experiment_manifest(
        approved_decision_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_decision"
        ),
        require_input_fingerprints=True,
    ).passed
    tampered_decision_verification = (
        verify_provider_market_data_imbalance_release_decision(
            approved_decision_dir
        )
    )
    assert not tampered_decision_verification.verified
    assert tampered_decision_verification.manifest_current
    assert not tampered_decision_verification.artifacts_consistent
    assert not tampered_decision_verification.non_authorizing
    tampered_decision_catalog = catalog_experiment_runs(
        [approved_decision_dir]
    )
    assert not bool(
        tampered_decision_catalog.catalog.iloc[0]["summary_status"]
    )
    (
        approved_decision_dir
        / "provider_market_data_imbalance_release_decision.json"
    ).write_text(original_sealed_decision_text, encoding="utf-8")
    write_experiment_manifest(
        approved_decision_dir,
        run_type=(
            "provider_market_data_imbalance_release_decision"
        ),
        parameters=approved_decision_manifest["parameters"],
        inputs=_manifest_input_paths(approved_decision_manifest["inputs"]),
        extra=approved_decision_manifest["extra"],
    )
    assert verify_provider_market_data_imbalance_release_decision(
        approved_decision_dir
    ).verified

    original_operator_decision_text = approved_operator_decision_path.read_text(
        encoding="utf-8"
    )
    approved_operator_decision_path.write_text(
        original_operator_decision_text.replace(
            "risk_operator",
            "changed_role",
        ),
        encoding="utf-8",
    )
    operator_drift_verification = (
        verify_provider_market_data_imbalance_release_decision(
            approved_decision_dir
        )
    )
    assert not operator_drift_verification.verified
    assert not operator_drift_verification.operator_decision_current
    approved_operator_decision_path.write_text(
        original_operator_decision_text,
        encoding="utf-8",
    )
    assert verify_provider_market_data_imbalance_release_decision(
        approved_decision_dir
    ).verified

    controls_dir = tmp_path / "live_dryrun_controls"
    controls_dir.mkdir()
    rollback_runbook_path = controls_dir / "rollback.md"
    rollback_runbook_path.write_text(
        "# Controlled live dry-run rollback\n\nStop the runtime and reconcile outputs.\n",
        encoding="utf-8",
    )
    runtime_controls = {
        "contract_version": "provider_live_dryrun_runtime_controls/v1",
        "decision_id": str(approved_decision_summary["decision_id"]),
        "decision_sha256": str(
            approved_decision_summary["decision_sha256"]
        ),
        "provider_session": {
            "provider": "arrow_money",
            "transport": "websocket",
            "exchange": "NSE",
            "adapter": "arrow_ws",
            "session_id": "nse-live-dryrun-20260714",
            "trading_date": "2026-07-14",
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        },
        "limits": {
            "max_orders_per_session": 100,
            "max_notional_per_session": 1_000_000.0,
            "max_open_orders": 10,
            "max_position_lots": 5,
        },
        "kill_switch": {
            "enabled": True,
            "trigger_on_limit_breach": True,
            "stop_new_orders": True,
            "cancel_open_orders": True,
            "owner": "risk_operator",
        },
        "rollback": {
            "procedure_id": "rollback-v1",
            "owner": "ops",
            "runbook_path": rollback_runbook_path.name,
            "runbook_sha256": file_sha256(rollback_runbook_path),
        },
        "safety": {
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
        },
    }
    runtime_controls_path = controls_dir / "runtime_controls.json"
    runtime_controls_path.write_text(
        json.dumps(runtime_controls, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    handoff_dir = tmp_path / "live_dryrun_handoff"
    assert (
        main(
            [
                "prepare-provider-market-data-imbalance-live-dryrun-handoff",
                "--release-decision",
                str(approved_decision_dir),
                "--runtime-controls",
                str(runtime_controls_path),
                "--out",
                str(handoff_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    handoff_plan_path = (
        handoff_dir
        / "provider_market_data_imbalance_live_dryrun_handoff_plan.json"
    )
    handoff_plan = json.loads(handoff_plan_path.read_text(encoding="utf-8"))
    assert handoff_plan["identity"]["provider"] == "arrow_money"
    assert handoff_plan["identity"]["session_id"] == (
        "nse-live-dryrun-20260714"
    )
    assert handoff_plan["limits"]["max_orders_per_session"] == 100
    assert handoff_plan["limits"]["max_notional_per_session"] == 1_000_000.0
    assert handoff_plan["safety"]["execution_enabled"] is False
    assert handoff_plan["safety"]["dry_run_only"] is True
    assert handoff_plan["safety"]["submission_enabled"] is False
    assert handoff_plan["safety"]["broker_api_called"] is False
    assert handoff_plan["safety"]["authorizes_submission"] is False
    assert handoff_plan["safety"]["credential_values_stored"] is False
    assert handoff_plan["safety"]["requires_separate_runtime_launcher"] is True
    handoff_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_dir)
    )
    assert handoff_verification.verified
    assert handoff_verification.ready
    assert handoff_verification.manifest_current
    assert handoff_verification.release_decision_current
    assert handoff_verification.runtime_controls_current
    assert handoff_verification.rollback_runbook_current
    assert handoff_verification.artifacts_consistent
    assert handoff_verification.non_authorizing
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-live-dryrun-handoff",
                "--handoff",
                str(handoff_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    handoff_catalog = catalog_experiment_runs([handoff_dir])
    handoff_catalog_row = handoff_catalog.catalog.iloc[0]
    assert bool(handoff_catalog_row["summary_status"])
    assert bool(
        handoff_catalog_row[
            "provider_live_dryrun_handoff_verification_verified"
        ]
    )
    assert bool(
        handoff_catalog_row[
            "provider_live_dryrun_handoff_verification_ready"
        ]
    )
    assert int(
        handoff_catalog.summary.iloc[0][
            "provider_live_dryrun_handoff_verification_ready_runs"
        ]
    ) == 1
    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_handoff(
            approved_decision_dir,
            runtime_controls_path,
            handoff_dir,
        )
    with pytest.raises(ValueError, match="verified approved release decision"):
        write_provider_market_data_imbalance_live_dryrun_handoff(
            rejected_decision_dir,
            runtime_controls_path,
            tmp_path / "handoff_from_rejected_decision",
        )

    invalid_controls = json.loads(json.dumps(runtime_controls))
    invalid_controls["provider_session"]["provider"] = "wrong_provider"
    invalid_controls_path = controls_dir / "invalid_provider_controls.json"
    invalid_controls_path.write_text(
        json.dumps(invalid_controls, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="provider_session_provider_matches_certificate",
    ):
        write_provider_market_data_imbalance_live_dryrun_handoff(
            approved_decision_dir,
            invalid_controls_path,
            tmp_path / "handoff_invalid_provider",
        )
    credential_controls = json.loads(json.dumps(runtime_controls))
    credential_controls["provider_session"]["api_token"] = "must-not-be-stored"
    credential_controls_path = controls_dir / "credential_controls.json"
    credential_controls_path.write_text(
        json.dumps(credential_controls, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="controls_credential_free"):
        write_provider_market_data_imbalance_live_dryrun_handoff(
            approved_decision_dir,
            credential_controls_path,
            tmp_path / "handoff_with_credential",
        )
    fractional_controls = json.loads(json.dumps(runtime_controls))
    fractional_controls["limits"]["max_orders_per_session"] = 100.5
    fractional_controls_path = controls_dir / "fractional_controls.json"
    fractional_controls_path.write_text(
        json.dumps(fractional_controls, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="max_orders_positive"):
        write_provider_market_data_imbalance_live_dryrun_handoff(
            approved_decision_dir,
            fractional_controls_path,
            tmp_path / "handoff_fractional_limit",
        )

    handoff_manifest_path = handoff_dir / "manifest.json"
    handoff_manifest = json.loads(
        handoff_manifest_path.read_text(encoding="utf-8")
    )
    original_handoff_plan_text = handoff_plan_path.read_text(encoding="utf-8")
    tampered_handoff_plan = json.loads(original_handoff_plan_text)
    tampered_handoff_plan["safety"]["authorizes_submission"] = True
    handoff_plan_path.write_text(
        json.dumps(tampered_handoff_plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        handoff_dir,
        run_type="provider_market_data_imbalance_live_dryrun_handoff",
        parameters=handoff_manifest["parameters"],
        inputs=_manifest_input_paths(handoff_manifest["inputs"]),
        extra=handoff_manifest["extra"],
    )
    assert verify_experiment_manifest(
        handoff_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_handoff"
        ),
        require_input_fingerprints=True,
    ).passed
    tampered_handoff_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_dir)
    )
    assert not tampered_handoff_verification.verified
    assert tampered_handoff_verification.manifest_current
    assert not tampered_handoff_verification.artifacts_consistent
    assert not tampered_handoff_verification.non_authorizing
    tampered_handoff_catalog = catalog_experiment_runs([handoff_dir])
    assert not bool(tampered_handoff_catalog.catalog.iloc[0]["summary_status"])
    handoff_plan_path.write_text(
        original_handoff_plan_text,
        encoding="utf-8",
    )
    write_experiment_manifest(
        handoff_dir,
        run_type="provider_market_data_imbalance_live_dryrun_handoff",
        parameters=handoff_manifest["parameters"],
        inputs=_manifest_input_paths(handoff_manifest["inputs"]),
        extra=handoff_manifest["extra"],
    )
    assert verify_provider_market_data_imbalance_live_dryrun_handoff(
        handoff_dir
    ).verified

    original_runtime_controls_text = runtime_controls_path.read_text(
        encoding="utf-8"
    )
    runtime_controls_path.write_text(
        original_runtime_controls_text.replace(
            "nse-live-dryrun-20260714",
            "changed-session",
        ),
        encoding="utf-8",
    )
    controls_drift_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_dir)
    )
    assert not controls_drift_verification.verified
    assert not controls_drift_verification.runtime_controls_current
    runtime_controls_path.write_text(
        original_runtime_controls_text,
        encoding="utf-8",
    )
    original_rollback_text = rollback_runbook_path.read_text(encoding="utf-8")
    rollback_runbook_path.write_text(
        original_rollback_text + "Unexpected drift.\n",
        encoding="utf-8",
    )
    rollback_drift_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_dir)
    )
    assert not rollback_drift_verification.verified
    assert not rollback_drift_verification.rollback_runbook_current
    rollback_runbook_path.write_text(original_rollback_text, encoding="utf-8")
    assert verify_provider_market_data_imbalance_live_dryrun_handoff(
        handoff_dir
    ).verified

    backend_module_name = (
        f"trusted_runtime_preflight_backend_{drift_target}"
    )
    backend_module_path = tmp_path / f"{backend_module_name}.py"
    backend_module_path.write_text(
        "from provider_connectivity import ProviderConnectivityOutcome\n\n"
        "def probe(request):\n"
        "    return ProviderConnectivityOutcome(\n"
        "        connected=True,\n"
        "        authenticated=True,\n"
        "        market_data_readable=True,\n"
        "        protocol=request.transport,\n"
        "    )\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    runtime_api_key = "runtime-key-must-not-be-stored"
    runtime_api_secret = "runtime-secret-must-not-be-stored"
    monkeypatch.setenv("ARROW_MONEY_API_KEY", runtime_api_key)
    monkeypatch.setenv("ARROW_MONEY_API_SECRET", runtime_api_secret)
    monkeypatch.setenv(
        "ARROW_MONEY_PROVIDER_CONNECTIVITY_BACKEND",
        f"{backend_module_name}:probe",
    )
    runtime_profile = {
        "contract_version": (
            "provider_live_dryrun_runtime_preflight_profile/v1"
        ),
        "capability": "market_data_connectivity",
        "handoff_id": handoff_plan["handoff_id"],
        "plan_sha256": handoff_plan["plan_sha256"],
        "identity": {
            field: handoff_plan["identity"][field]
            for field in (
                "provider",
                "adapter",
                "transport",
                "market",
                "exchange",
                "session_id",
            )
        },
        "endpoint": "wss://feed.arrow.money/market-data/nse",
        "credential_env_vars": [
            "ARROW_MONEY_API_KEY",
            "ARROW_MONEY_API_SECRET",
        ],
        "safety": {
            "connectivity_only": True,
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_order_api_enabled": False,
            "authorizes_submission": False,
            "credential_values_stored": False,
        },
    }
    runtime_profile_path = controls_dir / "runtime_preflight_profile.json"
    runtime_profile_path.write_text(
        json.dumps(runtime_profile, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    runtime_preflight_dir = tmp_path / "runtime_preflight"
    assert (
        main(
            [
                "preflight-provider-market-data-imbalance-live-dryrun-runtime",
                "--handoff",
                str(handoff_dir),
                "--runtime-profile",
                str(runtime_profile_path),
                "--out",
                str(runtime_preflight_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    runtime_receipt_path = (
        runtime_preflight_dir
        / "provider_market_data_imbalance_live_dryrun_launch_receipt.json"
    )
    runtime_receipt = json.loads(
        runtime_receipt_path.read_text(encoding="utf-8")
    )
    assert runtime_receipt["ready_for_separate_runtime_launch"] is True
    assert runtime_receipt["connectivity"]["probe_called"] is True
    assert runtime_receipt["connectivity"]["connected"] is True
    assert runtime_receipt["connectivity"]["authenticated"] is True
    assert runtime_receipt["connectivity"]["market_data_readable"] is True
    assert runtime_receipt["connectivity"]["backend_entrypoint"] == (
        f"{backend_module_name}:probe"
    )
    assert runtime_receipt["credentials"]["env_presence"] == {
        "ARROW_MONEY_API_KEY": True,
        "ARROW_MONEY_API_SECRET": True,
    }
    for field in (
        "strategy_execution_enabled",
        "launch_executed",
        "release_approved",
        "broker_order_api_enabled",
        "broker_order_api_called",
        "broker_api_called",
        "submission_enabled",
        "authorizes_submission",
        "credential_values_stored",
    ):
        assert runtime_receipt["safety"][field] is False
    assert runtime_receipt["safety"]["connectivity_only"] is True
    assert runtime_receipt["safety"]["dry_run_only"] is True
    assert (
        runtime_receipt["safety"]["requires_separate_runtime_launcher"]
        is True
    )
    serialized_preflight = "\n".join(
        path.read_text(encoding="utf-8")
        for path in runtime_preflight_dir.rglob("*")
        if path.is_file()
    )
    assert runtime_api_key not in serialized_preflight
    assert runtime_api_secret not in serialized_preflight
    runtime_preflight_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            runtime_preflight_dir
        )
    )
    assert runtime_preflight_verification.verified
    assert runtime_preflight_verification.ready
    assert runtime_preflight_verification.manifest_current
    assert runtime_preflight_verification.handoff_current
    assert runtime_preflight_verification.runtime_profile_current
    assert runtime_preflight_verification.artifacts_consistent
    assert runtime_preflight_verification.credential_safe
    assert runtime_preflight_verification.non_authorizing
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-live-dryrun-runtime-preflight",
                "--preflight",
                str(runtime_preflight_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    runtime_preflight_catalog = catalog_experiment_runs(
        [runtime_preflight_dir]
    )
    runtime_preflight_row = runtime_preflight_catalog.catalog.iloc[0]
    assert bool(runtime_preflight_row["summary_status"])
    assert (
        runtime_preflight_row[
            "provider_live_dryrun_runtime_preflight_verification_status"
        ]
        == "verified_ready"
    )
    assert bool(
        runtime_preflight_row[
            "provider_live_dryrun_runtime_preflight_verification_verified"
        ]
    )
    assert bool(
        runtime_preflight_row[
            "provider_live_dryrun_runtime_preflight_verification_ready"
        ]
    )
    assert int(
        runtime_preflight_catalog.summary.iloc[0][
            "provider_live_dryrun_runtime_preflight_verification_ready_runs"
        ]
    ) == 1
    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            handoff_dir,
            runtime_profile_path,
            runtime_preflight_dir,
        )

    blocked_preflight_dir = tmp_path / "runtime_preflight_missing_credentials"
    blocked_preflight = (
        write_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            handoff_dir,
            runtime_profile_path,
            blocked_preflight_dir,
            backend_entrypoint=(
                "must_not_import_missing_credentials:probe"
            ),
            environ={},
        )
    )
    assert not blocked_preflight.ready
    assert blocked_preflight.receipt["connectivity"]["error_code"] == (
        "credentials_missing"
    )
    blocked_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            blocked_preflight_dir
        )
    )
    assert blocked_verification.verified
    assert not blocked_verification.ready
    assert blocked_verification.credential_safe
    assert blocked_verification.non_authorizing
    blocked_catalog = catalog_experiment_runs([blocked_preflight_dir])
    blocked_row = blocked_catalog.catalog.iloc[0]
    assert not bool(blocked_row["summary_status"])
    assert (
        blocked_row[
            "provider_live_dryrun_runtime_preflight_verification_status"
        ]
        == "verified_blocked"
    )
    assert int(
        blocked_catalog.summary.iloc[0][
            "provider_live_dryrun_runtime_preflight_verification_blocked_runs"
        ]
    ) == 1

    unsafe_runtime_profile = json.loads(json.dumps(runtime_profile))
    unsafe_runtime_profile["endpoint"] += "?token=must-not-be-stored"
    unsafe_runtime_profile_path = controls_dir / "unsafe_runtime_profile.json"
    unsafe_runtime_profile_path.write_text(
        json.dumps(unsafe_runtime_profile, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="endpoint_secure_and_credential_free",
    ):
        write_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            handoff_dir,
            unsafe_runtime_profile_path,
            tmp_path / "unsafe_runtime_preflight",
        )

    runtime_preflight_manifest_path = runtime_preflight_dir / "manifest.json"
    runtime_preflight_manifest = json.loads(
        runtime_preflight_manifest_path.read_text(encoding="utf-8")
    )
    original_runtime_receipt_text = runtime_receipt_path.read_text(
        encoding="utf-8"
    )
    tampered_runtime_receipt = json.loads(original_runtime_receipt_text)
    tampered_runtime_receipt["safety"]["authorizes_submission"] = True
    runtime_receipt_path.write_text(
        json.dumps(tampered_runtime_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        runtime_preflight_dir,
        run_type=(
            "provider_market_data_imbalance_live_dryrun_runtime_preflight"
        ),
        parameters=runtime_preflight_manifest["parameters"],
        inputs=_manifest_input_paths(runtime_preflight_manifest["inputs"]),
        extra=runtime_preflight_manifest["extra"],
    )
    assert verify_experiment_manifest(
        runtime_preflight_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_runtime_preflight"
        ),
        require_input_fingerprints=True,
    ).passed
    tampered_runtime_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            runtime_preflight_dir
        )
    )
    assert not tampered_runtime_verification.verified
    assert tampered_runtime_verification.manifest_current
    assert not tampered_runtime_verification.artifacts_consistent
    assert not tampered_runtime_verification.non_authorizing
    assert not bool(
        catalog_experiment_runs(
            [runtime_preflight_dir]
        ).catalog.iloc[0]["summary_status"]
    )
    runtime_receipt_path.write_text(
        original_runtime_receipt_text,
        encoding="utf-8",
    )
    write_experiment_manifest(
        runtime_preflight_dir,
        run_type=(
            "provider_market_data_imbalance_live_dryrun_runtime_preflight"
        ),
        parameters=runtime_preflight_manifest["parameters"],
        inputs=_manifest_input_paths(runtime_preflight_manifest["inputs"]),
        extra=runtime_preflight_manifest["extra"],
    )
    assert verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
        runtime_preflight_dir
    ).verified

    original_runtime_profile_text = runtime_profile_path.read_text(
        encoding="utf-8"
    )
    runtime_profile_path.write_text(
        original_runtime_profile_text.replace(
            "nse-live-dryrun-20260714",
            "changed-runtime-session",
        ),
        encoding="utf-8",
    )
    runtime_profile_drift = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            runtime_preflight_dir
        )
    )
    assert not runtime_profile_drift.verified
    assert not runtime_profile_drift.runtime_profile_current
    runtime_profile_path.write_text(
        original_runtime_profile_text,
        encoding="utf-8",
    )
    assert verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
        runtime_preflight_dir
    ).verified

    runtime_launcher_dir = tmp_path / "runtime_launcher"
    assert (
        main(
            [
                "launch-provider-market-data-imbalance-live-dryrun-simulated-runtime",
                "--preflight",
                str(runtime_preflight_dir),
                "--out",
                str(runtime_launcher_dir),
                "--events",
                "3",
                "--interval-ms",
                "250",
                "--fail-on-halt",
            ]
        )
        == 0
    )
    runtime_terminal_receipt_path = (
        runtime_launcher_dir
        / "provider_market_data_imbalance_live_dryrun_terminal_receipt.json"
    )
    runtime_terminal_receipt = json.loads(
        runtime_terminal_receipt_path.read_text(encoding="utf-8")
    )
    assert runtime_terminal_receipt["completed"] is True
    assert runtime_terminal_receipt["halted"] is False
    assert runtime_terminal_receipt["launcher_mode"] == (
        "deterministic_simulation"
    )
    for field in (
        "provider_network_called",
        "provider_backend_loaded",
        "credential_environment_read",
        "credential_values_stored",
        "strategy_execution_enabled",
        "order_generation_enabled",
        "broker_order_api_imported",
        "broker_order_api_called",
        "broker_api_called",
        "submission_enabled",
        "authorizes_submission",
        "release_approved",
    ):
        assert runtime_terminal_receipt["safety"][field] is False
    serialized_launcher = "\n".join(
        path.read_text(encoding="utf-8")
        for path in runtime_launcher_dir.rglob("*")
        if path.is_file()
    )
    assert runtime_api_key not in serialized_launcher
    assert runtime_api_secret not in serialized_launcher
    runtime_launcher_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            runtime_launcher_dir
        )
    )
    assert runtime_launcher_verification.verified
    assert runtime_launcher_verification.completed
    assert not runtime_launcher_verification.halted
    assert runtime_launcher_verification.manifest_current
    assert runtime_launcher_verification.preflight_current
    assert runtime_launcher_verification.handoff_current
    assert runtime_launcher_verification.artifacts_consistent
    assert runtime_launcher_verification.simulation_only
    assert runtime_launcher_verification.non_authorizing
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-live-dryrun-runtime-launcher",
                "--launcher",
                str(runtime_launcher_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    runtime_launcher_catalog = catalog_experiment_runs(
        [runtime_launcher_dir]
    )
    runtime_launcher_row = runtime_launcher_catalog.catalog.iloc[0]
    assert bool(runtime_launcher_row["summary_status"])
    assert (
        runtime_launcher_row[
            "provider_live_dryrun_runtime_launcher_verification_status"
        ]
        == "verified_completed"
    )
    assert bool(
        runtime_launcher_row[
            "provider_live_dryrun_runtime_launcher_verification_verified"
        ]
    )
    assert int(
        runtime_launcher_catalog.summary.iloc[0][
            "provider_live_dryrun_runtime_launcher_verification_completed_runs"
        ]
    ) == 1
    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            runtime_preflight_dir,
            runtime_launcher_dir,
        )

    runtime_shadow_dir = tmp_path / "runtime_shadow"
    assert (
        main(
            [
                "evaluate-provider-market-data-imbalance-live-dryrun-shadow",
                "--launcher",
                str(runtime_launcher_dir),
                "--out",
                str(runtime_shadow_dir),
                "--fail-on-halt",
            ]
        )
        == 0
    )
    runtime_shadow_receipt_path = (
        runtime_shadow_dir
        / "provider_market_data_imbalance_live_dryrun_shadow_terminal_receipt.json"
    )
    runtime_shadow_receipt = json.loads(
        runtime_shadow_receipt_path.read_text(encoding="utf-8")
    )
    assert runtime_shadow_receipt["completed"] is True
    assert runtime_shadow_receipt["halted"] is False
    for field in (
        "provider_network_called",
        "provider_backend_loaded",
        "credential_environment_read",
        "credential_values_stored",
        "execution_engine_loaded",
        "order_object_created",
        "live_position_created",
        "broker_order_api_imported",
        "broker_order_api_called",
        "broker_api_called",
        "routing_enabled",
        "submission_enabled",
        "authorizes_submission",
        "release_approved",
    ):
        assert runtime_shadow_receipt["safety"][field] is False
    for field in (
        "shadow_only",
        "market_data_read_only",
        "deterministic_evaluation",
        "broker_neutral_intents_only",
        "kill_switch_armed",
        "terminal_flatten_required",
        "requires_separate_order_runtime",
    ):
        assert runtime_shadow_receipt["safety"][field] is True
    runtime_shadow_intents = pd.read_csv(
        runtime_shadow_dir
        / "provider_market_data_imbalance_live_dryrun_shadow_intents.csv"
    )
    assert runtime_shadow_intents["action"].tolist() == [
        "entry",
        "exit_hold",
    ]
    assert set(runtime_shadow_intents["routing_status"]) == {"not_routable"}
    assert set(runtime_shadow_intents["submission_status"]) == {
        "not_submitted"
    }
    serialized_shadow = "\n".join(
        path.read_text(encoding="utf-8")
        for path in runtime_shadow_dir.rglob("*")
        if path.is_file()
    )
    assert runtime_api_key not in serialized_shadow
    assert runtime_api_secret not in serialized_shadow
    runtime_shadow_verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            runtime_shadow_dir
        )
    )
    assert runtime_shadow_verification.verified
    assert runtime_shadow_verification.completed
    assert not runtime_shadow_verification.halted
    assert runtime_shadow_verification.manifest_current
    assert runtime_shadow_verification.launcher_current
    assert runtime_shadow_verification.handoff_current
    assert runtime_shadow_verification.artifacts_consistent
    assert runtime_shadow_verification.shadow_only
    assert runtime_shadow_verification.non_authorizing
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-live-dryrun-shadow-evaluation",
                "--shadow",
                str(runtime_shadow_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    runtime_shadow_catalog = catalog_experiment_runs([runtime_shadow_dir])
    runtime_shadow_row = runtime_shadow_catalog.catalog.iloc[0]
    assert bool(runtime_shadow_row["summary_status"])
    assert (
        runtime_shadow_row[
            "provider_live_dryrun_shadow_verification_status"
        ]
        == "verified_completed"
    )
    assert bool(
        runtime_shadow_row[
            "provider_live_dryrun_shadow_verification_verified"
        ]
    )
    assert int(
        runtime_shadow_catalog.summary.iloc[0][
            "provider_live_dryrun_shadow_verification_completed_runs"
        ]
    ) == 1
    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            runtime_launcher_dir,
            runtime_shadow_dir,
        )

    runtime_calibration_dir = tmp_path / "runtime_shadow_calibration"
    assert (
        main(
            [
                "calibrate-provider-market-data-imbalance-live-dryrun-shadow",
                "--shadow",
                str(runtime_shadow_dir),
                "--out",
                str(runtime_calibration_dir),
                "--fail-on-incomplete",
            ]
        )
        == 0
    )
    runtime_calibration_receipt_path = (
        runtime_calibration_dir
        / "provider_market_data_imbalance_live_dryrun_shadow_calibration_receipt.json"
    )
    runtime_calibration_receipt = json.loads(
        runtime_calibration_receipt_path.read_text(encoding="utf-8")
    )
    assert runtime_calibration_receipt["completed"] is True
    assert runtime_calibration_receipt["insufficient"] is False
    for field in (
        "provider_network_called",
        "provider_backend_loaded",
        "credential_environment_read",
        "credential_values_stored",
        "execution_engine_loaded",
        "order_object_created",
        "live_position_created",
        "broker_order_api_imported",
        "broker_order_api_called",
        "broker_api_called",
        "routing_enabled",
        "submission_enabled",
        "authorizes_submission",
        "performance_gate_enabled",
        "authorizes_promotion",
        "strategy_promoted",
        "release_approved",
    ):
        assert runtime_calibration_receipt["safety"][field] is False
    for field in (
        "calibration_only",
        "shadow_source_only",
        "deterministic_reconstruction",
        "cost_rates_require_external_validation",
        "requires_real_provider_observations",
        "requires_separate_promotion_review",
    ):
        assert runtime_calibration_receipt["safety"][field] is True
    runtime_cost_sensitivity = pd.read_csv(
        runtime_calibration_dir
        / "provider_market_data_imbalance_live_dryrun_shadow_cost_sensitivity.csv"
    )
    assert set(runtime_cost_sensitivity["cost_scenario"]) == {
        "nse_index_futures_reference",
        "nse_index_options_reference",
    }
    assert set(runtime_cost_sensitivity["reference_status"]) == {
        "repository_reference_requires_external_validation"
    }
    serialized_calibration = "\n".join(
        path.read_text(encoding="utf-8")
        for path in runtime_calibration_dir.rglob("*")
        if path.is_file()
    )
    assert runtime_api_key not in serialized_calibration
    assert runtime_api_secret not in serialized_calibration
    runtime_calibration_verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
            runtime_calibration_dir
        )
    )
    assert runtime_calibration_verification.verified
    assert runtime_calibration_verification.completed
    assert not runtime_calibration_verification.insufficient
    assert runtime_calibration_verification.manifest_current
    assert runtime_calibration_verification.shadow_current
    assert runtime_calibration_verification.artifacts_consistent
    assert runtime_calibration_verification.calibration_only
    assert runtime_calibration_verification.non_authorizing
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration",
                "--calibration",
                str(runtime_calibration_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    runtime_calibration_catalog = catalog_experiment_runs(
        [runtime_calibration_dir]
    )
    runtime_calibration_row = runtime_calibration_catalog.catalog.iloc[0]
    assert bool(runtime_calibration_row["summary_status"])
    assert (
        runtime_calibration_row[
            "provider_live_dryrun_shadow_calibration_verification_status"
        ]
        == "verified_completed"
    )
    assert bool(
        runtime_calibration_row[
            "provider_live_dryrun_shadow_calibration_verification_verified"
        ]
    )
    assert int(
        runtime_calibration_catalog.summary.iloc[0][
            "provider_live_dryrun_shadow_calibration_verification_completed_runs"
        ]
    ) == 1
    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
            runtime_shadow_dir,
            runtime_calibration_dir,
        )

    certificate_source.write_text(
        "source\nchanged_after_release_review\n",
        encoding="utf-8",
    )
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_evidence_review",
        require_input_fingerprints=True,
    ).passed
    assert not verify_experiment_manifest(
        release_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_review"
        ),
        require_input_fingerprints=True,
    ).passed
    stale_release_verification = (
        verify_provider_market_data_imbalance_release_review(release_dir)
    )
    assert not stale_release_verification.verified
    assert not stale_release_verification.ready
    assert not stale_release_verification.source_current
    stale_decision_verification = (
        verify_provider_market_data_imbalance_release_decision(
            approved_decision_dir
        )
    )
    assert not stale_decision_verification.verified
    assert not stale_decision_verification.release_review_current
    stale_handoff_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_dir)
    )
    assert not stale_handoff_verification.verified
    assert not stale_handoff_verification.release_decision_current
    stale_runtime_preflight_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            runtime_preflight_dir
        )
    )
    assert not stale_runtime_preflight_verification.verified
    assert not stale_runtime_preflight_verification.handoff_current
    stale_runtime_launcher_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            runtime_launcher_dir
        )
    )
    assert not stale_runtime_launcher_verification.verified
    assert not stale_runtime_launcher_verification.preflight_current
    stale_runtime_shadow_verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            runtime_shadow_dir
        )
    )
    assert not stale_runtime_shadow_verification.verified
    assert not stale_runtime_shadow_verification.launcher_current
    stale_runtime_calibration_verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
            runtime_calibration_dir
        )
    )
    assert not stale_runtime_calibration_verification.verified
    assert not stale_runtime_calibration_verification.shadow_current
    assert not verify_experiment_manifest(
        runtime_calibration_dir / "manifest.json",
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_shadow_calibration"
        ),
        require_input_fingerprints=True,
    ).passed
    assert not verify_experiment_manifest(
        runtime_shadow_dir / "manifest.json",
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_shadow_evaluator"
        ),
        require_input_fingerprints=True,
    ).passed
    assert not verify_experiment_manifest(
        runtime_launcher_dir / "manifest.json",
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_runtime_launcher"
        ),
        require_input_fingerprints=True,
    ).passed
    assert not verify_experiment_manifest(
        runtime_preflight_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_runtime_preflight"
        ),
        require_input_fingerprints=True,
    ).passed
    assert not verify_experiment_manifest(
        handoff_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_live_dryrun_handoff"
        ),
        require_input_fingerprints=True,
    ).passed
    assert not verify_experiment_manifest(
        approved_decision_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_decision"
        ),
        require_input_fingerprints=True,
    ).passed
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-release-review",
                "--release-review",
                str(release_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )
    stale_release_catalog = catalog_experiment_runs([release_dir])
    stale_release_row = stale_release_catalog.catalog.iloc[0]
    assert not bool(stale_release_row["summary_status"])
    assert not bool(
        stale_release_row[
            "provider_release_review_verification_verified"
        ]
    )
    assert int(
        stale_release_catalog.summary.iloc[0][
            "provider_release_review_verification_stale_runs"
        ]
    ) == 1
    with pytest.raises(ValueError, match="verified and ready"):
        write_provider_market_data_imbalance_release_review(
            out_dir,
            tmp_path / "release_review_after_recursive_drift",
        )
    assert not (tmp_path / "release_review_after_recursive_drift").exists()
    certificate_source.write_text("source\nready\n", encoding="utf-8")
    assert verify_experiment_manifest(
        release_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_review"
        ),
        require_input_fingerprints=True,
    ).passed
    assert verify_provider_market_data_imbalance_release_review(
        release_dir
    ).verified
    assert verify_provider_market_data_imbalance_release_decision(
        approved_decision_dir
    ).verified
    assert verify_provider_market_data_imbalance_live_dryrun_handoff(
        handoff_dir
    ).verified
    assert verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
        runtime_preflight_dir
    ).verified
    assert verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
        runtime_launcher_dir
    ).verified
    assert verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        runtime_shadow_dir
    ).verified
    assert verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
        runtime_calibration_dir
    ).verified
    cataloged = catalog_experiment_runs([out_dir])
    cataloged_row = cataloged.catalog.iloc[0]
    assert bool(cataloged_row["summary_status"])
    assert bool(
        cataloged_row["strategy_evidence_verification_required"]
    )
    assert bool(
        cataloged_row["strategy_evidence_verification_verified"]
    )
    assert (
        cataloged_row["strategy_evidence_verification_status"]
        == "verified_current"
    )
    assert int(
        cataloged.summary.iloc[0][
            "strategy_evidence_verification_verified_runs"
        ]
    ) == 1
    manifest_path = out_dir / "manifest.json"
    original_manifest_text = manifest_path.read_text(encoding="utf-8")
    tampered_manifest = json.loads(original_manifest_text)
    tampered_manifest["extra"]["source_catalog_manifest_required"] = False
    manifest_path.write_text(
        json.dumps(tampered_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata_tamper = verify_strategy_evidence_review(out_dir)
    assert not metadata_tamper.verified
    assert metadata_tamper.manifest_current
    assert not metadata_tamper.artifacts_consistent
    summary_path = out_dir / "strategy_evidence_summary.csv"
    original_summary_text = summary_path.read_text(encoding="utf-8")
    tampered_summary = pd.read_csv(summary_path)
    tampered_summary.loc[0, "evidence_profile"] = "default"
    tampered_summary.to_csv(summary_path, index=False)
    bypass_catalog = catalog_experiment_runs([out_dir])
    bypass_row = bypass_catalog.catalog.iloc[0]
    assert bool(
        bypass_row["strategy_evidence_verification_required"]
    )
    assert not bool(bypass_row["summary_status"])
    assert not bool(
        bypass_row["strategy_evidence_verification_verified"]
    )
    summary_path.write_text(original_summary_text, encoding="utf-8")
    manifest_path.write_text(original_manifest_text, encoding="utf-8")

    drifted_artifact = (
        audit_artifact if drift_target == "audit" else certificate_artifact
    )
    drifted_artifact.write_text("ready\nfalse\n", encoding="utf-8")
    assert not verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_evidence_review",
        require_input_fingerprints=True,
    ).passed
    assert not verify_provider_market_data_imbalance_release_review(
        release_dir
    ).verified
    assert not verify_provider_market_data_imbalance_release_decision(
        approved_decision_dir
    ).verified
    assert not verify_provider_market_data_imbalance_live_dryrun_handoff(
        handoff_dir
    ).verified
    assert not verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
        runtime_preflight_dir
    ).verified
    assert not verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
        runtime_launcher_dir
    ).verified
    assert not verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        runtime_shadow_dir
    ).verified
    assert not verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
        runtime_calibration_dir
    ).verified
    assert not verify_experiment_manifest(
        release_manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_release_review"
        ),
        require_input_fingerprints=True,
    ).passed
    stale_verification = verify_strategy_evidence_review(out_dir)
    assert not stale_verification.verified
    assert not stale_verification.ready
    assert not stale_verification.manifest_current
    assert not stale_verification.source_current
    assert (
        main(
            [
                "verify-strategy-evidence",
                "--evidence",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )
    stale_catalog = catalog_experiment_runs([out_dir])
    stale_row = stale_catalog.catalog.iloc[0]
    assert not bool(stale_row["summary_status"])
    assert not bool(
        stale_row["strategy_evidence_verification_verified"]
    )
    assert (
        stale_row["strategy_evidence_verification_status"]
        == "stale_or_inconsistent"
    )
    assert int(
        stale_catalog.summary.iloc[0][
            "strategy_evidence_verification_stale_runs"
        ]
    ) == 1

    replay = write_strategy_evidence_review(
        catalog_path,
        output_dir=tmp_path / f"evidence_after_{drift_target}_drift",
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types(
                "provider_imbalance_ops_launch"
            ),
            require_provider_lineage_selection=True,
        ),
    )
    failed = set(
        replay.checks.loc[
            ~replay.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not replay.ready
    assert "source_catalog_manifest_current" in failed
    assert "selected_provider_active_lineage_chain_audit_current" in failed
    if drift_target == "certificate":
        assert (
            "selected_provider_broker_rehearsal_certificate_current" in failed
        )


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


def test_cli_strategy_evidence_provider_ops_launch_rejects_flat_catalog_replay(
    tmp_path,
):
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
    lineage_selection = pd.read_csv(
        out_dir / "strategy_evidence_provider_lineage_selection.csv"
    )
    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert set(items["required_run_type"]) == set(EVIDENCE_PROFILE_RUN_TYPES["provider_imbalance_ops_launch"])
    assert not bool(summary.loc[0, "ready"])
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
    assert bool(summary.loc[0, "require_provider_lineage_selection"])
    assert summary.loc[0, "provider_lineage_selection_policy"] == "required"
    assert int(summary.loc[0, "provider_lineage_covered_run_type_count"]) == 3
    assert len(lineage_selection) == 3
    assert lineage_selection["selected"].astype(bool).all()
    assert int(summary.loc[0, "provider_lineage_selected_pair_count"]) == 3
    assert len(summary.loc[0, "provider_lineage_selection_contract_sha256"]) == 64
    assert bool(summary.loc[0, "source_catalog_manifest_required"])
    assert not bool(summary.loc[0, "source_catalog_manifest_current"])
    assert {
        "source_catalog_manifest_current",
        "selected_provider_active_lineage_chain_audit_current",
        "selected_provider_broker_rehearsal_certificate_current",
        "provider_retained_proof_catalog_binding_current",
        "provider_retained_proof_contract_binding_current",
    } <= failed


def test_cli_strategy_evidence_provider_lineage_audit_override_is_non_candidate(
    tmp_path,
):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "provider_ops_launch_lineage_audit"
    catalog = provider_imbalance_ops_launch_catalog_rows().drop(
        columns=[
            "provider_lineage_selection_status",
            "provider_lineage_selection_eligible",
        ]
    )
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
            "--allow-ineligible-provider-lineage-for-audit",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_evidence_checks.csv")
    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 0
    assert not bool(summary.loc[0, "ready"])
    assert failed == {"provider_lineage_selection_audit_only"}
    assert summary.loc[0, "provider_lineage_selection_policy"] == "audit_only"
    assert summary.loc[0, "recommendation"] == "provider_lineage_audit_only"


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
