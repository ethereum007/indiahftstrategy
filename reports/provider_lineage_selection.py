from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


PROVIDER_LINEAGE_SELECTION_CONTRACT_VERSION = "provider_active_lineage_selection/v1"

_SUMMARY_FIELDS = {
    "version": "route_readiness_ops_provider_lineage_selection_contract_version",
    "sha256": "route_readiness_ops_provider_lineage_selection_contract_sha256",
    "selected_run_count": "route_readiness_ops_provider_lineage_selected_run_count",
    "selected_pair_count": "route_readiness_ops_provider_lineage_selected_pair_count",
    "selected_pair_ids": "route_readiness_ops_provider_lineage_selected_pair_ids",
    "selected_run_dirs": "route_readiness_ops_provider_lineage_selected_run_dirs",
    "artifact": "route_readiness_ops_provider_lineage_selection_artifact",
}


def provider_lineage_selection_contract_from_summary(
    value: pd.DataFrame | pd.Series | Mapping[str, Any] | None,
) -> dict[str, Any]:
    record = _record(value)
    return normalize_provider_lineage_selection_contract(
        {key: record.get(field, "") for key, field in _SUMMARY_FIELDS.items()}
    )


def provider_lineage_selection_contract_from_config(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    config = _mapping(value)
    return normalize_provider_lineage_selection_contract(
        _mapping(config.get("provider_lineage_selection_contract"))
    )


def provider_lineage_selection_contract_from_manifest(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    manifest = _mapping(value)
    return provider_lineage_selection_contract_from_config(
        _mapping(manifest.get("extra"))
    )


def normalize_provider_lineage_selection_contract(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    contract = _mapping(value)
    return {
        "version": _text(contract.get("version")),
        "sha256": _text(contract.get("sha256")).lower(),
        "selected_run_count": _integer(contract.get("selected_run_count")),
        "selected_pair_count": _integer(contract.get("selected_pair_count")),
        "selected_pair_ids": ";".join(
            item.lower() for item in _semicolon_values(contract.get("selected_pair_ids"))
        ),
        "selected_run_dirs": ";".join(
            _semicolon_values(contract.get("selected_run_dirs"))
        ),
        "artifact": _text(contract.get("artifact")),
    }


def provider_lineage_selection_contract_valid(
    value: Mapping[str, Any] | None,
) -> bool:
    contract = normalize_provider_lineage_selection_contract(value)
    pair_ids = _semicolon_values(contract["selected_pair_ids"])
    run_dirs = _semicolon_values(contract["selected_run_dirs"])
    return bool(
        contract["version"] == PROVIDER_LINEAGE_SELECTION_CONTRACT_VERSION
        and _valid_sha256(contract["sha256"])
        and contract["selected_run_count"] == 3
        and contract["selected_pair_count"] == 3
        and len(pair_ids) == 3
        and len(set(pair_ids)) == 3
        and all(_valid_sha256(value) for value in pair_ids)
        and len(run_dirs) == 3
        and len(set(run_dirs)) == 3
        and contract["artifact"]
    )


def provider_lineage_selection_contracts_match(
    *values: Mapping[str, Any] | None,
) -> bool:
    contracts = [normalize_provider_lineage_selection_contract(value) for value in values]
    return bool(
        contracts
        and provider_lineage_selection_contract_valid(contracts[0])
        and all(contract == contracts[0] for contract in contracts[1:])
    )


def _record(
    value: pd.DataFrame | pd.Series | Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if isinstance(value, pd.DataFrame):
        return {} if value.empty else value.iloc[0]
    if isinstance(value, (pd.Series, Mapping)):
        return value
    return {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _semicolon_values(value: object) -> list[str]:
    return [item.strip() for item in _text(value).split(";") if item.strip()]


def _valid_sha256(value: object) -> bool:
    candidate = _text(value).lower()
    return len(candidate) == 64 and all(
        character in "0123456789abcdef" for character in candidate
    )


def _integer(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return int(number) if number.is_integer() else 0


def _text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
