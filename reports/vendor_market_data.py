from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def vendor_market_data_batch_source_active(vendor: Mapping[str, Any] | None) -> bool:
    if not vendor:
        return False
    return bool(
        _to_bool(vendor.get("provided", False))
        or int(_number_value(vendor.get("dataset_count"), 0.0)) > 0
        or _identity_key(vendor.get("adapter", ""))
        or _identity_key(vendor.get("market", ""))
    )


def select_vendor_market_data_batch_source(
    config: Mapping[str, Any],
    candidates: Sequence[str],
    *,
    default_source: str | None = None,
) -> tuple[dict[str, Any], str]:
    for field_prefix in candidates:
        vendor = config.get(field_prefix, {}) or {}
        if isinstance(vendor, Mapping) and vendor_market_data_batch_source_active(vendor):
            return dict(vendor), field_prefix
    fallback = default_source if default_source is not None else (candidates[-1] if candidates else "")
    return {}, fallback


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    if value is None:
        return False
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def _number_value(value: object, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(fallback)
    return float(fallback) if math.isnan(parsed) else parsed


def _identity_key(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text.lower().replace("-", "_").replace(" ", "_").replace(".", "_")
