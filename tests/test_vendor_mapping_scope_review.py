import json
from pathlib import Path

import pandas as pd
import pytest

from adapters.vendor_intake import (
    VendorCsvIntakeConfig,
    write_vendor_csv_intake_report,
)
from adapters.vendor_mapping_review import write_vendor_mapping_review
from adapters.vendor_mapping_scope_review import (
    verify_vendor_mapping_scope_review,
    write_vendor_mapping_scope_review,
)
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import file_sha256, write_experiment_manifest


def test_mapping_scope_review_seals_exact_header_approval_and_cli(tmp_path):
    review_dir, source_path, reviewed_mapping = _mapping_review(tmp_path, "approved")
    decision_path = tmp_path / "approved_scope_decision.csv"
    scope_dir = tmp_path / "approved_scope_review"
    _scope_decision(review_dir, decision="approved").to_csv(
        decision_path,
        index=False,
    )

    report = write_vendor_mapping_scope_review(
        review_dir,
        decision_path,
        scope_dir,
    )
    verification = verify_vendor_mapping_scope_review(scope_dir)
    receipt = json.loads(
        (scope_dir / "vendor_mapping_scope_review_receipt.json").read_text(
            encoding="utf-8"
        )
    )

    assert report.sealed
    assert report.approved
    assert report.action_queue.empty
    assert verification.verified
    assert verification.sealed
    assert verification.approved
    assert not verification.rejected
    assert verification.manifest_current
    assert verification.mapping_review_current
    assert verification.operator_decision_current
    assert verification.artifacts_consistent
    assert verification.application_only
    assert verification.non_routing
    assert verification.mapping_review_dir == review_dir.resolve()
    assert (
        scope_dir / "scope_approved_vendor_mapping.csv"
    ).read_bytes() == reviewed_mapping.read_bytes()
    assert receipt["contract_version"] == "vendor_mapping_scope_review/v1"
    assert receipt["scope"]["reuse_scope"] == "exact_header"
    assert receipt["scope"]["header_order_sensitive"]
    assert receipt["scope"]["exact_header_match_required"]
    assert receipt["safety"]["authorizes_header_scoped_application"]
    assert not receipt["safety"]["authorizes_normalization"]
    assert not receipt["safety"]["authorizes_strategy_research"]
    assert not receipt["safety"]["authorizes_routing"]
    assert not receipt["safety"]["authorizes_submission"]
    assert not receipt["safety"]["authorizes_live_release"]

    catalog = catalog_experiment_runs([scope_dir])
    row = catalog.catalog.iloc[0]
    assert bool(row["summary_status"])
    assert (
        row["vendor_mapping_scope_review_verification_status"]
        == "verified_approved"
    )
    assert bool(row["vendor_mapping_scope_review_verification_verified"])

    with pytest.raises(FileExistsError, match="already exists"):
        write_vendor_mapping_scope_review(review_dir, decision_path, scope_dir)

    cli_dir = tmp_path / "approved_cli_scope_review"
    assert (
        main(
            [
                "review-vendor-mapping-scope",
                "--review",
                str(review_dir),
                "--decision",
                str(decision_path),
                "--out",
                str(cli_dir),
                "--fail-on-rejected",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-vendor-mapping-scope-review",
                "--scope-review",
                str(cli_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    assert source_path.is_file()


def test_mapping_scope_review_seals_rejection_and_strict_cli_fails(tmp_path):
    review_dir, _, _ = _mapping_review(tmp_path, "rejected_scope")
    decision_path = tmp_path / "rejected_scope_decision.csv"
    scope_dir = tmp_path / "rejected_scope_review"
    _scope_decision(review_dir, decision="rejected").to_csv(
        decision_path,
        index=False,
    )

    report = write_vendor_mapping_scope_review(
        review_dir,
        decision_path,
        scope_dir,
    )
    verification = verify_vendor_mapping_scope_review(scope_dir)

    assert report.sealed
    assert not report.approved
    assert not report.action_queue.empty
    assert verification.verified
    assert verification.rejected
    assert not verification.approved
    assert verification.application_only
    assert verification.non_routing
    assert (
        main(
            [
                "verify-vendor-mapping-scope-review",
                "--scope-review",
                str(scope_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )

    cli_dir = tmp_path / "rejected_cli_scope_review"
    assert (
        main(
            [
                "review-vendor-mapping-scope",
                "--review",
                str(review_dir),
                "--decision",
                str(decision_path),
                "--out",
                str(cli_dir),
                "--fail-on-rejected",
            ]
        )
        == 2
    )
    catalog = catalog_experiment_runs([scope_dir])
    row = catalog.catalog.iloc[0]
    assert not bool(row["summary_status"])
    assert (
        row["vendor_mapping_scope_review_verification_status"]
        == "verified_rejected"
    )
    assert bool(row["vendor_mapping_scope_review_verification_verified"])


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("header_mismatch", "source_header_sha256_matches"),
        ("unknown_claim", "operator_columns_known"),
        (
            "missing_semantic_attestation",
            "field_semantics_stable_across_files_confirmed_attested",
        ),
        (
            "application_authority_mismatch",
            "header_scoped_application_authority_consistent",
        ),
    ],
)
def test_mapping_scope_review_rejects_unbound_or_incomplete_decisions(
    tmp_path,
    mutation,
    expected_check,
):
    review_dir, _, _ = _mapping_review(tmp_path, mutation)
    decision = _scope_decision(review_dir, decision="approved")
    if mutation == "header_mismatch":
        decision.loc[0, "source_header_sha256"] = "0" * 64
    elif mutation == "unknown_claim":
        decision["authorizes_strategy_research"] = True
    elif mutation == "missing_semantic_attestation":
        decision.loc[
            0,
            "field_semantics_stable_across_files_confirmed",
        ] = False
    else:
        decision.loc[0, "authorizes_header_scoped_application"] = False
    decision_path = tmp_path / f"{mutation}_scope_decision.csv"
    decision.to_csv(decision_path, index=False)

    with pytest.raises(ValueError, match=expected_check):
        write_vendor_mapping_scope_review(
            review_dir,
            decision_path,
            tmp_path / f"{mutation}_scope_review",
        )


def test_mapping_scope_review_refuses_rejected_base_mapping_review(tmp_path):
    review_dir, _, _ = _mapping_review(
        tmp_path,
        "rejected_base",
        review_decision="rejected",
    )
    decision_path = tmp_path / "rejected_base_scope_decision.csv"
    _scope_decision(review_dir, decision="rejected").to_csv(
        decision_path,
        index=False,
    )

    with pytest.raises(ValueError, match="verified approved mapping review"):
        write_vendor_mapping_scope_review(
            review_dir,
            decision_path,
            tmp_path / "rejected_base_scope_review",
        )


def test_mapping_scope_review_verifier_rejects_decision_drift(tmp_path):
    review_dir, _, _ = _mapping_review(tmp_path, "decision_drift")
    decision_path = tmp_path / "decision_drift_scope_decision.csv"
    scope_dir = tmp_path / "decision_drift_scope_review"
    _scope_decision(review_dir, decision="approved").to_csv(
        decision_path,
        index=False,
    )
    write_vendor_mapping_scope_review(review_dir, decision_path, scope_dir)

    decision = pd.read_csv(decision_path)
    decision.loc[0, "notes"] = "Changed after the scope review was sealed."
    decision.to_csv(decision_path, index=False)
    verification = verify_vendor_mapping_scope_review(scope_dir)

    assert not verification.verified
    assert not verification.manifest_current
    assert verification.mapping_review_current
    assert not verification.operator_decision_current
    assert "fingerprint is stale" in verification.error
    catalog = catalog_experiment_runs([scope_dir])
    row = catalog.catalog.iloc[0]
    assert (
        row["vendor_mapping_scope_review_verification_status"]
        == "stale_or_inconsistent"
    )
    assert not bool(row["summary_status"])


def test_mapping_scope_review_verifier_rejects_upstream_source_drift(tmp_path):
    review_dir, source_path, _ = _mapping_review(tmp_path, "source_drift")
    decision_path = tmp_path / "source_drift_scope_decision.csv"
    scope_dir = tmp_path / "source_drift_scope_review"
    _scope_decision(review_dir, decision="approved").to_csv(
        decision_path,
        index=False,
    )
    write_vendor_mapping_scope_review(review_dir, decision_path, scope_dir)

    source = pd.read_csv(source_path)
    source.loc[0, "best_bid"] = 99.95
    source.to_csv(source_path, index=False)
    verification = verify_vendor_mapping_scope_review(scope_dir)

    assert not verification.verified
    assert not verification.manifest_current
    assert not verification.mapping_review_current
    assert not verification.approved
    assert "verified approved mapping review" in verification.error


def test_mapping_scope_review_rejects_remanifested_authority_tamper(tmp_path):
    review_dir, source_path, reviewed_mapping = _mapping_review(tmp_path, "tamper")
    decision_path = tmp_path / "tamper_scope_decision.csv"
    scope_dir = tmp_path / "tamper_scope_review"
    _scope_decision(review_dir, decision="approved").to_csv(
        decision_path,
        index=False,
    )
    write_vendor_mapping_scope_review(review_dir, decision_path, scope_dir)

    summary_path = scope_dir / "vendor_mapping_scope_review_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "authorizes_normalization"] = True
    summary.to_csv(summary_path, index=False)
    manifest = json.loads((scope_dir / "manifest.json").read_text(encoding="utf-8"))
    write_experiment_manifest(
        scope_dir,
        run_type="vendor_mapping_scope_review",
        parameters=manifest["parameters"],
        inputs={
            "mapping_review": review_dir,
            "mapping_review_manifest": review_dir / "manifest.json",
            "mapping_review_receipt": (
                review_dir / "vendor_mapping_review_receipt.json"
            ),
            "reviewed_mapping": reviewed_mapping,
            "review_seed_source": source_path,
            "operator_decision": decision_path,
        },
        extra=manifest["extra"],
    )
    verification = verify_vendor_mapping_scope_review(scope_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.mapping_review_current
    assert verification.operator_decision_current
    assert not verification.artifacts_consistent
    assert not verification.application_only


def test_mapping_scope_review_rejects_evidence_path_collisions(tmp_path):
    review_dir, _, _ = _mapping_review(tmp_path, "collision")
    decision_path = tmp_path / "collision_scope_decision.csv"
    _scope_decision(review_dir, decision="approved").to_csv(
        decision_path,
        index=False,
    )

    with pytest.raises(ValueError, match="cannot modify mapping-review evidence"):
        write_vendor_mapping_scope_review(
            review_dir,
            decision_path,
            review_dir / "scope_review",
        )

    nested_decision = review_dir / "scope_decision.csv"
    nested_decision.write_bytes(decision_path.read_bytes())
    with pytest.raises(ValueError, match="must remain outside"):
        write_vendor_mapping_scope_review(
            review_dir,
            nested_decision,
            tmp_path / "collision_scope_review",
        )


def _mapping_review(
    tmp_path: Path,
    label: str,
    *,
    review_decision: str = "approved",
) -> tuple[Path, Path, Path]:
    source_path = tmp_path / f"{label}_ticks.csv"
    intake_dir = tmp_path / f"{label}_intake"
    mapping_path = tmp_path / f"{label}_mapping.csv"
    mapping_decision_path = tmp_path / f"{label}_mapping_decision.csv"
    review_dir = tmp_path / f"{label}_mapping_review"
    pd.DataFrame(
        [
            {
                "exchange_ts": "2026-07-14 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            }
        ]
    ).to_csv(source_path, index=False)
    intake = write_vendor_csv_intake_report(
        source_path,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="ticks"),
    )
    intake.mapping_draft.to_csv(mapping_path, index=False)
    pd.DataFrame(
        [
            {
                "intake_receipt_id": intake.receipt["intake_receipt_id"],
                "source_file_sha256": intake.source_profile["file_sha256"],
                "mapping_candidate_sha256": file_sha256(mapping_path),
                "adapter": intake.summary.loc[0, "adapter"],
                "kind": intake.summary.loc[0, "best_kind"],
                "decision": review_decision,
                "operator_id": "market-data-reviewer-1",
                "operator_role": "market_data_engineer",
                "reviewed_at_utc": "2026-07-14T06:30:00+00:00",
                "vendor_documentation_checked": True,
                "source_columns_confirmed": True,
                "field_semantics_confirmed": True,
                "timestamp_semantics_confirmed": True,
                "price_quantity_units_confirmed": True,
                "transform_semantics_confirmed": True,
                "notes": (
                    "Reviewed against retained vendor documentation."
                    if review_decision == "approved"
                    else "Operator rejected this source-bound mapping."
                ),
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(mapping_decision_path, index=False)
    write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        mapping_decision_path,
        review_dir,
    )
    return review_dir, source_path, review_dir / "reviewed_vendor_mapping.csv"


def _scope_decision(review_dir: Path, *, decision: str) -> pd.DataFrame:
    receipt = json.loads(
        (review_dir / "vendor_mapping_review_receipt.json").read_text(
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
                "reviewed_at_utc": "2026-07-14T07:30:00+00:00",
                "vendor_documentation_checked": True,
                "schema_stability_confirmed": True,
                "field_semantics_stable_across_files_confirmed": True,
                "timestamp_semantics_stable_across_files_confirmed": True,
                "price_quantity_units_stable_across_files_confirmed": True,
                "transform_semantics_stable_across_files_confirmed": True,
                "partitioning_semantics_confirmed": True,
                "notes": (
                    "Approved exact ordered-header reuse across retained daily files."
                    if decision == "approved"
                    else "Operator rejected cross-file mapping reuse."
                ),
                "authorizes_header_scoped_application": decision == "approved",
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    )
