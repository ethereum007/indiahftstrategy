from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import hft_cli
import reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator as shadow_report_module
import shadow_calibration_stability
from reports import (
    provider_market_data_imbalance_live_dryrun_shadow_calibration_stability
    as stability_module,
)
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
    write_provider_market_data_imbalance_live_dryrun_shadow_calibration,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration_stability import (
    ProviderShadowCalibrationStabilityConfig,
    verify_provider_shadow_calibration_stability,
    write_provider_shadow_calibration_stability,
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


def _root(path):
    candidate = Path(path)
    return (candidate.parent if candidate.is_file() else candidate).resolve()


@pytest.fixture
def stability_sources(tmp_path, monkeypatch):
    launcher_verifications = {}
    handoff_verifications = {}
    monkeypatch.setattr(
        shadow_report_module,
        "verify_provider_market_data_imbalance_live_dryrun_runtime_launcher",
        lambda path: launcher_verifications[_root(path)],
    )
    monkeypatch.setattr(
        shadow_report_module,
        "verify_provider_market_data_imbalance_live_dryrun_handoff",
        lambda path: handoff_verifications[_root(path)],
    )
    calibration_dirs = []
    telemetry_paths = []
    for index in (1, 2):
        day = 13 + index
        identity = {
            "strategy": "microprice_imbalance",
            "market": "india_nse_index_derivatives",
            "target_mode": "live_dryrun",
            "provider": "arrow_money",
            "transport": "websocket",
            "exchange": "NSE",
            "adapter": "arrow_ws",
            "session_id": f"nse-live-dryrun-202607{day}",
            "trading_date": f"2026-07-{day}",
            "timezone": "Asia/Kolkata",
            "open_local": "09:15",
            "close_local": "15:30",
        }
        handoff_dir = tmp_path / f"handoff_{index}"
        handoff_dir.mkdir()
        handoff_plan = {
            "handoff_id": f"handoff-stability-{index}",
            "plan_sha256": f"{index}" * 64,
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

        launcher_dir = tmp_path / f"launcher_{index}"
        launcher_dir.mkdir()
        launcher_receipt = {
            "terminal_receipt_id": f"provider-runtime-stability-{index}",
            "terminal_receipt_sha256": f"{index + 2}" * 64,
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
        telemetry_path = (
            launcher_dir / shadow_report_module.LAUNCHER_TELEMETRY_FILE
        )
        telemetry.to_csv(telemetry_path, index=False)
        write_experiment_manifest(
            launcher_dir,
            run_type=RUNTIME_LAUNCHER_RUN_TYPE,
            inputs={
                "live_dryrun_handoff": handoff_dir,
                "live_dryrun_handoff_manifest": (
                    handoff_dir / "manifest.json"
                ),
            },
        )
        launcher_verifications[launcher_dir.resolve()] = SimpleNamespace(
            verified=True,
            completed=True,
            simulation_only=True,
            non_authorizing=True,
            handoff_dir=handoff_dir.resolve(),
            error="",
        )
        handoff_verifications[handoff_dir.resolve()] = SimpleNamespace(
            verified=True,
            ready=True,
            non_authorizing=True,
        )
        shadow_dir = tmp_path / f"shadow_{index}"
        shadow = write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            launcher_dir,
            shadow_dir,
        )
        assert shadow.completed
        calibration_dir = tmp_path / f"calibration_{index}"
        calibration = (
            write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
                shadow_dir,
                calibration_dir,
            )
        )
        assert calibration.completed
        calibration_dirs.append(calibration_dir)
        telemetry_paths.append(telemetry_path)
    return SimpleNamespace(
        calibration_dirs=calibration_dirs,
        telemetry_paths=telemetry_paths,
    )


def test_shadow_calibration_stability_writes_and_semantically_verifies(
    stability_sources,
    tmp_path,
):
    out = tmp_path / "stability"
    report = write_provider_shadow_calibration_stability(
        stability_sources.calibration_dirs,
        out,
    )

    assert report.stable
    assert report.summary.iloc[0]["status"] == (
        "stable_non_authorizing_simulation_cohort"
    )
    assert len(report.sessions) == 2
    assert report.sessions["session_id"].nunique() == 2
    assert set(report.cost_stability["reference_status"]) == {
        "repository_reference_requires_external_validation"
    }
    assert report.receipt["evidence_class"] == "deterministic_simulation"
    assert report.receipt["safety"]["performance_gate_enabled"] is False
    assert report.receipt["safety"]["authorizes_promotion"] is False
    assert report.receipt["safety"]["routing_enabled"] is False
    assert report.receipt["safety"]["submission_enabled"] is False
    assert report.receipt["safety"]["stability_evidence_only"] is True
    verification = verify_provider_shadow_calibration_stability(out)
    assert verification.verified
    assert verification.stable
    assert not verification.unstable
    assert verification.manifest_current
    assert verification.calibrations_current
    assert verification.artifacts_consistent
    assert verification.stability_evidence_only
    assert verification.non_authorizing

    with pytest.raises(FileExistsError, match="already exists"):
        write_provider_shadow_calibration_stability(
            stability_sources.calibration_dirs,
            out,
        )


def test_shadow_calibration_stability_records_verified_unstable_cohort(
    stability_sources,
    tmp_path,
):
    out = tmp_path / "unstable"
    report = write_provider_shadow_calibration_stability(
        stability_sources.calibration_dirs,
        out,
        config=ProviderShadowCalibrationStabilityConfig(min_sessions=3),
    )

    assert not report.stable
    assert "minimum_distinct_sessions" in report.summary.iloc[0][
        "instability_reason"
    ]
    verification = verify_provider_shadow_calibration_stability(out)
    assert verification.verified
    assert not verification.stable
    assert verification.unstable


def test_shadow_calibration_stability_cli_and_catalog_states(
    stability_sources,
    tmp_path,
):
    stable = tmp_path / "cli_stable"
    unstable = tmp_path / "cli_unstable"
    sources = [str(path) for path in stability_sources.calibration_dirs]

    assert hft_cli.main(
        [
            "compare-provider-market-data-imbalance-live-dryrun-shadow-calibrations",
            "--calibration",
            *sources,
            "--out",
            str(stable),
            "--fail-on-unstable",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "compare-provider-market-data-imbalance-live-dryrun-shadow-calibrations",
            "--calibration",
            *sources,
            "--out",
            str(unstable),
            "--min-sessions",
            "3",
            "--fail-on-unstable",
        ]
    ) == 2
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration-stability",
            "--stability",
            str(stable),
            "--fail-on-breach",
        ]
    ) == 0
    assert hft_cli.main(
        [
            "verify-provider-market-data-imbalance-live-dryrun-shadow-calibration-stability",
            "--stability",
            str(unstable),
            "--fail-on-breach",
        ]
    ) == 2

    catalog = write_experiment_catalog(
        [stable, unstable],
        output_dir=tmp_path / "stability_catalog",
    )
    rows = catalog.catalog.set_index("run_dir")
    prefix = (
        "provider_live_dryrun_shadow_calibration_stability_verification_"
    )
    assert rows.loc[str(stable.resolve()), f"{prefix}status"] == (
        "verified_stable"
    )
    assert bool(rows.loc[str(stable.resolve()), f"{prefix}stable"])
    assert rows.loc[str(unstable.resolve()), f"{prefix}status"] == (
        "verified_unstable"
    )
    assert bool(rows.loc[str(unstable.resolve()), f"{prefix}unstable"])
    assert bool(rows.loc[str(stable.resolve()), "summary_status"])
    assert not bool(rows.loc[str(unstable.resolve()), "summary_status"])
    summary = catalog.summary.iloc[0]
    assert int(summary[f"{prefix}required_runs"]) == 2
    assert int(summary[f"{prefix}verified_runs"]) == 2
    assert int(summary[f"{prefix}stable_runs"]) == 1
    assert int(summary[f"{prefix}unstable_runs"]) == 1
    assert int(summary[f"{prefix}stale_runs"]) == 0


def test_shadow_calibration_stability_rejects_duplicate_source_path(
    stability_sources,
    tmp_path,
):
    source = stability_sources.calibration_dirs[0]

    with pytest.raises(ValueError, match="must be distinct"):
        write_provider_shadow_calibration_stability(
            [source, source],
            tmp_path / "duplicate",
        )


def test_shadow_calibration_stability_rejects_incomplete_source(
    stability_sources,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        stability_module,
        "verify_provider_market_data_imbalance_live_dryrun_shadow_calibration",
        lambda _path: SimpleNamespace(
            verified=True,
            completed=False,
            calibration_only=True,
            non_authorizing=True,
            error="insufficient",
        ),
    )

    with pytest.raises(ValueError, match="verified completed"):
        write_provider_shadow_calibration_stability(
            stability_sources.calibration_dirs,
            tmp_path / "blocked",
        )


def test_shadow_calibration_stability_rejects_remanifested_authorization(
    stability_sources,
    tmp_path,
):
    out = tmp_path / "tampered"
    write_provider_shadow_calibration_stability(
        stability_sources.calibration_dirs,
        out,
    )
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_path = out / stability_module.RECEIPT_FILE
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["safety"]["authorizes_promotion"] = True
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type=stability_module.RUN_TYPE,
        parameters=manifest["parameters"],
        inputs=_manifest_input_paths(manifest["inputs"]),
        extra=manifest["extra"],
    )

    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=stability_module.RUN_TYPE,
        require_input_fingerprints=True,
    ).passed
    verification = verify_provider_shadow_calibration_stability(out)
    assert not verification.verified
    assert verification.manifest_current
    assert not verification.artifacts_consistent
    assert not verification.non_authorizing

    catalog = write_experiment_catalog(
        [out],
        output_dir=tmp_path / "tampered_catalog",
    )
    row = catalog.catalog.iloc[0]
    prefix = (
        "provider_live_dryrun_shadow_calibration_stability_verification_"
    )
    assert row[f"{prefix}status"] == "stale_or_inconsistent"
    assert not bool(row[f"{prefix}verified"])
    assert not bool(row["summary_status"])
    assert int(catalog.summary.iloc[0][f"{prefix}stale_runs"]) == 1


def test_shadow_calibration_stability_detects_recursive_source_drift(
    stability_sources,
    tmp_path,
):
    out = tmp_path / "source_drift"
    write_provider_shadow_calibration_stability(
        stability_sources.calibration_dirs,
        out,
    )
    telemetry_path = stability_sources.telemetry_paths[0]
    telemetry_path.write_text(
        telemetry_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    verification = verify_provider_shadow_calibration_stability(out)
    assert not verification.verified
    assert not verification.calibrations_current


@pytest.mark.parametrize(
    "module_path",
    [
        Path(stability_module.__file__),
        Path(shadow_calibration_stability.__file__),
    ],
)
def test_shadow_calibration_stability_has_no_execution_capabilities(
    module_path,
):
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
