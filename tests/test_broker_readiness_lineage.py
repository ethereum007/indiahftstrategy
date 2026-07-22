import json

import pandas as pd

import reports.operational_lineage as operational_lineage
from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS,
    broker_dispatch_roundtrip_lineage_fields,
    empty_broker_dispatch_roundtrip_lineage,
    load_broker_readiness_lineage,
)


def _roundtrip_lineage(manifest_sha256, manifest_path):
    state = empty_broker_dispatch_roundtrip_lineage(required=True)
    state.update(
        {
            "provided": True,
            "manifest_current": True,
            "manifest_run_type": "broker_dispatch_roundtrip",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "manifest_error": "",
            "contract_consistent": True,
            "contract_error": "",
            "non_authorizing": True,
            "ack_lineage_gate_passed": True,
            "ack_matches_current": True,
            "expected_ack_matches_current": True,
            "gate_passed": True,
        }
    )
    return state


def _write_readiness_bundle(root, roundtrip_config, roundtrip_state):
    root.mkdir(parents=True, exist_ok=True)
    lineage = broker_dispatch_roundtrip_lineage_fields(roundtrip_state)
    retained = {
        field: lineage[field]
        for field in BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS
    }
    pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": "arrow_money",
                "failed_checks": 0,
                **retained,
            }
        ]
    ).to_csv(root / "broker_readiness_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "component": "dispatch_roundtrip",
                "required": True,
                "provided": True,
                "ready": True,
                **retained,
            }
        ]
    ).to_csv(root / "broker_readiness_items.csv", index=False)
    pd.DataFrame(
        [
            {
                "check": "dispatch_roundtrip_ready",
                "passed": True,
                "value": True,
                "operator": "is",
                "threshold": True,
                "reason": "",
            }
        ]
    ).to_csv(root / "broker_readiness_checks.csv", index=False)
    pd.DataFrame(
        [
            {
                "priority": 1,
                "queue_status": "ready",
                "check": "dispatch_roundtrip_ready",
                "next_gate": "review-broker-readiness",
            }
        ]
    ).to_csv(root / "broker_readiness_action_queue.csv", index=False)
    config = {
        "ready": True,
        "adapter": "arrow_money",
        "component_counts": {"failed_checks": 0},
        "dispatch_roundtrip": {
            "lineage": {
                field.removeprefix("broker_dispatch_roundtrip_"): value
                for field, value in retained.items()
            }
        },
    }
    (root / "broker_readiness_config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "broker_readiness_runbook.md").write_text(
        "# Broker readiness\n\nReview-only evidence bundle.\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        root,
        run_type="broker_readiness",
        inputs={"dispatch_roundtrip_config": roundtrip_config},
        extra={"ready": True, **retained},
    )


def test_broker_readiness_lineage_reopens_current_roundtrip_after_remanifest(
    tmp_path,
    monkeypatch,
):
    roundtrip = tmp_path / "roundtrip"
    roundtrip.mkdir()
    roundtrip_config = roundtrip / "broker_dispatch_roundtrip_config.json"
    roundtrip_config.write_text('{"revision": 1}\n', encoding="utf-8")
    original = _roundtrip_lineage("a" * 64, roundtrip / "manifest.json")
    readiness = tmp_path / "readiness"
    _write_readiness_bundle(readiness, roundtrip_config, original)
    monkeypatch.setattr(
        operational_lineage,
        "load_broker_dispatch_roundtrip_lineage",
        lambda _path: original,
    )

    accepted = load_broker_readiness_lineage(
        readiness / "broker_readiness_config.json"
    )

    assert accepted["manifest_current"]
    assert accepted["contract_consistent"]
    assert accepted["roundtrip_lineage_gate_passed"]
    assert accepted["roundtrip_matches_current"]
    assert accepted["gate_passed"]

    roundtrip_config.write_text('{"revision": 2}\n', encoding="utf-8")
    _write_readiness_bundle(readiness, roundtrip_config, original)
    detached = _roundtrip_lineage("b" * 64, roundtrip / "manifest.json")
    monkeypatch.setattr(
        operational_lineage,
        "load_broker_dispatch_roundtrip_lineage",
        lambda _path: detached,
    )

    rejected = load_broker_readiness_lineage(
        readiness / "broker_readiness_config.json"
    )

    assert rejected["manifest_current"]
    assert rejected["roundtrip_lineage_gate_passed"]
    assert not rejected["roundtrip_matches_current"]
    assert not rejected["contract_consistent"]
    assert not rejected["gate_passed"]
    assert (
        "roundtrip_broker_dispatch_roundtrip_manifest_sha256_mismatch"
        in rejected["contract_error"]
    )


def test_broker_readiness_lineage_cannot_downgrade_manifest_bound_roundtrip(
    tmp_path,
    monkeypatch,
):
    roundtrip = tmp_path / "roundtrip"
    roundtrip.mkdir()
    roundtrip_config = roundtrip / "broker_dispatch_roundtrip_config.json"
    roundtrip_config.write_text('{"revision": 1}\n', encoding="utf-8")
    current = _roundtrip_lineage("a" * 64, roundtrip / "manifest.json")
    readiness = tmp_path / "readiness"
    _write_readiness_bundle(readiness, roundtrip_config, current)
    field = "broker_dispatch_roundtrip_lineage_required"

    for name in ("broker_readiness_summary.csv", "broker_readiness_items.csv"):
        path = readiness / name
        frame = pd.read_csv(path).drop(columns=[field])
        frame.to_csv(path, index=False)
    config_path = readiness / "broker_readiness_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["dispatch_roundtrip"]["lineage"].pop("lineage_required")
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads((readiness / "manifest.json").read_text(encoding="utf-8"))
    extra = dict(manifest["extra"])
    extra.pop(field)
    write_experiment_manifest(
        readiness,
        run_type="broker_readiness",
        inputs={"dispatch_roundtrip_config": roundtrip_config},
        extra=extra,
    )
    monkeypatch.setattr(
        operational_lineage,
        "load_broker_dispatch_roundtrip_lineage",
        lambda _path: current,
    )

    rejected = load_broker_readiness_lineage(
        readiness / "broker_readiness_config.json"
    )

    assert rejected["manifest_current"]
    assert rejected["roundtrip_lineage_required"]
    assert rejected["roundtrip_lineage_gate_passed"]
    assert not rejected["roundtrip_matches_current"]
    assert not rejected["contract_consistent"]
    assert not rejected["gate_passed"]
    assert f"roundtrip_{field}_missing:summary" in rejected["contract_error"]
    assert f"roundtrip_{field}_missing:items" in rejected["contract_error"]
    assert f"roundtrip_{field}_missing:config" in rejected["contract_error"]
    assert f"roundtrip_{field}_missing:manifest" in rejected["contract_error"]


def test_broker_readiness_lineage_threshold_prevents_roundtrip_source_removal(
    tmp_path,
):
    roundtrip = tmp_path / "roundtrip"
    roundtrip.mkdir()
    roundtrip_config = roundtrip / "broker_dispatch_roundtrip_config.json"
    roundtrip_config.write_text('{"revision": 1}\n', encoding="utf-8")
    current = _roundtrip_lineage("a" * 64, roundtrip / "manifest.json")
    readiness = tmp_path / "readiness"
    _write_readiness_bundle(readiness, roundtrip_config, current)

    summary_path = readiness / "broker_readiness_summary.csv"
    summary = pd.read_csv(summary_path).drop(
        columns=list(BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS),
    )
    summary.to_csv(summary_path, index=False)
    items_path = readiness / "broker_readiness_items.csv"
    items = pd.read_csv(items_path).drop(
        columns=list(BROKER_READINESS_ROUNDTRIP_LINEAGE_FIELDS),
    )
    items[["required", "provided", "ready"]] = False
    items.to_csv(items_path, index=False)
    config_path = readiness / "broker_readiness_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["dispatch_roundtrip"] = {}
    config["thresholds"] = {"require_dispatch_roundtrip": True}
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    neutral_source = tmp_path / "readiness_source.csv"
    neutral_source.write_text("ready\ntrue\n", encoding="utf-8")
    write_experiment_manifest(
        readiness,
        run_type="broker_readiness",
        inputs={"broker_readiness_source": neutral_source},
        extra={"ready": True},
    )

    rejected = load_broker_readiness_lineage(config_path)

    assert rejected["manifest_current"]
    assert rejected["roundtrip_lineage_required"]
    assert not rejected["roundtrip_lineage_gate_passed"]
    assert not rejected["roundtrip_matches_current"]
    assert not rejected["contract_consistent"]
    assert not rejected["gate_passed"]
    assert (
        "roundtrip_config_missing_from_manifest"
        in rejected["contract_error"]
    )
