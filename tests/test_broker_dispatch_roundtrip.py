import pandas as pd

from hft_cli import main
from reports.broker_dispatch_roundtrip import (
    evaluate_broker_dispatch_roundtrip,
    write_broker_dispatch_roundtrip,
)
from reports.catalog import catalog_experiment_runs


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
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "dispatch_state": "armed_dry_run" if ready else "disabled",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dispatch_orders": 2,
                "dispatch_batch_id": "BDP-1",
                "dry_run_only": True,
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
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def dispatch_orders(route_roundtrip_batch_id="BDP-0"):
    return pd.DataFrame(
        [
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
        ]
    )


def send_summary(
    ready=True,
    strategy="lead_lag_taker",
    submission_enabled=False,
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
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "request_state": "dry_run_send_packet_ready" if ready else "disabled",
                "target_mode": "live_dryrun",
                "strategy": strategy,
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dispatch_batch_id": "BDP-1",
                "dispatch_orders": 2,
                "requests": 2,
                "dry_run_only": True,
                "submission_enabled": submission_enabled,
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
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def send_requests(submission_enabled=False, route_roundtrip_batch_id="BDP-0"):
    return pd.DataFrame(
        [
            {
                "request_id": "BDR-1",
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "submission_enabled": submission_enabled,
                "dry_run_only": True,
                "idempotency_key": "IDEMP-1",
                "request_payload_hash": "REQ-1",
                "payload_valid": True,
            },
            {
                "request_id": "BDR-2",
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "submission_enabled": False,
                "dry_run_only": True,
                "idempotency_key": "IDEMP-2",
                "request_payload_hash": "REQ-2",
                "payload_valid": True,
            },
        ]
    )


def ack_summary(
    passed=True,
    strategy="lead_lag_taker",
    acked_orders=2,
    missing=0,
    rejected=0,
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
):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "target_mode": "live_dryrun",
                "strategy": strategy,
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dispatch_orders": 2,
                "acked_orders": acked_orders,
                "missing_acks": missing,
                "rejected_orders": rejected,
                "duplicate_ack_orders": 0,
                "unmatched_acks": 0,
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
                "ack_rate": acked_orders / 2,
                "failed_checks": 0 if passed else 1,
            }
        ]
    )


def acknowledgements(
    missing_second=False,
    rejected_second=False,
    route_roundtrip_batch_id="BDP-0",
    ack_route_roundtrip_batch_ids=None,
):
    raw_route_batch_ids = (
        route_roundtrip_batch_id
        if ack_route_roundtrip_batch_ids is None
        else ack_route_roundtrip_batch_ids
    )
    return pd.DataFrame(
        [
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "dispatch_order_route_roundtrip_batch_id": route_roundtrip_batch_id,
                "ack_route_dispatch_roundtrip_batch_ids": raw_route_batch_ids,
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "ack_count": 1,
                "ack_status": "accepted",
                "broker_order_id": "BRK-1",
                "acked": True,
                "rejected": False,
                "duplicate_ack": False,
                "missing_ack": False,
            },
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "dispatch_order_route_roundtrip_batch_id": route_roundtrip_batch_id,
                "ack_route_dispatch_roundtrip_batch_ids": raw_route_batch_ids,
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "ack_count": 0 if missing_second else 1,
                "ack_status": "rejected" if rejected_second else ("" if missing_second else "accepted"),
                "broker_order_id": "" if missing_second else "BRK-2",
                "acked": not missing_second and not rejected_second,
                "rejected": rejected_second,
                "duplicate_ack": False,
                "missing_ack": missing_second,
            },
        ]
    )


def write_inputs(tmp_path, *, missing_ack=False):
    dispatch = tmp_path / "dispatch"
    send = tmp_path / "send"
    ack = tmp_path / "ack"
    dispatch.mkdir()
    send.mkdir()
    ack.mkdir()
    dispatch_summary().to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    dispatch_orders().to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
    send_summary().to_csv(send / "broker_dispatch_send_summary.csv", index=False)
    send_requests().to_csv(send / "broker_dispatch_send_requests.csv", index=False)
    ack_summary(passed=not missing_ack, acked_orders=1 if missing_ack else 2, missing=1 if missing_ack else 0).to_csv(
        ack / "broker_dispatch_ack_summary.csv",
        index=False,
    )
    acknowledgements(missing_second=missing_ack).to_csv(ack / "broker_dispatch_acknowledgements.csv", index=False)
    return dispatch, send, ack


def test_broker_dispatch_roundtrip_passes_complete_dry_run_evidence():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
    )

    assert report.passed
    assert report.summary.iloc[0]["recommendation"] == "broker_dry_run_roundtrip_proved"
    assert report.orders["request_id"].tolist() == ["BDR-1", "BDR-2"]
    assert report.orders["acked"].tolist() == [True, True]
    assert report.orders["dispatch_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["request_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["ack_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["ack_raw_route_roundtrip_batch_ids"].tolist() == ["BDP-0", "BDP-0"]
    assert int(report.summary.iloc[0]["missing_request_acks"]) == 0
    assert bool(report.summary.iloc[0]["route_dispatch_roundtrip_ready"])
    assert report.config["route_dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-0"


def test_broker_dispatch_roundtrip_requires_route_roundtrip_proof():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        dispatch_orders=dispatch_orders(route_roundtrip_batch_id=""),
        send_summary=send_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        send_requests=send_requests(route_roundtrip_batch_id=""),
        ack_summary=ack_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        acknowledgements=acknowledgements(route_roundtrip_batch_id=""),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_roundtrip_blocks_dirty_route_roundtrip_chain():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(route_roundtrip_batch_id="BDP-X"),
        send_requests=send_requests(route_roundtrip_batch_id="BDP-X"),
        ack_summary=ack_summary(
            route_roundtrip_ready=False,
            route_roundtrip_target_mode="shadow",
            route_roundtrip_batch_id="BDP-0",
            route_roundtrip_acked_orders=1,
            route_roundtrip_missing_request_acks=1,
            route_roundtrip_rejected_orders=1,
            route_roundtrip_unmatched_acks=1,
        ),
        acknowledgements=acknowledgements(route_roundtrip_batch_id="BDP-0"),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_identity_match",
        "route_dispatch_roundtrip_batch_consistent",
        "route_dispatch_roundtrip_request_counts_match",
        "route_dispatch_roundtrip_missing_request_acks",
        "route_dispatch_roundtrip_rejected_orders",
        "route_dispatch_roundtrip_unmatched_acks",
    } <= failed


def test_broker_dispatch_roundtrip_blocks_raw_ack_route_batch_mismatch():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(ack_route_roundtrip_batch_ids="BDP-OLD"),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_dispatch_roundtrip_batch_consistent" in failed
    assert report.orders["ack_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["ack_raw_route_roundtrip_batch_ids"].tolist() == ["BDP-OLD", "BDP-OLD"]


def test_broker_dispatch_roundtrip_blocks_identity_submission_and_missing_acks():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(ready=False),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(strategy="parity", submission_enabled=True),
        send_requests=send_requests(submission_enabled=True),
        ack_summary=ack_summary(passed=False, strategy="parity", acked_orders=1, missing=1, rejected=1),
        acknowledgements=acknowledgements(missing_second=True, rejected_second=True),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed >= {
        "dispatch_ready",
        "ack_passed",
        "identity_match",
        "submission_disabled",
        "all_requests_acked",
        "missing_request_acks",
        "rejected_orders",
        "component_failed_checks",
    }
    assert report.summary.iloc[0]["recommendation"] == "investigate_broker_dry_run_roundtrip"


def test_write_broker_dispatch_roundtrip_outputs_artifacts_and_catalog_entry(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path)
    out_dir = tmp_path / "roundtrip"

    report = write_broker_dispatch_roundtrip(
        dispatch_dir=dispatch,
        send_dir=send,
        ack_dir=ack,
        output_dir=out_dir,
    )

    assert report.passed
    assert (out_dir / "broker_dispatch_roundtrip_orders.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_checks.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_summary.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_roundtrip"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_roundtrip_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_roundtrip_fails_on_missing_ack(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path, missing_ack=True)
    out_dir = tmp_path / "roundtrip"

    code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_roundtrip_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "missing_request_acks" in set(checks.loc[~checks["passed"].astype(bool), "check"])
