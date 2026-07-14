import json
from pathlib import Path

import pandas as pd
import pytest

from adapters.vendor_intake import (
    VendorCsvIntakeConfig,
    write_vendor_csv_intake_report,
)
from adapters.vendor_mapping_application import (
    approved_vendor_mapping_application_inputs,
    verify_vendor_mapping_application,
    write_vendor_mapping_application,
)
from adapters.vendor_mapping_review import write_vendor_mapping_review
from adapters.vendor_mapping_scope_review import write_vendor_mapping_scope_review
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import file_sha256, write_experiment_manifest


def test_mapping_application_binds_scope_to_different_exact_header_file(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "approved")
    intake_dir, target_source, intake = _target_intake(tmp_path, "target")
    application_dir = tmp_path / "target_application"

    report = write_vendor_mapping_application(
        scope_dir,
        intake_dir,
        application_dir,
    )
    verification = verify_vendor_mapping_application(application_dir)
    inputs = approved_vendor_mapping_application_inputs(application_dir)
    receipt = json.loads(
        (application_dir / "vendor_mapping_application_receipt.json").read_text(
            encoding="utf-8"
        )
    )

    assert report.ready
    assert report.action_queue.empty
    assert verification.verified
    assert verification.ready
    assert verification.manifest_current
    assert verification.scope_review_current
    assert verification.target_intake_current
    assert verification.target_source_current
    assert verification.artifacts_consistent
    assert verification.target_bound
    assert verification.application_only
    assert verification.non_routing
    assert verification.target_source_path == target_source.resolve()
    assert inputs.target_source_path == target_source.resolve()
    assert inputs.target_intake_dir == intake_dir.resolve()
    assert inputs.source_header_sha256 == intake.source_profile["header_sha256"]
    assert (
        application_dir / "target_applied_vendor_mapping.csv"
    ).read_bytes() == (scope_dir / "scope_approved_vendor_mapping.csv").read_bytes()
    assert receipt["contract_version"] == "vendor_mapping_target_application/v1"
    assert receipt["target_source"]["path"] == str(target_source.resolve())
    assert receipt["mapping"]["bytes_preserved"]
    assert receipt["safety"]["target_file_bound"]
    assert receipt["safety"]["exact_header_verified"]
    assert receipt["safety"]["authorizes_target_mapping_application"]
    assert not receipt["safety"]["normalization_executed"]
    assert not receipt["safety"]["authorizes_normalization"]
    assert not receipt["safety"]["authorizes_strategy_research"]
    assert not receipt["safety"]["authorizes_routing"]
    assert not receipt["safety"]["authorizes_submission"]

    catalog = catalog_experiment_runs([application_dir])
    row = catalog.catalog.iloc[0]
    assert bool(row["summary_status"])
    assert (
        row["vendor_mapping_application_verification_status"]
        == "verified_ready"
    )
    assert bool(row["vendor_mapping_application_verification_verified"])

    with pytest.raises(FileExistsError, match="already exists"):
        write_vendor_mapping_application(scope_dir, intake_dir, application_dir)

    cli_dir = tmp_path / "target_application_cli"
    assert (
        main(
            [
                "apply-vendor-mapping-scope",
                "--scope-review",
                str(scope_dir),
                "--intake",
                str(intake_dir),
                "--out",
                str(cli_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-vendor-mapping-application",
                "--application",
                str(cli_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )


def test_mapping_application_rejects_reordered_target_header(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "reordered")
    columns = list(_normal_ticks("2026-07-15").columns)
    reordered = _normal_ticks("2026-07-15")[
        [columns[1], columns[0], *columns[2:]]
    ]
    intake_dir, _, _ = _target_intake(
        tmp_path,
        "reordered_target",
        frame=reordered,
    )
    out = tmp_path / "reordered_application"

    with pytest.raises(ValueError, match="ordered_header_matches"):
        write_vendor_mapping_application(scope_dir, intake_dir, out)
    assert not out.exists()


@pytest.mark.parametrize(
    ("adapter", "kind", "expected_check"),
    [
        ("irage", "ticks", "adapter_matches"),
        ("arrow_money", "chain", "best_kind_matches"),
    ],
)
def test_mapping_application_rejects_identity_substitution(
    tmp_path,
    adapter,
    kind,
    expected_check,
):
    scope_dir, _ = _mapping_scope(tmp_path, f"{adapter}_{kind}")
    intake_dir, _, _ = _target_intake(
        tmp_path,
        f"{adapter}_{kind}_target",
        adapter=adapter,
        kind=kind,
    )

    with pytest.raises(ValueError, match=expected_check):
        write_vendor_mapping_application(
            scope_dir,
            intake_dir,
            tmp_path / f"{adapter}_{kind}_application",
        )


def test_mapping_application_accepts_verified_blocked_opaque_intake(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "opaque", opaque=True)
    intake_dir, _, intake = _target_intake(
        tmp_path,
        "opaque_target",
        frame=_opaque_ticks("2026-07-15"),
    )
    assert not intake.ready

    report = write_vendor_mapping_application(
        scope_dir,
        intake_dir,
        tmp_path / "opaque_application",
    )

    assert report.ready
    assert verify_vendor_mapping_application(report.output_dir).verified


def test_mapping_application_refuses_rejected_scope(tmp_path):
    scope_dir, _ = _mapping_scope(
        tmp_path,
        "rejected_scope",
        scope_decision="rejected",
    )
    intake_dir, _, _ = _target_intake(tmp_path, "rejected_scope_target")

    with pytest.raises(ValueError, match="verified approved scope review"):
        write_vendor_mapping_application(
            scope_dir,
            intake_dir,
            tmp_path / "rejected_scope_application",
        )


def test_mapping_application_verifier_rejects_target_source_drift(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "source_drift")
    intake_dir, source_path, _ = _target_intake(tmp_path, "source_drift_target")
    application_dir = tmp_path / "source_drift_application"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)

    source = pd.read_csv(source_path)
    source.loc[0, "best_bid"] = 99.95
    source.to_csv(source_path, index=False)
    verification = verify_vendor_mapping_application(application_dir)

    assert not verification.verified
    assert not verification.manifest_current
    assert verification.scope_review_current
    assert not verification.target_intake_current
    assert not verification.target_source_current
    assert "target intake" in verification.error
    assert (
        main(
            [
                "verify-vendor-mapping-application",
                "--application",
                str(application_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )
    catalog = catalog_experiment_runs([application_dir])
    row = catalog.catalog.iloc[0]
    assert (
        row["vendor_mapping_application_verification_status"]
        == "stale_or_inconsistent"
    )
    assert not bool(row["summary_status"])


def test_mapping_application_verifier_rejects_scope_drift(tmp_path):
    scope_dir, scope_decision_path = _mapping_scope(tmp_path, "scope_drift")
    intake_dir, _, _ = _target_intake(tmp_path, "scope_drift_target")
    application_dir = tmp_path / "scope_drift_application"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)

    decision = pd.read_csv(scope_decision_path)
    decision.loc[0, "notes"] = "Changed after target application."
    decision.to_csv(scope_decision_path, index=False)
    verification = verify_vendor_mapping_application(application_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert not verification.scope_review_current
    assert "verified approved scope review" in verification.error


def test_mapping_application_rejects_remanifested_normalization_claim(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "tamper")
    intake_dir, source_path, _ = _target_intake(tmp_path, "tamper_target")
    application_dir = tmp_path / "tamper_application"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)

    summary_path = application_dir / "vendor_mapping_application_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "normalization_executed"] = True
    summary.loc[0, "authorizes_normalization"] = True
    summary.to_csv(summary_path, index=False)
    manifest = json.loads(
        (application_dir / "manifest.json").read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        application_dir,
        run_type="vendor_mapping_target_application",
        parameters=manifest["parameters"],
        inputs=_application_manifest_inputs(
            scope_dir,
            intake_dir,
            source_path,
        ),
        extra=manifest["extra"],
    )
    verification = verify_vendor_mapping_application(application_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.scope_review_current
    assert verification.target_intake_current
    assert verification.target_source_current
    assert not verification.artifacts_consistent
    assert not verification.application_only


def test_mapping_application_rejects_remanifested_mapping_tamper(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "mapping_tamper")
    intake_dir, source_path, _ = _target_intake(
        tmp_path,
        "mapping_tamper_target",
    )
    application_dir = tmp_path / "mapping_tamper_application"
    write_vendor_mapping_application(scope_dir, intake_dir, application_dir)

    mapping_path = application_dir / "target_applied_vendor_mapping.csv"
    mapping = pd.read_csv(mapping_path)
    mapping.loc[0, "source_column"] = "best_bid"
    mapping.to_csv(mapping_path, index=False)
    manifest = json.loads(
        (application_dir / "manifest.json").read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        application_dir,
        run_type="vendor_mapping_target_application",
        parameters=manifest["parameters"],
        inputs=_application_manifest_inputs(
            scope_dir,
            intake_dir,
            source_path,
        ),
        extra=manifest["extra"],
    )
    verification = verify_vendor_mapping_application(application_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.scope_review_current
    assert verification.target_intake_current
    assert verification.target_source_current
    assert not verification.artifacts_consistent
    assert verification.application_only


def test_mapping_application_rejects_evidence_path_collisions(tmp_path):
    scope_dir, _ = _mapping_scope(tmp_path, "collision")
    intake_dir, _, _ = _target_intake(tmp_path, "collision_target")

    with pytest.raises(ValueError, match="scope-review evidence"):
        write_vendor_mapping_application(
            scope_dir,
            intake_dir,
            scope_dir / "application",
        )
    with pytest.raises(ValueError, match="target-intake evidence"):
        write_vendor_mapping_application(
            scope_dir,
            intake_dir,
            intake_dir / "application",
        )


def _mapping_scope(
    tmp_path: Path,
    label: str,
    *,
    opaque: bool = False,
    scope_decision: str = "approved",
) -> tuple[Path, Path]:
    source_path = tmp_path / f"{label}_seed.csv"
    intake_dir = tmp_path / f"{label}_seed_intake"
    candidate_path = tmp_path / f"{label}_mapping.csv"
    mapping_decision_path = tmp_path / f"{label}_mapping_decision.csv"
    mapping_review_dir = tmp_path / f"{label}_mapping_review"
    scope_decision_path = tmp_path / f"{label}_scope_decision.csv"
    scope_dir = tmp_path / f"{label}_scope_review"
    source = (
        _opaque_ticks("2026-07-14")
        if opaque
        else _normal_ticks("2026-07-14")
    )
    source.to_csv(source_path, index=False)
    intake = write_vendor_csv_intake_report(
        source_path,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="ticks"),
    )
    mapping = _opaque_mapping() if opaque else intake.mapping_draft
    mapping.to_csv(candidate_path, index=False)
    _mapping_decision(intake, candidate_path).to_csv(
        mapping_decision_path,
        index=False,
    )
    write_vendor_mapping_review(
        intake_dir,
        candidate_path,
        mapping_decision_path,
        mapping_review_dir,
    )
    _scope_decision(mapping_review_dir, scope_decision).to_csv(
        scope_decision_path,
        index=False,
    )
    write_vendor_mapping_scope_review(
        mapping_review_dir,
        scope_decision_path,
        scope_dir,
    )
    return scope_dir, scope_decision_path


def _target_intake(
    tmp_path: Path,
    label: str,
    *,
    frame: pd.DataFrame | None = None,
    adapter: str = "arrow_money",
    kind: str = "ticks",
):
    source_path = tmp_path / f"{label}.csv"
    intake_dir = tmp_path / f"{label}_intake"
    (frame if frame is not None else _normal_ticks("2026-07-15")).to_csv(
        source_path,
        index=False,
    )
    intake = write_vendor_csv_intake_report(
        source_path,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(adapter=adapter, kind=kind),
    )
    return intake_dir, source_path, intake


def _mapping_decision(intake, mapping_path: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "intake_receipt_id": intake.receipt["intake_receipt_id"],
                "source_file_sha256": intake.source_profile["file_sha256"],
                "mapping_candidate_sha256": file_sha256(mapping_path),
                "adapter": "arrow_money",
                "kind": "ticks",
                "decision": "approved",
                "operator_id": "market-data-reviewer-1",
                "operator_role": "market_data_engineer",
                "reviewed_at_utc": "2026-07-14T08:00:00+00:00",
                "vendor_documentation_checked": True,
                "source_columns_confirmed": True,
                "field_semantics_confirmed": True,
                "timestamp_semantics_confirmed": True,
                "price_quantity_units_confirmed": True,
                "transform_semantics_confirmed": True,
                "notes": "Reviewed against retained vendor documentation.",
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    )


def _scope_decision(mapping_review_dir: Path, decision: str) -> pd.DataFrame:
    receipt = json.loads(
        (mapping_review_dir / "vendor_mapping_review_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    return pd.DataFrame(
        [
            {
                "mapping_review_id": receipt["mapping_review_id"],
                "mapping_review_sha256": receipt["mapping_review_sha256"],
                "reviewed_mapping_sha256": receipt["mapping"]["reviewed_sha256"],
                "source_header_sha256": receipt["intake"]["source_header_sha256"],
                "adapter": receipt["identity"]["adapter"],
                "kind": receipt["identity"]["kind"],
                "reuse_scope": "exact_header",
                "decision": decision,
                "operator_id": "market-data-scope-reviewer-1",
                "operator_role": "market_data_engineer",
                "reviewed_at_utc": "2026-07-14T08:05:00+00:00",
                "vendor_documentation_checked": True,
                "schema_stability_confirmed": True,
                "field_semantics_stable_across_files_confirmed": True,
                "timestamp_semantics_stable_across_files_confirmed": True,
                "price_quantity_units_stable_across_files_confirmed": True,
                "transform_semantics_stable_across_files_confirmed": True,
                "partitioning_semantics_confirmed": True,
                "notes": (
                    "Approved exact ordered-header reuse."
                    if decision == "approved"
                    else "Operator rejected exact-header reuse."
                ),
                "authorizes_header_scoped_application": decision == "approved",
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    )


def _normal_ticks(day: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "exchange_ts": f"{day} 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            }
        ]
    )


def _opaque_ticks(day: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "T": f"{day} 09:15:00",
                "B": 100.0,
                "A": 100.05,
                "BQ": 75,
                "AQ": 150,
                "L": 100.05,
                "LQ": 75,
            }
        ]
    )


def _opaque_mapping() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"normalized_column": "ts", "source_column": "T"},
            {"normalized_column": "bid", "source_column": "B", "transform": "float"},
            {"normalized_column": "ask", "source_column": "A", "transform": "float"},
            {"normalized_column": "bid_qty", "source_column": "BQ", "transform": "int"},
            {"normalized_column": "ask_qty", "source_column": "AQ", "transform": "int"},
            {"normalized_column": "last", "source_column": "L", "transform": "float"},
            {"normalized_column": "last_qty", "source_column": "LQ", "transform": "int"},
        ]
    )


def _application_manifest_inputs(
    scope_dir: Path,
    intake_dir: Path,
    source_path: Path,
) -> dict[str, Path]:
    return {
        "scope_review": scope_dir,
        "scope_review_manifest": scope_dir / "manifest.json",
        "scope_review_receipt": scope_dir / "vendor_mapping_scope_review_receipt.json",
        "scope_mapping": scope_dir / "scope_approved_vendor_mapping.csv",
        "target_intake": intake_dir,
        "target_intake_manifest": intake_dir / "manifest.json",
        "target_intake_receipt": intake_dir / "vendor_intake_receipt.json",
        "target_intake_source_profile": intake_dir / "vendor_intake_source_profile.json",
        "target_source": source_path,
    }
