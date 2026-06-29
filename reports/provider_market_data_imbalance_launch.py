from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.imbalance_launch_pipeline import (
    ImbalanceLaunchPipelineConfig,
    ImbalanceLaunchPipelineReport,
    write_imbalance_launch_pipeline,
)
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLaunchConfig:
    require_provider_evidence_ready: bool = True
    require_launch_ready: bool = True
    adapter: str = "arrow_money"
    mode: str = "shadow"
    route_tag: str | None = None
    instrument_id: str = "BOOK"
    qty: int | None = None
    reference_price: float | None = None
    buy_limit_price: float | None = None
    sell_limit_price: float | None = None
    entry_offset_ticks: float = 0.0
    tick_size: float | None = None
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    max_orders: int | None = None
    contract_multiplier: float = 1.0
    product: str = "MIS"
    exchange: str = "NFO"
    require_reviewed_schema: bool = True
    broker_schema_audit_dir: str | Path | None = None
    broker_mapping_draft_dir: str | Path | None = None
    broker_mapped_orders_dir: str | Path | None = None
    broker_halt_export_dir: str | Path | None = None
    broker_reconciliation_dir: str | Path | None = None
    broker_runtime_session_dir: str | Path | None = None
    broker_vendor_data_readiness_dir: str | Path | None = None
    require_broker_schema_audit: bool = False
    require_broker_mapping_draft: bool = False
    require_broker_mapped_orders: bool = False
    require_broker_halt_export: bool = False
    require_broker_reconciliation: bool = False
    require_broker_runtime_session: bool = False


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLaunchReport:
    launch: ImbalanceLaunchPipelineReport | None
    components: pd.DataFrame
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


def write_provider_market_data_imbalance_launch_packet(
    provider_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceLaunchConfig | None = None,
) -> ProviderMarketDataImbalanceLaunchReport:
    config = config or ProviderMarketDataImbalanceLaunchConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    evidence_dir = Path(provider_evidence_dir)
    evidence_summary, evidence_summary_error = _read_csv(
        evidence_dir / "provider_market_data_imbalance_evidence_summary.csv"
    )
    evidence_config, evidence_config_error = _read_json(
        evidence_dir / "provider_market_data_imbalance_evidence_config.json"
    )
    promotion_dir = _promotion_dir(evidence_summary)
    launch_dir = out / "imbalance_launch_pipeline"
    launch = None
    launch_error = ""
    if _should_run_launch(evidence_summary, promotion_dir, config):
        try:
            launch = write_imbalance_launch_pipeline(
                promotion_dir,
                output_dir=launch_dir,
                config=_launch_config(config),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            launch_error = str(exc)
    checks = _checks(
        evidence_dir,
        evidence_summary,
        evidence_summary_error,
        evidence_config,
        evidence_config_error,
        promotion_dir,
        launch,
        launch_error,
        config,
    )
    components = _components(evidence_dir, evidence_summary, promotion_dir, launch_dir, launch)
    summary = _summary(evidence_dir, evidence_summary, promotion_dir, launch_dir, launch, checks, out, config)
    action_queue = _action_queue(summary.iloc[0], checks)
    payload = _config(
        summary.iloc[0],
        evidence_summary,
        evidence_config,
        launch,
        components,
        checks,
        action_queue,
        config,
    )

    components.to_csv(out / "provider_market_data_imbalance_launch_components.csv", index=False)
    checks.to_csv(out / "provider_market_data_imbalance_launch_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_launch_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_launch_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_launch_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_launch_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], components, checks, action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"provider_evidence_dir": evidence_dir}
    if promotion_dir.exists():
        inputs["promotion"] = promotion_dir
    if launch is not None and launch.output_dir is not None:
        inputs["imbalance_launch_pipeline"] = launch.output_dir
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
        run_type="provider_market_data_imbalance_launch_packet",
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "provider_evidence_ready": bool(summary.iloc[0]["provider_evidence_ready"]),
            "launch_pipeline_ready": bool(summary.iloc[0]["launch_pipeline_ready"]),
            "strategy": str(summary.iloc[0]["strategy"]),
            "market": str(summary.iloc[0]["market"]),
            "exchange": str(summary.iloc[0]["exchange"]),
            "source_session": _source_session_contract_from_summary(summary.iloc[0]),
            "market_session": _market_session_contract_from_summary(summary.iloc[0]),
            "capture_bundle_provided": bool(summary.iloc[0]["capture_bundle_provided"]),
            "capture_env_template_exists": bool(summary.iloc[0]["capture_env_template_exists"]),
            "adapter_handoff_exists": bool(summary.iloc[0]["adapter_handoff_exists"]),
            "capture_env_template": {
                "path": str(summary.iloc[0]["capture_env_template_path"]),
                "exists": bool(summary.iloc[0]["capture_env_template_exists"]),
                "sha256": str(summary.iloc[0]["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(summary.iloc[0]["adapter_handoff_path"]),
                "exists": bool(summary.iloc[0]["adapter_handoff_exists"]),
                "sha256": str(summary.iloc[0]["adapter_handoff_sha256"]),
            },
            "capture_bundle_metadata_matches_session": bool(summary.iloc[0]["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "provider_capture_command_count": int(summary.iloc[0]["provider_capture_command_count"]),
            "provider_capture_command_providers": str(summary.iloc[0]["provider_capture_command_providers"]),
            "provider_capture_command_transports": str(summary.iloc[0]["provider_capture_command_transports"]),
            "capture_bundle_provider_capture_command_count": int(
                summary.iloc[0]["capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                summary.iloc[0]["capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"]
            ),
            "capture_bundle": {
                "exchange": str(summary.iloc[0]["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary.iloc[0]),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary.iloc[0]),
                "provider_capture_commands": _list(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
                ),
                "provider_capture_command_count": int(
                    summary.iloc[0]["capture_bundle_provider_capture_command_count"]
                ),
                "provider_capture_commands_match_session": bool(
                    summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"]
                ),
                "metadata_matches_session": bool(summary.iloc[0]["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "source_credential_env_template": {
                "path": str(summary.iloc[0]["source_credential_env_template_path"]),
                "exists": bool(summary.iloc[0]["source_credential_env_template_exists"]),
                "sha256": str(summary.iloc[0]["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary.iloc[0]["source_live_fetch_contract_available"]),
                "next_gate": str(summary.iloc[0]["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary.iloc[0]["source_live_fetch_contract_command_template"]),
                "exchange": str(summary.iloc[0]["source_live_fetch_contract_exchange"]),
                "market": str(summary.iloc[0]["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary.iloc[0]),
            },
            "provider_capture_commands": _list(payload.get("provider_capture_commands")),
            "capture_bundle_provider_capture_commands": _list(
                payload.get("capture_bundle_provider_capture_commands")
            ),
        },
    )
    return ProviderMarketDataImbalanceLaunchReport(launch, components, checks, summary, action_queue, payload, out)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"{path.name} does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"{path.name} is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"{path.name} JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{path.name} JSON must be an object"
    return payload, ""


def _promotion_dir(evidence_summary: pd.DataFrame) -> Path:
    provider_dir = _first_text(evidence_summary, "provider_research_dir")
    if not provider_dir:
        return Path("")
    return Path(provider_dir) / "imbalance_research" / "promotion"


def _should_run_launch(
    evidence_summary: pd.DataFrame,
    promotion_dir: Path,
    config: ProviderMarketDataImbalanceLaunchConfig,
) -> bool:
    if config.require_provider_evidence_ready and not _first_bool(evidence_summary, "ready"):
        return False
    return bool(
        str(promotion_dir)
        and (promotion_dir / "promotion_summary.csv").exists()
        and (promotion_dir / "candidate_config.json").exists()
    )


def _launch_config(config: ProviderMarketDataImbalanceLaunchConfig) -> ImbalanceLaunchPipelineConfig:
    return ImbalanceLaunchPipelineConfig(
        adapter=config.adapter,
        mode=config.mode,
        route_tag=config.route_tag,
        instrument_id=config.instrument_id,
        qty=config.qty,
        reference_price=config.reference_price,
        buy_limit_price=config.buy_limit_price,
        sell_limit_price=config.sell_limit_price,
        entry_offset_ticks=config.entry_offset_ticks,
        tick_size=config.tick_size,
        max_order_qty=config.max_order_qty,
        max_notional=config.max_notional,
        price_band_pct=config.price_band_pct,
        max_orders=config.max_orders,
        contract_multiplier=config.contract_multiplier,
        product=config.product,
        exchange=config.exchange,
        require_reviewed_schema=config.require_reviewed_schema,
        broker_schema_audit_dir=config.broker_schema_audit_dir,
        broker_mapping_draft_dir=config.broker_mapping_draft_dir,
        broker_mapped_orders_dir=config.broker_mapped_orders_dir,
        broker_halt_export_dir=config.broker_halt_export_dir,
        broker_reconciliation_dir=config.broker_reconciliation_dir,
        broker_runtime_session_dir=config.broker_runtime_session_dir,
        broker_vendor_data_readiness_dir=config.broker_vendor_data_readiness_dir,
        require_broker_schema_audit=config.require_broker_schema_audit,
        require_broker_mapping_draft=config.require_broker_mapping_draft,
        require_broker_mapped_orders=config.require_broker_mapped_orders,
        require_broker_halt_export=config.require_broker_halt_export,
        require_broker_reconciliation=config.require_broker_reconciliation,
        require_broker_runtime_session=config.require_broker_runtime_session,
    )


def _checks(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    evidence_summary_error: str,
    evidence_config: dict[str, Any],
    evidence_config_error: str,
    promotion_dir: Path,
    launch: ImbalanceLaunchPipelineReport | None,
    launch_error: str,
    config: ProviderMarketDataImbalanceLaunchConfig,
) -> pd.DataFrame:
    launch_ready = bool(launch.ready) if launch is not None else False
    launch_summary = launch.summary if launch is not None else pd.DataFrame()
    bundle_provided = _first_bool(evidence_summary, "capture_bundle_provided")
    provider_capture_command_count = int(_first_number(evidence_summary, "provider_capture_command_count"))
    bundle_provider_capture_command_count = int(
        _first_number(evidence_summary, "capture_bundle_provider_capture_command_count")
    )
    bundle_provider_capture_command_missing_count = int(
        _first_number(evidence_summary, "capture_bundle_provider_capture_command_missing_count")
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and _first_bool(evidence_summary, "capture_bundle_provider_capture_commands_match_session")
    )
    return pd.DataFrame(
        [
            _check(
                "provider_evidence_dir_exists",
                str(evidence_dir),
                "exists",
                True,
                evidence_dir.exists(),
                "provider imbalance evidence directory is required",
            ),
            _check(
                "provider_evidence_summary_readable",
                evidence_summary_error or "ok",
                "is",
                "ok",
                not evidence_summary_error,
                evidence_summary_error or "provider imbalance evidence summary could not be read",
            ),
            _check(
                "provider_evidence_config_readable",
                evidence_config_error or "ok",
                "is",
                "ok",
                not evidence_config_error,
                evidence_config_error or "provider imbalance evidence config could not be read",
            ),
            _check(
                "provider_imbalance_evidence_ready",
                _first_bool(evidence_summary, "ready"),
                "is",
                True,
                _first_bool(evidence_summary, "ready") or not config.require_provider_evidence_ready,
                "provider imbalance evidence review is not ready",
            ),
            _check(
                "provider_evidence_provider_capture_commands_carried",
                bundle_provider_capture_command_count,
                "==",
                provider_capture_command_count,
                bundle_provider_capture_commands_carried if bundle_provided else True,
                "provider imbalance evidence is missing capture-bundle provider command proof",
            ),
            _check(
                "provider_evidence_provider_capture_commands_match_session",
                bundle_provider_capture_command_count,
                "matches",
                provider_capture_command_count,
                bundle_provider_capture_commands_match_session if bundle_provided else True,
                "provider imbalance evidence command proof no longer matches the session packet",
            ),
            _check(
                "promotion_summary_exists",
                str(promotion_dir / "promotion_summary.csv"),
                "exists",
                True,
                bool(str(promotion_dir)) and (promotion_dir / "promotion_summary.csv").exists(),
                "promoted imbalance candidate summary is missing",
            ),
            _check(
                "candidate_config_exists",
                str(promotion_dir / "candidate_config.json"),
                "exists",
                True,
                bool(str(promotion_dir)) and (promotion_dir / "candidate_config.json").exists(),
                "promoted imbalance candidate config is missing",
            ),
            _check(
                "launch_pipeline_runnable",
                launch_error or ("ran" if launch is not None else "not_run"),
                "is",
                "ran",
                launch is not None and not launch_error,
                launch_error or "imbalance launch pipeline was not run",
            ),
            _check(
                "launch_pipeline_ready",
                launch_ready,
                "is",
                True,
                launch_ready or not config.require_launch_ready,
                "imbalance launch pipeline is not ready",
            ),
            _check(
                "strategy_identity_imbalance",
                _first_text(launch_summary, "strategy") or _first_text(evidence_summary, "strategy"),
                "is",
                "imbalance",
                (_first_text(launch_summary, "strategy") or _first_text(evidence_summary, "strategy")) == "imbalance",
                "launch packet did not resolve to imbalance strategy",
            ),
            _check(
                "market_identity_present",
                _first_text(launch_summary, "market") or _first_text(evidence_summary, "market"),
                "is_not",
                "",
                bool(_first_text(launch_summary, "market") or _first_text(evidence_summary, "market")),
                "launch packet did not resolve a market identity",
            ),
        ]
    )


def _components(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    promotion_dir: Path,
    launch_dir: Path,
    launch: ImbalanceLaunchPipelineReport | None,
) -> pd.DataFrame:
    launch_summary = launch.summary if launch is not None else pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "component": "provider_imbalance_evidence",
                "status": "ready" if _first_bool(evidence_summary, "ready") else "not_ready",
                "ready": _first_bool(evidence_summary, "ready"),
                "artifact_dir": str(evidence_dir),
                "run_type": "provider_market_data_imbalance_evidence_review",
                "reason": "",
            },
            {
                "component": "provider_imbalance_promotion",
                "status": "ready"
                if (promotion_dir / "promotion_summary.csv").exists()
                and (promotion_dir / "candidate_config.json").exists()
                else "not_ready",
                "ready": (promotion_dir / "promotion_summary.csv").exists()
                and (promotion_dir / "candidate_config.json").exists(),
                "artifact_dir": str(promotion_dir),
                "run_type": "promotion_report",
                "reason": "",
            },
            {
                "component": "imbalance_launch_pipeline",
                "status": "ready" if _first_bool(launch_summary, "ready") else "not_ready",
                "ready": _first_bool(launch_summary, "ready"),
                "artifact_dir": str(launch_dir if launch is not None else ""),
                "run_type": "imbalance_launch_pipeline",
                "reason": "" if launch is not None else "launch_pipeline_not_run",
            },
        ]
    )


def _summary(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    promotion_dir: Path,
    launch_dir: Path,
    launch: ImbalanceLaunchPipelineReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    config: ProviderMarketDataImbalanceLaunchConfig,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    launch_summary = launch.summary if launch is not None else pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_evidence_ready": _first_bool(evidence_summary, "ready"),
                "launch_pipeline_ready": bool(launch.ready) if launch is not None else False,
                "provider_evidence_dir": str(evidence_dir),
                "provider_research_dir": _first_text(evidence_summary, "provider_research_dir"),
                "promotion_dir": str(promotion_dir),
                "launch_pipeline_dir": str(launch_dir if launch is not None else ""),
                "output_dir": str(output_dir),
                "provider": _first_text(evidence_summary, "provider"),
                "transport": _first_text(evidence_summary, "transport"),
                "exchange": _first_text(evidence_summary, "exchange"),
                "source_session_timezone": _first_text(evidence_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(evidence_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(evidence_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(evidence_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(evidence_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(evidence_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(evidence_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(evidence_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(evidence_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(evidence_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(evidence_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    evidence_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    evidence_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    evidence_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    evidence_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    evidence_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    evidence_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    evidence_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    evidence_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                ),
                "capture_env_template_path": _first_text(evidence_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(evidence_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(evidence_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(evidence_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(evidence_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(evidence_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(evidence_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(evidence_summary, "adapter_handoff_sha256"),
                "source_credential_env_template_path": _first_text(
                    evidence_summary, "source_credential_env_template_path"
                ),
                "source_credential_env_template_exists": _first_bool(
                    evidence_summary, "source_credential_env_template_exists"
                ),
                "source_credential_env_template_sha256": _first_text(
                    evidence_summary, "source_credential_env_template_sha256"
                ),
                "source_live_fetch_contract_available": _first_bool(
                    evidence_summary, "source_live_fetch_contract_available"
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    evidence_summary, "source_live_fetch_contract_next_gate"
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    evidence_summary, "source_live_fetch_contract_command_template"
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    evidence_summary, "source_live_fetch_contract_exchange"
                ),
                "source_live_fetch_contract_market": _first_text(
                    evidence_summary, "source_live_fetch_contract_market"
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    evidence_summary, "source_live_fetch_contract_session_timezone"
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    evidence_summary, "source_live_fetch_contract_session_open_local"
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    evidence_summary, "source_live_fetch_contract_session_close_local"
                ),
                "provider_capture_command_count": int(
                    _first_number(evidence_summary, "provider_capture_command_count")
                ),
                "provider_capture_command_providers": _first_text(
                    evidence_summary, "provider_capture_command_providers"
                ),
                "provider_capture_command_transports": _first_text(
                    evidence_summary, "provider_capture_command_transports"
                ),
                "capture_bundle_provider_capture_command_count": int(
                    _first_number(evidence_summary, "capture_bundle_provider_capture_command_count")
                ),
                "capture_bundle_provider_capture_command_missing_count": int(
                    _first_number(evidence_summary, "capture_bundle_provider_capture_command_missing_count")
                ),
                "capture_bundle_provider_capture_commands_match_session": _first_bool(
                    evidence_summary, "capture_bundle_provider_capture_commands_match_session"
                )
                if _first_bool(evidence_summary, "capture_bundle_provided")
                else True,
                "market": _first_text(launch_summary, "market") or _first_text(evidence_summary, "market"),
                "strategy": _first_text(launch_summary, "strategy") or _first_text(evidence_summary, "strategy"),
                "adapter": config.adapter,
                "mode": config.mode,
                "route_tag": _text(config.route_tag),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "review_full_imbalance_launch_evidence" if ready else "repair_provider_imbalance_launch",
                "next_gate": "review-strategy-evidence" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _ready_help_command() if ready else _blocked_help_command(checks),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(summary: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "review_full_imbalance_launch_evidence",
                    "reason": "provider imbalance launch packet is ready for the full imbalance evidence profile",
                    "next_gate": "review-strategy-evidence",
                    "next_gate_help_command": _ready_help_command(),
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
                "reason": _reason_for_check(check),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_launch",
                "reason": "provider imbalance launch packet is not ready",
                "next_gate": "pipeline-provider-market-data-imbalance-launch",
                "next_gate_help_command": "python -m hft_cli pipeline-provider-market-data-imbalance-launch --help",
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    evidence_summary: pd.DataFrame,
    evidence_config: dict[str, Any],
    launch: ImbalanceLaunchPipelineReport | None,
    components: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceLaunchConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "summary": _series_record(summary),
        "provider_evidence": _first_record(evidence_summary),
        "provider_evidence_config": _jsonable(evidence_config),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_capture_commands": _provider_capture_commands(evidence_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(evidence_config),
        "capture_bundle": _provider_capture_bundle(evidence_summary, evidence_config),
        "launch_pipeline": {
            "ready": False if launch is None else bool(launch.ready),
            "output_dir": "" if launch is None else str(launch.output_dir or ""),
            "summary": _first_record(None if launch is None else launch.summary),
            "components": _records(None if launch is None else launch.components),
        },
        "components": _records(components),
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "pipeline-provider-market-data-imbalance-launch"
    return _next_gate_for_check(failed[0])


def _blocked_help_command(checks: pd.DataFrame) -> str:
    return _help_command_for_gate(_blocked_next_gate(checks))


def _next_gate_for_check(check: str) -> str:
    if check.startswith("provider_evidence") or check.startswith("provider_imbalance"):
        return "review-provider-market-data-imbalance-evidence"
    if check.startswith("promotion") or check.startswith("candidate"):
        return "run-provider-market-data-imbalance-research"
    if check.startswith("launch_pipeline"):
        return "pipeline-imbalance-launch"
    if check.startswith("strategy_identity") or check.startswith("market_identity"):
        return "review-strategy-evidence"
    return "pipeline-provider-market-data-imbalance-launch"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-evidence":
        return "python -m hft_cli review-provider-market-data-imbalance-evidence --help"
    if next_gate == "run-provider-market-data-imbalance-research":
        return "python -m hft_cli run-provider-market-data-imbalance-research --help"
    if next_gate == "pipeline-imbalance-launch":
        return "python -m hft_cli pipeline-imbalance-launch --help"
    if next_gate == "review-strategy-evidence":
        return _ready_help_command()
    return "python -m hft_cli pipeline-provider-market-data-imbalance-launch --help"


def _ready_help_command() -> str:
    return "python -m hft_cli review-strategy-evidence --profile imbalance --help"


def _repair_action(check: str) -> str:
    if check.startswith("provider_evidence") or check.startswith("provider_imbalance"):
        return "review_provider_imbalance_evidence"
    if check.startswith("promotion") or check.startswith("candidate"):
        return "rerun_provider_imbalance_research"
    if check.startswith("launch_pipeline"):
        return "repair_imbalance_launch_pipeline"
    return "repair_provider_imbalance_launch"


def _reason_for_check(check: str) -> str:
    return check.replace("_", " ")


def _runbook_markdown(
    summary: pd.Series,
    components: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Provider Market Data Imbalance Launch",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Strategy: {summary['strategy']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Adapter: {summary['adapter']}",
        f"- Mode: {summary['mode']}",
        f"- Capture bundle: {summary['capture_bundle_path']}",
        f"- Credential env template: {summary['capture_env_template_path']}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        "",
        "## Components",
        "",
        _components_table(components),
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


def _components_table(components: pd.DataFrame) -> str:
    if components.empty:
        return "_None_"
    rows = [
        [
            str(row.get("component", "")),
            str(row.get("status", "")),
            str(row.get("artifact_dir", "")),
            str(row.get("reason", "")),
        ]
        for row in components.to_dict(orient="records")
    ]
    return _markdown_table(["Component", "Status", "Artifact", "Reason"], rows)


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


def _provider_capture_bundle(evidence_summary: pd.DataFrame, evidence_config: dict[str, Any]) -> dict[str, Any]:
    payload = _mapping(evidence_config.get("capture_bundle"))
    if payload:
        return {str(key): _jsonable(value) for key, value in payload.items()}
    return {
        "capture_bundle_path": _first_text(evidence_summary, "capture_bundle_path"),
        "capture_bundle_provided": _first_bool(evidence_summary, "capture_bundle_provided"),
        "capture_bundle_exists": _first_bool(evidence_summary, "capture_bundle_exists"),
        "capture_bundle_ready": _first_bool(evidence_summary, "capture_bundle_ready"),
        "exchange": _first_text(evidence_summary, "capture_bundle_exchange"),
        "source_session": {
            "timezone": _first_text(evidence_summary, "capture_bundle_source_session_timezone"),
            "open_local": _first_text(evidence_summary, "capture_bundle_source_session_open_local"),
            "close_local": _first_text(evidence_summary, "capture_bundle_source_session_close_local"),
        },
        "market_session": {
            "timezone": _first_text(evidence_summary, "capture_bundle_market_session_timezone"),
            "open_local": _first_text(evidence_summary, "capture_bundle_market_session_open_local"),
            "close_local": _first_text(evidence_summary, "capture_bundle_market_session_close_local"),
        },
        "capture_bundle_metadata_matches_session": _first_bool(
            evidence_summary, "capture_bundle_metadata_matches_session"
        ),
        "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
            evidence_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
        ),
        "metadata_matches_session": _first_bool(evidence_summary, "capture_bundle_metadata_matches_session"),
        "live_fetch_contract_metadata_matches_session": _first_bool(
            evidence_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
        ),
        "capture_env_template_path": _first_text(evidence_summary, "capture_env_template_path"),
        "capture_env_template_provided": _first_bool(evidence_summary, "capture_env_template_provided"),
        "capture_env_template_exists": _first_bool(evidence_summary, "capture_env_template_exists"),
        "capture_env_template_sha256": _first_text(evidence_summary, "capture_env_template_sha256"),
        "adapter_handoff_path": _first_text(evidence_summary, "adapter_handoff_path"),
        "adapter_handoff_provided": _first_bool(evidence_summary, "adapter_handoff_provided"),
        "adapter_handoff_exists": _first_bool(evidence_summary, "adapter_handoff_exists"),
        "adapter_handoff_sha256": _first_text(evidence_summary, "adapter_handoff_sha256"),
        "source_credential_env_template_path": _first_text(
            evidence_summary, "source_credential_env_template_path"
        ),
        "source_credential_env_template_exists": _first_bool(
            evidence_summary, "source_credential_env_template_exists"
        ),
        "source_credential_env_template_sha256": _first_text(
            evidence_summary, "source_credential_env_template_sha256"
        ),
        "source_live_fetch_contract_available": _first_bool(
            evidence_summary, "source_live_fetch_contract_available"
        ),
        "source_live_fetch_contract_next_gate": _first_text(
            evidence_summary, "source_live_fetch_contract_next_gate"
        ),
        "source_live_fetch_contract_command_template": _first_text(
            evidence_summary, "source_live_fetch_contract_command_template"
        ),
        "source_live_fetch_contract_exchange": _first_text(
            evidence_summary, "source_live_fetch_contract_exchange"
        ),
        "source_live_fetch_contract_market": _first_text(
            evidence_summary, "source_live_fetch_contract_market"
        ),
        "source_live_fetch_contract_session_timezone": _first_text(
            evidence_summary, "source_live_fetch_contract_session_timezone"
        ),
        "source_live_fetch_contract_session_open_local": _first_text(
            evidence_summary, "source_live_fetch_contract_session_open_local"
        ),
        "source_live_fetch_contract_session_close_local": _first_text(
            evidence_summary, "source_live_fetch_contract_session_close_local"
        ),
        "provider_capture_command_count": int(_first_number(evidence_summary, "provider_capture_command_count")),
        "provider_capture_command_providers": _first_text(evidence_summary, "provider_capture_command_providers"),
        "provider_capture_command_transports": _first_text(evidence_summary, "provider_capture_command_transports"),
        "capture_bundle_provider_capture_command_count": int(
            _first_number(evidence_summary, "capture_bundle_provider_capture_command_count")
        ),
        "capture_bundle_provider_capture_command_missing_count": int(
            _first_number(evidence_summary, "capture_bundle_provider_capture_command_missing_count")
        ),
        "capture_bundle_provider_capture_commands_match_session": _first_bool(
            evidence_summary, "capture_bundle_provider_capture_commands_match_session"
        )
        if _first_bool(evidence_summary, "capture_bundle_provided")
        else True,
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(evidence_config),
    }


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _provider_capture_commands(evidence_config: dict[str, Any]) -> list[Any]:
    return _list(evidence_config.get("provider_capture_commands"))


def _bundle_provider_capture_commands(evidence_config: dict[str, Any]) -> list[Any]:
    bundle = _mapping(evidence_config.get("capture_bundle"))
    return (
        _list(evidence_config.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("provider_capture_commands"))
    )


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


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
