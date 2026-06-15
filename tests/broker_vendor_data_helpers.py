import json


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
