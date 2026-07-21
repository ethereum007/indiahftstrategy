from __future__ import annotations

import re
from typing import Any, Mapping

import numpy as np


def edge_audit(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    value = candidate.get("edge_audit", {}) if candidate else {}
    return value if isinstance(value, dict) else {}


def edge_metrics(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    value = edge_audit(candidate).get("metrics", {})
    return value if isinstance(value, dict) else {}


def edge_latency_budget_ns(candidate: Mapping[str, Any] | None) -> float:
    audit = edge_audit(candidate)
    value = audit.get("max_profitable_latency_ns")
    if value is None:
        value = edge_metrics(candidate).get("max_profitable_latency_ns")
    budget = number(value)
    return budget if np.isfinite(budget) and budget >= 0 else np.nan


def edge_audit_bound(candidate: Mapping[str, Any] | None) -> bool:
    audit = edge_audit(candidate)
    return bool(
        audit
        and _to_bool(audit.get("passed", False))
        and _to_bool(audit.get("measurement_manifest_current", False))
        and str(audit.get("measurement_manifest_sha256", "")).strip()
        and not np.isnan(edge_latency_budget_ns(candidate))
    )


def edge_candidate_manifest(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if not candidate:
        return {}
    value = candidate.get("edge_candidate_manifest", {})
    if isinstance(value, dict) and value:
        return value
    value = candidate.get("replay_walkforward", {})
    return value if isinstance(value, dict) else {}


def edge_candidate_manifest_bound(candidate: Mapping[str, Any] | None) -> bool:
    value = edge_candidate_manifest(candidate)
    sha256 = str(value.get("edge_candidate_manifest_sha256", "")).strip()
    return bool(
        _to_bool(value.get("edge_candidate_manifest_required", False))
        and _to_bool(value.get("edge_candidate_manifest_current", False))
        and re.fullmatch(r"[0-9a-fA-F]{64}", sha256)
    )


def replay_latency_ns(replay_params: Mapping[str, Any]) -> float:
    feed_latency_us = number(replay_params.get("feed_latency_us"))
    order_latency_us = number(replay_params.get("order_latency_us"))
    if np.isnan(feed_latency_us) or np.isnan(order_latency_us):
        return np.nan
    total = (feed_latency_us + order_latency_us) * 1_000.0
    return float(total) if total >= 0 else np.nan


def candidate_replay_latency_ns(candidate: Mapping[str, Any]) -> float:
    walkforward = candidate.get("replay_walkforward", {})
    if isinstance(walkforward, dict):
        total = number(walkforward.get("total_replay_latency_ns"))
        if np.isfinite(total) and total >= 0:
            return total
    replay_defaults = candidate.get("replay_defaults", {})
    if not isinstance(replay_defaults, dict):
        return np.nan
    return replay_latency_ns(replay_defaults)


def latency_budget_respected(candidate: Mapping[str, Any]) -> bool:
    if not edge_audit_bound(candidate):
        return False
    total = candidate_replay_latency_ns(candidate)
    budget = edge_latency_budget_ns(candidate)
    return bool(not np.isnan(total) and total <= budget)


def latency_headroom_ns(candidate: Mapping[str, Any]) -> float:
    total = candidate_replay_latency_ns(candidate)
    budget = edge_latency_budget_ns(candidate)
    if np.isnan(total) or np.isnan(budget):
        return np.nan
    return float(budget - total)


def number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    return result if np.isfinite(result) else np.nan


def _to_bool(value: Any) -> bool:
    if value is None:
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
    try:
        if np.isnan(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)
