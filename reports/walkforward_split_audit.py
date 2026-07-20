from __future__ import annotations

import json
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
from research.validation import PurgedSplit, purged_walk_forward_splits


RUN_TYPE = "walkforward_split_audit"
READY_NEXT_GATE = "pipeline-robust-selection"
REPAIR_NEXT_GATE = "audit-walkforward-splits"

REQUIRED_ARTIFACTS = (
    "walkforward_split_assignments.csv",
    "walkforward_split_folds.csv",
    "walkforward_split_checks.csv",
    "walkforward_split_summary.csv",
    "walkforward_split_action_queue.csv",
    "walkforward_split_config.json",
    "walkforward_split_runbook.md",
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
class WalkForwardSplitAuditConfig:
    time_col: str = "ts"
    label_end_col: str = "label_end_ts"
    n_splits: int = 3
    embargo_ns: int = 0
    test_size: int | None = None


@dataclass(frozen=True)
class WalkForwardSplitAuditThresholds:
    min_train_rows: int = 1
    min_test_rows: int = 1


@dataclass(frozen=True)
class WalkForwardSplitAuditReport:
    assignments: pd.DataFrame
    folds: pd.DataFrame
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
class WalkForwardSplitAuditSnapshot:
    root: Path
    manifest_path: Path
    summary: dict[str, Any]
    config: dict[str, Any]
    manifest: dict[str, Any]
    checks: pd.DataFrame
    folds: pd.DataFrame
    action_queue: pd.DataFrame
    passed: bool
    manifest_current: bool
    manifest_error: str
    manifest_sha256: str
    manifest_artifact_count: int
    manifest_artifact_match_count: int
    manifest_input_count: int
    manifest_input_match_count: int
    non_authorizing: bool
    failed_check_names: tuple[str, ...]


def evaluate_walk_forward_split_audit(
    labels: pd.DataFrame,
    *,
    config: WalkForwardSplitAuditConfig | None = None,
    thresholds: WalkForwardSplitAuditThresholds | None = None,
) -> WalkForwardSplitAuditReport:
    config = config or WalkForwardSplitAuditConfig()
    thresholds = thresholds or WalkForwardSplitAuditThresholds()
    _validate_thresholds(thresholds)
    source = labels.reset_index(drop=True)
    splits = purged_walk_forward_splits(
        source,
        time_col=config.time_col,
        label_end_col=config.label_end_col,
        n_splits=config.n_splits,
        embargo_ns=config.embargo_ns,
        test_size=config.test_size,
    )
    starts = pd.to_numeric(source[config.time_col], errors="raise").astype("int64")
    ends = pd.to_numeric(source[config.label_end_col], errors="raise").astype("int64")
    assignments = _assignments(labels.index, starts, ends, splits)
    folds = _folds(starts, ends, splits, config=config)
    checks = _checks(assignments, folds, config=config, thresholds=thresholds)
    action_queue = _action_queue(checks)
    summary = _summary(labels, folds, checks, action_queue)
    blocked_actions = [_record(row) for _, row in action_queue.iterrows()]
    primary_action = blocked_actions[0] if blocked_actions else {}
    payload = {
        "schema_version": 1,
        "passed": bool(summary.iloc[0]["passed"]),
        "ready": bool(summary.iloc[0]["passed"]),
        "parameters": asdict(config),
        "thresholds": asdict(thresholds),
        "summary": _record(summary.iloc[0]),
        "action_count": int(len(action_queue)),
        "ready_action_count": 0,
        "blocked_action_count": int(len(action_queue)),
        "next_gate": str(summary.iloc[0]["next_gate"]),
        "next_gate_help_command": str(summary.iloc[0]["next_gate_help_command"]),
        "primary_action_status": "blocked" if blocked_actions else "",
        "primary_action": primary_action,
        "next_actions": blocked_actions,
        "ready_actions": [],
        "blocked_actions": blocked_actions,
        "authorizes_submission": False,
    }
    return WalkForwardSplitAuditReport(
        assignments=assignments,
        folds=folds,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=payload,
    )


def write_walk_forward_split_audit(
    labels_path: str | Path,
    *,
    output_dir: str | Path,
    config: WalkForwardSplitAuditConfig | None = None,
    thresholds: WalkForwardSplitAuditThresholds | None = None,
) -> WalkForwardSplitAuditReport:
    path = Path(labels_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"walk-forward labels CSV not found: {path}")
    config = config or WalkForwardSplitAuditConfig()
    thresholds = thresholds or WalkForwardSplitAuditThresholds()
    labels = pd.read_csv(path)
    report = evaluate_walk_forward_split_audit(
        labels,
        config=config,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.assignments.to_csv(out / "walkforward_split_assignments.csv", index=False)
    report.folds.to_csv(out / "walkforward_split_folds.csv", index=False)
    report.checks.to_csv(out / "walkforward_split_checks.csv", index=False)
    report.summary.to_csv(out / "walkforward_split_summary.csv", index=False)
    report.action_queue.to_csv(out / "walkforward_split_action_queue.csv", index=False)
    payload = dict(report.config)
    payload["labels_path"] = str(path)
    (out / "walkforward_split_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "walkforward_split_runbook.md").write_text(
        _runbook(report.summary.iloc[0], report.folds, report.checks, report.action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "thresholds": asdict(thresholds),
        },
        inputs={"labels": path},
        extra={
            "passed": bool(report.passed),
            "authorizes_submission": False,
        },
    )
    return WalkForwardSplitAuditReport(
        assignments=report.assignments,
        folds=report.folds,
        checks=report.checks,
        summary=report.summary,
        action_queue=report.action_queue,
        config=payload,
        output_dir=out,
    )


def load_walk_forward_split_audit(
    audit_path: str | Path,
) -> WalkForwardSplitAuditSnapshot:
    raw = Path(audit_path).resolve()
    if raw.name == "manifest.json":
        root = raw.parent
        manifest_path = raw
    else:
        root = raw
        manifest_path = root / "manifest.json"
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    manifest = _read_json_object(manifest_path)
    config = _read_json_object(root / "walkforward_split_config.json")
    summary_frame = pd.read_csv(root / "walkforward_split_summary.csv")
    checks = pd.read_csv(root / "walkforward_split_checks.csv")
    folds = pd.read_csv(root / "walkforward_split_folds.csv")
    action_queue = pd.read_csv(root / "walkforward_split_action_queue.csv")
    if len(summary_frame) != 1:
        raise ValueError("walk-forward split audit summary must contain one row")

    summary = _record(summary_frame.iloc[0])
    manifest_extra = manifest.get("extra", {})
    manifest_extra = manifest_extra if isinstance(manifest_extra, dict) else {}
    checks_passed = bool(
        not checks.empty
        and "passed" in checks.columns
        and checks["passed"].map(_to_bool).all()
    )
    folds_passed = bool(
        not folds.empty
        and "passed" in folds.columns
        and folds["passed"].map(_to_bool).all()
    )
    leakage_metrics_zero = bool(
        _int(summary.get("future_training_rows")) == 0
        and _int(summary.get("overlapping_training_labels")) == 0
        and _int(summary.get("embargo_breach_rows")) == 0
    )
    non_authorizing = bool(
        "authorizes_submission" in summary
        and not _to_bool(summary.get("authorizes_submission", True))
        and "authorizes_submission" in config
        and not _to_bool(config.get("authorizes_submission", True))
        and "authorizes_submission" in manifest_extra
        and not _to_bool(manifest_extra.get("authorizes_submission", True))
    )
    validations = {
        "manifest_current": bool(integrity.passed),
        "summary_passed": _to_bool(summary.get("passed", False)),
        "summary_ready": _to_bool(summary.get("ready", False)),
        "config_passed": _to_bool(config.get("passed", False)),
        "config_ready": _to_bool(config.get("ready", False)),
        "manifest_declares_pass": _to_bool(
            manifest_extra.get("passed", False)
        ),
        "checks_passed": checks_passed,
        "folds_passed": folds_passed,
        "leakage_metrics_zero": leakage_metrics_zero,
        "no_blocked_actions": bool(
            action_queue.empty
            and _int(summary.get("blocked_action_count")) == 0
        ),
        "non_authorizing": non_authorizing,
    }
    failed = tuple(name for name, value in validations.items() if not value)
    return WalkForwardSplitAuditSnapshot(
        root=root,
        manifest_path=manifest_path,
        summary=summary,
        config=config,
        manifest=manifest,
        checks=checks,
        folds=folds,
        action_queue=action_queue,
        passed=not failed,
        manifest_current=bool(integrity.passed),
        manifest_error=str(integrity.error),
        manifest_sha256=(
            file_sha256(manifest_path) if manifest_path.is_file() else ""
        ),
        manifest_artifact_count=int(integrity.artifact_count),
        manifest_artifact_match_count=int(integrity.artifact_match_count),
        manifest_input_count=int(integrity.input_fingerprint_count),
        manifest_input_match_count=int(
            integrity.input_fingerprint_match_count
        ),
        non_authorizing=non_authorizing,
        failed_check_names=failed,
    )


def _assignments(
    source_index: pd.Index,
    starts: pd.Series,
    ends: pd.Series,
    splits: list[PurgedSplit],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    index_values = [str(value) for value in source_index]
    for split in splits:
        roles = np.full(len(starts), "future_excluded", dtype=object)
        roles[_positions(split.train_index)] = "train"
        roles[_positions(split.purged_index)] = "purged"
        roles[_positions(split.embargoed_index)] = "embargoed"
        roles[_positions(split.test_index)] = "test"
        for source_row, role in enumerate(roles):
            rows.append(
                {
                    "fold": int(split.fold),
                    "source_row": int(source_row),
                    "source_index": index_values[source_row],
                    "ts": int(starts.iloc[source_row]),
                    "label_end_ts": int(ends.iloc[source_row]),
                    "role": str(role),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["fold", "source_row", "source_index", "ts", "label_end_ts", "role"],
    )


def _folds(
    starts: pd.Series,
    ends: pd.Series,
    splits: list[PurgedSplit],
    *,
    config: WalkForwardSplitAuditConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for split in splits:
        train = _positions(split.train_index)
        test = _positions(split.test_index)
        train_starts = starts.iloc[train]
        train_ends = ends.iloc[train]
        test_starts = starts.iloc[test]
        future_training_rows = int((train_starts >= split.test_start_ts).sum())
        overlapping_training_labels = int((train_ends >= split.test_start_ts).sum())
        embargo_breach_rows = 0
        if config.embargo_ns:
            embargo_breach_rows = int(
                (train_ends > split.test_start_ts - config.embargo_ns).sum()
            )
        rows.append(
            {
                "fold": int(split.fold),
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "purged_rows": int(len(split.purged_index)),
                "embargoed_rows": int(len(split.embargoed_index)),
                "train_start_ts": _minimum(train_starts),
                "train_last_start_ts": _maximum(train_starts),
                "train_last_label_end_ts": _maximum(train_ends),
                "test_start_ts": int(split.test_start_ts),
                "test_last_start_ts": _maximum(test_starts),
                "test_end_ts": int(split.test_end_ts),
                "future_training_rows": future_training_rows,
                "overlapping_training_labels": overlapping_training_labels,
                "embargo_breach_rows": embargo_breach_rows,
                "passed": bool(
                    future_training_rows == 0
                    and overlapping_training_labels == 0
                    and embargo_breach_rows == 0
                ),
            }
        )
    return pd.DataFrame(rows)


def _checks(
    assignments: pd.DataFrame,
    folds: pd.DataFrame,
    *,
    config: WalkForwardSplitAuditConfig,
    thresholds: WalkForwardSplitAuditThresholds,
) -> pd.DataFrame:
    fold_count = int(len(folds))
    min_train_rows = int(folds["train_rows"].min()) if not folds.empty else 0
    min_test_rows = int(folds["test_rows"].min()) if not folds.empty else 0
    future_training_rows = _sum(folds, "future_training_rows")
    overlapping_training_labels = _sum(folds, "overlapping_training_labels")
    embargo_breach_rows = _sum(folds, "embargo_breach_rows")
    test_assignments = assignments.loc[assignments["role"] == "test", "source_row"]
    duplicate_test_assignments = int(test_assignments.duplicated().sum())
    test_starts = folds["test_start_ts"].astype("int64").tolist() if not folds.empty else []
    increasing_test_windows = all(
        later > earlier for earlier, later in zip(test_starts, test_starts[1:])
    )
    train_counts = folds["train_rows"].astype("int64").tolist() if not folds.empty else []
    expanding_training_windows = all(
        later >= earlier for earlier, later in zip(train_counts, train_counts[1:])
    )
    rows = [
        _check(
            "fold_count",
            fold_count,
            "==",
            config.n_splits,
            fold_count == config.n_splits,
            "the requested number of temporal folds was not produced",
        ),
        _check(
            "minimum_train_rows",
            min_train_rows,
            ">=",
            thresholds.min_train_rows,
            min_train_rows >= thresholds.min_train_rows,
            "one or more folds lack the required past-only training history",
        ),
        _check(
            "minimum_test_rows",
            min_test_rows,
            ">=",
            thresholds.min_test_rows,
            min_test_rows >= thresholds.min_test_rows,
            "one or more folds lack the required contiguous test observations",
        ),
        _check(
            "future_training_rows",
            future_training_rows,
            "==",
            0,
            future_training_rows == 0,
            "future observations entered one or more training folds",
        ),
        _check(
            "overlapping_training_labels",
            overlapping_training_labels,
            "==",
            0,
            overlapping_training_labels == 0,
            "training labels overlap a test boundary",
        ),
        _check(
            "embargo_breach_rows",
            embargo_breach_rows,
            "==",
            0,
            embargo_breach_rows == 0,
            "training labels enter the configured pre-test embargo",
        ),
        _check(
            "duplicate_test_assignments",
            duplicate_test_assignments,
            "==",
            0,
            duplicate_test_assignments == 0,
            "a source observation appears in more than one test fold",
        ),
        _check(
            "strictly_increasing_test_windows",
            int(increasing_test_windows),
            "==",
            1,
            increasing_test_windows,
            "test folds do not advance through strictly later timestamps",
        ),
        _check(
            "expanding_training_windows",
            int(expanding_training_windows),
            "==",
            1,
            expanding_training_windows,
            "training history shrinks between successive walk-forward folds",
        ),
    ]
    return pd.DataFrame(rows)


def _summary(
    labels: pd.DataFrame,
    folds: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    passed = bool(not checks.empty and checks["passed"].astype(bool).all())
    next_gate = READY_NEXT_GATE if passed else REPAIR_NEXT_GATE
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "ready": passed,
                "source_rows": int(len(labels)),
                "fold_count": int(len(folds)),
                "min_train_rows": int(folds["train_rows"].min()) if not folds.empty else 0,
                "min_test_rows": int(folds["test_rows"].min()) if not folds.empty else 0,
                "total_purged_rows": _sum(folds, "purged_rows"),
                "total_embargoed_rows": _sum(folds, "embargoed_rows"),
                "future_training_rows": _sum(folds, "future_training_rows"),
                "overlapping_training_labels": _sum(folds, "overlapping_training_labels"),
                "embargo_breach_rows": _sum(folds, "embargo_breach_rows"),
                "failed_checks": int((~checks["passed"].astype(bool)).sum()),
                "action_count": int(len(action_queue)),
                "blocked_action_count": int(len(action_queue)),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "recommendation": (
                    "use_manifest_bound_splits_for_model_research"
                    if passed
                    else "repair_temporal_split_contract_before_model_selection"
                ),
                "authorizes_submission": False,
            }
        ]
    )


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    rows = []
    for priority, row in enumerate(failed.itertuples(index=False), start=1):
        recommendation = _recommendation(str(row.check))
        rows.append(
            {
                "priority": priority,
                "queue_status": "blocked",
                "source": RUN_TYPE,
                "component": "temporal_split",
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
    if check in {"minimum_train_rows", "minimum_test_rows", "fold_count"}:
        return "supply_more_ordered_labels_or_reduce_split_count"
    if check == "strictly_increasing_test_windows":
        return "keep_equal_timestamps_inside_the_same_test_window"
    if check == "duplicate_test_assignments":
        return "regenerate_disjoint_contiguous_test_windows"
    return "regenerate_past_only_purged_and_embargoed_walkforward_splits"


def _runbook(
    summary: pd.Series,
    folds: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Walk-Forward Split Audit",
        "",
        f"- Status: **{'passed' if bool(summary['passed']) else 'blocked'}**",
        f"- Source rows: {int(summary['source_rows'])}",
        f"- Folds: {int(summary['fold_count'])}",
        f"- Minimum train/test rows: {int(summary['min_train_rows'])}/{int(summary['min_test_rows'])}",
        f"- Purged/embargoed assignments: {int(summary['total_purged_rows'])}/{int(summary['total_embargoed_rows'])}",
        f"- Future training rows: {int(summary['future_training_rows'])}",
        f"- Overlapping training labels: {int(summary['overlapping_training_labels'])}",
        f"- Next gate: `{summary['next_gate']}`",
        "- Authorizes submission: `false`",
        "",
        (
            "Training windows expand through historical observations only. Labels "
            "that reach a test boundary are purged, and the configured duration gap "
            "is applied before each test fold."
        ),
    ]
    if not folds.empty:
        lines.extend(["", "## Folds", ""])
        for row in folds.itertuples(index=False):
            lines.append(
                f"- Fold {int(row.fold)}: train={int(row.train_rows)}, "
                f"test={int(row.test_rows)}, purged={int(row.purged_rows)}, "
                f"embargoed={int(row.embargoed_rows)}"
            )
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    if not failed.empty:
        lines.extend(["", "## Blocking Checks", ""])
        for row in failed.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.reason}")
    if not action_queue.empty:
        lines.extend(["", "## Actions", ""])
        for row in action_queue.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.recommendation}")
    return "\n".join(lines) + "\n"


def _positions(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=int)


def _minimum(values: pd.Series) -> int | None:
    return int(values.min()) if not values.empty else None


def _maximum(values: pd.Series) -> int | None:
    return int(values.max()) if not values.empty else None


def _sum(frame: pd.DataFrame, column: str) -> int:
    return int(pd.to_numeric(frame.get(column, pd.Series(dtype=float)), errors="coerce").fillna(0).sum())


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


def _validate_thresholds(thresholds: WalkForwardSplitAuditThresholds) -> None:
    if thresholds.min_train_rows <= 0:
        raise ValueError("min_train_rows must be positive")
    if thresholds.min_test_rows <= 0:
        raise ValueError("min_test_rows must be positive")


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help"


def _record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return payload


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


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    return value
