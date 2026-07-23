from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from reports.data_readiness import (
    DataReadinessThresholds,
    write_data_readiness_report,
)
from reports.manifest import write_experiment_manifest


def reseal_experiment_manifest(path: str | Path) -> dict[str, object]:
    root = Path(path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def source_value(value):
        if isinstance(value, list):
            return [source_value(item) for item in value]
        if isinstance(value, Mapping):
            if value.get("kind") in {"file", "directory"}:
                return value["path"]
            return {
                str(name): source_value(item)
                for name, item in value.items()
            }
        return value

    write_experiment_manifest(
        root,
        run_type=manifest["run_type"],
        parameters=manifest["parameters"],
        inputs={
            name: source_value(value)
            for name, value in manifest["inputs"].items()
        },
        extra=manifest["extra"],
    )
    return manifest


def write_manifest_bound_data_readiness(
    path: str | Path,
    summary: Mapping[str, object],
    *,
    source_text: str = "value\n1\n",
    market_calendar_dir: str | Path | None = None,
) -> Path:
    root = Path(path)
    vendor_root = root.parent / f"{root.name}_vendor_intake"
    vendor_root.mkdir(parents=True, exist_ok=True)
    ready = bool(summary.get("ready", False))
    source = vendor_root / "raw.csv"
    source.write_text(source_text, encoding="utf-8")
    vendor_summary = {
        "ready": ready,
        "adapter": "arrow_money",
        "best_kind": "ticks",
        "kind_selection": "explicit",
        "selected_kind_ambiguous": False,
        "ambiguous_kinds": "",
        "sampled_rows": 100,
        "source_columns": 7,
        "required_columns": 7,
        "mapped_columns": 7 if ready else 6,
        "unmapped_required_columns": 0 if ready else 1,
        "mapping_coverage": summary.get(
            "vendor_intake_mapping_coverage",
            1.0 if ready else 6 / 7,
        ),
        "failed_checks": summary.get(
            "failed_checks",
            0 if ready else 1,
        ),
        "source_file_sha256": summary.get(
            "vendor_intake_source_file_sha256",
            "",
        ),
        "source_file_size_bytes": len(source_text.encode("utf-8")),
        "source_header_sha256": summary.get(
            "vendor_intake_source_header_sha256",
            "",
        ),
        "mapping_draft_sha256": summary.get(
            "vendor_intake_mapping_draft_sha256",
            "",
        ),
        "recommendation": (
            "review_mapping_then_normalize"
            if ready
            else "complete_vendor_mapping_before_research"
        ),
    }
    if market_calendar_dir is not None:
        calendar = pd.read_csv(
            Path(market_calendar_dir) / "market_calendar_summary.csv"
        ).iloc[0]
        for column in (
            "market",
            "market_calendar_provided",
            "market_calendar_policy",
            "market_calendar_id",
            "market_calendar_sha256",
            "market_calendar_valid_from",
            "market_calendar_valid_to",
        ):
            vendor_summary[column] = calendar.get(column, "")
    pd.DataFrame([vendor_summary]).to_csv(
        vendor_root / "vendor_intake_summary.csv",
        index=False,
    )
    write_data_readiness_report(
        output_dir=root,
        market_calendar_dir=market_calendar_dir,
        vendor_intake_dir=vendor_root,
        thresholds=DataReadinessThresholds(
            require_market_calendar=market_calendar_dir is not None,
            require_vendor_intake=True,
            require_tick_diagnostics=False,
        ),
    )
    return source
