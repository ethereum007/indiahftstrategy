from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import hft_cli
import reports.provider_market_data_imbalance_live_dryrun_shadow_calibration as calibration_module
import reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator as shadow_report_module
import shadow_markout_calibration
from market_data_observation_simulator import (
    BoundedMarketDataSimulationConfig,
    simulate_bounded_market_data_session,
)
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from reports.catalog import write_experiment_catalog
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    RUN_TYPE as RUNTIME_LAUNCHER_RUN_TYPE,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration import (
    ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
    verify_provider_market_data_imbalance_live_dryrun_shadow_calibration,
    write_provider_market_data_imbalance_live_dryrun_shadow_calibration,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator import (
    write_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
)


def _manifest_input_paths(value):
    if isinstance(value, dict):
        if value.get("kind") in {"file", "directory"} and value.get("path"):
            return value["path"]
        return {
            key: _manifest_input_paths(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_manifest_input_paths(item) for item in value]
    return value


@pytest.fixture
def calibration_source(tmp_path, monkeypatch):
    identity = {
        "strategy": "microprice_imbalance",
        "market": "india_nse_index_derivatives",
        "target_mode": "live_dryrun",
        "provider": "arrow_money",
        "transport": "websocket",
        "exchange": "NSE",
        "adapter": "arrow_ws",
        "session_id": "nse-live-dryrun-20260714",
        "trading_date": "2026-07-14",
        "timezone": "Asia/Kolkata",
        "open_local": "09:15",
        "close_local": "15:30",
    }
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    handoff_plan = {
        "handoff_id": "handoff-calibration",
        "plan_sha256": "a" * 64,
        "identity": identity,
        "limits": {
            "max_orders_per_session": 100,
            "max_notional_per_session": 1_000_000.0,
            "max_open_orders": 10,
            "max_position_lots": 5,
        },
        "kill_switch": {
            "enabled": True,
            "trigger_on_limit_breach": True,
            "stop_new_orders": True,
            "cancel_open_orders": True,
            "owner": "risk_operator",
        },
        "safety": {
            "execution_enabled": False,
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
            "credential_values_stored": False,
        },
    }
    (handoff_dir / shadow_report_module.HANDOFF_PLAN_FILE).write_text(
        json.dumps(handoff_plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        handoff_dir,
        run_type="provider_market_data_imbalance_live_dryrun_handoff",
    )

    launcher_dir = tmp_path / "launcher"
    launcher_dir.mkdir()
    launcher_receipt = {
        "terminal_receipt_id": "provider-runtime-calibration",
        "terminal_receipt_sha256": "b" * 64,
        "launcher_mode": "deterministic_simulation",
        "completed": True,
        "halted": False,
        "identity": {
            field: identity[field]
            for field in (
                "strategy",
                "market",
                "target_mode",
                "provider",
                "transport",
                "exchange",
                "adapter",
                "session_id",
            )
        },
        "safety": {
            "simulation_only": True,
            "provider_network_called": False,
            "credential_environment_read": False,
            "broker_order_api_called": False,
            "submission_enabled": False,
            "authorizes_submission": False,
        },
    }
    (launcher_dir / shadow_report_module.LAUNCHER_RECEIPT_FILE).write_text(
        json.dumps(launcher_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    telemetry = simulate_bounded_market_data_session(
        config=BoundedMarketDataSimulationConfig(event_count=8),
        provider=identity["provider"],
        adapter=identity["adapter"],
        transport=identity["transport"],
        market=identity["market"],
        exchange=identity["exchange"],
        session_id=identity["session_id"],
        trading_date=identity["trading_date"],
        timezone_name=identity["timezone"],
        open_local=identity["open_local"],
        close_local=identity["close_local"],
        kill_switch_enabled=True,
    ).telemetry
    telemetry_path = launcher_dir / shadow_report_module.LAUNCHER_TELEMETRY_FILE
    telemetry.to_csv(telemetry_path, index=False)
    write_experiment_manifest(
        launcher_dir,
        run_type=RUNTIME_LAUNCHER_RUN_TYPE,
        inputs={
            "live_dryrun_handoff": handoff_dir,
            "live_dryrun_handoff_manifest": handoff_dir / "manifest.json",
        },
    )
    launcher_verification = SimpleNamespace(
        verified=True,
        completed=True,
        simulation_only=True,
        non_authorizing=True,
        handoff_dir=handoff_dir.resolve(),
        error="",
    )
    handoff_verification = SimpleNamespace(
        verified=True,
        ready=True,
        non_authorizing=True,
    )
    monkeypatch.setattr(
        shadow_report_module,
        "verify_provider_market_data_imbalance_live_dryrun_runtime_launcher",
        lambda _path: launcher_verification,
    )
    monkeypatch.setattr(
        shadow_report_module,
        "verify_provider_market_data_imbalance_live_dryrun_handoff",
        lambda _path: handoff_verification,
    )
    shadow_dir = tmp_path / "shadow"
    shadow = write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        launcher_dir,
        shadow_dir,
    )
    assert shadow.completed
    return SimpleNamespace(
        shadow_dir=shadow_dir,
        telemetry_path=telemetry_path,
    )


def test_shadow_calibration_completes_and_semantically_verifies(
    calibration_source,
    tmp_path,
):
    out = tmp_path / "calibration"
    report = write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
        calibration_source.shadow_dir,
        out,
    )

    assert report.completed
    assert set(report.cost_sensitivity["cost_scenario"]) == {
        "nse_index_futures_reference",
        "nse_index_options_reference",
    }
    assert set(report.cost_sensitivity["reference_status"]) == {
        "repository_reference_requires_external_validation"
    }
    assert report.receipt["safety"]["calibration_only"] is True
    assert report.receipt["safety"]["performance_gate_enabled"] is False
    assert report.receipt["safety"]["authorizes_promotion"] is False
    assert report.receipt["safety"]["routing_enabled"] is False
    assert report.receipt["safety"]["submission_enabled"] is False
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(out)
    )
    assert verification.verified
    assert verification.completed
    assert not verification.insufficient
    assert verification.manifest_current
    assert verification.shadow_current
    assert verification.artifacts_consistent
    assert verification.calibration_only
    assert verification.non_authorizing

    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
            calibration_source.shadow_dir,
            out,
        )


def test_shadow_calibration_records_verified_insufficient_coverage(
    calibration_source,
    tmp_path,
):
    out = tmp_path / "insufficient"
    report = write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
        calibration_source.shadow_dir,
        out,
        config=ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig(
            horizons_ns=(10_000_000_000,),
        ),
    )

    assert not report.completed
    assert report.summary.iloc[0]["status"] == (
        "insufficient_shadow_observation_coverage"
    )
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(out)
    )
    assert verification.verified
    assert not verification.completed
    assert verification.insufficient


def test_shadow_calibration_cli_and_catalog_states(
    calibration_source,
    tmp_path,
):
    completed = tmp_path / "cli_completed"
    insufficient = tmp_path / "cli_insufficient"
    assert hft_cli.main(
        [
            "calibrate-provider-market-data-imbalance-live-dryrun-shadow",
            "--shadow",
            str(calibration_source.shadow_dir),
            "--out",
            str(completed),
            "--fail-on-incomplete",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "calibrate-provider-market-data-imbalance-live-dryrun-shadow",
            "--shadow",
            str(calibration_source.shadow_dir),
            "--out",
            str(insufficient),
            "--horizons-ns",
            "10000000000",
            "--fail-on-incomplete",
        ]
    ) == 2
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration",
            "--calibration",
            str(completed),
            "--fail-on-breach",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration",
            "--calibration",
            str(insufficient),
            "--fail-on-breach",
        ]
    ) == 2

    catalog = write_experiment_catalog(
        [completed, insufficient],
        output_dir=tmp_path / "calibration_catalog",
    )
    rows = catalog.catalog.set_index("run_dir")
    prefix = "provider_live_dryrun_shadow_calibration_verification_"
    assert rows.loc[str(completed.resolve()), f"{prefix}status"] == (
        "verified_completed"
    )
    assert bool(rows.loc[str(completed.resolve()), f"{prefix}verified"])
    assert bool(rows.loc[str(completed.resolve()), f"{prefix}completed"])
    assert rows.loc[str(insufficient.resolve()), f"{prefix}status"] == (
        "verified_insufficient"
    )
    assert bool(rows.loc[str(insufficient.resolve()), f"{prefix}verified"])
    assert bool(rows.loc[str(insufficient.resolve()), f"{prefix}insufficient"])
    summary = catalog.summary.iloc[0]
    assert int(summary[f"{prefix}required_runs"]) == 2
    assert int(summary[f"{prefix}verified_runs"]) == 2
    assert int(summary[f"{prefix}completed_runs"]) == 1
    assert int(summary[f"{prefix}insufficient_runs"]) == 1
    assert int(summary[f"{prefix}stale_runs"]) == 0


def test_shadow_calibration_rejects_remanifested_authorization(
    calibration_source,
    tmp_path,
):
    out = tmp_path / "tampered"
    write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
        calibration_source.shadow_dir,
        out,
    )
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_path = out / calibration_module.RECEIPT_FILE
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["safety"]["authorizes_promotion"] = True
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=calibration_module.RUN_TYPE,
        parameters=manifest["parameters"],
        inputs=_manifest_input_paths(manifest["inputs"]),
        extra=manifest["extra"],
    )

    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=calibration_module.RUN_TYPE,
        require_input_fingerprints=True,
    ).passed
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(out)
    )
    assert not verification.verified
    assert verification.manifest_current
    assert not verification.artifacts_consistent
    assert not verification.non_authorizing

    catalog = write_experiment_catalog(
        [out],
        output_dir=tmp_path / "tampered_catalog",
    )
    row = catalog.catalog.iloc[0]
    prefix = "provider_live_dryrun_shadow_calibration_verification_"
    assert row[f"{prefix}status"] == "stale_or_inconsistent"
    assert not bool(row[f"{prefix}verified"])
    assert not bool(row["summary_status"])
    assert int(catalog.summary.iloc[0][f"{prefix}stale_runs"]) == 1


def test_shadow_calibration_detects_recursive_source_drift(
    calibration_source,
    tmp_path,
):
    out = tmp_path / "source_drift"
    write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
        calibration_source.shadow_dir,
        out,
    )
    calibration_source.telemetry_path.write_text(
        calibration_source.telemetry_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(out)
    )
    assert not verification.verified
    assert not verification.shadow_current


def test_shadow_calibration_requires_completed_shadow_source(
    calibration_source,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        calibration_module,
        "verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation",
        lambda _path: SimpleNamespace(
            verified=True,
            completed=False,
            shadow_only=True,
            non_authorizing=True,
            error="insufficient",
        ),
    )

    with pytest.raises(ValueError, match="verified completed"):
        write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
            calibration_source.shadow_dir,
            tmp_path / "blocked",
        )


@pytest.mark.parametrize(
    "module_path",
    [
        Path(calibration_module.__file__),
        Path(shadow_markout_calibration.__file__),
    ],
)
def test_shadow_calibration_modules_have_no_execution_capabilities(module_path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_roots = {
        "engine",
        "provider_adapter",
        "provider_connectivity",
        "socket",
        "requests",
        "httpx",
        "subprocess",
        "importlib",
    }
    forbidden_calls = {
        "send",
        "route",
        "submit",
        "place_order",
        "__import__",
    }
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)

    assert not (imported & forbidden_roots)
    assert not (called & forbidden_calls)
