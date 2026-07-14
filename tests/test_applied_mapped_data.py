import json
from pathlib import Path

import pandas as pd
import pytest

from adapters.applied_mapped_data import (
    AppliedMappedDataConfig,
    verify_applied_mapped_data_normalization,
    write_applied_mapped_data_normalization,
)
from adapters.vendor_mapping_application import write_vendor_mapping_application
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.data_readiness import (
    DataReadinessThresholds,
    evaluate_data_readiness,
    write_data_readiness_report,
)
from reports.manifest import write_experiment_manifest
from tests.test_data_readiness import reviewed_mapped_data_summary
from tests.test_vendor_mapping_application import (
    _mapping_scope,
    _normal_ticks,
    _opaque_ticks,
    _target_intake,
)


def test_applied_normalization_is_ready_write_once_cli_catalog_and_readiness(tmp_path):
    application_dir, intake_dir, source_path = _mapping_application(
        tmp_path,
        "ready",
    )
    normalization_dir = tmp_path / "ready_normalization"
    config = AppliedMappedDataConfig(timestamp_unit="datetime")

    report = write_applied_mapped_data_normalization(
        application_dir,
        output_dir=normalization_dir,
        config=config,
    )
    verification = verify_applied_mapped_data_normalization(normalization_dir)
    receipt = json.loads(
        (normalization_dir / "mapped_data_receipt.json").read_text(
            encoding="utf-8"
        )
    )

    assert report.ready
    assert len(report.data) == 1
    assert verification.verified
    assert verification.ready
    assert not verification.blocked
    assert verification.manifest_current
    assert verification.mapping_application_current
    assert verification.source_current
    assert verification.applied_mapping_current
    assert verification.artifacts_consistent
    assert verification.target_bound
    assert verification.normalization_only
    assert verification.non_routing
    assert verification.source_path == source_path.resolve()
    assert receipt["contract_version"] == "target_applied_mapped_data_normalization/v1"
    assert receipt["mapping_application"]["verified"]
    assert not receipt["mapping_application"]["authorizes_normalization"]
    assert receipt["normalization"]["output_rows"] == 1
    assert receipt["safety"]["normalization_executed"]
    assert receipt["safety"]["target_application_bound"]
    assert not receipt["safety"]["authorizes_strategy_research"]
    assert not receipt["safety"]["authorizes_routing"]
    assert not receipt["safety"]["authorizes_submission"]

    readiness = write_data_readiness_report(
        output_dir=tmp_path / "readiness",
        vendor_intake_dir=intake_dir,
        mapped_data_dir=normalization_dir,
        thresholds=DataReadinessThresholds(
            require_vendor_intake=True,
            require_target_application_normalization=True,
            require_tick_diagnostics=False,
        ),
    )
    assert readiness.ready
    assert bool(
        readiness.summary.loc[0, "require_target_application_normalization"]
    )
    assert bool(readiness.summary.loc[0, "mapped_data_target_application_bound"])
    assert readiness.action_queue is not None
    assert readiness.action_queue.empty

    cli_readiness_dir = tmp_path / "readiness_cli"
    assert (
        main(
            [
                "review-data-readiness",
                "--out",
                str(cli_readiness_dir),
                "--vendor-intake",
                str(intake_dir),
                "--mapped-data",
                str(normalization_dir),
                "--require-vendor-intake",
                "--require-target-application-normalization",
                "--skip-tick-diagnostics",
                "--fail-on-breach",
            ]
        )
        == 0
    )

    catalog = catalog_experiment_runs([normalization_dir])
    catalog_row = catalog.catalog.iloc[0]
    assert bool(catalog_row["summary_status"])
    assert (
        catalog_row["applied_mapped_data_verification_status"]
        == "verified_ready"
    )
    assert bool(catalog_row["applied_mapped_data_verification_verified"])

    with pytest.raises(FileExistsError, match="already exists"):
        write_applied_mapped_data_normalization(
            application_dir,
            output_dir=normalization_dir,
            config=config,
        )

    cli_dir = tmp_path / "ready_normalization_cli"
    assert (
        main(
            [
                "normalize-applied-vendor-mapping",
                "--application",
                str(application_dir),
                "--out",
                str(cli_dir),
                "--timestamp-unit",
                "datetime",
                "--fail-on-breach",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-applied-vendor-mapping-normalization",
                "--normalization",
                str(cli_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )


def test_applied_normalization_unblocks_opaque_exact_header_intake(tmp_path):
    application_dir, intake_dir, _ = _mapping_application(
        tmp_path,
        "opaque",
        opaque=True,
    )
    intake_summary = pd.read_csv(intake_dir / "vendor_intake_summary.csv")
    assert not bool(intake_summary.loc[0, "ready"])

    report = write_applied_mapped_data_normalization(
        application_dir,
        output_dir=tmp_path / "opaque_normalization",
        config=AppliedMappedDataConfig(timestamp_unit="datetime"),
    )

    assert report.ready
    assert len(report.data) == 1
    assert report.data.loc[0, "bid"] == 100.0
    assert report.data.loc[0, "ask"] == 100.05
    assert verify_applied_mapped_data_normalization(report.output_dir).verified


def test_applied_normalization_preserves_verified_blocked_data_quality_state(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "blocked")
    target = _normal_ticks("2026-07-15")
    target.loc[0, "exchange_ts"] = "2026-07-15 08:00:00"
    intake_dir, _, _ = _target_intake(
        tmp_path,
        "blocked_target",
        frame=target,
    )
    application_dir = tmp_path / "blocked_application"
    normalization_dir = tmp_path / "blocked_normalization"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)

    report = write_applied_mapped_data_normalization(
        application_dir,
        output_dir=normalization_dir,
        config=AppliedMappedDataConfig(timestamp_unit="datetime"),
    )
    verification = verify_applied_mapped_data_normalization(normalization_dir)
    catalog = catalog_experiment_runs([normalization_dir])

    assert not report.ready
    assert report.data.empty
    assert not report.action_queue.empty
    assert verification.verified
    assert not verification.ready
    assert verification.blocked
    assert verification.artifacts_consistent
    assert (
        catalog.catalog.loc[0, "applied_mapped_data_verification_status"]
        == "verified_blocked"
    )
    assert not bool(catalog.catalog.loc[0, "summary_status"])


def test_applied_normalization_rejects_evidence_path_collision(tmp_path):
    application_dir, _, _ = _mapping_application(tmp_path, "collision")

    with pytest.raises(ValueError, match="mapping-application evidence"):
        write_applied_mapped_data_normalization(
            application_dir,
            output_dir=application_dir / "normalization",
            config=AppliedMappedDataConfig(timestamp_unit="datetime"),
        )


def test_applied_normalization_verifier_rejects_target_source_drift(tmp_path):
    application_dir, _, source_path = _mapping_application(tmp_path, "source_drift")
    normalization_dir = tmp_path / "source_drift_normalization"
    write_applied_mapped_data_normalization(
        application_dir,
        output_dir=normalization_dir,
        config=AppliedMappedDataConfig(timestamp_unit="datetime"),
    )

    source = pd.read_csv(source_path)
    source.loc[0, source.columns[1]] = 99.95
    source.to_csv(source_path, index=False)
    verification = verify_applied_mapped_data_normalization(normalization_dir)

    assert not verification.verified
    assert not verification.manifest_current
    assert not verification.mapping_application_current
    assert not verification.source_current
    assert verification.applied_mapping_current
    assert "stale" in verification.error
    assert (
        main(
            [
                "verify-applied-vendor-mapping-normalization",
                "--normalization",
                str(normalization_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_applied_normalization_verifier_rejects_upstream_scope_drift(tmp_path):
    application_dir, _, _ = _mapping_application(tmp_path, "scope_drift")
    normalization_dir = tmp_path / "scope_drift_normalization"
    write_applied_mapped_data_normalization(
        application_dir,
        output_dir=normalization_dir,
        config=AppliedMappedDataConfig(timestamp_unit="datetime"),
    )
    application_receipt = json.loads(
        (application_dir / "vendor_mapping_application_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    scope_dir = Path(application_receipt["scope_review"]["path"])
    scope_manifest = json.loads(
        (scope_dir / "manifest.json").read_text(encoding="utf-8")
    )
    decision_path = Path(scope_manifest["inputs"]["operator_decision"]["path"])
    decision = pd.read_csv(decision_path)
    decision.loc[0, "notes"] = "Changed after target-applied normalization."
    decision.to_csv(decision_path, index=False)

    verification = verify_applied_mapped_data_normalization(normalization_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert not verification.mapping_application_current
    assert verification.source_current
    assert verification.applied_mapping_current
    assert "stale" in verification.error


@pytest.mark.parametrize(
    ("artifact", "mutate"),
    [
        (
            "normalized_data.csv",
            lambda frame: frame.assign(bid=frame["bid"] - 0.25),
        ),
        (
            "mapped_data_summary.csv",
            lambda frame: frame.assign(authorizes_strategy_research=True),
        ),
    ],
)
def test_applied_normalization_rejects_remanifested_artifact_tamper(
    tmp_path,
    artifact,
    mutate,
):
    application_dir, _, source_path = _mapping_application(tmp_path, "tamper")
    normalization_dir = tmp_path / f"tamper_{Path(artifact).stem}"
    write_applied_mapped_data_normalization(
        application_dir,
        output_dir=normalization_dir,
        config=AppliedMappedDataConfig(timestamp_unit="datetime"),
    )

    artifact_path = normalization_dir / artifact
    mutate(pd.read_csv(artifact_path)).to_csv(artifact_path, index=False)
    manifest = json.loads(
        (normalization_dir / "manifest.json").read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        normalization_dir,
        run_type="target_applied_mapped_data_normalization",
        parameters=manifest["parameters"],
        inputs=_normalization_manifest_inputs(
            application_dir,
            source_path,
        ),
        extra=manifest["extra"],
    )

    verification = verify_applied_mapped_data_normalization(normalization_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.mapping_application_current
    assert verification.source_current
    assert verification.applied_mapping_current
    assert not verification.artifacts_consistent


def test_target_application_readiness_rejects_review_only_normalization():
    reviewed = reviewed_mapped_data_summary()

    result = evaluate_data_readiness(
        mapped_data_summary=reviewed,
        thresholds=DataReadinessThresholds(
            require_target_application_normalization=True,
            require_tick_diagnostics=False,
        ),
    )

    assert not result.ready
    assert result.action_queue is not None
    assert set(result.action_queue["next_gate"]) == {
        "normalize-applied-vendor-mapping"
    }
    failed = set(
        result.checks.loc[~result.checks["passed"].astype(bool), "check"]
    )
    assert "mapped_data_target_application_bound" in failed


def test_data_readiness_rejects_conflicting_strict_normalization_modes():
    with pytest.raises(ValueError, match="mutually exclusive"):
        evaluate_data_readiness(
            thresholds=DataReadinessThresholds(
                require_reviewed_mapping_normalization=True,
                require_target_application_normalization=True,
                require_tick_diagnostics=False,
            )
        )


def _mapping_application(
    tmp_path: Path,
    label: str,
    *,
    opaque: bool = False,
) -> tuple[Path, Path, Path]:
    scope_dir, _ = _mapping_scope(tmp_path, label, opaque=opaque)
    target_frame = (
        _opaque_ticks("2026-07-15")
        if opaque
        else _normal_ticks("2026-07-15")
    )
    intake_dir, source_path, _ = _target_intake(
        tmp_path,
        f"{label}_target",
        frame=target_frame,
    )
    application_dir = tmp_path / f"{label}_application"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)
    return application_dir, intake_dir, source_path


def _normalization_manifest_inputs(
    application_dir: Path,
    source_path: Path,
) -> dict[str, Path]:
    return {
        "mapping_application": application_dir,
        "mapping_application_manifest": application_dir / "manifest.json",
        "mapping_application_receipt": (
            application_dir / "vendor_mapping_application_receipt.json"
        ),
        "target_source": source_path,
        "applied_mapping": (
            application_dir / "target_applied_vendor_mapping.csv"
        ),
    }
