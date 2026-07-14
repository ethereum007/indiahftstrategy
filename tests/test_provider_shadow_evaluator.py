from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import hft_cli
import reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator as shadow_report_module
import shadow_microprice_evaluator
import strategies.microprice_features as microprice_features_module
from market_data_observation_simulator import (
    BoundedMarketDataSimulationConfig,
    simulate_bounded_market_data_session,
)
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from reports.catalog import write_experiment_catalog
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    RUN_TYPE as RUNTIME_LAUNCHER_RUN_TYPE,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator import (
    ProviderMarketDataImbalanceLiveDryrunShadowConfig,
    verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
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
def shadow_sources(tmp_path, monkeypatch):
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
        "handoff_id": "handoff-123",
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

    launcher_dir = tmp_path / "launcher"
    launcher_dir.mkdir()
    launcher_receipt = {
        "terminal_receipt_id": "provider-runtime-terminal-123",
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
    launcher_receipt_path = (
        launcher_dir
        / "provider_market_data_imbalance_live_dryrun_terminal_receipt.json"
    )
    launcher_receipt_path.write_text(
        json.dumps(launcher_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    telemetry = simulate_bounded_market_data_session(
        config=BoundedMarketDataSimulationConfig(event_count=6),
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
    telemetry_path = (
        launcher_dir
        / "provider_market_data_imbalance_live_dryrun_market_data_telemetry.csv"
    )
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
    return SimpleNamespace(
        launcher_dir=launcher_dir,
        launcher_receipt_path=launcher_receipt_path,
        telemetry_path=telemetry_path,
        launcher_verification=launcher_verification,
        handoff_dir=handoff_dir,
    )


def test_shadow_report_completes_and_semantically_verifies(
    shadow_sources,
    tmp_path,
):
    out = tmp_path / "shadow"
    report = write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        shadow_sources.launcher_dir,
        out,
    )

    assert report.completed
    assert not report.halted
    assert report.intents["action"].tolist() == [
        "entry",
        "exit_decay",
        "entry",
        "exit_decay",
    ]
    assert set(report.intents["routing_status"]) == {"not_routable"}
    assert set(report.intents["submission_status"]) == {"not_submitted"}
    safety = report.receipt["safety"]
    assert safety["shadow_only"] is True
    assert safety["execution_engine_loaded"] is False
    assert safety["order_object_created"] is False
    assert safety["broker_order_api_imported"] is False
    assert safety["broker_order_api_called"] is False
    assert safety["routing_enabled"] is False
    assert safety["submission_enabled"] is False
    assert safety["authorizes_submission"] is False
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(out)
    )
    assert verification.verified
    assert verification.completed
    assert not verification.halted
    assert verification.manifest_current
    assert verification.launcher_current
    assert verification.handoff_current
    assert verification.artifacts_consistent
    assert verification.shadow_only
    assert verification.non_authorizing

    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            shadow_sources.launcher_dir,
            out,
        )


def test_shadow_report_records_verified_limit_halt(shadow_sources, tmp_path):
    out = tmp_path / "halted_shadow"
    report = write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        shadow_sources.launcher_dir,
        out,
        config=ProviderMarketDataImbalanceLiveDryrunShadowConfig(lot_size=100),
    )

    assert not report.completed
    assert report.halted
    assert report.receipt["halt_reason"] == "max_notional_per_session"
    assert report.intents.iloc[-1]["intent_status"] == "rejected_limit"
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(out)
    )
    assert verification.verified
    assert not verification.completed
    assert verification.halted
    assert verification.shadow_only
    assert verification.non_authorizing


def test_shadow_cli_and_catalog_distinguish_complete_and_halt(
    shadow_sources,
    tmp_path,
):
    completed = tmp_path / "cli_completed_shadow"
    halted = tmp_path / "cli_halted_shadow"
    assert hft_cli.main(
        [
            "evaluate-provider-market-data-imbalance-live-dryrun-shadow",
            "--launcher",
            str(shadow_sources.launcher_dir),
            "--out",
            str(completed),
            "--fail-on-halt",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "evaluate-provider-market-data-imbalance-live-dryrun-shadow",
            "--launcher",
            str(shadow_sources.launcher_dir),
            "--out",
            str(halted),
            "--lot-size",
            "100",
            "--fail-on-halt",
        ]
    ) == 2
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-shadow-evaluation",
            "--shadow",
            str(completed),
            "--fail-on-breach",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-shadow-evaluation",
            "--shadow",
            str(halted),
            "--fail-on-breach",
        ]
    ) == 2

    catalog = write_experiment_catalog(
        [completed, halted],
        output_dir=tmp_path / "shadow_catalog",
    )
    rows = catalog.catalog.set_index("run_dir")
    prefix = "provider_live_dryrun_shadow_verification_"
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


def test_shadow_report_rejects_remanifested_authorization(
    shadow_sources,
    tmp_path,
):
    out = tmp_path / "tampered_shadow"
    write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        shadow_sources.launcher_dir,
        out,
    )
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_path = (
        out
        / "provider_market_data_imbalance_live_dryrun_shadow_terminal_receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["safety"]["authorizes_submission"] = True
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=shadow_report_module.RUN_TYPE,
        parameters=manifest["parameters"],
        inputs=_manifest_input_paths(manifest["inputs"]),
        extra=manifest["extra"],
    )

    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=shadow_report_module.RUN_TYPE,
        require_input_fingerprints=True,
    ).passed
    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(out)
    )
    assert not verification.verified
    assert verification.manifest_current
    assert not verification.artifacts_consistent
    assert not verification.non_authorizing
    catalog = write_experiment_catalog(
        [out],
        output_dir=tmp_path / "tampered_shadow_catalog",
    )
    row = catalog.catalog.iloc[0]
    prefix = "provider_live_dryrun_shadow_verification_"
    assert row[f"{prefix}status"] == "stale_or_inconsistent"
    assert not bool(row[f"{prefix}verified"])
    assert row["summary_status_column"] == (
        "provider_live_dryrun_shadow_verification"
    )
    assert not bool(row["summary_status"])
    assert int(catalog.summary.iloc[0][f"{prefix}stale_runs"]) == 1


def test_shadow_report_detects_launcher_source_drift(shadow_sources, tmp_path):
    out = tmp_path / "source_drift_shadow"
    write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
        shadow_sources.launcher_dir,
        out,
    )
    shadow_sources.telemetry_path.write_text(
        shadow_sources.telemetry_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(out)
    )
    assert not verification.verified
    assert not verification.manifest_current


def test_shadow_report_requires_completed_launcher(shadow_sources, tmp_path):
    shadow_sources.launcher_verification.completed = False
    with pytest.raises(ValueError, match="verified completed"):
        write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            shadow_sources.launcher_dir,
            tmp_path / "blocked_shadow",
        )


def test_shadow_execution_modules_have_no_order_or_network_capabilities():
    forbidden_roots = {
        "broker",
        "ctypes",
        "engine",
        "httpx",
        "importlib",
        "os",
        "provider_adapter",
        "provider_connectivity",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "websocket",
    }
    forbidden_calls = {"__import__", "place_order", "route", "send", "submit"}
    for module in (
        shadow_report_module,
        shadow_microprice_evaluator,
        microprice_features_module,
    ):
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
            and (
                (
                    isinstance(node.func, ast.Name)
                    and node.func.id in forbidden_calls
                )
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                )
            )
            for node in ast.walk(tree)
        )
