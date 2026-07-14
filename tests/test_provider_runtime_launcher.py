from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import hft_cli
import market_data_observation_simulator
import reports.provider_market_data_imbalance_live_dryrun_runtime_launcher as launcher_module
from reports.catalog import write_experiment_catalog
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher,
    write_provider_market_data_imbalance_live_dryrun_runtime_launcher,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_preflight import (
    RUN_TYPE as RUNTIME_PREFLIGHT_RUN_TYPE,
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
def launcher_sources(tmp_path, monkeypatch):
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    handoff_plan = {
        "handoff_id": "handoff-123",
        "plan_sha256": "a" * 64,
        "identity": {
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
            "requires_separate_runtime_launcher": True,
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
            "credential_values_stored": False,
        },
    }
    handoff_plan_path = (
        handoff_dir
        / "provider_market_data_imbalance_live_dryrun_handoff_plan.json"
    )
    handoff_plan_path.write_text(
        json.dumps(handoff_plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        handoff_dir,
        run_type="provider_market_data_imbalance_live_dryrun_handoff",
    )

    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    preflight_receipt = {
        "preflight_id": "preflight-123",
        "receipt_sha256": "b" * 64,
        "identity": {
            field: handoff_plan["identity"][field]
            for field in (
                "provider",
                "adapter",
                "transport",
                "market",
                "exchange",
                "session_id",
            )
        },
        "connectivity": {
            "probe_called": True,
            "connected": True,
            "authenticated": True,
            "market_data_readable": True,
        },
        "safety": {
            "strategy_execution_enabled": False,
            "launch_executed": False,
            "requires_separate_runtime_launcher": True,
            "release_approved": False,
            "dry_run_only": True,
            "connectivity_only": True,
            "market_data_connectivity_probe_called": True,
            "broker_order_api_enabled": False,
            "broker_order_api_called": False,
            "broker_api_called": False,
            "submission_enabled": False,
            "authorizes_submission": False,
            "credential_values_stored": False,
        },
    }
    preflight_receipt_path = (
        preflight_dir
        / "provider_market_data_imbalance_live_dryrun_launch_receipt.json"
    )
    preflight_receipt_path.write_text(
        json.dumps(preflight_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        preflight_dir,
        run_type=RUNTIME_PREFLIGHT_RUN_TYPE,
        inputs={
            "live_dryrun_handoff": handoff_dir,
            "live_dryrun_handoff_manifest": handoff_dir / "manifest.json",
        },
    )

    preflight_verification = SimpleNamespace(
        verified=True,
        ready=True,
        credential_safe=True,
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
        launcher_module,
        "verify_provider_market_data_imbalance_live_dryrun_runtime_preflight",
        lambda _path: preflight_verification,
    )
    monkeypatch.setattr(
        launcher_module,
        "verify_provider_market_data_imbalance_live_dryrun_handoff",
        lambda _path: handoff_verification,
    )
    return SimpleNamespace(
        preflight_dir=preflight_dir,
        preflight_receipt_path=preflight_receipt_path,
        preflight_verification=preflight_verification,
        handoff_dir=handoff_dir,
        handoff_plan_path=handoff_plan_path,
    )


def test_runtime_launcher_completes_simulation_and_verifies(launcher_sources, tmp_path):
    out = tmp_path / "launcher"
    report = write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
        launcher_sources.preflight_dir,
        out,
        config=ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
            event_count=5,
            interval_ms=250,
        ),
    )

    assert report.completed
    assert not report.halted
    assert len(report.telemetry) == 5
    assert report.receipt["launcher_mode"] == "deterministic_simulation"
    assert report.receipt["safety"]["provider_network_called"] is False
    assert report.receipt["safety"]["provider_backend_loaded"] is False
    assert report.receipt["safety"]["credential_environment_read"] is False
    assert report.receipt["safety"]["strategy_execution_enabled"] is False
    assert report.receipt["safety"]["order_generation_enabled"] is False
    assert report.receipt["safety"]["broker_order_api_imported"] is False
    assert report.receipt["safety"]["broker_order_api_called"] is False
    assert report.receipt["safety"]["submission_enabled"] is False
    assert report.receipt["safety"]["authorizes_submission"] is False
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(out)
    )
    assert verification.verified
    assert verification.completed
    assert not verification.halted
    assert verification.manifest_current
    assert verification.preflight_current
    assert verification.handoff_current
    assert verification.artifacts_consistent
    assert verification.simulation_only
    assert verification.non_authorizing

    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            launcher_sources.preflight_dir,
            out,
        )


def test_runtime_launcher_records_verified_kill_switch_halt(launcher_sources, tmp_path):
    out = tmp_path / "halted_launcher"
    report = write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
        launcher_sources.preflight_dir,
        out,
        config=ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
            event_count=5,
            fault_mode="invalid_quote",
            fault_at_event=3,
        ),
    )

    assert not report.completed
    assert report.halted
    assert report.receipt["halt_reason"] == "invalid_quote"
    assert not bool(report.summary.iloc[0]["ready"])
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(out)
    )
    assert verification.verified
    assert not verification.completed
    assert verification.halted
    assert verification.simulation_only
    assert verification.non_authorizing


def test_runtime_launcher_cli_and_catalog_distinguish_complete_and_halt(
    launcher_sources,
    tmp_path,
):
    completed = tmp_path / "cli_completed_launcher"
    halted = tmp_path / "cli_halted_launcher"
    assert hft_cli.main(
        [
            "launch-provider-market-data-imbalance-live-dryrun-simulated-runtime",
            "--preflight",
            str(launcher_sources.preflight_dir),
            "--out",
            str(completed),
            "--events",
            "3",
            "--interval-ms",
            "250",
            "--fail-on-halt",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "launch-provider-market-data-imbalance-live-dryrun-simulated-runtime",
            "--preflight",
            str(launcher_sources.preflight_dir),
            "--out",
            str(halted),
            "--events",
            "3",
            "--simulate-fault",
            "invalid_quote",
            "--fault-at-event",
            "2",
            "--fail-on-halt",
        ]
    ) == 2
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-runtime-launcher",
            "--launcher",
            str(completed),
            "--fail-on-breach",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-runtime-launcher",
            "--launcher",
            str(halted),
            "--fail-on-breach",
        ]
    ) == 2

    catalog = write_experiment_catalog(
        [completed, halted],
        output_dir=tmp_path / "launcher_catalog",
    )
    rows = catalog.catalog.set_index("run_dir")
    prefix = "provider_live_dryrun_runtime_launcher_verification_"
    assert rows.loc[str(completed.resolve()), f"{prefix}status"] == (
        "verified_completed"
    )
    assert bool(rows.loc[str(completed.resolve()), f"{prefix}verified"])
    assert bool(rows.loc[str(completed.resolve()), f"{prefix}completed"])
    assert rows.loc[str(halted.resolve()), f"{prefix}status"] == (
        "verified_halted"
    )
    assert bool(rows.loc[str(halted.resolve()), f"{prefix}verified"])
    assert bool(rows.loc[str(halted.resolve()), f"{prefix}halted"])
    summary = catalog.summary.iloc[0]
    assert int(summary[f"{prefix}required_runs"]) == 2
    assert int(summary[f"{prefix}verified_runs"]) == 2
    assert int(summary[f"{prefix}completed_runs"]) == 1
    assert int(summary[f"{prefix}halted_runs"]) == 1
    assert int(summary[f"{prefix}stale_runs"]) == 0


def test_runtime_launcher_semantic_verifier_rejects_remanifested_authorization(
    launcher_sources,
    tmp_path,
):
    out = tmp_path / "tampered_launcher"
    write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
        launcher_sources.preflight_dir,
        out,
        config=ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
            event_count=2,
        ),
    )
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_path = (
        out / "provider_market_data_imbalance_live_dryrun_terminal_receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["safety"]["authorizes_submission"] = True
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=launcher_module.RUN_TYPE,
        parameters=manifest["parameters"],
        inputs=_manifest_input_paths(manifest["inputs"]),
        extra=manifest["extra"],
    )

    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=launcher_module.RUN_TYPE,
        require_input_fingerprints=True,
    ).passed
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(out)
    )
    assert not verification.verified
    assert verification.manifest_current
    assert not verification.artifacts_consistent
    assert not verification.non_authorizing
    catalog = write_experiment_catalog(
        [out],
        output_dir=tmp_path / "tampered_launcher_catalog",
    )
    row = catalog.catalog.iloc[0]
    prefix = "provider_live_dryrun_runtime_launcher_verification_"
    assert row[f"{prefix}status"] == "stale_or_inconsistent"
    assert not bool(row[f"{prefix}verified"])
    assert row["summary_status_column"] == (
        "provider_live_dryrun_runtime_launcher_verification"
    )
    assert not bool(row["summary_status"])
    assert int(catalog.summary.iloc[0][f"{prefix}stale_runs"]) == 1


def test_runtime_launcher_manifest_detects_preflight_source_drift(
    launcher_sources,
    tmp_path,
):
    out = tmp_path / "source_drift_launcher"
    write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
        launcher_sources.preflight_dir,
        out,
        config=ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
            event_count=2,
        ),
    )
    launcher_sources.preflight_receipt_path.write_text(
        launcher_sources.preflight_receipt_path.read_text(encoding="utf-8")
        + "\n",
        encoding="utf-8",
    )

    verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(out)
    )
    assert not verification.verified
    assert not verification.manifest_current


def test_runtime_launcher_requires_ready_preflight(
    launcher_sources,
    tmp_path,
):
    launcher_sources.preflight_verification.ready = False
    with pytest.raises(ValueError, match="verified ready"):
        write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            launcher_sources.preflight_dir,
            tmp_path / "blocked_launcher",
        )


def test_runtime_launcher_execution_modules_have_no_ambient_capability_imports():
    forbidden_roots = {
        "importlib",
        "os",
        "socket",
        "requests",
        "httpx",
        "websocket",
        "provider_adapter",
        "provider_connectivity",
    }
    for module in (launcher_module, market_data_observation_simulator):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not imported_roots & forbidden_roots
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            for node in ast.walk(tree)
        )
