import json

import pandas as pd

from hft_cli import main
from reports.runtime_guard import evaluate_runtime_guard, write_runtime_guard_report


def scaleup_config(require_proof_refresh=False, require_broker_resume_gate=False, **overrides):
    config = {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "identity": {
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "expected_strategy": "lead_lag_taker",
            "expected_market": "india_nse_index_derivatives",
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "max_scale_multiplier": 1.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": {
            "max_total_failed_component_checks": 0,
            "max_total_unmatched_fills": 0,
            "max_total_mismatched_orders": 0,
            "max_total_overfilled_orders": 0,
            "max_worst_adverse_slippage": 0.05,
        },
    }
    if require_proof_refresh:
        config["proof_freshness"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "mixed_identity": False,
            "proof_source": "latest",
            "fresh_proof_required": True,
        }
    if require_broker_resume_gate:
        config["broker_readiness"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "resume_gate": {
                "required": True,
                "provided": True,
                "ready": True,
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "incident_strategy": "lead_lag_taker",
                "incident_market": "india_nse_index_derivatives",
                "proof_refresh_ready": True,
                "proof_refresh_strategy": "lead_lag_taker",
                "proof_refresh_market": "india_nse_index_derivatives",
            },
        }
    config.update(overrides)
    return config


def instrument_metadata_config():
    return {
        "required": True,
        "provided": True,
        "passed": True,
        "parse_coverage": 1.0,
        "min_parse_coverage": 1.0,
        "unparsed_instruments": 0,
    }


def telemetry(**overrides):
    row = {
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "orders_sent": 4,
        "session_notional": 40_000.0,
        "realized_pnl": -500.0,
        "total_failed_component_checks": 0,
        "unmatched_fills": 0,
        "mismatched_orders": 0,
        "overfilled_orders": 0,
        "worst_adverse_slippage": 0.02,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_runtime_guard_continues_when_telemetry_is_inside_limits():
    report = evaluate_runtime_guard(scaleup_config(), telemetry())

    assert not report.halted
    assert report.summary.iloc[0]["guard_action"] == "continue"
    assert report.summary.iloc[0]["target_mode"] == "shadow"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert set(report.checks["passed"]) == {True}
    assert report.metrics.iloc[0]["max_orders_per_session"] == 10


def test_runtime_guard_halts_on_strategy_or_market_mismatch():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(strategy="imbalance", market="us_equities_regular"),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"strategy_match", "market_match"} <= failed
    summary = report.summary.iloc[0]
    assert summary["strategy"] == "imbalance"
    assert summary["market"] == "us_equities_regular"


def test_runtime_guard_halts_on_limit_and_kill_switch_breaches():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(
            orders_sent=11,
            realized_pnl=-5_500.0,
            unmatched_fills=1,
            worst_adverse_slippage=0.08,
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"orders_sent", "realized_pnl", "unmatched_fills", "worst_adverse_slippage"} <= failed
    summary = report.summary.iloc[0]
    assert "orders_sent" in summary["failed_check_names"].split(";")
    assert summary["first_failed_reason"].startswith("orders_sent:")
    assert "worst_adverse_slippage:" in summary["failed_check_reasons"]


def test_runtime_guard_halts_on_manual_halt_flag():
    report = evaluate_runtime_guard(scaleup_config(manual_halt=True), telemetry())

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "manual_halt" in failed


def test_runtime_guard_continues_when_telemetry_is_fresh():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(snapshot_ts_ns=1_000),
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    assert not report.halted
    row = report.metrics.iloc[0]
    assert row["runtime_telemetry_age_ns"] == 500.0
    assert row["max_telemetry_age_ns"] == 1_000.0


def test_runtime_guard_halts_when_telemetry_is_stale():
    report = evaluate_runtime_guard(
        scaleup_config(),
        telemetry(snapshot_ts_ns=1_000),
        as_of_ts_ns=2_500,
        max_telemetry_age_ns=1_000,
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_telemetry_age_ns" in failed


def test_runtime_guard_halts_on_open_order_and_position_breaches():
    config = scaleup_config()
    config["kill_switches"].update(
        {
            "max_open_order_count": 1,
            "max_open_order_qty": 50,
            "max_open_order_notional": 400,
            "max_open_order_age_ns": 500,
            "max_gross_position_qty": 100,
            "max_abs_net_position_qty": 25,
            "max_gross_notional": 1_000,
            "max_abs_net_delta": 40,
            "max_abs_net_vega": 600,
        }
    )

    report = evaluate_runtime_guard(
        config,
        telemetry(
            open_order_count=2,
            open_order_qty=75,
            open_order_notional=500,
            oldest_open_order_age_ns=1_000,
            gross_position_qty=150,
            abs_net_position_qty=50,
            gross_position_notional=1_250,
            abs_net_delta=50,
            abs_net_vega=700,
        ),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "open_order_count",
        "open_order_qty",
        "open_order_notional",
        "oldest_open_order_age_ns",
        "gross_position_qty",
        "abs_net_position_qty",
        "gross_position_notional",
        "abs_net_delta",
        "abs_net_vega",
    } <= failed


def test_runtime_guard_halts_on_lifecycle_and_replace_breaches():
    config = scaleup_config()
    config["kill_switches"].update({"max_lifecycle_orders": 2, "max_replace_orders": 0})

    report = evaluate_runtime_guard(config, telemetry(lifecycle_orders=3, replace_orders=1))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"lifecycle_orders", "replace_orders"} <= failed


def test_runtime_guard_continues_within_open_order_and_position_limits():
    config = scaleup_config()
    config["kill_switches"].update(
        {
            "max_open_order_count": 2,
            "max_open_order_qty": 100,
            "max_open_order_notional": 1_000,
            "max_open_order_age_ns": 2_000,
            "max_gross_position_qty": 200,
            "max_abs_net_position_qty": 75,
            "max_gross_notional": 2_000,
            "max_abs_net_delta": 75,
            "max_abs_net_vega": 800,
        }
    )

    report = evaluate_runtime_guard(
        config,
        telemetry(
            open_order_count=1,
            open_order_qty=50,
            open_order_notional=500,
            oldest_open_order_age_ns=1_000,
            gross_position_qty=100,
            abs_net_position_qty=25,
            gross_position_notional=1_250,
            abs_net_delta=50,
            abs_net_vega=700,
        ),
    )

    assert not report.halted
    assert set(report.checks["passed"]) == {True}


def test_runtime_guard_uses_legacy_limits_for_delta_and_vega():
    config = scaleup_config()
    config["limits"].update({"max_abs_net_delta": 40, "max_abs_net_vega": 600})

    report = evaluate_runtime_guard(config, telemetry(abs_net_delta=50, abs_net_vega=700))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"abs_net_delta", "abs_net_vega"} <= failed


def test_runtime_guard_uses_legacy_limit_for_gross_notional():
    config = scaleup_config()
    config["limits"]["max_gross_notional"] = 1_000

    report = evaluate_runtime_guard(config, telemetry(gross_position_notional=1_250))

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "gross_position_notional" in failed


def test_runtime_guard_uses_scaleup_config_telemetry_age_limit():
    config = scaleup_config()
    config["kill_switches"]["max_telemetry_age_ns"] = 1_000

    report = evaluate_runtime_guard(
        config,
        telemetry(snapshot_ts_ns=1_000),
        as_of_ts_ns=2_500,
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_telemetry_age_ns" in failed
    assert report.metrics.iloc[0]["max_telemetry_age_ns"] == 1_000.0


def test_runtime_guard_halts_when_required_instrument_metadata_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(instrument_metadata=instrument_metadata_config()),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_instrument_metadata_provided" in failed


def test_runtime_guard_continues_when_required_instrument_metadata_is_present():
    report = evaluate_runtime_guard(
        scaleup_config(instrument_metadata=instrument_metadata_config()),
        telemetry(
            instrument_metadata_provided=True,
            instrument_metadata_passed=True,
            instrument_parse_coverage=1.0,
            min_instrument_parse_coverage=1.0,
            unparsed_instruments=0,
        ),
    )

    assert not report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed == set()


def test_runtime_guard_halts_when_required_proof_refresh_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(require_proof_refresh=True),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_proof_refresh_provided",
        "runtime_proof_refresh_ready",
        "runtime_proof_refresh_strategy_matches",
        "runtime_proof_refresh_market_matches",
    } <= failed


def test_runtime_guard_continues_with_required_proof_refresh_evidence():
    report = evaluate_runtime_guard(
        scaleup_config(require_proof_refresh=True),
        telemetry(
            proof_refresh_provided=True,
            proof_refresh_ready=True,
            proof_refresh_strategy="leadlag",
            proof_refresh_market="india_nse_index_derivatives",
            proof_refresh_mixed_identity=False,
        ),
    )

    assert not report.halted
    assert set(report.checks.loc[~report.checks["passed"].astype(bool), "check"]) == set()
    assert bool(report.summary.iloc[0]["proof_refresh_ready"])


def test_runtime_guard_halts_when_required_broker_resume_gate_is_missing_from_telemetry():
    report = evaluate_runtime_guard(
        scaleup_config(require_broker_resume_gate=True),
        telemetry(),
    )

    assert report.halted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_broker_resume_gate_provided",
        "runtime_broker_resume_gate_ready",
        "runtime_broker_resume_strategy_matches",
        "runtime_broker_resume_market_matches",
        "runtime_broker_resume_proof_refresh_ready",
        "runtime_broker_resume_proof_refresh_strategy_matches",
        "runtime_broker_resume_proof_refresh_market_matches",
    } <= failed


def test_runtime_guard_continues_with_required_broker_resume_gate_evidence():
    report = evaluate_runtime_guard(
        scaleup_config(require_broker_resume_gate=True),
        telemetry(
            broker_resume_gate_provided=True,
            broker_resume_gate_ready=True,
            broker_resume_strategy="leadlag",
            broker_resume_market="india_nse_index_derivatives",
            broker_resume_proof_refresh_ready=True,
            broker_resume_proof_refresh_strategy="lead_lag_taker",
            broker_resume_proof_refresh_market="india_nse_index_derivatives",
        ),
    )

    assert not report.halted
    assert set(report.checks.loc[~report.checks["passed"].astype(bool), "check"]) == set()
    summary = report.summary.iloc[0]
    assert bool(summary["broker_resume_gate_ready"])
    assert summary["broker_resume_strategy"] == "lead_lag_taker"
    assert summary["broker_resume_proof_refresh_market"] == "india_nse_index_derivatives"


def test_write_runtime_guard_outputs_artifacts(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    telemetry().to_csv(telemetry_path, index=False)

    report = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry_path,
        output_dir=out_dir,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "runtime_guard_metrics.csv").exists()
    assert (out_dir / "runtime_guard_checks.csv").exists()
    assert (out_dir / "runtime_guard_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_runtime_guard_can_fail_on_halt(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    telemetry(orders_sent=12).to_csv(telemetry_path, index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_path),
            "--out",
            str(out_dir),
            "--fail-on-halt",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_guard_summary.csv")
    assert code == 2
    assert summary.loc[0, "guard_action"] == "halt"


def test_cli_runtime_guard_reads_runtime_telemetry_output_dir(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    telemetry_dir = tmp_path / "telemetry"
    out_dir = tmp_path / "guard"
    scaleup_dir.mkdir()
    telemetry_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    telemetry().to_csv(telemetry_dir / "runtime_telemetry.csv", index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_dir),
            "--out",
            str(out_dir),
            "--fail-on-halt",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_guard_summary.csv")
    assert code == 0
    assert summary.loc[0, "guard_action"] == "continue"


def test_cli_runtime_guard_can_fail_on_stale_telemetry(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "guard"
    telemetry_path = tmp_path / "telemetry.csv"
    scaleup_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    telemetry(snapshot_ts_ns=1_000).to_csv(telemetry_path, index=False)

    code = main(
        [
            "monitor-scaleup-guard",
            "--scaleup",
            str(scaleup_dir),
            "--telemetry",
            str(telemetry_path),
            "--out",
            str(out_dir),
            "--as-of-ts-ns",
            "3000",
            "--max-telemetry-age-ns",
            "1000",
            "--fail-on-halt",
        ]
    )

    checks = pd.read_csv(out_dir / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_telemetry_age_ns" in failed
