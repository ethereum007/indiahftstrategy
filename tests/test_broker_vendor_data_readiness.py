import json

import pandas as pd

from hft_cli import main
from reports.broker_vendor_data_readiness import (
    BrokerVendorDataReadinessConfig,
    write_broker_vendor_data_readiness_pipeline,
)
from tests.broker_vendor_data_helpers import assert_broker_vendor_data_proof_forwarded


def vendor_ticks(day: str, *, base: float = 100.0):
    return pd.DataFrame(
        [
            {
                "exchange_ts": f"{day} 09:15:00",
                "best_bid": base,
                "best_ask": base + 0.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": base + 0.05,
                "last_size": 75,
            },
            {
                "exchange_ts": f"{day} 09:15:01",
                "best_bid": base + 0.05,
                "best_ask": base + 0.10,
                "bid_size": 150,
                "ask_size": 75,
                "last_px": base + 0.10,
                "last_size": 75,
            },
        ]
    )


def schema_summary(adapter):
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "kind": "orders",
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "missing_required_columns": 0,
                "all_required_present": True,
            }
        ]
    )


def order_export_summary(adapter):
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0,
            }
        ]
    )


def upload_summary(adapter):
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0,
                "recommendation": "dry_run_or_paper_review",
            }
        ]
    )


def dispatch_roundtrip_summary(adapter):
    return pd.DataFrame(
        [
            {
                "passed": True,
                "adapter": adapter,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "batch_id": "BDP-1",
                "requests": 2,
                "send_requests": 2,
                "acked_orders": 2,
                "missing_request_acks": 0,
                "rejected_orders": 0,
                "unmatched_acks": 0,
                "failed_checks": 0,
                "route_dispatch_roundtrip_provided": True,
                "route_dispatch_roundtrip_ready": True,
                "route_dispatch_roundtrip_target_mode": "live_dryrun",
                "route_dispatch_roundtrip_strategy": "lead_lag_taker",
                "route_dispatch_roundtrip_market": "india_nse_index_derivatives",
                "route_dispatch_roundtrip_scenario_key": "trigger_ticks=2",
                "route_dispatch_roundtrip_batch_id": "BDP-0",
                "route_dispatch_roundtrip_requests": 2,
                "route_dispatch_roundtrip_acked_orders": 2,
                "route_dispatch_roundtrip_missing_request_acks": 0,
                "route_dispatch_roundtrip_rejected_orders": 0,
                "route_dispatch_roundtrip_unmatched_acks": 0,
                "recommendation": "ready_for_broker_readiness_review",
            }
        ]
    )


def dispatch_roundtrip_config():
    return {
        "route_readiness": {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "route_ready_pairs": 1,
            "gap_pairs": 0,
            "recommendation": "eligible_for_live_dryrun_route_review",
        },
        "route_enable_dispatch_roundtrip": {"failed_checks": 0},
    }


def leadlag_scenario_key():
    return (
        "strategy=lead_lag_taker|market=india_nse_index_derivatives|trigger_ticks=10|"
        "delta=1|leader_tick=0.05|laggard_tick=0.05"
    )


def write_leadlag_promotion(path):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": True,
                "candidate_scenario_key": leadlag_scenario_key(),
                "failed_checks": 0,
                "recommendation": "paper_or_shadow_candidate",
            }
        ]
    ).to_csv(path / "promotion_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "lead_lag_taker",
                "scenario_key": leadlag_scenario_key(),
                "parameters": {
                    "market": "india_nse_index_derivatives",
                    "leader_tick": 0.05,
                    "laggard_tick": 0.05,
                    "delta": 1.0,
                    "trigger_ticks": 10.0,
                    "qty": 75,
                    "flat_after_ns": 200_000,
                    "cooloff_ns": 1000,
                },
                "metrics": {
                    "total_net_pnl": 42.0,
                    "median_markout_mean": 0.15,
                },
                "failed_checks": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_inputs(root, adapter):
    day1 = root / f"{adapter}_ticks_day1.csv"
    day2 = root / f"{adapter}_ticks_day2.csv"
    schema_dir = root / "schema"
    export_dir = root / "export"
    upload_dir = root / "upload"
    roundtrip_dir = root / "roundtrip"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir(parents=True)
    vendor_ticks("2026-06-10", base=100.0).to_csv(day1, index=False)
    vendor_ticks("2026-06-11", base=100.5).to_csv(day2, index=False)
    schema_summary(adapter).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary(adapter).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary(adapter).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    dispatch_roundtrip_summary(adapter).to_csv(roundtrip_dir / "broker_dispatch_roundtrip_summary.csv", index=False)
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(dispatch_roundtrip_config(), indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "input": [day1, day2],
        "schema": schema_dir,
        "export": export_dir,
        "upload": upload_dir,
        "roundtrip": roundtrip_dir,
    }


def test_broker_vendor_data_readiness_pipeline_runs_arrow_and_irage(tmp_path):
    for adapter in ("arrow_money", "irage"):
        root = tmp_path / adapter
        paths = write_inputs(root, adapter)
        out_dir = root / "proof"

        report = write_broker_vendor_data_readiness_pipeline(
            paths["input"],
            output_dir=out_dir,
            labels=["day1", "day2"],
            schema_audit_dir=paths["schema"],
            order_export_dir=paths["export"],
            upload_pack_dir=paths["upload"],
            dispatch_roundtrip_dir=paths["roundtrip"],
            config=BrokerVendorDataReadinessConfig(
                adapter=adapter,
                kind="ticks",
                timestamp_unit="datetime",
                tick_size=0.05,
                min_rows=2,
            ),
        )

        assert report.ready
        summary = report.summary.iloc[0]
        assert summary["adapter"] == adapter
        assert bool(summary["vendor_batch_ready"])
        assert bool(summary["broker_readiness_ready"])
        assert bool(summary["broker_vendor_data_ready"])
        assert int(summary["dataset_count"]) == 2
        assert (out_dir / "01_vendor_market_data_batch" / "vendor_market_data_batch_config.json").exists()
        assert (out_dir / "02_broker_readiness" / "broker_readiness_config.json").exists()
        config = json.loads((out_dir / "broker_vendor_data_readiness_config.json").read_text(encoding="utf-8"))
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert config["ready"]
        assert config["adapter"] == adapter
        assert manifest["run_type"] == "broker_vendor_data_readiness_pipeline"
        assert "vendor_market_data_batch" in manifest["inputs"]
        assert "broker_readiness" in manifest["inputs"]


def test_cli_broker_vendor_data_readiness_pipeline(tmp_path):
    paths = write_inputs(tmp_path, "arrow_money")
    out_dir = tmp_path / "proof"

    code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(out_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_vendor_data_readiness_summary.csv")
    components = pd.read_csv(out_dir / "broker_vendor_data_readiness_components.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_vendor_data_ready"])
    assert set(components["component"]) == {"vendor_market_data_batch", "broker_readiness"}


def test_cli_broker_vendor_data_readiness_output_feeds_launch_cli(tmp_path):
    paths = write_inputs(tmp_path / "broker_inputs", "arrow_money")
    proof_dir = tmp_path / "broker_vendor_data"

    vendor_code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(proof_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    promotion_dir = tmp_path / "promotion"
    launch_dir = tmp_path / "launch_pipeline"
    write_leadlag_promotion(promotion_dir)
    launch_code = main(
        [
            "pipeline-leadlag-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(launch_dir),
            "--adapter",
            "arrow_money",
            "--route-tag",
            "leadlag_shadow",
            "--laggard-instrument-id",
            "NIFTY_20260610_25000C",
            "--reference-price",
            "10",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--max-orders",
            "2",
            "--broker-vendor-data-readiness",
            str(proof_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    launch_summary = pd.read_csv(launch_dir / "leadlag_launch_pipeline_summary.csv")
    assert vendor_code == 0
    assert launch_code == 0
    assert bool(launch_summary.loc[0, "ready"])
    assert_broker_vendor_data_proof_forwarded(launch_dir)
