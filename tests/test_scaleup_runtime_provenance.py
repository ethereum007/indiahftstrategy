import json
from pathlib import Path

import pandas as pd

from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.operational_lineage import (
    broker_readiness_lineage_fields,
    broker_readiness_lineage_manifest_inputs,
    load_broker_readiness_lineage,
)
from reports.runtime_guard import write_runtime_guard_report
from reports.runtime_telemetry import write_runtime_telemetry_snapshot
from reports.scaleup import ScaleUpThresholds, write_scaleup_plan
from reports.scaleup_runtime_provenance import load_scaleup_runtime_provenance
from tests.data_readiness_helpers import reseal_experiment_manifest


def _write_broker_readiness_bundle(root):
    from adapters.broker_readiness import (
        BrokerReadinessThresholds,
        write_broker_readiness_report,
    )
    from tests.test_broker_readiness import write_broker_readiness_input_dirs

    schema, export, upload, roundtrip = write_broker_readiness_input_dirs(
        root.parent / "broker_readiness_sources",
        "arrow_money",
        verified_roundtrip=True,
    )
    report = write_broker_readiness_report(
        output_dir=root,
        schema_audit_dir=schema,
        order_export_dir=export,
        upload_pack_dir=upload,
        dispatch_roundtrip_dir=roundtrip,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )
    assert report.ready
    lineage = load_broker_readiness_lineage(
        root / "broker_readiness_config.json"
    )
    assert lineage["gate_passed"]
    return lineage


def _write_scaleup_bundle(root, broker_lineage):
    root.mkdir(parents=True)
    lineage_fields = broker_readiness_lineage_fields(broker_lineage)
    config = {
        "schema_version": 1,
        "ready": True,
        "authorizes_submission": False,
        "failed_check_count": 0,
        "target_mode": "shadow",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "identity": {
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "expected_strategy": "lead_lag_taker",
            "expected_market": "india_nse_index_derivatives",
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "pre_portfolio_max_notional_per_session": 100_000.0,
            "max_scale_multiplier": 1.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": {
            "max_total_failed_component_checks": 0,
            "max_total_unmatched_fills": 0,
            "max_total_mismatched_orders": 0,
            "max_total_overfilled_orders": 0,
            "max_worst_adverse_slippage": 0.05,
        },
        "broker_readiness": {
            "required": True,
            "provided": True,
            "ready": True,
            "lineage": {
                field.removeprefix("broker_readiness_"): value
                for field, value in lineage_fields.items()
            },
        },
    }
    core = {
        "ready": True,
        "authorizes_submission": False,
        "target_mode": "shadow",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "max_orders_per_session": 10,
        "max_notional_per_session": 100_000.0,
        "pre_portfolio_max_notional_per_session": 100_000.0,
        **lineage_fields,
    }
    (root / "scaleup_config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame([core]).to_csv(root / "scaleup_summary.csv", index=False)
    pd.DataFrame([core]).to_csv(root / "scaleup_plan.csv", index=False)
    pd.DataFrame(
        [{"check": "scaleup_ready", "passed": True, "reason": ""}]
    ).to_csv(root / "scaleup_checks.csv", index=False)
    source = root.parent / "scaleup_source.csv"
    pd.DataFrame([{"source": "fixture"}]).to_csv(source, index=False)
    inputs = {
        "source": source,
        "broker_readiness_config": Path(broker_lineage["manifest_path"]).parent
        / "broker_readiness_config.json",
        **broker_readiness_lineage_manifest_inputs(broker_lineage),
    }
    write_experiment_manifest(
        root,
        run_type="scaleup_plan",
        inputs=inputs,
        extra={"ready": True, "authorizes_submission": False, **lineage_fields},
    )
    return root


def _write_optional_broker_scaleup_bundle(root, broker_input):
    root.mkdir(parents=True)
    config = {
        "schema_version": 1,
        "ready": True,
        "authorizes_submission": False,
        "failed_check_count": 0,
        "target_mode": "shadow",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "pre_portfolio_max_notional_per_session": 100_000.0,
        },
        "broker_readiness": {
            "required": False,
            "provided": False,
            "lineage": {},
        },
    }
    core = {
        "ready": True,
        "authorizes_submission": False,
        "target_mode": "shadow",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "max_orders_per_session": 10,
        "max_notional_per_session": 100_000.0,
        "pre_portfolio_max_notional_per_session": 100_000.0,
    }
    config_path = root / "scaleup_config.json"
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame([core]).to_csv(root / "scaleup_summary.csv", index=False)
    pd.DataFrame([core]).to_csv(root / "scaleup_plan.csv", index=False)
    pd.DataFrame(
        [{"check": "scaleup_ready", "passed": True, "reason": ""}]
    ).to_csv(root / "scaleup_checks.csv", index=False)
    source = root.parent / "optional_scaleup_source.csv"
    pd.DataFrame([{"source": "fixture"}]).to_csv(source, index=False)
    manifest_path = write_experiment_manifest(
        root,
        run_type="scaleup_plan",
        inputs={
            "source": source,
            "broker_readiness_config": broker_input,
        },
        extra={"ready": True, "authorizes_submission": False},
    )
    if broker_input is None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["inputs"]["broker_readiness_config"] = None
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return config_path


def _write_proof_refresh_scaleup_bundle(root):
    from tests.test_scaleup_plan import (
        write_inputs,
        write_proof_refresh_bundle,
    )

    inputs_root = root.parent / f"{root.name}_inputs"
    evidence, shadow, launch, _ = write_inputs(inputs_root)
    proof_refresh, proof_source = write_proof_refresh_bundle(
        inputs_root / "proof_refresh"
    )
    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        proof_refresh_dir=proof_refresh,
        output_dir=root,
        thresholds=ScaleUpThresholds(
            require_proof_refresh=True,
        ),
    )
    assert report.ready
    return root, proof_refresh, proof_source


def test_scaleup_runtime_ignores_null_optional_broker_readiness_input(
    tmp_path,
):
    config_path = _write_optional_broker_scaleup_bundle(
        tmp_path / "scaleup",
        None,
    )

    provenance = load_scaleup_runtime_provenance(config_path)

    assert provenance["manifest_current"]
    assert provenance["contract_consistent"], provenance["contract_error"]
    assert provenance["non_authorizing"]
    assert provenance["source_ready"]
    assert provenance["broker_readiness_matches_current"]
    assert provenance["provenance_gate_passed"]


def test_scaleup_runtime_keeps_deleted_broker_fingerprint_active(
    tmp_path,
):
    broker_config = tmp_path / "broker_readiness_config.json"
    broker_config.write_text("{}\n", encoding="utf-8")
    config_path = _write_optional_broker_scaleup_bundle(
        tmp_path / "scaleup",
        broker_config,
    )
    broker_config.unlink()

    provenance = load_scaleup_runtime_provenance(config_path)

    assert not provenance["manifest_current"]
    assert not provenance["contract_consistent"]
    assert not provenance["broker_readiness_matches_current"]
    assert not provenance["provenance_gate_passed"]
    assert (
        "scaleup_broker_readiness_source_missing"
        in provenance["contract_error"]
    )


def _manifest_input_values(value):
    if isinstance(value, list):
        return [_manifest_input_values(item) for item in value]
    if isinstance(value, dict) and value.get("path"):
        return value["path"]
    return value


def _refresh_scaleup_manifest(manifest_path, *, extra_updates=None):
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    write_experiment_manifest(
        manifest_path.parent,
        run_type=payload["run_type"],
        parameters=payload.get("parameters", {}),
        inputs={
            name: _manifest_input_values(value)
            for name, value in payload.get("inputs", {}).items()
        },
        extra={**payload.get("extra", {}), **(extra_updates or {})},
    )


def _tamper_carried_broker_manifest_sha(scaleup_dir, fake_sha):
    config_path = scaleup_dir / "scaleup_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["broker_readiness"]["lineage"]["manifest_sha256"] = fake_sha
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name in ("scaleup_summary.csv", "scaleup_plan.csv"):
        path = scaleup_dir / name
        frame = pd.read_csv(path)
        frame.loc[0, "broker_readiness_manifest_sha256"] = fake_sha
        frame.to_csv(path, index=False)
    _refresh_scaleup_manifest(
        scaleup_dir / "manifest.json",
        extra_updates={"broker_readiness_manifest_sha256": fake_sha},
    )


def test_runtime_retains_current_scaleup_proof_refresh_lineage(tmp_path):
    scaleup_dir, proof_refresh, _ = (
        _write_proof_refresh_scaleup_bundle(
            tmp_path / "scaleup"
        )
    )

    provenance = load_scaleup_runtime_provenance(
        scaleup_dir / "scaleup_config.json"
    )
    telemetry = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        output_dir=tmp_path / "telemetry",
        snapshot_ts_ns=1_000,
    )
    guard = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry.output_dir,
        output_dir=tmp_path / "guard",
    )

    refresh_sha = file_sha256(proof_refresh / "manifest.json")
    telemetry_row = telemetry.summary.iloc[0]
    guard_row = guard.summary.iloc[0]
    assert provenance["manifest_current"]
    assert provenance["contract_consistent"], provenance["contract_error"]
    assert provenance["proof_refresh_active"]
    assert provenance["proof_refresh_required"]
    assert provenance["proof_refresh_requested"]
    assert provenance["proof_refresh_verified"]
    assert provenance["proof_refresh_manifest_current"]
    assert provenance["proof_refresh_manifest_sha256"] == refresh_sha
    assert provenance["proof_refresh_semantically_verified"]
    assert provenance["proof_refresh_source_manifest_current"]
    assert provenance["proof_refresh_source_manifest_sha256"] == refresh_sha
    assert provenance["proof_refresh_source_semantically_verified"]
    assert provenance["proof_refresh_source_provenance_gate_passed"]
    assert provenance["proof_refresh_matches_current"]
    assert provenance["provenance_gate_passed"]
    assert telemetry.ready
    assert telemetry_row["scaleup_proof_refresh_matches_current"]
    assert (
        telemetry_row["scaleup_proof_refresh_manifest_sha256"]
        == refresh_sha
    )
    assert not guard.halted
    assert guard_row[
        "runtime_telemetry_proof_refresh_provenance_gate_passed"
    ]
    assert guard_row[
        "runtime_telemetry_proof_refresh_matches_current"
    ]
    assert guard_row["runtime_telemetry_lineage_matches_current"]


def test_runtime_rejects_resealed_proof_refresh_semantic_drift(tmp_path):
    scaleup_dir, proof_refresh, _ = (
        _write_proof_refresh_scaleup_bundle(
            tmp_path / "scaleup"
        )
    )
    refresh_summary_path = (
        proof_refresh / "proof_refresh_summary.csv"
    )
    refresh_summary = pd.read_csv(refresh_summary_path)
    refresh_summary.loc[0, "proof_source"] = "latest"
    refresh_summary.to_csv(refresh_summary_path, index=False)
    reseal_experiment_manifest(proof_refresh)
    refresh_sha = file_sha256(proof_refresh / "manifest.json")

    scaleup_config_path = scaleup_dir / "scaleup_config.json"
    scaleup_config = json.loads(
        scaleup_config_path.read_text(encoding="utf-8")
    )
    scaleup_config["proof_freshness"]["manifest"]["sha256"] = (
        refresh_sha
    )
    scaleup_config_path.write_text(
        json.dumps(scaleup_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name in ("scaleup_summary.csv", "scaleup_plan.csv"):
        path = scaleup_dir / name
        frame = pd.read_csv(path)
        frame.loc[0, "proof_refresh_manifest_sha256"] = refresh_sha
        frame.to_csv(path, index=False)
    _refresh_scaleup_manifest(
        scaleup_dir / "manifest.json",
        extra_updates={
            "proof_refresh_manifest_sha256": refresh_sha,
        },
    )

    assert verify_experiment_manifest(
        proof_refresh / "manifest.json",
        expected_run_type="proof_refresh_gate",
        require_input_fingerprints=True,
    ).passed
    assert verify_experiment_manifest(
        scaleup_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed
    provenance = load_scaleup_runtime_provenance(
        scaleup_config_path
    )
    telemetry = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        output_dir=tmp_path / "telemetry",
        snapshot_ts_ns=1_000,
    )
    guard = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry.output_dir,
        output_dir=tmp_path / "guard",
    )

    telemetry_failed = set(
        telemetry.checks.loc[
            ~telemetry.checks["passed"].astype(bool),
            "check",
        ]
    )
    guard_failed = set(
        guard.checks.loc[
            ~guard.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert provenance["manifest_current"]
    assert provenance["proof_refresh_manifest_sha256"] == refresh_sha
    assert provenance["proof_refresh_source_manifest_current"]
    assert provenance["proof_refresh_source_manifest_sha256"] == refresh_sha
    assert not provenance["proof_refresh_source_semantically_verified"]
    assert not provenance["proof_refresh_source_provenance_gate_passed"]
    assert not provenance["proof_refresh_matches_current"]
    assert not provenance["contract_consistent"]
    assert not provenance["provenance_gate_passed"]
    assert (
        "scaleup_proof_refresh_semantic_verification_"
        "verified_source_mismatch"
        in provenance["contract_error"]
    )
    assert (
        "scaleup_proof_refresh_source_provenance_not_current"
        in provenance["contract_error"]
    )
    assert not telemetry.ready
    assert {
        "scaleup_contract_consistent",
        "scaleup_provenance_gate_passed",
        "scaleup_proof_refresh_source_semantically_verified",
        "scaleup_proof_refresh_source_provenance_gate_passed",
        "scaleup_proof_refresh_matches_current",
    } <= telemetry_failed
    assert guard.halted
    assert {
        "scaleup_contract_consistent",
        "scaleup_provenance_gate_passed",
        "scaleup_proof_refresh_source_semantically_verified",
        "scaleup_proof_refresh_source_provenance_gate_passed",
        "scaleup_proof_refresh_matches_current",
        "runtime_telemetry_proof_refresh_matches_current",
        "runtime_telemetry_lineage_matches_current",
    } <= guard_failed


def test_guard_rejects_telemetry_after_proof_refresh_source_drift(
    tmp_path,
):
    scaleup_dir, proof_refresh, _ = (
        _write_proof_refresh_scaleup_bundle(
            tmp_path / "scaleup"
        )
    )
    telemetry = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        output_dir=tmp_path / "telemetry",
        snapshot_ts_ns=1_000,
    )
    assert telemetry.ready

    refresh_summary_path = (
        proof_refresh / "proof_refresh_summary.csv"
    )
    refresh_summary = pd.read_csv(refresh_summary_path)
    refresh_summary.loc[0, "proof_source"] = "latest"
    refresh_summary.to_csv(refresh_summary_path, index=False)
    reseal_experiment_manifest(proof_refresh)

    guard = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry.output_dir,
        output_dir=tmp_path / "guard",
    )
    failed = set(
        guard.checks.loc[
            ~guard.checks["passed"].astype(bool),
            "check",
        ]
    )
    summary = guard.summary.iloc[0]
    assert guard.halted
    assert not summary[
        "runtime_telemetry_proof_refresh_matches_current"
    ]
    assert {
        "scaleup_manifest_current",
        "scaleup_proof_refresh_matches_current",
        "runtime_telemetry_proof_refresh_matches_current",
        "runtime_telemetry_lineage_matches_current",
    } <= failed


def test_runtime_telemetry_and_guard_retain_current_broker_readiness_lineage(
    tmp_path,
):
    broker_lineage = _write_broker_readiness_bundle(
        tmp_path / "broker_readiness"
    )
    scaleup_dir = _write_scaleup_bundle(
        tmp_path / "scaleup",
        broker_lineage,
    )

    provenance = load_scaleup_runtime_provenance(
        scaleup_dir / "scaleup_config.json"
    )
    telemetry = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        output_dir=tmp_path / "telemetry",
        snapshot_ts_ns=1_000,
    )
    guard = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry.output_dir,
        output_dir=tmp_path / "guard",
    )

    telemetry_row = telemetry.summary.iloc[0]
    guard_row = guard.summary.iloc[0]
    assert provenance["provenance_gate_passed"]
    assert provenance["broker_readiness_matches_current"]
    assert provenance["broker_readiness_source_provenance_gate_passed"]
    assert provenance["broker_readiness_roundtrip_lineage_required"]
    assert provenance["broker_readiness_roundtrip_lineage_gate_passed"]
    assert provenance["broker_readiness_roundtrip_matches_current"]
    assert (
        provenance["broker_readiness_manifest_sha256"]
        == provenance["broker_readiness_source_manifest_sha256"]
    )
    assert telemetry.ready
    assert telemetry_row["scaleup_broker_readiness_matches_current"]
    assert (
        telemetry_row["scaleup_broker_readiness_manifest_sha256"]
        == broker_lineage["manifest_sha256"]
    )
    assert not guard.halted
    assert guard_row["runtime_telemetry_broker_readiness_matches_current"]
    assert guard_row["runtime_telemetry_lineage_matches_current"]


def test_runtime_rejects_remanifested_broker_readiness_lineage_forgery(tmp_path):
    broker_lineage = _write_broker_readiness_bundle(
        tmp_path / "broker_readiness"
    )
    scaleup_dir = _write_scaleup_bundle(
        tmp_path / "scaleup",
        broker_lineage,
    )
    fake_sha = "f" * 64
    _tamper_carried_broker_manifest_sha(scaleup_dir, fake_sha)

    provenance = load_scaleup_runtime_provenance(
        scaleup_dir / "scaleup_config.json"
    )
    telemetry = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        output_dir=tmp_path / "telemetry",
        snapshot_ts_ns=1_000,
    )
    guard = write_runtime_guard_report(
        scaleup_dir=scaleup_dir,
        telemetry_path=telemetry.output_dir,
        output_dir=tmp_path / "guard",
    )

    telemetry_failed = set(
        telemetry.checks.loc[~telemetry.checks["passed"].astype(bool), "check"]
    )
    guard_failed = set(
        guard.checks.loc[~guard.checks["passed"].astype(bool), "check"]
    )
    assert provenance["manifest_current"]
    assert provenance["broker_readiness_source_manifest_current"]
    assert not provenance["contract_consistent"]
    assert not provenance["broker_readiness_matches_current"]
    assert not provenance["provenance_gate_passed"]
    assert (
        "scaleup_broker_readiness_manifest_sha256_source_mismatch"
        in provenance["contract_error"]
    )
    assert not telemetry.ready
    assert {
        "scaleup_contract_consistent",
        "scaleup_provenance_gate_passed",
        "scaleup_broker_readiness_matches_current",
    } <= telemetry_failed
    assert guard.halted
    assert {
        "scaleup_contract_consistent",
        "scaleup_provenance_gate_passed",
        "scaleup_broker_readiness_matches_current",
        "runtime_telemetry_broker_readiness_matches_current",
        "runtime_telemetry_lineage_matches_current",
    } <= guard_failed
