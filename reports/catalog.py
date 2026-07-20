from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from adapters.applied_mapped_data import (
    RUN_TYPE as APPLIED_MAPPED_DATA_RUN_TYPE,
    verify_applied_mapped_data_normalization,
)
from adapters.vendor_intake import (
    RUN_TYPE as VENDOR_CSV_INTAKE_RUN_TYPE,
    verify_vendor_csv_intake_report,
)
from adapters.vendor_mapping_review import (
    RUN_TYPE as VENDOR_MAPPING_REVIEW_RUN_TYPE,
    verify_vendor_mapping_review,
)
from adapters.reviewed_mapped_data import (
    RUN_TYPE as REVIEWED_MAPPED_DATA_RUN_TYPE,
    verify_reviewed_mapped_data_normalization,
)
from adapters.vendor_mapping_application import (
    RUN_TYPE as VENDOR_MAPPING_APPLICATION_RUN_TYPE,
    verify_vendor_mapping_application,
)
from adapters.vendor_mapping_scope_review import (
    RUN_TYPE as VENDOR_MAPPING_SCOPE_REVIEW_RUN_TYPE,
    verify_vendor_mapping_scope_review,
)
from reports.evidence import (
    PROVIDER_BROKER_REHEARSAL_CERTIFICATE_RUN_TYPE,
    verify_strategy_evidence_review,
)
from reports.manifest import MANIFEST_NAME, file_sha256, write_experiment_manifest
from reports.provider_market_data_imbalance_broker_active_lineage import (
    verified_provider_broker_active_lineage_records,
)
from reports.provider_market_data_imbalance_active_lineage_chain import (
    verified_provider_market_data_imbalance_active_lineage_chain_audit_records,
)
from reports.provider_market_data_imbalance_release_review import (
    RUN_TYPE as PROVIDER_RELEASE_REVIEW_RUN_TYPE,
    verify_provider_market_data_imbalance_release_review,
)
from reports.provider_market_data_imbalance_release_decision import (
    RUN_TYPE as PROVIDER_RELEASE_DECISION_RUN_TYPE,
    verify_provider_market_data_imbalance_release_decision,
)
from reports.provider_market_data_imbalance_live_dryrun_handoff import (
    RUN_TYPE as PROVIDER_LIVE_DRYRUN_HANDOFF_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_handoff,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_preflight import (
    RUN_TYPE as PROVIDER_LIVE_DRYRUN_RUNTIME_PREFLIGHT_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    RUN_TYPE as PROVIDER_LIVE_DRYRUN_RUNTIME_LAUNCHER_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator import (
    RUN_TYPE as PROVIDER_LIVE_DRYRUN_SHADOW_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration import (
    RUN_TYPE as PROVIDER_LIVE_DRYRUN_SHADOW_CALIBRATION_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_shadow_calibration,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration_stability import (
    RUN_TYPE as PROVIDER_LIVE_DRYRUN_SHADOW_CALIBRATION_STABILITY_RUN_TYPE,
    verify_provider_shadow_calibration_stability,
)


SUMMARY_FILES = [
    "parity_edge_summary.csv",
    "parity_order_summary.csv",
    "parity_launch_pipeline_summary.csv",
    "leadlag_measure_summary.csv",
    "leadlag_edge_summary.csv",
    "leadlag_replay_walkforward_summary.csv",
    "leadlag_order_summary.csv",
    "leadlag_launch_pipeline_summary.csv",
    "imbalance_edge_summary.csv",
    "imbalance_edge_sweep_summary.csv",
    "imbalance_edge_selection_summary.csv",
    "imbalance_edge_walkforward_summary.csv",
    "imbalance_replay_walkforward_summary.csv",
    "imbalance_order_summary.csv",
    "imbalance_launch_pipeline_summary.csv",
    "imbalance_pipeline_summary.csv",
    "robust_selection_pipeline_summary.csv",
    "surface_mm_pipeline_summary.csv",
    "surface_mm_launch_pipeline_summary.csv",
    "settlement_convergence_walkforward_summary.csv",
    "settlement_launch_pipeline_summary.csv",
    "settlement_convergence_summary.csv",
    "settlement_order_summary.csv",
    "proof_summary.csv",
    "backtest_overfit_summary.csv",
    "backtest_significance_summary.csv",
    "backtest_holdout_summary.csv",
    "walkforward_split_summary.csv",
    "research_family_summary.csv",
    "research_family_registration_summary.csv",
    "research_family_launch_summary.csv",
    "proof_refresh_summary.csv",
    "strategy_evidence_summary.csv",
    "strategy_scorecard_summary.csv",
    "strategy_portfolio_summary.csv",
    "scaleup_summary.csv",
    "market_profile_summary.csv",
    "market_portability_summary.csv",
    "route_readiness_summary.csv",
    "instrument_metadata_summary.csv",
    "vendor_market_data_batch_summary.csv",
    "vendor_market_data_pipeline_summary.csv",
    "data_readiness_summary.csv",
    "data_readiness_comparison_summary.csv",
    "diagnostic_summary.csv",
    "mapped_data_summary.csv",
    "stress_summary.csv",
    "selection_summary.csv",
    "promotion_summary.csv",
    "launch_summary.csv",
    "broker_order_summary.csv",
    "broker_upload_summary.csv",
    "broker_readiness_summary.csv",
    "broker_vendor_data_readiness_summary.csv",
    "mapped_order_summary.csv",
    "order_mapping_draft_summary.csv",
    "reconciliation_summary.csv",
    "shadow_session_summary.csv",
    "shadow_session_comparison_summary.csv",
    "runtime_telemetry_summary.csv",
    "runtime_guard_summary.csv",
    "runtime_session_summary.csv",
    "cutover_summary.csv",
    "route_enable_summary.csv",
    "broker_dispatch_summary.csv",
    "broker_dispatch_send_summary.csv",
    "broker_dispatch_ack_summary.csv",
    "broker_dispatch_roundtrip_summary.csv",
    "provider_market_data_research_handoff_summary.csv",
    "provider_market_data_imbalance_research_summary.csv",
    "provider_market_data_imbalance_evidence_summary.csv",
    "provider_market_data_imbalance_launch_summary.csv",
    "provider_market_data_imbalance_launch_evidence_summary.csv",
    "provider_market_data_imbalance_scorecard_summary.csv",
    "provider_market_data_imbalance_route_readiness_summary.csv",
    "provider_market_data_imbalance_scaleup_summary.csv",
    "provider_market_data_imbalance_runtime_telemetry_summary.csv",
    "provider_market_data_imbalance_runtime_guard_summary.csv",
    "provider_market_data_imbalance_runtime_session_summary.csv",
    "provider_market_data_imbalance_broker_readiness_summary.csv",
    "provider_market_data_imbalance_cutover_summary.csv",
    "provider_market_data_imbalance_route_enable_summary.csv",
    "provider_market_data_imbalance_broker_dispatch_summary.csv",
    "provider_market_data_imbalance_broker_dispatch_send_summary.csv",
    "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
    "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
    "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
    "provider_market_data_imbalance_release_review_summary.csv",
    "provider_market_data_imbalance_release_decision_summary.csv",
    "provider_market_data_imbalance_live_dryrun_handoff_summary.csv",
    "provider_market_data_imbalance_live_dryrun_runtime_preflight_summary.csv",
    "provider_market_data_imbalance_live_dryrun_runtime_launcher_summary.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_summary.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_summary.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_stability_summary.csv",
    "provider_broker_lineage_migration_summary.csv",
    "provider_broker_lineage_audit_usage_summary.csv",
    "provider_broker_lineage_refresh_convergence_summary.csv",
    "provider_broker_active_lineage_summary.csv",
    "halt_response_summary.csv",
    "halt_response_export_summary.csv",
    "halt_execution_summary.csv",
    "halt_incident_summary.csv",
    "resume_summary.csv",
    "surface_quality_summary.csv",
    "quote_risk_summary.csv",
    "quote_lifecycle_summary.csv",
    "order_exposure_summary.csv",
    "staged_order_summary.csv",
    "fill_model_summary.csv",
    "fill_model_drift_summary.csv",
    "calibrated_replay_summary.csv",
    "adapter_schema_summary.csv",
    "vendor_mapping_review_summary.csv",
    "vendor_mapping_scope_review_summary.csv",
    "vendor_mapping_application_summary.csv",
    "vendor_intake_summary.csv",
    "surface_quote_summary.csv",
    "sweep_summary.csv",
    "summary.csv",
    "calibration_summary.csv",
]

PLACEHOLDER_SCHEMA_STATUS = "placeholder_normalized_pending_vendor_schema"

STATUS_COLUMNS = [
    "passed",
    "all_passed",
    "ready",
    "accepted",
    "all_scenarios_passed",
    "has_selection",
    "selection_passed",
    "all_required_present",
]

PROVIDER_BROKER_LINEAGE_RUN_TYPES = {
    "provider_market_data_imbalance_broker_dispatch_ack": "provider_ack",
    "provider_market_data_imbalance_broker_dispatch_roundtrip": (
        "provider_roundtrip"
    ),
    "provider_market_data_imbalance_broker_rehearsal_certificate": (
        "rehearsal_certificate"
    ),
}


@dataclass(frozen=True)
class ExperimentCatalog:
    catalog: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    hygiene_gaps: pd.DataFrame | None = None

    @property
    def run_count(self) -> int:
        return int(len(self.catalog))


def catalog_experiment_runs(
    roots: list[str | Path],
    *,
    provider_broker_active_lineage_index: str | Path | None = None,
    provider_active_lineage_chain_audits: list[str | Path] | None = None,
) -> ExperimentCatalog:
    if not roots:
        raise ValueError("at least one experiment root is required")
    manifests = _manifest_paths(roots)
    lineage_records = (
        None
        if provider_broker_active_lineage_index is None
        else verified_provider_broker_active_lineage_records(
            provider_broker_active_lineage_index
        )
    )
    chain_audit_records = (
        None
        if provider_active_lineage_chain_audits is None
        else verified_provider_market_data_imbalance_active_lineage_chain_audit_records(
            provider_active_lineage_chain_audits
        )
    )
    rows = [
        _catalog_row(
            path,
            lineage_records=lineage_records,
            chain_audit_records=chain_audit_records,
        )
        for path in manifests
    ]
    catalog = pd.DataFrame(rows)
    action_queue = _catalog_action_queue(catalog)
    hygiene_gaps = _catalog_hygiene_gaps(catalog)
    summary = _catalog_summary(catalog, action_queue, hygiene_gaps)
    return ExperimentCatalog(
        catalog=catalog,
        summary=summary,
        action_queue=action_queue,
        hygiene_gaps=hygiene_gaps,
    )


def write_experiment_catalog(
    roots: list[str | Path],
    *,
    output_dir: str | Path,
    provider_broker_active_lineage_index: str | Path | None = None,
    provider_active_lineage_chain_audits: list[str | Path] | None = None,
) -> ExperimentCatalog:
    report = catalog_experiment_runs(
        roots,
        provider_broker_active_lineage_index=(
            provider_broker_active_lineage_index
        ),
        provider_active_lineage_chain_audits=(
            provider_active_lineage_chain_audits
        ),
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.catalog.to_csv(out / "experiment_catalog.csv", index=False)
    report.summary.to_csv(out / "experiment_catalog_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _catalog_action_queue(report.catalog)
    hygiene_gaps = report.hygiene_gaps if report.hygiene_gaps is not None else _catalog_hygiene_gaps(report.catalog)
    action_queue.to_csv(out / "experiment_catalog_action_queue.csv", index=False)
    hygiene_gaps.to_csv(out / "experiment_catalog_hygiene_gaps.csv", index=False)
    (out / "experiment_catalog_action_plan.json").write_text(
        json.dumps(
            _catalog_action_plan(report.summary.iloc[0], action_queue, hygiene_gaps),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "experiment_catalog_runbook.md").write_text(
        _catalog_runbook_markdown(report.summary.iloc[0], action_queue, hygiene_gaps),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="experiment_catalog",
        parameters={
            "roots": [str(Path(root)) for root in roots],
            "provider_broker_active_lineage_index": (
                ""
                if provider_broker_active_lineage_index is None
                else str(Path(provider_broker_active_lineage_index).resolve())
            ),
            "provider_active_lineage_chain_audits": [
                str(Path(path).resolve())
                for path in (provider_active_lineage_chain_audits or [])
            ],
        },
        inputs={
            "roots": [Path(root) for root in roots],
            **(
                {}
                if provider_broker_active_lineage_index is None
                else {
                    "provider_broker_active_lineage_index": Path(
                        provider_broker_active_lineage_index
                    ).resolve()
                }
            ),
            **(
                {}
                if provider_active_lineage_chain_audits is None
                else {
                    "provider_active_lineage_chain_audits": [
                        Path(path).resolve()
                        for path in provider_active_lineage_chain_audits
                    ],
                    "provider_active_lineage_chain_audit_manifests": [
                        Path(path).resolve() / MANIFEST_NAME
                        for path in provider_active_lineage_chain_audits
                    ],
                }
            ),
        },
    )
    return ExperimentCatalog(report.catalog, report.summary, out, action_queue, hygiene_gaps)


def _manifest_paths(roots: list[str | Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        path = Path(root)
        if path.is_file():
            candidates = [path] if path.name == MANIFEST_NAME else []
        elif path.exists():
            candidates = sorted(path.rglob(MANIFEST_NAME))
        else:
            raise FileNotFoundError(f"experiment root not found: {path}")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return sorted(paths)


def _catalog_row(
    manifest_path: Path,
    *,
    lineage_records: pd.DataFrame | None = None,
    chain_audit_records: pd.DataFrame | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_dir = manifest_path.parent
    summary_file, summary_row = _summary_row(run_dir)
    status_column, status = _summary_status(summary_row)
    strategy_evidence_verification = _strategy_evidence_verification_fields(
        run_dir,
        str(manifest.get("run_type", "")),
        manifest,
        summary_row,
    )
    provider_release_review_verification = (
        _provider_release_review_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_release_decision_verification = (
        _provider_release_decision_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_live_dryrun_handoff_verification = (
        _provider_live_dryrun_handoff_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_live_dryrun_runtime_preflight_verification = (
        _provider_live_dryrun_runtime_preflight_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_live_dryrun_runtime_launcher_verification = (
        _provider_live_dryrun_runtime_launcher_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_live_dryrun_shadow_verification = (
        _provider_live_dryrun_shadow_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_live_dryrun_shadow_calibration_verification = (
        _provider_live_dryrun_shadow_calibration_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    provider_live_dryrun_shadow_calibration_stability_verification = (
        _provider_live_dryrun_shadow_calibration_stability_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    vendor_intake_verification = _vendor_intake_verification_fields(
        run_dir,
        str(manifest.get("run_type", "")),
    )
    vendor_mapping_review_verification = (
        _vendor_mapping_review_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    reviewed_mapped_data_verification = _reviewed_mapped_data_verification_fields(
        run_dir,
        str(manifest.get("run_type", "")),
    )
    applied_mapped_data_verification = _applied_mapped_data_verification_fields(
        run_dir,
        str(manifest.get("run_type", "")),
    )
    vendor_mapping_scope_review_verification = (
        _vendor_mapping_scope_review_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    vendor_mapping_application_verification = (
        _vendor_mapping_application_verification_fields(
            run_dir,
            str(manifest.get("run_type", "")),
        )
    )
    if (
        strategy_evidence_verification[
            "strategy_evidence_verification_required"
        ]
        and not strategy_evidence_verification[
            "strategy_evidence_verification_verified"
        ]
    ):
        status_column = "strategy_evidence_verification"
        status = False
    if (
        provider_release_review_verification[
            "provider_release_review_verification_required"
        ]
        and not provider_release_review_verification[
            "provider_release_review_verification_verified"
        ]
    ):
        status_column = "provider_release_review_verification"
        status = False
    if (
        provider_release_decision_verification[
            "provider_release_decision_verification_required"
        ]
        and not provider_release_decision_verification[
            "provider_release_decision_verification_verified"
        ]
    ):
        status_column = "provider_release_decision_verification"
        status = False
    if (
        provider_live_dryrun_handoff_verification[
            "provider_live_dryrun_handoff_verification_required"
        ]
        and not provider_live_dryrun_handoff_verification[
            "provider_live_dryrun_handoff_verification_verified"
        ]
    ):
        status_column = "provider_live_dryrun_handoff_verification"
        status = False
    if (
        provider_live_dryrun_runtime_preflight_verification[
            "provider_live_dryrun_runtime_preflight_verification_required"
        ]
        and not provider_live_dryrun_runtime_preflight_verification[
            "provider_live_dryrun_runtime_preflight_verification_verified"
        ]
    ):
        status_column = "provider_live_dryrun_runtime_preflight_verification"
        status = False
    if (
        provider_live_dryrun_runtime_launcher_verification[
            "provider_live_dryrun_runtime_launcher_verification_required"
        ]
        and not provider_live_dryrun_runtime_launcher_verification[
            "provider_live_dryrun_runtime_launcher_verification_verified"
        ]
    ):
        status_column = "provider_live_dryrun_runtime_launcher_verification"
        status = False
    if (
        provider_live_dryrun_shadow_verification[
            "provider_live_dryrun_shadow_verification_required"
        ]
        and not provider_live_dryrun_shadow_verification[
            "provider_live_dryrun_shadow_verification_verified"
        ]
    ):
        status_column = "provider_live_dryrun_shadow_verification"
        status = False
    if (
        provider_live_dryrun_shadow_calibration_verification[
            "provider_live_dryrun_shadow_calibration_verification_required"
        ]
        and not provider_live_dryrun_shadow_calibration_verification[
            "provider_live_dryrun_shadow_calibration_verification_verified"
        ]
    ):
        status_column = (
            "provider_live_dryrun_shadow_calibration_verification"
        )
        status = False
    if (
        provider_live_dryrun_shadow_calibration_stability_verification[
            "provider_live_dryrun_shadow_calibration_stability_verification_required"
        ]
        and not provider_live_dryrun_shadow_calibration_stability_verification[
            "provider_live_dryrun_shadow_calibration_stability_verification_verified"
        ]
    ):
        status_column = (
            "provider_live_dryrun_shadow_calibration_stability_verification"
        )
        status = False
    if (
        vendor_intake_verification["vendor_intake_verification_required"]
        and not vendor_intake_verification["vendor_intake_verification_verified"]
    ):
        status_column = "vendor_intake_verification"
        status = False
    if (
        vendor_mapping_review_verification[
            "vendor_mapping_review_verification_required"
        ]
        and not vendor_mapping_review_verification[
            "vendor_mapping_review_verification_verified"
        ]
    ):
        status_column = "vendor_mapping_review_verification"
        status = False
    if (
        reviewed_mapped_data_verification[
            "reviewed_mapped_data_verification_required"
        ]
        and not reviewed_mapped_data_verification[
            "reviewed_mapped_data_verification_verified"
        ]
    ):
        status_column = "reviewed_mapped_data_verification"
        status = False
    if (
        applied_mapped_data_verification[
            "applied_mapped_data_verification_required"
        ]
        and not applied_mapped_data_verification[
            "applied_mapped_data_verification_verified"
        ]
    ):
        status_column = "applied_mapped_data_verification"
        status = False
    if (
        vendor_mapping_scope_review_verification[
            "vendor_mapping_scope_review_verification_required"
        ]
        and not vendor_mapping_scope_review_verification[
            "vendor_mapping_scope_review_verification_verified"
        ]
    ):
        status_column = "vendor_mapping_scope_review_verification"
        status = False
    if (
        vendor_mapping_application_verification[
            "vendor_mapping_application_verification_required"
        ]
        and not vendor_mapping_application_verification[
            "vendor_mapping_application_verification_verified"
        ]
    ):
        status_column = "vendor_mapping_application_verification"
        status = False
    inputs = manifest.get("inputs", {}) or {}
    input_stats = _input_stats(inputs)
    row = {
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "run_type": manifest.get("run_type", ""),
        "generated_at_utc": manifest.get("generated_at_utc", ""),
        "git_branch": _nested(manifest, "git", "branch"),
        "git_commit": _nested(manifest, "git", "commit"),
        "git_dirty": _nested(manifest, "git", "dirty"),
        "artifact_count": len(manifest.get("artifacts", []) or []),
        "input_count": len(inputs),
        **input_stats,
        "summary_file": summary_file,
        "summary_status_column": status_column,
        "summary_status": status,
        "parameters_json": json.dumps(manifest.get("parameters", {}), sort_keys=True),
        "inputs_json": json.dumps(inputs, sort_keys=True),
        **strategy_evidence_verification,
        **provider_release_review_verification,
        **provider_release_decision_verification,
        **provider_live_dryrun_handoff_verification,
        **provider_live_dryrun_runtime_preflight_verification,
        **provider_live_dryrun_runtime_launcher_verification,
        **provider_live_dryrun_shadow_verification,
        **provider_live_dryrun_shadow_calibration_verification,
        **provider_live_dryrun_shadow_calibration_stability_verification,
        **vendor_intake_verification,
        **vendor_mapping_review_verification,
        **reviewed_mapped_data_verification,
        **applied_mapped_data_verification,
        **vendor_mapping_scope_review_verification,
        **vendor_mapping_application_verification,
        **_provider_lineage_selection_fields(
            run_dir,
            str(manifest.get("run_type", "")),
            lineage_records,
            chain_audit_records,
        ),
    }
    for column, value in summary_row.items():
        key = f"summary_{column}"
        if key in row:
            row[f"summary_reported_{column}"] = value
        else:
            row[key] = value
    return row


def _vendor_intake_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == VENDOR_CSV_INTAKE_RUN_TYPE
    prefix = "vendor_intake_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": "verification_required" if required else "not_applicable",
        f"{prefix}verified": False,
        f"{prefix}ready": False,
        f"{prefix}blocked": False,
        f"{prefix}manifest_current": False,
        f"{prefix}source_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}intake_only": False,
        f"{prefix}non_authorizing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_vendor_csv_intake_report(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = "verified_ready" if verification.ready else "verified_blocked"
    fields.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}ready": verification.ready,
            f"{prefix}blocked": verification.blocked,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}source_current": verification.source_current,
            f"{prefix}artifacts_consistent": verification.artifacts_consistent,
            f"{prefix}intake_only": verification.intake_only,
            f"{prefix}non_authorizing": verification.non_authorizing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _vendor_mapping_review_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == VENDOR_MAPPING_REVIEW_RUN_TYPE
    prefix = "vendor_mapping_review_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": "verification_required" if required else "not_applicable",
        f"{prefix}verified": False,
        f"{prefix}sealed": False,
        f"{prefix}approved": False,
        f"{prefix}rejected": False,
        f"{prefix}manifest_current": False,
        f"{prefix}intake_current": False,
        f"{prefix}mapping_candidate_current": False,
        f"{prefix}operator_decision_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}normalization_only": False,
        f"{prefix}non_routing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_vendor_mapping_review(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = "verified_approved" if verification.approved else "verified_rejected"
    fields.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}sealed": verification.sealed,
            f"{prefix}approved": verification.approved,
            f"{prefix}rejected": verification.rejected,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}intake_current": verification.intake_current,
            f"{prefix}mapping_candidate_current": (
                verification.mapping_candidate_current
            ),
            f"{prefix}operator_decision_current": (
                verification.operator_decision_current
            ),
            f"{prefix}artifacts_consistent": verification.artifacts_consistent,
            f"{prefix}normalization_only": verification.normalization_only,
            f"{prefix}non_routing": verification.non_routing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _reviewed_mapped_data_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == REVIEWED_MAPPED_DATA_RUN_TYPE
    prefix = "reviewed_mapped_data_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": "verification_required" if required else "not_applicable",
        f"{prefix}verified": False,
        f"{prefix}ready": False,
        f"{prefix}blocked": False,
        f"{prefix}manifest_current": False,
        f"{prefix}mapping_review_current": False,
        f"{prefix}source_current": False,
        f"{prefix}reviewed_mapping_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}normalization_only": False,
        f"{prefix}non_routing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_reviewed_mapped_data_normalization(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = "verified_ready" if verification.ready else "verified_blocked"
    fields.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}ready": verification.ready,
            f"{prefix}blocked": verification.blocked,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}mapping_review_current": verification.mapping_review_current,
            f"{prefix}source_current": verification.source_current,
            f"{prefix}reviewed_mapping_current": (
                verification.reviewed_mapping_current
            ),
            f"{prefix}artifacts_consistent": verification.artifacts_consistent,
            f"{prefix}normalization_only": verification.normalization_only,
            f"{prefix}non_routing": verification.non_routing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _applied_mapped_data_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == APPLIED_MAPPED_DATA_RUN_TYPE
    prefix = "applied_mapped_data_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": "verification_required" if required else "not_applicable",
        f"{prefix}verified": False,
        f"{prefix}ready": False,
        f"{prefix}blocked": False,
        f"{prefix}manifest_current": False,
        f"{prefix}mapping_application_current": False,
        f"{prefix}source_current": False,
        f"{prefix}applied_mapping_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}target_bound": False,
        f"{prefix}normalization_only": False,
        f"{prefix}non_routing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_applied_mapped_data_normalization(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = "verified_ready" if verification.ready else "verified_blocked"
    fields.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}ready": verification.ready,
            f"{prefix}blocked": verification.blocked,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}mapping_application_current": (
                verification.mapping_application_current
            ),
            f"{prefix}source_current": verification.source_current,
            f"{prefix}applied_mapping_current": (
                verification.applied_mapping_current
            ),
            f"{prefix}artifacts_consistent": verification.artifacts_consistent,
            f"{prefix}target_bound": verification.target_bound,
            f"{prefix}normalization_only": verification.normalization_only,
            f"{prefix}non_routing": verification.non_routing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _vendor_mapping_scope_review_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == VENDOR_MAPPING_SCOPE_REVIEW_RUN_TYPE
    prefix = "vendor_mapping_scope_review_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": "verification_required" if required else "not_applicable",
        f"{prefix}verified": False,
        f"{prefix}sealed": False,
        f"{prefix}approved": False,
        f"{prefix}rejected": False,
        f"{prefix}manifest_current": False,
        f"{prefix}mapping_review_current": False,
        f"{prefix}operator_decision_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}application_only": False,
        f"{prefix}non_routing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_vendor_mapping_scope_review(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = "verified_approved" if verification.approved else "verified_rejected"
    fields.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}sealed": verification.sealed,
            f"{prefix}approved": verification.approved,
            f"{prefix}rejected": verification.rejected,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}mapping_review_current": verification.mapping_review_current,
            f"{prefix}operator_decision_current": (
                verification.operator_decision_current
            ),
            f"{prefix}artifacts_consistent": verification.artifacts_consistent,
            f"{prefix}application_only": verification.application_only,
            f"{prefix}non_routing": verification.non_routing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _vendor_mapping_application_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == VENDOR_MAPPING_APPLICATION_RUN_TYPE
    prefix = "vendor_mapping_application_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": "verification_required" if required else "not_applicable",
        f"{prefix}verified": False,
        f"{prefix}ready": False,
        f"{prefix}manifest_current": False,
        f"{prefix}scope_review_current": False,
        f"{prefix}target_intake_current": False,
        f"{prefix}target_source_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}target_bound": False,
        f"{prefix}application_only": False,
        f"{prefix}non_routing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_vendor_mapping_application(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    fields.update(
        {
            f"{prefix}status": (
                "verified_ready"
                if verification.verified and verification.ready
                else "stale_or_inconsistent"
            ),
            f"{prefix}verified": verification.verified,
            f"{prefix}ready": verification.ready,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}scope_review_current": verification.scope_review_current,
            f"{prefix}target_intake_current": verification.target_intake_current,
            f"{prefix}target_source_current": verification.target_source_current,
            f"{prefix}artifacts_consistent": verification.artifacts_consistent,
            f"{prefix}target_bound": verification.target_bound,
            f"{prefix}application_only": verification.application_only,
            f"{prefix}non_routing": verification.non_routing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _strategy_evidence_verification_fields(
    run_dir: Path,
    run_type: str,
    manifest: dict[str, Any],
    summary_row: dict[str, Any],
) -> dict[str, Any]:
    extra_value = manifest.get("extra", {})
    extra = extra_value if isinstance(extra_value, dict) else {}
    parameters_value = manifest.get("parameters", {})
    parameters = (
        parameters_value if isinstance(parameters_value, dict) else {}
    )
    thresholds_value = parameters.get("thresholds", {})
    thresholds = (
        thresholds_value if isinstance(thresholds_value, dict) else {}
    )
    required_run_types = thresholds.get("required_run_types", ())
    provider_contract_declared = bool(
        isinstance(required_run_types, (list, tuple))
        and PROVIDER_BROKER_REHEARSAL_CERTIFICATE_RUN_TYPE
        in {str(value) for value in required_run_types}
    )
    required = bool(
        run_type == "strategy_evidence_review"
        and (
            str(summary_row.get("evidence_profile", "")).strip().lower()
            == "provider_imbalance_ops_launch"
            or _to_bool(extra.get("source_catalog_manifest_required"))
            or provider_contract_declared
        )
    )
    fields: dict[str, Any] = {
        "strategy_evidence_verification_required": required,
        "strategy_evidence_verification_status": (
            "verification_required" if required else "not_applicable"
        ),
        "strategy_evidence_verification_verified": False,
        "strategy_evidence_verification_ready": False,
        "strategy_evidence_verification_manifest_current": False,
        "strategy_evidence_verification_source_current": False,
        "strategy_evidence_verification_artifacts_consistent": False,
        "strategy_evidence_verification_manifest_input_contract_current": False,
        "strategy_evidence_verification_provider_retained_proofs_current": False,
        "strategy_evidence_verification_non_authorizing": False,
        "strategy_evidence_verification_error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_strategy_evidence_review(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields["strategy_evidence_verification_status"] = (
            "verification_error"
        )
        fields["strategy_evidence_verification_error"] = str(exc)
        return fields
    fields.update(
        {
            "strategy_evidence_verification_status": (
                "verified_current"
                if verification.verified
                else "stale_or_inconsistent"
            ),
            "strategy_evidence_verification_verified": verification.verified,
            "strategy_evidence_verification_ready": verification.ready,
            "strategy_evidence_verification_manifest_current": (
                verification.manifest_current
            ),
            "strategy_evidence_verification_source_current": (
                verification.source_current
            ),
            "strategy_evidence_verification_artifacts_consistent": (
                verification.artifacts_consistent
            ),
            "strategy_evidence_verification_manifest_input_contract_current": (
                verification.manifest_input_contract_current
            ),
            "strategy_evidence_verification_provider_retained_proofs_current": (
                verification.provider_retained_proofs_current
            ),
            "strategy_evidence_verification_non_authorizing": (
                verification.non_authorizing
            ),
            "strategy_evidence_verification_error": verification.error,
        }
    )
    return fields


def _provider_release_review_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_RELEASE_REVIEW_RUN_TYPE
    fields: dict[str, Any] = {
        "provider_release_review_verification_required": required,
        "provider_release_review_verification_status": (
            "verification_required" if required else "not_applicable"
        ),
        "provider_release_review_verification_verified": False,
        "provider_release_review_verification_ready": False,
        "provider_release_review_verification_manifest_current": False,
        "provider_release_review_verification_source_current": False,
        "provider_release_review_verification_artifacts_consistent": False,
        "provider_release_review_verification_non_authorizing": False,
        "provider_release_review_verification_operator_approval_pending": False,
        "provider_release_review_verification_error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_provider_market_data_imbalance_release_review(
            run_dir
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields["provider_release_review_verification_status"] = (
            "verification_error"
        )
        fields["provider_release_review_verification_error"] = str(exc)
        return fields
    fields.update(
        {
            "provider_release_review_verification_status": (
                "verified_current"
                if verification.verified
                else "stale_or_inconsistent"
            ),
            "provider_release_review_verification_verified": (
                verification.verified
            ),
            "provider_release_review_verification_ready": verification.ready,
            "provider_release_review_verification_manifest_current": (
                verification.manifest_current
            ),
            "provider_release_review_verification_source_current": (
                verification.source_current
            ),
            "provider_release_review_verification_artifacts_consistent": (
                verification.artifacts_consistent
            ),
            "provider_release_review_verification_non_authorizing": (
                verification.non_authorizing
            ),
            "provider_release_review_verification_operator_approval_pending": (
                verification.operator_approval_pending
            ),
            "provider_release_review_verification_error": verification.error,
        }
    )
    return fields


def _provider_release_decision_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_RELEASE_DECISION_RUN_TYPE
    fields: dict[str, Any] = {
        "provider_release_decision_verification_required": required,
        "provider_release_decision_verification_status": (
            "verification_required" if required else "not_applicable"
        ),
        "provider_release_decision_verification_verified": False,
        "provider_release_decision_verification_sealed": False,
        "provider_release_decision_verification_approved": False,
        "provider_release_decision_verification_ready": False,
        "provider_release_decision_verification_manifest_current": False,
        "provider_release_decision_verification_release_review_current": False,
        "provider_release_decision_verification_operator_decision_current": False,
        "provider_release_decision_verification_artifacts_consistent": False,
        "provider_release_decision_verification_non_authorizing": False,
        "provider_release_decision_verification_error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_provider_market_data_imbalance_release_decision(
            run_dir
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields["provider_release_decision_verification_status"] = (
            "verification_error"
        )
        fields["provider_release_decision_verification_error"] = str(exc)
        return fields
    fields.update(
        {
            "provider_release_decision_verification_status": (
                "verified_approved"
                if verification.verified and verification.approved
                else (
                    "verified_rejected"
                    if verification.verified
                    else "stale_or_inconsistent"
                )
            ),
            "provider_release_decision_verification_verified": (
                verification.verified
            ),
            "provider_release_decision_verification_sealed": (
                verification.sealed
            ),
            "provider_release_decision_verification_approved": (
                verification.approved
            ),
            "provider_release_decision_verification_ready": (
                verification.ready
            ),
            "provider_release_decision_verification_manifest_current": (
                verification.manifest_current
            ),
            "provider_release_decision_verification_release_review_current": (
                verification.release_review_current
            ),
            "provider_release_decision_verification_operator_decision_current": (
                verification.operator_decision_current
            ),
            "provider_release_decision_verification_artifacts_consistent": (
                verification.artifacts_consistent
            ),
            "provider_release_decision_verification_non_authorizing": (
                verification.non_authorizing
            ),
            "provider_release_decision_verification_error": verification.error,
        }
    )
    return fields


def _provider_live_dryrun_handoff_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_LIVE_DRYRUN_HANDOFF_RUN_TYPE
    fields: dict[str, Any] = {
        "provider_live_dryrun_handoff_verification_required": required,
        "provider_live_dryrun_handoff_verification_status": (
            "verification_required" if required else "not_applicable"
        ),
        "provider_live_dryrun_handoff_verification_verified": False,
        "provider_live_dryrun_handoff_verification_ready": False,
        "provider_live_dryrun_handoff_verification_manifest_current": False,
        "provider_live_dryrun_handoff_verification_release_decision_current": False,
        "provider_live_dryrun_handoff_verification_runtime_controls_current": False,
        "provider_live_dryrun_handoff_verification_rollback_runbook_current": False,
        "provider_live_dryrun_handoff_verification_artifacts_consistent": False,
        "provider_live_dryrun_handoff_verification_non_authorizing": False,
        "provider_live_dryrun_handoff_verification_error": "",
    }
    if not required:
        return fields
    try:
        verification = verify_provider_market_data_imbalance_live_dryrun_handoff(
            run_dir
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields["provider_live_dryrun_handoff_verification_status"] = (
            "verification_error"
        )
        fields["provider_live_dryrun_handoff_verification_error"] = str(exc)
        return fields
    fields.update(
        {
            "provider_live_dryrun_handoff_verification_status": (
                "verified_current"
                if verification.verified
                else "stale_or_inconsistent"
            ),
            "provider_live_dryrun_handoff_verification_verified": (
                verification.verified
            ),
            "provider_live_dryrun_handoff_verification_ready": verification.ready,
            "provider_live_dryrun_handoff_verification_manifest_current": (
                verification.manifest_current
            ),
            "provider_live_dryrun_handoff_verification_release_decision_current": (
                verification.release_decision_current
            ),
            "provider_live_dryrun_handoff_verification_runtime_controls_current": (
                verification.runtime_controls_current
            ),
            "provider_live_dryrun_handoff_verification_rollback_runbook_current": (
                verification.rollback_runbook_current
            ),
            "provider_live_dryrun_handoff_verification_artifacts_consistent": (
                verification.artifacts_consistent
            ),
            "provider_live_dryrun_handoff_verification_non_authorizing": (
                verification.non_authorizing
            ),
            "provider_live_dryrun_handoff_verification_error": verification.error,
        }
    )
    return fields


def _provider_live_dryrun_runtime_preflight_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_LIVE_DRYRUN_RUNTIME_PREFLIGHT_RUN_TYPE
    fields: dict[str, Any] = {
        "provider_live_dryrun_runtime_preflight_verification_required": required,
        "provider_live_dryrun_runtime_preflight_verification_status": (
            "verification_required" if required else "not_applicable"
        ),
        "provider_live_dryrun_runtime_preflight_verification_verified": False,
        "provider_live_dryrun_runtime_preflight_verification_ready": False,
        "provider_live_dryrun_runtime_preflight_verification_manifest_current": False,
        "provider_live_dryrun_runtime_preflight_verification_handoff_current": False,
        "provider_live_dryrun_runtime_preflight_verification_runtime_profile_current": False,
        "provider_live_dryrun_runtime_preflight_verification_artifacts_consistent": False,
        "provider_live_dryrun_runtime_preflight_verification_credential_safe": False,
        "provider_live_dryrun_runtime_preflight_verification_non_authorizing": False,
        "provider_live_dryrun_runtime_preflight_verification_error": "",
    }
    if not required:
        return fields
    try:
        verification = (
            verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
                run_dir
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[
            "provider_live_dryrun_runtime_preflight_verification_status"
        ] = "verification_error"
        fields[
            "provider_live_dryrun_runtime_preflight_verification_error"
        ] = str(exc)
        return fields
    fields.update(
        {
            "provider_live_dryrun_runtime_preflight_verification_status": (
                "verified_ready"
                if verification.verified and verification.ready
                else (
                    "verified_blocked"
                    if verification.verified
                    else "stale_or_inconsistent"
                )
            ),
            "provider_live_dryrun_runtime_preflight_verification_verified": (
                verification.verified
            ),
            "provider_live_dryrun_runtime_preflight_verification_ready": (
                verification.ready
            ),
            "provider_live_dryrun_runtime_preflight_verification_manifest_current": (
                verification.manifest_current
            ),
            "provider_live_dryrun_runtime_preflight_verification_handoff_current": (
                verification.handoff_current
            ),
            "provider_live_dryrun_runtime_preflight_verification_runtime_profile_current": (
                verification.runtime_profile_current
            ),
            "provider_live_dryrun_runtime_preflight_verification_artifacts_consistent": (
                verification.artifacts_consistent
            ),
            "provider_live_dryrun_runtime_preflight_verification_credential_safe": (
                verification.credential_safe
            ),
            "provider_live_dryrun_runtime_preflight_verification_non_authorizing": (
                verification.non_authorizing
            ),
            "provider_live_dryrun_runtime_preflight_verification_error": (
                verification.error
            ),
        }
    )
    return fields


def _provider_live_dryrun_runtime_launcher_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_LIVE_DRYRUN_RUNTIME_LAUNCHER_RUN_TYPE
    fields: dict[str, Any] = {
        "provider_live_dryrun_runtime_launcher_verification_required": required,
        "provider_live_dryrun_runtime_launcher_verification_status": (
            "verification_required" if required else "not_applicable"
        ),
        "provider_live_dryrun_runtime_launcher_verification_verified": False,
        "provider_live_dryrun_runtime_launcher_verification_completed": False,
        "provider_live_dryrun_runtime_launcher_verification_halted": False,
        "provider_live_dryrun_runtime_launcher_verification_manifest_current": False,
        "provider_live_dryrun_runtime_launcher_verification_preflight_current": False,
        "provider_live_dryrun_runtime_launcher_verification_handoff_current": False,
        "provider_live_dryrun_runtime_launcher_verification_artifacts_consistent": False,
        "provider_live_dryrun_runtime_launcher_verification_simulation_only": False,
        "provider_live_dryrun_runtime_launcher_verification_non_authorizing": False,
        "provider_live_dryrun_runtime_launcher_verification_error": "",
    }
    if not required:
        return fields
    try:
        verification = (
            verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
                run_dir
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[
            "provider_live_dryrun_runtime_launcher_verification_status"
        ] = "verification_error"
        fields[
            "provider_live_dryrun_runtime_launcher_verification_error"
        ] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = (
            "verified_completed"
            if verification.completed
            else (
                "verified_halted"
                if verification.halted
                else "verified_incomplete"
            )
        )
    fields.update(
        {
            "provider_live_dryrun_runtime_launcher_verification_status": status,
            "provider_live_dryrun_runtime_launcher_verification_verified": (
                verification.verified
            ),
            "provider_live_dryrun_runtime_launcher_verification_completed": (
                verification.completed
            ),
            "provider_live_dryrun_runtime_launcher_verification_halted": (
                verification.halted
            ),
            "provider_live_dryrun_runtime_launcher_verification_manifest_current": (
                verification.manifest_current
            ),
            "provider_live_dryrun_runtime_launcher_verification_preflight_current": (
                verification.preflight_current
            ),
            "provider_live_dryrun_runtime_launcher_verification_handoff_current": (
                verification.handoff_current
            ),
            "provider_live_dryrun_runtime_launcher_verification_artifacts_consistent": (
                verification.artifacts_consistent
            ),
            "provider_live_dryrun_runtime_launcher_verification_simulation_only": (
                verification.simulation_only
            ),
            "provider_live_dryrun_runtime_launcher_verification_non_authorizing": (
                verification.non_authorizing
            ),
            "provider_live_dryrun_runtime_launcher_verification_error": (
                verification.error
            ),
        }
    )
    return fields


def _provider_live_dryrun_shadow_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_LIVE_DRYRUN_SHADOW_RUN_TYPE
    prefix = "provider_live_dryrun_shadow_verification_"
    fields: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": (
            "verification_required" if required else "not_applicable"
        ),
        f"{prefix}verified": False,
        f"{prefix}completed": False,
        f"{prefix}halted": False,
        f"{prefix}manifest_current": False,
        f"{prefix}launcher_current": False,
        f"{prefix}handoff_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}shadow_only": False,
        f"{prefix}non_authorizing": False,
        f"{prefix}error": "",
    }
    if not required:
        return fields
    try:
        verification = (
            verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
                run_dir
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fields[f"{prefix}status"] = "verification_error"
        fields[f"{prefix}error"] = str(exc)
        return fields
    status = "stale_or_inconsistent"
    if verification.verified:
        status = (
            "verified_completed"
            if verification.completed
            else (
                "verified_halted"
                if verification.halted
                else "verified_incomplete"
            )
        )
    fields.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}completed": verification.completed,
            f"{prefix}halted": verification.halted,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}launcher_current": verification.launcher_current,
            f"{prefix}handoff_current": verification.handoff_current,
            f"{prefix}artifacts_consistent": (
                verification.artifacts_consistent
            ),
            f"{prefix}shadow_only": verification.shadow_only,
            f"{prefix}non_authorizing": verification.non_authorizing,
            f"{prefix}error": verification.error,
        }
    )
    return fields


def _provider_live_dryrun_shadow_calibration_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = run_type == PROVIDER_LIVE_DRYRUN_SHADOW_CALIBRATION_RUN_TYPE
    prefix = "provider_live_dryrun_shadow_calibration_verification_"
    values: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": (
            "verification_required" if required else "not_applicable"
        ),
        f"{prefix}verified": False,
        f"{prefix}completed": False,
        f"{prefix}insufficient": False,
        f"{prefix}manifest_current": False,
        f"{prefix}shadow_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}calibration_only": False,
        f"{prefix}non_authorizing": False,
        f"{prefix}error": "",
    }
    if not required:
        return values
    try:
        verification = (
            verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
                run_dir
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        values[f"{prefix}status"] = "verification_error"
        values[f"{prefix}error"] = str(exc)
        return values
    status = "stale_or_inconsistent"
    if verification.verified:
        status = (
            "verified_completed"
            if verification.completed
            else "verified_insufficient"
        )
    values.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}completed": verification.completed,
            f"{prefix}insufficient": verification.insufficient,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}shadow_current": verification.shadow_current,
            f"{prefix}artifacts_consistent": (
                verification.artifacts_consistent
            ),
            f"{prefix}calibration_only": verification.calibration_only,
            f"{prefix}non_authorizing": verification.non_authorizing,
            f"{prefix}error": verification.error,
        }
    )
    return values


def _provider_live_dryrun_shadow_calibration_stability_verification_fields(
    run_dir: Path,
    run_type: str,
) -> dict[str, Any]:
    required = (
        run_type
        == PROVIDER_LIVE_DRYRUN_SHADOW_CALIBRATION_STABILITY_RUN_TYPE
    )
    prefix = (
        "provider_live_dryrun_shadow_calibration_stability_verification_"
    )
    values: dict[str, Any] = {
        f"{prefix}required": required,
        f"{prefix}status": (
            "verification_required" if required else "not_applicable"
        ),
        f"{prefix}verified": False,
        f"{prefix}stable": False,
        f"{prefix}unstable": False,
        f"{prefix}manifest_current": False,
        f"{prefix}calibrations_current": False,
        f"{prefix}artifacts_consistent": False,
        f"{prefix}stability_evidence_only": False,
        f"{prefix}non_authorizing": False,
        f"{prefix}error": "",
    }
    if not required:
        return values
    try:
        verification = verify_provider_shadow_calibration_stability(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        values[f"{prefix}status"] = "verification_error"
        values[f"{prefix}error"] = str(exc)
        return values
    status = "stale_or_inconsistent"
    if verification.verified:
        status = (
            "verified_stable"
            if verification.stable
            else "verified_unstable"
        )
    values.update(
        {
            f"{prefix}status": status,
            f"{prefix}verified": verification.verified,
            f"{prefix}stable": verification.stable,
            f"{prefix}unstable": verification.unstable,
            f"{prefix}manifest_current": verification.manifest_current,
            f"{prefix}calibrations_current": (
                verification.calibrations_current
            ),
            f"{prefix}artifacts_consistent": (
                verification.artifacts_consistent
            ),
            f"{prefix}stability_evidence_only": (
                verification.stability_evidence_only
            ),
            f"{prefix}non_authorizing": verification.non_authorizing,
            f"{prefix}error": verification.error,
        }
    )
    return values


def _provider_lineage_selection_fields(
    run_dir: Path,
    run_type: str,
    lineage_records: pd.DataFrame | None,
    chain_audit_records: pd.DataFrame | None,
) -> dict[str, Any]:
    index_provided = lineage_records is not None
    bundle_type = PROVIDER_BROKER_LINEAGE_RUN_TYPES.get(run_type, "")
    if not index_provided:
        return _provider_active_lineage_chain_audit_fields(
            run_dir,
            bundle_type,
            chain_audit_records,
            {
                "provider_lineage_index_provided": False,
                "provider_lineage_bundle_type": bundle_type,
                "provider_lineage_pair_id": "",
                "provider_lineage_role": "unindexed" if bundle_type else "",
                "provider_lineage_selection_status": (
                    "index_not_provided" if bundle_type else "not_applicable"
                ),
                "provider_lineage_selection_eligible": not bool(bundle_type),
                "provider_lineage_counterpart_path": "",
            },
        )
    if not bundle_type:
        return _provider_active_lineage_chain_audit_fields(
            run_dir,
            bundle_type,
            chain_audit_records,
            {
                "provider_lineage_index_provided": True,
                "provider_lineage_bundle_type": "",
                "provider_lineage_pair_id": "",
                "provider_lineage_role": "",
                "provider_lineage_selection_status": "not_applicable",
                "provider_lineage_selection_eligible": True,
                "provider_lineage_counterpart_path": "",
            },
        )
    matches = lineage_records.loc[
        lineage_records["bundle_path"].map(_resolved_path_text).eq(
            str(run_dir.resolve())
        )
        & lineage_records["bundle_type"].astype(str).eq(bundle_type)
    ]
    if len(matches) != 1:
        return _provider_active_lineage_chain_audit_fields(
            run_dir,
            bundle_type,
            chain_audit_records,
            {
                "provider_lineage_index_provided": True,
                "provider_lineage_bundle_type": bundle_type,
                "provider_lineage_pair_id": "",
                "provider_lineage_role": "unindexed",
                "provider_lineage_selection_status": "unindexed",
                "provider_lineage_selection_eligible": False,
                "provider_lineage_counterpart_path": "",
            },
        )
    match = matches.iloc[0]
    return _provider_active_lineage_chain_audit_fields(
        run_dir,
        bundle_type,
        chain_audit_records,
        {
            "provider_lineage_index_provided": True,
            "provider_lineage_bundle_type": bundle_type,
            "provider_lineage_pair_id": str(match.get("lineage_pair_id", "")),
            "provider_lineage_role": str(match.get("lineage_role", "")),
            "provider_lineage_selection_status": str(
                match.get("selection_status", "")
            ),
            "provider_lineage_selection_eligible": _to_bool(
                match.get("catalog_selectable")
            ),
            "provider_lineage_counterpart_path": str(
                match.get("counterpart_bundle_path", "")
            ),
        },
    )


def _provider_active_lineage_chain_audit_fields(
    run_dir: Path,
    bundle_type: str,
    chain_audit_records: pd.DataFrame | None,
    selection: dict[str, Any],
) -> dict[str, Any]:
    fields = dict(selection)
    required = bool(
        bundle_type == "rehearsal_certificate"
        and str(fields.get("provider_lineage_selection_status", ""))
        == "selectable"
    )
    provided = chain_audit_records is not None
    fields.update(
        {
            "provider_active_lineage_chain_audit_required": required,
            "provider_active_lineage_chain_audit_provided": provided,
            "provider_active_lineage_chain_audit_covered": False,
            "provider_active_lineage_chain_audit_selection_bound": False,
            "provider_active_lineage_chain_audit_status": (
                "not_applicable" if not required else "audit_not_provided"
            ),
            "provider_active_lineage_chain_audit_dir": "",
            "provider_active_lineage_chain_audit_manifest_sha256": "",
            "provider_active_lineage_chain_audit_chain_digest_sha256": "",
            "provider_active_lineage_chain_audit_contract_sha256": "",
            "provider_active_lineage_chain_audit_certificate_manifest_sha256": "",
            "provider_lineage_selection_block_reason": "",
        }
    )
    if not required:
        if bundle_type and not _to_bool(
            fields.get("provider_lineage_selection_eligible")
        ):
            fields["provider_lineage_selection_block_reason"] = (
                "active_lineage_index_not_selectable"
            )
        return fields
    if chain_audit_records is None:
        fields["provider_lineage_selection_eligible"] = False
        fields["provider_lineage_selection_block_reason"] = (
            "active_lineage_chain_audit_not_provided"
        )
        return fields
    matches = chain_audit_records.loc[
        chain_audit_records["certificate_dir"].map(_resolved_path_text).eq(
            str(run_dir.resolve())
        )
    ]
    if len(matches) != 1:
        fields["provider_active_lineage_chain_audit_status"] = (
            "certificate_not_covered"
        )
        fields["provider_lineage_selection_eligible"] = False
        fields["provider_lineage_selection_block_reason"] = (
            "certificate_not_covered_by_active_lineage_chain_audit"
        )
        return fields
    match = matches.iloc[0]
    certificate_manifest = run_dir / MANIFEST_NAME
    current_manifest_sha256 = (
        file_sha256(certificate_manifest)
        if certificate_manifest.is_file()
        else ""
    )
    expected_manifest_sha256 = str(
        match.get("certificate_manifest_sha256", "")
    )
    current = bool(
        current_manifest_sha256
        and current_manifest_sha256 == expected_manifest_sha256
    )
    index_selectable = _to_bool(
        fields.get("provider_lineage_selection_eligible")
    )
    selection_bound = bool(index_selectable and current)
    fields.update(
        {
            "provider_active_lineage_chain_audit_covered": current,
            "provider_active_lineage_chain_audit_selection_bound": (
                selection_bound
            ),
            "provider_active_lineage_chain_audit_status": (
                "certificate_manifest_drift"
                if not current
                else (
                    "covered_current"
                    if selection_bound
                    else "active_lineage_index_not_selectable"
                )
            ),
            "provider_active_lineage_chain_audit_dir": str(
                match.get("audit_dir", "")
            ),
            "provider_active_lineage_chain_audit_manifest_sha256": str(
                match.get("audit_manifest_sha256", "")
            ),
            "provider_active_lineage_chain_audit_chain_digest_sha256": str(
                match.get("chain_digest_sha256", "")
            ),
            "provider_active_lineage_chain_audit_contract_sha256": str(
                match.get(
                    "provider_lineage_selection_contract_sha256",
                    "",
                )
            ),
            "provider_active_lineage_chain_audit_certificate_manifest_sha256": (
                expected_manifest_sha256
            ),
        }
    )
    fields["provider_lineage_selection_eligible"] = selection_bound
    if not current:
        fields["provider_lineage_selection_block_reason"] = (
            "certificate_manifest_drift_after_active_lineage_chain_audit"
        )
    elif not index_selectable:
        fields["provider_lineage_selection_block_reason"] = (
            "active_lineage_index_not_selectable"
        )
    return fields


def _resolved_path_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return str(Path(text).resolve()) if text else ""


def _summary_row(run_dir: Path) -> tuple[str, dict[str, Any]]:
    for name in SUMMARY_FILES:
        path = run_dir / name
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return name, {}
        if frame.empty:
            return name, {}
        return name, _jsonable_row(frame.iloc[0].to_dict())
    return "", {}


def _summary_status(row: dict[str, Any]) -> tuple[str, bool | None]:
    for column in STATUS_COLUMNS:
        if column in row:
            return column, _to_bool(row[column])
    if "failed_checks" in row:
        return "failed_checks", _numeric(row["failed_checks"]) == 0
    if "failed_runs" in row:
        return "failed_runs", _numeric(row["failed_runs"]) == 0
    if "failed_rows" in row:
        return "failed_rows", _numeric(row["failed_rows"]) == 0
    return "", None


def _provider_lineage_selection_counts(catalog: pd.DataFrame) -> dict[str, int]:
    counts = {
        "provider_lineage_indexed_runs": 0,
        "provider_lineage_selectable_runs": 0,
        "provider_lineage_retained_only_runs": 0,
        "provider_lineage_unindexed_runs": 0,
        "provider_lineage_selection_blocked_runs": 0,
        "provider_active_lineage_chain_audit_required_runs": 0,
        "provider_active_lineage_chain_audit_covered_runs": 0,
        "provider_active_lineage_chain_audit_blocked_runs": 0,
        "provider_active_lineage_chain_audit_not_provided_runs": 0,
        "provider_active_lineage_chain_audit_uncovered_runs": 0,
    }
    if catalog.empty or "provider_lineage_selection_status" not in catalog:
        return counts
    statuses = catalog["provider_lineage_selection_status"].astype(str)
    provider_runs = catalog["provider_lineage_bundle_type"].astype(str).ne("")
    eligible = catalog["provider_lineage_selection_eligible"].map(_to_bool)
    selectable = statuses.eq("selectable") & eligible
    retained = statuses.eq("retained_only")
    unindexed = statuses.isin(["unindexed", "index_not_provided"])
    audit_required = catalog.get(
        "provider_active_lineage_chain_audit_required",
        pd.Series(False, index=catalog.index),
    ).map(_to_bool)
    audit_covered = catalog.get(
        "provider_active_lineage_chain_audit_covered",
        pd.Series(False, index=catalog.index),
    ).map(_to_bool)
    audit_status = catalog.get(
        "provider_active_lineage_chain_audit_status",
        pd.Series("", index=catalog.index),
    ).astype(str)
    counts.update(
        {
            "provider_lineage_indexed_runs": int(
                (statuses.isin(["selectable", "retained_only"])).sum()
            ),
            "provider_lineage_selectable_runs": int(selectable.sum()),
            "provider_lineage_retained_only_runs": int(retained.sum()),
            "provider_lineage_unindexed_runs": int(unindexed.sum()),
            "provider_lineage_selection_blocked_runs": int(
                (provider_runs & ~eligible).sum()
            ),
            "provider_active_lineage_chain_audit_required_runs": int(
                audit_required.sum()
            ),
            "provider_active_lineage_chain_audit_covered_runs": int(
                (
                    audit_required
                    & audit_covered
                    & audit_status.eq("covered_current")
                ).sum()
            ),
            "provider_active_lineage_chain_audit_blocked_runs": int(
                (audit_required & ~audit_status.eq("covered_current")).sum()
            ),
            "provider_active_lineage_chain_audit_not_provided_runs": int(
                (audit_required & audit_status.eq("audit_not_provided")).sum()
            ),
            "provider_active_lineage_chain_audit_uncovered_runs": int(
                (
                    audit_required
                    & audit_status.isin(
                        [
                            "certificate_not_covered",
                            "certificate_manifest_drift",
                        ]
                    )
                ).sum()
            ),
        }
    )
    return counts


def _catalog_summary(
    catalog: pd.DataFrame,
    action_queue: pd.DataFrame | None = None,
    hygiene_gaps: pd.DataFrame | None = None,
) -> pd.DataFrame:
    action_counts = _action_queue_counts(action_queue)
    hygiene_counts = _hygiene_gap_counts(hygiene_gaps)
    broker_roundtrip_counts = _broker_roundtrip_portfolio_counts(catalog)
    broker_roundtrip_resume_route_counts = _broker_roundtrip_resume_route_counts(catalog)
    provider_broker_roundtrip_sidecar_counts = _provider_broker_roundtrip_synthetic_sidecar_counts(catalog)
    placeholder_schema_counts = _placeholder_schema_counts(catalog)
    provider_lineage_selection_counts = _provider_lineage_selection_counts(
        catalog
    )
    strategy_evidence_verification_counts = (
        _strategy_evidence_verification_counts(catalog)
    )
    provider_release_review_verification_counts = (
        _provider_release_review_verification_counts(catalog)
    )
    provider_release_decision_verification_counts = (
        _provider_release_decision_verification_counts(catalog)
    )
    provider_live_dryrun_handoff_verification_counts = (
        _provider_live_dryrun_handoff_verification_counts(catalog)
    )
    provider_live_dryrun_runtime_preflight_verification_counts = (
        _provider_live_dryrun_runtime_preflight_verification_counts(catalog)
    )
    provider_live_dryrun_runtime_launcher_verification_counts = (
        _provider_live_dryrun_runtime_launcher_verification_counts(catalog)
    )
    provider_live_dryrun_shadow_verification_counts = (
        _provider_live_dryrun_shadow_verification_counts(catalog)
    )
    provider_live_dryrun_shadow_calibration_verification_counts = (
        _provider_live_dryrun_shadow_calibration_verification_counts(catalog)
    )
    provider_live_dryrun_shadow_calibration_stability_verification_counts = (
        _provider_live_dryrun_shadow_calibration_stability_verification_counts(
            catalog
        )
    )
    if catalog.empty:
        return pd.DataFrame(
            [
                {
                    "run_count": 0,
                    "run_type_count": 0,
                    "status_true_runs": 0,
                    "status_false_runs": 0,
                    "missing_summary_runs": 0,
                    "dirty_runs": 0,
                    "git_commit_count": 0,
                    "input_file_count": 0,
                    "input_directory_count": 0,
                    "input_other_count": 0,
                    "input_hashed_count": 0,
                    "input_unfingerprinted_count": 0,
                    "runs_with_directory_inputs": 0,
                    "runs_with_unfingerprinted_inputs": 0,
                    **broker_roundtrip_counts,
                    **broker_roundtrip_resume_route_counts,
                    **provider_broker_roundtrip_sidecar_counts,
                    **placeholder_schema_counts,
                    **provider_lineage_selection_counts,
                    **strategy_evidence_verification_counts,
                    **provider_release_review_verification_counts,
                    **provider_release_decision_verification_counts,
                    **provider_live_dryrun_handoff_verification_counts,
                    **provider_live_dryrun_runtime_preflight_verification_counts,
                    **provider_live_dryrun_runtime_launcher_verification_counts,
                    **provider_live_dryrun_shadow_verification_counts,
                    **provider_live_dryrun_shadow_calibration_verification_counts,
                    **provider_live_dryrun_shadow_calibration_stability_verification_counts,
                    **action_counts,
                    **hygiene_counts,
                }
            ]
        )
    status = catalog["summary_status"]
    return pd.DataFrame(
        [
            {
                "run_count": int(len(catalog)),
                "run_type_count": int(catalog["run_type"].nunique()),
                "status_true_runs": int(status.map(lambda value: value is True).sum()),
                "status_false_runs": int(status.map(lambda value: value is False).sum()),
                "missing_summary_runs": int((catalog["summary_file"].astype(str) == "").sum()),
                "dirty_runs": int(catalog["git_dirty"].map(_to_bool).sum()),
                "git_commit_count": int(catalog["git_commit"].dropna().nunique()),
                "input_file_count": int(catalog["input_file_count"].sum()),
                "input_directory_count": int(catalog["input_directory_count"].sum()),
                "input_other_count": int(catalog["input_other_count"].sum()),
                "input_hashed_count": int(catalog["input_hashed_count"].sum()),
                "input_unfingerprinted_count": int(catalog["input_unfingerprinted_count"].sum()),
                "runs_with_directory_inputs": int((catalog["input_directory_count"] > 0).sum()),
                "runs_with_unfingerprinted_inputs": int((catalog["input_unfingerprinted_count"] > 0).sum()),
                **broker_roundtrip_counts,
                **broker_roundtrip_resume_route_counts,
                **provider_broker_roundtrip_sidecar_counts,
                **placeholder_schema_counts,
                **provider_lineage_selection_counts,
                **strategy_evidence_verification_counts,
                **provider_release_review_verification_counts,
                **provider_release_decision_verification_counts,
                **provider_live_dryrun_handoff_verification_counts,
                **provider_live_dryrun_runtime_preflight_verification_counts,
                **provider_live_dryrun_runtime_launcher_verification_counts,
                **provider_live_dryrun_shadow_verification_counts,
                **provider_live_dryrun_shadow_calibration_verification_counts,
                **provider_live_dryrun_shadow_calibration_stability_verification_counts,
                **action_counts,
                **hygiene_counts,
            }
        ]
    )


def _strategy_evidence_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    counts = {
        "strategy_evidence_verification_required_runs": 0,
        "strategy_evidence_verification_verified_runs": 0,
        "strategy_evidence_verification_ready_runs": 0,
        "strategy_evidence_verification_stale_runs": 0,
    }
    required_column = "strategy_evidence_verification_required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[
        "strategy_evidence_verification_verified"
    ].map(_to_bool)
    ready = catalog["strategy_evidence_verification_ready"].map(_to_bool)
    counts.update(
        {
            "strategy_evidence_verification_required_runs": int(
                required.sum()
            ),
            "strategy_evidence_verification_verified_runs": int(
                (required & verified).sum()
            ),
            "strategy_evidence_verification_ready_runs": int(
                (required & ready).sum()
            ),
            "strategy_evidence_verification_stale_runs": int(
                (required & ~verified).sum()
            ),
        }
    )
    return counts


def _provider_release_review_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    counts = {
        "provider_release_review_verification_required_runs": 0,
        "provider_release_review_verification_verified_runs": 0,
        "provider_release_review_verification_ready_runs": 0,
        "provider_release_review_verification_stale_runs": 0,
    }
    required_column = "provider_release_review_verification_required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[
        "provider_release_review_verification_verified"
    ].map(_to_bool)
    ready = catalog[
        "provider_release_review_verification_ready"
    ].map(_to_bool)
    counts.update(
        {
            "provider_release_review_verification_required_runs": int(
                required.sum()
            ),
            "provider_release_review_verification_verified_runs": int(
                (required & verified).sum()
            ),
            "provider_release_review_verification_ready_runs": int(
                (required & ready).sum()
            ),
            "provider_release_review_verification_stale_runs": int(
                (required & ~verified).sum()
            ),
        }
    )
    return counts


def _provider_release_decision_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    counts = {
        "provider_release_decision_verification_required_runs": 0,
        "provider_release_decision_verification_verified_runs": 0,
        "provider_release_decision_verification_sealed_runs": 0,
        "provider_release_decision_verification_approved_runs": 0,
        "provider_release_decision_verification_ready_runs": 0,
        "provider_release_decision_verification_stale_runs": 0,
    }
    required_column = "provider_release_decision_verification_required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[
        "provider_release_decision_verification_verified"
    ].map(_to_bool)
    sealed = catalog[
        "provider_release_decision_verification_sealed"
    ].map(_to_bool)
    approved = catalog[
        "provider_release_decision_verification_approved"
    ].map(_to_bool)
    ready = catalog[
        "provider_release_decision_verification_ready"
    ].map(_to_bool)
    counts.update(
        {
            "provider_release_decision_verification_required_runs": int(
                required.sum()
            ),
            "provider_release_decision_verification_verified_runs": int(
                (required & verified).sum()
            ),
            "provider_release_decision_verification_sealed_runs": int(
                (required & sealed).sum()
            ),
            "provider_release_decision_verification_approved_runs": int(
                (required & verified & approved).sum()
            ),
            "provider_release_decision_verification_ready_runs": int(
                (required & ready).sum()
            ),
            "provider_release_decision_verification_stale_runs": int(
                (required & ~verified).sum()
            ),
        }
    )
    return counts


def _provider_live_dryrun_handoff_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    counts = {
        "provider_live_dryrun_handoff_verification_required_runs": 0,
        "provider_live_dryrun_handoff_verification_verified_runs": 0,
        "provider_live_dryrun_handoff_verification_ready_runs": 0,
        "provider_live_dryrun_handoff_verification_stale_runs": 0,
    }
    required_column = "provider_live_dryrun_handoff_verification_required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[
        "provider_live_dryrun_handoff_verification_verified"
    ].map(_to_bool)
    ready = catalog[
        "provider_live_dryrun_handoff_verification_ready"
    ].map(_to_bool)
    counts.update(
        {
            "provider_live_dryrun_handoff_verification_required_runs": int(
                required.sum()
            ),
            "provider_live_dryrun_handoff_verification_verified_runs": int(
                (required & verified).sum()
            ),
            "provider_live_dryrun_handoff_verification_ready_runs": int(
                (required & ready).sum()
            ),
            "provider_live_dryrun_handoff_verification_stale_runs": int(
                (required & ~verified).sum()
            ),
        }
    )
    return counts


def _provider_live_dryrun_runtime_preflight_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    counts = {
        "provider_live_dryrun_runtime_preflight_verification_required_runs": 0,
        "provider_live_dryrun_runtime_preflight_verification_verified_runs": 0,
        "provider_live_dryrun_runtime_preflight_verification_ready_runs": 0,
        "provider_live_dryrun_runtime_preflight_verification_blocked_runs": 0,
        "provider_live_dryrun_runtime_preflight_verification_stale_runs": 0,
    }
    required_column = (
        "provider_live_dryrun_runtime_preflight_verification_required"
    )
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[
        "provider_live_dryrun_runtime_preflight_verification_verified"
    ].map(_to_bool)
    ready = catalog[
        "provider_live_dryrun_runtime_preflight_verification_ready"
    ].map(_to_bool)
    counts.update(
        {
            "provider_live_dryrun_runtime_preflight_verification_required_runs": int(
                required.sum()
            ),
            "provider_live_dryrun_runtime_preflight_verification_verified_runs": int(
                (required & verified).sum()
            ),
            "provider_live_dryrun_runtime_preflight_verification_ready_runs": int(
                (required & ready).sum()
            ),
            "provider_live_dryrun_runtime_preflight_verification_blocked_runs": int(
                (required & verified & ~ready).sum()
            ),
            "provider_live_dryrun_runtime_preflight_verification_stale_runs": int(
                (required & ~verified).sum()
            ),
        }
    )
    return counts


def _provider_live_dryrun_runtime_launcher_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    counts = {
        "provider_live_dryrun_runtime_launcher_verification_required_runs": 0,
        "provider_live_dryrun_runtime_launcher_verification_verified_runs": 0,
        "provider_live_dryrun_runtime_launcher_verification_completed_runs": 0,
        "provider_live_dryrun_runtime_launcher_verification_halted_runs": 0,
        "provider_live_dryrun_runtime_launcher_verification_stale_runs": 0,
    }
    required_column = (
        "provider_live_dryrun_runtime_launcher_verification_required"
    )
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[
        "provider_live_dryrun_runtime_launcher_verification_verified"
    ].map(_to_bool)
    completed = catalog[
        "provider_live_dryrun_runtime_launcher_verification_completed"
    ].map(_to_bool)
    halted = catalog[
        "provider_live_dryrun_runtime_launcher_verification_halted"
    ].map(_to_bool)
    counts.update(
        {
            "provider_live_dryrun_runtime_launcher_verification_required_runs": int(
                required.sum()
            ),
            "provider_live_dryrun_runtime_launcher_verification_verified_runs": int(
                (required & verified).sum()
            ),
            "provider_live_dryrun_runtime_launcher_verification_completed_runs": int(
                (required & verified & completed).sum()
            ),
            "provider_live_dryrun_runtime_launcher_verification_halted_runs": int(
                (required & verified & halted).sum()
            ),
            "provider_live_dryrun_runtime_launcher_verification_stale_runs": int(
                (required & ~verified).sum()
            ),
        }
    )
    return counts


def _provider_live_dryrun_shadow_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    prefix = "provider_live_dryrun_shadow_verification_"
    counts = {
        f"{prefix}required_runs": 0,
        f"{prefix}verified_runs": 0,
        f"{prefix}completed_runs": 0,
        f"{prefix}halted_runs": 0,
        f"{prefix}stale_runs": 0,
    }
    required_column = f"{prefix}required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[f"{prefix}verified"].map(_to_bool)
    completed = catalog[f"{prefix}completed"].map(_to_bool)
    halted = catalog[f"{prefix}halted"].map(_to_bool)
    counts.update(
        {
            f"{prefix}required_runs": int(required.sum()),
            f"{prefix}verified_runs": int((required & verified).sum()),
            f"{prefix}completed_runs": int(
                (required & verified & completed).sum()
            ),
            f"{prefix}halted_runs": int(
                (required & verified & halted).sum()
            ),
            f"{prefix}stale_runs": int((required & ~verified).sum()),
        }
    )
    return counts


def _provider_live_dryrun_shadow_calibration_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    prefix = "provider_live_dryrun_shadow_calibration_verification_"
    counts = {
        f"{prefix}required_runs": 0,
        f"{prefix}verified_runs": 0,
        f"{prefix}completed_runs": 0,
        f"{prefix}insufficient_runs": 0,
        f"{prefix}stale_runs": 0,
    }
    required_column = f"{prefix}required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[f"{prefix}verified"].map(_to_bool)
    completed = catalog[f"{prefix}completed"].map(_to_bool)
    insufficient = catalog[f"{prefix}insufficient"].map(_to_bool)
    counts.update(
        {
            f"{prefix}required_runs": int(required.sum()),
            f"{prefix}verified_runs": int((required & verified).sum()),
            f"{prefix}completed_runs": int(
                (required & verified & completed).sum()
            ),
            f"{prefix}insufficient_runs": int(
                (required & verified & insufficient).sum()
            ),
            f"{prefix}stale_runs": int((required & ~verified).sum()),
        }
    )
    return counts


def _provider_live_dryrun_shadow_calibration_stability_verification_counts(
    catalog: pd.DataFrame,
) -> dict[str, int]:
    prefix = (
        "provider_live_dryrun_shadow_calibration_stability_verification_"
    )
    counts = {
        f"{prefix}required_runs": 0,
        f"{prefix}verified_runs": 0,
        f"{prefix}stable_runs": 0,
        f"{prefix}unstable_runs": 0,
        f"{prefix}stale_runs": 0,
    }
    required_column = f"{prefix}required"
    if catalog.empty or required_column not in catalog.columns:
        return counts
    required = catalog[required_column].map(_to_bool)
    verified = catalog[f"{prefix}verified"].map(_to_bool)
    stable = catalog[f"{prefix}stable"].map(_to_bool)
    unstable = catalog[f"{prefix}unstable"].map(_to_bool)
    counts.update(
        {
            f"{prefix}required_runs": int(required.sum()),
            f"{prefix}verified_runs": int((required & verified).sum()),
            f"{prefix}stable_runs": int(
                (required & verified & stable).sum()
            ),
            f"{prefix}unstable_runs": int(
                (required & verified & unstable).sum()
            ),
            f"{prefix}stale_runs": int((required & ~verified).sum()),
        }
    )
    return counts


def _broker_roundtrip_portfolio_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "broker_roundtrip_runs": 0,
        "broker_roundtrip_passed_runs": 0,
        "broker_roundtrip_portfolio_provided_runs": 0,
        "broker_roundtrip_portfolio_ready_runs": 0,
        "broker_roundtrip_portfolio_safe_runs": 0,
        "broker_roundtrip_portfolio_breach_runs": 0,
        "broker_roundtrip_portfolio_concentration_runs": 0,
        "broker_roundtrip_portfolio_concentration_ok_runs": 0,
        "broker_roundtrip_portfolio_concentration_breach_runs": 0,
    }
    if catalog.empty or "run_type" not in catalog.columns:
        return keys
    frame = catalog.loc[catalog["run_type"].astype(str) == "broker_dispatch_roundtrip"].copy()
    if frame.empty:
        return keys
    provided = _bool_column(frame, "summary_strategy_portfolio_provided")
    ready = _bool_column(frame, "summary_strategy_portfolio_ready")
    passed = _bool_column(frame, "summary_status")
    dispatch_notional = _numeric_column(frame, "summary_dispatch_total_notional")
    selected_allocation = _numeric_column(frame, "summary_strategy_portfolio_selected_allocation_notional")
    valid_allocation = selected_allocation > 0.0
    breach = provided & valid_allocation & (dispatch_notional > selected_allocation)
    safe = provided & ready & passed & valid_allocation & (dispatch_notional <= selected_allocation)
    min_strategy_count = _numeric_column(frame, "summary_strategy_portfolio_min_strategy_count")
    min_market_count = _numeric_column(frame, "summary_strategy_portfolio_min_market_count")
    max_strategy_weight = _numeric_column(frame, "summary_strategy_portfolio_max_strategy_weight")
    max_market_weight = _numeric_column(frame, "summary_strategy_portfolio_max_market_weight")
    allocated_strategy_count = _numeric_column(frame, "summary_strategy_portfolio_allocated_strategy_count")
    allocated_market_count = _numeric_column(frame, "summary_strategy_portfolio_allocated_market_count")
    max_strategy_allocation_weight = _numeric_column(
        frame, "summary_strategy_portfolio_max_strategy_allocation_weight"
    )
    max_market_allocation_weight = _numeric_column(frame, "summary_strategy_portfolio_max_market_allocation_weight")
    concentration_provided = (
        (min_strategy_count > 0.0)
        | (min_market_count > 0.0)
        | (max_strategy_weight > 0.0)
        | (max_market_weight > 0.0)
        | (allocated_strategy_count > 0.0)
        | (allocated_market_count > 0.0)
        | (max_strategy_allocation_weight > 0.0)
        | (max_market_allocation_weight > 0.0)
    )
    concentration = provided & ready & valid_allocation & concentration_provided
    strategy_count_ok = (min_strategy_count <= 0.0) | (allocated_strategy_count >= min_strategy_count)
    market_count_ok = (min_market_count <= 0.0) | (allocated_market_count >= min_market_count)
    strategy_weight_ok = (max_strategy_weight <= 0.0) | (
        max_strategy_allocation_weight <= max_strategy_weight + 1e-9
    )
    market_weight_ok = (max_market_weight <= 0.0) | (max_market_allocation_weight <= max_market_weight + 1e-9)
    concentration_ok = (
        concentration
        & strategy_count_ok
        & market_count_ok
        & strategy_weight_ok
        & market_weight_ok
    )
    concentration_breach = concentration & ~concentration_ok
    keys.update(
        {
            "broker_roundtrip_runs": int(len(frame)),
            "broker_roundtrip_passed_runs": int(passed.sum()),
            "broker_roundtrip_portfolio_provided_runs": int(provided.sum()),
            "broker_roundtrip_portfolio_ready_runs": int((provided & ready).sum()),
            "broker_roundtrip_portfolio_safe_runs": int(safe.sum()),
            "broker_roundtrip_portfolio_breach_runs": int(breach.sum()),
            "broker_roundtrip_portfolio_concentration_runs": int(concentration.sum()),
            "broker_roundtrip_portfolio_concentration_ok_runs": int(concentration_ok.sum()),
            "broker_roundtrip_portfolio_concentration_breach_runs": int(concentration_breach.sum()),
        }
    )
    return keys


def _broker_roundtrip_resume_route_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "broker_roundtrip_resume_route_provided_runs": 0,
        "broker_roundtrip_resume_route_ready_runs": 0,
        "broker_roundtrip_resume_route_primary_ready_runs": 0,
        "broker_roundtrip_resume_route_incident_ready_runs": 0,
        "broker_roundtrip_resume_route_breach_runs": 0,
        "broker_roundtrip_resume_route_gap_breach_runs": 0,
        "broker_roundtrip_resume_route_launch_control_breach_runs": 0,
        "broker_roundtrip_resume_route_portfolio_breach_runs": 0,
        "broker_roundtrip_resume_route_concentration_breach_runs": 0,
    }
    if catalog.empty or "run_type" not in catalog.columns:
        return keys
    frame = catalog.loc[catalog["run_type"].astype(str) == "broker_dispatch_roundtrip"].copy()
    if frame.empty:
        return keys

    primary = _resume_route_branch_state(frame, "summary_route_broker_resume_broker_route_readiness")
    incident = _resume_route_branch_state(frame, "summary_route_broker_resume_incident_broker_route_readiness")
    any_active = primary["active"] | incident["active"]
    provided = primary["provided"] & incident["provided"]
    ready = primary["ready"] & incident["ready"]
    gap_breach = primary["gap_breach"] | incident["gap_breach"]
    launch_control_breach = primary["launch_control_breach"] | incident["launch_control_breach"]
    portfolio_breach = primary["portfolio_breach"] | incident["portfolio_breach"]
    concentration_breach = primary["concentration_breach"] | incident["concentration_breach"]
    any_breach = any_active & (
        ~provided
        | ~ready
        | gap_breach
        | launch_control_breach
        | portfolio_breach
        | concentration_breach
    )
    keys.update(
        {
            "broker_roundtrip_resume_route_provided_runs": int(provided.sum()),
            "broker_roundtrip_resume_route_ready_runs": int(ready.sum()),
            "broker_roundtrip_resume_route_primary_ready_runs": int(primary["ready"].sum()),
            "broker_roundtrip_resume_route_incident_ready_runs": int(incident["ready"].sum()),
            "broker_roundtrip_resume_route_breach_runs": int(any_breach.sum()),
            "broker_roundtrip_resume_route_gap_breach_runs": int((any_active & gap_breach).sum()),
            "broker_roundtrip_resume_route_launch_control_breach_runs": int(
                (any_active & launch_control_breach).sum()
            ),
            "broker_roundtrip_resume_route_portfolio_breach_runs": int((any_active & portfolio_breach).sum()),
            "broker_roundtrip_resume_route_concentration_breach_runs": int(
                (any_active & concentration_breach).sum()
            ),
        }
    )
    return keys


def _resume_route_branch_state(frame: pd.DataFrame, prefix: str) -> dict[str, pd.Series]:
    required = _bool_column(frame, f"{prefix}_required")
    provided = _bool_column(frame, f"{prefix}_provided")
    ready_flag = _bool_column(frame, f"{prefix}_ready")
    route_ready_pairs = _numeric_column(frame, f"{prefix}_route_ready_pairs")
    gap_pairs = _numeric_column(frame, f"{prefix}_gap_pairs")
    launch_ready = _bool_column(frame, f"{prefix}_ops_launch_controls_ready")
    safe_runs = _numeric_column(frame, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs")
    breach_runs = _numeric_column(frame, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs")
    concentration_ok_runs = _numeric_column(
        frame,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
    )
    concentration_breach_runs = _numeric_column(
        frame,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    )
    active = (
        required
        | provided
        | ready_flag
        | (route_ready_pairs > 0.0)
        | (gap_pairs > 0.0)
        | launch_ready
        | (safe_runs > 0.0)
        | (breach_runs > 0.0)
        | (concentration_ok_runs > 0.0)
        | (concentration_breach_runs > 0.0)
    )
    gap_breach = (route_ready_pairs <= 0.0) | (gap_pairs > 0.0)
    launch_control_breach = ~launch_ready
    portfolio_breach = (safe_runs <= 0.0) | (breach_runs > 0.0)
    concentration_breach = (concentration_ok_runs <= 0.0) | (concentration_breach_runs > 0.0)
    ready = (
        provided
        & ready_flag
        & ~gap_breach
        & ~launch_control_breach
        & ~portfolio_breach
        & ~concentration_breach
    )
    return {
        "active": active,
        "provided": provided,
        "ready": ready,
        "gap_breach": gap_breach,
        "launch_control_breach": launch_control_breach,
        "portfolio_breach": portfolio_breach,
        "concentration_breach": concentration_breach,
    }


def _provider_broker_roundtrip_synthetic_sidecar_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "provider_broker_roundtrip_runs": 0,
        "provider_broker_roundtrip_passed_runs": 0,
        "provider_broker_roundtrip_synthetic_dataset_count": 0,
        "provider_broker_roundtrip_synthetic_sidecar_count": 0,
        "provider_broker_roundtrip_synthetic_sidecar_readable_count": 0,
        "provider_broker_roundtrip_synthetic_sidecar_proof_runs": 0,
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs": 0,
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs": 0,
    }
    if catalog.empty or "run_type" not in catalog.columns:
        return keys
    frame = catalog.loc[
        catalog["run_type"].astype(str) == "provider_market_data_imbalance_broker_dispatch_roundtrip"
    ].copy()
    if frame.empty:
        return keys
    passed = _bool_column(frame, "summary_status")
    dataset_count = _numeric_column(frame, "summary_dispatch_roundtrip_synthetic_dataset_count")
    sidecar_count = _numeric_column(frame, "summary_dispatch_roundtrip_synthetic_sidecar_count")
    readable_count = _numeric_column(frame, "summary_dispatch_roundtrip_synthetic_sidecar_readable_count")
    ready_flag = _bool_column(frame, "summary_dispatch_roundtrip_synthetic_sidecar_proof_ready")
    proof_runs = dataset_count > 0.0
    ready_runs = proof_runs & ready_flag & (sidecar_count >= dataset_count) & (readable_count >= dataset_count)
    breach_runs = proof_runs & ~ready_runs
    keys.update(
        {
            "provider_broker_roundtrip_runs": int(len(frame)),
            "provider_broker_roundtrip_passed_runs": int(passed.sum()),
            "provider_broker_roundtrip_synthetic_dataset_count": int(dataset_count.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_count": int(sidecar_count.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_readable_count": int(readable_count.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_proof_runs": int(proof_runs.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_ready_runs": int(ready_runs.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_breach_runs": int(breach_runs.sum()),
        }
    )
    return keys


def _placeholder_schema_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "placeholder_schema_active_runs": 0,
        "placeholder_schema_allowed_runs": 0,
        "placeholder_schema_reviewed_runs": 0,
        "placeholder_schema_unreviewed_runs": 0,
        "placeholder_schema_blocked_runs": 0,
    }
    if catalog.empty:
        return keys
    explicit_active = _bool_column(catalog, "summary_placeholder_schema_active")
    if "summary_adapter_schema_status" in catalog.columns:
        status_active = catalog["summary_adapter_schema_status"].map(_is_placeholder_schema)
    else:
        status_active = pd.Series(False, index=catalog.index)
    active = explicit_active | status_active
    allowed = active & _bool_column(catalog, "summary_placeholder_schema_allowed")
    reviewed = active & _bool_column(catalog, "summary_schema_reviewed")
    unreviewed = active & ~reviewed
    blocked = unreviewed & ~allowed
    keys.update(
        {
            "placeholder_schema_active_runs": int(active.sum()),
            "placeholder_schema_allowed_runs": int(allowed.sum()),
            "placeholder_schema_reviewed_runs": int(reviewed.sum()),
            "placeholder_schema_unreviewed_runs": int(unreviewed.sum()),
            "placeholder_schema_blocked_runs": int(blocked.sum()),
        }
    )
    return keys


def _bool_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[column].map(_to_bool)


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _is_placeholder_schema(value: Any) -> bool:
    return str(value).strip() == PLACEHOLDER_SCHEMA_STATUS


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "run_type",
    "run_dir",
    "strategy",
    "market",
    "profile",
    "summary_status",
    "action_source_file",
    "action_source",
    "dataset",
    "component",
    "check",
    "failed_check_count",
    "failed_check_names",
    "first_failed_reason",
    "primary_blocker_check",
    "primary_blocker_value",
    "primary_blocker_operator",
    "primary_blocker_threshold",
    "primary_blocker_reason",
    "pipeline_dir",
    "next_gate",
    "next_gate_help_command",
    "recommendation",
    "generated_at_utc",
]

EXCLUDED_SIDECAR_ACTION_QUEUES = {"experiment_catalog_action_queue.csv"}


def _catalog_action_queue(catalog: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not catalog.empty:
        for _, row in catalog.iterrows():
            item = row.to_dict()
            sidecar_rows = _sidecar_action_rows(item)
            if sidecar_rows:
                rows.extend(sidecar_rows)
                continue
            blocker_fields = _summary_blocker_fields(item)
            next_gate = _first_text(item, "summary_next_gate", "summary_best_next_gate")
            help_command = _first_text(
                item,
                "summary_next_gate_help_command",
                "summary_best_next_gate_help_command",
            )
            if not next_gate and not help_command:
                continue
            rows.append(
                {
                    "queue_status": _queue_status(item.get("summary_status")),
                    "run_type": _text(item.get("run_type")),
                    "run_dir": _text(item.get("run_dir")),
                    "strategy": _first_text(
                        item,
                        "summary_strategy",
                        "summary_best_strategy",
                        "summary_runtime_strategy",
                    ),
                    "market": _first_text(
                        item,
                        "summary_market",
                        "summary_best_market",
                        "summary_runtime_market",
                    ),
                    "profile": _first_text(
                        item,
                        "summary_evidence_profile",
                        "summary_profile",
                        "summary_best_profile",
                    ),
                    "summary_status": item.get("summary_status"),
                    "action_source_file": "",
                    "action_source": "",
                    "dataset": "",
                    "component": "",
                    "check": blocker_fields["primary_blocker_check"],
                    **blocker_fields,
                    "pipeline_dir": "",
                    "next_gate": next_gate,
                    "next_gate_help_command": help_command,
                    "recommendation": _text(item.get("summary_recommendation")),
                    "generated_at_utc": _text(item.get("generated_at_utc")),
                    "_source_priority": 0,
                }
            )
    if rows:
        ordered = sorted(
            rows,
            key=lambda row: (
                _queue_rank(row["queue_status"]),
                row["run_type"],
                row["run_dir"],
                _int_metric(row.get("_source_priority")),
                row["next_gate"],
            ),
        )
        for priority, row in enumerate(ordered, start=1):
            row["priority"] = priority
            row.pop("_source_priority", None)
        rows = ordered
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _action_queue_counts(action_queue: pd.DataFrame | None) -> dict[str, int]:
    if action_queue is None or action_queue.empty:
        return {
            "action_queue_count": 0,
            "action_queue_ready_count": 0,
            "action_queue_blocked_count": 0,
            "action_queue_unknown_count": 0,
        }
    statuses = action_queue["queue_status"].astype(str)
    ready_count = int((statuses == "ready").sum())
    blocked_count = int((statuses == "blocked").sum())
    total_count = int(len(action_queue))
    return {
        "action_queue_count": total_count,
        "action_queue_ready_count": ready_count,
        "action_queue_blocked_count": blocked_count,
        "action_queue_unknown_count": max(total_count - ready_count - blocked_count, 0),
    }


HYGIENE_GAP_COLUMNS = [
    "priority",
    "gap_type",
    "run_type",
    "run_dir",
    "summary_file",
    "summary_status",
    "git_dirty",
    "input_unfingerprinted_count",
    "next_gate",
    "next_gate_help_command",
    "recommendation",
    "generated_at_utc",
]


def _catalog_hygiene_gaps(catalog: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not catalog.empty:
        for _, row in catalog.iterrows():
            item = row.to_dict()
            rows.extend(_catalog_row_hygiene_gaps(item))
    rows = sorted(
        rows,
        key=lambda row: (
            _hygiene_gap_rank(row.get("gap_type")),
            _text(row.get("run_type")),
            _text(row.get("run_dir")),
        ),
    )
    for priority, row in enumerate(rows, start=1):
        row["priority"] = priority
    return pd.DataFrame(rows, columns=HYGIENE_GAP_COLUMNS)


def _catalog_row_hygiene_gaps(row: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if row.get("summary_status") is False:
        rows.append(_hygiene_gap(row, "summary_failed", "resolve_failed_summary_status"))
    if not _text(row.get("summary_file")):
        rows.append(_hygiene_gap(row, "missing_summary", "write_recognized_summary_artifact"))
    if _to_bool(row.get("git_dirty")):
        rows.append(_hygiene_gap(row, "dirty_git", "rerun_from_clean_git_state"))
    if _int_metric(row.get("input_unfingerprinted_count")) > 0:
        rows.append(
            _hygiene_gap(
                row,
                "unfingerprinted_inputs",
                "replace_unfingerprinted_inputs_with_file_or_directory_manifest_inputs",
            )
        )
    return rows


def _hygiene_gap(row: dict[str, Any], gap_type: str, recommendation: str) -> dict[str, Any]:
    return {
        "gap_type": gap_type,
        "run_type": _text(row.get("run_type")),
        "run_dir": _text(row.get("run_dir")),
        "summary_file": _text(row.get("summary_file")),
        "summary_status": row.get("summary_status"),
        "git_dirty": row.get("git_dirty"),
        "input_unfingerprinted_count": _int_metric(row.get("input_unfingerprinted_count")),
        "next_gate": _first_text(row, "summary_next_gate", "summary_best_next_gate"),
        "next_gate_help_command": _first_text(
            row,
            "summary_next_gate_help_command",
            "summary_best_next_gate_help_command",
        ),
        "recommendation": recommendation,
        "generated_at_utc": _text(row.get("generated_at_utc")),
    }


def _hygiene_gap_rank(gap_type: Any) -> int:
    return {
        "summary_failed": 0,
        "missing_summary": 1,
        "dirty_git": 2,
        "unfingerprinted_inputs": 3,
    }.get(_text(gap_type), 4)


def _hygiene_gap_counts(hygiene_gaps: pd.DataFrame | None) -> dict[str, int]:
    if hygiene_gaps is None or hygiene_gaps.empty:
        return {
            "hygiene_gap_count": 0,
            "hygiene_failed_status_count": 0,
            "hygiene_missing_summary_count": 0,
            "hygiene_dirty_run_count": 0,
            "hygiene_unfingerprinted_input_count": 0,
        }
    gap_types = hygiene_gaps["gap_type"].astype(str)
    return {
        "hygiene_gap_count": int(len(hygiene_gaps)),
        "hygiene_failed_status_count": int((gap_types == "summary_failed").sum()),
        "hygiene_missing_summary_count": int((gap_types == "missing_summary").sum()),
        "hygiene_dirty_run_count": int((gap_types == "dirty_git").sum()),
        "hygiene_unfingerprinted_input_count": int((gap_types == "unfingerprinted_inputs").sum()),
    }


def _catalog_action_plan(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    hygiene_gaps: pd.DataFrame,
) -> dict[str, Any]:
    actions = [_action_plan_row(row) for row in action_queue.to_dict(orient="records")]
    gaps = [_hygiene_gap_plan_row(row) for row in hygiene_gaps.to_dict(orient="records")]
    ready_actions = [action for action in actions if action["queue_status"] == "ready"]
    blocked_actions = [action for action in actions if action["queue_status"] == "blocked"]
    unknown_actions = [
        action
        for action in actions
        if action["queue_status"] not in {"ready", "blocked"}
    ]
    primary_action, primary_action_status = _primary_catalog_action(
        ready_actions,
        blocked_actions,
        unknown_actions,
    )
    failed_checks = [_action_failed_check(action) for action in blocked_actions if _action_failed_check(action)]
    primary_blocker = _catalog_primary_blocker(blocked_actions[0]) if blocked_actions else {}
    return {
        "schema_version": 1,
        "run_count": _int_metric(summary_row.get("run_count")),
        "run_type_count": _int_metric(summary_row.get("run_type_count")),
        "status_false_runs": _int_metric(summary_row.get("status_false_runs")),
        "missing_summary_runs": _int_metric(summary_row.get("missing_summary_runs")),
        "catalog_hygiene_ready": len(gaps) == 0,
        "hygiene_gap_count": len(gaps),
        "broker_roundtrip_runs": _int_metric(summary_row.get("broker_roundtrip_runs")),
        "broker_roundtrip_passed_runs": _int_metric(summary_row.get("broker_roundtrip_passed_runs")),
        "broker_roundtrip_portfolio_provided_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_provided_runs")
        ),
        "broker_roundtrip_portfolio_ready_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_ready_runs")
        ),
        "broker_roundtrip_portfolio_safe_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_safe_runs")
        ),
        "broker_roundtrip_portfolio_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_breach_runs")
        ),
        "broker_roundtrip_portfolio_concentration_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_concentration_runs")
        ),
        "broker_roundtrip_portfolio_concentration_ok_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_concentration_ok_runs")
        ),
        "broker_roundtrip_portfolio_concentration_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_portfolio_concentration_breach_runs")
        ),
        "broker_roundtrip_resume_route_provided_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_provided_runs")
        ),
        "broker_roundtrip_resume_route_ready_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_ready_runs")
        ),
        "broker_roundtrip_resume_route_primary_ready_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_primary_ready_runs")
        ),
        "broker_roundtrip_resume_route_incident_ready_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_incident_ready_runs")
        ),
        "broker_roundtrip_resume_route_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_breach_runs")
        ),
        "broker_roundtrip_resume_route_gap_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_gap_breach_runs")
        ),
        "broker_roundtrip_resume_route_launch_control_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_launch_control_breach_runs")
        ),
        "broker_roundtrip_resume_route_portfolio_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_portfolio_breach_runs")
        ),
        "broker_roundtrip_resume_route_concentration_breach_runs": _int_metric(
            summary_row.get("broker_roundtrip_resume_route_concentration_breach_runs")
        ),
        "provider_broker_roundtrip_runs": _int_metric(summary_row.get("provider_broker_roundtrip_runs")),
        "provider_broker_roundtrip_passed_runs": _int_metric(
            summary_row.get("provider_broker_roundtrip_passed_runs")
        ),
        "provider_broker_roundtrip_synthetic_dataset_count": _int_metric(
            summary_row.get("provider_broker_roundtrip_synthetic_dataset_count")
        ),
        "provider_broker_roundtrip_synthetic_sidecar_count": _int_metric(
            summary_row.get("provider_broker_roundtrip_synthetic_sidecar_count")
        ),
        "provider_broker_roundtrip_synthetic_sidecar_readable_count": _int_metric(
            summary_row.get("provider_broker_roundtrip_synthetic_sidecar_readable_count")
        ),
        "provider_broker_roundtrip_synthetic_sidecar_proof_runs": _int_metric(
            summary_row.get("provider_broker_roundtrip_synthetic_sidecar_proof_runs")
        ),
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs": _int_metric(
            summary_row.get("provider_broker_roundtrip_synthetic_sidecar_ready_runs")
        ),
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs": _int_metric(
            summary_row.get("provider_broker_roundtrip_synthetic_sidecar_breach_runs")
        ),
        "placeholder_schema_active_runs": _int_metric(summary_row.get("placeholder_schema_active_runs")),
        "placeholder_schema_allowed_runs": _int_metric(summary_row.get("placeholder_schema_allowed_runs")),
        "placeholder_schema_reviewed_runs": _int_metric(summary_row.get("placeholder_schema_reviewed_runs")),
        "placeholder_schema_unreviewed_runs": _int_metric(
            summary_row.get("placeholder_schema_unreviewed_runs")
        ),
        "placeholder_schema_blocked_runs": _int_metric(summary_row.get("placeholder_schema_blocked_runs")),
        "action_queue_count": len(actions),
        "ready_action_count": len(ready_actions),
        "blocked_action_count": len(blocked_actions),
        "unknown_action_count": len(unknown_actions),
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
        "first_failed_reason": _text(primary_blocker.get("reason")),
        "primary_blocker": primary_blocker,
        "next_gate": _text(primary_action.get("next_gate")),
        "next_gate_help_command": _text(primary_action.get("next_gate_help_command")),
        "primary_action_status": primary_action_status,
        "primary_action": primary_action,
        "scheduler_recommendation": _action_plan_recommendation(
            gaps,
            ready_actions,
            blocked_actions,
            unknown_actions,
        ),
        "next_actions": actions,
        "ready_actions": ready_actions,
        "blocked_actions": blocked_actions,
        "unknown_actions": unknown_actions,
        "hygiene_gaps": gaps,
        "top_hygiene_gap": gaps[0] if gaps else {},
        "top_ready_action": ready_actions[0] if ready_actions else {},
        "top_blocked_action": blocked_actions[0] if blocked_actions else {},
        "top_unknown_action": unknown_actions[0] if unknown_actions else {},
    }


def _primary_catalog_action(
    ready_actions: list[dict[str, Any]],
    blocked_actions: list[dict[str, Any]],
    unknown_actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    if ready_actions:
        return ready_actions[0], "ready"
    if blocked_actions:
        return blocked_actions[0], "blocked"
    if unknown_actions:
        return unknown_actions[0], "unknown"
    return {}, ""


def _action_failed_check(action: dict[str, Any]) -> str:
    return _text(action.get("primary_blocker_check")) or _text(action.get("check"))


def _catalog_primary_blocker(action: dict[str, Any]) -> dict[str, Any]:
    if not action:
        return {}
    check = _action_failed_check(action)
    return {
        "check": check,
        "run_type": _text(action.get("run_type")),
        "run_dir": _text(action.get("run_dir")),
        "strategy": _text(action.get("strategy")),
        "market": _text(action.get("market")),
        "profile": _text(action.get("profile")),
        "component": _text(action.get("component")),
        "value": _jsonable(action.get("primary_blocker_value")),
        "operator": _text(action.get("primary_blocker_operator")),
        "threshold": _jsonable(action.get("primary_blocker_threshold")),
        "reason": _text(action.get("primary_blocker_reason"))
        or _text(action.get("first_failed_reason"))
        or _text(action.get("recommendation")),
        "next_gate": _text(action.get("next_gate")),
        "next_gate_help_command": _text(action.get("next_gate_help_command")),
        "action_source_file": _text(action.get("action_source_file")),
        "action_source": _text(action.get("action_source")),
    }


def _action_plan_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "priority": _int_metric(row.get("priority")),
        "queue_status": _text(row.get("queue_status")) or "unknown",
        "run_type": _text(row.get("run_type")),
        "run_dir": _text(row.get("run_dir")),
        "strategy": _text(row.get("strategy")),
        "market": _text(row.get("market")),
        "profile": _text(row.get("profile")),
        "summary_status": _jsonable(row.get("summary_status")),
        "action_source_file": _text(row.get("action_source_file")),
        "action_source": _text(row.get("action_source")),
        "dataset": _text(row.get("dataset")),
        "component": _text(row.get("component")),
        "check": _text(row.get("check")),
        "failed_check_count": _int_metric(row.get("failed_check_count")),
        "failed_check_names": _text(row.get("failed_check_names")),
        "first_failed_reason": _text(row.get("first_failed_reason")),
        "primary_blocker_check": _text(row.get("primary_blocker_check")),
        "primary_blocker_value": _jsonable(row.get("primary_blocker_value")),
        "primary_blocker_operator": _text(row.get("primary_blocker_operator")),
        "primary_blocker_threshold": _jsonable(row.get("primary_blocker_threshold")),
        "primary_blocker_reason": _text(row.get("primary_blocker_reason")),
        "pipeline_dir": _text(row.get("pipeline_dir")),
        "next_gate": _text(row.get("next_gate")),
        "next_gate_help_command": _text(row.get("next_gate_help_command")),
        "recommendation": _text(row.get("recommendation")),
        "generated_at_utc": _text(row.get("generated_at_utc")),
    }


def _hygiene_gap_plan_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "priority": _int_metric(row.get("priority")),
        "gap_type": _text(row.get("gap_type")),
        "run_type": _text(row.get("run_type")),
        "run_dir": _text(row.get("run_dir")),
        "summary_file": _text(row.get("summary_file")),
        "summary_status": _jsonable(row.get("summary_status")),
        "git_dirty": _jsonable(row.get("git_dirty")),
        "input_unfingerprinted_count": _int_metric(row.get("input_unfingerprinted_count")),
        "next_gate": _text(row.get("next_gate")),
        "next_gate_help_command": _text(row.get("next_gate_help_command")),
        "recommendation": _text(row.get("recommendation")),
        "generated_at_utc": _text(row.get("generated_at_utc")),
    }


def _action_plan_recommendation(
    hygiene_gaps: list[dict[str, Any]],
    ready_actions: list[dict[str, Any]],
    blocked_actions: list[dict[str, Any]],
    unknown_actions: list[dict[str, Any]],
) -> str:
    if hygiene_gaps and (ready_actions or blocked_actions or unknown_actions):
        return "repair_catalog_hygiene_gaps_before_scheduling_actions"
    if hygiene_gaps:
        return "repair_catalog_hygiene_gaps"
    if ready_actions and blocked_actions:
        return "run_ready_actions_and_resolve_blocked_actions"
    if ready_actions:
        return "run_ready_actions"
    if blocked_actions:
        return "resolve_blocked_actions"
    if unknown_actions:
        return "review_unknown_actions"
    return "no_catalog_actions"


def _sidecar_action_rows(catalog_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _sidecar_action_queue_paths(catalog_row.get("run_dir")):
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if frame.empty:
            continue
        for _, action in frame.iterrows():
            item = action.to_dict()
            next_gate = _text(item.get("next_gate"))
            help_command = _text(item.get("next_gate_help_command"))
            if not next_gate and not help_command:
                continue
            blocker_fields = _action_blocker_fields(item, catalog_row)
            rows.append(
                {
                    "queue_status": _first_text(item, "queue_status")
                    or _queue_status(catalog_row.get("summary_status")),
                    "run_type": _text(catalog_row.get("run_type")),
                    "run_dir": _text(catalog_row.get("run_dir")),
                    "strategy": _first_text_from_sources(
                        item,
                        catalog_row,
                        "strategy",
                        "summary_strategy",
                        "summary_best_strategy",
                        "summary_runtime_strategy",
                    ),
                    "market": _first_text_from_sources(
                        item,
                        catalog_row,
                        "market",
                        "summary_market",
                        "summary_best_market",
                        "summary_runtime_market",
                    ),
                    "profile": _first_text_from_sources(
                        item,
                        catalog_row,
                        "profile",
                        "summary_evidence_profile",
                        "summary_profile",
                        "summary_best_profile",
                    ),
                    "summary_status": catalog_row.get("summary_status"),
                    "action_source_file": path.name,
                    "action_source": _text(item.get("source")),
                    "dataset": _text(item.get("dataset")),
                    "component": _text(item.get("component")),
                    "check": blocker_fields["primary_blocker_check"],
                    **blocker_fields,
                    "pipeline_dir": _text(item.get("pipeline_dir")),
                    "next_gate": next_gate,
                    "next_gate_help_command": help_command,
                    "recommendation": _action_recommendation(item, path),
                    "generated_at_utc": _text(catalog_row.get("generated_at_utc")),
                    "_source_priority": _int_metric(item.get("priority")),
                }
            )
    return rows


def _summary_blocker_fields(row: dict[str, Any]) -> dict[str, Any]:
    check = _first_text(row, "summary_primary_blocker_check", "summary_check")
    reason = _first_text(row, "summary_primary_blocker_reason", "summary_first_failed_reason")
    failed_check_names = _summary_failed_check_names(row, check)
    return {
        "failed_check_count": _summary_failed_check_count(row, failed_check_names, check),
        "failed_check_names": failed_check_names,
        "first_failed_reason": _first_text(row, "summary_first_failed_reason", "summary_primary_blocker_reason"),
        "primary_blocker_check": check,
        "primary_blocker_value": _jsonable(_first_existing(row, "summary_primary_blocker_value")),
        "primary_blocker_operator": _first_text(row, "summary_primary_blocker_operator"),
        "primary_blocker_threshold": _jsonable(_first_existing(row, "summary_primary_blocker_threshold")),
        "primary_blocker_reason": reason,
    }


def _action_blocker_fields(action: dict[str, Any], catalog_row: dict[str, Any]) -> dict[str, Any]:
    status = _first_text(action, "queue_status") or _queue_status(catalog_row.get("summary_status"))
    check = _action_check_name(action)
    reason = _action_blocker_reason(action)
    failed_count = _int_metric(_first_existing(action, "failed_check_count"))
    if failed_count == 0 and status == "blocked" and check:
        failed_count = 1
    failed_names = _first_text(action, "failed_check_names", "failed_checks")
    if not failed_names and status == "blocked":
        failed_names = check
    return {
        "failed_check_count": failed_count,
        "failed_check_names": failed_names,
        "first_failed_reason": _first_text(action, "first_failed_reason", "primary_blocker_reason") or reason,
        "primary_blocker_check": check,
        "primary_blocker_value": _jsonable(
            _first_existing(action, "primary_blocker_value", "actual", "observed", "value")
        ),
        "primary_blocker_operator": _first_text(action, "primary_blocker_operator", "operator"),
        "primary_blocker_threshold": _jsonable(
            _first_existing(action, "primary_blocker_threshold", "expected", "threshold")
        ),
        "primary_blocker_reason": reason,
    }


def _action_check_name(action: dict[str, Any]) -> str:
    check = _first_text(action, "primary_blocker_check", "check")
    if check:
        return check
    profile = _text(action.get("profile"))
    if profile:
        return f"profile_ready:{profile}"
    component = _text(action.get("component"))
    if component:
        return f"{component}_ready"
    return ""


def _action_blocker_reason(action: dict[str, Any]) -> str:
    reason = _first_text(action, "primary_blocker_reason", "reason", "message")
    if reason:
        return reason
    profile = _text(action.get("profile"))
    missing = _split_action_items(action.get("missing_required_run_types"))
    blocked = _split_action_items(action.get("blocked_required_run_types"))
    if profile and missing:
        return f"{profile} profile is missing required run type {missing[0]}"
    if profile and blocked:
        return f"{profile} profile has non-passing required run type {blocked[0]}"
    recommendation = _text(action.get("recommendation"))
    return recommendation


def _summary_failed_check_count(row: dict[str, Any], failed_check_names: str, check: str) -> int:
    explicit = _int_metric(_first_existing(row, "summary_failed_check_count"))
    if explicit:
        return explicit
    failed_checks = _first_existing(row, "summary_failed_checks")
    numeric = _int_metric(failed_checks)
    if numeric:
        return numeric
    if failed_check_names:
        return len(_split_action_items(failed_check_names))
    return 1 if check else 0


def _summary_failed_check_names(row: dict[str, Any], check: str) -> str:
    names = _first_text(row, "summary_failed_check_names")
    if names:
        return names
    failed_checks = _first_existing(row, "summary_failed_checks")
    if _is_numeric_text(failed_checks):
        return check
    return _text(failed_checks) or check


def _first_existing(row: dict[str, Any], *columns: str) -> Any:
    for column in columns:
        if column not in row:
            continue
        value = row.get(column)
        if _text(value):
            return value
    return ""


def _split_action_items(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _is_numeric_text(value: Any) -> bool:
    if _text(value) == "":
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _sidecar_action_queue_paths(run_dir: Any) -> list[Path]:
    run_dir_text = _text(run_dir)
    if not run_dir_text:
        return []
    path = Path(run_dir_text)
    if not path.exists() or not path.is_dir():
        return []
    return sorted(
        candidate
        for candidate in path.glob("*_action_queue.csv")
        if candidate.name not in EXCLUDED_SIDECAR_ACTION_QUEUES
    )


def _first_text_from_sources(primary: dict[str, Any], fallback: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = _text(primary.get(column))
        if value:
            return value
        value = _text(fallback.get(column))
        if value:
            return value
    return ""


def _action_recommendation(action: dict[str, Any], path: Path) -> str:
    recommendation = _first_text(action, "recommendation", "reason")
    if recommendation:
        return recommendation
    check = _text(action.get("check"))
    component = _text(action.get("component"))
    if check and component:
        return f"{path.name}:{component}:{check}"
    if check:
        return f"{path.name}:{check}"
    if component:
        return f"{path.name}:{component}"
    return path.name


def _queue_status(value: Any) -> str:
    if value is True:
        return "ready"
    if value is False:
        return "blocked"
    return "unknown"


def _queue_rank(status: str) -> int:
    return {"ready": 0, "blocked": 1, "unknown": 2}.get(status, 3)


def _catalog_runbook_markdown(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    hygiene_gaps: pd.DataFrame,
) -> str:
    ready = (
        _int_metric(summary_row.get("status_false_runs")) == 0
        and _int_metric(summary_row.get("missing_summary_runs")) == 0
    )
    lines = [
        "# Experiment Catalog Runbook",
        "",
        "## Readiness",
        "",
        f"- Ready: {'yes' if ready else 'no'}",
        f"- Runs: {_int_metric(summary_row.get('run_count'))}",
        f"- Run types: {_int_metric(summary_row.get('run_type_count'))}",
        f"- Status true runs: {_int_metric(summary_row.get('status_true_runs'))}",
        f"- Status false runs: {_int_metric(summary_row.get('status_false_runs'))}",
        f"- Missing summary runs: {_int_metric(summary_row.get('missing_summary_runs'))}",
        f"- Dirty runs: {_int_metric(summary_row.get('dirty_runs'))}",
        f"- Hygiene gaps: {_int_metric(summary_row.get('hygiene_gap_count'))}",
        "",
        "## Input Provenance",
        "",
        f"- Input files: {_int_metric(summary_row.get('input_file_count'))}",
        f"- Input directories: {_int_metric(summary_row.get('input_directory_count'))}",
        f"- Input hashes: {_int_metric(summary_row.get('input_hashed_count'))}",
        f"- Unfingerprinted inputs: {_int_metric(summary_row.get('input_unfingerprinted_count'))}",
        f"- Runs with directory inputs: {_int_metric(summary_row.get('runs_with_directory_inputs'))}",
        f"- Runs with unfingerprinted inputs: {_int_metric(summary_row.get('runs_with_unfingerprinted_inputs'))}",
        "",
        "## Broker Round-Trip Portfolio Proofs",
        "",
        f"- Broker round-trip runs: {_int_metric(summary_row.get('broker_roundtrip_runs'))}",
        f"- Passed broker round-trip runs: {_int_metric(summary_row.get('broker_roundtrip_passed_runs'))}",
        (
            "- Portfolio-provided broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_provided_runs'))}"
        ),
        (
            "- Portfolio-ready broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_ready_runs'))}"
        ),
        (
            "- Portfolio-safe broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_safe_runs'))}"
        ),
        (
            "- Portfolio-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_breach_runs'))}"
        ),
        (
            "- Portfolio-concentration broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_concentration_runs'))}"
        ),
        (
            "- Portfolio-concentration-ok broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_concentration_ok_runs'))}"
        ),
        (
            "- Portfolio-concentration-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_portfolio_concentration_breach_runs'))}"
        ),
        (
            "- Resume-route-provided broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_provided_runs'))}"
        ),
        (
            "- Resume-route-ready broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_ready_runs'))}"
        ),
        (
            "- Resume-route primary-ready broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_primary_ready_runs'))}"
        ),
        (
            "- Resume-route incident-ready broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_incident_ready_runs'))}"
        ),
        (
            "- Resume-route-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_breach_runs'))}"
        ),
        (
            "- Resume-route gap-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_gap_breach_runs'))}"
        ),
        (
            "- Resume-route launch-control-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_launch_control_breach_runs'))}"
        ),
        (
            "- Resume-route portfolio-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_portfolio_breach_runs'))}"
        ),
        (
            "- Resume-route concentration-breach broker round-trip runs: "
            f"{_int_metric(summary_row.get('broker_roundtrip_resume_route_concentration_breach_runs'))}"
        ),
        (
            "- Provider broker round-trip runs: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_runs'))}"
        ),
        (
            "- Provider broker round-trip passed runs: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_passed_runs'))}"
        ),
        (
            "- Provider broker round-trip synthetic datasets: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_synthetic_dataset_count'))}"
        ),
        (
            "- Provider broker round-trip synthetic sidecars: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_synthetic_sidecar_count'))}"
        ),
        (
            "- Provider broker round-trip readable synthetic sidecars: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_synthetic_sidecar_readable_count'))}"
        ),
        (
            "- Provider broker round-trip synthetic sidecar proof runs: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_synthetic_sidecar_proof_runs'))}"
        ),
        (
            "- Provider broker round-trip synthetic sidecar ready runs: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_synthetic_sidecar_ready_runs'))}"
        ),
        (
            "- Provider broker round-trip synthetic sidecar breach runs: "
            f"{_int_metric(summary_row.get('provider_broker_roundtrip_synthetic_sidecar_breach_runs'))}"
        ),
        "",
        "## Broker Schema Review",
        "",
        f"- Placeholder-schema active runs: {_int_metric(summary_row.get('placeholder_schema_active_runs'))}",
        f"- Placeholder-schema allowed runs: {_int_metric(summary_row.get('placeholder_schema_allowed_runs'))}",
        f"- Placeholder-schema reviewed runs: {_int_metric(summary_row.get('placeholder_schema_reviewed_runs'))}",
        (
            "- Placeholder-schema unreviewed runs: "
            f"{_int_metric(summary_row.get('placeholder_schema_unreviewed_runs'))}"
        ),
        f"- Placeholder-schema blocked runs: {_int_metric(summary_row.get('placeholder_schema_blocked_runs'))}",
        "",
        "## Hygiene Gaps",
        "",
        f"- Gap rows: {len(hygiene_gaps)}",
        "",
        _hygiene_gap_table(hygiene_gaps),
        "",
        "## Action Queue",
        "",
        f"- Queue rows: {len(action_queue)}",
        f"- Ready actions: {_int_metric(summary_row.get('action_queue_ready_count'))}",
        f"- Blocked actions: {_int_metric(summary_row.get('action_queue_blocked_count'))}",
        f"- Unknown actions: {_int_metric(summary_row.get('action_queue_unknown_count'))}",
        "",
        _action_queue_markdown_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _hygiene_gap_table(hygiene_gaps: pd.DataFrame) -> str:
    if hygiene_gaps.empty:
        return "_None_"
    columns = [
        "priority",
        "gap_type",
        "run_type",
        "summary_file",
        "input_unfingerprinted_count",
        "next_gate",
        "next_gate_help_command",
        "recommendation",
    ]
    headers = [
        "Priority",
        "Gap",
        "Run Type",
        "Summary File",
        "Unfingerprinted Inputs",
        "Next Gate",
        "Help Command",
        "Recommendation",
    ]
    rows = [
        [_format_markdown_cell(row.get(column)) for column in columns]
        for _, row in hygiene_gaps.iterrows()
    ]
    return _markdown_table(headers, rows)


def _action_queue_markdown_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    columns = [
        "priority",
        "queue_status",
        "run_type",
        "strategy",
        "market",
        "profile",
        "action_source_file",
        "action_source",
        "dataset",
        "component",
        "check",
        "first_failed_reason",
        "next_gate",
        "next_gate_help_command",
        "recommendation",
    ]
    headers = [
        "Priority",
        "Status",
        "Run Type",
        "Strategy",
        "Market",
        "Profile",
        "Source File",
        "Source",
        "Dataset",
        "Component",
        "Check",
        "First Failed Reason",
        "Next Gate",
        "Help Command",
        "Recommendation",
    ]
    rows = [
        [_format_markdown_cell(row.get(column)) for column in columns]
        for _, row in action_queue.iterrows()
    ]
    return _markdown_table(headers, rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(_escape_markdown_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape_markdown_cell(value) for value in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def _format_markdown_cell(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if text.startswith("python -m ") or "--" in text:
        return f"`{text}`"
    return text


def _escape_markdown_cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


def _int_metric(value: Any) -> int:
    numeric = _numeric(value)
    if pd.isna(numeric):
        return 0
    return int(numeric)


def _first_text(row: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = _text(row.get(column))
        if value:
            return value
    return ""


def _nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _input_stats(inputs: Any) -> dict[str, int]:
    stats = {
        "input_file_count": 0,
        "input_directory_count": 0,
        "input_other_count": 0,
        "input_hashed_count": 0,
        "input_unfingerprinted_count": 0,
    }
    _accumulate_input_stats(inputs, stats)
    return stats


def _accumulate_input_stats(value: Any, stats: dict[str, int]) -> None:
    if isinstance(value, dict):
        kind = value.get("kind")
        if isinstance(kind, str) and "path" in value:
            normalized = kind.strip().lower()
            if normalized == "file":
                stats["input_file_count"] += 1
            elif normalized == "directory":
                stats["input_directory_count"] += 1
            else:
                stats["input_other_count"] += 1
            if value.get("sha256") or value.get("tree_sha256"):
                stats["input_hashed_count"] += 1
            return
        for item in value.values():
            _accumulate_input_stats(item, stats)
        return
    if isinstance(value, list):
        for item in value:
            _accumulate_input_stats(item, stats)
        return
    if value is not None:
        stats["input_unfingerprinted_count"] += 1


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan
