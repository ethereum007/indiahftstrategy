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
