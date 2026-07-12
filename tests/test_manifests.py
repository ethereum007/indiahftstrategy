import json

import pandas as pd

from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


def test_write_experiment_manifest_hashes_inputs_and_artifacts(tmp_path):
    input_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "run"
    input_path.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")
    out_dir.mkdir()
    pd.DataFrame([{"net_pnl": 1.0}]).to_csv(out_dir / "summary.csv", index=False)

    manifest_path = write_experiment_manifest(
        out_dir,
        run_type="unit_test_run",
        parameters={"threshold": 1.5},
        inputs={"ticks": input_path},
        extra={"note": "manifest smoke"},
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_type"] == "unit_test_run"
    assert manifest["parameters"]["threshold"] == 1.5
    assert manifest["inputs"]["ticks"]["sha256"] == file_sha256(input_path)
    assert manifest["artifacts"][0]["path"] == "summary.csv"
    assert manifest["artifacts"][0]["sha256"] == file_sha256(out_dir / "summary.csv")
    assert manifest["environment"]["python"]


def test_verify_experiment_manifest_checks_artifacts_and_inputs(tmp_path):
    source = tmp_path / "ticks.csv"
    output = tmp_path / "run"
    source.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")
    output.mkdir()
    (output / "summary.csv").write_text("passed\ntrue\n", encoding="utf-8")
    manifest = write_experiment_manifest(
        output,
        run_type="unit_test_run",
        inputs={"ticks": source},
    )

    current = verify_experiment_manifest(
        manifest,
        expected_run_type="unit_test_run",
        required_artifacts=("summary.csv",),
        require_input_fingerprints=True,
    )

    assert current.passed
    assert current.artifact_match_count == 1
    assert current.required_artifact_match_count == 1
    assert current.input_fingerprint_match_count == 1

    (output / "summary.csv").write_text("passed\nfalse\n", encoding="utf-8")
    artifact_drift = verify_experiment_manifest(manifest)
    assert not artifact_drift.passed
    assert artifact_drift.error == "artifact_drift"

    write_experiment_manifest(
        output,
        run_type="unit_test_run",
        inputs={"ticks": source},
    )
    source.write_text("ts,bid,ask\n1,99,102\n", encoding="utf-8")
    input_drift = verify_experiment_manifest(
        manifest,
        require_input_fingerprints=True,
    )
    assert not input_drift.passed
    assert input_drift.error == "input_drift"

    write_experiment_manifest(
        output,
        run_type="unit_test_run",
        inputs={"ticks": source},
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"][0].update(
        {
            "path": "../ticks.csv",
            "size_bytes": source.stat().st_size,
            "sha256": file_sha256(source),
        }
    )
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    escaped_artifact = verify_experiment_manifest(manifest)
    assert not escaped_artifact.passed
    assert escaped_artifact.error == "artifact_drift"


def test_verify_experiment_manifest_fails_missing_or_wrong_run_type(tmp_path):
    missing = verify_experiment_manifest(tmp_path / "missing" / "manifest.json")
    assert not missing.passed
    assert missing.error == "manifest_missing"

    output = tmp_path / "run"
    output.mkdir()
    (output / "summary.csv").write_text("passed\ntrue\n", encoding="utf-8")
    manifest = write_experiment_manifest(output, run_type="actual")
    mismatch = verify_experiment_manifest(
        manifest,
        expected_run_type="expected",
    )
    assert not mismatch.passed
    assert mismatch.error == "run_type_mismatch"


def test_write_experiment_manifest_excludes_dynamic_artifact_tree(tmp_path):
    output = tmp_path / "run"
    executions = output / "executions"
    executions.mkdir(parents=True)
    (output / "summary.csv").write_text("passed\ntrue\n", encoding="utf-8")
    attempt = executions / "attempt.json"
    attempt.write_text('{"attempt": 1}\n', encoding="utf-8")

    manifest_path = write_experiment_manifest(
        output,
        run_type="unit_test_run",
        artifact_exclude_paths=("executions",),
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert [item["path"] for item in payload["artifacts"]] == ["summary.csv"]
    attempt.write_text('{"attempt": 2}\n', encoding="utf-8")
    assert verify_experiment_manifest(manifest_path).passed


def test_manifest_dependency_paths_flattens_nested_manifests(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    (child / "summary.csv").write_text("ready\ntrue\n", encoding="utf-8")
    child_manifest = write_experiment_manifest(
        child,
        run_type="child",
        inputs={"source": source},
    )
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "summary.csv").write_text("ready\ntrue\n", encoding="utf-8")
    parent_manifest = write_experiment_manifest(
        parent,
        run_type="parent",
        inputs={"child": child, "child_manifest": child_manifest},
    )

    dependencies = set(manifest_dependency_paths(parent_manifest))

    assert dependencies == {
        child.resolve(),
        child_manifest.resolve(),
        source.resolve(),
    }
