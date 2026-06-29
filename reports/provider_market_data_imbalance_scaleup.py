from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.scaleup import ScaleUpPlanReport, ScaleUpThresholds, write_scaleup_plan


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_scaleup_plan"


@dataclass(frozen=True)
class ProviderMarketDataImbalanceScaleupConfig:
    require_scorecard_ready: bool = True
    require_scaleup_ready: bool = True


@dataclass(frozen=True)
class ProviderMarketDataImbalanceScaleupReport:
    scaleup: ScaleUpPlanReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_imbalance_scaleup_plan(
    provider_scorecard_dir: str | Path,
    shadow_comparison_dir: str | Path,
    output_dir: str | Path,
    *,
    order_exposure_dir: str | Path | None = None,
    proof_refresh_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    data_readiness_dir: str | Path | None = None,
    data_readiness_comparison_dir: str | Path | None = None,
    strategy_portfolio_dir: str | Path | None = None,
    route_readiness_dir: str | Path | None = None,
    broker_readiness_dir: str | Path | None = None,
    config: ProviderMarketDataImbalanceScaleupConfig | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ProviderMarketDataImbalanceScaleupReport:
    config = config or ProviderMarketDataImbalanceScaleupConfig()
    thresholds = thresholds or ScaleUpThresholds()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    scorecard_dir = Path(provider_scorecard_dir)
    shadow_dir = Path(shadow_comparison_dir)
    scorecard_summary, scorecard_summary_error = _read_csv(
        scorecard_dir / "provider_market_data_imbalance_scorecard_summary.csv"
    )
    launch_evidence_dir = _path_from_text(_first_text(scorecard_summary, "provider_launch_evidence_dir"))
    launch_evidence_summary, launch_evidence_summary_error = _read_csv(
        _path_or_empty(launch_evidence_dir) / "provider_market_data_imbalance_launch_evidence_summary.csv"
    )
    provider_launch_dir = _first_existing_path(
        _path_from_text(_first_text(launch_evidence_summary, "provider_launch_dir")),
        _path_from_text(_first_text(scorecard_summary, "provider_launch_dir")),
    )
    provider_launch_summary, provider_launch_summary_error = _read_csv(
        _path_or_empty(provider_launch_dir) / "provider_market_data_imbalance_launch_summary.csv"
    )
    strategy_evidence_dir = _first_existing_path(
        _path_from_text(_first_text(launch_evidence_summary, "strategy_evidence_dir")),
        _path_or_none(_path_or_empty(launch_evidence_dir) / "strategy_evidence") if launch_evidence_dir else None,
    )
    launch_pipeline_dir = _first_existing_path(
        _path_from_text(_first_text(provider_launch_summary, "launch_pipeline_dir")),
        _path_or_none(_path_or_empty(provider_launch_dir) / "imbalance_launch_pipeline")
        if provider_launch_dir
        else None,
    )
    shadow_summary, shadow_summary_error = _read_csv(shadow_dir / "shadow_session_comparison_summary.csv")
    resolved_route_readiness_dir = _resolved_nested_summary_dir(
        route_readiness_dir,
        nested_dir="route_readiness",
        summary_file="route_readiness_summary.csv",
    )
    provider_route_readiness_wrapper_dir = _provider_wrapper_dir(
        route_readiness_dir,
        resolved_route_readiness_dir,
    )

    resolved_thresholds = _resolve_thresholds(thresholds, scorecard_summary, launch_evidence_summary)
    scaleup: ScaleUpPlanReport | None = None
    scaleup_error = ""
    scaleup_dir = out / "scaleup"
    prechecks = _prechecks(
        scorecard_dir,
        scorecard_summary,
        scorecard_summary_error,
        launch_evidence_dir,
        launch_evidence_summary,
        launch_evidence_summary_error,
        provider_launch_dir,
        provider_launch_summary,
        provider_launch_summary_error,
        strategy_evidence_dir,
        launch_pipeline_dir,
        shadow_dir,
        shadow_summary,
        shadow_summary_error,
        config,
    )
    if bool(prechecks["passed"].all()):
        try:
            scaleup = write_scaleup_plan(
                evidence_dir=_path_or_empty(strategy_evidence_dir),
                shadow_comparison_dir=shadow_dir,
                launch_dir=_path_or_empty(launch_pipeline_dir),
                output_dir=scaleup_dir,
                order_exposure_dir=order_exposure_dir,
                proof_refresh_dir=proof_refresh_dir,
                instrument_metadata_dir=instrument_metadata_dir,
                data_readiness_dir=data_readiness_dir,
                data_readiness_comparison_dir=data_readiness_comparison_dir,
                strategy_portfolio_dir=strategy_portfolio_dir,
                route_readiness_dir=resolved_route_readiness_dir,
                broker_readiness_dir=broker_readiness_dir,
                thresholds=resolved_thresholds,
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            scaleup_error = str(exc)
    else:
        scaleup_error = "provider imbalance scale-up prerequisites are not ready"

    checks = _checks(prechecks, scaleup, scaleup_error, scorecard_summary, config)
    summary = _summary(
        scorecard_dir,
        launch_evidence_dir,
        provider_launch_dir,
        strategy_evidence_dir,
        launch_pipeline_dir,
        shadow_dir,
        resolved_route_readiness_dir,
        provider_route_readiness_wrapper_dir,
        scaleup,
        checks,
        out,
        scorecard_summary,
        launch_evidence_summary,
        provider_launch_summary,
        resolved_thresholds,
    )
    action_queue = _action_queue(summary.iloc[0], checks, scaleup)
    payload = _config(
        summary.iloc[0],
        scorecard_summary,
        launch_evidence_summary,
        provider_launch_summary,
        scaleup,
        checks,
        action_queue,
        config,
        resolved_thresholds,
        resolved_route_readiness_dir,
        provider_route_readiness_wrapper_dir,
    )

    checks.to_csv(out / "provider_market_data_imbalance_scaleup_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_scaleup_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_scaleup_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_scaleup_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_scaleup_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {
        "provider_scorecard_dir": scorecard_dir,
        "shadow_comparison": shadow_dir,
    }
    if launch_evidence_dir:
        inputs["provider_launch_evidence_dir"] = launch_evidence_dir
    if strategy_evidence_dir:
        inputs["strategy_evidence"] = strategy_evidence_dir
    if provider_launch_dir:
        inputs["provider_launch_dir"] = provider_launch_dir
    if launch_pipeline_dir:
        inputs["launch_pipeline"] = launch_pipeline_dir
    if scaleup is not None and scaleup.output_dir is not None:
        inputs["scaleup"] = scaleup.output_dir
    for name, value in {
        "order_exposure": order_exposure_dir,
        "proof_refresh": proof_refresh_dir,
        "instrument_metadata": instrument_metadata_dir,
        "data_readiness": data_readiness_dir,
        "data_readiness_comparison": data_readiness_comparison_dir,
        "strategy_portfolio": strategy_portfolio_dir,
        "route_readiness": resolved_route_readiness_dir,
        "provider_route_readiness_wrapper": provider_route_readiness_wrapper_dir,
        "broker_readiness": broker_readiness_dir,
    }.items():
        if value is not None:
            inputs[name] = Path(value)

    summary_row = summary.iloc[0]
    capture_bundle = _path_from_text(str(summary_row["capture_bundle_path"]))
    if capture_bundle is not None and capture_bundle.exists():
        inputs["capture_bundle"] = capture_bundle
    capture_env_template = _path_from_text(str(summary_row["capture_env_template_path"]))
    if capture_env_template is not None and capture_env_template.exists():
        inputs["capture_env_template"] = capture_env_template
    adapter_handoff = _path_from_text(str(summary_row["adapter_handoff_path"]))
    if adapter_handoff is not None and adapter_handoff.exists():
        inputs["adapter_handoff"] = adapter_handoff
    source_env_template = _path_from_text(str(summary_row["source_credential_env_template_path"]))
    if source_env_template is not None and source_env_template.exists():
        inputs["source_credential_env_template"] = source_env_template

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config), "thresholds": asdict(resolved_thresholds)},
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "scorecard_ready": bool(summary_row["scorecard_ready"]),
            "scaleup_ready": bool(summary_row["scaleup_ready"]),
            "profile": PROFILE,
            "exchange": str(summary_row["exchange"]),
            "source_session": _source_session_contract_from_summary(summary_row),
            "market_session": _market_session_contract_from_summary(summary_row),
            "capture_bundle_provided": bool(summary_row["capture_bundle_provided"]),
            "capture_env_template_exists": bool(summary_row["capture_env_template_exists"]),
            "adapter_handoff_exists": bool(summary_row["adapter_handoff_exists"]),
            "capture_env_template": {
                "path": str(summary_row["capture_env_template_path"]),
                "exists": bool(summary_row["capture_env_template_exists"]),
                "sha256": str(summary_row["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(summary_row["adapter_handoff_path"]),
                "exists": bool(summary_row["adapter_handoff_exists"]),
                "sha256": str(summary_row["adapter_handoff_sha256"]),
            },
            "capture_bundle_metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_bundle": {
                "exchange": str(summary_row["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary_row),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary_row),
                "metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "source_credential_env_template": {
                "path": str(summary_row["source_credential_env_template_path"]),
                "exists": bool(summary_row["source_credential_env_template_exists"]),
                "sha256": str(summary_row["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary_row["source_live_fetch_contract_available"]),
                "next_gate": str(summary_row["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary_row["source_live_fetch_contract_command_template"]),
                "exchange": str(summary_row["source_live_fetch_contract_exchange"]),
                "market": str(summary_row["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary_row),
            },
        },
    )
    return ProviderMarketDataImbalanceScaleupReport(scaleup, checks, summary, action_queue, payload, out)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _prechecks(
    scorecard_dir: Path,
    scorecard_summary: pd.DataFrame,
    scorecard_summary_error: str,
    launch_evidence_dir: Path | None,
    launch_evidence_summary: pd.DataFrame,
    launch_evidence_summary_error: str,
    provider_launch_dir: Path | None,
    provider_launch_summary: pd.DataFrame,
    provider_launch_summary_error: str,
    strategy_evidence_dir: Path | None,
    launch_pipeline_dir: Path | None,
    shadow_dir: Path,
    shadow_summary: pd.DataFrame,
    shadow_summary_error: str,
    config: ProviderMarketDataImbalanceScaleupConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_scorecard_dir_exists",
                str(scorecard_dir),
                "exists",
                True,
                scorecard_dir.exists(),
                "provider imbalance scorecard directory is required",
            ),
            _check(
                "provider_scorecard_summary_readable",
                scorecard_summary_error or "ok",
                "is",
                "ok",
                not scorecard_summary_error,
                scorecard_summary_error or "provider imbalance scorecard summary could not be read",
            ),
            _check(
                "provider_imbalance_scorecard_ready",
                _first_bool(scorecard_summary, "ready"),
                "is",
                True,
                _first_bool(scorecard_summary, "ready") or not config.require_scorecard_ready,
                "provider imbalance scorecard is not ready",
            ),
            _check(
                "provider_launch_evidence_dir_exists",
                _path_text(launch_evidence_dir),
                "exists",
                True,
                bool(launch_evidence_dir and launch_evidence_dir.exists()),
                "provider imbalance launch-evidence directory is required",
            ),
            _check(
                "launch_evidence_summary_readable",
                launch_evidence_summary_error or "ok",
                "is",
                "ok",
                not launch_evidence_summary_error,
                launch_evidence_summary_error or "provider imbalance launch-evidence summary could not be read",
            ),
            _check(
                "provider_launch_dir_exists",
                _path_text(provider_launch_dir),
                "exists",
                True,
                bool(provider_launch_dir and provider_launch_dir.exists()),
                "provider imbalance launch packet directory is required",
            ),
            _check(
                "provider_launch_summary_readable",
                provider_launch_summary_error or "ok",
                "is",
                "ok",
                not provider_launch_summary_error,
                provider_launch_summary_error or "provider imbalance launch summary could not be read",
            ),
            _check(
                "strategy_evidence_dir_exists",
                _path_text(strategy_evidence_dir),
                "exists",
                True,
                bool(strategy_evidence_dir and (strategy_evidence_dir / "strategy_evidence_summary.csv").exists()),
                "full imbalance strategy evidence directory is required",
            ),
            _check(
                "launch_pipeline_dir_exists",
                _path_text(launch_pipeline_dir),
                "exists",
                True,
                bool(launch_pipeline_dir and (launch_pipeline_dir / "03_launch" / "launch_summary.csv").exists()),
                "imbalance launch pipeline directory with launch_summary.csv is required",
            ),
            _check(
                "shadow_comparison_summary_readable",
                shadow_summary_error or "ok",
                "is",
                "ok",
                not shadow_summary_error and not shadow_summary.empty,
                shadow_summary_error or "shadow session comparison summary could not be read",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    scaleup: ScaleUpPlanReport | None,
    scaleup_error: str,
    scorecard_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceScaleupConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    scaleup_ready = bool(scaleup.ready) if scaleup is not None else False
    scaleup_summary = scaleup.summary if scaleup is not None else pd.DataFrame()
    rows.append(
        _check(
            "scaleup_plan_runnable",
            scaleup_error or ("ran" if scaleup is not None else "not_run"),
            "is",
            "ran",
            scaleup is not None and not scaleup_error,
            scaleup_error or "generic scale-up planner was not run",
        )
    )
    rows.append(
        _check(
            "scaleup_plan_ready",
            scaleup_ready,
            "is",
            True,
            scaleup_ready or not config.require_scaleup_ready,
            _scaleup_failure_reason(scaleup) or "scale-up plan is not ready",
        )
    )
    rows.append(
        _check(
            "strategy_identity_imbalance",
            _first_text(scaleup_summary, "strategy") or _first_text(scorecard_summary, "strategy"),
            "is",
            PROFILE,
            (_first_text(scaleup_summary, "strategy") or _first_text(scorecard_summary, "strategy")) == PROFILE,
            "scale-up plan did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(scorecard_summary, "market")
    scaleup_market = _first_text(scaleup_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            scaleup_market or expected_market,
            "is",
            expected_market or "present",
            bool(scaleup_market)
            and (not expected_market or _identity_key(scaleup_market) == _identity_key(expected_market)),
            "scale-up market identity does not match the provider scorecard",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    scorecard_dir: Path,
    launch_evidence_dir: Path | None,
    provider_launch_dir: Path | None,
    strategy_evidence_dir: Path | None,
    launch_pipeline_dir: Path | None,
    shadow_dir: Path,
    route_readiness_dir: Path | None,
    provider_route_readiness_wrapper_dir: Path | None,
    scaleup: ScaleUpPlanReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    scorecard_summary: pd.DataFrame,
    launch_evidence_summary: pd.DataFrame,
    provider_launch_summary: pd.DataFrame,
    thresholds: ScaleUpThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    scaleup_summary = scaleup.summary if scaleup is not None else pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "scorecard_ready": _first_bool(scorecard_summary, "ready"),
                "scaleup_ready": bool(scaleup.ready) if scaleup is not None else False,
                "provider_scorecard_dir": str(scorecard_dir),
                "provider_launch_evidence_dir": _path_text(launch_evidence_dir),
                "provider_launch_dir": _path_text(provider_launch_dir),
                "strategy_evidence_dir": _path_text(strategy_evidence_dir),
                "launch_pipeline_dir": _path_text(launch_pipeline_dir),
                "exchange": _first_text(scorecard_summary, "exchange")
                or _first_text(launch_evidence_summary, "exchange")
                or _first_text(provider_launch_summary, "exchange"),
                "source_session_timezone": _first_text(scorecard_summary, "source_session_timezone")
                or _first_text(launch_evidence_summary, "source_session_timezone")
                or _first_text(provider_launch_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(scorecard_summary, "source_session_open_local")
                or _first_text(launch_evidence_summary, "source_session_open_local")
                or _first_text(provider_launch_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(scorecard_summary, "source_session_close_local")
                or _first_text(launch_evidence_summary, "source_session_close_local")
                or _first_text(provider_launch_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(scorecard_summary, "market_session_timezone")
                or _first_text(launch_evidence_summary, "market_session_timezone")
                or _first_text(provider_launch_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(scorecard_summary, "market_session_open_local")
                or _first_text(launch_evidence_summary, "market_session_open_local")
                or _first_text(provider_launch_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(scorecard_summary, "market_session_close_local")
                or _first_text(launch_evidence_summary, "market_session_close_local")
                or _first_text(provider_launch_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(scorecard_summary, "capture_bundle_path")
                or _first_text(launch_evidence_summary, "capture_bundle_path")
                or _first_text(provider_launch_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(scorecard_summary, "capture_bundle_provided")
                or _first_bool(launch_evidence_summary, "capture_bundle_provided")
                or _first_bool(provider_launch_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(scorecard_summary, "capture_bundle_exists")
                or _first_bool(launch_evidence_summary, "capture_bundle_exists")
                or _first_bool(provider_launch_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(scorecard_summary, "capture_bundle_ready")
                or _first_bool(launch_evidence_summary, "capture_bundle_ready")
                or _first_bool(provider_launch_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(scorecard_summary, "capture_bundle_exchange")
                or _first_text(launch_evidence_summary, "capture_bundle_exchange")
                or _first_text(provider_launch_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    scorecard_summary, "capture_bundle_source_session_timezone"
                )
                or _first_text(launch_evidence_summary, "capture_bundle_source_session_timezone")
                or _first_text(provider_launch_summary, "capture_bundle_source_session_timezone"),
                "capture_bundle_source_session_open_local": _first_text(
                    scorecard_summary, "capture_bundle_source_session_open_local"
                )
                or _first_text(launch_evidence_summary, "capture_bundle_source_session_open_local")
                or _first_text(provider_launch_summary, "capture_bundle_source_session_open_local"),
                "capture_bundle_source_session_close_local": _first_text(
                    scorecard_summary, "capture_bundle_source_session_close_local"
                )
                or _first_text(launch_evidence_summary, "capture_bundle_source_session_close_local")
                or _first_text(provider_launch_summary, "capture_bundle_source_session_close_local"),
                "capture_bundle_market_session_timezone": _first_text(
                    scorecard_summary, "capture_bundle_market_session_timezone"
                )
                or _first_text(launch_evidence_summary, "capture_bundle_market_session_timezone")
                or _first_text(provider_launch_summary, "capture_bundle_market_session_timezone"),
                "capture_bundle_market_session_open_local": _first_text(
                    scorecard_summary, "capture_bundle_market_session_open_local"
                )
                or _first_text(launch_evidence_summary, "capture_bundle_market_session_open_local")
                or _first_text(provider_launch_summary, "capture_bundle_market_session_open_local"),
                "capture_bundle_market_session_close_local": _first_text(
                    scorecard_summary, "capture_bundle_market_session_close_local"
                )
                or _first_text(launch_evidence_summary, "capture_bundle_market_session_close_local")
                or _first_text(provider_launch_summary, "capture_bundle_market_session_close_local"),
                "capture_bundle_metadata_matches_session": _first_bool(
                    scorecard_summary, "capture_bundle_metadata_matches_session"
                )
                or _first_bool(launch_evidence_summary, "capture_bundle_metadata_matches_session")
                or _first_bool(provider_launch_summary, "capture_bundle_metadata_matches_session"),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    scorecard_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                )
                or _first_bool(launch_evidence_summary, "capture_bundle_live_fetch_contract_metadata_matches_session")
                or _first_bool(provider_launch_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"),
                "capture_env_template_path": _first_text(scorecard_summary, "capture_env_template_path")
                or _first_text(launch_evidence_summary, "capture_env_template_path")
                or _first_text(provider_launch_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(scorecard_summary, "capture_env_template_provided")
                or _first_bool(launch_evidence_summary, "capture_env_template_provided")
                or _first_bool(provider_launch_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(scorecard_summary, "capture_env_template_exists")
                or _first_bool(launch_evidence_summary, "capture_env_template_exists")
                or _first_bool(provider_launch_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(scorecard_summary, "capture_env_template_sha256")
                or _first_text(launch_evidence_summary, "capture_env_template_sha256")
                or _first_text(provider_launch_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(scorecard_summary, "adapter_handoff_path")
                or _first_text(launch_evidence_summary, "adapter_handoff_path")
                or _first_text(provider_launch_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(scorecard_summary, "adapter_handoff_provided")
                or _first_bool(launch_evidence_summary, "adapter_handoff_provided")
                or _first_bool(provider_launch_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(scorecard_summary, "adapter_handoff_exists")
                or _first_bool(launch_evidence_summary, "adapter_handoff_exists")
                or _first_bool(provider_launch_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(scorecard_summary, "adapter_handoff_sha256")
                or _first_text(launch_evidence_summary, "adapter_handoff_sha256")
                or _first_text(provider_launch_summary, "adapter_handoff_sha256"),
                "source_credential_env_template_path": _first_text(
                    scorecard_summary, "source_credential_env_template_path"
                )
                or _first_text(launch_evidence_summary, "source_credential_env_template_path")
                or _first_text(provider_launch_summary, "source_credential_env_template_path"),
                "source_credential_env_template_exists": _first_bool(
                    scorecard_summary, "source_credential_env_template_exists"
                )
                or _first_bool(launch_evidence_summary, "source_credential_env_template_exists")
                or _first_bool(provider_launch_summary, "source_credential_env_template_exists"),
                "source_credential_env_template_sha256": _first_text(
                    scorecard_summary, "source_credential_env_template_sha256"
                )
                or _first_text(launch_evidence_summary, "source_credential_env_template_sha256")
                or _first_text(provider_launch_summary, "source_credential_env_template_sha256"),
                "source_live_fetch_contract_available": _first_bool(
                    scorecard_summary, "source_live_fetch_contract_available"
                )
                or _first_bool(launch_evidence_summary, "source_live_fetch_contract_available")
                or _first_bool(provider_launch_summary, "source_live_fetch_contract_available"),
                "source_live_fetch_contract_next_gate": _first_text(
                    scorecard_summary, "source_live_fetch_contract_next_gate"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_next_gate")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_next_gate"),
                "source_live_fetch_contract_command_template": _first_text(
                    scorecard_summary, "source_live_fetch_contract_command_template"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_command_template")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_command_template"),
                "source_live_fetch_contract_exchange": _first_text(
                    scorecard_summary, "source_live_fetch_contract_exchange"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_exchange")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_exchange"),
                "source_live_fetch_contract_market": _first_text(
                    scorecard_summary, "source_live_fetch_contract_market"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_market")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_market"),
                "source_live_fetch_contract_session_timezone": _first_text(
                    scorecard_summary, "source_live_fetch_contract_session_timezone"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_session_timezone")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_session_timezone"),
                "source_live_fetch_contract_session_open_local": _first_text(
                    scorecard_summary, "source_live_fetch_contract_session_open_local"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_session_open_local")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_session_open_local"),
                "source_live_fetch_contract_session_close_local": _first_text(
                    scorecard_summary, "source_live_fetch_contract_session_close_local"
                )
                or _first_text(launch_evidence_summary, "source_live_fetch_contract_session_close_local")
                or _first_text(provider_launch_summary, "source_live_fetch_contract_session_close_local"),
                "shadow_comparison_dir": str(shadow_dir),
                "route_readiness_dir": _path_text(route_readiness_dir),
                "provider_route_readiness_wrapper_dir": _path_text(provider_route_readiness_wrapper_dir),
                "scaleup_dir": "" if scaleup is None else str(scaleup.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(scorecard_summary, "provider")
                or _first_text(launch_evidence_summary, "provider"),
                "transport": _first_text(scorecard_summary, "transport")
                or _first_text(launch_evidence_summary, "transport"),
                "market": _first_text(scaleup_summary, "market")
                or _first_text(scorecard_summary, "market")
                or _first_text(launch_evidence_summary, "market"),
                "strategy": _first_text(scaleup_summary, "strategy")
                or _first_text(scorecard_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(scaleup_summary, "target_mode") or thresholds.target_mode,
                "adapter": _first_text(scaleup_summary, "adapter") or _first_text(provider_launch_summary, "adapter"),
                "scenario_key": _first_text(scaleup_summary, "scenario_key"),
                "max_orders_per_session": _first_number(scaleup_summary, "max_orders_per_session"),
                "max_notional_per_session": _first_number(scaleup_summary, "max_notional_per_session"),
                "observed_shadow_sessions": _first_number(scaleup_summary, "observed_shadow_sessions"),
                "observed_acceptance_rate": _first_number(scaleup_summary, "observed_acceptance_rate"),
                "route_readiness_provided": _first_bool(scaleup_summary, "route_readiness_provided"),
                "route_readiness_ready": _first_bool(scaleup_summary, "route_readiness_ready"),
                "route_readiness_route_ready_pairs": int(
                    _first_number(scaleup_summary, "route_readiness_route_ready_pairs")
                ),
                "route_readiness_gap_pairs": int(_first_number(scaleup_summary, "route_readiness_gap_pairs")),
                "route_readiness_ops_launch_controls_present": _first_bool(
                    scaleup_summary,
                    "route_readiness_ops_launch_controls_present",
                ),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "build_provider_imbalance_runtime_telemetry"
                if ready
                else "repair_provider_imbalance_scaleup",
                "next_gate": "build-provider-market-data-imbalance-runtime-telemetry" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _help_command_for_gate(
                    "build-provider-market-data-imbalance-runtime-telemetry"
                )
                if ready
                else _blocked_help_command(checks),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    scaleup: ScaleUpPlanReport | None,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "build_provider_imbalance_runtime_telemetry",
                    "reason": "provider imbalance scale-up plan is ready for runtime telemetry and guard monitoring",
                    "next_gate": "build-provider-market-data-imbalance-runtime-telemetry",
                    "next_gate_help_command": _help_command_for_gate(
                        "build-provider-market-data-imbalance-runtime-telemetry"
                    ),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    for check in failed:
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": _reason_for_check(check, scaleup),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_scaleup",
                "reason": "provider imbalance scale-up plan is not ready",
                "next_gate": "plan-provider-market-data-imbalance-scaleup",
                "next_gate_help_command": _help_command_for_gate("plan-provider-market-data-imbalance-scaleup"),
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    scorecard_summary: pd.DataFrame,
    launch_evidence_summary: pd.DataFrame,
    provider_launch_summary: pd.DataFrame,
    scaleup: ScaleUpPlanReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceScaleupConfig,
    thresholds: ScaleUpThresholds,
    route_readiness_dir: Path | None,
    provider_route_readiness_wrapper_dir: Path | None,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "scaleup_thresholds": asdict(thresholds),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "capture_bundle": {
            "capture_bundle_path": str(summary["capture_bundle_path"]),
            "capture_bundle_provided": bool(summary["capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary["capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary["capture_bundle_ready"]),
            "exchange": str(summary["capture_bundle_exchange"]),
            "source_session": _capture_bundle_source_session_contract_from_summary(summary),
            "market_session": _capture_bundle_market_session_contract_from_summary(summary),
            "capture_bundle_metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "live_fetch_contract_metadata_matches_session": bool(
                summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_env_template_path": str(summary["capture_env_template_path"]),
            "capture_env_template_provided": bool(summary["capture_env_template_provided"]),
            "capture_env_template_exists": bool(summary["capture_env_template_exists"]),
            "capture_env_template_sha256": str(summary["capture_env_template_sha256"]),
            "adapter_handoff_path": str(summary["adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
            "adapter_handoff_sha256": str(summary["adapter_handoff_sha256"]),
            "source_credential_env_template_path": str(summary["source_credential_env_template_path"]),
            "source_credential_env_template_exists": bool(summary["source_credential_env_template_exists"]),
            "source_credential_env_template_sha256": str(summary["source_credential_env_template_sha256"]),
            "source_live_fetch_contract_available": bool(summary["source_live_fetch_contract_available"]),
            "source_live_fetch_contract_next_gate": str(summary["source_live_fetch_contract_next_gate"]),
            "source_live_fetch_contract_command_template": str(
                summary["source_live_fetch_contract_command_template"]
            ),
            "source_live_fetch_contract_exchange": str(summary["source_live_fetch_contract_exchange"]),
            "source_live_fetch_contract_market": str(summary["source_live_fetch_contract_market"]),
            "source_live_fetch_contract_session_timezone": str(
                summary["source_live_fetch_contract_session_timezone"]
            ),
            "source_live_fetch_contract_session_open_local": str(
                summary["source_live_fetch_contract_session_open_local"]
            ),
            "source_live_fetch_contract_session_close_local": str(
                summary["source_live_fetch_contract_session_close_local"]
            ),
        },
        "scorecard": _first_record(scorecard_summary),
        "provider_launch_evidence": _first_record(launch_evidence_summary),
        "provider_launch": _first_record(provider_launch_summary),
        "route_readiness_inputs": {
            "route_readiness_dir": _path_text(route_readiness_dir),
            "provider_route_readiness_wrapper_dir": _path_text(provider_route_readiness_wrapper_dir),
        },
        "scaleup": {
            "ready": False if scaleup is None else bool(scaleup.ready),
            "output_dir": "" if scaleup is None else str(scaleup.output_dir or ""),
            "summary": _first_record(None if scaleup is None else scaleup.summary),
            "plan": _records(None if scaleup is None else scaleup.plan),
            "checks": _records(None if scaleup is None else scaleup.checks),
            "config": {} if scaleup is None else scaleup.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _resolve_thresholds(
    thresholds: ScaleUpThresholds,
    scorecard_summary: pd.DataFrame,
    launch_evidence_summary: pd.DataFrame,
) -> ScaleUpThresholds:
    expected_strategy = thresholds.expected_strategy or _first_text(scorecard_summary, "strategy") or PROFILE
    expected_market = (
        thresholds.expected_market
        or _first_text(scorecard_summary, "market")
        or _first_text(launch_evidence_summary, "market")
        or None
    )
    return replace(thresholds, expected_strategy=expected_strategy, expected_market=expected_market)


def _scaleup_failure_reason(scaleup: ScaleUpPlanReport | None) -> str:
    if scaleup is None or scaleup.checks.empty:
        return ""
    failed = scaleup.checks.loc[~scaleup.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "plan-provider-market-data-imbalance-scaleup"
    return _next_gate_for_check(failed[0])


def _blocked_help_command(checks: pd.DataFrame) -> str:
    return _help_command_for_gate(_blocked_next_gate(checks))


def _next_gate_for_check(check: str) -> str:
    if check.startswith("provider_scorecard") or check.startswith("provider_imbalance_scorecard"):
        return "score-provider-market-data-imbalance-readiness"
    if check.startswith("provider_launch_evidence") or check.startswith("launch_evidence"):
        return "review-provider-market-data-imbalance-launch-evidence"
    if check.startswith("provider_launch") or check.startswith("launch_pipeline"):
        return "pipeline-provider-market-data-imbalance-launch"
    if check.startswith("strategy_evidence") or check in {"strategy_identity_imbalance", "market_identity_consistent"}:
        return "review-provider-market-data-imbalance-launch-evidence"
    if check.startswith("shadow_comparison"):
        return "compare-shadow-sessions"
    if check.startswith("scaleup"):
        return "plan-scaleup"
    return "plan-provider-market-data-imbalance-scaleup"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "score-provider-market-data-imbalance-readiness":
        return "python -m hft_cli score-provider-market-data-imbalance-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-launch-evidence":
        return "python -m hft_cli review-provider-market-data-imbalance-launch-evidence --help"
    if next_gate == "pipeline-provider-market-data-imbalance-launch":
        return "python -m hft_cli pipeline-provider-market-data-imbalance-launch --help"
    if next_gate == "compare-shadow-sessions":
        return "python -m hft_cli compare-shadow-sessions --help"
    if next_gate == "plan-scaleup":
        return "python -m hft_cli plan-scaleup --help"
    if next_gate == "build-runtime-telemetry":
        return "python -m hft_cli build-runtime-telemetry --help"
    if next_gate == "build-provider-market-data-imbalance-runtime-telemetry":
        return "python -m hft_cli build-provider-market-data-imbalance-runtime-telemetry --help"
    return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"


def _repair_action(check: str) -> str:
    if check.startswith("provider_scorecard") or check.startswith("provider_imbalance_scorecard"):
        return "score_provider_imbalance_readiness"
    if check.startswith("provider_launch_evidence") or check.startswith("launch_evidence"):
        return "review_full_provider_imbalance_launch_evidence"
    if check.startswith("provider_launch") or check.startswith("launch_pipeline"):
        return "rebuild_provider_imbalance_launch_packet"
    if check.startswith("shadow_comparison"):
        return "rerun_provider_imbalance_shadow_comparison"
    if check.startswith("scaleup"):
        return "repair_generic_scaleup_plan"
    return "repair_provider_imbalance_scaleup"


def _reason_for_check(check: str, scaleup: ScaleUpPlanReport | None) -> str:
    if check == "scaleup_plan_ready":
        return _scaleup_failure_reason(scaleup) or "generic scale-up plan is not ready"
    return check.replace("_", " ")


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Scale-up",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Target mode: {summary['target_mode']}",
        f"- Scale-up dir: {summary['scaleup_dir']}",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        "",
        "## Checks",
        "",
        _checks_table(checks),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "_None_"
    rows = [
        [
            str(row.get("check", "")),
            "pass" if _truthy(row.get("passed")) else "fail",
            str(row.get("value", "")),
            str(row.get("threshold", "")),
            str(row.get("reason", "")),
        ]
        for row in checks.to_dict(orient="records")
    ]
    return _markdown_table(["Check", "Status", "Value", "Threshold", "Reason"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(row.get("priority", "")),
            str(row.get("queue_status", "")),
            str(row.get("action", "")),
            str(row.get("next_gate", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
    return _markdown_table(["#", "Status", "Action", "Next gate", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: str) -> Path | None:
    return Path(value) if value else None


def _resolved_nested_summary_dir(
    value: str | Path | None,
    *,
    nested_dir: str,
    summary_file: str,
) -> Path | None:
    if value is None:
        return None
    candidate = Path(value)
    if candidate.is_dir():
        direct_summary = candidate / summary_file
        nested_summary = candidate / nested_dir / summary_file
        if not direct_summary.exists() and nested_summary.exists():
            return candidate / nested_dir
    return candidate


def _provider_wrapper_dir(original: str | Path | None, resolved: Path | None) -> Path | None:
    if original is None or resolved is None:
        return None
    original_path = Path(original)
    if original_path == resolved:
        return None
    return original_path


def _path_or_none(path: Path) -> Path | None:
    return path


def _path_or_empty(path: Path | None) -> Path:
    return path if path is not None else Path("__missing__")


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _identity_key(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _series_record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_session_timezone"]),
        "open_local": str(summary["source_session_open_local"]),
        "close_local": str(summary["source_session_close_local"]),
    }


def _market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["market_session_timezone"]),
        "open_local": str(summary["market_session_open_local"]),
        "close_local": str(summary["market_session_close_local"]),
    }


def _capture_bundle_source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_source_session_timezone"]),
        "open_local": str(summary["capture_bundle_source_session_open_local"]),
        "close_local": str(summary["capture_bundle_source_session_close_local"]),
    }


def _capture_bundle_market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_market_session_timezone"]),
        "open_local": str(summary["capture_bundle_market_session_open_local"]),
        "close_local": str(summary["capture_bundle_market_session_close_local"]),
    }


def _source_live_fetch_contract_session_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_live_fetch_contract_session_timezone"]),
        "open_local": str(summary["source_live_fetch_contract_session_open_local"]),
        "close_local": str(summary["source_live_fetch_contract_session_close_local"]),
    }


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return _number(frame.iloc[0][column])


def _text(value: object, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "ready", "pass"}


def _number(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
