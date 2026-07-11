from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.research_family_registration import (
    load_research_family_registration,
)
from reports.research_family_launch import (
    ResearchFamilyLaunchSnapshot,
    load_research_family_launch_matrix,
)


RUN_TYPE = "research_family_audit"
READY_NEXT_GATE = "score-strategy-readiness"
REPAIR_NEXT_GATE = "audit-research-family"

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]


@dataclass(frozen=True)
class ResearchFamilyConfig:
    family_id: str
    declaration_complete_attested: bool = False
    require_study_manifests: bool = True
    require_source_ready: bool = True
    require_holdout_passed: bool = True
    require_prospective_registration: bool = False
    require_launch_coverage: bool = False


@dataclass(frozen=True)
class ResearchFamilyThresholds:
    min_studies: int = 2
    max_holm_adjusted_pvalue: float = 0.1
    min_family_candidates: int = 1


@dataclass(frozen=True)
class ResearchFamilyReport:
    studies: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False

    @property
    def ready(self) -> bool:
        return self.passed


def evaluate_research_family(
    studies: pd.DataFrame,
    *,
    config: ResearchFamilyConfig,
    thresholds: ResearchFamilyThresholds | None = None,
    registration: dict[str, Any] | None = None,
    launch_coverage: dict[str, Any] | None = None,
) -> ResearchFamilyReport:
    thresholds = thresholds or ResearchFamilyThresholds()
    _validate(config, thresholds)
    _require_columns(
        studies,
        (
            "study_label",
            "study_path",
            "manifest_current",
            "source_ready",
            "holdout_passed",
            "candidate_scenario",
            "within_study_adjusted_pvalue",
            "source_authorizes_submission",
            "study_disposition",
        ),
    )
    frame = _holm_adjust(
        studies.copy(),
        thresholds.max_holm_adjusted_pvalue,
        config=config,
    )
    study_count = int(len(frame))
    unique_path_count = (
        int(frame["study_path"].astype(str).str.casefold().nunique())
        if not frame.empty
        else 0
    )
    unique_label_count = (
        int(frame["study_label"].astype(str).nunique()) if not frame.empty else 0
    )
    manifest_current_count = _bool_count(frame, "manifest_current")
    candidate_count = int(
        frame.get("candidate_scenario", pd.Series(dtype=str))
        .astype(str)
        .str.strip()
        .ne("")
        .sum()
    )
    abandoned_count = int(
        frame["study_disposition"].astype(str).eq("abandoned").sum()
    )
    never_launched_count = int(
        frame["study_disposition"].astype(str).eq("never_launched").sum()
    )
    required_candidate_count = study_count - abandoned_count
    adjusted_pvalues = _numeric(frame, "within_study_adjusted_pvalue")
    valid_pvalue_count = int(
        (np.isfinite(adjusted_pvalues) & adjusted_pvalues.between(0.0, 1.0)).sum()
    )
    family_candidate_count = _bool_count(frame, "family_passed")
    non_authorizing_count = int(
        (~frame.get("source_authorizes_submission", pd.Series(False, index=frame.index))
         .map(_to_bool)).sum()
    )
    registration = registration or {}
    launch_coverage = launch_coverage or {}
    checks = pd.DataFrame(
        [
            *_registration_checks(registration, config),
            *_launch_coverage_checks(launch_coverage, config, registration),
            {
                "check": "family_declaration_attested",
                "actual": bool(config.declaration_complete_attested),
                "operator": "is",
                "expected": True,
                "passed": bool(config.declaration_complete_attested),
                "reason": (
                    ""
                    if config.declaration_complete_attested
                    else "operator must attest that every attempted study is declared"
                ),
            },
            _numeric_check(
                "study_count",
                study_count,
                ">=",
                thresholds.min_studies,
                "not enough declared studies for family-wise correction",
            ),
            _numeric_check(
                "unique_study_paths",
                unique_path_count,
                "==",
                study_count,
                "the same study root was declared more than once",
            ),
            _numeric_check(
                "unique_study_labels",
                unique_label_count,
                "==",
                study_count,
                "study labels must be unique",
            ),
            _numeric_check(
                "current_study_manifests",
                manifest_current_count,
                "==",
                study_count,
                "one or more robust-study artifacts or inputs drifted",
                allow_failure=not config.require_study_manifests,
            ),
            _numeric_check(
                "candidate_scenarios",
                candidate_count,
                "==",
                required_candidate_count,
                "one or more non-abandoned studies lack a frozen candidate identity",
            ),
            _numeric_check(
                "valid_adjusted_pvalues",
                valid_pvalue_count,
                "==",
                study_count,
                "one or more studies lack a valid adjusted p-value in [0, 1]",
            ),
            _numeric_check(
                "non_authorizing_sources",
                non_authorizing_count,
                "==",
                study_count,
                "a source study unexpectedly claims broker-submission authority",
            ),
            _numeric_check(
                "family_candidates",
                family_candidate_count,
                ">=",
                thresholds.min_family_candidates,
                "no source-ready candidate survives family-wise correction",
            ),
        ]
    )
    passed = bool(not checks.empty and checks["passed"].astype(bool).all())
    failed_checks = int((~checks["passed"].astype(bool)).sum())
    action_queue = _action_queue(checks)
    selected = frame.loc[frame["family_passed"].map(_to_bool)]
    best = selected.iloc[0] if not selected.empty else pd.Series(dtype=object)
    summary = pd.DataFrame(
        [
            {
                "passed": passed,
                "family_id": config.family_id,
                "study_count": study_count,
                "unique_study_path_count": unique_path_count,
                "manifest_current_count": manifest_current_count,
                "source_ready_count": _bool_count(frame, "source_ready"),
                "holdout_passed_count": _bool_count(frame, "holdout_passed"),
                "abandoned_study_count": abandoned_count,
                "never_launched_study_count": never_launched_count,
                "valid_adjusted_pvalue_count": valid_pvalue_count,
                "family_candidate_count": family_candidate_count,
                "registration_provided": bool(registration.get("provided", False)),
                "prospective_registration_passed": bool(
                    registration.get("passed", False)
                ),
                "registration_id": str(registration.get("registration_id", "")),
                "registration_closed": bool(
                    passed and registration.get("passed", False)
                ),
                "launch_coverage_provided": bool(
                    launch_coverage.get("provided", False)
                ),
                "launch_coverage_passed": bool(
                    launch_coverage.get("passed", False)
                ),
                "declaration_complete_attested": bool(
                    config.declaration_complete_attested
                ),
                "family_wise_error_control_claimed": bool(
                    passed and config.declaration_complete_attested
                ),
                "max_holm_adjusted_pvalue": thresholds.max_holm_adjusted_pvalue,
                "best_study_label": str(best.get("study_label", "")),
                "best_candidate_scenario": str(best.get("candidate_scenario", "")),
                "best_holm_adjusted_pvalue": _float(
                    best.get("holm_adjusted_pvalue")
                ),
                "failed_checks": failed_checks,
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": READY_NEXT_GATE if passed else REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(
                    READY_NEXT_GATE if passed else REPAIR_NEXT_GATE
                ),
                "recommendation": (
                    "catalog_family_survivors_for_strategy_readiness"
                    if passed
                    else "repair_family_declaration_or_keep_candidates_in_research"
                ),
                "authorizes_submission": False,
            }
        ]
    )
    payload = {
        "schema_version": 1,
        "passed": passed,
        "parameters": asdict(config),
        "thresholds": asdict(thresholds),
        "summary": _record(summary.iloc[0]),
        "prospective_registration": _jsonable(registration),
        "launch_coverage": _jsonable(launch_coverage),
        "candidate_decisions": [_record(row) for _, row in frame.iterrows()],
        "selected_candidates": (
            [_record(row) for _, row in selected.iterrows()] if passed else []
        ),
    }
    return ResearchFamilyReport(
        studies=frame,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
    )


def write_research_family_audit(
    study_paths: list[str | Path],
    *,
    output_dir: str | Path,
    config: ResearchFamilyConfig,
    labels: list[str] | None = None,
    thresholds: ResearchFamilyThresholds | None = None,
    registration_path: str | Path | None = None,
    launch_matrix_path: str | Path | None = None,
) -> ResearchFamilyReport:
    paths = [Path(path).resolve() for path in study_paths]
    if not paths and launch_matrix_path is None:
        raise ValueError("at least one robust study path or launch matrix is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match study_paths length")
    resolved_labels = labels or [path.stem for path in paths]
    studies = (
        _read_studies(paths, resolved_labels)
        if paths
        else pd.DataFrame()
    )
    launch_snapshot = (
        load_research_family_launch_matrix(launch_matrix_path)
        if launch_matrix_path is not None
        else None
    )
    studies, launch_coverage = _merge_launch_coverage(
        studies,
        launch_snapshot,
    )
    registration = _read_registration(
        registration_path,
        family_id=config.family_id,
        studies=studies,
    )
    report = evaluate_research_family(
        studies,
        config=config,
        thresholds=thresholds,
        registration=registration,
        launch_coverage=launch_coverage,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.studies.to_csv(out / "research_family_studies.csv", index=False)
    report.checks.to_csv(out / "research_family_checks.csv", index=False)
    report.summary.to_csv(out / "research_family_summary.csv", index=False)
    report.action_queue.to_csv(
        out / "research_family_action_queue.csv",
        index=False,
    )
    payload = dict(report.config)
    payload.update(
        {
            "study_paths": [str(path) for path in paths],
            "study_labels": report.studies["study_label"].astype(str).tolist(),
            "completed_study_labels": resolved_labels,
            "study_manifest_sha256": {
                str(row.study_label): str(row.manifest_sha256)
                for row in report.studies.itertuples(index=False)
            },
            "declaration_complete_attested": bool(
                config.declaration_complete_attested
            ),
            "registration_path": str(registration.get("path", "")),
            "registration_manifest_sha256": str(
                registration.get("manifest_sha256", "")
            ),
            "launch_matrix_path": str(launch_coverage.get("path", "")),
            "launch_matrix_manifest_sha256": str(
                launch_coverage.get("manifest_sha256", "")
            ),
        }
    )
    (out / "research_family_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "research_family_runbook.md").write_text(
        _runbook(report.summary.iloc[0], report.studies, report.checks),
        encoding="utf-8",
    )
    manifests = [path / "manifest.json" for path in paths]
    inputs: dict[str, Any] = {
        "robust_studies": paths,
        "robust_study_manifests": [
            path for path in manifests if path.is_file()
        ],
    }
    if registration.get("provided", False):
        registration_root = Path(str(registration["path"]))
        inputs["research_family_registration"] = registration_root
        registration_manifest = registration_root / "manifest.json"
        if registration_manifest.is_file():
            inputs["research_family_registration_manifest"] = registration_manifest
    if launch_coverage.get("provided", False):
        launch_root = Path(str(launch_coverage["path"]))
        inputs["research_family_launch_matrix"] = launch_root
        launch_manifest = launch_root / "manifest.json"
        if launch_manifest.is_file():
            inputs["research_family_launch_manifest"] = launch_manifest
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "thresholds": asdict(thresholds or ResearchFamilyThresholds()),
            "labels": report.studies["study_label"].astype(str).tolist(),
            "completed_labels": resolved_labels,
        },
        inputs=inputs,
        extra={
            "passed": bool(report.passed),
            "family_id": config.family_id,
            "study_count": int(len(report.studies)),
            "family_candidate_count": int(
                report.summary.iloc[0]["family_candidate_count"]
            ),
            "declaration_complete_attested": bool(
                config.declaration_complete_attested
            ),
            "family_wise_error_control_claimed": bool(
                report.summary.iloc[0]["family_wise_error_control_claimed"]
            ),
            "prospective_registration_passed": bool(
                report.summary.iloc[0]["prospective_registration_passed"]
            ),
            "registration_id": str(report.summary.iloc[0]["registration_id"]),
            "registration_closed": bool(
                report.summary.iloc[0]["registration_closed"]
            ),
            "launch_coverage_passed": bool(
                report.summary.iloc[0]["launch_coverage_passed"]
            ),
            "abandoned_study_count": int(
                report.summary.iloc[0]["abandoned_study_count"]
            ),
            "authorizes_submission": False,
        },
    )
    return ResearchFamilyReport(
        studies=report.studies,
        checks=report.checks,
        summary=report.summary,
        action_queue=report.action_queue,
        config=payload,
        output_dir=out,
    )


def _read_studies(paths: list[Path], labels: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path, label in zip(paths, labels):
        summary_path = path / "robust_selection_pipeline_summary.csv"
        significance_path = (
            path
            / "02_backtest_significance"
            / "backtest_significance_summary.csv"
        )
        overfit_path = path / "02_backtest_overfit" / "backtest_overfit_summary.csv"
        manifest_path = path / "manifest.json"
        if not summary_path.is_file():
            raise FileNotFoundError(
                f"robust_selection_pipeline_summary.csv not found: {summary_path}"
            )
        summary = pd.read_csv(summary_path)
        if summary.empty:
            raise ValueError(f"robust selection summary is empty: {summary_path}")
        significance = (
            pd.read_csv(significance_path)
            if significance_path.is_file()
            else pd.DataFrame()
        )
        overfit = pd.read_csv(overfit_path) if overfit_path.is_file() else pd.DataFrame()
        source = summary.iloc[0]
        evidence = (
            significance.iloc[0]
            if not significance.empty
            else pd.Series(dtype=object)
        )
        overfit_evidence = (
            overfit.iloc[0] if not overfit.empty else pd.Series(dtype=object)
        )
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="robust_selection_pipeline",
            required_artifacts=(
                "robust_selection_pipeline_summary.csv",
                "02_backtest_significance/backtest_significance_summary.csv",
                "02_backtest_overfit/backtest_overfit_summary.csv",
            ),
            require_input_fingerprints=True,
        )
        manifest_payload = _read_json_object(manifest_path)
        registration_manifest_input = _manifest_input(
            manifest_payload,
            "research_family_registration_manifest",
        )
        rows.append(
            {
                "study_label": str(label),
                "study_disposition": "completed",
                "abandonment_reason": "",
                "study_path": str(path),
                "manifest_path": str(manifest_path),
                "manifest_sha256": (
                    file_sha256(manifest_path) if manifest_path.is_file() else ""
                ),
                "manifest_current": integrity.passed,
                "manifest_error": integrity.error,
                "manifest_generated_at_utc": str(
                    manifest_payload.get("generated_at_utc", "")
                ),
                "source_ready": _to_bool(source.get("ready", False)),
                "holdout_passed": _to_bool(
                    source.get("backtest_holdout_passed", False)
                ),
                "strategy": str(source.get("strategy", "")),
                "market": str(source.get("market", "")),
                "candidate_scenario": str(
                    source.get("candidate_scenario_key", "")
                ),
                "primary_metric": str(overfit_evidence.get("score_column", "")),
                "scenario_count": _int(source.get("overfit_scenario_count", 0)),
                "development_sweeps": _int(
                    source.get("development_sweep_count", 0)
                ),
                "holdout_sweeps": _int(source.get("holdout_sweep_count", 0)),
                "source_registration_provided": _to_bool(
                    source.get("research_registration_provided", False)
                ),
                "source_registration_passed": _to_bool(
                    source.get("research_registration_passed", False)
                ),
                "source_registration_id": str(
                    source.get("research_registration_id", "")
                ),
                "source_registered_study_label": str(
                    source.get("registered_study_label", "")
                ),
                "source_registration_manifest_summary_sha256": str(
                    source.get("research_registration_manifest_sha256", "")
                ),
                "source_registration_manifest_path": str(
                    registration_manifest_input.get("path", "")
                ),
                "source_registration_manifest_sha256": str(
                    registration_manifest_input.get("sha256", "")
                ),
                "scenario_trial_count": _int(
                    evidence.get(
                        "scenario_trial_count",
                        source.get("overfit_scenario_count", 0),
                    )
                ),
                "raw_sign_pvalue": _float(evidence.get("sign_pvalue")),
                "within_study_adjusted_pvalue": _float(
                    source.get(
                        "adjusted_sign_pvalue",
                        evidence.get("adjusted_sign_pvalue"),
                    )
                ),
                "source_next_gate": str(source.get("next_gate", "")),
                "source_authorizes_submission": _to_bool(
                    source.get("authorizes_submission", False)
                ),
            }
        )
    return pd.DataFrame(rows)


def _merge_launch_coverage(
    studies: pd.DataFrame,
    snapshot: ResearchFamilyLaunchSnapshot | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if snapshot is None:
        return studies, {
            "provided": False,
            "passed": False,
            "path": "",
            "manifest_sha256": "",
        }
    launches = snapshot.launches.copy()
    required = {
        "study_label",
        "planned_study_path",
        "strategy",
        "market",
        "primary_metric",
        "development_sweeps",
        "holdout_sweeps",
        "study_status",
        "closure_covered",
        "registration_id",
        "registration_manifest_sha256",
    }
    columns_present = required.issubset(launches.columns)
    launch_labels = launches.get("study_label", pd.Series(dtype=str)).astype(str)
    unique_launch_labels = bool(
        columns_present and not launch_labels.duplicated().any()
    )
    study_labels = (
        studies.get("study_label", pd.Series(dtype=str)).astype(str)
        if not studies.empty
        else pd.Series(dtype=str)
    )
    provided_labels_known = bool(set(study_labels).issubset(set(launch_labels)))
    manifest_input = _manifest_input(
        snapshot.manifest,
        "research_family_registration_manifest",
    )
    existing = studies.copy()
    if not existing.empty:
        path_by_label = launches.set_index("study_label")["planned_study_path"]
        existing["launch_path_matches"] = existing.apply(
            lambda row: (
                str(row["study_label"]) in path_by_label.index
                and _canonical_path(row["study_path"])
                == _canonical_path(path_by_label.loc[str(row["study_label"])])
            ),
            axis=1,
        )
    else:
        existing["launch_path_matches"] = pd.Series(dtype=bool)
    synthetic: list[dict[str, Any]] = []
    existing_labels = set(study_labels)
    omitted_completed = 0
    for launch in launches.itertuples(index=False):
        label = str(launch.study_label)
        if label in existing_labels:
            continue
        status = str(launch.study_status)
        if status.startswith("completed_"):
            disposition = "completed_omitted"
            omitted_completed += 1
        elif status == "abandoned":
            disposition = "abandoned"
        else:
            disposition = "never_launched"
        abandoned = disposition == "abandoned"
        registration_sha = str(launch.registration_manifest_sha256)
        synthetic.append(
            {
                "study_label": label,
                "study_disposition": disposition,
                "abandonment_reason": str(
                    getattr(launch, "abandonment_reason", "")
                ),
                "study_path": str(launch.planned_study_path),
                "manifest_path": str(snapshot.root / "manifest.json"),
                "manifest_sha256": snapshot.manifest_sha256,
                "manifest_current": bool(snapshot.manifest_current and abandoned),
                "manifest_error": "" if abandoned else disposition,
                "manifest_generated_at_utc": snapshot.generated_at_utc,
                "source_ready": False,
                "holdout_passed": False,
                "strategy": str(launch.strategy),
                "market": str(launch.market),
                "candidate_scenario": "",
                "primary_metric": str(launch.primary_metric),
                "scenario_count": 0,
                "development_sweeps": _int(launch.development_sweeps),
                "holdout_sweeps": _int(launch.holdout_sweeps),
                "source_registration_provided": abandoned,
                "source_registration_passed": bool(
                    abandoned
                    and snapshot.manifest_current
                    and snapshot.passed
                    and snapshot.registration_id
                ),
                "source_registration_id": str(launch.registration_id),
                "source_registered_study_label": label,
                "source_registration_manifest_summary_sha256": registration_sha,
                "source_registration_manifest_path": str(
                    manifest_input.get("path", "")
                ),
                "source_registration_manifest_sha256": str(
                    manifest_input.get("sha256", "")
                ),
                "scenario_trial_count": 1,
                "raw_sign_pvalue": 1.0,
                "within_study_adjusted_pvalue": 1.0,
                "source_next_gate": "audit-research-family",
                "source_authorizes_submission": False,
                "launch_path_matches": True,
            }
        )
    merged = pd.concat(
        [existing, pd.DataFrame(synthetic)],
        ignore_index=True,
        sort=False,
    )
    labels_match = bool(
        unique_launch_labels
        and len(merged) == len(launches)
        and set(merged["study_label"].astype(str)) == set(launch_labels)
    )
    paths_match = bool(
        not merged.empty
        and merged.get(
            "launch_path_matches",
            pd.Series(False, index=merged.index),
        ).map(_to_bool).all()
    )
    uncovered_count = int(
        (~launches.get(
            "closure_covered",
            pd.Series(False, index=launches.index),
        ).map(_to_bool)).sum()
    ) if not launches.empty else 0
    non_authorizing = not _to_bool(snapshot.config.get("authorizes_submission", False))
    passed = bool(
        snapshot.passed
        and snapshot.manifest_current
        and snapshot.registration_id
        and columns_present
        and unique_launch_labels
        and provided_labels_known
        and labels_match
        and paths_match
        and omitted_completed == 0
        and uncovered_count == 0
        and non_authorizing
    )
    return merged, {
        "provided": True,
        "passed": passed,
        "path": str(snapshot.root),
        "manifest_path": str(snapshot.root / "manifest.json"),
        "manifest_sha256": snapshot.manifest_sha256,
        "manifest_current": snapshot.manifest_current,
        "manifest_error": snapshot.manifest_error,
        "registration_id": snapshot.registration_id,
        "family_id": str(snapshot.config.get("family_id", "")),
        "columns_present": columns_present,
        "unique_launch_labels": unique_launch_labels,
        "provided_labels_known": provided_labels_known,
        "labels_match": labels_match,
        "paths_match": paths_match,
        "omitted_completed_count": omitted_completed,
        "uncovered_count": uncovered_count,
        "abandoned_count": int(
            merged["study_disposition"].astype(str).eq("abandoned").sum()
        ),
        "never_launched_count": int(
            merged["study_disposition"].astype(str).eq("never_launched").sum()
        ),
        "non_authorizing": non_authorizing,
    }


def _read_registration(
    raw_path: str | Path | None,
    *,
    family_id: str,
    studies: pd.DataFrame,
) -> dict[str, Any]:
    if raw_path is None:
        return {
            "provided": False,
            "passed": False,
            "path": "",
            "registration_id": "",
        }
    snapshot = load_research_family_registration(raw_path)
    root = snapshot.root
    manifest_path = root / "manifest.json"
    registration_studies = snapshot.studies
    registered_family = snapshot.family_id
    family_matches = bool(registered_family and registered_family == family_id)
    declared_labels = studies["study_label"].astype(str).tolist()
    registered_labels = registration_studies["study_label"].astype(str).tolist()
    labels_match = bool(
        len(declared_labels) == len(registered_labels)
        and set(declared_labels) == set(registered_labels)
    )
    declared_paths = {
        _canonical_path(value) for value in studies["study_path"].astype(str)
    }
    registered_paths = {
        _canonical_path(value)
        for value in registration_studies["planned_study_path"].astype(str)
    }
    paths_match = bool(
        len(declared_paths) == len(studies)
        and len(registered_paths) == len(registration_studies)
        and declared_paths == registered_paths
    )
    contract = _registration_contract_evidence(registration_studies, studies)
    binding = _source_registration_binding_evidence(
        studies,
        registration_id=snapshot.registration_id,
        registration_manifest_path=manifest_path,
        registration_manifest_sha256=snapshot.manifest_sha256,
    )
    registration_time = _parse_datetime(snapshot.generated_at_utc)
    study_times = [
        _parse_datetime(value)
        for value in studies["manifest_generated_at_utc"].astype(str)
    ]
    prospective = bool(
        registration_time is not None
        and study_times
        and all(
            study_time is not None and registration_time < study_time
            for study_time in study_times
        )
    )
    passed = bool(
        snapshot.ready
        and snapshot.manifest_current
        and family_matches
        and labels_match
        and paths_match
        and contract["strategy_market_metric_match"]
        and contract["search_breadth_within_plan"]
        and contract["period_counts_match"]
        and snapshot.registration_id_consistent
        and binding["source_registration_bindings"]
        and binding["source_registration_manifest_fingerprints"]
        and prospective
    )
    return {
        "provided": True,
        "passed": passed,
        "path": str(root),
        "manifest_path": str(manifest_path),
        "manifest_sha256": snapshot.manifest_sha256,
        "manifest_current": snapshot.manifest_current,
        "manifest_error": snapshot.manifest_error,
        "registration_ready": snapshot.ready,
        "family_matches": family_matches,
        "labels_match": labels_match,
        "paths_match": paths_match,
        **contract,
        **binding,
        "registration_id_consistent": snapshot.registration_id_consistent,
        "registration_id": snapshot.registration_id,
        "registration_generated_at_utc": snapshot.generated_at_utc,
        "prospective": prospective,
    }


def _source_registration_binding_evidence(
    studies: pd.DataFrame,
    *,
    registration_id: str,
    registration_manifest_path: Path,
    registration_manifest_sha256: str,
) -> dict[str, Any]:
    required = {
        "study_label",
        "source_registration_provided",
        "source_registration_passed",
        "source_registration_id",
        "source_registered_study_label",
        "source_registration_manifest_summary_sha256",
        "source_registration_manifest_path",
        "source_registration_manifest_sha256",
    }
    if studies.empty or not required.issubset(studies.columns):
        return {
            "source_registration_bindings": False,
            "source_registration_manifest_fingerprints": False,
            "source_registration_binding_count": 0,
            "source_registration_manifest_match_count": 0,
        }
    binding_mask = (
        studies["source_registration_provided"].map(_to_bool)
        & studies["source_registration_passed"].map(_to_bool)
        & studies["source_registration_id"].astype(str).eq(registration_id)
        & studies["source_registered_study_label"].astype(str).eq(
            studies["study_label"].astype(str)
        )
    )
    manifest_mask = (
        studies["source_registration_manifest_summary_sha256"]
        .astype(str)
        .eq(registration_manifest_sha256)
        & studies["source_registration_manifest_sha256"]
        .astype(str)
        .eq(registration_manifest_sha256)
        & studies["source_registration_manifest_path"]
        .map(_canonical_path)
        .eq(_canonical_path(registration_manifest_path))
    )
    binding_count = int(binding_mask.sum())
    manifest_count = int(manifest_mask.sum())
    return {
        "source_registration_bindings": bool(binding_mask.all()),
        "source_registration_manifest_fingerprints": bool(manifest_mask.all()),
        "source_registration_binding_count": binding_count,
        "source_registration_manifest_match_count": manifest_count,
    }


def _registration_checks(
    registration: dict[str, Any],
    config: ResearchFamilyConfig,
) -> list[dict[str, Any]]:
    provided = bool(registration.get("provided", False))
    rows: list[dict[str, Any]] = []
    if config.require_prospective_registration:
        rows.append(
            _check(
                "prospective_registration_provided",
                provided,
                "is",
                True,
                provided,
                "a prospective family registration is required for closure",
            )
        )
    if not provided:
        return rows
    for check, reason in (
        ("registration_ready", "prospective registration did not pass"),
        ("manifest_current", "registration artifacts or plan input drifted"),
        ("family_matches", "registration belongs to a different family"),
        ("labels_match", "declared study labels differ from the registration"),
        ("paths_match", "robust-study roots differ from the registered plan"),
        (
            "strategy_market_metric_match",
            "actual strategy, market, or primary metric differs from the plan",
        ),
        (
            "search_breadth_within_plan",
            "actual scenario count exceeds the registered maximum",
        ),
        (
            "period_counts_match",
            "actual development or holdout period count differs from the plan",
        ),
        (
            "source_registration_bindings",
            "one or more robust-study roots were not launched from the registered study row",
        ),
        (
            "source_registration_manifest_fingerprints",
            "one or more robust-study roots fingerprint a different registration manifest",
        ),
        (
            "registration_id_consistent",
            "registration ID differs across summary, config, lock, or manifest",
        ),
        ("prospective", "registration was not created before every study result"),
    ):
        passed = bool(registration.get(check, False))
        rows.append(_check(check, passed, "is", True, passed, reason))
    return rows


def _launch_coverage_checks(
    coverage: dict[str, Any],
    config: ResearchFamilyConfig,
    registration: dict[str, Any],
) -> list[dict[str, Any]]:
    provided = bool(coverage.get("provided", False))
    rows: list[dict[str, Any]] = []
    if config.require_launch_coverage:
        rows.append(
            _check(
                "launch_coverage_provided",
                provided,
                "is",
                True,
                provided,
                "a current registered-study launch matrix is required",
            )
        )
    if not provided:
        return rows
    family_matches = bool(
        str(coverage.get("family_id", "")) == config.family_id
    )
    registration_matches = bool(
        not registration.get("provided", False)
        or str(coverage.get("registration_id", ""))
        == str(registration.get("registration_id", ""))
    )
    rows.extend(
        [
            _check(
                "launch_family_matches",
                family_matches,
                "is",
                True,
                family_matches,
                "launch matrix belongs to a different research family",
            ),
            _check(
                "launch_registration_matches",
                registration_matches,
                "is",
                True,
                registration_matches,
                "launch matrix and closure use different registration IDs",
            ),
        ]
    )
    for check, reason in (
        ("manifest_current", "launch matrix artifacts or inputs drifted"),
        ("columns_present", "launch matrix is missing closure fields"),
        ("unique_launch_labels", "launch matrix study labels are duplicated"),
        (
            "provided_labels_known",
            "a supplied robust study is absent from the launch matrix",
        ),
        ("labels_match", "launch matrix does not cover the registered family"),
        ("paths_match", "supplied robust roots differ from launch contracts"),
        (
            "non_authorizing",
            "launch matrix unexpectedly claims broker-submission authority",
        ),
    ):
        passed = bool(coverage.get(check, False))
        rows.append(
            _check(
                f"launch_{check}",
                passed,
                "is",
                True,
                passed,
                reason,
            )
        )
    rows.extend(
        [
            _numeric_check(
                "launch_omitted_completed_studies",
                int(coverage.get("omitted_completed_count", 0)),
                "==",
                0,
                "a completed registered study was omitted from family inputs",
            ),
            _numeric_check(
                "launch_uncovered_studies",
                int(coverage.get("uncovered_count", 0)),
                "==",
                0,
                "registered studies remain never launched or unaccounted for",
            ),
            _check(
                "launch_coverage_passed",
                bool(coverage.get("passed", False)),
                "is",
                True,
                bool(coverage.get("passed", False)),
                "registered-study launch coverage did not pass",
            ),
        ]
    )
    return rows


def _check(
    check: str,
    actual: Any,
    operator: str,
    expected: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _canonical_path(value: Any) -> str:
    return str(Path(str(value)).resolve()).casefold()


def _registration_contract_evidence(
    registration_studies: pd.DataFrame,
    studies: pd.DataFrame,
) -> dict[str, bool]:
    if registration_studies.empty or studies.empty:
        return {
            "strategy_market_metric_match": False,
            "search_breadth_within_plan": False,
            "period_counts_match": False,
        }
    required_registration = {
        "study_label",
        "strategy",
        "market",
        "primary_metric",
        "max_scenarios",
        "development_sweeps",
        "holdout_sweeps",
    }
    required_actual = {
        "study_label",
        "strategy",
        "market",
        "primary_metric",
        "scenario_count",
        "development_sweeps",
        "holdout_sweeps",
        "study_disposition",
    }
    if not required_registration.issubset(registration_studies.columns) or not (
        required_actual.issubset(studies.columns)
    ):
        return {
            "strategy_market_metric_match": False,
            "search_breadth_within_plan": False,
            "period_counts_match": False,
        }
    if registration_studies["study_label"].duplicated().any() or studies[
        "study_label"
    ].duplicated().any():
        return {
            "strategy_market_metric_match": False,
            "search_breadth_within_plan": False,
            "period_counts_match": False,
        }
    planned = registration_studies[list(required_registration)].copy()
    actual = studies[list(required_actual)].copy()
    merged = planned.merge(
        actual,
        on="study_label",
        how="inner",
        suffixes=("_planned", "_actual"),
        validate="one_to_one",
    )
    complete = bool(len(merged) == len(planned) == len(actual))
    identity_match = bool(
        complete
        and merged["strategy_planned"].astype(str).eq(
            merged["strategy_actual"].astype(str)
        ).all()
        and merged["market_planned"].astype(str).eq(
            merged["market_actual"].astype(str)
        ).all()
        and merged["primary_metric_planned"].astype(str).eq(
            merged["primary_metric_actual"].astype(str)
        ).all()
    )
    planned_scenarios = pd.to_numeric(merged["max_scenarios"], errors="coerce")
    actual_scenarios = pd.to_numeric(merged["scenario_count"], errors="coerce")
    abandoned = merged["study_disposition"].astype(str).eq("abandoned")
    breadth_match = bool(
        complete
        and np.isfinite(planned_scenarios).all()
        and np.isfinite(actual_scenarios).all()
        and (actual_scenarios.gt(0) | abandoned).all()
        and actual_scenarios.le(planned_scenarios).all()
    )
    period_match = bool(
        complete
        and pd.to_numeric(
            merged["development_sweeps_planned"], errors="coerce"
        ).eq(
            pd.to_numeric(
                merged["development_sweeps_actual"], errors="coerce"
            )
        ).all()
        and pd.to_numeric(
            merged["holdout_sweeps_planned"], errors="coerce"
        ).eq(
            pd.to_numeric(merged["holdout_sweeps_actual"], errors="coerce")
        ).all()
    )
    return {
        "strategy_market_metric_match": identity_match,
        "search_breadth_within_plan": breadth_match,
        "period_counts_match": period_match,
    }


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _manifest_input(payload: dict[str, Any], name: str) -> dict[str, Any]:
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        return {}
    value = inputs.get(name, {})
    return value if isinstance(value, dict) else {}


def _holm_adjust(
    studies: pd.DataFrame,
    threshold: float,
    *,
    config: ResearchFamilyConfig,
) -> pd.DataFrame:
    frame = studies.copy()
    if frame.empty:
        for column in (
            "family_rank",
            "holm_factor",
            "holm_adjusted_pvalue",
            "source_eligible",
            "family_passed",
        ):
            frame[column] = pd.Series(dtype=float if "pvalue" in column else object)
        return frame
    pvalues = _numeric(frame, "within_study_adjusted_pvalue")
    frame["family_rank"] = 0
    frame["holm_factor"] = np.nan
    frame["holm_adjusted_pvalue"] = np.nan
    valid = np.isfinite(pvalues) & pvalues.between(0.0, 1.0)
    finite = frame.loc[valid].copy()
    finite["_pvalue"] = pvalues.loc[finite.index]
    finite = finite.sort_values(
        ["_pvalue", "study_label", "study_path"],
        kind="stable",
    )
    running = 0.0
    family_size = int(len(frame))
    for rank, (index, row) in enumerate(finite.iterrows(), start=1):
        factor = family_size - rank + 1
        running = max(running, min(1.0, float(row["_pvalue"]) * factor))
        frame.loc[index, "family_rank"] = rank
        frame.loc[index, "holm_factor"] = factor
        frame.loc[index, "holm_adjusted_pvalue"] = running
    source_ready = frame.get("source_ready", False).map(_to_bool)
    holdout_passed = frame.get("holdout_passed", False).map(_to_bool)
    manifest_current = frame.get("manifest_current", False).map(_to_bool)
    non_authorizing = ~frame.get(
        "source_authorizes_submission",
        pd.Series(False, index=frame.index),
    ).map(_to_bool)
    frame["source_eligible"] = (
        (source_ready | (not config.require_source_ready))
        & (holdout_passed | (not config.require_holdout_passed))
        & (manifest_current | (not config.require_study_manifests))
        & non_authorizing
        & frame.get("candidate_scenario", "").astype(str).str.strip().ne("")
    )
    frame["family_passed"] = (
        frame["source_eligible"]
        & valid
        & _numeric(frame, "holm_adjusted_pvalue").le(threshold)
    )
    return frame.sort_values(
        ["family_passed", "family_rank", "study_label"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    rows: list[dict[str, Any]] = []
    for priority, row in enumerate(failed.itertuples(index=False), start=1):
        recommendation = _recommendation(str(row.check))
        rows.append(
            {
                "priority": priority,
                "queue_status": "blocked",
                "source": RUN_TYPE,
                "component": "study_family",
                "check": str(row.check),
                "actual": row.actual,
                "operator": row.operator,
                "expected": row.expected,
                "action": recommendation,
                "reason": str(row.reason),
                "recommendation": recommendation,
                "next_gate": REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(REPAIR_NEXT_GATE),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _recommendation(check: str) -> str:
    if check.startswith("launch_"):
        return "repair_launch_coverage_or_include_every_completed_study"
    if check == "prospective_registration_provided":
        return "register_the_family_before_producing_study_outcomes"
    if check in {
        "registration_ready",
        "manifest_current",
        "registration_id_consistent",
    }:
        return "restore_the_original_current_registration_and_lock"
    if check in {"family_matches", "labels_match", "paths_match"}:
        return "close_exactly_the_family_labels_and_paths_that_were_registered"
    if check == "strategy_market_metric_match":
        return "rerun_each_study_with_its_registered_strategy_market_and_metric"
    if check in {"search_breadth_within_plan", "period_counts_match"}:
        return "create_a_new_registration_before_changing_search_or_period_counts"
    if check in {
        "source_registration_bindings",
        "source_registration_manifest_fingerprints",
    }:
        return "rerun_each_study_directly_from_its_registered_plan_row"
    if check == "prospective":
        return "create_a_new_registration_before_running_a_new_study_family"
    if check == "family_declaration_attested":
        return "declare_every_attempted_study_then_attest_family_completeness"
    if check == "study_count":
        return "declare_all_attempted_studies_before_family_review"
    if check in {"unique_study_paths", "unique_study_labels"}:
        return "remove_duplicate_declarations_and_assign_unique_labels"
    if check == "current_study_manifests":
        return "regenerate_drifted_robust_studies_from_current_inputs"
    if check in {"candidate_scenarios", "valid_adjusted_pvalues"}:
        return "complete_each_robust_study_without_omitting_failed_attempts"
    if check == "non_authorizing_sources":
        return "repair_source_evidence_that_claims_submission_authority"
    return "collect_new_evidence_or_reduce_the_declared_research_family"


def _numeric_check(
    check: str,
    actual: Any,
    operator: str,
    expected: int | float,
    reason: str,
    *,
    allow_failure: bool = False,
) -> dict[str, Any]:
    value = _float(actual)
    expected_value = _float(expected)
    matched = bool(
        np.isfinite(value)
        and np.isfinite(expected_value)
        and (
            (operator == ">=" and value >= expected_value)
            or (operator == "==" and value == expected_value)
        )
    )
    passed = matched or allow_failure
    return {
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "passed": passed,
        "reason": "" if passed else reason,
    }


def _validate(
    config: ResearchFamilyConfig,
    thresholds: ResearchFamilyThresholds,
) -> None:
    if not config.family_id.strip():
        raise ValueError("family_id must be non-empty")
    if thresholds.min_studies < 2:
        raise ValueError("min_studies must be at least 2")
    if thresholds.min_family_candidates < 1:
        raise ValueError("min_family_candidates must be positive")
    if not 0.0 <= thresholds.max_holm_adjusted_pvalue <= 1.0:
        raise ValueError("max_holm_adjusted_pvalue must be between 0 and 1")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"research family studies missing columns: {missing}")


def _runbook(
    summary: pd.Series,
    studies: pd.DataFrame,
    checks: pd.DataFrame,
) -> str:
    lines = [
        "# Research Family Audit",
        "",
        f"- Status: **{'passed' if bool(summary['passed']) else 'blocked'}**",
        f"- Family: `{summary['family_id']}`",
        "- Prospective registration: "
        f"`{str(bool(summary['prospective_registration_passed'])).lower()}`",
        f"- Registration ID: `{summary['registration_id']}`",
        "- Registration closed: "
        f"`{str(bool(summary['registration_closed'])).lower()}`",
        "- Launch coverage: "
        f"`{str(bool(summary['launch_coverage_passed'])).lower()}`",
        "- Complete-family attestation: "
        f"`{str(bool(summary['declaration_complete_attested'])).lower()}`",
        f"- Declared studies: {int(summary['study_count'])}",
        f"- Current manifests: {int(summary['manifest_current_count'])}",
        f"- Source-ready studies: {int(summary['source_ready_count'])}",
        f"- Attested abandoned studies: {int(summary['abandoned_study_count'])}",
        f"- Family-surviving candidates: {int(summary['family_candidate_count'])}",
        (
            "- Best Holm-adjusted p-value: "
            f"{_format_number(summary['best_holm_adjusted_pvalue'])}"
        ),
        f"- Next gate: `{summary['next_gate']}`",
        "- Authorizes submission: `false`",
        "",
        (
            "Holm-Bonferroni is applied to each study's scenario-adjusted "
            "p-value. Failed and non-ready declared attempts remain in the "
            "family size; they are never promoted as candidates."
        ),
        (
            "This report cannot detect omitted experiments. Family-wise error "
            "control is invalid if attempted studies are left out or registered "
            "only after their outcomes are inspected."
        ),
        "",
        "## Studies",
        "",
    ]
    for row in studies.itertuples(index=False):
        lines.append(
            f"- `{row.study_label}` ({row.study_disposition}) / "
            f"`{row.candidate_scenario}`: "
            f"within={_format_number(row.within_study_adjusted_pvalue)}, "
            f"Holm={_format_number(row.holm_adjusted_pvalue)}, "
            f"{'passed' if bool(row.family_passed) else 'blocked'}"
        )
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    if not failed.empty:
        lines.extend(["", "## Blocking Checks", ""])
        for row in failed.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.reason}")
    return "\n".join(lines) + "\n"


def _bool_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].map(_to_bool).sum())


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


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
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready"}
    return bool(value)


def _int(value: Any) -> int:
    number = _float(value)
    return int(number) if np.isfinite(number) else 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _format_number(value: Any) -> str:
    number = _float(value)
    return "n/a" if not np.isfinite(number) else f"{number:.6f}"


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"
