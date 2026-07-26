import json

import pandas as pd

from adapters.broker_instrument_resolution import (
    BrokerInstrumentResolutionConfig,
    resolve_broker_instruments,
    verify_broker_instrument_resolution_evidence,
    write_broker_instrument_resolution,
)
from hft_cli import main
from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)


def box_orders():
    return pd.DataFrame(
        [
            _order("LOW_CALL", "NIFTY_20260630_1000C", 1000.0, "C"),
            _order("LOW_PUT", "NIFTY_20260630_1000P", 1000.0, "P"),
            _order("HIGH_CALL", "NIFTY_20260630_1010C", 1010.0, "C"),
            _order("HIGH_PUT", "NIFTY_20260630_1010P", 1010.0, "P"),
        ]
    )


def instrument_master():
    return pd.DataFrame(
        [
            _master("NIFTY26JUN1000CE", 1000.0, "CE", "10001"),
            _master("NIFTY26JUN1000PE", 1000.0, "PE", "10002"),
            _master("NIFTY26JUN1010CE", 1010.0, "CE", "10003"),
            _master("NIFTY26JUN1010PE", 1010.0, "PE", "10004"),
        ]
    )


def _order(role, instrument_id, strike, option_type):
    return {
        "client_order_id": f"BOX-{role}",
        "instrument_id": instrument_id,
        "expiry": "2026-06-30",
        "strike": strike,
        "option_type": option_type,
        "leg_group_id": "PBOX-1",
        "leg_role": role,
        "leg_count": 4,
        "side": 1,
        "qty": 75,
        "price": 10.0,
    }


def _master(symbol, strike, option_type, token):
    return {
        "name": "NIFTY",
        "expiry": "2026-06-30",
        "strike": strike,
        "instrument_type": option_type,
        "exchange": "NFO-OPT",
        "tradingsymbol": symbol,
        "instrument_token": token,
    }


def test_resolve_broker_instruments_requires_exact_complete_box_coverage():
    report = resolve_broker_instruments(box_orders(), instrument_master())

    assert report.ready
    assert report.summary.loc[0, "resolved_orders"] == 4
    assert report.summary.loc[0, "resolution_coverage"] == 1.0
    assert report.groups.loc[0, "complete"]
    assert set(report.orders["research_instrument_id"]) == {
        "NIFTY_20260630_1000C",
        "NIFTY_20260630_1000P",
        "NIFTY_20260630_1010C",
        "NIFTY_20260630_1010P",
    }
    assert set(report.orders["instrument_id"]) == {
        "NIFTY26JUN1000CE",
        "NIFTY26JUN1000PE",
        "NIFTY26JUN1010CE",
        "NIFTY26JUN1010PE",
    }
    assert set(report.orders["broker_instrument_token"].astype(str)) == {
        "10001",
        "10002",
        "10003",
        "10004",
    }
    assert set(report.orders["instrument_resolution_status"]) == {"resolved"}


def test_resolve_broker_instruments_blocks_missing_or_ambiguous_box_leg():
    missing = resolve_broker_instruments(
        box_orders(),
        instrument_master().iloc[:-1].copy(),
    )
    duplicated_master = pd.concat(
        [
            instrument_master(),
            pd.DataFrame(
                [
                    _master(
                        "NIFTY26JUN1010PE_ALT",
                        1010.0,
                        "PE",
                        "20004",
                    )
                ]
            ),
        ],
        ignore_index=True,
    )
    ambiguous = resolve_broker_instruments(
        box_orders(),
        duplicated_master,
    )

    assert not missing.ready
    assert missing.summary.loc[0, "unresolved_orders"] == 1
    assert missing.resolution.iloc[-1]["reason"] == "instrument_not_found"
    assert not missing.groups.loc[0, "complete"]
    assert not ambiguous.ready
    assert ambiguous.summary.loc[0, "ambiguous_orders"] == 1
    assert (
        ambiguous.resolution.iloc[-1]["reason"]
        == "ambiguous_instrument_match"
    )


def test_direct_research_id_mapping_supports_non_option_contracts():
    orders = pd.DataFrame(
        [
            {
                "client_order_id": "FUT-1",
                "instrument_id": "NIFTY_FUT",
                "leg_group_id": "PARITY-1",
                "leg_role": "FUTURE",
                "leg_count": 1,
            }
        ]
    )
    master = pd.DataFrame(
        [
            {
                "source_instrument_id": "NIFTY_FUT",
                "exchange": "NFO-FUT",
                "tradingsymbol": "NIFTY26JUNFUT",
                "instrument_token": "90001",
            }
        ]
    )

    report = resolve_broker_instruments(orders, master)

    assert report.ready
    assert report.resolution.loc[0, "match_method"] == "direct_research_id"
    assert report.orders.loc[0, "instrument_id"] == "NIFTY26JUNFUT"


def test_write_broker_instrument_resolution_outputs_lineage_bound_artifacts(
    tmp_path,
):
    orders_path = tmp_path / "orders.csv"
    master_path = tmp_path / "instrument_master.csv"
    out_dir = tmp_path / "resolution"
    box_orders().to_csv(orders_path, index=False)
    instrument_master().to_csv(master_path, index=False)

    report = write_broker_instrument_resolution(
        orders_path,
        master_path,
        output_dir=out_dir,
        config=BrokerInstrumentResolutionConfig(adapter="arrow_money"),
    )

    assert report.ready
    assert (out_dir / "resolved_order_candidates.csv").exists()
    assert (out_dir / "instrument_resolution.csv").exists()
    assert (out_dir / "instrument_resolution_checks.csv").exists()
    assert (out_dir / "instrument_resolution_groups.csv").exists()
    assert (out_dir / "instrument_resolution_summary.csv").exists()
    assert (out_dir / "instrument_resolution_action_queue.csv").exists()
    config = json.loads(
        (out_dir / "instrument_resolution_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert config["resolution"]["resolved_orders"] == 4
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="broker_instrument_resolution",
        required_artifacts=(
            "resolved_order_candidates.csv",
            "instrument_resolution.csv",
            "instrument_resolution_checks.csv",
            "instrument_resolution_groups.csv",
            "instrument_resolution_summary.csv",
            "instrument_resolution_action_queue.csv",
            "instrument_resolution_config.json",
            "instrument_resolution_runbook.md",
        ),
        require_input_fingerprints=True,
    )
    assert integrity.passed, integrity.error
    evidence = verify_broker_instrument_resolution_evidence(out_dir)
    assert evidence.passed, evidence.consistency_error
    assert evidence.manifest_current
    assert evidence.artifacts_consistent
    assert evidence.rebuilt_artifact_match_count == 8
    assert evidence.dependency_count == 2
    borrowed_summary_path = out_dir / "borrowed_ready_summary.csv"
    report.summary.to_csv(borrowed_summary_path, index=False)
    borrowed = verify_broker_instrument_resolution_evidence(
        borrowed_summary_path
    )
    assert borrowed.manifest_current
    assert not borrowed.artifacts_consistent
    assert not borrowed.passed
    assert (
        "summary_path_not_manifest_bound"
        in borrowed.consistency_error
    )


def test_resolution_evidence_rejects_remanifested_forged_ready_summary(
    tmp_path,
):
    orders_path = tmp_path / "orders.csv"
    master_path = tmp_path / "instrument_master.csv"
    out_dir = tmp_path / "resolution"
    box_orders().to_csv(orders_path, index=False)
    instrument_master().iloc[:-1].to_csv(master_path, index=False)
    write_broker_instrument_resolution(
        orders_path,
        master_path,
        output_dir=out_dir,
        config=BrokerInstrumentResolutionConfig(adapter="arrow_money"),
    )
    summary_path = out_dir / "instrument_resolution_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "ready"] = True
    summary.loc[0, "resolved_orders"] = 4
    summary.loc[0, "unresolved_orders"] = 0
    summary.loc[0, "resolution_coverage"] = 1.0
    summary.loc[0, "complete_leg_groups"] = 1
    summary.loc[0, "failed_checks"] = 0
    summary.to_csv(summary_path, index=False)
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        out_dir,
        run_type="broker_instrument_resolution",
        parameters=manifest["parameters"],
        inputs={
            "orders": orders_path,
            "instrument_master": master_path,
        },
    )

    manifest_integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="broker_instrument_resolution",
        require_input_fingerprints=True,
    )
    evidence = verify_broker_instrument_resolution_evidence(out_dir)

    assert manifest_integrity.passed
    assert evidence.manifest_current
    assert not evidence.artifacts_consistent
    assert not evidence.passed
    assert (
        "artifact_content_mismatch:instrument_resolution_summary.csv"
        in evidence.consistency_error
    )


def test_cli_resolve_broker_instruments_fails_closed_on_missing_leg(
    tmp_path,
):
    orders_path = tmp_path / "orders.csv"
    master_path = tmp_path / "instrument_master.csv"
    out_dir = tmp_path / "resolution"
    box_orders().to_csv(orders_path, index=False)
    instrument_master().iloc[:-1].to_csv(master_path, index=False)

    code = main(
        [
            "resolve-broker-instruments",
            "--orders",
            str(orders_path),
            "--instrument-master",
            str(master_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--exchange",
            "NFO",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(
        out_dir / "instrument_resolution_summary.csv"
    )
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "resolved_orders"] == 3
