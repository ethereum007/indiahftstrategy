from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
)
from reports.scaleup import load_strategy_portfolio_provenance


SCALEUP_REQUIRED_ARTIFACTS = (
    "scaleup_plan.csv",
    "scaleup_checks.csv",
    "scaleup_summary.csv",
    "scaleup_config.json",
)

BROKER_READINESS_LINEAGE_FIELDS = (
    ("lineage_required", "broker_readiness_lineage_required"),
    ("lineage_provided", "broker_readiness_lineage_provided"),
    ("manifest_current", "broker_readiness_manifest_current"),
    ("manifest_run_type", "broker_readiness_manifest_run_type"),
    ("manifest_path", "broker_readiness_manifest_path"),
    ("manifest_sha256", "broker_readiness_manifest_sha256"),
    ("manifest_error", "broker_readiness_manifest_error"),
    (
        "lineage_contract_consistent",
        "broker_readiness_lineage_contract_consistent",
    ),
    ("lineage_contract_error", "broker_readiness_lineage_contract_error"),
    (
        "roundtrip_lineage_required",
        "broker_readiness_roundtrip_lineage_required",
    ),
    (
        "roundtrip_lineage_gate_passed",
        "broker_readiness_roundtrip_lineage_gate_passed",
    ),
    (
        "roundtrip_matches_current",
        "broker_readiness_roundtrip_matches_current",
    ),
    ("lineage_gate_passed", "broker_readiness_lineage_gate_passed"),
    (
        "lineage_dependency_count",
        "broker_readiness_lineage_dependency_count",
    ),
)


def empty_scaleup_runtime_provenance(*, required: bool = False) -> dict[str, Any]:
    return {
        "manifest_required": required,
        "manifest_provided": False,
        "manifest_current": not required,
        "manifest_run_type": "",
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_error": "manifest_missing" if required else "",
        "contract_consistent": not required,
        "contract_error": "",
        "non_authorizing": not required,
        "source_ready": not required,
        "provenance_gate_passed": not required,
        "dependency_count": 0,
        "dependency_paths": [],
        "artifact_paths": [],
        "strategy_portfolio_required": False,
        "strategy_portfolio_provided": False,
        "strategy_portfolio_manifest_required": False,
        "strategy_portfolio_manifest_current": False,
        "strategy_portfolio_manifest_sha256": "",
        "strategy_portfolio_provenance_gate_passed": False,
        "scorecard_manifest_required": False,
        "scorecard_manifest_current": False,
        "scorecard_manifest_sha256": "",
        "scorecard_provenance_gate_passed": False,
        "research_family_bound": False,
        "research_family_provenance_current": False,
        "research_family_id": "",
        "research_family_registration_id": "",
        "research_family_manifest_sha256": "",
        "broker_readiness_required": False,
        "broker_readiness_provided": False,
        "broker_readiness_lineage_required": False,
        "broker_readiness_lineage_provided": False,
        "broker_readiness_manifest_current": False,
        "broker_readiness_manifest_run_type": "",
        "broker_readiness_manifest_path": "",
        "broker_readiness_manifest_sha256": "",
        "broker_readiness_manifest_error": "",
        "broker_readiness_lineage_contract_consistent": False,
        "broker_readiness_lineage_contract_error": "",
        "broker_readiness_roundtrip_lineage_required": False,
        "broker_readiness_roundtrip_lineage_gate_passed": False,
        "broker_readiness_roundtrip_matches_current": False,
        "broker_readiness_lineage_gate_passed": False,
        "broker_readiness_lineage_dependency_count": 0,
        "broker_readiness_source_manifest_current": False,
        "broker_readiness_source_manifest_sha256": "",
        "broker_readiness_source_provenance_gate_passed": False,
        "broker_readiness_matches_current": not required,
    }


def load_scaleup_runtime_provenance(
    scaleup_config_path: str | Path,
    *,
    scaleup_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_path = Path(scaleup_config_path).resolve()
    root = config_path.parent
    manifest_path = root / "manifest.json"
    evidence = empty_scaleup_runtime_provenance(required=True)
    evidence.update(
        {
            "manifest_path": str(manifest_path),
            "manifest_provided": manifest_path.is_file(),
            "artifact_paths": [
                str(root / name)
                for name in SCALEUP_REQUIRED_ARTIFACTS
                if (root / name).is_file()
            ],
        }
    )
    config = scaleup_config if isinstance(scaleup_config, dict) else _read_json(config_path)
    manifest = _read_json(manifest_path)
    summary = _read_csv(root / "scaleup_summary.csv")
    checks = _read_csv(root / "scaleup_checks.csv")
    plan = _read_csv(root / "scaleup_plan.csv")

    broker_readiness_active = _broker_readiness_active(config, manifest)
    broker_readiness_config_path = _manifest_input_path(
        manifest,
        "broker_readiness_config",
    )
    current_broker_readiness_fields: dict[str, Any] = {}
    if broker_readiness_config_path is not None:
        current_broker_readiness_fields = _broker_readiness_lineage_fields(
            _load_broker_readiness_lineage(broker_readiness_config_path)
        )

    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="scaleup_plan",
            required_artifacts=SCALEUP_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        evidence.update(
            {
                "manifest_current": bool(integrity.passed),
                "manifest_run_type": integrity.run_type,
                "manifest_sha256": file_sha256(manifest_path),
                "manifest_error": integrity.error,
                "dependency_paths": [
                    str(path) for path in manifest_dependency_paths(manifest_path)
                ],
            }
        )
    evidence["dependency_count"] = len(evidence["dependency_paths"])

    errors = _scaleup_contract_errors(
        config=config,
        manifest=manifest,
        summary=summary,
        checks=checks,
        plan=plan,
        broker_readiness_active=broker_readiness_active,
        broker_readiness_config_path=broker_readiness_config_path,
        current_broker_readiness_fields=current_broker_readiness_fields,
    )
    non_authorizing = _scaleup_non_authorizing(config, manifest, summary, plan)
    source_ready = _bool(config.get("ready", False))
    evidence.update(_lineage(config))
    broker_readiness_errors = [
        error
        for error in errors
        if error.startswith("scaleup_broker_readiness_")
    ]
    evidence.update(
        {
            "broker_readiness_source_manifest_current": _bool(
                current_broker_readiness_fields.get(
                    "broker_readiness_manifest_current",
                    False,
                )
            ),
            "broker_readiness_source_manifest_sha256": _text(
                current_broker_readiness_fields.get(
                    "broker_readiness_manifest_sha256",
                    "",
                )
            ),
            "broker_readiness_source_provenance_gate_passed": _bool(
                current_broker_readiness_fields.get(
                    "broker_readiness_lineage_gate_passed",
                    False,
                )
            ),
            "broker_readiness_matches_current": bool(
                not broker_readiness_active
                or (
                    broker_readiness_config_path is not None
                    and not broker_readiness_errors
                    and _bool(
                        current_broker_readiness_fields.get(
                            "broker_readiness_lineage_gate_passed",
                            False,
                        )
                    )
                )
            ),
        }
    )
    evidence["contract_consistent"] = not errors
    evidence["contract_error"] = ";".join(sorted(set(errors)))
    evidence["non_authorizing"] = non_authorizing
    evidence["source_ready"] = source_ready
    evidence["provenance_gate_passed"] = bool(
        evidence["manifest_provided"]
        and evidence["manifest_current"]
        and evidence["contract_consistent"]
        and non_authorizing
        and source_ready
    )
    return evidence


def scaleup_runtime_manifest_inputs(provenance: Mapping[str, Any]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    manifest_path = _existing_path(provenance.get("manifest_path"))
    if manifest_path is not None:
        inputs["scaleup_manifest"] = manifest_path
    artifacts = _existing_paths(provenance.get("artifact_paths"))
    if artifacts:
        inputs["scaleup_artifacts"] = artifacts
    dependencies = _existing_paths(provenance.get("dependency_paths"))
    if dependencies:
        inputs["scaleup_dependencies"] = dependencies
    return inputs


def scaleup_runtime_manifest_extra(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scaleup_manifest_current": _bool(provenance.get("manifest_current", False)),
        "scaleup_manifest_sha256": _text(provenance.get("manifest_sha256", "")),
        "scaleup_contract_consistent": _bool(provenance.get("contract_consistent", False)),
        "scaleup_non_authorizing": _bool(provenance.get("non_authorizing", False)),
        "scaleup_provenance_gate_passed": _bool(
            provenance.get("provenance_gate_passed", False)
        ),
        "strategy_portfolio_manifest_sha256": _text(
            provenance.get("strategy_portfolio_manifest_sha256", "")
        ),
        "scorecard_manifest_sha256": _text(
            provenance.get("scorecard_manifest_sha256", "")
        ),
        "research_family_bound": _bool(
            provenance.get("research_family_bound", False)
        ),
        "research_family_id": _text(provenance.get("research_family_id", "")),
        "research_family_registration_id": _text(
            provenance.get("research_family_registration_id", "")
        ),
        "research_family_manifest_sha256": _text(
            provenance.get("research_family_manifest_sha256", "")
        ),
        "broker_readiness_manifest_sha256": _text(
            provenance.get("broker_readiness_manifest_sha256", "")
        ),
        "broker_readiness_source_manifest_sha256": _text(
            provenance.get("broker_readiness_source_manifest_sha256", "")
        ),
        "broker_readiness_lineage_gate_passed": _bool(
            provenance.get("broker_readiness_lineage_gate_passed", False)
        ),
        "broker_readiness_matches_current": _bool(
            provenance.get("broker_readiness_matches_current", False)
        ),
        "authorizes_submission": False,
    }


def scaleup_runtime_fields(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scaleup_manifest_required": _bool(provenance.get("manifest_required", False)),
        "scaleup_manifest_provided": _bool(provenance.get("manifest_provided", False)),
        "scaleup_manifest_current": _bool(provenance.get("manifest_current", False)),
        "scaleup_manifest_run_type": _text(provenance.get("manifest_run_type", "")),
        "scaleup_manifest_path": _text(provenance.get("manifest_path", "")),
        "scaleup_manifest_sha256": _text(provenance.get("manifest_sha256", "")),
        "scaleup_manifest_error": _text(provenance.get("manifest_error", "")),
        "scaleup_contract_consistent": _bool(provenance.get("contract_consistent", False)),
        "scaleup_contract_error": _text(provenance.get("contract_error", "")),
        "scaleup_non_authorizing": _bool(provenance.get("non_authorizing", False)),
        "scaleup_source_ready": _bool(provenance.get("source_ready", False)),
        "scaleup_provenance_gate_passed": _bool(
            provenance.get("provenance_gate_passed", False)
        ),
        "scaleup_dependency_count": int(provenance.get("dependency_count", 0)),
        "scaleup_strategy_portfolio_required": _bool(
            provenance.get("strategy_portfolio_required", False)
        ),
        "scaleup_strategy_portfolio_provided": _bool(
            provenance.get("strategy_portfolio_provided", False)
        ),
        "scaleup_strategy_portfolio_manifest_required": _bool(
            provenance.get("strategy_portfolio_manifest_required", False)
        ),
        "scaleup_strategy_portfolio_manifest_current": _bool(
            provenance.get("strategy_portfolio_manifest_current", False)
        ),
        "scaleup_strategy_portfolio_manifest_sha256": _text(
            provenance.get("strategy_portfolio_manifest_sha256", "")
        ),
        "scaleup_strategy_portfolio_provenance_gate_passed": _bool(
            provenance.get("strategy_portfolio_provenance_gate_passed", False)
        ),
        "scaleup_scorecard_manifest_required": _bool(
            provenance.get("scorecard_manifest_required", False)
        ),
        "scaleup_scorecard_manifest_current": _bool(
            provenance.get("scorecard_manifest_current", False)
        ),
        "scaleup_scorecard_manifest_sha256": _text(
            provenance.get("scorecard_manifest_sha256", "")
        ),
        "scaleup_scorecard_provenance_gate_passed": _bool(
            provenance.get("scorecard_provenance_gate_passed", False)
        ),
        "scaleup_research_family_bound": _bool(
            provenance.get("research_family_bound", False)
        ),
        "scaleup_research_family_provenance_current": _bool(
            provenance.get("research_family_provenance_current", False)
        ),
        "scaleup_research_family_id": _text(provenance.get("research_family_id", "")),
        "scaleup_research_family_registration_id": _text(
            provenance.get("research_family_registration_id", "")
        ),
        "scaleup_research_family_manifest_sha256": _text(
            provenance.get("research_family_manifest_sha256", "")
        ),
        "scaleup_broker_readiness_required": _bool(
            provenance.get("broker_readiness_required", False)
        ),
        "scaleup_broker_readiness_provided": _bool(
            provenance.get("broker_readiness_provided", False)
        ),
        "scaleup_broker_readiness_lineage_required": _bool(
            provenance.get("broker_readiness_lineage_required", False)
        ),
        "scaleup_broker_readiness_lineage_provided": _bool(
            provenance.get("broker_readiness_lineage_provided", False)
        ),
        "scaleup_broker_readiness_manifest_current": _bool(
            provenance.get("broker_readiness_manifest_current", False)
        ),
        "scaleup_broker_readiness_manifest_run_type": _text(
            provenance.get("broker_readiness_manifest_run_type", "")
        ),
        "scaleup_broker_readiness_manifest_path": _text(
            provenance.get("broker_readiness_manifest_path", "")
        ),
        "scaleup_broker_readiness_manifest_sha256": _text(
            provenance.get("broker_readiness_manifest_sha256", "")
        ),
        "scaleup_broker_readiness_manifest_error": _text(
            provenance.get("broker_readiness_manifest_error", "")
        ),
        "scaleup_broker_readiness_lineage_contract_consistent": _bool(
            provenance.get(
                "broker_readiness_lineage_contract_consistent",
                False,
            )
        ),
        "scaleup_broker_readiness_lineage_contract_error": _text(
            provenance.get("broker_readiness_lineage_contract_error", "")
        ),
        "scaleup_broker_readiness_roundtrip_lineage_required": _bool(
            provenance.get("broker_readiness_roundtrip_lineage_required", False)
        ),
        "scaleup_broker_readiness_roundtrip_lineage_gate_passed": _bool(
            provenance.get(
                "broker_readiness_roundtrip_lineage_gate_passed",
                False,
            )
        ),
        "scaleup_broker_readiness_roundtrip_matches_current": _bool(
            provenance.get("broker_readiness_roundtrip_matches_current", False)
        ),
        "scaleup_broker_readiness_lineage_gate_passed": _bool(
            provenance.get("broker_readiness_lineage_gate_passed", False)
        ),
        "scaleup_broker_readiness_lineage_dependency_count": int(
            provenance.get("broker_readiness_lineage_dependency_count", 0)
        ),
        "scaleup_broker_readiness_source_manifest_current": _bool(
            provenance.get("broker_readiness_source_manifest_current", False)
        ),
        "scaleup_broker_readiness_source_manifest_sha256": _text(
            provenance.get("broker_readiness_source_manifest_sha256", "")
        ),
        "scaleup_broker_readiness_source_provenance_gate_passed": _bool(
            provenance.get(
                "broker_readiness_source_provenance_gate_passed",
                False,
            )
        ),
        "scaleup_broker_readiness_matches_current": _bool(
            provenance.get("broker_readiness_matches_current", False)
        ),
    }


def _scaleup_contract_errors(
    *,
    config: dict[str, Any],
    manifest: dict[str, Any],
    summary: pd.DataFrame,
    checks: pd.DataFrame,
    plan: pd.DataFrame,
    broker_readiness_active: bool,
    broker_readiness_config_path: Path | None,
    current_broker_readiness_fields: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not config:
        errors.append("scaleup_config_missing_or_invalid")
    if summary.empty:
        errors.append("scaleup_summary_missing_or_empty")
    if checks.empty or "passed" not in checks.columns:
        errors.append("scaleup_checks_missing_or_invalid")
    if plan.empty:
        errors.append("scaleup_plan_missing_or_empty")
    if not manifest:
        errors.append("scaleup_manifest_missing_or_invalid")
    if errors:
        return errors

    row = summary.iloc[0]
    plan_row = plan.iloc[0]
    extra = _mapping(manifest.get("extra"))
    ready = _bool(config.get("ready", False))
    for source, value in (
        ("summary", row.get("ready", False)),
        ("plan", plan_row.get("ready", False)),
        ("manifest", extra.get("ready", False)),
    ):
        if _bool(value) != ready:
            errors.append(f"scaleup_{source}_ready_mismatch")
    checks_ready = bool(checks["passed"].map(_bool).all())
    if checks_ready != ready:
        errors.append("scaleup_checks_ready_mismatch")
    failed_count = int((~checks["passed"].map(_bool)).sum())
    if _integer(config.get("failed_check_count", -1), fallback=-1) != failed_count:
        errors.append("scaleup_failed_check_count_mismatch")

    for field in ("target_mode", "strategy", "market", "scenario_key", "adapter"):
        if not _same(row.get(field, ""), config.get(field, "")):
            errors.append(f"scaleup_summary_{field}_mismatch")
        if field in plan_row.index and not _same(plan_row.get(field, ""), config.get(field, "")):
            errors.append(f"scaleup_plan_{field}_mismatch")
    limits = _mapping(config.get("limits"))
    for config_field, summary_field in (
        ("max_orders_per_session", "max_orders_per_session"),
        ("max_notional_per_session", "max_notional_per_session"),
        ("pre_portfolio_max_notional_per_session", "pre_portfolio_max_notional_per_session"),
    ):
        if config_field in limits and summary_field in row.index:
            if not _same(row.get(summary_field), limits.get(config_field)):
                errors.append(f"scaleup_summary_{summary_field}_mismatch")

    portfolio = _mapping(config.get("strategy_portfolio"))
    portfolio_active = _bool(portfolio.get("required", False)) or _bool(
        portfolio.get("provided", False)
    )
    if portfolio_active:
        errors.extend(
            _portfolio_contract_errors(
                manifest=manifest,
                manifest_extra=extra,
                summary=row,
                portfolio=portfolio,
            )
        )
    if broker_readiness_active:
        errors.extend(
            _broker_readiness_contract_errors(
                manifest_extra=extra,
                summary=row,
                plan=plan_row,
                broker_readiness=_mapping(config.get("broker_readiness")),
                broker_readiness_config_path=broker_readiness_config_path,
                current_fields=current_broker_readiness_fields,
            )
        )
    return errors


def _broker_readiness_contract_errors(
    *,
    manifest_extra: dict[str, Any],
    summary: pd.Series,
    plan: pd.Series,
    broker_readiness: dict[str, Any],
    broker_readiness_config_path: Path | None,
    current_fields: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    lineage = _mapping(broker_readiness.get("lineage"))
    for config_field, report_field in BROKER_READINESS_LINEAGE_FIELDS:
        if config_field not in lineage:
            errors.append(
                f"scaleup_broker_readiness_{config_field}_missing:config"
            )
            expected: Any = None
        else:
            expected = lineage.get(config_field)
        for source, row in (("summary", summary), ("plan", plan)):
            if report_field not in row.index:
                errors.append(
                    f"scaleup_broker_readiness_{config_field}_missing:{source}"
                )
            elif config_field in lineage and not _same(row.get(report_field), expected):
                errors.append(
                    f"scaleup_broker_readiness_{config_field}_{source}_mismatch"
                )
        if report_field not in manifest_extra:
            errors.append(
                f"scaleup_broker_readiness_{config_field}_missing:manifest"
            )
        elif config_field in lineage and not _same(
            manifest_extra.get(report_field),
            expected,
        ):
            errors.append(
                f"scaleup_broker_readiness_{config_field}_manifest_mismatch"
            )

    if broker_readiness_config_path is None:
        errors.append("scaleup_broker_readiness_source_missing")
        return errors
    for config_field, report_field in BROKER_READINESS_LINEAGE_FIELDS:
        if config_field not in lineage:
            continue
        if not _same(lineage.get(config_field), current_fields.get(report_field)):
            errors.append(
                f"scaleup_broker_readiness_{config_field}_source_mismatch"
            )
    if not _bool(
        current_fields.get("broker_readiness_lineage_gate_passed", False)
    ):
        errors.append("scaleup_broker_readiness_source_provenance_not_current")
    return errors


def _portfolio_contract_errors(
    *,
    manifest: dict[str, Any],
    manifest_extra: dict[str, Any],
    summary: pd.Series,
    portfolio: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    summary_fields = {
        "required": "strategy_portfolio_required",
        "provided": "strategy_portfolio_provided",
        "manifest_required": "strategy_portfolio_manifest_required",
        "manifest_provided": "strategy_portfolio_manifest_provided",
        "manifest_current": "strategy_portfolio_manifest_current",
        "manifest_sha256": "strategy_portfolio_manifest_sha256",
        "contract_consistent": "strategy_portfolio_contract_consistent",
        "non_authorizing": "strategy_portfolio_non_authorizing",
        "provenance_gate_passed": "strategy_portfolio_provenance_gate_passed",
    }
    for config_field, summary_field in summary_fields.items():
        if not _same(summary.get(summary_field, ""), portfolio.get(config_field, "")):
            errors.append(f"scaleup_portfolio_{config_field}_summary_mismatch")

    scorecard = _mapping(portfolio.get("scorecard_provenance"))
    for config_field, summary_field in (
        ("manifest_required", "strategy_portfolio_scorecard_manifest_required"),
        ("manifest_current", "strategy_portfolio_scorecard_manifest_current"),
        ("manifest_sha256", "strategy_portfolio_scorecard_manifest_sha256"),
        ("contract_consistent", "strategy_portfolio_scorecard_contract_consistent"),
        ("non_authorizing", "strategy_portfolio_scorecard_non_authorizing"),
        ("gate_passed", "strategy_portfolio_scorecard_provenance_gate_passed"),
    ):
        if not _same(summary.get(summary_field, ""), scorecard.get(config_field, "")):
            errors.append(f"scaleup_scorecard_{config_field}_summary_mismatch")

    family = _mapping(portfolio.get("research_family"))
    for config_field, summary_field in (
        ("bound", "strategy_portfolio_research_family_bound"),
        ("provenance_current", "strategy_portfolio_research_family_provenance_current"),
        ("family_id", "strategy_portfolio_research_family_id"),
        ("registration_id", "strategy_portfolio_research_family_registration_id"),
        ("manifest_sha256", "strategy_portfolio_research_family_manifest_sha256"),
    ):
        if not _same(summary.get(summary_field, ""), family.get(config_field, "")):
            errors.append(f"scaleup_family_{config_field}_summary_mismatch")

    for extra_field, expected in (
        ("strategy_portfolio_manifest_required", portfolio.get("manifest_required", False)),
        ("strategy_portfolio_manifest_current", portfolio.get("manifest_current", False)),
        ("strategy_portfolio_manifest_sha256", portfolio.get("manifest_sha256", "")),
        ("research_family_bound", family.get("bound", False)),
        ("research_family_id", family.get("family_id", "")),
        ("research_family_registration_id", family.get("registration_id", "")),
        ("research_family_manifest_sha256", family.get("manifest_sha256", "")),
    ):
        if not _same(manifest_extra.get(extra_field, ""), expected):
            errors.append(f"scaleup_manifest_{extra_field}_mismatch")

    portfolio_summary_path = _manifest_input_path(manifest, "strategy_portfolio")
    if portfolio_summary_path is None:
        errors.append("scaleup_portfolio_source_missing")
        return errors
    allocations_path = portfolio_summary_path.parent / "strategy_portfolio_allocations.csv"
    fresh = load_strategy_portfolio_provenance(
        portfolio_summary_path,
        _read_csv(portfolio_summary_path),
        _read_csv(allocations_path),
    )
    comparisons = (
        ("manifest_required", "manifest_required"),
        ("manifest_provided", "manifest_provided"),
        ("manifest_current", "manifest_current"),
        ("manifest_sha256", "manifest_sha256"),
        ("contract_consistent", "contract_consistent"),
        ("non_authorizing", "non_authorizing"),
        ("provenance_gate_passed", "gate_passed"),
    )
    for config_field, fresh_field in comparisons:
        if not _same(portfolio.get(config_field, ""), fresh.get(fresh_field, "")):
            errors.append(f"scaleup_portfolio_{config_field}_source_mismatch")
    for config_field, fresh_field in (
        ("manifest_required", "scorecard_manifest_required"),
        ("manifest_current", "scorecard_manifest_current"),
        ("manifest_sha256", "scorecard_manifest_sha256"),
        ("contract_consistent", "scorecard_contract_consistent"),
        ("non_authorizing", "scorecard_non_authorizing"),
        ("gate_passed", "scorecard_provenance_gate_passed"),
    ):
        if not _same(scorecard.get(config_field, ""), fresh.get(fresh_field, "")):
            errors.append(f"scaleup_scorecard_{config_field}_source_mismatch")
    for config_field, fresh_field in (
        ("bound", "research_family_bound"),
        ("provenance_current", "research_family_provenance_current"),
        ("family_id", "research_family_id"),
        ("registration_id", "research_family_registration_id"),
        ("manifest_sha256", "research_family_manifest_sha256"),
    ):
        if not _same(family.get(config_field, ""), fresh.get(fresh_field, "")):
            errors.append(f"scaleup_family_{config_field}_source_mismatch")
    if not _bool(fresh.get("gate_passed", False)):
        errors.append("scaleup_portfolio_source_provenance_not_current")
    return errors


def _scaleup_non_authorizing(
    config: dict[str, Any],
    manifest: dict[str, Any],
    summary: pd.DataFrame,
    plan: pd.DataFrame,
) -> bool:
    extra = _mapping(manifest.get("extra"))
    required_claims = (
        "authorizes_submission" in config,
        "authorizes_submission" in extra,
        not summary.empty and "authorizes_submission" in summary.columns,
        not plan.empty and "authorizes_submission" in plan.columns,
    )
    if not all(required_claims):
        return False
    return bool(
        not _bool(config.get("authorizes_submission", True))
        and not _bool(extra.get("authorizes_submission", True))
        and not summary["authorizes_submission"].map(_bool).any()
        and not plan["authorizes_submission"].map(_bool).any()
    )


def _lineage(config: dict[str, Any]) -> dict[str, Any]:
    portfolio = _mapping(config.get("strategy_portfolio"))
    scorecard = _mapping(portfolio.get("scorecard_provenance"))
    family = _mapping(portfolio.get("research_family"))
    broker_readiness = _mapping(config.get("broker_readiness"))
    broker_lineage = _mapping(broker_readiness.get("lineage"))
    return {
        "strategy_portfolio_required": _bool(portfolio.get("required", False)),
        "strategy_portfolio_provided": _bool(portfolio.get("provided", False)),
        "strategy_portfolio_manifest_required": _bool(
            portfolio.get("manifest_required", False)
        ),
        "strategy_portfolio_manifest_current": _bool(
            portfolio.get("manifest_current", False)
        ),
        "strategy_portfolio_manifest_sha256": _text(
            portfolio.get("manifest_sha256", "")
        ),
        "strategy_portfolio_provenance_gate_passed": _bool(
            portfolio.get("provenance_gate_passed", False)
        ),
        "scorecard_manifest_required": _bool(scorecard.get("manifest_required", False)),
        "scorecard_manifest_current": _bool(scorecard.get("manifest_current", False)),
        "scorecard_manifest_sha256": _text(scorecard.get("manifest_sha256", "")),
        "scorecard_provenance_gate_passed": _bool(scorecard.get("gate_passed", False)),
        "research_family_bound": _bool(family.get("bound", False)),
        "research_family_provenance_current": _bool(
            family.get("provenance_current", False)
        ),
        "research_family_id": _text(family.get("family_id", "")),
        "research_family_registration_id": _text(family.get("registration_id", "")),
        "research_family_manifest_sha256": _text(family.get("manifest_sha256", "")),
        "broker_readiness_required": _bool(
            broker_readiness.get("required", False)
        ),
        "broker_readiness_provided": _bool(
            broker_readiness.get("provided", False)
        ),
        "broker_readiness_lineage_required": _bool(
            broker_lineage.get("lineage_required", False)
        ),
        "broker_readiness_lineage_provided": _bool(
            broker_lineage.get("lineage_provided", False)
        ),
        "broker_readiness_manifest_current": _bool(
            broker_lineage.get("manifest_current", False)
        ),
        "broker_readiness_manifest_run_type": _text(
            broker_lineage.get("manifest_run_type", "")
        ),
        "broker_readiness_manifest_path": _text(
            broker_lineage.get("manifest_path", "")
        ),
        "broker_readiness_manifest_sha256": _text(
            broker_lineage.get("manifest_sha256", "")
        ),
        "broker_readiness_manifest_error": _text(
            broker_lineage.get("manifest_error", "")
        ),
        "broker_readiness_lineage_contract_consistent": _bool(
            broker_lineage.get("lineage_contract_consistent", False)
        ),
        "broker_readiness_lineage_contract_error": _text(
            broker_lineage.get("lineage_contract_error", "")
        ),
        "broker_readiness_roundtrip_lineage_required": _bool(
            broker_lineage.get("roundtrip_lineage_required", False)
        ),
        "broker_readiness_roundtrip_lineage_gate_passed": _bool(
            broker_lineage.get("roundtrip_lineage_gate_passed", False)
        ),
        "broker_readiness_roundtrip_matches_current": _bool(
            broker_lineage.get("roundtrip_matches_current", False)
        ),
        "broker_readiness_lineage_gate_passed": _bool(
            broker_lineage.get("lineage_gate_passed", False)
        ),
        "broker_readiness_lineage_dependency_count": _integer(
            broker_lineage.get("lineage_dependency_count", 0)
        ),
    }


def _broker_readiness_active(
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    broker_readiness = _mapping(config.get("broker_readiness"))
    lineage = _mapping(broker_readiness.get("lineage"))
    inputs = _mapping(manifest.get("inputs"))
    return bool(
        _bool(broker_readiness.get("required", False))
        or _bool(broker_readiness.get("provided", False))
        or _bool(lineage.get("lineage_required", False))
        or _bool(lineage.get("lineage_provided", False))
        or any(
            name in inputs
            for name in (
                "broker_readiness",
                "broker_readiness_config",
                "broker_readiness_manifest",
            )
        )
    )


def _load_broker_readiness_lineage(config_path: str | Path) -> dict[str, Any]:
    from reports.operational_lineage import load_broker_readiness_lineage

    return load_broker_readiness_lineage(config_path)


def _broker_readiness_lineage_fields(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    from reports.operational_lineage import broker_readiness_lineage_fields

    return broker_readiness_lineage_fields(lineage)


def _manifest_input_path(manifest: dict[str, Any], name: str) -> Path | None:
    value = _mapping(manifest.get("inputs")).get(name)
    if isinstance(value, Mapping):
        return _existing_path(value.get("path"))
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return _bool(actual) == expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if pd.isna(actual_number) and pd.isna(expected_number):
            return True
        return abs(actual_number - expected_number) <= 1e-9
    return _text(actual) == _text(expected)


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _integer(value: Any, *, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _existing_path(value: Any) -> Path | None:
    text = _text(value)
    if not text:
        return None
    path = Path(text)
    return path if path.exists() else None


def _existing_paths(value: Any) -> list[Path]:
    if not isinstance(value, (list, tuple)):
        return []
    return [path for item in value if (path := _existing_path(item)) is not None]
