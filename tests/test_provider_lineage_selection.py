import copy

import pandas as pd

from reports.provider_lineage_selection import (
    provider_lineage_selection_contract_from_config,
    provider_lineage_selection_contract_from_manifest,
    provider_lineage_selection_contract_from_summary,
    provider_lineage_selection_contract_valid,
    provider_lineage_selection_contracts_match,
)


def _contract():
    return {
        "version": "provider_active_lineage_selection/v1",
        "sha256": "a" * 64,
        "selected_run_count": 3,
        "selected_pair_count": 3,
        "selected_pair_ids": ";".join(("1" * 64, "2" * 64, "3" * 64)),
        "selected_run_dirs": "runs/ack;runs/roundtrip;runs/certificate",
        "artifact": "strategy_evidence_provider_lineage_selection.csv",
    }


def test_provider_lineage_selection_contract_normalizes_artifact_surfaces():
    contract = _contract()
    summary = pd.DataFrame(
        [
            {
                "route_readiness_ops_provider_lineage_selection_contract_version": contract[
                    "version"
                ],
                "route_readiness_ops_provider_lineage_selection_contract_sha256": contract[
                    "sha256"
                ],
                "route_readiness_ops_provider_lineage_selected_run_count": 3.0,
                "route_readiness_ops_provider_lineage_selected_pair_count": 3.0,
                "route_readiness_ops_provider_lineage_selected_pair_ids": contract[
                    "selected_pair_ids"
                ],
                "route_readiness_ops_provider_lineage_selected_run_dirs": contract[
                    "selected_run_dirs"
                ],
                "route_readiness_ops_provider_lineage_selection_artifact": contract[
                    "artifact"
                ],
            }
        ]
    )
    config = {"provider_lineage_selection_contract": contract}
    manifest = {"extra": config}

    assert provider_lineage_selection_contract_from_summary(summary) == contract
    assert provider_lineage_selection_contract_from_config(config) == contract
    assert provider_lineage_selection_contract_from_manifest(manifest) == contract


def test_provider_lineage_selection_contract_normalizes_route_readiness_origin_fields():
    contract = _contract()
    summary = pd.Series(
        {
            "provider_lineage_selection_contract_version": contract["version"],
            "provider_lineage_selection_contract_sha256": contract["sha256"],
            "provider_lineage_selected_run_count": contract["selected_run_count"],
            "provider_lineage_selected_pair_count": contract["selected_pair_count"],
            "provider_lineage_selected_pair_ids": contract["selected_pair_ids"],
            "provider_lineage_selected_run_dirs": contract["selected_run_dirs"],
            "provider_lineage_selection_artifact": contract["artifact"],
        }
    )

    assert provider_lineage_selection_contract_from_summary(summary) == contract


def test_provider_lineage_selection_contract_rejects_malformed_roster():
    contract = _contract()
    invalid_contracts = []
    for key, value in (
        ("version", "provider_active_lineage_selection/v0"),
        ("selected_run_count", 3.5),
        ("selected_pair_count", 2),
        ("selected_pair_ids", ";".join(("1" * 64, "1" * 64, "3" * 64))),
        ("selected_run_dirs", "runs/ack;runs/ack;runs/certificate"),
        ("artifact", ""),
    ):
        candidate = copy.deepcopy(contract)
        candidate[key] = value
        invalid_contracts.append(candidate)

    assert provider_lineage_selection_contract_valid(contract)
    assert all(
        not provider_lineage_selection_contract_valid(candidate)
        for candidate in invalid_contracts
    )


def test_provider_lineage_selection_contract_requires_cross_artifact_agreement():
    contract = _contract()
    drifted = copy.deepcopy(contract)
    drifted["sha256"] = "b" * 64

    assert provider_lineage_selection_contracts_match(contract, contract, contract)
    assert not provider_lineage_selection_contracts_match(contract, drifted, contract)
