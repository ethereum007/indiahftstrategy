from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
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
    ResearchFamilyRegistrationSnapshot,
    load_research_family_registration,
)


RUN_TYPE = "research_family_launch_matrix"
READY_NEXT_GATE = "audit-research-family"
LAUNCH_NEXT_GATE = "pipeline-robust-selection"
REPAIR_NEXT_GATE = "plan-research-family-launches"

LAUNCH_COLUMNS = (
    "sweep_paths_json",
    "group_cols_json",
)
ABANDONMENT_COLUMNS = (
    "study_label",
    "reason",
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
class ResearchFamilyLaunchReport:
    launches: pd.DataFrame
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
class ResearchFamilyLaunchSnapshot:
    root: Path
    launches: pd.DataFrame
    summary: dict[str, Any]
    config: dict[str, Any]
    manifest: dict[str, Any]
    passed: bool
    manifest_current: bool
    manifest_error: str
    manifest_sha256: str
    generated_at_utc: str
    registration_id: str


def load_research_family_launch_matrix(
    launch_matrix_path: str | Path,
) -> ResearchFamilyLaunchSnapshot:
    path = Path(launch_matrix_path).resolve()
    root = path if path.is_dir() else path.parent
    launches_path = root / "research_family_launch_matrix.csv"
    summary_path = root / "research_family_launch_summary.csv"
    config_path = root / "research_family_launch_config.json"
    manifest_path = root / "manifest.json"
    for required in (launches_path, summary_path, config_path, manifest_path):
        if not required.is_file():
            raise FileNotFoundError(
                f"required research family launch artifact not found: {required}"
            )
    launches = pd.read_csv(launches_path)
    summary_frame = pd.read_csv(summary_path)
    if summary_frame.empty:
        raise ValueError(f"research family launch summary is empty: {summary_path}")
    summary = _record(summary_frame.iloc[0])
    config = _read_json_object(config_path)
    manifest = _read_json_object(manifest_path)
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=(
            "research_family_launch_matrix.csv",
            "research_family_launch_checks.csv",
            "research_family_launch_summary.csv",
            "research_family_launch_action_queue.csv",
            "research_family_launch_config.json",
        ),
        require_input_fingerprints=True,
    )
    manifest_extra = manifest.get("extra", {})
    statuses = (
        _to_bool(summary.get("passed", False)),
        _to_bool(config.get("passed", False)),
        _to_bool(manifest_extra.get("passed", False))
        if isinstance(manifest_extra, dict)
        else False,
    )
    registration_ids = {
        str(summary.get("registration_id", "")),
        str(config.get("registration_id", "")),
        str(manifest_extra.get("registration_id", ""))
        if isinstance(manifest_extra, dict)
        else "",
    }
    registration_id = (
        next(iter(registration_ids))
        if len(registration_ids) == 1 and "" not in registration_ids
        else ""
    )
    return ResearchFamilyLaunchSnapshot(
        root=root,
        launches=launches,
        summary=summary,
        config=config,
        manifest=manifest,
        passed=bool(all(statuses)),
        manifest_current=bool(integrity.passed),
        manifest_error=str(integrity.error),
        manifest_sha256=file_sha256(manifest_path),
        generated_at_utc=str(manifest.get("generated_at_utc", "")),
        registration_id=registration_id,
    )


def write_research_family_launch_matrix(
    registration_path: str | Path,
    *,
    output_dir: str | Path,
    abandonment_path: str | Path | None = None,
    attest_abandonments: bool = False,
) -> ResearchFamilyLaunchReport:
    registration = load_research_family_registration(registration_path)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    contract_dir = out / "contracts"
    contract_dir.mkdir(parents=True, exist_ok=True)

    abandonments, abandonment_source = _read_abandonments(abandonment_path)
    plan_path = Path(str(registration.config.get("plan_path", "")))
    plan_root = plan_path.parent if plan_path.is_file() else registration.root
    launches = _build_launches(
        registration,
        abandonments=abandonments,
        attest_abandonments=attest_abandonments,
        plan_root=plan_root,
        contract_dir=contract_dir,
    )
    checks = _checks(
        registration,
        launches,
        abandonments,
        attest_abandonments=attest_abandonments,
    )
    passed = bool(not checks.empty and checks["passed"].map(_to_bool).all())
    action_queue = _action_queue(launches, checks)
    summary = _summary(
        registration,
        launches,
        checks,
        action_queue,
        passed=passed,
        attest_abandonments=attest_abandonments,
    )
    launches.to_csv(out / "research_family_launch_matrix.csv", index=False)
    checks.to_csv(out / "research_family_launch_checks.csv", index=False)
    summary.to_csv(out / "research_family_launch_summary.csv", index=False)
    action_queue.to_csv(
        out / "research_family_launch_action_queue.csv",
        index=False,
    )
    payload = {
        "schema_version": 1,
        "passed": passed,
        "family_id": registration.family_id,
        "registration_id": registration.registration_id,
        "registration_path": str(registration.root),
        "registration_manifest_sha256": registration.manifest_sha256,
        "abandonment_path": str(abandonment_source or ""),
        "attest_abandonments": bool(attest_abandonments),
        "summary": _record(summary.iloc[0]),
        "launch_contracts": [_record(row) for _, row in launches.iterrows()],
        "authorizes_submission": False,
    }
    (out / "research_family_launch_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "research_family_launch_runbook.md").write_text(
        _runbook(summary.iloc[0], launches, checks),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "research_family_registration": registration.root,
        "research_family_registration_manifest": registration.root / "manifest.json",
    }
    if abandonment_source is not None:
        inputs["research_family_abandonments"] = abandonment_source
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "attest_abandonments": bool(attest_abandonments),
        },
        inputs=inputs,
        extra={
            "passed": passed,
            "family_id": registration.family_id,
            "registration_id": registration.registration_id,
            "study_count": int(len(launches)),
            "contract_ready_count": _bool_count(launches, "contract_ready"),
            "closure_covered_count": _bool_count(launches, "closure_covered"),
            "abandoned_count": int(
                launches.get("study_status", pd.Series(dtype=str))
                .astype(str)
                .eq("abandoned")
                .sum()
            ),
            "authorizes_submission": False,
        },
    )
    return ResearchFamilyLaunchReport(
        launches=launches,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
        output_dir=out,
    )


def _build_launches(
    registration: ResearchFamilyRegistrationSnapshot,
    *,
    abandonments: pd.DataFrame,
    attest_abandonments: bool,
    plan_root: Path,
    contract_dir: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, study in registration.studies.reset_index(drop=True).iterrows():
        label = str(study.get("study_label", "")).strip()
        sweeps, sweep_error = _json_string_list(
            study.get("sweep_paths_json"),
            field="sweep_paths_json",
        )
        group_cols, group_error = _json_string_list(
            study.get("group_cols_json"),
            field="group_cols_json",
        )
        sweep_labels, label_error = _optional_json_string_list(
            study.get("sweep_labels_json"),
            field="sweep_labels_json",
        )
        sweep_paths = [_resolve_path(value, plan_root) for value in sweeps]
        expected_sweeps = _int(study.get("development_sweeps")) + _int(
            study.get("holdout_sweeps")
        )
        sweep_count_matches = bool(
            expected_sweeps > 0 and len(sweep_paths) == expected_sweeps
        )
        sweep_paths_unique = bool(
            sweep_paths
            and len({_canonical_path(path) for path in sweep_paths})
            == len(sweep_paths)
        )
        group_cols_valid = bool(group_cols and len(set(group_cols)) == len(group_cols))
        sweep_labels_valid = bool(
            not sweep_labels
            or (
                len(sweep_labels) == len(sweep_paths)
                and len(set(sweep_labels)) == len(sweep_labels)
            )
        )
        sweep_current_count, sweep_errors = _sweep_integrity(sweep_paths)
        sweep_inputs_current = bool(
            sweep_paths and sweep_current_count == len(sweep_paths)
        )
        parse_error = ";".join(
            value for value in (sweep_error, group_error, label_error) if value
        )
        contract_valid = bool(
            not parse_error
            and sweep_count_matches
            and sweep_paths_unique
            and group_cols_valid
            and sweep_labels_valid
        )
        argv = _launch_argv(
            registration,
            study,
            sweep_paths=sweep_paths,
            group_cols=group_cols,
            sweep_labels=sweep_labels,
        )
        contract_payload = {
            "schema_version": 1,
            "family_id": registration.family_id,
            "registration_id": registration.registration_id,
            "registration_manifest_sha256": registration.manifest_sha256,
            "study": _record(study),
            "sweep_paths": [str(path) for path in sweep_paths],
            "group_cols": group_cols,
            "sweep_labels": sweep_labels,
            "argv": argv,
            "contract_valid": contract_valid,
            "authorizes_submission": False,
        }
        contract_id = _payload_sha256(contract_payload)
        contract_payload["contract_id"] = contract_id
        contract_path = contract_dir / (
            f"{index + 1:03d}_{_slug(label)}_{contract_id[:12]}.json"
        )
        contract_path.write_text(
            json.dumps(_jsonable(contract_payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = _result_evidence(registration, study)
        abandonment_matches = abandonments.loc[
            abandonments.get(
                "study_label",
                pd.Series("", index=abandonments.index),
            )
            .astype(str)
            .eq(label)
        ]
        abandonment_reason = (
            str(abandonment_matches.iloc[0].get("reason", "")).strip()
            if len(abandonment_matches) == 1
            else ""
        )
        abandonment_valid = bool(
            len(abandonment_matches) == 1
            and abandonment_reason
            and attest_abandonments
            and not result["result_exists"]
        )
        abandonment_conflict = bool(
            not abandonment_matches.empty and result["result_exists"]
        )
        if result["result_exists"]:
            status = (
                "completed_ready"
                if result["result_ready"]
                else "completed_blocked"
            )
        elif abandonment_valid:
            status = "abandoned"
        else:
            status = "never_launched"
        closure_covered = bool(
            (
                result["result_exists"]
                and result["result_manifest_current"]
                and result["result_registration_bound"]
                and not abandonment_conflict
            )
            or abandonment_valid
        )
        contract_ready = bool(
            contract_valid
            and sweep_inputs_current
            and registration.ready
            and registration.manifest_current
            and registration.registration_id_consistent
            and not result["result_exists"]
            and abandonment_matches.empty
        )
        rows.append(
            {
                "study_label": label,
                "strategy": str(study.get("strategy", "")),
                "market": str(study.get("market", "")),
                "planned_study_path": str(study.get("planned_study_path", "")),
                "primary_metric": str(study.get("primary_metric", "")),
                "max_scenarios": _int(study.get("max_scenarios")),
                "development_sweeps": _int(study.get("development_sweeps")),
                "holdout_sweeps": _int(study.get("holdout_sweeps")),
                "expected_sweep_count": expected_sweeps,
                "sweep_count": len(sweep_paths),
                "sweep_count_matches": sweep_count_matches,
                "sweep_paths_unique": sweep_paths_unique,
                "sweep_manifest_current_count": sweep_current_count,
                "sweep_inputs_current": sweep_inputs_current,
                "sweep_integrity_errors": ",".join(sweep_errors),
                "group_column_count": len(group_cols),
                "group_columns_valid": group_cols_valid,
                "sweep_labels_valid": sweep_labels_valid,
                "launch_spec_error": parse_error,
                "contract_valid": contract_valid,
                "contract_ready": contract_ready,
                "contract_id": contract_id,
                "contract_path": str(contract_path),
                "launch_argv_json": json.dumps(argv, separators=(",", ":")),
                "launch_command": subprocess.list2cmdline(argv),
                **result,
                "abandonment_declared": bool(len(abandonment_matches) == 1),
                "abandonment_reason": abandonment_reason,
                "abandonment_attested": bool(attest_abandonments),
                "abandonment_valid": abandonment_valid,
                "abandonment_conflict": abandonment_conflict,
                "study_status": status,
                "closure_covered": closure_covered,
                "registration_id": registration.registration_id,
                "registration_manifest_sha256": registration.manifest_sha256,
                "authorizes_submission": False,
            }
        )
    return pd.DataFrame(rows)


def _result_evidence(
    registration: ResearchFamilyRegistrationSnapshot,
    study: pd.Series,
) -> dict[str, Any]:
    root = Path(str(study.get("planned_study_path", ""))).resolve()
    summary_path = root / "robust_selection_pipeline_summary.csv"
    manifest_path = root / "manifest.json"
    if not summary_path.is_file():
        return {
            "result_exists": False,
            "result_ready": False,
            "result_manifest_current": False,
            "result_manifest_error": "result_summary_missing",
            "result_manifest_path": str(manifest_path),
            "result_registration_bound": False,
        }
    summary = pd.read_csv(summary_path)
    source = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type="robust_selection_pipeline",
        required_artifacts=(
            "robust_selection_pipeline_summary.csv",
            "robust_selection_pipeline_research_registration.csv",
        ),
        require_input_fingerprints=True,
    )
    manifest = _read_json_object(manifest_path)
    registration_input = _manifest_input(
        manifest,
        "research_family_registration_manifest",
    )
    bound = bool(
        _to_bool(source.get("research_registration_provided", False))
        and _to_bool(source.get("research_registration_passed", False))
        and str(source.get("research_registration_id", ""))
        == registration.registration_id
        and str(source.get("registered_study_label", ""))
        == str(study.get("study_label", ""))
        and str(source.get("research_registration_manifest_sha256", ""))
        == registration.manifest_sha256
        and str(registration_input.get("sha256", ""))
        == registration.manifest_sha256
        and _canonical_path(registration_input.get("path", ""))
        == _canonical_path(registration.root / "manifest.json")
    )
    return {
        "result_exists": True,
        "result_ready": _to_bool(source.get("ready", False)),
        "result_manifest_current": bool(integrity.passed),
        "result_manifest_error": str(integrity.error),
        "result_manifest_path": str(manifest_path),
        "result_registration_bound": bound,
    }


def _launch_argv(
    registration: ResearchFamilyRegistrationSnapshot,
    study: pd.Series,
    *,
    sweep_paths: list[Path],
    group_cols: list[str],
    sweep_labels: list[str],
) -> list[str]:
    argv = [
        "python",
        "-m",
        "hft_cli",
        "pipeline-robust-selection",
        "--sweeps",
        *[str(path) for path in sweep_paths],
        "--out",
        str(study.get("planned_study_path", "")),
        "--group-cols",
        *group_cols,
        "--strategy",
        str(study.get("strategy", "")),
        "--market",
        str(study.get("market", "")),
        "--holdout-sweeps",
        str(_int(study.get("holdout_sweeps"))),
        "--research-registration",
        str(registration.root),
        "--registered-study-label",
        str(study.get("study_label", "")),
        "--require-research-registration",
        "--fail-on-actions",
        "--fail-on-breach",
    ]
    for label in sweep_labels:
        argv.extend(["--label", label])
    return argv


def _checks(
    registration: ResearchFamilyRegistrationSnapshot,
    launches: pd.DataFrame,
    abandonments: pd.DataFrame,
    *,
    attest_abandonments: bool,
) -> pd.DataFrame:
    study_count = int(len(launches))
    registered_labels = set(registration.studies["study_label"].astype(str))
    abandonment_labels = set(
        abandonments.get("study_label", pd.Series(dtype=str)).astype(str)
    )
    abandonment_rows_valid = bool(
        abandonments.empty
        or (
            not abandonments["study_label"].astype(str).duplicated().any()
            and abandonment_labels.issubset(registered_labels)
            and abandonments["reason"].astype(str).str.strip().ne("").all()
        )
    )
    rows = [
        _check(
            "registration_ready",
            registration.ready,
            "is",
            True,
            registration.ready,
            "prospective registration did not pass",
        ),
        _check(
            "registration_manifest_current",
            registration.manifest_current,
            "is",
            True,
            registration.manifest_current,
            "registration artifacts or original plan input drifted",
        ),
        _check(
            "registration_id_consistent",
            registration.registration_id_consistent,
            "is",
            True,
            registration.registration_id_consistent,
            "registration ID differs across its locked artifacts",
        ),
        _numeric_check(
            "launch_rows",
            study_count,
            "==",
            int(len(registration.studies)),
            "launch matrix does not cover every registered row",
        ),
        _numeric_check(
            "valid_launch_contracts",
            _bool_count(launches, "contract_valid"),
            "==",
            study_count,
            "one or more registered rows lack a valid immutable launch contract",
        ),
        _check(
            "abandonment_rows_valid",
            abandonment_rows_valid,
            "is",
            True,
            abandonment_rows_valid,
            "abandonment labels must be unique, registered, and include a reason",
        ),
        _check(
            "abandonments_attested",
            bool(attest_abandonments or abandonments.empty),
            "is",
            True,
            bool(attest_abandonments or abandonments.empty),
            "operator must attest the supplied abandonment ledger",
        ),
        _numeric_check(
            "closure_coverage",
            _bool_count(launches, "closure_covered"),
            "==",
            study_count,
            "registered studies remain never launched or lack current bound evidence",
        ),
    ]
    return pd.DataFrame(rows)


def _summary(
    registration: ResearchFamilyRegistrationSnapshot,
    launches: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    *,
    passed: bool,
    attest_abandonments: bool,
) -> pd.DataFrame:
    status = launches.get("study_status", pd.Series(dtype=str)).astype(str)
    contract_ready_count = _bool_count(launches, "contract_ready")
    next_gate = (
        READY_NEXT_GATE
        if passed
        else (
            REPAIR_NEXT_GATE
            if _bool_count(launches, "contract_valid") < len(launches)
            else LAUNCH_NEXT_GATE
        )
    )
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "family_id": registration.family_id,
                "registration_id": registration.registration_id,
                "study_count": int(len(launches)),
                "valid_contract_count": _bool_count(launches, "contract_valid"),
                "contract_ready_count": contract_ready_count,
                "completed_ready_count": int(status.eq("completed_ready").sum()),
                "completed_blocked_count": int(status.eq("completed_blocked").sum()),
                "abandoned_count": int(status.eq("abandoned").sum()),
                "never_launched_count": int(status.eq("never_launched").sum()),
                "closure_covered_count": _bool_count(launches, "closure_covered"),
                "abandonments_attested": bool(attest_abandonments),
                "failed_checks": int((~checks["passed"].map(_to_bool)).sum()),
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "recommendation": (
                    "close_the_complete_registered_research_family"
                    if passed
                    else (
                        "execute_ready_contracts_or_attest_abandonments"
                        if contract_ready_count
                        else "repair_launch_contracts_or_source_evidence"
                    )
                ),
                "authorizes_submission": False,
            }
        ]
    )


def _action_queue(
    launches: pd.DataFrame,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for launch in launches.itertuples(index=False):
        if bool(launch.closure_covered):
            continue
        if not bool(launch.contract_valid):
            action = "repair_the_registered_launch_spec"
            next_gate = REPAIR_NEXT_GATE
        elif bool(launch.contract_ready):
            action = f"execute_contract_{launch.contract_id}"
            next_gate = LAUNCH_NEXT_GATE
        elif bool(launch.abandonment_declared) and not bool(launch.abandonment_valid):
            action = "attest_the_reasoned_abandonment_or_remove_the_ledger_row"
            next_gate = REPAIR_NEXT_GATE
        else:
            action = "restore_or_rerun_the_manifest_bound_registered_study"
            next_gate = LAUNCH_NEXT_GATE
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "source": RUN_TYPE,
                "component": str(launch.study_label),
                "check": "closure_covered",
                "actual": False,
                "operator": "is",
                "expected": True,
                "action": action,
                "reason": str(launch.study_status),
                "recommendation": action,
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
            }
        )
    failed = checks.loc[~checks["passed"].map(_to_bool)]
    for check in failed.itertuples(index=False):
        if str(check.check) == "closure_coverage" and rows:
            continue
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "source": RUN_TYPE,
                "component": "research_family_launch",
                "check": str(check.check),
                "actual": check.actual,
                "operator": check.operator,
                "expected": check.expected,
                "action": "repair_the_launch_matrix_evidence",
                "reason": str(check.reason),
                "recommendation": "repair_the_launch_matrix_evidence",
                "next_gate": REPAIR_NEXT_GATE,
                "next_gate_help_command": _help_command(REPAIR_NEXT_GATE),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _read_abandonments(
    raw_path: str | Path | None,
) -> tuple[pd.DataFrame, Path | None]:
    if raw_path is None:
        return pd.DataFrame(columns=ABANDONMENT_COLUMNS), None
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"research family abandonment ledger not found: {path}")
    frame = pd.read_csv(path)
    missing = [column for column in ABANDONMENT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"abandonment ledger missing columns: {missing}")
    return frame[list(ABANDONMENT_COLUMNS)].copy(), path


def _sweep_integrity(paths: list[Path]) -> tuple[int, list[str]]:
    current = 0
    errors: list[str] = []
    for index, path in enumerate(paths, start=1):
        integrity = verify_experiment_manifest(
            path / "manifest.json",
            required_artifacts=("sweep_runs.csv",),
            require_input_fingerprints=True,
        )
        if integrity.passed:
            current += 1
        else:
            errors.append(f"sweep_{index}:{integrity.error or 'invalid'}")
    return current, errors


def _json_string_list(value: Any, *, field: str) -> tuple[list[str], str]:
    text = "" if value is None or _is_na(value) else str(value).strip()
    if not text:
        return [], f"{field}_missing"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [], f"{field}_invalid_json"
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) and item.strip() for item in parsed
    ):
        return [], f"{field}_must_be_a_string_array"
    return [item.strip() for item in parsed], ""


def _optional_json_string_list(value: Any, *, field: str) -> tuple[list[str], str]:
    if value is None or _is_na(value) or not str(value).strip():
        return [], ""
    return _json_string_list(value, field=field)


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _manifest_input(payload: dict[str, Any], name: str) -> dict[str, Any]:
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        return {}
    value = inputs.get(name, {})
    return value if isinstance(value, dict) else {}


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _slug(value: str) -> str:
    slug = "".join(character if character.isalnum() else "_" for character in value)
    slug = "_".join(part for part in slug.split("_") if part)
    return slug.lower() or "study"


def _canonical_path(value: Any) -> str:
    text = str(value or "").strip()
    return str(Path(text).resolve()).casefold() if text else ""


def _bool_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    return int(frame[column].map(_to_bool).sum())


def _numeric_check(
    check: str,
    actual: int,
    operator: str,
    expected: int,
    reason: str,
) -> dict[str, Any]:
    passed = bool(
        (operator == "==" and actual == expected)
        or (operator == ">=" and actual >= expected)
    )
    return _check(check, actual, operator, expected, passed, reason)


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


def _runbook(
    summary: pd.Series,
    launches: pd.DataFrame,
    checks: pd.DataFrame,
) -> str:
    lines = [
        "# Research Family Launch Matrix",
        "",
        f"- Status: **{'closure covered' if bool(summary['passed']) else 'blocked'}**",
        f"- Family: `{summary['family_id']}`",
        f"- Registration ID: `{summary['registration_id']}`",
        f"- Studies: {int(summary['study_count'])}",
        f"- Closure covered: {int(summary['closure_covered_count'])}/{int(summary['study_count'])}",
        f"- Never launched: {int(summary['never_launched_count'])}",
        f"- Explicitly abandoned: {int(summary['abandoned_count'])}",
        f"- Next gate: `{summary['next_gate']}`",
        "- Authorizes submission: `false`",
        "",
        "## Study Contracts",
        "",
    ]
    for launch in launches.itertuples(index=False):
        lines.append(
            f"- `{launch.study_label}`: {launch.study_status}; contract "
            f"`{launch.contract_id}`; closure covered "
            f"`{str(bool(launch.closure_covered)).lower()}`"
        )
        if bool(launch.contract_ready):
            lines.append(f"  `{launch.launch_command}`")
    failed = checks.loc[~checks["passed"].map(_to_bool)]
    if not failed.empty:
        lines.extend(["", "## Blocking Checks", ""])
        for row in failed.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.reason}")
    lines.extend(
        [
            "",
            "Launch contracts run research and backtests only. They never authorize "
            "broker submission.",
        ]
    )
    return "\n".join(lines) + "\n"


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
    if _is_na(value):
        return None
    return value


def _is_na(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _int(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return int(number) if np.isfinite(number) else 0


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"
