import json

import pandas as pd

from hft_cli import main
from reports.halt_response import evaluate_halt_response, write_halt_response_plan


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
    assert report.cancel_orders.iloc[0]["guard_failed_check_names"] == "orders_sent"
    assert report.cancel_orders.iloc[0]["guard_first_failed_reason"].startswith("orders_sent:")
    assert report.flatten_orders["side_text"].tolist() == ["SELL", "BUY"]
    assert report.flatten_orders["strategy"].tolist() == ["lead_lag_taker", "lead_lag_taker"]
    assert report.flatten_orders["market"].tolist() == ["india_nse_index_derivatives", "india_nse_index_derivatives"]
    assert report.flatten_orders["proof_refresh_market"].tolist() == [
        "india_nse_index_derivatives",
        "india_nse_index_derivatives",
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
    assert report.summary.iloc[0]["guard_failed_check_names"] == "orders_sent"
    assert report.summary.iloc[0]["guard_first_failed_reason"].startswith("orders_sent:")
    assert report.config["guard_failed_checks"] == ["orders_sent"]
    assert report.config["strategy"] == "lead_lag_taker"
    assert report.config["market"] == "india_nse_index_derivatives"
    assert report.config["proof_freshness"] == {
        "required": True,
        "provided": True,
        "ready": True,
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "mixed_identity": False,
        "proof_source": "latest",
    }


def test_halt_response_fails_when_guard_not_halted_by_default():
    report = evaluate_halt_response(guard_summary("continue"))

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed == {"guard_halted"}


def test_write_halt_response_plan_outputs_artifacts(tmp_path):
    guard_dir = tmp_path / "guard"
    out_dir = tmp_path / "response"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    guard_dir.mkdir()
    guard_summary().to_csv(guard_dir / "runtime_guard_summary.csv", index=False)
    guard_checks().to_csv(guard_dir / "runtime_guard_checks.csv", index=False)
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
    assert (out_dir / "halt_response_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    saved_config = json.loads((out_dir / "halt_response_config.json").read_text(encoding="utf-8"))
    assert saved_config["guard_failed_checks"] == ["orders_sent"]
    assert saved_config["proof_freshness"]["strategy"] == "lead_lag_taker"
    assert saved_config["proof_freshness"]["ready"]
    saved_summary = pd.read_csv(out_dir / "halt_response_summary.csv")
    assert saved_summary.loc[0, "guard_failed_check_names"] == "orders_sent"
    assert saved_summary.loc[0, "proof_refresh_strategy"] == "lead_lag_taker"
    assert bool(saved_summary.loc[0, "proof_refresh_ready"])
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {"guard_summary", "guard_checks", "open_orders", "positions"} <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["guard_summary"]["path"]).endswith(
        "/guard/runtime_guard_summary.csv"
    )
    assert path_tail(manifest["inputs"]["guard_checks"]["path"]).endswith(
        "/guard/runtime_guard_checks.csv"
    )
    assert path_tail(manifest["inputs"]["open_orders"]["path"]).endswith("/open_orders.csv")
    assert path_tail(manifest["inputs"]["positions"]["path"]).endswith("/positions.csv")


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
        ]
    )

    summary = pd.read_csv(out_dir / "halt_response_summary.csv")
    assert code == 2
    assert int(summary.loc[0, "failed_checks"]) == 1
