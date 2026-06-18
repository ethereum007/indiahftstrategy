import json

import pandas as pd

from hft_cli import main
from reports.runtime_telemetry import evaluate_runtime_telemetry, write_runtime_telemetry_snapshot


def scaleup_config(
    scenario_key="trigger_ticks=2",
    adapter="arrow_money",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    require_instrument_metadata=False,
    require_proof_refresh=False,
    require_broker_resume_gate=False,
    require_strategy_portfolio=False,
):
    config = {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "strategy": strategy,
        "market": market,
        "scenario_key": scenario_key,
        "adapter": adapter,
        "identity": {
            "strategy": strategy,
            "market": market,
            "expected_strategy": strategy,
            "expected_market": market,
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
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
    if require_instrument_metadata:
        config["instrument_metadata"] = {
            "required": True,
            "provided": True,
            "passed": True,
            "parse_coverage": 1.0,
            "min_parse_coverage": 1.0,
            "unparsed_instruments": 0,
        }
    if require_proof_refresh:
        config["proof_freshness"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": strategy,
            "market": market,
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
                "strategy": strategy,
                "market": market,
                "incident_strategy": strategy,
                "incident_market": market,
                "proof_refresh_ready": True,
                "proof_refresh_strategy": strategy,
                "proof_refresh_market": market,
            },
        }
    if require_strategy_portfolio:
        config["strategy_portfolio"] = {
            "required": True,
            "provided": True,
            "ready": True,
            "deployment_mode": "paper_shadow",
            "allocation_mode": "readiness_weighted",
            "capital_currency": "INR",
            "selected_profile": "leadlag",
            "selected_strategy": strategy,
            "selected_market": market,
            "selected_eligible": True,
            "selected_allocation_weight": 0.0012,
            "selected_allocation_notional": 1200.0,
            "notional_cap_applied": True,
        }
        config["limits"]["pre_portfolio_max_notional_per_session"] = 3000.0
    return config


def export_summary():
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": "arrow_money",
                "scenario_key": "trigger_ticks=2",
                "orders": 4,
                "total_notional": 40_000.0,
                "failed_checks": 1,
            }
        ]
    )


def upload_summary(ready=True, failed_checks=0):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": "arrow_money",
                "orders": 4,
                "lifecycle_orders": 3,
                "replace_orders": 1,
                "failed_checks": failed_checks,
            }
        ]
    )


def reconciliation_summary():
    return pd.DataFrame(
        [
            {
                "passed": False,
                "orders": 4,
                "unmatched_fills": 1,
                "mismatched_orders": 0,
                "overfilled_orders": 0,
                "max_adverse_slippage": 0.03,
            }
        ]
    )


def reconciliation_checks():
    return pd.DataFrame(
        [
            {"check": "unmatched_fills", "passed": False, "reason": "one stray fill"},
            {"check": "mismatched_orders", "passed": True, "reason": ""},
        ]
    )


def instrument_metadata_summary():
    return pd.DataFrame(
        [
            {
                "passed": True,
                "instruments": 2,
                "parsed_instruments": 2,
                "unparsed_instruments": 0,
                "parse_coverage": 1.0,
                "min_parse_coverage": 1.0,
                "symbol_formats": "nse_compact:2",
            }
        ]
    )


def pnl_snapshot():
    return pd.DataFrame(
        [
            {"ts_ns": 100, "realized_pnl": -10.0},
            {"ts_ns": 200, "realized_pnl": -125.5},
        ]
    )


def open_orders():
    return pd.DataFrame(
        [
            {
                "client_order_id": "A",
                "qty": 75,
                "filled_qty": 25,
                "status": "partial",
                "limit_price": 10.0,
                "created_ts_ns": 100,
            },
            {"client_order_id": "B", "qty": 75, "filled_qty": 75, "status": "filled", "limit_price": 11.0},
        ]
    )


def positions():
    return pd.DataFrame(
        [
            {
                "instrument_id": "NIFTY_C_22000",
                "net_qty": 75,
                "unit_delta": 0.45,
                "unit_vega": 12.0,
                "market_bid": 9.8,
                "market_ask": 10.2,
            },
            {
                "instrument_id": "NIFTY_P_22000",
                "net_qty": -25,
                "unit_delta": -0.30,
                "unit_vega": 8.0,
                "market_bid": 19.5,
                "market_ask": 20.5,
            },
        ]
    )


def path_tail(value):
    return str(value).replace("\\", "/")


def test_runtime_telemetry_combines_operational_artifacts():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        export_summary=export_summary(),
        upload_summary=upload_summary(),
        reconciliation_summary=reconciliation_summary(),
        reconciliation_checks=reconciliation_checks(),
        pnl_snapshot=pnl_snapshot(),
        open_orders=open_orders(),
        positions=positions(),
        snapshot_ts_ns=1_100,
    )

    row = report.telemetry.iloc[0]
    summary = report.summary.iloc[0]
    assert report.ready
    assert row["strategy"] == "lead_lag_taker"
    assert row["market"] == "india_nse_index_derivatives"
    assert summary["target_mode"] == "shadow"
    assert summary["strategy"] == "lead_lag_taker"
    assert summary["market"] == "india_nse_index_derivatives"
    assert row["orders_sent"] == 4
    assert row["lifecycle_orders"] == 3
    assert row["replace_orders"] == 1
    assert row["session_notional"] == 40_000.0
    assert row["realized_pnl"] == -125.5
    assert row["total_failed_component_checks"] == 2
    assert row["unmatched_fills"] == 1
    assert row["worst_adverse_slippage"] == 0.03
    assert row["open_order_count"] == 1
    assert row["gross_position_qty"] == 100.0
    assert row["open_order_notional"] == 500.0
    assert row["oldest_open_order_age_ns"] == 1_000.0
    assert row["gross_position_notional"] == 1250.0
    assert row["net_position_notional"] == 250.0
    assert row["abs_net_position_notional"] == 250.0
    assert row["net_delta"] == 41.25
    assert row["abs_net_delta"] == 41.25
    assert row["net_vega"] == 700.0
    assert row["abs_net_vega"] == 700.0
    assert bool(row["broker_upload_pack_ready"])
    assert report.summary.iloc[0]["recommendation"] == "feed_runtime_guard"


def test_runtime_telemetry_uses_total_position_greek_columns():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        positions=pd.DataFrame(
            [
                {"instrument_id": "NIFTY_C_22000", "net_delta": 15.0, "net_vega": 25.0},
                {"instrument_id": "NIFTY_P_22000", "net_delta": -5.0, "net_vega": -10.0},
            ]
        ),
    )

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["net_delta"] == 10.0
    assert row["abs_net_delta"] == 10.0
    assert row["net_vega"] == 15.0
    assert row["abs_net_vega"] == 15.0


def test_runtime_telemetry_uses_total_position_notional_columns():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        positions=pd.DataFrame(
            [
                {"instrument_id": "NIFTY_C_22000", "signed_notional": 750.0},
                {"instrument_id": "NIFTY_P_22000", "signed_notional": -500.0},
            ]
        ),
    )

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["gross_position_notional"] == 1250.0
    assert row["net_position_notional"] == 250.0
    assert row["abs_net_position_notional"] == 250.0


def test_runtime_telemetry_uses_side_aware_open_order_prices():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        open_orders=pd.DataFrame(
            [
                {
                    "client_order_id": "BUY-1",
                    "side": "BUY",
                    "open_qty": 50,
                    "status": "OPEN",
                    "market_bid": 9.8,
                    "market_ask": 10.2,
                },
                {
                    "client_order_id": "SELL-1",
                    "side": "SELL",
                    "open_qty": 25,
                    "status": "OPEN",
                    "market_bid": 19.5,
                    "market_ask": 20.5,
                },
                {
                    "client_order_id": "DONE",
                    "side": "BUY",
                    "open_qty": 100,
                    "status": "CANCELLED",
                    "market_bid": 99.0,
                    "market_ask": 100.0,
                },
            ]
        ),
    )

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["open_order_count"] == 2
    assert row["open_order_qty"] == 75.0
    assert row["open_order_notional"] == 997.5


def test_runtime_telemetry_uses_broker_supplied_open_order_age():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        open_orders=pd.DataFrame(
            [
                {"client_order_id": "A", "open_qty": 50, "status": "OPEN", "open_order_age_ns": 900},
                {"client_order_id": "B", "open_qty": 25, "status": "OPEN", "open_order_age_ns": 1_200},
                {"client_order_id": "DONE", "open_qty": 25, "status": "FILLED", "open_order_age_ns": 9_999},
            ]
        ),
    )

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["oldest_open_order_age_ns"] == 1_200.0


def test_runtime_telemetry_blocks_unready_upload_pack():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        export_summary=export_summary(),
        upload_summary=upload_summary(ready=False, failed_checks=1),
    )

    row = report.telemetry.iloc[0]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert row["total_failed_component_checks"] == 2
    assert "broker_upload_pack_ready" in failed


def test_runtime_telemetry_defaults_to_scaleup_config_without_optional_inputs():
    report = evaluate_runtime_telemetry(scaleup_config())

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["strategy"] == "lead_lag_taker"
    assert row["market"] == "india_nse_index_derivatives"
    assert row["scenario_key"] == "trigger_ticks=2"
    assert row["adapter"] == "arrow_money"
    assert row["orders_sent"] == 0
    assert row["total_failed_component_checks"] == 0


def test_runtime_telemetry_carries_required_instrument_metadata_summary():
    report = evaluate_runtime_telemetry(
        scaleup_config(require_instrument_metadata=True),
        instrument_metadata_summary=instrument_metadata_summary(),
    )

    row = report.telemetry.iloc[0]
    assert report.ready
    assert bool(row["instrument_metadata_required"])
    assert bool(row["instrument_metadata_provided"])
    assert bool(row["instrument_metadata_passed"])
    assert row["instrument_parse_coverage"] == 1.0
    assert row["unparsed_instruments"] == 0.0
    source = report.sources.loc[report.sources["source"] == "instrument_metadata_summary"].iloc[0]
    assert bool(source["provided"])


def test_runtime_telemetry_carries_required_proof_refresh_config():
    report = evaluate_runtime_telemetry(scaleup_config(require_proof_refresh=True))

    row = report.telemetry.iloc[0]
    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(row["proof_refresh_required"])
    assert bool(row["proof_refresh_provided"])
    assert bool(row["proof_refresh_ready"])
    assert row["proof_refresh_strategy"] == "lead_lag_taker"
    assert row["proof_refresh_market"] == "india_nse_index_derivatives"
    assert not bool(row["proof_refresh_mixed_identity"])
    assert summary["proof_source"] == "latest"
    assert bool(summary["proof_refresh_ready"])


def test_runtime_telemetry_carries_broker_resume_gate_config():
    report = evaluate_runtime_telemetry(scaleup_config(require_broker_resume_gate=True))

    row = report.telemetry.iloc[0]
    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(row["broker_resume_gate_required"])
    assert bool(row["broker_resume_gate_provided"])
    assert bool(row["broker_resume_gate_ready"])
    assert row["broker_resume_strategy"] == "lead_lag_taker"
    assert row["broker_resume_market"] == "india_nse_index_derivatives"
    assert bool(row["broker_resume_proof_refresh_ready"])
    assert row["broker_resume_proof_refresh_strategy"] == "lead_lag_taker"
    assert row["broker_resume_proof_refresh_market"] == "india_nse_index_derivatives"
    assert bool(summary["broker_resume_gate_ready"])
    assert summary["broker_resume_proof_refresh_strategy"] == "lead_lag_taker"


def test_runtime_telemetry_carries_strategy_portfolio_config():
    report = evaluate_runtime_telemetry(scaleup_config(require_strategy_portfolio=True))

    row = report.telemetry.iloc[0]
    summary = report.summary.iloc[0]
    assert report.ready
    assert bool(row["strategy_portfolio_required"])
    assert bool(row["strategy_portfolio_provided"])
    assert bool(row["strategy_portfolio_ready"])
    assert row["strategy_portfolio_selected_profile"] == "leadlag"
    assert row["strategy_portfolio_selected_strategy"] == "lead_lag_taker"
    assert row["strategy_portfolio_selected_market"] == "india_nse_index_derivatives"
    assert bool(row["strategy_portfolio_selected_eligible"])
    assert row["strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert bool(row["strategy_portfolio_notional_cap_applied"])
    assert row["pre_portfolio_max_notional_per_session"] == 3000.0
    assert bool(summary["strategy_portfolio_ready"])
    assert summary["strategy_portfolio_selected_allocation_notional"] == 1200.0


def test_runtime_telemetry_blocks_bad_strategy_portfolio_config():
    config = scaleup_config(require_strategy_portfolio=True)
    config["strategy_portfolio"].update(
        {
            "ready": False,
            "selected_strategy": "surface_mm",
            "selected_market": "us_options_regular",
            "selected_eligible": False,
            "selected_allocation_notional": 0.0,
        }
    )

    report = evaluate_runtime_telemetry(config)

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "strategy_portfolio_ready",
        "strategy_portfolio_allocation_eligible",
        "strategy_portfolio_strategy_matches",
        "strategy_portfolio_market_matches",
        "strategy_portfolio_allocation_positive",
    } <= failed


def test_runtime_telemetry_blocks_bad_broker_resume_gate_config():
    config = scaleup_config(require_broker_resume_gate=True)
    config["broker_readiness"]["resume_gate"].update(
        {
            "ready": False,
            "proof_refresh_ready": False,
            "proof_refresh_strategy": "surface_mm",
            "proof_refresh_market": "us_options_regular",
        }
    )

    report = evaluate_runtime_telemetry(config)

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_resume_gate_ready",
        "broker_resume_proof_refresh_ready",
        "broker_resume_proof_refresh_strategy_matches",
        "broker_resume_proof_refresh_market_matches",
    } <= failed


def test_runtime_telemetry_fails_when_required_instrument_metadata_is_missing():
    report = evaluate_runtime_telemetry(scaleup_config(require_instrument_metadata=True))

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "instrument_metadata_provided" in failed


def test_write_runtime_telemetry_snapshot_outputs_artifacts(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    reconciliation_dir = tmp_path / "reconciliation"
    instrument_metadata_dir = tmp_path / "instrument_metadata"
    out_dir = tmp_path / "telemetry"
    pnl_path = tmp_path / "pnl.csv"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    scaleup_dir.mkdir()
    export_dir.mkdir()
    upload_dir.mkdir()
    reconciliation_dir.mkdir()
    instrument_metadata_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    export_summary().to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary().to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    reconciliation_summary().to_csv(reconciliation_dir / "reconciliation_summary.csv", index=False)
    reconciliation_checks().to_csv(reconciliation_dir / "reconciliation_checks.csv", index=False)
    instrument_metadata_summary().to_csv(instrument_metadata_dir / "instrument_metadata_summary.csv", index=False)
    pnl_snapshot().to_csv(pnl_path, index=False)
    open_orders().to_csv(open_orders_path, index=False)
    positions().to_csv(positions_path, index=False)

    report = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        export_dir=export_dir,
        upload_pack_dir=upload_dir,
        reconciliation_dir=reconciliation_dir,
        instrument_metadata_dir=instrument_metadata_dir,
        pnl_path=pnl_path,
        open_orders_path=open_orders_path,
        positions_path=positions_path,
        output_dir=out_dir,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "runtime_telemetry.csv").exists()
    assert (out_dir / "runtime_telemetry_sources.csv").exists()
    assert (out_dir / "runtime_telemetry_checks.csv").exists()
    assert (out_dir / "runtime_telemetry_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    sources = pd.read_csv(out_dir / "runtime_telemetry_sources.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    export_source = sources.loc[sources["source"] == "export_summary", "path"].iloc[0]
    upload_source = sources.loc[sources["source"] == "upload_summary", "path"].iloc[0]
    assert path_tail(export_source).endswith("/export/broker_order_summary.csv")
    assert path_tail(upload_source).endswith("/upload/broker_upload_summary.csv")
    assert path_tail(manifest["inputs"]["export"]["path"]).endswith("/export/broker_order_summary.csv")
    assert path_tail(manifest["inputs"]["upload_pack"]["path"]).endswith("/upload/broker_upload_summary.csv")


def test_cli_runtime_telemetry_reads_settlement_pipeline_export(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    pipeline_dir = tmp_path / "settlement_pipeline"
    export_dir = pipeline_dir / "04_export"
    out_dir = tmp_path / "telemetry"
    scaleup_dir.mkdir()
    export_dir.mkdir(parents=True)
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    export_summary().to_csv(export_dir / "broker_order_summary.csv", index=False)

    code = main(
        [
            "build-runtime-telemetry",
            "--scaleup",
            str(scaleup_dir),
            "--export",
            str(pipeline_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_telemetry_summary.csv")
    telemetry = pd.read_csv(out_dir / "runtime_telemetry.csv")
    sources = pd.read_csv(out_dir / "runtime_telemetry_sources.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert int(telemetry.loc[0, "orders_sent"]) == 4
    assert bool(sources.loc[sources["source"] == "export_summary", "provided"].iloc[0])
    export_source = sources.loc[sources["source"] == "export_summary", "path"].iloc[0]
    assert path_tail(export_source).endswith("/settlement_pipeline/04_export/broker_order_summary.csv")


def test_cli_runtime_telemetry_reads_surface_pipeline_export(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    pipeline_dir = tmp_path / "surface_launch_pipeline"
    export_dir = pipeline_dir / "03_export"
    upload_dir = pipeline_dir / "04_upload_pack"
    out_dir = tmp_path / "telemetry"
    scaleup_dir.mkdir()
    export_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    export_summary().to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary().to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "build-runtime-telemetry",
            "--scaleup",
            str(scaleup_dir),
            "--export",
            str(pipeline_dir),
            "--upload-pack",
            str(pipeline_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_telemetry_summary.csv")
    telemetry = pd.read_csv(out_dir / "runtime_telemetry.csv")
    sources = pd.read_csv(out_dir / "runtime_telemetry_sources.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert int(telemetry.loc[0, "orders_sent"]) == 4
    assert int(telemetry.loc[0, "lifecycle_orders"]) == 3
    assert int(telemetry.loc[0, "replace_orders"]) == 1
    assert bool(sources.loc[sources["source"] == "export_summary", "provided"].iloc[0])
    assert bool(sources.loc[sources["source"] == "upload_summary", "provided"].iloc[0])
    export_source = sources.loc[sources["source"] == "export_summary", "path"].iloc[0]
    upload_source = sources.loc[sources["source"] == "upload_summary", "path"].iloc[0]
    assert path_tail(export_source).endswith("/surface_launch_pipeline/03_export/broker_order_summary.csv")
    assert path_tail(upload_source).endswith("/surface_launch_pipeline/04_upload_pack/broker_upload_summary.csv")


def test_cli_runtime_telemetry_records_strategy_pipeline_source_paths(tmp_path):
    cases = [
        ("leadlag", "lead_lag_taker"),
        ("imbalance", "imbalance"),
        ("parity", "parity"),
    ]
    for family, strategy in cases:
        case_dir = tmp_path / family
        scaleup_dir = case_dir / "scaleup"
        pipeline_dir = case_dir / f"{family}_launch_pipeline"
        export_dir = pipeline_dir / "04_export"
        upload_dir = pipeline_dir / "05_upload_pack"
        out_dir = case_dir / "telemetry"
        scaleup_dir.mkdir(parents=True)
        export_dir.mkdir(parents=True)
        upload_dir.mkdir(parents=True)
        (scaleup_dir / "scaleup_config.json").write_text(
            json.dumps(scaleup_config(strategy=strategy), indent=2) + "\n",
            encoding="utf-8",
        )
        export_summary().to_csv(export_dir / "broker_order_summary.csv", index=False)
        upload_summary().to_csv(upload_dir / "broker_upload_summary.csv", index=False)

        code = main(
            [
                "build-runtime-telemetry",
                "--scaleup",
                str(scaleup_dir),
                "--export",
                str(pipeline_dir),
                "--upload-pack",
                str(pipeline_dir),
                "--out",
                str(out_dir),
                "--fail-on-breach",
            ]
        )

        summary = pd.read_csv(out_dir / "runtime_telemetry_summary.csv")
        sources = pd.read_csv(out_dir / "runtime_telemetry_sources.csv")
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        export_source = sources.loc[sources["source"] == "export_summary", "path"].iloc[0]
        upload_source = sources.loc[sources["source"] == "upload_summary", "path"].iloc[0]
        assert code == 0
        assert bool(summary.loc[0, "ready"])
        assert path_tail(export_source).endswith(
            f"/{family}_launch_pipeline/04_export/broker_order_summary.csv"
        )
        assert path_tail(upload_source).endswith(
            f"/{family}_launch_pipeline/05_upload_pack/broker_upload_summary.csv"
        )
        assert path_tail(manifest["inputs"]["export"]["path"]).endswith(
            f"/{family}_launch_pipeline/04_export/broker_order_summary.csv"
        )
        assert path_tail(manifest["inputs"]["upload_pack"]["path"]).endswith(
            f"/{family}_launch_pipeline/05_upload_pack/broker_upload_summary.csv"
        )


def test_cli_runtime_telemetry_can_fail_on_missing_identity(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "telemetry"
    scaleup_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(
        json.dumps(scaleup_config(scenario_key="", adapter="", strategy="", market=""), indent=2) + "\n",
        encoding="utf-8",
    )

    code = main(
        [
            "build-runtime-telemetry",
            "--scaleup",
            str(scaleup_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_telemetry_summary.csv")
    checks = pd.read_csv(out_dir / "runtime_telemetry_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {"strategy_present", "market_present", "scenario_key_present", "adapter_present"} <= failed
