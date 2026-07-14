import json
from pathlib import Path

import pandas as pd
import pytest

from adapters.vendor_intake import (
    VendorCsvIntakeConfig,
    write_vendor_csv_intake_report,
)
from adapters.vendor_mapping_review import (
    VendorMappingReviewConfig,
    verify_vendor_mapping_review,
    write_vendor_mapping_review,
)
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import file_sha256, write_experiment_manifest


def test_vendor_mapping_review_seals_approved_mapping_and_is_write_once(tmp_path):
    intake_dir, intake = _write_intake(tmp_path, "approved")
    mapping_path = tmp_path / "approved_mapping.csv"
    decision_path = tmp_path / "approved_decision.csv"
    review_dir = tmp_path / "approved_review"
    intake.mapping_draft.to_csv(mapping_path, index=False)
    _decision(intake, mapping_path, decision="approved").to_csv(
        decision_path,
        index=False,
    )

    report = write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )
    verification = verify_vendor_mapping_review(review_dir)
    receipt = json.loads(
        (review_dir / "vendor_mapping_review_receipt.json").read_text(
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
    assert verification.intake_current
    assert verification.mapping_candidate_current
    assert verification.operator_decision_current
    assert verification.artifacts_consistent
    assert verification.normalization_only
    assert verification.non_routing
    assert receipt["contract_version"] == "vendor_mapping_review/v1"
    assert receipt["mapping"]["mapping_valid"]
    assert receipt["safety"]["authorizes_normalization"]
    assert not receipt["safety"]["authorizes_strategy_research"]
    assert not receipt["safety"]["authorizes_routing"]
    assert not receipt["safety"]["authorizes_submission"]
    assert (review_dir / "reviewed_vendor_mapping.csv").exists()

    catalog = catalog_experiment_runs([review_dir])
    catalog_row = catalog.catalog.iloc[0]
    assert bool(catalog_row["summary_status"])
    assert (
        catalog_row["vendor_mapping_review_verification_status"]
        == "verified_approved"
    )

    with pytest.raises(FileExistsError, match="already exists"):
        write_vendor_mapping_review(
            intake_dir,
            mapping_path,
            decision_path,
            review_dir,
        )

    cli_review_dir = tmp_path / "approved_cli_review"
    assert (
        main(
            [
                "review-vendor-mapping",
                "--intake",
                str(intake_dir),
                "--mapping",
                str(mapping_path),
                "--decision",
                str(decision_path),
                "--out",
                str(cli_review_dir),
                "--fail-on-rejected",
            ]
        )
        == 0
    )
    assert verify_vendor_mapping_review(cli_review_dir).approved
    assert (
        main(
            [
                "verify-vendor-mapping-review",
                "--review",
                str(review_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )


def test_vendor_mapping_review_can_supersede_blocked_inference_without_mutation(tmp_path):
    source_path = tmp_path / "opaque_vendor_ticks.csv"
    intake_dir = tmp_path / "opaque_intake"
    mapping_path = tmp_path / "manual_mapping.csv"
    decision_path = tmp_path / "manual_decision.csv"
    review_dir = tmp_path / "manual_review"
    pd.DataFrame(
        [
            {
                "T": "2026-06-10 09:15:00",
                "B": 100.0,
                "A": 100.05,
                "BQ": 75,
                "AQ": 150,
                "L": 100.05,
                "LQ": 75,
            }
        ]
    ).to_csv(source_path, index=False)
    intake = write_vendor_csv_intake_report(
        source_path,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(kind="ticks"),
    )
    assert not intake.ready
    pd.DataFrame(
        [
            {"normalized_column": "ts", "source_column": "T"},
            {"normalized_column": "bid", "source_column": "B", "transform": "float"},
            {"normalized_column": "ask", "source_column": "A", "transform": "float"},
            {"normalized_column": "bid_qty", "source_column": "BQ", "transform": "int"},
            {"normalized_column": "ask_qty", "source_column": "AQ", "transform": "int"},
            {"normalized_column": "last", "source_column": "L", "transform": "float"},
            {"normalized_column": "last_qty", "source_column": "LQ", "transform": "int"},
        ]
    ).to_csv(mapping_path, index=False)
    _decision(intake, mapping_path, decision="approved").to_csv(
        decision_path,
        index=False,
    )

    report = write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )

    assert report.approved
    assert bool(report.summary.loc[0, "mapping_valid"])
    assert int(report.summary.loc[0, "normalized_target_count"]) == 7
    assert verify_vendor_mapping_review(review_dir).verified
    assert (intake_dir / "vendor_mapping_draft.csv").read_bytes() != mapping_path.read_bytes()


def test_vendor_mapping_review_rejects_invalid_approved_mapping(tmp_path):
    intake_dir, intake = _write_intake(tmp_path, "invalid_approved")
    mapping_path = tmp_path / "invalid_approved_mapping.csv"
    decision_path = tmp_path / "invalid_approved_decision.csv"
    mapping = intake.mapping_draft.copy()
    mapping.loc[
        mapping["normalized_column"] == "ask_qty",
        "source_column",
    ] = "missing_ask_qty"
    mapping.to_csv(mapping_path, index=False)
    _decision(intake, mapping_path, decision="approved").to_csv(
        decision_path,
        index=False,
    )

    with pytest.raises(ValueError, match="approved vendor mapping failed"):
        write_vendor_mapping_review(
            intake_dir,
            mapping_path,
            decision_path,
            tmp_path / "invalid_approved_review",
        )


def test_vendor_mapping_review_rejects_unknown_operator_claims(tmp_path):
    intake_dir, intake = _write_intake(tmp_path, "unknown_claim")
    mapping_path = tmp_path / "unknown_claim_mapping.csv"
    decision_path = tmp_path / "unknown_claim_decision.csv"
    intake.mapping_draft.to_csv(mapping_path, index=False)
    decision = _decision(intake, mapping_path, decision="approved")
    decision["authorizes_strategy_research"] = True
    decision.to_csv(decision_path, index=False)

    with pytest.raises(ValueError, match="operator_columns_known"):
        write_vendor_mapping_review(
            intake_dir,
            mapping_path,
            decision_path,
            tmp_path / "unknown_claim_review",
        )


def test_vendor_mapping_review_seals_rejection_and_strict_cli_fails(tmp_path):
    intake_dir, intake = _write_intake(tmp_path, "rejected")
    mapping_path = tmp_path / "rejected_mapping.csv"
    decision_path = tmp_path / "rejected_decision.csv"
    review_dir = tmp_path / "rejected_review"
    mapping = intake.mapping_draft.copy()
    mapping.loc[
        mapping["normalized_column"] == "last_qty",
        "source_column",
    ] = "missing_last_qty"
    mapping.to_csv(mapping_path, index=False)
    _decision(
        intake,
        mapping_path,
        decision="rejected",
        notes="Vendor documentation does not confirm last-quantity units.",
    ).to_csv(decision_path, index=False)

    report = write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )
    verification = verify_vendor_mapping_review(review_dir)

    assert report.sealed
    assert not report.approved
    assert not report.action_queue.empty
    assert verification.verified
    assert verification.rejected
    assert not verification.approved
    cli_review_dir = tmp_path / "rejected_cli_review"
    assert (
        main(
            [
                "review-vendor-mapping",
                "--intake",
                str(intake_dir),
                "--mapping",
                str(mapping_path),
                "--decision",
                str(decision_path),
                "--out",
                str(cli_review_dir),
                "--fail-on-rejected",
            ]
        )
        == 2
    )
    assert verify_vendor_mapping_review(cli_review_dir).rejected
    assert (
        main(
            [
                "verify-vendor-mapping-review",
                "--review",
                str(review_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_vendor_mapping_review_verifier_rejects_upstream_source_drift(tmp_path):
    intake_dir, intake = _write_intake(tmp_path, "source_drift")
    mapping_path = tmp_path / "source_drift_mapping.csv"
    decision_path = tmp_path / "source_drift_decision.csv"
    review_dir = tmp_path / "source_drift_review"
    intake.mapping_draft.to_csv(mapping_path, index=False)
    _decision(intake, mapping_path, decision="approved").to_csv(
        decision_path,
        index=False,
    )
    write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )

    source_path = Path(str(intake.source_profile["source_path"]))
    changed = pd.read_csv(source_path)
    changed.loc[0, "best_bid"] = 99.95
    changed.to_csv(source_path, index=False)
    verification = verify_vendor_mapping_review(review_dir)

    assert not verification.verified
    assert not verification.intake_current
    assert not verification.manifest_current
    assert "source is stale" in verification.error


def test_vendor_mapping_review_rejects_remanifested_candidate_tamper(tmp_path):
    intake_dir, intake = _write_intake(tmp_path, "candidate_tamper")
    mapping_path = tmp_path / "candidate_tamper_mapping.csv"
    decision_path = tmp_path / "candidate_tamper_decision.csv"
    review_dir = tmp_path / "candidate_tamper_review"
    intake.mapping_draft.to_csv(mapping_path, index=False)
    _decision(intake, mapping_path, decision="approved").to_csv(
        decision_path,
        index=False,
    )
    write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )

    mapping = pd.read_csv(mapping_path)
    mapping.loc[mapping["normalized_column"] == "bid", "source_column"] = "best_ask"
    mapping.to_csv(mapping_path, index=False)
    manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
    write_experiment_manifest(
        review_dir,
        run_type="vendor_mapping_review",
        parameters=manifest["parameters"],
        inputs={
            "vendor_intake": intake_dir,
            "vendor_intake_manifest": intake_dir / "manifest.json",
            "vendor_intake_receipt": intake_dir / "vendor_intake_receipt.json",
            "vendor_source": Path(str(intake.source_profile["source_path"])),
            "mapping_candidate": mapping_path,
            "operator_decision": decision_path,
        },
        extra=manifest["extra"],
    )
    verification = verify_vendor_mapping_review(review_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.mapping_candidate_current
    assert verification.operator_decision_current
    assert "operator decision contract failed" in verification.error


def test_catalog_distinguishes_approved_rejected_and_stale_mapping_reviews(tmp_path):
    review_dirs = {}
    for label, decision in (("approved", "approved"), ("rejected", "rejected")):
        root = tmp_path / label
        root.mkdir()
        intake_dir, intake = _write_intake(root, label)
        mapping_path = root / "mapping.csv"
        decision_path = root / "decision.csv"
        review_dir = root / "review"
        intake.mapping_draft.to_csv(mapping_path, index=False)
        _decision(
            intake,
            mapping_path,
            decision=decision,
            notes="Needs revision." if decision == "rejected" else "Reviewed.",
        ).to_csv(decision_path, index=False)
        write_vendor_mapping_review(
            intake_dir,
            mapping_path,
            decision_path,
            review_dir,
        )
        review_dirs[label] = (review_dir, decision_path)
    stale_review, stale_decision = review_dirs["approved"]
    decision_frame = pd.read_csv(stale_decision)
    decision_frame.loc[0, "notes"] = "Changed after sealing."
    decision_frame.to_csv(stale_decision, index=False)

    catalog = catalog_experiment_runs([tmp_path])
    reviews = catalog.catalog.loc[
        catalog.catalog["run_type"].astype(str).eq("vendor_mapping_review")
    ]
    rows = {
        Path(str(row["run_dir"])).parent.name: row
        for row in reviews.to_dict(orient="records")
    }

    assert len(rows) == 2
    assert rows["approved"]["vendor_mapping_review_verification_status"] == "stale_or_inconsistent"
    assert not bool(rows["approved"]["summary_status"])
    assert rows["rejected"]["vendor_mapping_review_verification_status"] == "verified_rejected"
    assert bool(rows["rejected"]["vendor_mapping_review_verification_verified"])
    assert not bool(rows["rejected"]["summary_status"])


def _write_intake(tmp_path: Path, label: str):
    source_path = tmp_path / f"{label}_ticks.csv"
    intake_dir = tmp_path / f"{label}_intake"
    pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
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
        config=VendorCsvIntakeConfig(kind="ticks"),
    )
    return intake_dir, intake


def _decision(
    intake,
    mapping_path: Path,
    *,
    decision: str,
    notes: str = "Reviewed against retained vendor documentation.",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "intake_receipt_id": intake.receipt["intake_receipt_id"],
                "source_file_sha256": intake.source_profile["file_sha256"],
                "mapping_candidate_sha256": file_sha256(mapping_path),
                "adapter": intake.summary.loc[0, "adapter"],
                "kind": intake.summary.loc[0, "best_kind"],
                "decision": decision,
                "operator_id": "market-data-reviewer-1",
                "operator_role": "market_data_engineer",
                "reviewed_at_utc": "2026-07-14T06:15:00+00:00",
                "vendor_documentation_checked": True,
                "source_columns_confirmed": True,
                "field_semantics_confirmed": True,
                "timestamp_semantics_confirmed": True,
                "price_quantity_units_confirmed": True,
                "transform_semantics_confirmed": True,
                "notes": notes,
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    )
