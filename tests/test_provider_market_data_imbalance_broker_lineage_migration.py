import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import hft_cli
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.operational_lineage import (
    broker_dispatch_ack_lineage_fields,
    empty_broker_dispatch_ack_lineage,
)
from reports.provider_market_data_imbalance_broker_dispatch_ack import (
    ProviderMarketDataImbalanceBrokerDispatchAckConfig,
    write_provider_market_data_imbalance_broker_dispatch_ack,
)
from reports.provider_market_data_imbalance_broker_dispatch_roundtrip import (
    ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig,
    write_provider_market_data_imbalance_broker_dispatch_roundtrip,
)
from reports.provider_market_data_imbalance_broker_lineage_migration import (
    ProviderBrokerLineageMigrationConfig,
    provider_broker_lineage_migration_audit_check,
    provider_broker_lineage_migration_audit_evidence,
    provider_broker_lineage_migration_audit_inputs,
    provider_broker_lineage_migration_audit_summary_fields,
    verify_provider_broker_lineage_migration_audit,
    write_provider_broker_lineage_migration_audit,
)
from reports.provider_market_data_imbalance_broker_lineage_audit_usage import (
    write_provider_broker_lineage_audit_usage_review,
)
from reports.provider_market_data_imbalance_broker_lineage_refresh_convergence import (
    write_provider_broker_lineage_refresh_convergence,
)
from reports.provider_market_data_imbalance_broker_active_lineage import (
    resolve_provider_broker_active_lineage_bundle,
    verify_provider_broker_active_lineage_index,
    write_provider_broker_active_lineage_index,
)
from reports.provider_market_data_imbalance_broker_rehearsal_certificate import (
    ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig,
    write_provider_market_data_imbalance_broker_rehearsal_certificate,
)


ACK_RUN_TYPE = "provider_market_data_imbalance_broker_dispatch_ack"
ROUNDTRIP_RUN_TYPE = (
    "provider_market_data_imbalance_broker_dispatch_roundtrip"
)
CERTIFICATE_RUN_TYPE = (
    "provider_market_data_imbalance_broker_rehearsal_certificate"
)


def test_lineage_migration_audit_accepts_strict_archive_and_catalogs_report(
    tmp_path,
):
    chain = _write_provider_chain(tmp_path / "archive", strict=True)
    output = chain["root"] / "migration_audit"

    report = write_provider_broker_lineage_migration_audit(
        [chain["root"]],
        output,
    )

    assert report.ready
    assert set(report.inventory["migration_status"]) == {"strict_ready"}
    assert len(report.inventory) == 3
    assert report.action_queue.empty
    assert bool(report.summary.iloc[0]["ready_for_strict_default"])
    assert float(report.summary.iloc[0]["strict_ready_coverage"]) == 1.0
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert {
        "provider_broker_lineage_migration_inventory.csv",
        "provider_broker_lineage_migration_checks.csv",
        "provider_broker_lineage_migration_summary.csv",
        "provider_broker_lineage_migration_action_queue.csv",
        "provider_broker_lineage_migration_config.json",
        "provider_broker_lineage_migration_runbook.md",
        "manifest.json",
    }.issubset({path.name for path in output.iterdir()})

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_type"] == (
        "provider_market_data_imbalance_broker_lineage_migration_audit"
    )
    assert manifest["extra"]["authorizes_submission"] is False
    assert len(manifest["inputs"]["audited_provider_bundles"]) == 3
    assert len(manifest["inputs"]["audited_provider_manifests"]) == 3
    assert manifest["inputs"]["audited_provider_dependencies"]
    assert int(report.summary.iloc[0]["audited_manifest_count"]) == 3
    assert int(report.summary.iloc[0]["audited_dependency_count"]) > 3
    assert report.config["schema_version"] == 2

    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert catalog["run_type"] == manifest["run_type"]
    assert bool(catalog["summary_status"])
    assert not bool(catalog["summary_authorizes_submission"])


def test_lineage_migration_audit_plans_ordered_non_destructive_regeneration(
    tmp_path,
):
    chain = _write_provider_chain(tmp_path / "archive", strict=False)

    report = write_provider_broker_lineage_migration_audit(
        [chain["root"]],
        chain["root"] / "migration_audit",
    )

    assert not report.ready
    assert set(report.inventory["migration_status"]) == {"regenerate_strict"}
    assert int(report.summary.iloc[0]["regenerate_strict_bundles"]) == 3
    assert int(report.summary.iloc[0]["blocked_bundles"]) == 0
    assert list(report.action_queue["bundle_type"]) == [
        "provider_ack",
        "provider_roundtrip",
        "rehearsal_certificate",
    ]
    assert set(report.action_queue["queue_status"]) == {"ready"}

    commands = dict(
        zip(
            report.action_queue["bundle_type"],
            report.action_queue["command"],
        )
    )
    assert "--require-send-packet" in commands["provider_ack"]
    assert "--allow-rejections" in commands["provider_ack"]
    assert "--max-unmatched-acks 2" in commands["provider_ack"]
    assert "--require-ack-lineage" in commands["provider_roundtrip"]
    assert "01_provider_ack_strict" in commands["provider_roundtrip"]
    assert "--target-mode shadow" in commands["provider_roundtrip"]
    assert "--require-ack-lineage" in commands["rehearsal_certificate"]
    assert "02_provider_roundtrip_strict" in commands["rehearsal_certificate"]
    assert "--max-manifests 96" in commands["rehearsal_certificate"]
    assert not (chain["ack"].parent / "01_provider_ack_strict").exists()
    assert not (
        chain["roundtrip"].parent / "02_provider_roundtrip_strict"
    ).exists()

    runbook = (
        report.output_dir / "provider_broker_lineage_migration_runbook.md"
    ).read_text(encoding="utf-8")
    assert "This audit is read-only" in runbook
    assert "Authorizes broker submission: no" in runbook


@pytest.mark.parametrize("strict", [False, True])
def test_lineage_migration_audit_blocks_transitively_stale_archive(
    tmp_path,
    strict,
):
    chain = _write_provider_chain(tmp_path / "archive", strict=strict)
    (chain["provider_send"] / "proof.txt").write_text(
        "changed after archival\n",
        encoding="utf-8",
    )

    report = write_provider_broker_lineage_migration_audit(
        [chain["root"]],
        chain["root"] / "migration_audit",
        config=ProviderBrokerLineageMigrationConfig(
            max_blocked_bundles=0,
            min_strict_ready_coverage=0.0,
        ),
    )

    assert not report.ready
    assert set(report.inventory["migration_status"]) == {"blocked"}
    assert int(report.summary.iloc[0]["blocked_bundles"]) == 3
    assert set(report.action_queue["queue_status"]) == {"blocked"}
    assert not report.inventory["source_manifest_current"].astype(bool).any()


def test_lineage_migration_audit_accepts_equivalent_strict_replacements(
    tmp_path,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )

    report = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )

    assert report.ready
    assert len(report.inventory) == 6
    assert int(report.summary.iloc[0]["strict_ready_bundles"]) == 3
    assert int(
        report.summary.iloc[0]["strict_replacement_covered_bundles"]
    ) == 3
    assert float(report.summary.iloc[0]["strict_ready_coverage"]) == 1.0
    assert report.action_queue.empty
    legacy_rows = report.inventory.loc[
        ~report.inventory["bundle_path"].astype(str).str.endswith("_strict")
    ]
    assert set(legacy_rows["migration_status"]) == {"covered_by_strict"}
    assert legacy_rows["strict_replacement_current"].astype(bool).all()
    assert legacy_rows["strict_replacement_matches_policy"].astype(bool).all()
    assert legacy_rows[
        "strict_replacement_matches_evidence"
    ].astype(bool).all()
    assert legacy_rows[
        "strict_replacement_dependency_covered"
    ].astype(bool).all()
    manifest = json.loads(
        (report.output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["extra"]["strict_replacement_covered_bundles"] == 3


@pytest.mark.parametrize(
    (
        "command",
        "source_key",
        "writer_name",
        "legacy_flag",
        "source_option",
        "extra_args",
    ),
    [
        (
            "reconcile-provider-market-data-imbalance-broker-dispatch",
            "provider_send",
            "write_provider_market_data_imbalance_broker_dispatch_ack",
            "--allow-legacy-send-lineage",
            "--provider-broker-dispatch-send",
            ("--acks", "acks"),
        ),
        (
            "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
            "ack",
            "write_provider_market_data_imbalance_broker_dispatch_roundtrip",
            "--allow-legacy-ack-lineage",
            "--provider-broker-dispatch-ack",
            (),
        ),
        (
            "certify-provider-market-data-imbalance-broker-rehearsal",
            "roundtrip",
            "write_provider_market_data_imbalance_broker_rehearsal_certificate",
            "--allow-legacy-ack-lineage",
            "--provider-broker-dispatch-roundtrip",
            (),
        ),
    ],
)
def test_legacy_provider_cli_overrides_require_exact_source_audit(
    tmp_path,
    monkeypatch,
    command,
    source_key,
    writer_name,
    legacy_flag,
    source_option,
    extra_args,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    audit = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )
    writer_calls = []

    def fake_writer(*args, **kwargs):
        writer_calls.append((args, kwargs))
        return SimpleNamespace(
            summary=pd.DataFrame([{"passed": True, "ready": True}]),
            action_queue=pd.DataFrame(),
        )

    monkeypatch.setattr(hft_cli, writer_name, fake_writer)
    argv = [
        command,
        source_option,
        str(legacy[source_key]),
        "--out",
        str(tmp_path / f"{source_key}_cli_output"),
        legacy_flag,
    ]
    if extra_args:
        option, path_key = extra_args
        argv.extend([option, str(legacy[path_key])])

    with pytest.raises(
        ValueError,
        match="--lineage-migration-audit is required",
    ):
        hft_cli.main(argv)
    with pytest.raises(
        ValueError,
        match="only valid with",
    ):
        hft_cli.main(
            [
                item
                for item in argv
                if item != legacy_flag
            ]
            + ["--lineage-migration-audit", str(audit.output_dir)]
        )
    assert not writer_calls

    status = hft_cli.main(
        argv + ["--lineage-migration-audit", str(audit.output_dir)]
    )

    assert status == 0
    assert len(writer_calls) == 1
    writer_config = writer_calls[0][1]["config"]
    assert writer_config.lineage_migration_audit_dir == str(
        audit.output_dir.resolve()
    )


def test_lineage_migration_audit_inputs_seal_post_audit_drift(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    audit = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )
    output = tmp_path / "audit_consumer"
    output.mkdir()
    (output / "proof.txt").write_text("consumer\n", encoding="utf-8")
    audit_inputs = provider_broker_lineage_migration_audit_inputs(
        audit.output_dir
    )
    audit_evidence = provider_broker_lineage_migration_audit_evidence(
        audit.output_dir,
        source_path=legacy["provider_send"],
        source_role="provider_send",
    )
    manifest = write_experiment_manifest(
        output,
        run_type="lineage_migration_audit_consumer_test",
        inputs=audit_inputs,
        extra={"authorizes_submission": False},
    )

    assert {
        "lineage_migration_audit",
        "lineage_migration_audit_manifest",
        "lineage_migration_audit_dependencies",
    } == set(audit_inputs)
    assert audit_evidence["ready"]
    assert audit_evidence["source_covered"]
    assert audit_evidence["source_status"] == "covered_by_strict"
    assert audit_evidence["manifest_sha256"]
    assert audit_evidence["strict_replacement_manifest_sha256"]
    assert provider_broker_lineage_migration_audit_check(
        audit_evidence
    )["passed"]
    assert provider_broker_lineage_migration_audit_summary_fields(
        audit_evidence
    )["lineage_migration_audit_ready"]
    assert verify_experiment_manifest(
        manifest,
        expected_run_type="lineage_migration_audit_consumer_test",
        require_input_fingerprints=True,
    ).passed

    (legacy["provider_send"] / "proof.txt").write_text(
        "changed after consumer proof\n",
        encoding="utf-8",
    )
    assert not verify_experiment_manifest(
        manifest,
        expected_run_type="lineage_migration_audit_consumer_test",
        require_input_fingerprints=True,
    ).passed


@pytest.mark.parametrize("stage", ["ack", "roundtrip", "certificate"])
def test_provider_legacy_outputs_surface_lineage_migration_audit(
    tmp_path,
    stage,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    audit = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )
    output = tmp_path / f"{stage}_legacy_output"

    if stage == "ack":
        write_provider_market_data_imbalance_broker_dispatch_ack(
            legacy["provider_send"],
            legacy["acks"],
            output,
            config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(
                require_send_packet=False,
                lineage_migration_audit_dir=str(audit.output_dir),
            ),
        )
        summary_name = (
            "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
        )
        checks_name = (
            "provider_market_data_imbalance_broker_dispatch_ack_checks.csv"
        )
        config_name = (
            "provider_market_data_imbalance_broker_dispatch_ack_config.json"
        )
        runbook_name = (
            "provider_market_data_imbalance_broker_dispatch_ack_runbook.md"
        )
        run_type = ACK_RUN_TYPE
    elif stage == "roundtrip":
        write_provider_market_data_imbalance_broker_dispatch_roundtrip(
            legacy["ack"],
            output,
            config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(
                require_ack_lineage=False,
                lineage_migration_audit_dir=str(audit.output_dir),
            ),
        )
        summary_name = (
            "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
        )
        checks_name = (
            "provider_market_data_imbalance_broker_dispatch_roundtrip_checks.csv"
        )
        config_name = (
            "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
        )
        runbook_name = (
            "provider_market_data_imbalance_broker_dispatch_roundtrip_runbook.md"
        )
        run_type = ROUNDTRIP_RUN_TYPE
    else:
        write_provider_market_data_imbalance_broker_rehearsal_certificate(
            legacy["roundtrip"],
            output,
            config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
                require_clean_recorded_git=False,
                require_ack_lineage=False,
                lineage_migration_audit_dir=str(audit.output_dir),
            ),
        )
        summary_name = (
            "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv"
        )
        checks_name = (
            "provider_market_data_imbalance_broker_rehearsal_certificate_checks.csv"
        )
        config_name = (
            "provider_market_data_imbalance_broker_rehearsal_certificate.json"
        )
        runbook_name = (
            "provider_market_data_imbalance_broker_rehearsal_certificate_runbook.md"
        )
        run_type = CERTIFICATE_RUN_TYPE

    summary = pd.read_csv(output / summary_name).iloc[0]
    checks = pd.read_csv(output / checks_name)
    config_payload = json.loads(
        (output / config_name).read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    audit_payload = (
        config_payload["payload"]["lineage_migration_audit"]
        if stage == "certificate"
        else config_payload["lineage_migration_audit"]
    )

    assert bool(summary["lineage_migration_audit_provided"])
    assert bool(summary["lineage_migration_audit_ready"])
    assert bool(summary["lineage_migration_audit_manifest_current"])
    assert bool(summary["lineage_migration_audit_policy_ready"])
    assert bool(summary["lineage_migration_audit_source_covered"])
    assert summary["lineage_migration_audit_source_status"] == (
        "covered_by_strict"
    )
    audit_check = checks.loc[
        checks["check"] == "lineage_migration_audit_ready"
    ].iloc[0]
    assert bool(audit_check["passed"])
    assert audit_payload["ready"] is True
    assert manifest["extra"]["lineage_migration_audit"]["ready"] is True
    assert {
        "lineage_migration_audit",
        "lineage_migration_audit_manifest",
        "lineage_migration_audit_dependencies",
    }.issubset(manifest["inputs"])
    assert "Lineage migration audit: ready" in (
        output / runbook_name
    ).read_text(encoding="utf-8")
    assert verify_experiment_manifest(
        output / "manifest.json",
        expected_run_type=run_type,
        require_input_fingerprints=True,
    ).passed
    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert bool(catalog["summary_lineage_migration_audit_ready"])
    assert bool(catalog["summary_lineage_migration_audit_source_covered"])


def test_lineage_audit_usage_review_accepts_strict_archive_and_catalogs_report(
    tmp_path,
):
    chain = _write_provider_chain(tmp_path / "strict_archive", strict=True)
    output = tmp_path / "strict_usage_review"

    report = write_provider_broker_lineage_audit_usage_review(
        [chain["root"]],
        output,
    )

    assert report.ready
    assert len(report.inventory) == 3
    assert set(report.inventory["usage_status"]) == {"strict_ready"}
    assert report.action_queue.empty
    assert int(report.summary.iloc[0]["strict_ready_bundles"]) == 3
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert verify_experiment_manifest(
        output / "manifest.json",
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_audit_usage_review"
        ),
        require_input_fingerprints=True,
    ).passed
    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert bool(catalog["summary_status"])
    assert int(catalog["summary_strict_ready_bundles"]) == 3


def test_lineage_audit_usage_review_blocks_unaudited_legacy_and_cli_exits(
    tmp_path,
):
    chain = _write_provider_chain(tmp_path / "legacy_archive", strict=False)
    reserved_strict_ack = chain["ack"].with_name(f"{chain['ack'].name}_strict")
    reserved_strict_ack.mkdir()
    output = tmp_path / "legacy_usage_review"

    report = write_provider_broker_lineage_audit_usage_review(
        [chain["root"]],
        output,
    )

    assert not report.ready
    assert set(report.inventory["usage_status"]) == {"unaudited_legacy"}
    assert int(report.summary.iloc[0]["unaudited_legacy_bundles"]) == 3
    assert len(report.action_queue) == 3
    assert list(report.action_queue["bundle_type"]) == [
        "provider_ack",
        "provider_roundtrip",
        "rehearsal_certificate",
    ]
    assert set(report.action_queue["queue_status"]) == {"ready"}
    assert int(report.summary.iloc[0]["ready_action_count"]) == 3
    assert int(report.summary.iloc[0]["blocked_action_count"]) == 0
    commands = dict(
        zip(
            report.action_queue["bundle_type"],
            report.action_queue["command"],
        )
    )
    assert "--require-send-packet" in commands["provider_ack"]
    assert "01_provider_ack_strict_rebuilt" in commands["provider_ack"]
    assert "--allow-rejections" in commands["provider_ack"]
    assert "--max-unmatched-acks 2" in commands["provider_ack"]
    assert "--require-ack-lineage" in commands["provider_roundtrip"]
    assert "01_provider_ack_strict_rebuilt" in commands["provider_roundtrip"]
    assert "--target-mode shadow" in commands["provider_roundtrip"]
    assert "--require-ack-lineage" in commands["rehearsal_certificate"]
    assert "02_provider_roundtrip_strict" in commands["rehearsal_certificate"]
    assert "--max-manifests 96" in commands["rehearsal_certificate"]
    assert not chain["ack"].with_name(
        f"{chain['ack'].name}_strict_rebuilt"
    ).exists()
    assert (
        main(
            [
                "review-provider-market-data-imbalance-broker-lineage-audit-usage",
                "--roots",
                str(chain["ack"]),
                "--out",
                str(tmp_path / "legacy_usage_cli"),
                "--no-recursive",
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_lineage_audit_usage_review_accepts_current_audited_legacy_proofs(
    tmp_path,
):
    legacy, _, outputs = _write_audited_legacy_provider_outputs(tmp_path)
    output = tmp_path / "audited_legacy_usage_review"

    report = write_provider_broker_lineage_audit_usage_review(
        list(outputs.values()),
        output,
        config=None,
    )

    assert report.ready
    assert len(report.inventory) == 3
    assert set(report.inventory["usage_status"]) == {
        "audited_legacy_ready"
    }
    assert report.inventory["stored_evidence_consistent"].astype(bool).all()
    assert report.inventory["current_evidence_matches_stored"].astype(bool).all()
    assert int(report.summary.iloc[0]["audited_legacy_ready_bundles"]) == 3
    assert int(report.summary.iloc[0]["dependency_count"]) > 3
    assert report.action_queue.empty
    manifest_path = output / "manifest.json"
    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_audit_usage_review"
        ),
        require_input_fingerprints=True,
    ).passed

    (legacy["provider_send"] / "proof.txt").write_text(
        "changed after aggregate review\n",
        encoding="utf-8",
    )
    assert not verify_experiment_manifest(
        manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_audit_usage_review"
        ),
        require_input_fingerprints=True,
    ).passed


def test_lineage_audit_usage_review_detects_post_acceptance_drift(tmp_path):
    legacy, _, outputs = _write_audited_legacy_provider_outputs(tmp_path)
    (legacy["provider_send"] / "proof.txt").write_text(
        "changed after accepted legacy proofs\n",
        encoding="utf-8",
    )

    report = write_provider_broker_lineage_audit_usage_review(
        list(outputs.values()),
        tmp_path / "drifted_usage_review",
    )

    assert not report.ready
    assert set(report.inventory["usage_status"]) == {
        "audited_legacy_drifted"
    }
    assert int(report.summary.iloc[0]["drifted_audit_bundles"]) == 3
    assert len(report.action_queue) == 3
    assert set(report.action_queue["queue_status"]) == {"ready"}
    assert report.action_queue["command"].astype(str).str.len().gt(0).all()


def test_lineage_audit_usage_review_detects_stored_evidence_disagreement(
    tmp_path,
):
    _, _, outputs = _write_audited_legacy_provider_outputs(tmp_path)
    bundle = outputs["ack"]
    summary_path = (
        bundle
        / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    )
    summary = pd.read_csv(summary_path)
    summary.loc[0, "lineage_migration_audit_manifest_sha256"] = "0" * 64
    summary.to_csv(summary_path, index=False)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        if artifact["path"] == summary_path.name:
            artifact["size_bytes"] = summary_path.stat().st_size
            artifact["sha256"] = file_sha256(summary_path)
    _write_json(manifest_path, manifest)
    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=ACK_RUN_TYPE,
        require_input_fingerprints=True,
    ).passed

    report = write_provider_broker_lineage_audit_usage_review(
        [bundle],
        tmp_path / "inconsistent_usage_review",
    )

    row = report.inventory.iloc[0]
    assert not report.ready
    assert row["usage_status"] == "audited_legacy_drifted"
    assert not bool(row["stored_evidence_consistent"])
    assert not bool(row["current_evidence_matches_stored"])
    assert "disagrees" in row["reason"]
    assert bool(row["refresh_ready"])
    assert report.action_queue.iloc[0]["queue_status"] == "ready"


def test_lineage_audit_usage_refresh_blocks_artifact_drift(tmp_path):
    _, _, outputs = _write_audited_legacy_provider_outputs(tmp_path)
    bundle = outputs["ack"]
    manifest_path = bundle / "manifest.json"
    original_manifest = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(original_manifest)
    manifest["inputs"] = {}
    _write_json(manifest_path, manifest)

    missing_inputs = write_provider_broker_lineage_audit_usage_review(
        [bundle],
        tmp_path / "missing_inputs_usage_review",
    )

    missing_inputs_row = missing_inputs.inventory.iloc[0]
    missing_inputs_action = missing_inputs.action_queue.iloc[0]
    assert not bool(missing_inputs_row["refresh_ready"])
    assert "not limited to input drift" in missing_inputs_row["refresh_reason"]
    assert missing_inputs_action["queue_status"] == "blocked"
    assert missing_inputs_action["command"] == ""

    manifest_path.write_text(original_manifest, encoding="utf-8")
    summary_path = (
        bundle
        / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv"
    )
    summary_path.write_text("passed\nfalse\n", encoding="utf-8")

    report = write_provider_broker_lineage_audit_usage_review(
        [bundle],
        tmp_path / "artifact_drift_usage_review",
    )

    row = report.inventory.iloc[0]
    action = report.action_queue.iloc[0]
    assert not report.ready
    assert row["usage_status"] == "audited_legacy_drifted"
    assert not bool(row["refresh_ready"])
    assert "artifacts" in row["refresh_reason"]
    assert action["queue_status"] == "blocked"
    assert action["command"] == ""
    assert int(report.summary.iloc[0]["blocked_action_count"]) == 1


def test_lineage_refresh_convergence_exposes_missing_output_commands(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )

    report = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    assert not report.ready
    assert len(report.inventory) == 3
    assert set(report.inventory["convergence_status"]) == {"output_missing"}
    assert int(report.summary.iloc[0]["missing_output_count"]) == 3
    assert int(report.summary.iloc[0]["unresolved_action_count"]) == 3
    assert set(report.action_queue["queue_status"]) == {"ready"}
    assert report.action_queue["command"].astype(str).str.len().gt(0).all()
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert verify_experiment_manifest(
        report.output_dir / "manifest.json",
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_refresh_convergence"
        ),
        require_input_fingerprints=True,
    ).passed
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-broker-lineage-refresh",
                "--audit-usage",
                str(usage.output_dir),
                "--out",
                str(tmp_path / "convergence_cli"),
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_lineage_refresh_convergence_accepts_noop_strict_review(tmp_path):
    strict = _write_provider_chain(tmp_path / "strict_archive", strict=True)
    usage = write_provider_broker_lineage_audit_usage_review(
        [strict["root"]],
        tmp_path / "usage_review",
    )

    report = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    assert usage.ready
    assert report.ready
    assert report.inventory.empty
    assert report.action_queue.empty
    assert not bool(report.summary.iloc[0]["refresh_required"])
    assert report.summary.iloc[0]["recommendation"] == "no_refresh_required"


def test_lineage_refresh_convergence_accepts_exact_strict_siblings_and_catalogs(
    tmp_path,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    strict = _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )

    report = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    assert report.ready
    assert len(report.inventory) == 3
    assert set(report.inventory["convergence_status"]) == {"converged"}
    for field in (
        "plan_record_consistent",
        "output_manifest_current",
        "output_bundle_passed",
        "output_strict_lineage_required",
        "output_strict_lineage_current",
        "output_source_manifest_current",
        "output_non_authorizing",
        "policy_matches",
        "evidence_identity_matches",
        "command_output_matches",
        "command_source_matches",
        "command_requires_strict",
        "command_omits_legacy_audit",
    ):
        assert report.inventory[field].astype(bool).all()
    assert not report.inventory["output_audit_provided"].astype(bool).any()
    assert report.action_queue.empty
    manifest_path = report.output_dir / "manifest.json"
    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_refresh_convergence"
        ),
        require_input_fingerprints=True,
    ).passed
    catalog = catalog_experiment_runs([report.output_dir]).catalog.iloc[0]
    assert bool(catalog["summary_status"])
    assert int(catalog["summary_converged_action_count"]) == 3
    assert (
        main(
            [
                "verify-provider-market-data-imbalance-broker-lineage-refresh",
                "--audit-usage",
                str(usage.output_dir),
                "--out",
                str(tmp_path / "convergence_cli"),
                "--fail-on-breach",
                "--fail-on-blocked-actions",
                "--fail-on-actions",
            ]
        )
        == 0
    )

    (strict["ack"] / "proof_after_convergence.txt").write_text(
        "drift\n",
        encoding="utf-8",
    )
    assert not verify_experiment_manifest(
        manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_refresh_convergence"
        ),
        require_input_fingerprints=True,
    ).passed


def test_lineage_refresh_convergence_rejects_policy_mismatched_output(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
        ack_parameter_overrides={"allow_rejections": False},
    )

    report = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    assert not report.ready
    ack = report.inventory.loc[
        report.inventory["bundle_type"] == "provider_ack"
    ].iloc[0]
    assert ack["convergence_status"] == "output_invalid"
    assert not bool(ack["policy_matches"])
    action = report.action_queue.loc[
        report.action_queue["bundle_type"] == "provider_ack"
    ].iloc[0]
    assert action["queue_status"] == "blocked"
    assert action["command"] == ""
    assert action["action"] == "rerun_audit_usage_review_for_fresh_target"


def test_lineage_refresh_convergence_rejects_drifted_usage_review(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    actions_path = (
        usage.output_dir
        / "provider_broker_lineage_audit_usage_action_queue.csv"
    )
    actions = pd.read_csv(actions_path)
    actions.loc[0, "command"] = "python -m hft_cli tampered"
    actions.to_csv(actions_path, index=False)

    report = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    assert not report.ready
    assert not bool(report.summary.iloc[0]["audit_usage_review_current"])
    assert len(report.action_queue) == 1
    action = report.action_queue.iloc[0]
    assert action["queue_status"] == "blocked"
    assert action["convergence_status"] == "source_review_invalid"
    assert action["command"] == ""


def test_active_lineage_index_retires_exact_converged_originals(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    strict = _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    convergence = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    report = write_provider_broker_active_lineage_index(
        convergence.output_dir,
        tmp_path / "active_lineage",
    )

    assert report.ready
    assert len(report.inventory) == 6
    assert int(report.summary.iloc[0]["lineage_pair_count"]) == 3
    assert int(report.summary.iloc[0]["selectable_bundle_count"]) == 3
    assert int(report.summary.iloc[0]["retained_only_bundle_count"]) == 3
    assert set(report.inventory["selection_status"]) == {
        "selectable",
        "retained_only",
    }
    for _, pair in report.inventory.groupby("lineage_pair_id"):
        assert set(pair["lineage_role"]) == {
            "active_strict",
            "legacy_original",
        }
        assert int(pair["catalog_selectable"].astype(bool).sum()) == 1
        assert int(pair["retained_only"].astype(bool).sum()) == 1
        assert pair["pair_valid"].astype(bool).all()
    expected = {
        "provider_ack": strict["ack"],
        "provider_roundtrip": strict["roundtrip"],
        "rehearsal_certificate": strict["certificate"],
    }
    originals = {
        "provider_ack": legacy["ack"],
        "provider_roundtrip": legacy["roundtrip"],
        "rehearsal_certificate": legacy["certificate"],
    }
    for bundle_type, path in expected.items():
        assert resolve_provider_broker_active_lineage_bundle(
            report.output_dir,
            bundle_type=bundle_type,
            original_bundle_path=originals[bundle_type],
        ) == path.resolve()
    verification = verify_provider_broker_active_lineage_index(
        report.output_dir
    )
    assert verification.ready
    assert verification.manifest_current
    assert verification.source_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert verify_experiment_manifest(
        report.output_dir / "manifest.json",
        expected_run_type=(
            "provider_market_data_imbalance_broker_active_lineage_index"
        ),
        require_input_fingerprints=True,
    ).passed
    index_catalog = catalog_experiment_runs([report.output_dir]).catalog.iloc[0]
    assert index_catalog["run_type"] == (
        "provider_market_data_imbalance_broker_active_lineage_index"
    )
    assert bool(index_catalog["summary_status"])
    assert not bool(index_catalog["summary_authorizes_submission"])
    catalog = catalog_experiment_runs(
        [legacy["root"]],
        provider_broker_active_lineage_index=report.output_dir,
    )
    provider_rows = catalog.catalog.loc[
        catalog.catalog["provider_lineage_bundle_type"].astype(str).ne("")
    ]
    assert len(provider_rows) == 6
    assert set(provider_rows["provider_lineage_selection_status"]) == {
        "selectable",
        "retained_only",
    }
    selectable = provider_rows.loc[
        provider_rows["provider_lineage_selection_status"] == "selectable"
    ]
    retained = provider_rows.loc[
        provider_rows["provider_lineage_selection_status"] == "retained_only"
    ]
    assert selectable["provider_lineage_selection_eligible"].astype(bool).all()
    assert not retained[
        "provider_lineage_selection_eligible"
    ].astype(bool).any()
    assert int(catalog.summary.iloc[0]["provider_lineage_selectable_runs"]) == 3
    assert int(
        catalog.summary.iloc[0]["provider_lineage_retained_only_runs"]
    ) == 3
    assert int(catalog.summary.iloc[0]["provider_lineage_unindexed_runs"]) == 0
    unindexed_ack = _write_component(
        tmp_path / "unindexed_provider_ack",
        ACK_RUN_TYPE,
    )
    unindexed_catalog = catalog_experiment_runs(
        [unindexed_ack],
        provider_broker_active_lineage_index=report.output_dir,
    )
    unindexed_row = unindexed_catalog.catalog.iloc[0]
    assert unindexed_row["provider_lineage_selection_status"] == "unindexed"
    assert not bool(unindexed_row["provider_lineage_selection_eligible"])
    assert int(
        unindexed_catalog.summary.iloc[0]["provider_lineage_unindexed_runs"]
    ) == 1
    no_index_catalog = catalog_experiment_runs([strict["ack"]])
    no_index_row = no_index_catalog.catalog.iloc[0]
    assert no_index_row["provider_lineage_selection_status"] == (
        "index_not_provided"
    )
    assert not bool(no_index_row["provider_lineage_selection_eligible"])
    assert int(
        no_index_catalog.summary.iloc[0][
            "provider_lineage_selection_blocked_runs"
        ]
    ) == 1
    assert (
        main(
            [
                "index-provider-market-data-imbalance-broker-active-lineage",
                "--convergence",
                str(convergence.output_dir),
                "--out",
                str(tmp_path / "active_lineage_cli"),
                "--fail-on-breach",
                "--fail-on-blocked-actions",
                "--fail-on-actions",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "catalog-runs",
                "--roots",
                str(strict["ack"]),
                str(strict["roundtrip"]),
                str(strict["certificate"]),
                "--out",
                str(tmp_path / "strict_catalog"),
                "--provider-broker-active-lineage-index",
                str(report.output_dir),
                "--fail-on-provider-lineage-selection-blocks",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "catalog-runs",
                "--roots",
                str(legacy["ack"]),
                "--out",
                str(tmp_path / "legacy_catalog"),
                "--provider-broker-active-lineage-index",
                str(report.output_dir),
                "--fail-on-provider-lineage-selection-blocks",
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "catalog-runs",
                "--roots",
                str(strict["ack"]),
                "--out",
                str(tmp_path / "missing_index_catalog"),
                "--fail-on-provider-lineage-selection-blocks",
            ]
        )
        == 2
    )


def test_active_lineage_index_accepts_noop_strict_convergence(tmp_path):
    strict = _write_provider_chain(tmp_path / "strict_archive", strict=True)
    usage = write_provider_broker_lineage_audit_usage_review(
        [strict["root"]],
        tmp_path / "usage_review",
    )
    convergence = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    report = write_provider_broker_active_lineage_index(
        convergence.output_dir,
        tmp_path / "active_lineage",
    )

    assert report.ready
    assert report.inventory.empty
    assert report.action_queue.empty
    assert report.summary.iloc[0]["recommendation"] == (
        "no_retirements_required"
    )
    assert verify_provider_broker_active_lineage_index(
        report.output_dir
    ).ready
    with pytest.raises(ValueError, match="exactly one selectable"):
        resolve_provider_broker_active_lineage_bundle(
            report.output_dir,
            bundle_type="provider_ack",
        )


def test_active_lineage_index_blocks_before_refresh_convergence(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    convergence = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )

    report = write_provider_broker_active_lineage_index(
        convergence.output_dir,
        tmp_path / "active_lineage",
    )

    assert not report.ready
    assert report.inventory.empty
    assert len(report.action_queue) == 1
    action = report.action_queue.iloc[0]
    assert action["queue_status"] == "blocked"
    assert action["action"] == "regenerate_current_refresh_convergence"
    assert action["command"] == ""
    verification = verify_provider_broker_active_lineage_index(
        report.output_dir
    )
    assert not verification.ready
    assert verification.artifacts_consistent
    assert (
        main(
            [
                "index-provider-market-data-imbalance-broker-active-lineage",
                "--convergence",
                str(convergence.output_dir),
                "--out",
                str(tmp_path / "active_lineage_cli"),
                "--fail-on-breach",
            ]
        )
        == 2
    )
    with pytest.raises(ValueError, match="index is not trusted"):
        resolve_provider_broker_active_lineage_bundle(
            report.output_dir,
            bundle_type="provider_ack",
        )


def test_active_lineage_index_invalidates_after_strict_bundle_drift(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    strict = _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    convergence = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )
    report = write_provider_broker_active_lineage_index(
        convergence.output_dir,
        tmp_path / "active_lineage",
    )

    (strict["ack"] / "post_index_drift.txt").write_text(
        "drift\n",
        encoding="utf-8",
    )

    verification = verify_provider_broker_active_lineage_index(
        report.output_dir
    )
    assert not verification.ready
    assert not verification.manifest_current
    assert not verification.source_current
    with pytest.raises(ValueError, match="index is not trusted"):
        catalog_experiment_runs(
            [legacy["root"]],
            provider_broker_active_lineage_index=report.output_dir,
        )
    with pytest.raises(ValueError, match="index is not trusted"):
        resolve_provider_broker_active_lineage_bundle(
            report.output_dir,
            bundle_type="provider_ack",
            original_bundle_path=legacy["ack"],
        )


def test_active_lineage_index_rejects_edited_retirement_record(tmp_path):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [legacy["root"]],
        tmp_path / "usage_review",
    )
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    convergence = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )
    report = write_provider_broker_active_lineage_index(
        convergence.output_dir,
        tmp_path / "active_lineage",
    )
    index_path = report.output_dir / "provider_broker_active_lineage_index.csv"
    index = pd.read_csv(index_path)
    original = index["lineage_role"].astype(str).eq("legacy_original")
    index.loc[original, "selection_status"] = "selectable"
    index.loc[original, "catalog_selectable"] = True
    index.loc[original, "retained_only"] = False
    index.to_csv(index_path, index=False)

    verification = verify_provider_broker_active_lineage_index(
        report.output_dir
    )

    assert not verification.ready
    assert not verification.manifest_current
    assert not verification.artifacts_consistent
    with pytest.raises(ValueError, match="index is not trusted"):
        resolve_provider_broker_active_lineage_bundle(
            report.output_dir,
            bundle_type="provider_ack",
            original_bundle_path=legacy["ack"],
        )


def test_active_lineage_resolver_requires_original_when_type_is_ambiguous(
    tmp_path,
):
    first = _write_provider_chain(tmp_path / "first_archive", strict=False)
    second = _write_provider_chain(tmp_path / "second_archive", strict=False)
    usage = write_provider_broker_lineage_audit_usage_review(
        [first["root"], second["root"]],
        tmp_path / "usage_review",
    )
    first_strict = _write_provider_chain(
        first["root"],
        strict=True,
        suffix="_strict",
        shared=first,
    )
    _write_provider_chain(
        second["root"],
        strict=True,
        suffix="_strict",
        shared=second,
    )
    convergence = write_provider_broker_lineage_refresh_convergence(
        usage.output_dir,
        tmp_path / "convergence",
    )
    report = write_provider_broker_active_lineage_index(
        convergence.output_dir,
        tmp_path / "active_lineage",
    )

    assert report.ready
    assert int(report.summary.iloc[0]["lineage_pair_count"]) == 6
    with pytest.raises(ValueError, match="found 2"):
        resolve_provider_broker_active_lineage_bundle(
            report.output_dir,
            bundle_type="provider_ack",
        )
    assert resolve_provider_broker_active_lineage_bundle(
        report.output_dir,
        bundle_type="provider_ack",
        original_bundle_path=first["ack"],
    ) == first_strict["ack"].resolve()


@pytest.mark.parametrize(
    ("source_role", "source_key"),
    [
        ("provider_send", "provider_send"),
        ("provider_ack", "ack"),
        ("provider_roundtrip", "roundtrip"),
    ],
)
def test_lineage_migration_audit_verifier_requires_exact_covered_source(
    tmp_path,
    source_role,
    source_key,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    report = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )

    verified = verify_provider_broker_lineage_migration_audit(
        report.output_dir,
        source_path=legacy[source_key],
        source_role=source_role,
    )
    unrelated = verify_provider_broker_lineage_migration_audit(
        report.output_dir,
        source_path=tmp_path / "unrelated_source",
        source_role=source_role,
    )

    assert verified.ready
    assert verified.manifest_current
    assert verified.policy_ready
    assert verified.source_covered
    assert verified.source_status == "covered_by_strict"
    assert len(verified.matched_inventory) == 1
    assert not unrelated.ready
    assert not unrelated.source_covered
    assert "legacy_source_covered" in unrelated.error


def test_lineage_migration_audit_manifest_seals_transitive_source_drift(
    tmp_path,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    report = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )
    manifest_path = report.output_dir / "manifest.json"

    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_migration_audit"
        ),
        require_input_fingerprints=True,
    ).passed

    (legacy["provider_send"] / "proof.txt").write_text(
        "changed after migration audit\n",
        encoding="utf-8",
    )

    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=(
            "provider_market_data_imbalance_broker_lineage_migration_audit"
        ),
        require_input_fingerprints=True,
    )
    verified = verify_provider_broker_lineage_migration_audit(
        report.output_dir,
        source_path=legacy["provider_send"],
        source_role="provider_send",
    )
    assert not integrity.passed
    assert integrity.error == "input_drift"
    assert not verified.ready
    assert not verified.manifest_current
    assert "audit_manifest_current" in verified.error


def test_lineage_migration_audit_verifier_rejects_relaxed_unmigrated_policy(
    tmp_path,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    report = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
        config=ProviderBrokerLineageMigrationConfig(
            max_blocked_bundles=0,
            min_strict_ready_coverage=0.0,
        ),
    )

    assert report.ready
    verified = verify_provider_broker_lineage_migration_audit(
        report.output_dir,
        source_path=legacy["provider_send"],
        source_role="provider_send",
    )
    evidence = provider_broker_lineage_migration_audit_evidence(
        report.output_dir,
        source_path=legacy["provider_send"],
        source_role="provider_send",
    )
    assert not verified.ready
    assert not verified.policy_ready
    assert not verified.source_covered
    assert {"audit_policy_ready", "legacy_source_covered"}.issubset(
        set(
            verified.checks.loc[
                ~verified.checks["passed"].astype(bool),
                "check",
            ]
        )
    )
    assert evidence["provided"]
    assert not evidence["ready"]
    assert not provider_broker_lineage_migration_audit_check(evidence)[
        "passed"
    ]


def test_lineage_migration_audit_rejects_policy_mismatched_replacement(
    tmp_path,
):
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
        ack_parameter_overrides={"allow_rejections": False},
    )

    report = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )

    assert not report.ready
    legacy_rows = report.inventory.loc[
        ~report.inventory["bundle_path"].astype(str).str.endswith("_strict")
    ]
    assert set(legacy_rows["migration_status"]) == {"regenerate_strict"}
    legacy_ack = legacy_rows.loc[
        legacy_rows["bundle_type"] == "provider_ack"
    ].iloc[0]
    assert bool(legacy_ack["strict_replacement_current"])
    assert not bool(legacy_ack["strict_replacement_matches_policy"])
    downstream = legacy_rows.loc[
        legacy_rows["bundle_type"] != "provider_ack"
    ]
    assert not downstream[
        "strict_replacement_dependency_covered"
    ].astype(bool).any()
    assert len(report.action_queue) == 3
    assert "_strict_rebuilt" in report.action_queue.iloc[0]["command"]


def test_lineage_migration_cli_exit_policy_and_output_collision(tmp_path):
    legacy = _write_provider_chain(tmp_path / "legacy", strict=False)
    strict = _write_provider_chain(tmp_path / "strict", strict=True)

    assert (
        main(
            [
                "audit-provider-market-data-imbalance-broker-lineage-migration",
                "--roots",
                str(legacy["root"]),
                "--out",
                str(legacy["root"] / "cli_audit"),
                "--fail-on-breach",
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "audit-provider-market-data-imbalance-broker-lineage-migration",
                "--roots",
                str(strict["ack"]),
                "--out",
                str(strict["root"] / "cli_audit"),
                "--no-recursive",
                "--fail-on-breach",
                "--fail-on-actions",
            ]
        )
        == 0
    )

    with pytest.raises(
        ValueError,
        match="inside an audited provider bundle",
    ):
        write_provider_broker_lineage_migration_audit(
            [strict["ack"]],
            strict["ack"] / "audit",
        )


def _write_audited_legacy_provider_outputs(
    tmp_path: Path,
) -> tuple[dict[str, Path], Path, dict[str, Path]]:
    legacy = _write_provider_chain(tmp_path / "archive", strict=False)
    _write_provider_chain(
        legacy["root"],
        strict=True,
        suffix="_strict",
        shared=legacy,
    )
    audit = write_provider_broker_lineage_migration_audit(
        [legacy["root"]],
        legacy["root"] / "migration_audit",
    )
    outputs = {
        "ack": tmp_path / "accepted_legacy_ack",
        "roundtrip": tmp_path / "accepted_legacy_roundtrip",
        "certificate": tmp_path / "accepted_legacy_certificate",
    }
    write_provider_market_data_imbalance_broker_dispatch_ack(
        legacy["provider_send"],
        legacy["acks"],
        outputs["ack"],
        config=ProviderMarketDataImbalanceBrokerDispatchAckConfig(
            require_send_packet=False,
            lineage_migration_audit_dir=str(audit.output_dir),
        ),
    )
    write_provider_market_data_imbalance_broker_dispatch_roundtrip(
        legacy["ack"],
        outputs["roundtrip"],
        config=ProviderMarketDataImbalanceBrokerDispatchRoundTripConfig(
            require_ack_lineage=False,
            lineage_migration_audit_dir=str(audit.output_dir),
        ),
    )
    write_provider_market_data_imbalance_broker_rehearsal_certificate(
        legacy["roundtrip"],
        outputs["certificate"],
        config=ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig(
            require_clean_recorded_git=False,
            require_ack_lineage=False,
            lineage_migration_audit_dir=str(audit.output_dir),
        ),
    )
    return legacy, audit.output_dir, outputs


def _write_provider_chain(
    root: Path,
    *,
    strict: bool,
    suffix: str = "",
    shared: dict[str, Path] | None = None,
    ack_parameter_overrides: dict | None = None,
) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    if shared is None:
        components = root / "components"
        provider_send = _write_component(
            components / "provider_send",
            "provider_market_data_imbalance_broker_dispatch_send",
        )
        generic_ack = _write_component(
            components / "generic_ack",
            "broker_dispatch_ack_reconciliation",
        )
        broker_dispatch = _write_component(
            components / "broker_dispatch",
            "broker_dispatch_plan",
        )
        broker_send = _write_component(
            components / "broker_send",
            "broker_dispatch_send_packet",
        )
        acks = components / "broker_acks.csv"
        acks.write_text("order_id,status\n1,ACKED\n", encoding="utf-8")
    else:
        provider_send = shared["provider_send"]
        generic_ack = shared["generic_ack"]
        broker_dispatch = shared["broker_dispatch"]
        broker_send = shared["broker_send"]
        acks = shared["acks"]
    lineage = _lineage_record(generic_ack, strict=strict)

    ack = root / f"01_provider_ack{suffix}"
    ack.mkdir()
    ack_parameters = {
        "require_provider_broker_dispatch_send_ready": True,
        "require_broker_dispatch_ack_passed": True,
        "use_provider_broker_dispatch_send_inputs": True,
        "require_dispatch_ready": True,
        "require_all_acked": True,
        "require_route_readiness": False,
        "require_dispatch_roundtrip": False,
        "require_send_packet": strict,
        "allow_rejections": True,
        "max_duplicate_ack_orders": 0,
        "max_unmatched_acks": 2,
    }
    ack_parameters.update(ack_parameter_overrides or {})
    pd.DataFrame(
        [
            {
                "passed": True,
                "provider_broker_dispatch_send_dir": str(provider_send),
                "broker_dispatch_dir": str(broker_dispatch),
                "broker_dispatch_send_dir": str(broker_send),
                "acks_path": str(acks),
            }
        ]
    ).to_csv(
        ack / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
        index=False,
    )
    _write_json(
        ack / "provider_market_data_imbalance_broker_dispatch_ack_config.json",
        {
            "parameters": ack_parameters,
            "broker_dispatch_ack": {"summary": lineage},
        },
    )
    write_experiment_manifest(
        ack,
        run_type=ACK_RUN_TYPE,
        parameters={"config": ack_parameters},
        inputs={
            "provider_send": provider_send,
            "broker_dispatch": broker_dispatch,
            "broker_send": broker_send,
            "generic_ack": generic_ack,
            "acks": acks,
        },
        extra={"passed": True, "authorizes_submission": False},
    )

    roundtrip = root / f"02_provider_roundtrip{suffix}"
    roundtrip.mkdir()
    roundtrip_parameters = {
        "require_provider_broker_dispatch_ack_passed": True,
        "require_broker_dispatch_roundtrip_passed": True,
        "use_provider_broker_dispatch_ack_inputs": True,
        "target_mode": "shadow",
        "require_dispatch_ready": True,
        "require_send_ready": True,
        "require_ack_passed": True,
        "require_identity_match": True,
        "require_submission_disabled": True,
        "require_all_requests_acked": True,
        "require_route_readiness": False,
        "require_dispatch_roundtrip": False,
        "require_ack_lineage": strict,
        "allow_rejections": False,
        "max_duplicate_ack_orders": 0,
        "max_unmatched_acks": 0,
        "max_missing_request_acks": 0,
        "max_total_failed_component_checks": 0,
    }
    pd.DataFrame(
        [
            {
                "passed": True,
                "provider_broker_dispatch_ack_dir": str(ack),
                "broker_dispatch_dir": str(broker_dispatch),
                "broker_dispatch_send_dir": str(broker_send),
                "broker_dispatch_ack_dir": str(generic_ack),
                **lineage,
            }
        ]
    ).to_csv(
        roundtrip
        / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    _write_json(
        roundtrip
        / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json",
        {
            "parameters": roundtrip_parameters,
            "broker_dispatch_ack_lineage": lineage,
        },
    )
    write_experiment_manifest(
        roundtrip,
        run_type=ROUNDTRIP_RUN_TYPE,
        parameters={"config": roundtrip_parameters},
        inputs={"provider_ack": ack},
        extra={
            "passed": True,
            "authorizes_submission": False,
            "broker_dispatch_ack_lineage": lineage,
        },
    )

    certificate = root / f"03_rehearsal_certificate{suffix}"
    certificate.mkdir()
    certificate_parameters = {
        "allowed_target_modes": ["paper", "shadow", "live_dryrun"],
        "require_clean_recorded_git": False,
        "require_sealed_provider_receipts": False,
        "require_ack_lineage": strict,
        "max_manifest_count": 96,
    }
    pd.DataFrame(
        [{"ready": True, "source_roundtrip_dir": str(roundtrip)}]
    ).to_csv(
        certificate
        / "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
        index=False,
    )
    _write_json(
        certificate
        / "provider_market_data_imbalance_broker_rehearsal_certificate.json",
        {
            "authorizes_submission": False,
            "payload": {
                "source": {"path": str(roundtrip)},
                "broker_dispatch_ack_lineage": lineage,
            },
        },
    )
    write_experiment_manifest(
        certificate,
        run_type=CERTIFICATE_RUN_TYPE,
        parameters={"config": certificate_parameters},
        inputs={"provider_roundtrip": roundtrip},
        extra={"ready": True, "authorizes_submission": False},
    )
    return {
        "root": root,
        "provider_send": provider_send,
        "generic_ack": generic_ack,
        "broker_dispatch": broker_dispatch,
        "broker_send": broker_send,
        "acks": acks,
        "ack": ack,
        "roundtrip": roundtrip,
        "certificate": certificate,
    }


def _write_component(path: Path, run_type: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    proof = path / "proof.txt"
    proof.write_text(f"{run_type}\n", encoding="utf-8")
    write_experiment_manifest(
        path,
        run_type=run_type,
        inputs={"proof": proof},
        extra={"passed": True, "authorizes_submission": False},
    )
    return path


def _lineage_record(generic_ack: Path, *, strict: bool) -> dict:
    record = broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage(required=strict)
    )
    if not strict:
        return record
    for field, value in tuple(record.items()):
        if isinstance(value, bool):
            record[field] = True
    manifest = generic_ack / "manifest.json"
    record.update(
        {
            "broker_dispatch_ack_manifest_run_type": (
                "broker_dispatch_ack_reconciliation"
            ),
            "broker_dispatch_ack_manifest_path": str(manifest),
            "broker_dispatch_ack_manifest_sha256": file_sha256(manifest),
            "broker_dispatch_ack_manifest_error": "",
            "broker_dispatch_ack_lineage_contract_error": "",
        }
    )
    return record


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
