from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def build_robust_selection_semantics(
    *,
    sweep_paths: list[str | Path],
    labels: list[str] | None,
    group_cols: list[str],
    strategy: str,
    market: str,
    selection: dict[str, Any],
    overfit_config: dict[str, Any],
    overfit_thresholds: dict[str, Any],
    significance_config: dict[str, Any],
    significance_thresholds: dict[str, Any],
    holdout_sweeps: int,
    holdout_config: dict[str, Any],
    holdout_thresholds: dict[str, Any],
    promotion_thresholds: dict[str, Any],
    walkforward_split_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    split_audit = {
        "path": "",
        "required": False,
        "manifest_sha256": "",
    }
    split_audit.update(walkforward_split_audit or {})
    semantics = {
        "schema_version": 1,
        "sweep_paths": [str(Path(path).resolve()) for path in sweep_paths],
        "labels": [str(value) for value in (labels or [])],
        "group_cols": [str(value) for value in group_cols],
        "strategy": str(strategy),
        "market": str(market),
        "selection": _jsonable(selection),
        "overfit_config": _jsonable(overfit_config),
        "overfit_thresholds": _jsonable(overfit_thresholds),
        "significance_config": _jsonable(significance_config),
        "significance_thresholds": _jsonable(significance_thresholds),
        "holdout_sweeps": int(holdout_sweeps),
        "holdout_config": _jsonable(holdout_config),
        "holdout_thresholds": _jsonable(holdout_thresholds),
        "promotion_thresholds": _jsonable(promotion_thresholds),
        "authorizes_submission": False,
    }
    if any(
        (
            str(split_audit["path"]),
            bool(split_audit["required"]),
            str(split_audit["manifest_sha256"]),
        )
    ):
        semantics["walkforward_split_audit"] = _jsonable(split_audit)
    return semantics


def semantic_digest(parameters: dict[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(parameters),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def argv_digest(argv: list[str]) -> str:
    encoded = json.dumps(
        [str(value) for value in argv],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
