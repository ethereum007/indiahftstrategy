from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


RUN_TYPE = "research_family_registration"
READY_NEXT_GATE = "audit-research-family"
REPAIR_NEXT_GATE = "register-research-family"

REQUIRED_COLUMNS = (
    "study_label",
    "strategy",
    "market",
    "hypothesis",
    "planned_study_path",
    "primary_metric",
    "max_scenarios",
    "development_sweeps",
    "holdout_sweeps",
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
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]


@dataclass(frozen=True)
class ResearchFamilyRegistrationThresholds:
    min_studies: int = 2
    min_development_sweeps: int = 6
    min_holdout_sweeps: int = 3


@dataclass(frozen=True)
class ResearchFamilyRegistrationReport:
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


@dataclass(frozen=True)
class ResearchFamilyRegistrationSnapshot:
    root: Path
    studies: pd.DataFrame
    summary: dict[str, Any]
    config: dict[str, Any]
    lock: dict[str, Any]
    manifest: dict[str, Any]
    family_id: str
    registration_id: str
    registration_id_consistent: bool
    ready: bool
    manifest_current: bool
    manifest_error: str
    manifest_sha256: str
    generated_at_utc: str


def evaluate_research_family_registration(
    plan: pd.DataFrame,
    *,
    family_id: str,
    plan_root: str | Path,
    thresholds: ResearchFamilyRegistrationThresholds | None = None,
) -> ResearchFamilyRegistrationReport:
    thresholds = thresholds or ResearchFamilyRegistrationThresholds()
    _validate(family_id, thresholds)
    studies = _normalize_plan(plan, Path(plan_root))
    study_count = int(len(studies))
    unique_labels = int(studies["study_label"].nunique()) if not studies.empty else 0
    unique_paths = (
        int(studies["planned_study_path"].str.casefold().nunique())
        if not studies.empty
        else 0
    )
    complete_text_rows = _complete_text_rows(studies)
    valid_scenario_rows = int(
        _positive_integer_mask(studies, "max_scenarios", minimum=1).sum()
    )
    valid_development_rows = int(
        _positive_integer_mask(
            studies,
            "development_sweeps",
            minimum=thresholds.min_development_sweeps,
        ).sum()
    )
    valid_holdout_rows = int(
        _positive_integer_mask(
            studies,
            "holdout_sweeps",
            minimum=thresholds.min_holdout_sweeps,
        ).sum()
    )
    audit_paths = studies.get(
        "walkforward_split_audit_path",
        pd.Series("", index=studies.index, dtype=str),
    ).fillna("").astype(str).str.strip()
    audit_required = studies.get(
        "require_walkforward_split_audit",
        pd.Series(False, index=studies.index, dtype=bool),
    ).map(_to_bool)
    valid_audit_declarations = int((~audit_required | audit_paths.ne("")).sum())
    checks = pd.DataFrame(
        [
            _numeric_check(
                "study_count",
                study_count,
                ">=",
                thresholds.min_studies,
                "registration requires more planned studies",
            ),
            _numeric_check(
                "unique_study_labels",
                unique_labels,
                "==",
                study_count,
                "planned study labels must be unique",
            ),
            _numeric_check(
                "unique_study_paths",
                unique_paths,
                "==",
                study_count,
                "planned robust-study roots must be unique",
            ),
            _numeric_check(
                "complete_text_fields",
                complete_text_rows,
                "==",
                study_count,
                "strategy, market, hypothesis, metric, and path are required",
            ),
            _numeric_check(
                "valid_max_scenarios",
                valid_scenario_rows,
                "==",
                study_count,
                "max_scenarios must be a positive integer for every study",
            ),
            _numeric_check(
                "development_sweep_plan",
                valid_development_rows,
                "==",
                study_count,
                "every study must plan enough development sweeps",
            ),
            _numeric_check(
                "holdout_sweep_plan",
                valid_holdout_rows,
                "==",
                study_count,
                "every study must reserve enough chronological holdouts",
            ),
            _numeric_check(
                "walkforward_split_audit_declarations",
                valid_audit_declarations,
                "==",
                study_count,
                "every required walk-forward split audit needs a planned path",
            ),
        ]
    )
    passed = bool(not checks.empty and checks["passed"].astype(bool).all())
    failed_checks = int((~checks["passed"].astype(bool)).sum())
    action_queue = _action_queue(checks)
    registration_id = registration_id_for_plan(family_id, studies)
    summary = pd.DataFrame(
        [
            {
                "passed": passed,
                "family_id": family_id,
                "registration_id": registration_id,
                "study_count": study_count,
                "unique_study_label_count": unique_labels,
                "unique_study_path_count": unique_paths,
                "min_planned_development_sweeps": _min_int(
                    studies,
                    "development_sweeps",
                ),
                "min_planned_holdout_sweeps": _min_int(
                    studies,
                    "holdout_sweeps",
                ),
                "total_max_scenarios": _sum_int(studies, "max_scenarios"),
                "walkforward_split_audit_declared_count": int(
                    audit_paths.ne("").sum()
                ),
                "walkforward_split_audit_required_count": int(
                    audit_required.sum()
                ),
                "failed_checks": failed_checks,
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": READY_NEXT_GATE if passed else REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(
                    READY_NEXT_GATE if passed else REPAIR_NEXT_GATE
                ),
                "recommendation": (
                    "run_only_the_registered_studies_then_close_the_family"
                    if passed
                    else "repair_and_reregister_before_producing_outcomes"
                ),
                "closed": False,
                "authorizes_submission": False,
            }
        ]
    )
    payload = {
        "schema_version": 1,
        "passed": passed,
        "family_id": family_id,
        "registration_id": registration_id,
        "thresholds": asdict(thresholds),
        "planned_studies": [_record(row) for _, row in studies.iterrows()],
        "summary": _record(summary.iloc[0]),
        "closed": False,
        "authorizes_submission": False,
    }
    return ResearchFamilyRegistrationReport(
        studies=studies,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
    )


def write_research_family_registration(
    plan_path: str | Path,
    *,
    output_dir: str | Path,
    family_id: str,
    thresholds: ResearchFamilyRegistrationThresholds | None = None,
) -> ResearchFamilyRegistrationReport:
    source = Path(plan_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"research family plan not found: {source}")
    plan = pd.read_csv(source)
    report = evaluate_research_family_registration(
        plan,
        family_id=family_id,
        plan_root=source.parent,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.studies.to_csv(
        out / "research_family_registration_studies.csv",
        index=False,
    )
    report.checks.to_csv(
        out / "research_family_registration_checks.csv",
        index=False,
    )
    report.summary.to_csv(
        out / "research_family_registration_summary.csv",
        index=False,
    )
    report.action_queue.to_csv(
        out / "research_family_registration_action_queue.csv",
        index=False,
    )
    normalized_sha256 = _frame_sha256(report.studies)
    payload = dict(report.config)
    payload.update(
        {
            "plan_path": str(source),
            "plan_sha256": file_sha256(source),
            "normalized_studies_sha256": normalized_sha256,
        }
    )
    (out / "research_family_registration_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lock = {
        "schema_version": 1,
        "family_id": family_id,
        "registration_id": str(report.summary.iloc[0]["registration_id"]),
        "plan_sha256": file_sha256(source),
        "normalized_studies_sha256": normalized_sha256,
        "study_count": int(report.summary.iloc[0]["study_count"]),
        "passed": bool(report.passed),
        "closed": False,
        "authorizes_submission": False,
    }
    (out / "registration.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "research_family_registration_runbook.md").write_text(
        _runbook(report.summary.iloc[0], report.studies, report.checks),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "family_id": family_id,
            "thresholds": asdict(
                thresholds or ResearchFamilyRegistrationThresholds()
            ),
        },
        inputs={"research_family_plan": source},
        extra={
            "passed": bool(report.passed),
            "family_id": family_id,
            "registration_id": str(report.summary.iloc[0]["registration_id"]),
            "study_count": int(report.summary.iloc[0]["study_count"]),
            "normalized_studies_sha256": normalized_sha256,
            "closed": False,
            "authorizes_submission": False,
        },
    )
    return ResearchFamilyRegistrationReport(
        studies=report.studies,
        checks=report.checks,
        summary=report.summary,
        action_queue=report.action_queue,
        config=payload,
        output_dir=out,
    )


def load_research_family_registration(
    registration_path: str | Path,
) -> ResearchFamilyRegistrationSnapshot:
    path = Path(registration_path).resolve()
    root = path if path.is_dir() else path.parent
    summary_path = root / "research_family_registration_summary.csv"
    studies_path = root / "research_family_registration_studies.csv"
    config_path = root / "research_family_registration_config.json"
    lock_path = root / "registration.lock.json"
    manifest_path = root / "manifest.json"
    for required in (
        summary_path,
        studies_path,
        config_path,
        lock_path,
        manifest_path,
    ):
        if not required.is_file():
            raise FileNotFoundError(
                f"required research family registration artifact not found: {required}"
            )
    summary_frame = pd.read_csv(summary_path)
    if summary_frame.empty:
        raise ValueError(f"research family registration summary is empty: {summary_path}")
    studies = _normalize_plan(pd.read_csv(studies_path), root)
    summary = _record(summary_frame.iloc[0])
    config = _read_json_object(config_path)
    lock = _read_json_object(lock_path)
    manifest = _read_json_object(manifest_path)
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=(
            "research_family_registration_summary.csv",
            "research_family_registration_studies.csv",
            "research_family_registration_config.json",
            "registration.lock.json",
        ),
        require_input_fingerprints=True,
    )
    manifest_extra = manifest.get("extra", {})
    family_id = str(summary.get("family_id", ""))
    recomputed_id = registration_id_for_plan(family_id, studies)
    ids = {
        str(summary.get("registration_id", "")),
        str(config.get("registration_id", "")),
        str(lock.get("registration_id", "")),
        str(manifest_extra.get("registration_id", ""))
        if isinstance(manifest_extra, dict)
        else "",
        recomputed_id,
    }
    registration_id_consistent = bool(len(ids) == 1 and "" not in ids)
    registration_id = next(iter(ids)) if registration_id_consistent else ""
    statuses = [
        _to_bool(summary.get("passed", False)),
        _to_bool(config.get("passed", False)),
        _to_bool(lock.get("passed", False)),
        _to_bool(manifest_extra.get("passed", False))
        if isinstance(manifest_extra, dict)
        else False,
    ]
    return ResearchFamilyRegistrationSnapshot(
        root=root,
        studies=studies,
        summary=summary,
        config=config,
        lock=lock,
        manifest=manifest,
        family_id=family_id,
        registration_id=registration_id,
        registration_id_consistent=registration_id_consistent,
        ready=bool(all(statuses)),
        manifest_current=bool(integrity.passed),
        manifest_error=str(integrity.error),
        manifest_sha256=(
            file_sha256(manifest_path) if manifest_path.is_file() else ""
        ),
        generated_at_utc=str(manifest.get("generated_at_utc", "")),
    )


def _normalize_plan(plan: pd.DataFrame, root: Path) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in plan.columns]
    if missing:
        raise ValueError(f"research family plan missing columns: {missing}")
    frame = plan.copy()
    for column in (
        "study_label",
        "strategy",
        "market",
        "hypothesis",
        "primary_metric",
    ):
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    frame["planned_study_path"] = frame["planned_study_path"].map(
        lambda value: _planned_path(value, root)
    )
    if "walkforward_split_audit_path" in frame.columns:
        frame["walkforward_split_audit_path"] = frame[
            "walkforward_split_audit_path"
        ].map(lambda value: _planned_path(value, root))
    if "require_walkforward_split_audit" in frame.columns:
        frame["require_walkforward_split_audit"] = frame[
            "require_walkforward_split_audit"
        ].map(_strict_bool)
    for column in ("max_scenarios", "development_sweeps", "holdout_sweeps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    ordered = list(REQUIRED_COLUMNS) + [
        column for column in frame.columns if column not in REQUIRED_COLUMNS
    ]
    return frame[ordered].sort_values(
        ["study_label", "planned_study_path"],
        kind="stable",
    ).reset_index(drop=True)


def _planned_path(value: Any, root: Path) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if not text:
        return ""
    path = Path(text)
    return str((root / path).resolve() if not path.is_absolute() else path.resolve())


def _strict_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if not text:
        return False
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _complete_text_rows(studies: pd.DataFrame) -> int:
    if studies.empty:
        return 0
    columns = (
        "study_label",
        "strategy",
        "market",
        "hypothesis",
        "planned_study_path",
        "primary_metric",
    )
    complete = pd.Series(True, index=studies.index)
    for column in columns:
        complete &= studies[column].astype(str).str.strip().ne("")
    return int(complete.sum())


def registration_id_for_plan(family_id: str, studies: pd.DataFrame) -> str:
    payload = {
        "family_id": family_id,
        "studies": [_record(row) for _, row in studies.iterrows()],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    records = [_record(row) for _, row in frame.iterrows()]
    encoded = json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
                "component": "prospective_registration",
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
    if check == "study_count":
        return "add_every_planned_study_to_the_family_plan"
    if check in {"unique_study_labels", "unique_study_paths"}:
        return "assign_unique_labels_and_future_result_roots"
    if check == "complete_text_fields":
        return "complete_strategy_market_hypothesis_metric_and_path_fields"
    if check == "valid_max_scenarios":
        return "declare_a_positive_maximum_search_breadth_per_study"
    if check == "development_sweep_plan":
        return "plan_at_least_six_development_sweeps_per_study"
    if check == "walkforward_split_audit_declarations":
        return "declare_an_audit_path_for_each_required_model_study"
    return "reserve_at_least_three_chronological_holdouts_per_study"


def _numeric_check(
    check: str,
    actual: Any,
    operator: str,
    expected: int | float,
    reason: str,
) -> dict[str, Any]:
    value = _float(actual)
    expected_value = _float(expected)
    passed = bool(
        np.isfinite(value)
        and np.isfinite(expected_value)
        and (
            (operator == ">=" and value >= expected_value)
            or (operator == "==" and value == expected_value)
        )
    )
    return {
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "passed": passed,
        "reason": "" if passed else reason,
    }


def _validate(
    family_id: str,
    thresholds: ResearchFamilyRegistrationThresholds,
) -> None:
    if not family_id.strip():
        raise ValueError("family_id must be non-empty")
    if thresholds.min_studies < 2:
        raise ValueError("min_studies must be at least 2")
    if thresholds.min_development_sweeps < 1:
        raise ValueError("min_development_sweeps must be positive")
    if thresholds.min_holdout_sweeps < 1:
        raise ValueError("min_holdout_sweeps must be positive")


def _runbook(
    summary: pd.Series,
    studies: pd.DataFrame,
    checks: pd.DataFrame,
) -> str:
    lines = [
        "# Prospective Research Family Registration",
        "",
        f"- Status: **{'registered' if bool(summary['passed']) else 'blocked'}**",
        f"- Family: `{summary['family_id']}`",
        f"- Registration ID: `{summary['registration_id']}`",
        f"- Planned studies: {int(summary['study_count'])}",
        (
            "- Minimum development/holdout sweeps: "
            f"{int(summary['min_planned_development_sweeps'])}/"
            f"{int(summary['min_planned_holdout_sweeps'])}"
        ),
        f"- Planned maximum scenarios: {int(summary['total_max_scenarios'])}",
        (
            "- Walk-forward split audits (declared/required): "
            f"{int(summary['walkforward_split_audit_declared_count'])}/"
            f"{int(summary['walkforward_split_audit_required_count'])}"
        ),
        f"- Next gate: `{summary['next_gate']}`",
        "- Closed: `false`",
        "- Authorizes submission: `false`",
        "",
        (
            "Produce outcomes only after this registration is written and "
            "preserved. Changing hypotheses, metrics, search breadth, period "
            "counts, or result roots requires a new registration ID."
        ),
        "",
        "## Planned Studies",
        "",
    ]
    for row in studies.itertuples(index=False):
        lines.append(
            f"- `{row.study_label}`: {row.strategy} / {row.market}; "
            f"metric `{row.primary_metric}`; max scenarios "
            f"{int(row.max_scenarios) if np.isfinite(row.max_scenarios) else 'n/a'}"
        )
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    if not failed.empty:
        lines.extend(["", "## Blocking Checks", ""])
        for row in failed.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.reason}")
    return "\n".join(lines) + "\n"


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _positive_integer_mask(
    frame: pd.DataFrame,
    column: str,
    *,
    minimum: int,
) -> pd.Series:
    values = _numeric(frame, column)
    return np.isfinite(values) & values.ge(minimum) & values.mod(1).eq(0)


def _min_int(frame: pd.DataFrame, column: str) -> int:
    values = _numeric(frame, column)
    finite = values.loc[np.isfinite(values)]
    return int(finite.min()) if not finite.empty else 0


def _sum_int(frame: pd.DataFrame, column: str) -> int:
    values = _numeric(frame, column)
    finite = values.loc[np.isfinite(values)]
    return int(finite.sum()) if not finite.empty else 0


def _record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "ready",
            "passed",
        }
    return bool(value)


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


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"
