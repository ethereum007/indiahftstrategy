import json
from pathlib import Path

import pandas as pd
import pytest

from adapters.reviewed_mapped_data import (
    ReviewedMappedDataConfig,
    verify_reviewed_mapped_data_normalization,
    write_reviewed_mapped_data_normalization,
)
from adapters.vendor_intake import (
    VendorCsvIntakeConfig,
    write_vendor_csv_intake_report,
)
from adapters.vendor_mapping_review import write_vendor_mapping_review
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.data_readiness import DataReadinessThresholds, write_data_readiness_report
from reports.manifest import file_sha256, write_experiment_manifest


def test_reviewed_normalization_is_ready_write_once_and_cli_verified(tmp_path):
    review_dir, source_path, mapping_path = _mapping_review(tmp_path, "ready")
    normalization_dir = tmp_path / "ready_normalization"
    config = ReviewedMappedDataConfig(timestamp_unit="datetime")

    report = write_reviewed_mapped_data_normalization(
        review_dir,
        output_dir=normalization_dir,
        config=config,
    )
    verification = verify_reviewed_mapped_data_normalization(normalization_dir)
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
    assert verification.mapping_review_current
    assert verification.source_current
    assert verification.reviewed_mapping_current
    assert verification.artifacts_consistent
    assert verification.normalization_only
    assert verification.non_routing
    assert verification.source_path == source_path.resolve()
    assert verification.reviewed_mapping_path == mapping_path.resolve()
    assert receipt["contract_version"] == "reviewed_mapped_data_normalization/v1"
    assert receipt["mapping_review"]["approved"]
    assert receipt["normalization"]["output_rows"] == 1
    assert not receipt["safety"]["authorizes_strategy_research"]
    assert not receipt["safety"]["authorizes_routing"]
    assert not receipt["safety"]["authorizes_submission"]

    with pytest.raises(FileExistsError, match="already exists"):
        write_reviewed_mapped_data_normalization(
            review_dir,
            output_dir=normalization_dir,
            config=config,
        )

    cli_dir = tmp_path / "ready_cli_normalization"
    assert (
        main(
            [
                "normalize-reviewed-mapped-data",
                "--review",
                str(review_dir),
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
                "verify-reviewed-mapped-data",
                "--normalization",
                str(cli_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )

    catalog = catalog_experiment_runs([normalization_dir])
    row = catalog.catalog.iloc[0]
    assert bool(row["summary_status"])
    assert row["reviewed_mapped_data_verification_status"] == "verified_ready"
    assert bool(row["reviewed_mapped_data_verification_verified"])

    readiness = write_data_readiness_report(
        output_dir=tmp_path / "ready_data_readiness",
        mapped_data_dir=normalization_dir,
        thresholds=DataReadinessThresholds(
            require_mapped_data=True,
            require_tick_diagnostics=False,
            expected_adapter="arrow_money",
            expected_vendor_data_kind="ticks",
        ),
    )
    assert readiness.ready


def test_reviewed_normalization_refuses_rejected_mapping_review(tmp_path):
    review_dir, _, _ = _mapping_review(
        tmp_path,
        "rejected",
        decision="rejected",
    )

    with pytest.raises(ValueError, match="verified approved mapping review"):
        write_reviewed_mapped_data_normalization(
            review_dir,
            output_dir=tmp_path / "rejected_normalization",
            config=ReviewedMappedDataConfig(timestamp_unit="datetime"),
        )


def test_reviewed_normalization_seals_valid_blocked_data_quality_evidence(tmp_path):
    review_dir, _, _ = _mapping_review(
        tmp_path,
        "blocked",
        timestamp="2026-07-14 08:00:00",
    )
    normalization_dir = tmp_path / "blocked_normalization"
    report = write_reviewed_mapped_data_normalization(
        review_dir,
        output_dir=normalization_dir,
        config=ReviewedMappedDataConfig(timestamp_unit="datetime"),
    )
    verification = verify_reviewed_mapped_data_normalization(normalization_dir)

    assert not report.ready
    assert report.data.empty
    assert not report.action_queue.empty
    assert report.action_queue.loc[0, "next_gate"] == "normalize-reviewed-mapped-data"
    assert verification.verified
    assert not verification.ready
    assert verification.blocked
    assert (
        main(
            [
                "verify-reviewed-mapped-data",
                "--normalization",
                str(normalization_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )

    catalog = catalog_experiment_runs([normalization_dir])
    row = catalog.catalog.iloc[0]
    assert not bool(row["summary_status"])
    assert row["reviewed_mapped_data_verification_status"] == "verified_blocked"
    assert bool(row["reviewed_mapped_data_verification_verified"])


def test_reviewed_normalization_verifier_rejects_source_drift(tmp_path):
    review_dir, source_path, _ = _mapping_review(tmp_path, "source_drift")
    normalization_dir = tmp_path / "source_drift_normalization"
    write_reviewed_mapped_data_normalization(
        review_dir,
        output_dir=normalization_dir,
        config=ReviewedMappedDataConfig(timestamp_unit="datetime"),
    )

    changed = pd.read_csv(source_path)
    changed.loc[0, "best_bid"] = 99.95
    changed.to_csv(source_path, index=False)
    verification = verify_reviewed_mapped_data_normalization(normalization_dir)

    assert not verification.verified
    assert not verification.manifest_current
    assert not verification.mapping_review_current
    assert not verification.source_current
    assert "source is stale" in verification.error


def test_reviewed_normalization_rejects_remanifested_output_tamper(tmp_path):
    review_dir, source_path, mapping_path = _mapping_review(tmp_path, "tamper")
    normalization_dir = tmp_path / "tamper_normalization"
    write_reviewed_mapped_data_normalization(
        review_dir,
        output_dir=normalization_dir,
        config=ReviewedMappedDataConfig(timestamp_unit="datetime"),
    )

    output_path = normalization_dir / "normalized_data.csv"
    output = pd.read_csv(output_path)
    output.loc[0, "bid"] = 0.01
    output.to_csv(output_path, index=False)
    manifest = json.loads(
        (normalization_dir / "manifest.json").read_text(encoding="utf-8")
    )
    write_experiment_manifest(
        normalization_dir,
        run_type="reviewed_mapped_data_normalization",
        parameters=manifest["parameters"],
        inputs={
            "mapping_review": review_dir,
            "mapping_review_manifest": review_dir / "manifest.json",
            "mapping_review_receipt": (
                review_dir / "vendor_mapping_review_receipt.json"
            ),
            "vendor_source": source_path,
            "reviewed_mapping": mapping_path,
        },
        extra=manifest["extra"],
    )
    verification = verify_reviewed_mapped_data_normalization(normalization_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.mapping_review_current
    assert verification.source_current
    assert verification.reviewed_mapping_current
    assert not verification.artifacts_consistent

    catalog = catalog_experiment_runs([normalization_dir])
    row = catalog.catalog.iloc[0]
    assert row["reviewed_mapped_data_verification_status"] == "stale_or_inconsistent"
    assert not bool(row["summary_status"])


def test_reviewed_normalization_rejects_output_inside_review(tmp_path):
    review_dir, _, _ = _mapping_review(tmp_path, "collision")

    with pytest.raises(ValueError, match="cannot modify mapping-review evidence"):
        write_reviewed_mapped_data_normalization(
            review_dir,
            output_dir=review_dir / "normalization",
            config=ReviewedMappedDataConfig(timestamp_unit="datetime"),
        )


def test_reviewed_normalization_rejects_unsafe_output_filename(tmp_path):
    review_dir, _, _ = _mapping_review(tmp_path, "unsafe_output")

    with pytest.raises(ValueError, match="must be a filename"):
        write_reviewed_mapped_data_normalization(
            review_dir,
            output_dir=tmp_path / "unsafe_normalization",
            config=ReviewedMappedDataConfig(
                output_filename="nested/normalized.csv",
                timestamp_unit="datetime",
            ),
        )


def _mapping_review(
    tmp_path: Path,
    label: str,
    *,
    timestamp: str = "2026-07-14 09:15:00",
    decision: str = "approved",
) -> tuple[Path, Path, Path]:
    source_path = tmp_path / f"{label}_ticks.csv"
    intake_dir = tmp_path / f"{label}_intake"
    mapping_path = tmp_path / f"{label}_mapping.csv"
    decision_path = tmp_path / f"{label}_decision.csv"
    review_dir = tmp_path / f"{label}_review"
    pd.DataFrame(
        [
            {
                "exchange_ts": timestamp,
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
                "decision": decision,
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
                    if decision == "approved"
                    else "Operator rejected this mapping."
                ),
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(decision_path, index=False)
    write_vendor_mapping_review(
        intake_dir,
        mapping_path,
        decision_path,
        review_dir,
    )
    return review_dir, source_path, review_dir / "reviewed_vendor_mapping.csv"
