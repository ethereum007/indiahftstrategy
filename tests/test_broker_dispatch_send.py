import json

import pandas as pd

from hft_cli import main
from reports.broker_dispatch_send import (
    evaluate_broker_dispatch_send_packet,
    write_broker_dispatch_send_packet,
)
from reports.catalog import catalog_experiment_runs


def dispatch_summary(
    ready=True,
    state="armed_dry_run",
    target_mode="live_dryrun",
    adapter="arrow_money",
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
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "dispatch_state": state,
                "target_mode": target_mode,
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": adapter,
                "dispatch_orders": 2,
                "dispatch_batch_id": "BDP-1",
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
                "dry_run_only": True,
                "failed_checks": 0 if ready else 1,
                "recommendation": "ready_for_broker_dryrun_dispatch"
                if ready
                else "keep_dispatch_disabled",
            }
        ]
    )


def dispatch_orders(*, dry_run=True, malformed_payload=False, route_roundtrip_batch_id="BDP-0"):
    payloads = [
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY24JUN22500CE",
            "transaction_type": "BUY",
            "quantity": 75,
            "order_type": "LIMIT",
            "product": "MIS",
            "price": 10.0,
            "validity": "DAY",
            "client_order_id": "ORD-1",
            "tag": "shadow_nse",
        },
        {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY24JUN22500PE",
            "transaction_type": "SELL",
            "quantity": 75,
            "order_type": "LIMIT",
            "product": "MIS",
            "price": 11.0,
            "validity": "DAY",
            "client_order_id": "ORD-2",
            "tag": "shadow_nse",
        },
    ]
    rows = []
    for index, payload in enumerate(payloads, start=1):
        payload_json = json.dumps(payload, sort_keys=True)
        if malformed_payload and index == 2:
            payload_json = "{bad-json"
        rows.append(
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_sequence": index,
                "dispatch_order_id": f"DSP-{index}",
                "dispatch_action": "dry_run_submit",
                "dry_run_only": dry_run if index == 1 else True,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "source_order_id": f"ORD-{index}",
                "source_payload_hash": f"hash-{index}",
                "upload_file_hash": "upload-hash",
                "route_enable_hash": "route-hash",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "order_payload_json": payload_json,
            }
        )
    return pd.DataFrame(rows)


def dispatch_config(route_enable_dispatch_roundtrip_failed_checks=0):
    return {
        "route_enable_dispatch_roundtrip": {
            "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
        }
    }


def write_dispatch(tmp_path, *, ready=True, state="armed_dry_run", route_roundtrip=True):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    dispatch_summary(
        ready=ready,
        state=state,
        route_roundtrip_provided=route_roundtrip,
        route_roundtrip_ready=route_roundtrip,
    ).to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    dispatch_orders().to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(dispatch_config(), indent=2) + "\n",
        encoding="utf-8",
    )
    return dispatch


def test_broker_dispatch_send_packet_prepares_non_submitting_requests():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
    )

    assert report.ready
    assert report.summary.iloc[0]["request_state"] == "dry_run_send_packet_ready"
    assert report.summary.iloc[0]["recommendation"] == "ready_for_non_submitting_broker_sender_review"
    assert report.requests["endpoint"].tolist() == [
        "arrow_money.orders.dry_run_submit",
        "arrow_money.orders.dry_run_submit",
    ]
    assert report.requests["submission_enabled"].tolist() == [False, False]
    assert report.requests["idempotency_key"].nunique() == 2
    request_payload = json.loads(report.requests.iloc[0]["request_payload_json"])
    assert request_payload["submission_enabled"] is False
    assert request_payload["dry_run_only"] is True
    assert request_payload["route_dispatch_roundtrip_batch_id"] == "BDP-0"
    assert request_payload["order"]["client_order_id"] == "ORD-1"
    assert report.requests["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.expected_acks["dispatch_order_id"].tolist() == ["DSP-1", "DSP-2"]
    assert report.expected_acks["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["route_dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 0


def test_broker_dispatch_send_requires_route_roundtrip_proof():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        dispatch_orders=dispatch_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_send_blocks_bad_route_roundtrip_quality():
    report = evaluate_broker_dispatch_send_packet(
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
    )

    assert not report.ready
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


def test_broker_dispatch_send_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        dispatch_orders=dispatch_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_send_reads_nested_route_enable_dispatch_roundtrip_failed_checks(tmp_path):
    dispatch = write_dispatch(tmp_path)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(dispatch_config(route_enable_dispatch_roundtrip_failed_checks=1), indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=tmp_path / "dispatch_send",
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_send_blocks_route_roundtrip_batch_mismatch():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_roundtrip_batch_id="BDP-0"),
        dispatch_orders=dispatch_orders(route_roundtrip_batch_id="BDP-OLD"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"dispatch_order_route_roundtrip_batch_matches", "request_route_roundtrip_batch_matches"} <= failed
    assert report.summary.iloc[0]["route_dispatch_roundtrip_batch_id"] == "BDP-0"
    assert report.requests["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-OLD", "BDP-OLD"]


def test_broker_dispatch_send_packet_blocks_unready_non_dry_run_and_bad_payloads():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(ready=False, state="disabled"),
        dispatch_orders=dispatch_orders(dry_run=False, malformed_payload=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed >= {"dispatch_ready", "dispatch_armed_dry_run", "dry_run_only", "payloads_valid"}
    assert report.summary.iloc[0]["recommendation"] == "keep_broker_sender_disabled"


def test_write_broker_dispatch_send_packet_outputs_artifacts_and_catalog_entry(tmp_path):
    dispatch = write_dispatch(tmp_path)
    out_dir = tmp_path / "dispatch_send"

    report = write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=out_dir)

    assert report.ready
    assert (out_dir / "broker_dispatch_send_requests.csv").exists()
    assert (out_dir / "broker_dispatch_expected_acks.csv").exists()
    assert (out_dir / "broker_dispatch_send_checks.csv").exists()
    assert (out_dir / "broker_dispatch_send_summary.csv").exists()
    assert (out_dir / "broker_dispatch_send_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_send_packet"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_send_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_send_fails_when_request_limit_breached(tmp_path):
    dispatch = write_dispatch(tmp_path)
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--max-requests",
            "1",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "request_count_within_limit" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_broker_dispatch_send_can_require_roundtrip_proof(tmp_path):
    dispatch = write_dispatch(tmp_path, route_roundtrip=False)
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_dispatch_roundtrip_provided" in failed
