from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from reports.data_readiness import DATA_READINESS_RUN_TYPE
from reports.manifest import write_experiment_manifest


def write_manifest_bound_data_readiness(
    path: str | Path,
    summary: Mapping[str, object],
    *,
    source_text: str = "value\n1\n",
) -> Path:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    ready = bool(summary.get("ready", False))
    pd.DataFrame([dict(summary)]).to_csv(
        root / "data_readiness_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [{"component": "vendor_intake", "required": True, "ready": ready}]
    ).to_csv(root / "data_readiness_items.csv", index=False)
    pd.DataFrame(
        [{"check": "vendor_intake_ready", "passed": ready}]
    ).to_csv(root / "data_readiness_checks.csv", index=False)
    pd.DataFrame(columns=["priority", "check", "next_gate"]).to_csv(
        root / "data_readiness_action_queue.csv",
        index=False,
    )
    (root / "data_readiness_config.json").write_text(
        json.dumps({"ready": ready}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "data_readiness_runbook.md").write_text(
        "# Data Readiness Runbook\n",
        encoding="utf-8",
    )
    source = root.parent / f"{root.name}_raw.csv"
    source.write_text(source_text, encoding="utf-8")
    write_experiment_manifest(
        root,
        run_type=DATA_READINESS_RUN_TYPE,
        inputs={"source": source},
    )
    return source
