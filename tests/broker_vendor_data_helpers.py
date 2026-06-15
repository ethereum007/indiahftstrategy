import json

import pandas as pd


def assert_broker_vendor_data_proof_forwarded(output_dir, *, readiness_subdir="06_broker_readiness"):
    broker_manifest = json.loads((output_dir / readiness_subdir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(broker_manifest["inputs"]["vendor_market_data_batch_config"]["path"]).endswith(
        "/broker_vendor_data/01_vendor_market_data_batch/vendor_market_data_batch_config.json"
    )
    assert path_tail(broker_manifest["inputs"]["vendor_market_data_batch_manifest"]["path"]).endswith(
        "/broker_vendor_data/01_vendor_market_data_batch/manifest.json"
    )
    pipeline_manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(pipeline_manifest["parameters"]["config"]["broker_vendor_data_readiness_dir"]).endswith(
        "/broker_vendor_data"
    )


def assert_broker_vendor_data_adapter_mismatch_blocked(
    output_dir,
    *,
    summary_file,
    components_file,
    readiness_subdir="06_broker_readiness",
    proof_adapter="irage",
):
    summary = pd.read_csv(output_dir / summary_file)
    components = pd.read_csv(output_dir / components_file)
    checks = pd.read_csv(output_dir / readiness_subdir / "broker_readiness_checks.csv")
    broker_summary = pd.read_csv(output_dir / readiness_subdir / "broker_readiness_summary.csv")

    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert not bool(summary.loc[0, "ready"])
    assert components.set_index("component").loc["broker_readiness", "status"] == "not_ready"
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
    } <= failed
    assert broker_summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_adapter"] == proof_adapter
    assert broker_summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == proof_adapter
    assert_broker_vendor_data_proof_forwarded(output_dir, readiness_subdir=readiness_subdir)


def path_tail(value):
    return str(value).replace("\\", "/")


def write_broker_vendor_data_proof(path, *, adapter="arrow_money"):
    batch_dir = path / "01_vendor_market_data_batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "vendor_market_data_batch_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "provided": True,
                "adapter": adapter,
                "kind": "ticks",
                "market": "india_nse_index_derivatives",
                "dataset_count": 2,
                "ready_datasets": 2,
                "failed_datasets": 0,
                "ready_rate": 1.0,
                "unique_source_files": 2,
                "unique_header_fingerprints": 1,
                "mapping_sources": "vendor_intake_draft",
                "comparison": {"accepted": True, "failed_checks": 0},
                "datasets": [
                    {
                        "dataset": "day1",
                        "ready": True,
                        "source_file_sha256": "a" * 64,
                        "source_header_sha256": "b" * 64,
                        "mapping_draft_sha256": "c" * 64,
                        "mapping_source": "vendor_intake_draft",
                    },
                    {
                        "dataset": "day2",
                        "ready": True,
                        "source_file_sha256": "d" * 64,
                        "source_header_sha256": "b" * 64,
                        "mapping_draft_sha256": "c" * 64,
                        "mapping_source": "vendor_intake_draft",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (batch_dir / "manifest.json").write_text(
        json.dumps({"run_type": "vendor_market_data_batch_pipeline"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (path / "broker_vendor_data_readiness_config.json").write_text(
        json.dumps({"ready": True, "adapter": adapter}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
