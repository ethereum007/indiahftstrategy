import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import write_experiment_manifest
from reports.provider_market_data_imbalance_broker_rehearsal_certificate import (
    ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig,
    write_provider_market_data_imbalance_broker_rehearsal_certificate,
)


def test_broker_rehearsal_certificate_seals_manifest_chain_and_is_deterministic(tmp_path):
    source = _write_roundtrip_fixture(tmp_path, sealed_receipts=True)

    first = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_one",
        config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
            require_sealed_provider_receipts=True,
        ),
    )
    second = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_two",
        config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
            require_sealed_provider_receipts=True,
        ),
    )

    assert first.ready
    assert first.certificate["status"] == "valid"
    assert first.certificate["authorizes_submission"] is False
    assert first.certificate["digitally_signed"] is False
    assert first.certificate["payload"]["integrity_scheme"] == "sha256_manifest_chain_v1"
    assert first.certificate["payload"]["safety"]["submission_enabled"] is False
    assert first.certificate["payload"]["safety"]["dry_run_only"] is True
    assert first.certificate["payload"]["assurance_level"] == "sealed_provider_receipts"
    assert first.certificate["cycle_id"].startswith("hft-rehearsal-")
    assert len(first.certificate["certificate_sha256"]) == 64
    assert first.certificate["cycle_id"] == second.certificate["cycle_id"]
    assert first.certificate["certificate_sha256"] == second.certificate["certificate_sha256"]
    assert first.fingerprint_inventory["matches"].astype(bool).all()
    assert first.manifest_graph["passed"].astype(bool).all()
    assert {
        "provider_market_data_imbalance_broker_dispatch_roundtrip",
        "broker_dispatch_roundtrip",
        "broker_dispatch_plan",
        "broker_dispatch_send_packet",
        "broker_dispatch_ack_reconciliation",
    }.issubset(set(first.manifest_graph["run_type"]))
    assert first.action_queue.empty

    summary = first.summary.iloc[0]
    assert bool(summary["ready"])
    assert not bool(summary["authorizes_submission"])
    assert int(summary["acked_orders"]) == 2
    assert summary["next_gate"] == "review-provider-market-data-imbalance-broker-readiness"

    output_manifest = json.loads((first.output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert output_manifest["run_type"] == "provider_market_data_imbalance_broker_rehearsal_certificate"
    assert output_manifest["extra"]["authorizes_submission"] is False
    assert output_manifest["extra"]["digitally_signed"] is False
    assert output_manifest["extra"]["cycle_id"] == first.certificate["cycle_id"]
    assert len(output_manifest["inputs"]["manifest_chain"]) == len(first.manifest_graph)

    catalog = catalog_experiment_runs([first.output_dir]).catalog.iloc[0]
    assert catalog["run_type"] == "provider_market_data_imbalance_broker_rehearsal_certificate"
    assert bool(catalog["summary_status"])
    assert not bool(catalog["summary_authorizes_submission"])


def test_broker_rehearsal_certificate_blocks_recorded_input_drift(tmp_path):
    source = _write_roundtrip_fixture(tmp_path, sealed_receipts=True)
    dispatch_artifact = tmp_path / "components" / "dispatch" / "dispatch.csv"
    dispatch_artifact.write_text(
        "id,status\n1,ready\n2,changed_after_roundtrip\n",
        encoding="utf-8",
    )

    report = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_drifted",
        config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
            require_sealed_provider_receipts=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "manifest_graph_valid" in failed
    assert "recorded_fingerprints_current" in failed
    drift = report.fingerprint_inventory.loc[
        report.fingerprint_inventory["path"].astype(str) == str(dispatch_artifact)
    ].iloc[0]
    assert not bool(drift["matches"])
    assert drift["reason"] == "fingerprint drift"
    assert report.summary.iloc[0]["next_gate"] == (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    )
    assert not report.action_queue.empty


def test_broker_rehearsal_certificate_rejects_relaxed_submission_threshold(tmp_path):
    source = _write_roundtrip_fixture(
        tmp_path,
        sealed_receipts=True,
        submission_enabled=True,
    )

    report = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_submission_enabled",
    )

    assert not report.ready
    submission = report.checks.loc[
        report.checks["check"] == "strict_submission_disabled"
    ].iloc[0]
    assert bool(submission["value"])
    assert not bool(submission["passed"])
    assert report.certificate["payload"]["safety"]["submission_enabled"] is True
    action = report.action_queue.loc[
        report.action_queue["check"] == "strict_submission_disabled"
    ].iloc[0]
    assert action["next_gate"] == "prepare-provider-market-data-imbalance-broker-dispatch-send"


def test_broker_rehearsal_certificate_rejects_relaxed_count_thresholds(tmp_path):
    source = _write_roundtrip_fixture(
        tmp_path,
        sealed_receipts=True,
        relaxed_request_count=True,
    )

    report = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_relaxed_counts",
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "strict_request_count_matches_dispatch" in failed
    assert "strict_unique_request_per_dispatch_order" in failed


def test_broker_rehearsal_certificate_supports_optional_and_required_receipt_levels(tmp_path):
    source = _write_roundtrip_fixture(tmp_path, sealed_receipts=False)

    generic = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_generic",
    )
    sealed = write_provider_market_data_imbalance_broker_rehearsal_certificate(
        source,
        tmp_path / "certificate_requires_receipts",
        config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
            require_sealed_provider_receipts=True,
        ),
    )

    assert generic.ready
    assert generic.certificate["payload"]["assurance_level"] == "broker_dry_run_roundtrip"
    assert not sealed.ready
    failed = set(sealed.checks.loc[~sealed.checks["passed"].astype(bool), "check"])
    assert "sealed_provider_receipts_present" in failed
    assert "provider_receipt_proof_ready" in failed


def test_broker_rehearsal_certificate_cli(tmp_path):
    source = _write_roundtrip_fixture(tmp_path, sealed_receipts=True)
    output = tmp_path / "certificate_cli"

    status = main(
        [
            "certify-provider-market-data-imbalance-broker-rehearsal",
            "--provider-broker-dispatch-roundtrip",
            str(source),
            "--out",
            str(output),
            "--require-sealed-provider-receipts",
            "--fail-on-breach",
        ]
    )

    assert status == 0
    summary = pd.read_csv(
        output / "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv"
    ).iloc[0]
    assert bool(summary["ready"])
    assert not bool(summary["authorizes_submission"])


def _write_roundtrip_fixture(
    tmp_path: Path,
    *,
    sealed_receipts: bool,
    submission_enabled: bool = False,
    relaxed_request_count: bool = False,
) -> Path:
    components = tmp_path / "components"
    dispatch = _write_component(components / "dispatch", "broker_dispatch_plan", "dispatch.csv")
    send = _write_component(components / "send", "broker_dispatch_send_packet", "send.csv")
    ack = _write_component(
        components / "ack",
        "broker_dispatch_ack_reconciliation",
        "ack.csv",
    )

    source = tmp_path / "provider_roundtrip"
    nested = source / "broker_dispatch_roundtrip"
    nested.mkdir(parents=True)
    nested_summary = {
        "passed": True,
        "target_mode": "live_dryrun",
        "strategy": "microprice_imbalance",
        "market": "india",
        "scenario_key": "nse_open_rehearsal",
        "adapter": "arrow_ws",
        "dispatch_batch_id": "batch-001",
        "dispatch_orders": 2,
        "send_requests": 2,
        "acked_orders": 2,
        "missing_request_acks": 0,
        "rejected_orders": 0,
        "duplicate_ack_orders": 0,
        "unmatched_acks": 0,
        "total_failed_component_checks": 0,
        "failed_checks": 0,
    }
    pd.DataFrame([nested_summary]).to_csv(
        nested / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    pd.DataFrame(
        _nested_safety_checks(
            submission_enabled=submission_enabled,
            relaxed_request_count=relaxed_request_count,
        )
    ).to_csv(
        nested / "broker_dispatch_roundtrip_checks.csv",
        index=False,
    )
    write_experiment_manifest(
        nested,
        run_type="broker_dispatch_roundtrip",
        inputs={"dispatch": dispatch, "send": send, "ack": ack},
        extra={"passed": True, "strategy": "microprice_imbalance", "market": "india"},
    )
    _mark_manifest_clean(nested / "manifest.json")

    evidence = tmp_path / "provider_evidence"
    evidence.mkdir()
    receipt = evidence / "receipt.json"
    capture = evidence / "capture.csv"
    receipt.write_text('{"status":"captured","sequence":1}\n', encoding="utf-8")
    capture.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")

    source_summary = {
        "passed": True,
        "ready": True,
        "provider_broker_dispatch_ack_passed": True,
        "broker_dispatch_roundtrip_passed": True,
        "profile": "imbalance",
        "provider": "arrow_ws",
        "transport": "websocket",
        "strategy": "microprice_imbalance",
        "market": "india",
        "exchange": "NSE",
        "target_mode": "live_dryrun",
        "adapter": "arrow_ws",
        "scenario_key": "nse_open_rehearsal",
        "broker_dispatch_roundtrip_dir": str(nested.resolve()),
        "dispatch_orders": 2,
        "send_requests": 2,
        "acked_orders": 2,
        "missing_request_acks": 0,
        "rejected_orders": 0,
        "duplicate_ack_orders": 0,
        "unmatched_acks": 0,
        "dispatch_roundtrip_adapter_receipts_required": sealed_receipts,
        "dispatch_roundtrip_adapter_receipt_required_count": 1 if sealed_receipts else 0,
        "dispatch_roundtrip_adapter_receipt_valid_count": 1 if sealed_receipts else 0,
        "dispatch_roundtrip_adapter_receipt_fingerprint_match_count": 1 if sealed_receipts else 0,
        "dispatch_roundtrip_capture_fingerprint_match_count": 1 if sealed_receipts else 0,
        "dispatch_roundtrip_adapter_receipt_proof_ready": sealed_receipts,
        "dispatch_roundtrip_adapter_receipt_proof_matches_manifest": sealed_receipts,
        "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session": sealed_receipts,
        "dispatch_roundtrip_provider_profile_sha256": "a" * 64,
        "failed_checks": 0,
    }
    pd.DataFrame([source_summary]).to_csv(
        source / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "check": "broker_dispatch_roundtrip_passed",
                "value": True,
                "operator": "is",
                "threshold": True,
                "passed": True,
                "reason": "",
            }
        ]
    ).to_csv(
        source / "provider_market_data_imbalance_broker_dispatch_roundtrip_checks.csv",
        index=False,
    )
    source_config = {
        "schema_version": 1,
        "passed": True,
        "ready": True,
        "summary": source_summary,
        "provider_profile": {"adapter": "arrow_ws", "sha256": "a" * 64},
    }
    (source / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(source_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (source / "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md").write_text(
        "# Provider broker roundtrip\n",
        encoding="utf-8",
    )
    inputs = {"broker_dispatch_roundtrip": nested}
    if sealed_receipts:
        inputs.update({"provider_receipt": receipt, "provider_capture": capture})
    write_experiment_manifest(
        source,
        run_type="provider_market_data_imbalance_broker_dispatch_roundtrip",
        inputs=inputs,
        extra={
            "passed": True,
            "broker_dispatch_roundtrip_passed": True,
            "profile": "imbalance",
            "strategy": "microprice_imbalance",
            "market": "india",
            "exchange": "NSE",
        },
    )
    _mark_manifest_clean(source / "manifest.json")
    return source


def _write_component(path: Path, run_type: str, artifact_name: str) -> Path:
    path.mkdir(parents=True)
    (path / artifact_name).write_text("id,status\n1,ready\n", encoding="utf-8")
    write_experiment_manifest(path, run_type=run_type, extra={"ready": True})
    _mark_manifest_clean(path / "manifest.json")
    return path


def _mark_manifest_clean(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["git"] = {"branch": "master", "commit": "f" * 40, "dirty": False}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _nested_safety_checks(
    *,
    submission_enabled: bool,
    relaxed_request_count: bool,
) -> list[dict]:
    request_count = 1 if relaxed_request_count else 2
    values = [
        ("dispatch_ready", True, "is", True),
        ("send_ready", True, "is", True),
        ("ack_passed", True, "is", True),
        ("target_mode_matches", "live_dryrun", "==", "live_dryrun"),
        ("identity_match", 0, "==", 0),
        ("request_count_matches_dispatch", request_count, "==", request_count),
        ("unique_request_per_dispatch_order", request_count, "==", request_count),
        ("submission_disabled", submission_enabled, "is", False),
        ("dry_run_only", True, "is", True),
        ("all_requests_acked", 2, "==", 2),
        ("missing_request_acks", 0, "<=", 0),
        ("rejected_orders", 0, "==", 0),
        ("duplicate_ack_orders", 0, "<=", 0),
        ("unmatched_acks", 0, "<=", 0),
        ("component_failed_checks", 0, "<=", 0),
        ("route_enable_dispatch_roundtrip_failed_checks", 0, "<=", 0),
    ]
    return [
        {
            "check": check,
            "value": value,
            "operator": operator,
            "threshold": threshold,
            "passed": True,
            "reason": "",
        }
        for check, value, operator, threshold in values
    ]
