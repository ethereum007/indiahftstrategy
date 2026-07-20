import json

import pandas as pd

from hft_cli import main
from reports.manifest import verify_experiment_manifest
from reports.walkforward_split_audit import (
    WalkForwardSplitAuditConfig,
    WalkForwardSplitAuditThresholds,
    evaluate_walk_forward_split_audit,
    load_walk_forward_split_audit,
    write_walk_forward_split_audit,
)


def labels_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": [0, 100, 200, 300, 400, 500, 600, 700],
            "label_end_ts": [50, 150, 410, 380, 450, 550, 650, 750],
            "target": [0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4],
        }
    )


def test_walkforward_split_audit_proves_past_only_purge_and_embargo():
    report = evaluate_walk_forward_split_audit(
        labels_frame(),
        config=WalkForwardSplitAuditConfig(
            n_splits=2,
            test_size=2,
            embargo_ns=50,
        ),
        thresholds=WalkForwardSplitAuditThresholds(
            min_train_rows=2,
            min_test_rows=2,
        ),
    )

    assert report.passed
    first_roles = report.assignments.loc[
        report.assignments["fold"] == 0,
        ["source_row", "role"],
    ].set_index("source_row")["role"]
    assert first_roles.to_dict() == {
        0: "train",
        1: "train",
        2: "purged",
        3: "embargoed",
        4: "test",
        5: "test",
        6: "future_excluded",
        7: "future_excluded",
    }
    assert list(report.folds["train_rows"]) == [2, 6]
    assert list(report.folds["test_rows"]) == [2, 2]
    assert int(report.summary.loc[0, "future_training_rows"]) == 0
    assert int(report.summary.loc[0, "overlapping_training_labels"]) == 0
    assert int(report.summary.loc[0, "total_purged_rows"]) == 1
    assert int(report.summary.loc[0, "total_embargoed_rows"]) == 1
    assert report.action_queue.empty
    assert not report.config["authorizes_submission"]


def test_walkforward_split_audit_blocks_equal_timestamp_test_boundaries():
    labels = pd.DataFrame(
        {
            "ts": [0, 100, 200, 200, 200, 300],
            "label_end_ts": [50, 150, 250, 250, 250, 350],
        }
    )

    report = evaluate_walk_forward_split_audit(
        labels,
        config=WalkForwardSplitAuditConfig(n_splits=2, test_size=2),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed == {"strictly_increasing_test_windows"}
    assert report.action_queue.loc[0, "next_gate"] == "audit-walkforward-splits"
    assert report.action_queue.loc[0, "recommendation"] == (
        "keep_equal_timestamps_inside_the_same_test_window"
    )


def test_write_walkforward_split_audit_outputs_manifest_bound_evidence(tmp_path):
    labels_path = tmp_path / "labels.csv"
    out_dir = tmp_path / "split_audit"
    labels_frame().to_csv(labels_path, index=False)

    report = write_walk_forward_split_audit(
        labels_path,
        output_dir=out_dir,
        config=WalkForwardSplitAuditConfig(
            n_splits=2,
            test_size=2,
            embargo_ns=50,
        ),
        thresholds=WalkForwardSplitAuditThresholds(
            min_train_rows=2,
            min_test_rows=2,
        ),
    )

    assert report.passed
    assert report.output_dir == out_dir
    expected = {
        "walkforward_split_assignments.csv",
        "walkforward_split_folds.csv",
        "walkforward_split_checks.csv",
        "walkforward_split_summary.csv",
        "walkforward_split_action_queue.csv",
        "walkforward_split_config.json",
        "walkforward_split_runbook.md",
        "manifest.json",
    }
    assert expected <= {path.name for path in out_dir.iterdir()}
    config = json.loads((out_dir / "walkforward_split_config.json").read_text(encoding="utf-8"))
    assert config["passed"]
    assert config["parameters"]["embargo_ns"] == 50
    assert config["next_gate"] == "pipeline-robust-selection"
    assert config["blocked_actions"] == []
    assert config["primary_action"] == {}
    assert not config["authorizes_submission"]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_type"] == "walkforward_split_audit"
    assert manifest["inputs"]["labels"]["sha256"]
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "walkforward_split_assignments.csv" in artifact_paths
    assert "walkforward_split_runbook.md" in artifact_paths
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="walkforward_split_audit",
        required_artifacts=tuple(sorted(expected - {"manifest.json"})),
        require_input_fingerprints=True,
    )
    assert integrity.passed
    snapshot = load_walk_forward_split_audit(out_dir)
    assert snapshot.passed
    assert snapshot.manifest_current
    assert snapshot.failed_check_names == ()
    assert snapshot.non_authorizing

    labels_path.write_text(
        labels_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    drifted = load_walk_forward_split_audit(out_dir / "manifest.json")
    assert not drifted.passed
    assert not drifted.manifest_current
    assert drifted.manifest_error == "input_drift"
    assert "manifest_current" in drifted.failed_check_names


def test_cli_walkforward_split_audit_returns_fail_closed_exit_codes(tmp_path):
    labels_path = tmp_path / "labels.csv"
    pass_dir = tmp_path / "pass"
    blocked_dir = tmp_path / "blocked"
    labels_frame().to_csv(labels_path, index=False)

    pass_code = main(
        [
            "audit-walkforward-splits",
            "--labels",
            str(labels_path),
            "--out",
            str(pass_dir),
            "--n-splits",
            "2",
            "--test-size",
            "2",
            "--embargo-ns",
            "50",
            "--min-train-rows",
            "2",
            "--min-test-rows",
            "2",
            "--fail-on-breach",
        ]
    )
    blocked_code = main(
        [
            "audit-walkforward-splits",
            "--labels",
            str(labels_path),
            "--out",
            str(blocked_dir),
            "--n-splits",
            "2",
            "--test-size",
            "2",
            "--embargo-ns",
            "50",
            "--min-train-rows",
            "3",
            "--fail-on-blocked-actions",
        ]
    )

    assert pass_code == 0
    assert blocked_code == 2
    blocked_summary = pd.read_csv(blocked_dir / "walkforward_split_summary.csv")
    blocked_queue = pd.read_csv(blocked_dir / "walkforward_split_action_queue.csv")
    assert not bool(blocked_summary.loc[0, "passed"])
    assert blocked_queue.loc[0, "check"] == "minimum_train_rows"
    assert blocked_queue.loc[0, "next_gate_help_command"] == (
        "python -m hft_cli audit-walkforward-splits --help"
    )
