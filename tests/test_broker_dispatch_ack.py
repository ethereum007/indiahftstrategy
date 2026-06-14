import json

import pandas as pd

from hft_cli import main
from reports.broker_dispatch_ack import (
    evaluate_broker_dispatch_acknowledgements,
    write_broker_dispatch_acknowledgements,
)
from reports.catalog import catalog_experiment_runs


def path_tail(value):
    return str(value).replace("\\", "/")


def dispatch_summary(
    ready=True,
    route_roundtrip_provided=True,
    route_roundtrip_ready=True,
    route_roundtrip_target_mode="live_dryrun",
    route_roundtrip_strategy="lead_lag_taker",
    route_roundtrip_market="india_nse_index_derivatives",
    route_roundtrip_scenario_key="trigger_ticks=2",
    route_roundtrip_batch_id="BDP-0",
    route_roundtrip_requests=2,
    route_roundtrip_acked_orders=2,
    route_roundtrip_missing_request_acks=0,
    route_roundtrip_rejected_orders=0,
    route_roundtrip_unmatched_acks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "dispatch_orders": 2,
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
                "route_dispatch_roundtrip_required": True,
                "route_dispatch_roundtrip_provided": route_roundtrip_provided,
                "route_dispatch_roundtrip_ready": route_roundtrip_ready,
                "route_dispatch_roundtrip_target_mode": route_roundtrip_target_mode,
                "route_dispatch_roundtrip_strategy": route_roundtrip_strategy,
                "route_dispatch_roundtrip_market": route_roundtrip_market,
                "route_dispatch_roundtrip_scenario_key": route_roundtrip_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "route_dispatch_roundtrip_requests": route_roundtrip_requests,
                "route_dispatch_roundtrip_acked_orders": route_roundtrip_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_roundtrip_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_roundtrip_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_roundtrip_unmatched_acks,
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "failed_checks": 0 if ready else 1,
                "recommendation": "ready_for_broker_dryrun_dispatch"
                if ready
                else "fix_broker_dispatch_plan",
            }
        ]
    )


def dispatch_orders():
    return pd.DataFrame(
        [
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": "BDP-0",
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": "BDP-0",
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
        ]
    )


def ack_rows(
    statuses=("accepted", "accepted"),
    *,
    extra=False,
    duplicate=False,
    by_source=False,
    route_roundtrip_batch_id="BDP-0",
):
    rows = []
    for index, status in enumerate(statuses, start=1):
        route_batch_id = _route_batch_id(route_roundtrip_batch_id, index)
        row = {
            "status": status,
            "broker_order_id": f"BRK-{index}",
            "ack_ts_ns": 1_000 + index,
        }
        if route_batch_id is not None:
            row["route_dispatch_roundtrip_batch_id"] = route_batch_id
        if by_source:
            row["source_order_id"] = f"ORD-{index}"
        else:
            row["dispatch_order_id"] = f"DSP-{index}"
            row["source_order_id"] = f"ORD-{index}"
        rows.append(row)
    if duplicate:
        route_batch_id = _route_batch_id(route_roundtrip_batch_id, 1)
        rows.append(
            {
                "dispatch_order_id": "DSP-1",
                "source_order_id": "ORD-1",
                "status": "accepted",
                "broker_order_id": "BRK-1-DUP",
                "ack_ts_ns": 1_099,
                **(
                    {"route_dispatch_roundtrip_batch_id": route_batch_id}
                    if route_batch_id is not None
                    else {}
                ),
            }
        )
    if extra:
        route_batch_id = _route_batch_id(route_roundtrip_batch_id, 999)
        rows.append(
            {
                "dispatch_order_id": "DSP-999",
                "source_order_id": "ORD-999",
                "status": "accepted",
                "broker_order_id": "BRK-999",
                "ack_ts_ns": 9_999,
                **(
                    {"route_dispatch_roundtrip_batch_id": route_batch_id}
                    if route_batch_id is not None
                    else {}
                ),
            }
        )
    return pd.DataFrame(rows)


def _route_batch_id(value, index):
    if isinstance(value, (list, tuple)):
        return value[index - 1] if index <= len(value) else value[-1]
    return value


def dispatch_config(
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
    )
    return {
        "broker_readiness": {
            "adapter_schema_status": broker_schema_status,
            "schema_reviewed": broker_schema_reviewed,
            "schema_review_mode": broker_schema_review_mode,
        },
        "route_readiness": {
            "required": route_readiness_required,
            "provided": route_readiness_provided,
            "ready": route_readiness_ready,
            "strategy": route_readiness_strategy,
            "market": route_readiness_market,
            "route_ready_pairs": route_readiness_route_ready_pairs,
            "gap_pairs": route_readiness_gap_pairs,
            "recommendation": route_readiness_recommendation,
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
        }
    }


def shadow_broker_config(
    sessions=2,
    ready_sessions=2,
    adapter="arrow_money",
    adapter_count=1,
    route_sessions=2,
    route_ready_sessions=2,
    route_strategy="lead_lag_taker",
    route_market="india_nse_index_derivatives",
    route_gap_pairs=0,
    dispatch_sessions=2,
    dispatch_ready_sessions=2,
    dispatch_strategy="lead_lag_taker",
    dispatch_market="india_nse_index_derivatives",
    dispatch_scenario_count=1,
    dispatch_missing_request_acks=0,
    dispatch_rejected_orders=0,
    dispatch_unmatched_acks=0,
    route_dispatch_sessions=2,
    route_dispatch_ready_sessions=2,
    route_dispatch_strategy="lead_lag_taker",
    route_dispatch_market="india_nse_index_derivatives",
    route_dispatch_scenario_count=1,
):
    return {
        "sessions": sessions,
        "ready_sessions": ready_sessions,
        "adapter": adapter,
        "adapter_count": adapter_count,
        "route_readiness": {
            "sessions": route_sessions,
            "ready_sessions": route_ready_sessions,
            "strategy": route_strategy,
            "market": route_market,
            "max_gap_pairs": route_gap_pairs,
        },
        "dispatch_roundtrip": {
            "sessions": dispatch_sessions,
            "ready_sessions": dispatch_ready_sessions,
            "strategy": dispatch_strategy,
            "market": dispatch_market,
            "scenario_count": dispatch_scenario_count,
            "max_missing_request_acks": dispatch_missing_request_acks,
            "max_rejected_orders": dispatch_rejected_orders,
            "max_unmatched_acks": dispatch_unmatched_acks,
        },
        "route_dispatch_roundtrip": {
            "sessions": route_dispatch_sessions,
            "ready_sessions": route_dispatch_ready_sessions,
            "strategy": route_dispatch_strategy,
            "market": route_dispatch_market,
            "scenario_count": route_dispatch_scenario_count,
        },
    }


def write_inputs(
    tmp_path,
    *,
    dispatch_ready=True,
    ack_statuses=("accepted", "accepted"),
    route_roundtrip=True,
    route_readiness=True,
):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    dispatch_summary(
        dispatch_ready,
        route_roundtrip_provided=route_roundtrip,
        route_roundtrip_ready=route_roundtrip,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    dispatch_orders().to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(
            dispatch_config(
                route_readiness_provided=route_readiness,
                route_readiness_ready=route_readiness,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    acks = tmp_path / "broker_dispatch_acks.csv"
    ack_rows(ack_statuses).to_csv(acks, index=False)
    return dispatch, acks


def test_broker_dispatch_ack_accepts_complete_source_id_acks():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(by_source=True),
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert summary["ack_rate"] == 1.0
    assert summary["recommendation"] == "broker_dispatch_acknowledged"
    assert report.acknowledgements["match_key"].tolist() == ["source_order_id", "source_order_id"]
    assert report.acknowledgements["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.acknowledgements["ack_route_dispatch_roundtrip_batch_ids"].tolist() == ["BDP-0", "BDP-0"]
    assert summary["broker_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(summary["broker_schema_reviewed"])
    assert summary["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["broker_readiness"]["schema_reviewed"]
    assert report.config["broker_readiness"]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert int(summary["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["route_dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 0
    assert bool(summary["route_readiness_required"])
    assert bool(summary["route_readiness_ready"])
    assert summary["route_readiness_strategy"] == "lead_lag_taker"
    assert report.config["route_readiness"]["required"]
    assert report.config["route_readiness"]["market"] == "india_nse_index_derivatives"


def test_broker_dispatch_ack_carries_send_shadow_broker_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_readiness_sessions"]) == 2
    assert int(summary["shadow_broker_readiness_ready_sessions"]) == 2
    assert summary["shadow_broker_adapter"] == "arrow_money"
    assert summary["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["shadow_broker_readiness"]["provided"]
    assert report.config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_ack_blocks_bad_send_shadow_broker_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        ready_sessions=1,
        adapter="irage",
        adapter_count=2,
        route_ready_sessions=1,
        route_strategy="surface_mm",
        route_market="us_options_regular",
        route_gap_pairs=2,
        dispatch_ready_sessions=1,
        dispatch_strategy="surface_mm",
        dispatch_market="us_options_regular",
        dispatch_scenario_count=2,
        dispatch_missing_request_acks=1,
        dispatch_rejected_orders=1,
        dispatch_unmatched_acks=1,
        route_dispatch_ready_sessions=1,
        route_dispatch_strategy="surface_mm",
        route_dispatch_market="us_options_regular",
        route_dispatch_scenario_count=2,
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "send_shadow_broker_readiness_ready",
        "send_shadow_broker_adapter_matches",
        "send_shadow_broker_adapter_consistent",
        "send_shadow_broker_route_readiness_ready",
        "send_shadow_broker_route_readiness_strategy_matches",
        "send_shadow_broker_route_readiness_market_matches",
        "send_shadow_broker_route_readiness_gap_pairs",
        "send_shadow_broker_dispatch_roundtrip_ready",
        "send_shadow_broker_dispatch_roundtrip_strategy_matches",
        "send_shadow_broker_dispatch_roundtrip_market_matches",
        "send_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "send_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "send_shadow_broker_dispatch_roundtrip_rejected_orders",
        "send_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "send_shadow_broker_route_dispatch_roundtrip_ready",
        "send_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "send_shadow_broker_route_dispatch_roundtrip_market_matches",
        "send_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_ack_carries_send_broker_shadow_broker_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert summary["route_broker_shadow_broker_readiness_provided"]
    assert int(summary["route_broker_shadow_broker_readiness_sessions"]) == 2
    assert int(summary["route_broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert summary["route_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["route_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["route_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["route_broker_shadow_broker_readiness"]["provided"]
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["route_broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["route_broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_ack_blocks_bad_send_broker_shadow_broker_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            ready_sessions=1,
            adapter="irage",
            adapter_count=2,
            route_ready_sessions=1,
            route_strategy="surface_mm",
            route_market="us_options_regular",
            route_gap_pairs=2,
            dispatch_ready_sessions=1,
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_count=2,
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
            route_dispatch_ready_sessions=1,
            route_dispatch_strategy="surface_mm",
            route_dispatch_market="us_options_regular",
            route_dispatch_scenario_count=2,
        ),
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "send_broker_shadow_broker_readiness_ready",
        "send_broker_shadow_broker_adapter_matches",
        "send_broker_shadow_broker_adapter_consistent",
        "send_broker_shadow_broker_route_readiness_ready",
        "send_broker_shadow_broker_route_readiness_strategy_matches",
        "send_broker_shadow_broker_route_readiness_market_matches",
        "send_broker_shadow_broker_route_readiness_gap_pairs",
        "send_broker_shadow_broker_dispatch_roundtrip_ready",
        "send_broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "send_broker_shadow_broker_dispatch_roundtrip_market_matches",
        "send_broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "send_broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "send_broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "send_broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "send_broker_shadow_broker_route_dispatch_roundtrip_ready",
        "send_broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "send_broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "send_broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_ack_requires_route_readiness():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(route_readiness_provided=False, route_readiness_ready=False),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_provided", "route_readiness_ready"} <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_broker_dispatch_ack_blocks_route_readiness_identity_mismatch():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_strategy_matches", "route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "us_options_regular"


def test_broker_dispatch_ack_requires_route_roundtrip_proof():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_ack_blocks_bad_route_roundtrip_quality():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            route_roundtrip_ready=False,
            route_roundtrip_target_mode="shadow",
            route_roundtrip_strategy="surface_mm",
            route_roundtrip_market="us_options_regular",
            route_roundtrip_scenario_key="wrong-scenario",
            route_roundtrip_missing_request_acks=1,
            route_roundtrip_rejected_orders=1,
            route_roundtrip_unmatched_acks=1,
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_target_mode_matches",
        "route_dispatch_roundtrip_strategy_matches",
        "route_dispatch_roundtrip_market_matches",
        "route_dispatch_roundtrip_scenario_matches",
        "route_dispatch_roundtrip_missing_request_acks",
        "route_dispatch_roundtrip_rejected_orders",
        "route_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert report.config["route_dispatch_roundtrip"]["missing_request_acks"] == 1


def test_broker_dispatch_ack_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.summary.iloc[0]["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1
    assert report.config["broker_readiness"]["schema_reviewed"]


def test_broker_dispatch_ack_reads_nested_route_enable_dispatch_roundtrip_failed_checks(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(dispatch_config(route_enable_dispatch_roundtrip_failed_checks=1), indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_broker_dispatch_acknowledgements(
        dispatch_dir=dispatch,
        acks_path=acks,
        output_dir=tmp_path / "dispatch_acks",
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_ack_blocks_route_roundtrip_batch_mismatch():
    orders = dispatch_orders()
    orders.loc[0, "route_dispatch_roundtrip_batch_id"] = "BDP-OLD"

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=orders,
        broker_acks=ack_rows(route_roundtrip_batch_id="BDP-BAD"),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_order_route_roundtrip_batch_matches",
        "ack_route_roundtrip_batch_matches",
    } <= failed
    assert report.acknowledgements["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-BAD", "BDP-BAD"]
    assert report.acknowledgements["ack_route_dispatch_roundtrip_batch_ids"].tolist() == ["BDP-BAD", "BDP-BAD"]


def test_broker_dispatch_ack_blocks_missing_ack():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(("accepted",)),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "all_dispatch_orders_acked" in failed
    assert int(report.summary.iloc[0]["missing_acks"]) == 1


def test_broker_dispatch_ack_blocks_rejected_duplicate_and_unmatched_acks():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(("accepted", "rejected"), duplicate=True, extra=True),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed >= {
        "all_dispatch_orders_acked",
        "rejected_orders",
        "duplicate_ack_orders",
        "unmatched_acks",
    }
    summary = report.summary.iloc[0]
    assert int(summary["rejected_orders"]) == 1
    assert int(summary["duplicate_ack_orders"]) == 1
    assert int(summary["unmatched_acks"]) == 1


def test_write_broker_dispatch_ack_outputs_artifacts_and_catalog_entry(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
    out_dir = tmp_path / "dispatch_acks"

    report = write_broker_dispatch_acknowledgements(
        dispatch_dir=dispatch,
        acks_path=acks,
        output_dir=out_dir,
    )

    assert report.passed
    assert (out_dir / "broker_dispatch_acknowledgements.csv").exists()
    assert (out_dir / "broker_dispatch_unmatched_acks.csv").exists()
    assert (out_dir / "broker_dispatch_ack_checks.csv").exists()
    assert (out_dir / "broker_dispatch_ack_summary.csv").exists()
    assert (out_dir / "broker_dispatch_ack_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(manifest["inputs"]["dispatch_summary"]["path"]).endswith(
        "/broker_dispatch_summary.csv"
    )
    assert path_tail(manifest["inputs"]["dispatch_orders"]["path"]).endswith(
        "/broker_dispatch_orders.csv"
    )
    assert path_tail(manifest["inputs"]["dispatch_config"]["path"]).endswith(
        "/broker_dispatch_config.json"
    )
    assert path_tail(manifest["inputs"]["broker_acks"]["path"]).endswith("/broker_dispatch_acks.csv")
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_ack_reconciliation"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_ack_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_ack_fails_on_rejected_ack(tmp_path):
    dispatch, acks = write_inputs(tmp_path, ack_statuses=("accepted", "rejected"))
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "rejected_orders" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_broker_dispatch_ack_can_require_roundtrip_proof(tmp_path):
    dispatch, acks = write_inputs(tmp_path, route_roundtrip=False)
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "route_dispatch_roundtrip_provided" in failed


def test_cli_broker_dispatch_ack_can_require_route_readiness(tmp_path):
    dispatch, acks = write_inputs(tmp_path, route_readiness=False)
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "route_readiness_provided" in failed
