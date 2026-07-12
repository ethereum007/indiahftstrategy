from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.evidence import _normalize_identity, _normalize_strategy
from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


SCORECARD_REQUIRED_ARTIFACTS = (
    "strategy_scorecard.csv",
    "strategy_scorecard_gaps.csv",
    "strategy_scorecard_summary.csv",
    "strategy_scorecard_action_queue.csv",
    "strategy_scorecard_next_actions.json",
    "strategy_scorecard_runbook.md",
)
RESEARCH_FAMILY_REQUIRED_ARTIFACTS = (
    "research_family_studies.csv",
    "research_family_checks.csv",
    "research_family_summary.csv",
    "research_family_action_queue.csv",
    "research_family_launch_attempt_census.csv",
    "research_family_config.json",
    "research_family_runbook.md",
)


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "profile",
    "strategy",
    "market",
    "readiness_score",
    "allocation_weight",
    "allocation_notional",
    "eligibility_reason",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


@dataclass(frozen=True)
class StrategyPortfolioConfig:
    total_capital: float = 1_000_000.0
    capital_currency: str = "INR"
    reserve_weight: float = 0.10
    max_profile_weight: float = 0.40
    min_readiness_score: float = 1.0
    require_ready: bool = True
    include_profiles: tuple[str, ...] = ()
    exclude_profiles: tuple[str, ...] = ()
    allocation_mode: str = "readiness_weighted"
    deployment_mode: str = "paper_shadow"
    min_strategy_count: int = 1
    min_market_count: int = 1
    max_strategy_weight: float | None = None
    max_market_weight: float | None = None
    require_scorecard_manifest: bool = False


@dataclass(frozen=True)
class StrategyPortfolioReport:
    allocations: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_strategy_portfolio(
    scorecard: pd.DataFrame,
    *,
    config: StrategyPortfolioConfig | None = None,
) -> StrategyPortfolioReport:
    config = config or StrategyPortfolioConfig()
    return _evaluate_strategy_portfolio(
        scorecard,
        config=config,
        scorecard_evidence=None,
    )


def _evaluate_strategy_portfolio(
    scorecard: pd.DataFrame,
    *,
    config: StrategyPortfolioConfig,
    scorecard_evidence: dict[str, Any] | None,
) -> StrategyPortfolioReport:
    normalized = _normalize_scorecard(scorecard)
    evidence = _resolve_scorecard_evidence(
        normalized,
        config,
        scorecard_evidence,
    )
    normalized = _apply_scorecard_evidence(normalized, evidence)
    allocations = _allocations(normalized, config)
    checks = _checks(allocations, config, evidence)
    summary = _summary(allocations, checks, config, evidence)
    action_queue = _action_queue(allocations, checks)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        allocations,
        checks,
        summary,
        config,
        action_queue,
        evidence,
    )
    return StrategyPortfolioReport(
        allocations=allocations,
        checks=checks,
        summary=summary,
        config=payload,
        action_queue=action_queue,
    )


def write_strategy_portfolio_allocations(
    scorecard_path: str | Path,
    *,
    output_dir: str | Path,
    config: StrategyPortfolioConfig | None = None,
) -> StrategyPortfolioReport:
    scorecard_file = _scorecard_path(scorecard_path)
    scorecard = pd.read_csv(scorecard_file)
    config = config or StrategyPortfolioConfig()
    scorecard_evidence = _load_scorecard_evidence(
        scorecard_file,
        scorecard,
        config,
    )
    report = _evaluate_strategy_portfolio(
        scorecard,
        config=config,
        scorecard_evidence=scorecard_evidence,
    )
    out = Path(output_dir)
    if (
        scorecard_evidence.get("manifest_provided", False)
        and out.resolve() == scorecard_file.parent.resolve()
    ):
        raise ValueError(
            "strategy portfolio output must not overwrite the source "
            "strategy scorecard bundle"
        )
    out.mkdir(parents=True, exist_ok=True)
    report.allocations.to_csv(out / "strategy_portfolio_allocations.csv", index=False)
    report.checks.to_csv(out / "strategy_portfolio_checks.csv", index=False)
    report.summary.to_csv(out / "strategy_portfolio_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.allocations, report.checks)
    action_queue.to_csv(out / "strategy_portfolio_action_queue.csv", index=False)
    (out / "strategy_portfolio_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "strategy_portfolio_runbook.md").write_text(
        _runbook_markdown(report.config),
        encoding="utf-8",
    )
    manifest_inputs: dict[str, Any] = {"strategy_scorecard": scorecard_file}
    if scorecard_evidence.get("manifest_provided", False):
        scorecard_root = Path(str(scorecard_evidence["root"]))
        manifest_inputs["strategy_scorecard_manifest"] = Path(
            str(scorecard_evidence["manifest_path"])
        )
        for artifact in SCORECARD_REQUIRED_ARTIFACTS:
            artifact_path = scorecard_root / artifact
            if artifact_path.is_file() and artifact != "strategy_scorecard.csv":
                manifest_inputs[f"strategy_scorecard_artifact:{artifact}"] = artifact_path
        dependency_paths = [
            Path(str(path))
            for path in scorecard_evidence.get("dependency_paths", [])
            if _text(path)
        ]
        if dependency_paths:
            manifest_inputs["strategy_scorecard_dependencies"] = (
                dependency_paths
            )
    raw_family_path = _text(
        scorecard_evidence.get("research_family_path", "")
    )
    family_path = Path(raw_family_path) if raw_family_path else Path()
    if (
        scorecard_evidence.get("research_family_bound", False)
        and raw_family_path
        and family_path.is_dir()
    ):
        manifest_inputs["research_family_audit"] = family_path
        family_manifest = family_path / "manifest.json"
        if family_manifest.is_file():
            manifest_inputs["research_family_manifest"] = family_manifest
    write_experiment_manifest(
        out,
        run_type="strategy_portfolio_allocation",
        parameters={"allocation": asdict(config)},
        inputs=manifest_inputs,
        extra={
            "ready": bool(report.ready),
            "scorecard_manifest_required": bool(
                scorecard_evidence.get("manifest_required", False)
            ),
            "scorecard_manifest_current": bool(
                scorecard_evidence.get("manifest_current", False)
            ),
            "scorecard_manifest_sha256": _text(
                scorecard_evidence.get("manifest_sha256", "")
            ),
            "research_family_bound": bool(
                scorecard_evidence.get("research_family_bound", False)
            ),
            "research_family_id": _text(
                scorecard_evidence.get("research_family_id", "")
            ),
            "research_family_registration_id": _text(
                scorecard_evidence.get("research_family_registration_id", "")
            ),
            "research_family_manifest_sha256": _text(
                scorecard_evidence.get(
                    "research_family_manifest_sha256",
                    "",
                )
            ),
            "authorizes_submission": False,
        },
    )
    return StrategyPortfolioReport(report.allocations, report.checks, report.summary, report.config, out, action_queue)


def _load_scorecard_evidence(
    scorecard_file: Path,
    scorecard: pd.DataFrame,
    config: StrategyPortfolioConfig,
) -> dict[str, Any]:
    normalized = _normalize_scorecard(scorecard)
    evidence = _empty_scorecard_evidence(normalized, config)
    root = scorecard_file.parent.resolve()
    manifest_path = root / "manifest.json"
    evidence.update(
        {
            "path": str(scorecard_file.resolve()),
            "root": str(root),
            "manifest_path": str(manifest_path),
            "manifest_provided": manifest_path.is_file(),
        }
    )
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="strategy_scorecard",
            required_artifacts=SCORECARD_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        evidence["manifest_current"] = bool(integrity.passed)
        evidence["manifest_error"] = _text(integrity.error)
        evidence["manifest_sha256"] = file_sha256(manifest_path)
        evidence["dependency_paths"] = [
            str(path) for path in manifest_dependency_paths(manifest_path)
        ]
        contract_errors = _scorecard_contract_errors(
            normalized,
            root,
            _read_json_object(manifest_path),
        )
        evidence["contract_consistent"] = not contract_errors
        evidence["contract_error"] = ";".join(contract_errors)

    family = _research_family_provenance(normalized, root)
    evidence.update(family)
    return _resolve_scorecard_evidence(normalized, config, evidence)


def _empty_scorecard_evidence(
    scorecard: pd.DataFrame,
    config: StrategyPortfolioConfig,
) -> dict[str, Any]:
    family_bound = _scorecard_family_bound(scorecard)
    family_reference = _scorecard_family_reference(scorecard)
    non_authorizing = not bool(
        scorecard.get("authorizes_submission", pd.Series(dtype=bool))
        .map(_bool)
        .any()
    )
    return {
        "path": "",
        "root": "",
        "manifest_path": "",
        "manifest_required": bool(
            config.require_scorecard_manifest or family_bound
        ),
        "manifest_provided": False,
        "manifest_current": False,
        "manifest_sha256": "",
        "manifest_error": "manifest_missing" if family_bound else "",
        "dependency_paths": [],
        "contract_consistent": True,
        "contract_error": "",
        "non_authorizing": non_authorizing,
        "research_family_bound": family_bound,
        "research_family_provenance_current": not family_bound,
        "research_family_provenance_error": (
            "research_family_proof_not_verified" if family_bound else ""
        ),
        "research_family_id": _text(
            family_reference.get("research_family_id", "")
        ),
        "research_family_registration_id": _text(
            family_reference.get("research_family_registration_id", "")
        ),
        "research_family_path": _text(
            family_reference.get("research_family_path", "")
        ),
        "research_family_manifest_sha256": _text(
            family_reference.get("research_family_manifest_sha256", "")
        ),
        "gate_passed": False,
    }


def _resolve_scorecard_evidence(
    scorecard: pd.DataFrame,
    config: StrategyPortfolioConfig,
    supplied: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence = _empty_scorecard_evidence(scorecard, config)
    if supplied:
        evidence.update(supplied)
    family_bound = bool(
        evidence.get("research_family_bound", False)
        or _scorecard_family_bound(scorecard)
    )
    required = bool(
        config.require_scorecard_manifest
        or family_bound
        or evidence.get("manifest_required", False)
    )
    provided = bool(evidence.get("manifest_provided", False))
    manifest_ok = bool(
        (not required and not provided)
        or (provided and evidence.get("manifest_current", False))
    )
    contract_ok = bool(
        (not required and not provided)
        or (provided and evidence.get("contract_consistent", False))
    )
    family_ok = bool(
        not family_bound
        or evidence.get("research_family_provenance_current", False)
    )
    non_authorizing = bool(evidence.get("non_authorizing", False))
    evidence.update(
        {
            "manifest_required": required,
            "manifest_provided": provided,
            "research_family_bound": family_bound,
            "non_authorizing": non_authorizing,
            "gate_passed": bool(
                manifest_ok and contract_ok and family_ok and non_authorizing
            ),
        }
    )
    return evidence


def _apply_scorecard_evidence(
    scorecard: pd.DataFrame,
    evidence: dict[str, Any],
) -> pd.DataFrame:
    frame = scorecard.copy()
    values = {
        "scorecard_manifest_required": bool(
            evidence.get("manifest_required", False)
        ),
        "scorecard_manifest_provided": bool(
            evidence.get("manifest_provided", False)
        ),
        "scorecard_manifest_current": bool(
            evidence.get("manifest_current", False)
        ),
        "scorecard_manifest_path": _text(evidence.get("manifest_path", "")),
        "scorecard_manifest_sha256": _text(
            evidence.get("manifest_sha256", "")
        ),
        "scorecard_manifest_error": _text(
            evidence.get("manifest_error", "")
        ),
        "scorecard_contract_consistent": bool(
            evidence.get("contract_consistent", False)
        ),
        "scorecard_contract_error": _text(
            evidence.get("contract_error", "")
        ),
        "scorecard_non_authorizing": bool(
            evidence.get("non_authorizing", False)
        ),
        "scorecard_provenance_gate_passed": bool(
            evidence.get("gate_passed", False)
        ),
        "research_family_bound": bool(
            evidence.get("research_family_bound", False)
        ),
        "research_family_provenance_current": bool(
            evidence.get("research_family_provenance_current", False)
        ),
        "research_family_provenance_error": _text(
            evidence.get("research_family_provenance_error", "")
        ),
    }
    for column, value in values.items():
        frame[column] = value
    frame["authorizes_submission"] = False
    return frame


def _scorecard_contract_errors(
    scorecard: pd.DataFrame,
    root: Path,
    manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    summary = _read_first_row(root / "strategy_scorecard_summary.csv")
    config = _read_json_object(root / "strategy_scorecard_next_actions.json")
    actions_value = config.get("next_actions", [])
    actions = actions_value if isinstance(actions_value, list) else []
    records = scorecard.to_dict(orient="records")
    if not summary:
        errors.append("summary_missing_or_empty")
    if not config:
        errors.append("next_actions_missing_or_invalid")
    if len(actions) != len(records):
        errors.append("scorecard_action_count_mismatch")
    else:
        for index, (row, action) in enumerate(zip(records, actions, strict=True)):
            if not isinstance(action, dict):
                errors.append(f"scorecard_action_not_object:{index}")
                continue
            for column in (
                "profile",
                "strategy",
                "market",
                "research_family_id",
                "research_family_registration_id",
                "research_family_manifest_sha256",
                "research_family_candidate_identity",
                "research_family_matched_study_label",
            ):
                if _text(row.get(column, "")) != _text(action.get(column, "")):
                    errors.append(f"scorecard_action_{column}_mismatch:{index}")
            for column in (
                "ready",
                "research_family_enabled",
                "research_family_required",
                "registered_research_detected",
                "research_family_provided",
                "research_family_gate_passed",
                "research_family_manifest_current",
                "research_family_valid",
                "research_family_candidate_match",
            ):
                if _bool(row.get(column, False)) != _bool(
                    action.get(column, False)
                ):
                    errors.append(f"scorecard_action_{column}_mismatch:{index}")
            if abs(
                _numeric(row.get("readiness_score", 0.0))
                - _numeric(action.get("readiness_score", 0.0))
            ) > 1e-12:
                errors.append(f"scorecard_action_readiness_score_mismatch:{index}")
            if abs(
                _numeric(
                    row.get(
                        "research_family_matched_holm_adjusted_pvalue",
                        0.0,
                    )
                )
                - _numeric(
                    action.get(
                        "research_family_matched_holm_adjusted_pvalue",
                        0.0,
                    )
                )
            ) > 1e-12:
                errors.append(
                    "scorecard_action_research_family_matched_"
                    f"holm_adjusted_pvalue_mismatch:{index}"
                )

    ready_count = int(scorecard["ready"].map(_bool).sum()) if not scorecard.empty else 0
    family_enabled = (
        scorecard["research_family_enabled"].map(_bool)
        if not scorecard.empty
        else pd.Series(dtype=bool)
    )
    family_passed = (
        scorecard["research_family_gate_passed"].map(_bool)
        if not scorecard.empty
        else pd.Series(dtype=bool)
    )
    registered = (
        scorecard["registered_research_detected"].map(_bool)
        if not scorecard.empty
        else pd.Series(dtype=bool)
    )
    expected_summary = {
        "profile_count": len(scorecard),
        "ready_profiles": ready_count,
        "blocked_profiles": len(scorecard) - ready_count,
        "registered_research_profiles": int(registered.sum()),
        "research_family_gate_passed_profiles": int(
            (family_enabled & family_passed).sum()
        ),
    }
    for column, expected in expected_summary.items():
        if _integer(summary.get(column, -1)) != int(expected):
            errors.append(f"summary_{column}_mismatch")
    if _integer(config.get("ready_action_count", -1)) != ready_count:
        errors.append("config_ready_action_count_mismatch")
    if _integer(config.get("blocked_action_count", -1)) != len(scorecard) - ready_count:
        errors.append("config_blocked_action_count_mismatch")
    expected_ready = ready_count > 0
    if _bool(summary.get("ready", False)) != expected_ready:
        errors.append("summary_ready_mismatch")
    if _bool(config.get("ready", False)) != expected_ready:
        errors.append("config_ready_mismatch")
    extra_value = manifest.get("extra", {})
    extra = extra_value if isinstance(extra_value, dict) else {}
    if _bool(extra.get("ready", False)) != expected_ready:
        errors.append("manifest_ready_mismatch")

    reference = _scorecard_family_reference(scorecard)
    for column in (
        "research_family_id",
        "research_family_registration_id",
        "research_family_path",
        "research_family_manifest_sha256",
    ):
        expected = _text(reference.get(column, ""))
        if _text(summary.get(column, "")) != expected:
            errors.append(f"summary_{column}_mismatch")
        if _text(config.get(column, "")) != expected:
            errors.append(f"config_{column}_mismatch")
    if _scorecard_family_bound(scorecard):
        for column in (
            "research_family_id",
            "research_family_manifest_sha256",
        ):
            if _text(extra.get(column, "")) != _text(
                reference.get(column, "")
            ):
                errors.append(f"manifest_{column}_mismatch")
        if not _bool(extra.get("research_family_provided", False)):
            errors.append("manifest_research_family_not_provided")
        if _integer(extra.get("registered_research_profiles", -1)) != int(
            registered.sum()
        ):
            errors.append("manifest_registered_research_profiles_mismatch")
        if _integer(
            extra.get("research_family_gate_passed_profiles", -1)
        ) != int((family_enabled & family_passed).sum()):
            errors.append(
                "manifest_research_family_gate_passed_profiles_mismatch"
            )
    if not _non_authorizing_contract(scorecard, summary, config, extra):
        errors.append("source_authorizes_submission")
    return sorted(set(errors))


def _research_family_provenance(
    scorecard: pd.DataFrame,
    scorecard_root: Path,
) -> dict[str, Any]:
    family_bound = _scorecard_family_bound(scorecard)
    reference = _scorecard_family_reference(scorecard)
    result = {
        "research_family_bound": family_bound,
        "research_family_provenance_current": not family_bound,
        "research_family_provenance_error": "",
        "research_family_id": _text(reference.get("research_family_id", "")),
        "research_family_registration_id": _text(
            reference.get("research_family_registration_id", "")
        ),
        "research_family_path": _text(
            reference.get("research_family_path", "")
        ),
        "research_family_manifest_sha256": _text(
            reference.get("research_family_manifest_sha256", "")
        ),
    }
    if not family_bound:
        return result
    errors = _scorecard_family_consistency_errors(scorecard)
    raw_family_path = _text(reference.get("research_family_path", ""))
    family_path = Path(raw_family_path) if raw_family_path else Path()
    if raw_family_path and not family_path.is_absolute():
        family_path = scorecard_root / family_path
    if not raw_family_path or not family_path.is_dir():
        errors.append("research_family_path_missing")
    else:
        family_path = family_path.resolve()
        result["research_family_path"] = str(family_path)
        manifest_path = family_path / "manifest.json"
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="research_family_audit",
            required_artifacts=RESEARCH_FAMILY_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        if not integrity.passed:
            errors.append(
                f"research_family_manifest_not_current:{integrity.error}"
            )
        if not manifest_path.is_file():
            errors.append("research_family_manifest_missing")
        else:
            actual_sha = file_sha256(manifest_path)
            if actual_sha != result["research_family_manifest_sha256"]:
                errors.append("research_family_manifest_sha256_mismatch")
            family_summary = _read_first_row(
                family_path / "research_family_summary.csv"
            )
            family_studies = _read_frame(
                family_path / "research_family_studies.csv"
            )
            family_config = _read_json_object(
                family_path / "research_family_config.json"
            )
            family_manifest = _read_json_object(manifest_path)
            family_extra_value = family_manifest.get("extra", {})
            family_extra = (
                family_extra_value
                if isinstance(family_extra_value, dict)
                else {}
            )
            if any(
                _bool(item.get("authorizes_submission", False))
                for item in (family_summary, family_config, family_extra)
            ):
                errors.append("research_family_authorizes_submission")
            errors.extend(
                _research_family_semantic_errors(
                    reference,
                    family_summary,
                    family_studies,
                    family_config,
                    family_extra,
                )
            )
    result["research_family_provenance_current"] = not errors
    result["research_family_provenance_error"] = ";".join(
        sorted(set(errors))
    )
    return result


def _research_family_semantic_errors(
    reference: dict[str, Any],
    summary: dict[str, Any],
    studies: pd.DataFrame,
    config: dict[str, Any],
    extra: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected_family_id = _text(reference.get("research_family_id", ""))
    expected_registration_id = _text(
        reference.get("research_family_registration_id", "")
    )
    config_parameters_value = config.get("parameters", {})
    config_parameters = (
        config_parameters_value
        if isinstance(config_parameters_value, dict)
        else {}
    )
    config_summary_value = config.get("summary", {})
    config_summary = (
        config_summary_value
        if isinstance(config_summary_value, dict)
        else {}
    )
    for source, value in (
        ("summary", summary.get("family_id", "")),
        ("config_parameters", config_parameters.get("family_id", "")),
        ("config_summary", config_summary.get("family_id", "")),
        ("manifest", extra.get("family_id", "")),
    ):
        if _text(value) != expected_family_id:
            errors.append(f"research_family_id_mismatch:{source}")
    for source, value in (
        ("summary", summary.get("registration_id", "")),
        ("config_summary", config_summary.get("registration_id", "")),
        ("manifest", extra.get("registration_id", "")),
    ):
        if _text(value) != expected_registration_id:
            errors.append(f"research_family_registration_id_mismatch:{source}")
    required_true = (
        ("summary_passed", summary.get("passed", False)),
        (
            "summary_prospective_registration_passed",
            summary.get("prospective_registration_passed", False),
        ),
        (
            "summary_registration_closed",
            summary.get("registration_closed", False),
        ),
        (
            "summary_family_wise_error_control_claimed",
            summary.get("family_wise_error_control_claimed", False),
        ),
        ("config_passed", config.get("passed", False)),
        (
            "config_registration_closed",
            config_summary.get("registration_closed", False),
        ),
        ("manifest_passed", extra.get("passed", False)),
        (
            "manifest_registration_closed",
            extra.get("registration_closed", False),
        ),
        (
            "manifest_prospective_registration_passed",
            extra.get("prospective_registration_passed", False),
        ),
        (
            "manifest_family_wise_error_control_claimed",
            extra.get("family_wise_error_control_claimed", False),
        ),
    )
    for check, value in required_true:
        if not _bool(value):
            errors.append(f"research_family_{check}_not_true")

    family_passed = (
        studies.get("family_passed", pd.Series(False, index=studies.index))
        .map(_bool)
        if not studies.empty
        else pd.Series(dtype=bool)
    )
    survivors = studies.loc[family_passed].copy() if not studies.empty else studies
    selected_value = config.get("selected_candidates", [])
    selected = selected_value if isinstance(selected_value, list) else []
    selected_records = [item for item in selected if isinstance(item, dict)]
    survivor_labels = sorted(
        survivors.get("study_label", pd.Series(dtype=str))
        .map(_text)
        .tolist()
    )
    selected_labels = sorted(
        _text(item.get("study_label", "")) for item in selected_records
    )
    if not survivor_labels or survivor_labels != selected_labels:
        errors.append("research_family_selected_candidate_ledger_mismatch")
    else:
        selected_by_label = {
            _text(item.get("study_label", "")): item
            for item in selected_records
        }
        for _, survivor in survivors.iterrows():
            label = _text(survivor.get("study_label", ""))
            selected_row = selected_by_label.get(label, {})
            if (
                _normalize_strategy(
                    _text(selected_row.get("strategy", ""))
                )
                != _normalize_strategy(_text(survivor.get("strategy", "")))
                or _normalize_identity(
                    _text(selected_row.get("market", ""))
                )
                != _normalize_identity(_text(survivor.get("market", "")))
                or _candidate_identity(
                    selected_row.get("candidate_scenario", "")
                )
                != _candidate_identity(survivor.get("candidate_scenario", ""))
                or not _bool(selected_row.get("family_passed", False))
            ):
                errors.append(
                    f"research_family_selected_candidate_mismatch:{label}"
                )
    if _integer(summary.get("family_candidate_count", -1)) != len(
        survivor_labels
    ):
        errors.append("research_family_candidate_count_mismatch")
    if (
        studies.get(
            "source_authorizes_submission",
            pd.Series(False, index=studies.index),
        )
        .map(_bool)
        .any()
        if not studies.empty
        else False
    ):
        errors.append("research_family_source_authorizes_submission")
    matched_label = _text(
        reference.get("research_family_matched_study_label", "")
    )
    matched_rows = (
        survivors.loc[
            survivors.get("study_label", pd.Series("", index=survivors.index))
            .map(_text)
            .eq(matched_label)
        ]
        if not survivors.empty
        else survivors
    )
    if len(matched_rows) != 1:
        errors.append("research_family_matched_survivor_not_unique")
    else:
        matched = matched_rows.iloc[0]
        if _normalize_strategy(_text(matched.get("strategy", ""))) != _normalize_strategy(
            _text(reference.get("strategy", ""))
        ):
            errors.append("research_family_matched_survivor_strategy_mismatch")
        if _normalize_identity(_text(matched.get("market", ""))) != _normalize_identity(
            _text(reference.get("market", ""))
        ):
            errors.append("research_family_matched_survivor_market_mismatch")
        if _candidate_identity(matched.get("candidate_scenario", "")) != _text(
            reference.get("research_family_candidate_identity", "")
        ):
            errors.append("research_family_matched_survivor_candidate_mismatch")
        if abs(
            _numeric(matched.get("holm_adjusted_pvalue", 0.0))
            - _numeric(
                reference.get(
                    "research_family_matched_holm_adjusted_pvalue",
                    0.0,
                )
            )
        ) > 1e-12:
            errors.append("research_family_matched_survivor_pvalue_mismatch")
    return errors


def _scorecard_family_bound(scorecard: pd.DataFrame) -> bool:
    if scorecard.empty:
        return False
    return any(
        bool(scorecard[column].map(_bool).any())
        for column in (
            "research_family_enabled",
            "research_family_required",
            "registered_research_detected",
        )
        if column in scorecard.columns
    )


def _scorecard_family_rows(scorecard: pd.DataFrame) -> pd.DataFrame:
    if scorecard.empty:
        return scorecard.iloc[0:0].copy()
    mask = pd.Series(False, index=scorecard.index)
    for column in (
        "research_family_enabled",
        "research_family_required",
        "registered_research_detected",
    ):
        if column in scorecard.columns:
            mask |= scorecard[column].map(_bool)
    return scorecard.loc[mask].copy()


def _scorecard_family_reference(scorecard: pd.DataFrame) -> dict[str, Any]:
    rows = _scorecard_family_rows(scorecard)
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _scorecard_family_consistency_errors(scorecard: pd.DataFrame) -> list[str]:
    rows = _scorecard_family_rows(scorecard)
    if rows.empty:
        return []
    errors: list[str] = []
    for column in (
        "research_family_id",
        "research_family_registration_id",
        "research_family_path",
        "research_family_manifest_sha256",
    ):
        normalized = [_text(value) for value in rows[column]]
        values = {value for value in normalized if value}
        if any(not value for value in normalized):
            errors.append(f"{column}_missing")
        if len(values) != 1:
            errors.append(f"{column}_not_unique")
    required_true = (
        "research_family_gate_passed",
        "research_family_manifest_current",
        "research_family_valid",
        "research_family_registration_closed",
        "research_family_error_control_claimed",
        "research_family_candidate_consistent",
        "research_family_candidate_match",
    )
    for column in required_true:
        if not bool(rows[column].map(_bool).all()):
            errors.append(f"{column}_not_true")
    if bool(rows["authorizes_submission"].map(_bool).any()):
        errors.append("scorecard_authorizes_submission")
    return errors


def _non_authorizing_contract(
    scorecard: pd.DataFrame,
    summary: dict[str, Any],
    config: dict[str, Any],
    extra: dict[str, Any],
) -> bool:
    scorecard_authorizes = bool(
        scorecard["authorizes_submission"].map(_bool).any()
    ) if not scorecard.empty else False
    return bool(
        not scorecard_authorizes
        and not _bool(summary.get("authorizes_submission", False))
        and not _bool(config.get("authorizes_submission", False))
        and not _bool(extra.get("authorizes_submission", False))
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_first_row(path: Path) -> dict[str, Any]:
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return {}
    return frame.iloc[0].to_dict() if not frame.empty else {}


def _read_frame(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _normalize_scorecard(scorecard: pd.DataFrame) -> pd.DataFrame:
    defaults: dict[str, Any] = {
        "rank": 0,
        "profile": "",
        "strategy": "",
        "market": "",
        "ready": False,
        "readiness_score": 0.0,
        "passed_required_run_types": 0,
        "required_run_type_count": 0,
        "next_required_run_type": "",
        "next_gate": "",
        "next_gate_help_command": "",
        "recommendation": "",
        "research_family_applicable": False,
        "research_family_enabled": False,
        "research_family_required": False,
        "registered_research_detected": False,
        "research_family_provided": False,
        "research_family_gate_passed": False,
        "research_family_reason": "",
        "research_family_manifest_current": False,
        "research_family_valid": False,
        "research_family_id": "",
        "research_family_registration_id": "",
        "research_family_path": "",
        "research_family_manifest_sha256": "",
        "research_family_registration_closed": False,
        "research_family_error_control_claimed": False,
        "research_family_candidate_identity": "",
        "research_family_candidate_identity_count": 0,
        "research_family_candidate_consistent": False,
        "research_family_candidate_match": False,
        "research_family_matched_study_label": "",
        "research_family_matched_holm_adjusted_pvalue": 0.0,
        "authorizes_submission": False,
    }
    frame = scorecard.copy()
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
    if frame.empty:
        return frame.loc[:, list(defaults)].copy()
    frame = frame.loc[:, list(defaults)].copy()
    frame["rank"] = frame["rank"].map(_integer)
    missing_rank = frame["rank"] <= 0
    if bool(missing_rank.any()):
        frame.loc[missing_rank, "rank"] = np.arange(1, int(missing_rank.sum()) + 1, dtype=int)
    frame["profile"] = frame["profile"].map(_text)
    frame["strategy"] = frame["strategy"].map(_text)
    frame["market"] = frame["market"].map(_text)
    frame["ready"] = frame["ready"].map(_bool)
    frame["readiness_score"] = frame["readiness_score"].map(_numeric)
    frame["passed_required_run_types"] = frame["passed_required_run_types"].map(_integer)
    frame["required_run_type_count"] = frame["required_run_type_count"].map(_integer)
    frame["next_required_run_type"] = frame["next_required_run_type"].map(_text)
    frame["next_gate"] = frame["next_gate"].map(_text)
    frame["next_gate_help_command"] = frame["next_gate_help_command"].map(_text)
    frame["recommendation"] = frame["recommendation"].map(_text)
    boolean_columns = (
        "research_family_applicable",
        "research_family_enabled",
        "research_family_required",
        "registered_research_detected",
        "research_family_provided",
        "research_family_gate_passed",
        "research_family_manifest_current",
        "research_family_valid",
        "research_family_registration_closed",
        "research_family_error_control_claimed",
        "research_family_candidate_consistent",
        "research_family_candidate_match",
        "authorizes_submission",
    )
    for column in boolean_columns:
        frame[column] = frame[column].map(_bool)
    text_columns = (
        "research_family_reason",
        "research_family_id",
        "research_family_registration_id",
        "research_family_path",
        "research_family_manifest_sha256",
        "research_family_candidate_identity",
        "research_family_matched_study_label",
    )
    for column in text_columns:
        frame[column] = frame[column].map(_text)
    frame["research_family_candidate_identity_count"] = frame[
        "research_family_candidate_identity_count"
    ].map(_integer)
    frame["research_family_matched_holm_adjusted_pvalue"] = frame[
        "research_family_matched_holm_adjusted_pvalue"
    ].map(_numeric)
    return frame.sort_values(["rank", "profile"]).reset_index(drop=True)


def _allocations(scorecard: pd.DataFrame, config: StrategyPortfolioConfig) -> pd.DataFrame:
    frame = scorecard.copy()
    include_profiles = {_profile_key(profile) for profile in config.include_profiles if _text(profile)}
    exclude_profiles = {_profile_key(profile) for profile in config.exclude_profiles if _text(profile)}
    frame["eligible"] = [
        _eligible(row, config, include_profiles=include_profiles, exclude_profiles=exclude_profiles)
        for _, row in frame.iterrows()
    ]
    frame["eligibility_reason"] = [
        _eligibility_reason(row, config, include_profiles=include_profiles, exclude_profiles=exclude_profiles)
        for _, row in frame.iterrows()
    ]
    frame["allocation_score"] = [
        _allocation_score(row) if bool(row.get("eligible", False)) else 0.0 for _, row in frame.iterrows()
    ]
    weights = _capped_weights(
        frame.loc[frame["eligible"].astype(bool), "allocation_score"],
        deployable_weight=_deployable_weight(config),
        max_profile_weight=_bounded_max_weight(config),
    )
    frame["allocation_weight"] = [float(weights.get(index, 0.0)) for index in frame.index]
    frame["allocation_notional"] = frame["allocation_weight"].map(lambda weight: weight * max(_numeric(config.total_capital), 0.0))
    frame["reserve_weight"] = _bounded_reserve_weight(config)
    frame["max_profile_weight"] = _bounded_max_weight(config)
    frame["capital_currency"] = _text(config.capital_currency)
    frame["deployment_mode"] = _text(config.deployment_mode)
    frame["allocation_mode"] = _text(config.allocation_mode)
    return frame[
        [
            "rank",
            "profile",
            "strategy",
            "market",
            "ready",
            "readiness_score",
            "passed_required_run_types",
            "required_run_type_count",
            "eligible",
            "eligibility_reason",
            "allocation_score",
            "allocation_weight",
            "allocation_notional",
            "reserve_weight",
            "max_profile_weight",
            "capital_currency",
            "deployment_mode",
            "allocation_mode",
            "next_required_run_type",
            "next_gate",
            "next_gate_help_command",
            "recommendation",
            "scorecard_manifest_required",
            "scorecard_manifest_provided",
            "scorecard_manifest_current",
            "scorecard_manifest_path",
            "scorecard_manifest_sha256",
            "scorecard_manifest_error",
            "scorecard_contract_consistent",
            "scorecard_contract_error",
            "scorecard_non_authorizing",
            "scorecard_provenance_gate_passed",
            "research_family_bound",
            "research_family_provenance_current",
            "research_family_provenance_error",
            "research_family_applicable",
            "research_family_enabled",
            "research_family_required",
            "registered_research_detected",
            "research_family_provided",
            "research_family_gate_passed",
            "research_family_reason",
            "research_family_manifest_current",
            "research_family_valid",
            "research_family_id",
            "research_family_registration_id",
            "research_family_path",
            "research_family_manifest_sha256",
            "research_family_registration_closed",
            "research_family_error_control_claimed",
            "research_family_candidate_identity",
            "research_family_candidate_identity_count",
            "research_family_candidate_consistent",
            "research_family_candidate_match",
            "research_family_matched_study_label",
            "research_family_matched_holm_adjusted_pvalue",
            "authorizes_submission",
        ]
    ]


def _checks(
    allocations: pd.DataFrame,
    config: StrategyPortfolioConfig,
    evidence: dict[str, Any],
) -> pd.DataFrame:
    eligible_count = int(allocations["eligible"].astype(bool).sum()) if not allocations.empty else 0
    allocated_weight = float(allocations["allocation_weight"].sum()) if not allocations.empty else 0.0
    allocated_profile_count = int((allocations["allocation_weight"] > 0.0).sum()) if not allocations.empty else 0
    concentration = _concentration(allocations)
    deployable_weight = _deployable_weight(config)
    rows = [
        _check(
            "total_capital_positive",
            _numeric(config.total_capital) > 0.0,
            _numeric(config.total_capital),
            ">",
            0.0,
            "total capital must be positive before creating a paper allocation",
        ),
        _check(
            "reserve_weight_between_0_and_1",
            0.0 <= _numeric(config.reserve_weight) <= 1.0,
            _numeric(config.reserve_weight),
            "between",
            "0..1",
            "reserve weight must be between 0 and 1",
        ),
        _check(
            "max_profile_weight_between_0_and_1",
            0.0 < _numeric(config.max_profile_weight) <= 1.0,
            _numeric(config.max_profile_weight),
            "between",
            "(0..1]",
            "max profile weight must be greater than 0 and no more than 1",
        ),
        _check(
            "min_readiness_score_between_0_and_1",
            0.0 <= _numeric(config.min_readiness_score) <= 1.0,
            _numeric(config.min_readiness_score),
            "between",
            "0..1",
            "minimum readiness score must be between 0 and 1",
        ),
        _check(
            "min_strategy_count_positive",
            _integer(config.min_strategy_count) >= 1,
            _integer(config.min_strategy_count),
            ">=",
            1,
            "minimum strategy count must be at least 1",
        ),
        _check(
            "min_market_count_positive",
            _integer(config.min_market_count) >= 1,
            _integer(config.min_market_count),
            ">=",
            1,
            "minimum market count must be at least 1",
        ),
        _check(
            "max_strategy_weight_between_0_and_1",
            _optional_weight(config.max_strategy_weight) is None
            or 0.0 < float(_optional_weight(config.max_strategy_weight)) <= 1.0,
            "" if _optional_weight(config.max_strategy_weight) is None else float(_optional_weight(config.max_strategy_weight)),
            "between",
            "(0..1]",
            "maximum aggregate strategy weight must be greater than 0 and no more than 1",
        ),
        _check(
            "max_market_weight_between_0_and_1",
            _optional_weight(config.max_market_weight) is None
            or 0.0 < float(_optional_weight(config.max_market_weight)) <= 1.0,
            "" if _optional_weight(config.max_market_weight) is None else float(_optional_weight(config.max_market_weight)),
            "between",
            "(0..1]",
            "maximum aggregate market weight must be greater than 0 and no more than 1",
        ),
        _check(
            "allocation_mode_supported",
            config.allocation_mode == "readiness_weighted",
            _text(config.allocation_mode),
            "is",
            "readiness_weighted",
            "only readiness-weighted paper allocation is supported",
        ),
        _check(
            "scorecard_manifest_provided",
            not bool(evidence.get("manifest_required", False))
            or bool(evidence.get("manifest_provided", False)),
            bool(evidence.get("manifest_provided", False)),
            "is",
            True if evidence.get("manifest_required", False) else "optional",
            "a current strategy scorecard manifest is required before allocating registered research",
        ),
        _check(
            "scorecard_manifest_current",
            (
                not bool(evidence.get("manifest_required", False))
                and not bool(evidence.get("manifest_provided", False))
            )
            or bool(evidence.get("manifest_current", False)),
            _text(evidence.get("manifest_error", ""))
            or bool(evidence.get("manifest_current", False)),
            "is",
            True,
            "the supplied strategy scorecard manifest is stale or invalid",
        ),
        _check(
            "scorecard_contract_consistent",
            (
                not bool(evidence.get("manifest_required", False))
                and not bool(evidence.get("manifest_provided", False))
            )
            or bool(evidence.get("contract_consistent", False)),
            _text(evidence.get("contract_error", ""))
            or bool(evidence.get("contract_consistent", False)),
            "is",
            True,
            "strategy scorecard CSV, summary, actions, and manifest claims disagree",
        ),
        _check(
            "scorecard_non_authorizing",
            bool(evidence.get("non_authorizing", False)),
            bool(evidence.get("non_authorizing", False)),
            "is",
            True,
            "strategy scorecard evidence must remain non-authorizing",
        ),
        _check(
            "research_family_provenance_current",
            not bool(evidence.get("research_family_bound", False))
            or bool(
                evidence.get("research_family_provenance_current", False)
            ),
            _text(evidence.get("research_family_provenance_error", ""))
            or bool(
                evidence.get("research_family_provenance_current", False)
            ),
            "is",
            True,
            "registered research family closure is missing, stale, mismatched, or authorizing",
        ),
        _check(
            "eligible_profile_count",
            eligible_count > 0,
            eligible_count,
            ">",
            0,
            "at least one strategy profile must pass readiness filters before allocation",
        ),
        _check(
            "allocated_weight_positive",
            allocated_weight > 0.0,
            allocated_weight,
            ">",
            0.0,
            "allocated weight must be positive after reserve and profile caps",
        ),
        _check(
            "allocated_weight_lte_deployable",
            allocated_weight <= deployable_weight + 1e-9,
            allocated_weight,
            "<=",
            deployable_weight,
            "allocated weight must not exceed the deployable budget",
        ),
        _check(
            "allocated_strategy_count",
            allocated_profile_count == 0
            or int(concentration["allocated_strategy_count"]) >= _integer(config.min_strategy_count),
            int(concentration["allocated_strategy_count"]),
            ">=",
            _integer(config.min_strategy_count),
            "allocated portfolio must include enough distinct strategies",
        ),
        _check(
            "allocated_market_count",
            allocated_profile_count == 0
            or int(concentration["allocated_market_count"]) >= _integer(config.min_market_count),
            int(concentration["allocated_market_count"]),
            ">=",
            _integer(config.min_market_count),
            "allocated portfolio must include enough distinct markets",
        ),
        _check(
            "max_strategy_allocation_weight",
            _optional_weight(config.max_strategy_weight) is None
            or allocated_profile_count == 0
            or float(concentration["max_strategy_allocation_weight"]) <= float(_optional_weight(config.max_strategy_weight)) + 1e-9,
            float(concentration["max_strategy_allocation_weight"]),
            "<=",
            "" if _optional_weight(config.max_strategy_weight) is None else float(_optional_weight(config.max_strategy_weight)),
            "aggregate allocation to one strategy exceeds the configured cap",
        ),
        _check(
            "max_market_allocation_weight",
            _optional_weight(config.max_market_weight) is None
            or allocated_profile_count == 0
            or float(concentration["max_market_allocation_weight"]) <= float(_optional_weight(config.max_market_weight)) + 1e-9,
            float(concentration["max_market_allocation_weight"]),
            "<=",
            "" if _optional_weight(config.max_market_weight) is None else float(_optional_weight(config.max_market_weight)),
            "aggregate allocation to one market exceeds the configured cap",
        ),
    ]
    return pd.DataFrame(rows)


def _summary(
    allocations: pd.DataFrame,
    checks: pd.DataFrame,
    config: StrategyPortfolioConfig,
    evidence: dict[str, Any],
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    primary = failed.iloc[0].to_dict() if not failed.empty else {}
    allocated = allocations.loc[allocations["allocation_weight"] > 0.0] if not allocations.empty else pd.DataFrame()
    top = _top_allocation(allocated)
    total_capital = max(_numeric(config.total_capital), 0.0)
    allocated_weight = float(allocations["allocation_weight"].sum()) if not allocations.empty else 0.0
    reserve_weight = _bounded_reserve_weight(config)
    unallocated_weight = max(0.0, 1.0 - reserve_weight - allocated_weight)
    concentration = _concentration(allocations)
    ready = failed.empty
    return pd.DataFrame(
        [
            {
                "ready": bool(ready),
                "deployment_mode": _text(config.deployment_mode),
                "allocation_mode": _text(config.allocation_mode),
                "capital_currency": _text(config.capital_currency),
                "total_capital": float(total_capital),
                "reserve_weight": float(reserve_weight),
                "reserve_notional": float(total_capital * reserve_weight),
                "deployable_weight": float(_deployable_weight(config)),
                "profile_count": int(len(allocations)),
                "eligible_profile_count": int(allocations["eligible"].astype(bool).sum()) if not allocations.empty else 0,
                "allocated_profile_count": int(len(allocated)),
                "allocated_weight": float(allocated_weight),
                "allocated_notional": float(total_capital * allocated_weight),
                "unallocated_weight": float(unallocated_weight),
                "unallocated_notional": float(total_capital * unallocated_weight),
                "max_profile_weight": float(_bounded_max_weight(config)),
                "min_strategy_count": int(_integer(config.min_strategy_count)),
                "min_market_count": int(_integer(config.min_market_count)),
                "max_strategy_weight": ""
                if _optional_weight(config.max_strategy_weight) is None
                else float(_optional_weight(config.max_strategy_weight)),
                "max_market_weight": ""
                if _optional_weight(config.max_market_weight) is None
                else float(_optional_weight(config.max_market_weight)),
                "allocated_strategy_count": int(concentration["allocated_strategy_count"]),
                "allocated_market_count": int(concentration["allocated_market_count"]),
                "top_strategy_by_weight": _text(concentration["top_strategy_by_weight"]),
                "top_market_by_weight": _text(concentration["top_market_by_weight"]),
                "max_strategy_allocation_weight": float(concentration["max_strategy_allocation_weight"]),
                "max_market_allocation_weight": float(concentration["max_market_allocation_weight"]),
                "top_profile": _text(top.get("profile", "")),
                "top_strategy": _text(top.get("strategy", "")),
                "top_market": _text(top.get("market", "")),
                "top_allocation_weight": float(_numeric(top.get("allocation_weight", 0.0))),
                "top_allocation_notional": float(_numeric(top.get("allocation_notional", 0.0))),
                "scorecard_manifest_required": bool(
                    evidence.get("manifest_required", False)
                ),
                "scorecard_manifest_provided": bool(
                    evidence.get("manifest_provided", False)
                ),
                "scorecard_manifest_current": bool(
                    evidence.get("manifest_current", False)
                ),
                "scorecard_manifest_sha256": _text(
                    evidence.get("manifest_sha256", "")
                ),
                "scorecard_contract_consistent": bool(
                    evidence.get("contract_consistent", False)
                ),
                "scorecard_non_authorizing": bool(
                    evidence.get("non_authorizing", False)
                ),
                "scorecard_provenance_gate_passed": bool(
                    evidence.get("gate_passed", False)
                ),
                "research_family_bound": bool(
                    evidence.get("research_family_bound", False)
                ),
                "research_family_provenance_current": bool(
                    evidence.get(
                        "research_family_provenance_current",
                        False,
                    )
                ),
                "research_family_id": _text(
                    evidence.get("research_family_id", "")
                ),
                "research_family_registration_id": _text(
                    evidence.get("research_family_registration_id", "")
                ),
                "research_family_path": _text(
                    evidence.get("research_family_path", "")
                ),
                "research_family_manifest_sha256": _text(
                    evidence.get("research_family_manifest_sha256", "")
                ),
                "authorizes_submission": False,
                "failed_check_count": int(len(failed)),
                "failed_check_names": ";".join(failed["check"].astype(str).tolist()) if not failed.empty else "",
                "first_failed_reason": _text(primary.get("reason", "")),
                "primary_blocker_check": _text(primary.get("check", "")),
                "primary_blocker_value": primary.get("value", ""),
                "primary_blocker_operator": _text(primary.get("operator", "")),
                "primary_blocker_threshold": primary.get("threshold", ""),
                "primary_blocker_reason": _text(primary.get("reason", "")),
                "recommendation": _recommendation(primary),
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["next_gate"] = _first_action_value(action_queue, "next_gate")
    out["next_gate_help_command"] = _first_action_value(action_queue, "next_gate_help_command")
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _config(
    allocations: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    config: StrategyPortfolioConfig,
    action_queue: pd.DataFrame,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    summary_row = _jsonable_row(summary.iloc[0].to_dict()) if not summary.empty else {}
    failed_checks = [row for row in _records(checks) if not bool(row.get("passed", False))]
    allocation_records = _records(allocations)
    ready_allocations = [row for row in allocation_records if _numeric(row.get("allocation_weight", 0.0)) > 0.0]
    blocked_allocations = [row for row in allocation_records if not bool(row.get("eligible", False))]
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    primary = failed_checks[0] if failed_checks else {}
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "deployment_mode": _text(config.deployment_mode),
        "allocation_mode": _text(config.allocation_mode),
        "allocation_config": _jsonable(asdict(config)),
        "scorecard_provenance": _jsonable(evidence),
        "scorecard_manifest_required": bool(
            evidence.get("manifest_required", False)
        ),
        "scorecard_manifest_current": bool(
            evidence.get("manifest_current", False)
        ),
        "scorecard_manifest_sha256": _text(
            evidence.get("manifest_sha256", "")
        ),
        "research_family_bound": bool(
            evidence.get("research_family_bound", False)
        ),
        "research_family_provenance_current": bool(
            evidence.get("research_family_provenance_current", False)
        ),
        "research_family_id": _text(
            evidence.get("research_family_id", "")
        ),
        "research_family_registration_id": _text(
            evidence.get("research_family_registration_id", "")
        ),
        "research_family_path": _text(
            evidence.get("research_family_path", "")
        ),
        "research_family_manifest_sha256": _text(
            evidence.get("research_family_manifest_sha256", "")
        ),
        "authorizes_submission": False,
        "summary": summary_row,
        "allocation_count": len(ready_allocations),
        "blocked_profile_count": len(blocked_allocations),
        "failed_check_count": len(failed_checks),
        "failed_checks": [str(row.get("check", "")) for row in failed_checks],
        "first_failed_reason": _text(primary.get("reason", "")),
        "primary_blocker": _primary_blocker(primary),
        "action_queue_count": int(len(action_queue)),
        "ready_action_count": int(len(ready_actions)),
        "blocked_action_count": int(len(blocked_actions)),
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _first_action_value(action_queue, "queue_status"),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(ready_actions),
        "blocked_actions": _action_records(blocked_actions),
        "allocations": allocation_records,
        "ready_allocations": ready_allocations,
        "blocked_allocations": blocked_allocations,
        "checks": _records(checks),
    }


def _eligible(
    row: pd.Series,
    config: StrategyPortfolioConfig,
    *,
    include_profiles: set[str],
    exclude_profiles: set[str],
) -> bool:
    return _eligibility_reason(
        row,
        config,
        include_profiles=include_profiles,
        exclude_profiles=exclude_profiles,
    ) == "eligible_for_paper_shadow_allocation"


def _eligibility_reason(
    row: pd.Series,
    config: StrategyPortfolioConfig,
    *,
    include_profiles: set[str],
    exclude_profiles: set[str],
) -> str:
    profile = _profile_key(row.get("profile", ""))
    if include_profiles and profile not in include_profiles:
        return "profile_not_in_include_filter"
    if profile in exclude_profiles:
        return "profile_excluded"
    if not _bool(row.get("scorecard_provenance_gate_passed", False)):
        return "scorecard_provenance_not_current"
    if _bool(row.get("research_family_enabled", False)) and not _bool(
        row.get("research_family_gate_passed", False)
    ):
        return "research_family_gate_not_passed"
    if config.require_ready and not _bool(row.get("ready", False)):
        return "profile_not_ready"
    if _numeric(row.get("readiness_score", 0.0)) < _numeric(config.min_readiness_score):
        return "readiness_score_below_threshold"
    return "eligible_for_paper_shadow_allocation"


def _allocation_score(row: pd.Series) -> float:
    score = max(_numeric(row.get("readiness_score", 0.0)), 0.0)
    if score > 0.0:
        return score
    return max(float(_integer(row.get("passed_required_run_types", 0))), 1.0)


def _capped_weights(scores: pd.Series, *, deployable_weight: float, max_profile_weight: float) -> dict[int, float]:
    if scores.empty or deployable_weight <= 0.0 or max_profile_weight <= 0.0:
        return {}
    weights = {int(index): 0.0 for index in scores.index}
    active = [int(index) for index in scores.index]
    remaining = float(deployable_weight)
    clean_scores = scores.map(_numeric)
    while active and remaining > 1e-12:
        active_scores = clean_scores.loc[active]
        score_sum = float(active_scores.sum())
        if score_sum <= 0.0:
            active_scores = pd.Series(1.0, index=active)
            score_sum = float(len(active))
        capped: list[tuple[int, float]] = []
        proposed: dict[int, float] = {}
        for index in active:
            share = remaining * float(active_scores.loc[index]) / score_sum
            cap_left = max(0.0, max_profile_weight - weights[index])
            if share >= cap_left - 1e-12:
                capped.append((index, cap_left))
            else:
                proposed[index] = share
        if not capped:
            for index, share in proposed.items():
                weights[index] += share
            remaining = 0.0
            break
        for index, share in capped:
            weights[index] += share
            remaining -= share
            active.remove(index)
    return weights


def _concentration(allocations: pd.DataFrame) -> dict[str, Any]:
    if allocations.empty or "allocation_weight" not in allocations.columns:
        return {
            "allocated_strategy_count": 0,
            "allocated_market_count": 0,
            "top_strategy_by_weight": "",
            "top_market_by_weight": "",
            "max_strategy_allocation_weight": 0.0,
            "max_market_allocation_weight": 0.0,
        }
    allocated = allocations.loc[allocations["allocation_weight"].map(_numeric) > 0.0].copy()
    if allocated.empty:
        return {
            "allocated_strategy_count": 0,
            "allocated_market_count": 0,
            "top_strategy_by_weight": "",
            "top_market_by_weight": "",
            "max_strategy_allocation_weight": 0.0,
            "max_market_allocation_weight": 0.0,
        }
    allocated["strategy"] = allocated["strategy"].map(_text).replace("", "unknown_strategy")
    allocated["market"] = allocated["market"].map(_text).replace("", "unknown_market")
    strategy_weights = allocated.groupby("strategy", sort=True)["allocation_weight"].sum().sort_values(
        ascending=False,
        kind="mergesort",
    )
    market_weights = allocated.groupby("market", sort=True)["allocation_weight"].sum().sort_values(
        ascending=False,
        kind="mergesort",
    )
    return {
        "allocated_strategy_count": int(len(strategy_weights)),
        "allocated_market_count": int(len(market_weights)),
        "top_strategy_by_weight": _text(strategy_weights.index[0]) if len(strategy_weights) else "",
        "top_market_by_weight": _text(market_weights.index[0]) if len(market_weights) else "",
        "max_strategy_allocation_weight": float(strategy_weights.iloc[0]) if len(strategy_weights) else 0.0,
        "max_market_allocation_weight": float(market_weights.iloc[0]) if len(market_weights) else 0.0,
    }


def _optional_weight(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _numeric(value)


def _check(check: str, passed: bool, value: Any, operator: str, threshold: Any, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "passed": bool(passed),
        "value": _jsonable(value),
        "operator": operator,
        "threshold": _jsonable(threshold),
        "reason": "" if passed else reason,
    }


def _action_queue(allocations: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in allocations.iterrows():
        if _numeric(row.get("allocation_weight", 0.0)) > 0.0:
            rows.append(_allocation_action(row, queue_status="ready"))
        elif not _bool(row.get("eligible", False)):
            rows.append(_allocation_action(row, queue_status="blocked"))
    if not checks.empty and "passed" in checks.columns:
        failed = checks.loc[~checks["passed"].astype(bool)]
        for _, row in failed.iterrows():
            rows.append(_check_action(row))
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _allocation_action(row: pd.Series, *, queue_status: str) -> dict[str, Any]:
    next_gate = _allocation_next_gate(row, queue_status)
    return {
        "queue_status": queue_status,
        "source": "strategy_portfolio_allocations",
        "component": "strategy_portfolio",
        "check": _allocation_check(row, queue_status),
        "actual": bool(row.get("eligible", False)) if queue_status == "blocked" else row.get("allocation_weight", 0.0),
        "operator": "is" if queue_status == "blocked" else ">",
        "expected": True if queue_status == "blocked" else 0.0,
        "profile": _text(row.get("profile")),
        "strategy": _text(row.get("strategy")),
        "market": _text(row.get("market")),
        "readiness_score": float(_numeric(row.get("readiness_score", 0.0))),
        "allocation_weight": float(_numeric(row.get("allocation_weight", 0.0))),
        "allocation_notional": float(_numeric(row.get("allocation_notional", 0.0))),
        "eligibility_reason": _text(row.get("eligibility_reason")),
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(row, next_gate),
        "reason": _allocation_reason(row, queue_status),
        "recommendation": _allocation_recommendation(row, queue_status),
    }


def _check_action(row: pd.Series) -> dict[str, Any]:
    check = _text(row.get("check"))
    next_gate = _check_next_gate(check)
    return {
        "queue_status": "blocked",
        "source": "strategy_portfolio_checks",
        "component": "strategy_portfolio",
        "check": check,
        "actual": row.get("value", ""),
        "operator": _text(row.get("operator")),
        "expected": row.get("threshold", ""),
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(row, next_gate),
        "reason": _text(row.get("reason")),
        "recommendation": _check_recommendation(check),
    }


def _allocation_check(row: pd.Series, queue_status: str) -> str:
    profile = _text(row.get("profile"))
    prefix = "profile_allocated" if queue_status == "ready" else "profile_eligible"
    return f"{prefix}:{profile}" if profile else prefix


def _allocation_next_gate(row: pd.Series, queue_status: str) -> str:
    reason = _text(row.get("eligibility_reason"))
    if reason == "scorecard_provenance_not_current":
        return "score-strategy-readiness"
    if reason == "research_family_gate_not_passed":
        return "audit-research-family"
    next_gate = _text(row.get("next_gate"))
    if next_gate:
        return next_gate
    return "plan-scaleup" if queue_status == "ready" else "score-strategy-readiness"


def _check_next_gate(check: str) -> str:
    if check == "research_family_provenance_current":
        return "audit-research-family"
    if check in {
        "scorecard_manifest_provided",
        "scorecard_manifest_current",
        "scorecard_contract_consistent",
        "scorecard_non_authorizing",
    }:
        return "score-strategy-readiness"
    if check == "eligible_profile_count":
        return "score-strategy-readiness"
    if check in {"allocated_strategy_count", "allocated_market_count"}:
        return "score-strategy-readiness"
    if check == "allocated_weight_positive":
        return "allocate-strategy-portfolio"
    return "allocate-strategy-portfolio"


def _help_command(row: pd.Series, next_gate: str) -> str:
    explicit = _text(row.get("next_gate_help_command"))
    if explicit:
        return explicit
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _allocation_reason(row: pd.Series, queue_status: str) -> str:
    if queue_status == "ready":
        return "strategy profile has a positive paper/shadow allocation"
    reason = _text(row.get("eligibility_reason"))
    if reason:
        return reason
    return "strategy profile is not eligible for allocation"


def _allocation_recommendation(row: pd.Series, queue_status: str) -> str:
    if queue_status == "ready":
        return "review_scaleup_for_allocated_strategy_profile"
    reason = _text(row.get("eligibility_reason"))
    if reason == "scorecard_provenance_not_current":
        return "regenerate_and_verify_strategy_scorecard_before_allocating"
    if reason == "research_family_gate_not_passed":
        return "close_registered_research_family_before_allocating"
    if reason == "profile_not_ready":
        return "complete_strategy_scorecard_evidence_before_allocating"
    if reason == "readiness_score_below_threshold":
        return "improve_strategy_readiness_score_before_allocating"
    if reason == "profile_not_in_include_filter":
        return "review_strategy_portfolio_include_filter"
    if reason == "profile_excluded":
        return "review_strategy_portfolio_exclusion_filter"
    return "review_strategy_portfolio_profile_eligibility"


def _check_recommendation(check: str) -> str:
    if check == "research_family_provenance_current":
        return "close_and_verify_registered_research_family_before_allocating"
    if check in {
        "scorecard_manifest_provided",
        "scorecard_manifest_current",
        "scorecard_contract_consistent",
        "scorecard_non_authorizing",
    }:
        return "regenerate_and_verify_strategy_scorecard_before_allocating"
    if check == "eligible_profile_count":
        return "complete_strategy_scorecard_evidence_before_allocating"
    if check == "allocated_strategy_count":
        return "add_distinct_strategy_profiles_before_allocating"
    if check == "allocated_market_count":
        return "add_distinct_market_profiles_before_allocating"
    if check == "max_strategy_allocation_weight":
        return "lower_strategy_concentration_or_add_diversifying_profiles"
    if check == "max_market_allocation_weight":
        return "lower_market_concentration_or_add_cross_market_profiles"
    if check == "allocated_weight_positive":
        return "increase_deployable_budget_or_profile_cap"
    if check in {
        "total_capital_positive",
        "reserve_weight_between_0_and_1",
        "max_profile_weight_between_0_and_1",
        "min_readiness_score_between_0_and_1",
        "min_strategy_count_positive",
        "min_market_count_positive",
        "max_strategy_weight_between_0_and_1",
        "max_market_weight_between_0_and_1",
        "allocation_mode_supported",
    }:
        return "fix_strategy_portfolio_allocation_inputs"
    return "review_strategy_portfolio_allocation_checks"


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, Any]:
    if action_queue.empty:
        return {}
    return _jsonable_row(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, Any]]:
    if action_queue.empty:
        return []
    return [_jsonable_row(row) for row in action_queue.to_dict(orient="records")]


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _text(action_queue.iloc[0].get(column))


def _top_allocation(allocated: pd.DataFrame) -> dict[str, Any]:
    if allocated.empty:
        return {}
    ordered = allocated.sort_values(["allocation_weight", "readiness_score", "rank"], ascending=[False, False, True])
    return ordered.iloc[0].to_dict()


def _recommendation(primary: dict[str, Any]) -> str:
    if not primary:
        return "paper_shadow_allocation_ready"
    check = _text(primary.get("check", ""))
    if check == "research_family_provenance_current":
        return "close_and_verify_registered_research_family_before_allocating"
    if check in {
        "scorecard_manifest_provided",
        "scorecard_manifest_current",
        "scorecard_contract_consistent",
        "scorecard_non_authorizing",
    }:
        return "regenerate_and_verify_strategy_scorecard_before_allocating"
    if check in {
        "total_capital_positive",
        "reserve_weight_between_0_and_1",
        "max_profile_weight_between_0_and_1",
        "min_readiness_score_between_0_and_1",
        "min_strategy_count_positive",
        "min_market_count_positive",
        "max_strategy_weight_between_0_and_1",
        "max_market_weight_between_0_and_1",
        "allocation_mode_supported",
    }:
        return "fix_strategy_portfolio_allocation_inputs"
    if check == "eligible_profile_count":
        return "complete_strategy_scorecard_evidence_before_allocating"
    if check in {"allocated_strategy_count", "allocated_market_count"}:
        return "add_diversifying_strategy_profiles_before_allocating"
    if check in {"max_strategy_allocation_weight", "max_market_allocation_weight"}:
        return "reduce_portfolio_concentration_before_scaleup"
    if check == "allocated_weight_positive":
        return "increase_deployable_budget_or_profile_cap"
    return "review_strategy_portfolio_allocation_checks"


def _primary_blocker(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "check": _text(row.get("check", "")),
        "passed": False,
        "value": row.get("value", ""),
        "operator": _text(row.get("operator", "")),
        "threshold": row.get("threshold", ""),
        "reason": _text(row.get("reason", "")),
    }


def _runbook_markdown(config: dict[str, Any]) -> str:
    ready_label = "yes" if bool(config.get("ready", False)) else "no"
    summary = config.get("summary", {}) if isinstance(config.get("summary"), dict) else {}
    lines = [
        "# Strategy Portfolio Allocation Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Deployment mode: {_code(config.get('deployment_mode'))}",
        f"- Allocation mode: {_code(config.get('allocation_mode'))}",
        f"- Total capital: {_format_money(summary.get('total_capital'), summary.get('capital_currency'))}",
        f"- Allocated: {_format_weight(summary.get('allocated_weight'))} / {_format_money(summary.get('allocated_notional'), summary.get('capital_currency'))}",
        f"- Reserve: {_format_weight(summary.get('reserve_weight'))} / {_format_money(summary.get('reserve_notional'), summary.get('capital_currency'))}",
        f"- Allocated strategies: {_integer(summary.get('allocated_strategy_count'))} (top {_code(summary.get('top_strategy_by_weight'))}: {_format_weight(summary.get('max_strategy_allocation_weight'))})",
        f"- Allocated markets: {_integer(summary.get('allocated_market_count'))} (top {_code(summary.get('top_market_by_weight'))}: {_format_weight(summary.get('max_market_allocation_weight'))})",
        f"- Recommendation: {_text(summary.get('recommendation'))}",
        "",
        "## Scorecard Provenance",
        "",
        f"- Manifest required: {'yes' if bool(config.get('scorecard_manifest_required', False)) else 'no'}",
        f"- Manifest current: {'yes' if bool(config.get('scorecard_manifest_current', False)) else 'no'}",
        f"- Manifest SHA-256: {_code(config.get('scorecard_manifest_sha256'))}",
        f"- Research family bound: {'yes' if bool(config.get('research_family_bound', False)) else 'no'}",
        f"- Research family current: {'yes' if bool(config.get('research_family_provenance_current', False)) else 'no'}",
        f"- Research family: {_code(config.get('research_family_id'))}",
        f"- Registration: {_code(config.get('research_family_registration_id'))}",
        "- Submission authorization: no",
        "",
        "## Allocations",
        "",
        _allocations_table(config.get("ready_allocations", [])),
        "",
        "## Blocked Profiles",
        "",
        _blocked_table(config.get("blocked_allocations", [])),
        "",
        "## Scheduler Actions",
        "",
        _action_queue_table(config.get("next_actions", [])),
        "",
        "## Failed Checks",
        "",
        _checks_table([row for row in config.get("checks", []) if isinstance(row, dict) and not bool(row.get("passed", False))]),
        "",
    ]
    return "\n".join(lines)


def _allocations_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Profile", "Strategy", "Market", "Weight", "Notional", "Score", "Next gate"],
        [
            [
                _text(row.get("profile")),
                _text(row.get("strategy")),
                _text(row.get("market")),
                _format_weight(row.get("allocation_weight")),
                _format_money(row.get("allocation_notional"), row.get("capital_currency")),
                f"{_numeric(row.get('readiness_score')):.3f}",
                _code(row.get("next_gate")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _blocked_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Profile", "Ready", "Score", "Reason", "Next gate"],
        [
            [
                _text(row.get("profile")),
                "yes" if bool(row.get("ready", False)) else "no",
                f"{_numeric(row.get('readiness_score')):.3f}",
                _text(row.get("eligibility_reason")),
                _code(row.get("next_gate")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _checks_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Check", "Value", "Operator", "Threshold", "Reason"],
        [
            [
                _text(row.get("check")),
                _text(row.get("value")),
                _text(row.get("operator")),
                _text(row.get("threshold")),
                _text(row.get("reason")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _action_queue_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Priority", "Status", "Check", "Profile", "Next gate", "Help", "Reason"],
        [
            [
                str(_integer(row.get("priority", 0))),
                _text(row.get("queue_status")),
                _text(row.get("check")),
                _text(row.get("profile")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _text(row.get("reason")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _scorecard_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "strategy_scorecard.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"strategy scorecard not found: {candidate}")
    return candidate


def _deployable_weight(config: StrategyPortfolioConfig) -> float:
    return max(0.0, 1.0 - _bounded_reserve_weight(config))


def _bounded_reserve_weight(config: StrategyPortfolioConfig) -> float:
    return min(max(_numeric(config.reserve_weight), 0.0), 1.0)


def _bounded_max_weight(config: StrategyPortfolioConfig) -> float:
    return min(max(_numeric(config.max_profile_weight), 0.0), 1.0)


def _profile_key(value: Any) -> str:
    return _text(value).strip().lower()


def _candidate_identity(value: Any) -> str:
    raw = _text(value).strip()
    if not raw:
        return ""
    parsed: dict[str, str] = {}
    for part in raw.split("|"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        normalized_key = _normalize_identity(key)
        normalized_value = item.strip().casefold()
        if (
            normalized_key
            and normalized_value
            and normalized_key not in {"strategy", "market", "profile"}
        ):
            parsed[normalized_key] = normalized_value
    if parsed:
        return "|".join(
            f"{key}={parsed[key]}" for key in sorted(parsed)
        )
    return raw.casefold()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_row(row) for row in frame.to_dict(orient="records")]


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _integer(value: Any) -> int:
    return int(round(_numeric(value)))


def _numeric(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
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


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _format_weight(value: Any) -> str:
    return f"{_numeric(value):.3f}"


def _format_money(value: Any, currency: Any) -> str:
    return f"{_text(currency) or 'INR'} {_numeric(value):,.2f}"


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
