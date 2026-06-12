import json

import pandas as pd

from reports.manifest import file_sha256, write_experiment_manifest


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
