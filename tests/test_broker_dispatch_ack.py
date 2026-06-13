import pandas as pd

from hft_cli import main
from reports.broker_dispatch_ack import (
    evaluate_broker_dispatch_acknowledgements,
    write_broker_dispatch_acknowledgements,
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
    route_enable_dispatch_roundtrip_failed_checks=0,
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dispatch_orders": 2,
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


def write_inputs(
    tmp_path,
    *,
    dispatch_ready=True,
    ack_statuses=("accepted", "accepted"),
    route_roundtrip=True,
):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    dispatch_summary(
        dispatch_ready,
        route_roundtrip_provided=route_roundtrip,
        route_roundtrip_ready=route_roundtrip,
    ).to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    dispatch_orders().to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
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
    assert int(summary["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["route_dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 0


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
