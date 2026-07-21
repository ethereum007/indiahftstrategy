from __future__ import annotations

from math import isclose, isfinite, nan
from typing import Any

from reports.evidence import (
    LEADLAG_EDGE_LINEAGE_CONTRACT_VERSION,
    LEADLAG_EDGE_LINEAGE_RUN_TYPES,
)


LEADLAG_LINEAGE_BOOLEAN_FIELDS = ("leadlag_edge_lineage_ready",)
LEADLAG_LINEAGE_INTEGER_FIELDS = (
    "leadlag_lineage_bound_stages",
    "leadlag_lineage_required_stages",
    "leadlag_lineage_selected_stage_count",
)
LEADLAG_LINEAGE_TEXT_FIELDS = (
    "leadlag_lineage_selected_run_dirs",
    "leadlag_measurement_manifest_sha256",
    "leadlag_edge_candidate_manifest_sha256",
    "leadlag_edge_lineage_contract_version",
    "leadlag_edge_lineage_contract_sha256",
)
LEADLAG_LINEAGE_NUMERIC_FIELDS = (
    "leadlag_edge_latency_budget_ns",
    "leadlag_total_replay_latency_ns",
    "leadlag_edge_latency_headroom_ns",
)
LEADLAG_LINEAGE_FIELDS = (
    *LEADLAG_LINEAGE_BOOLEAN_FIELDS,
    *LEADLAG_LINEAGE_INTEGER_FIELDS,
    *LEADLAG_LINEAGE_TEXT_FIELDS,
    *LEADLAG_LINEAGE_NUMERIC_FIELDS,
)


def leadlag_lineage_fields(
    source: Any,
    *,
    source_prefix: str = "",
    target_prefix: str = "",
) -> dict[str, Any]:
    getter = source.get if hasattr(source, "get") else lambda _key, default: default

    def value(field: str, default: Any) -> Any:
        return getter(f"{source_prefix}{field}", default)

    fields: dict[str, Any] = {
        "leadlag_edge_lineage_ready": _to_bool(
            value("leadlag_edge_lineage_ready", False)
        ),
        "leadlag_lineage_bound_stages": _integer(
            value("leadlag_lineage_bound_stages", 0)
        ),
        "leadlag_lineage_required_stages": _integer(
            value("leadlag_lineage_required_stages", 0)
        ),
        "leadlag_lineage_selected_stage_count": _integer(
            value("leadlag_lineage_selected_stage_count", 0)
        ),
        "leadlag_lineage_selected_run_dirs": _text(
            value("leadlag_lineage_selected_run_dirs", "")
        ),
        "leadlag_measurement_manifest_sha256": _text(
            value("leadlag_measurement_manifest_sha256", "")
        ),
        "leadlag_edge_candidate_manifest_sha256": _text(
            value("leadlag_edge_candidate_manifest_sha256", "")
        ),
        "leadlag_edge_lineage_contract_version": _text(
            value("leadlag_edge_lineage_contract_version", "")
        ),
        "leadlag_edge_lineage_contract_sha256": _text(
            value("leadlag_edge_lineage_contract_sha256", "")
        ),
        "leadlag_edge_latency_budget_ns": _number(
            value("leadlag_edge_latency_budget_ns", nan)
        ),
        "leadlag_total_replay_latency_ns": _number(
            value("leadlag_total_replay_latency_ns", nan)
        ),
        "leadlag_edge_latency_headroom_ns": _number(
            value("leadlag_edge_latency_headroom_ns", nan)
        ),
    }
    return {
        f"{target_prefix}{field}": field_value
        for field, field_value in fields.items()
    }


def leadlag_lineage_ready(source: Any, *, prefix: str = "") -> bool:
    fields = leadlag_lineage_fields(source, source_prefix=prefix)
    expected_stages = len(LEADLAG_EDGE_LINEAGE_RUN_TYPES)
    run_dirs = [
        item.strip()
        for item in fields["leadlag_lineage_selected_run_dirs"].split(";")
        if item.strip()
    ]
    budget = fields["leadlag_edge_latency_budget_ns"]
    replay = fields["leadlag_total_replay_latency_ns"]
    headroom = fields["leadlag_edge_latency_headroom_ns"]
    return bool(
        fields["leadlag_edge_lineage_ready"]
        and fields["leadlag_lineage_bound_stages"] == expected_stages
        and fields["leadlag_lineage_required_stages"] == expected_stages
        and fields["leadlag_lineage_selected_stage_count"] == expected_stages
        and len(run_dirs) == expected_stages
        and len(set(run_dirs)) == expected_stages
        and _valid_sha256(fields["leadlag_measurement_manifest_sha256"])
        and _valid_sha256(fields["leadlag_edge_candidate_manifest_sha256"])
        and fields["leadlag_edge_lineage_contract_version"]
        == LEADLAG_EDGE_LINEAGE_CONTRACT_VERSION
        and _valid_sha256(fields["leadlag_edge_lineage_contract_sha256"])
        and isfinite(budget)
        and isfinite(replay)
        and isfinite(headroom)
        and budget > 0.0
        and replay >= 0.0
        and headroom >= 0.0
        and isclose(budget - replay, headroom, rel_tol=0.0, abs_tol=1e-9)
    )


def leadlag_lineage_field_matches(
    field: str,
    actual: Any,
    expected: Any,
) -> bool:
    if field in LEADLAG_LINEAGE_BOOLEAN_FIELDS:
        return _to_bool(actual) == _to_bool(expected)
    if field in LEADLAG_LINEAGE_INTEGER_FIELDS:
        return _integer(actual) == _integer(expected)
    if field in LEADLAG_LINEAGE_NUMERIC_FIELDS:
        actual_number = _number(actual)
        expected_number = _number(expected)
        return bool(
            isfinite(actual_number)
            and isfinite(expected_number)
            and isclose(
                actual_number,
                expected_number,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
    return _text(actual) == _text(expected)


def _valid_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


def _integer(value: Any) -> int:
    number = _number(value)
    return int(number) if isfinite(number) else 0


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return nan
    return number if isfinite(number) else nan


def _text(value: Any) -> str:
    if _missing(value):
        return ""
    return str(value).strip()


def _to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "passed",
            "ready",
        }
    if _missing(value):
        return False
    return bool(value)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False
