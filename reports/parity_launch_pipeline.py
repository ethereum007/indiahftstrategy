from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from adapters.broker_instrument_resolution import (
    BrokerInstrumentResolutionConfig,
    BrokerInstrumentResolutionReport,
    write_broker_instrument_resolution,
)
from adapters.broker_readiness import (
    BrokerReadinessReport,
    BrokerReadinessThresholds,
    write_broker_readiness_report,
)
from adapters.order_export import OrderExportConfig, OrderExportReport, write_order_export
from adapters.order_upload_pack import (
    OrderUploadPackConfig,
    OrderUploadPackReport,
    write_order_upload_pack,
)
from adapters.orders import OrderStagingLimits, OrderStagingReport, write_staged_orders
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.launch import LaunchBundleReport, LaunchThresholds, write_launch_bundle
from reports.manifest import (
    manifest_dependency_paths,
    write_experiment_manifest,
)
from reports.parity_order_plan import (
    PARITY_BOX_STRATEGY,
    ParityOrderPlanConfig,
    ParityOrderPlanReport,
    write_parity_order_plan,
)


@dataclass(frozen=True)
class ParityLaunchPipelineConfig:
    adapter: str = "arrow_money"
    mode: str = "shadow"
    route_tag: str | None = None
    symbol_prefix: str = "NIFTY"
    future_instrument_id: str = "NIFTY_FUT"
    direction: str | None = None
    expiry: str | None = None
    strike: float | None = None
    low_strike: float | None = None
    high_strike: float | None = None
    qty: int | None = None
    call_price: float | None = None
    put_price: float | None = None
    future_price: float | None = None
    low_call_price: float | None = None
    low_put_price: float | None = None
    high_call_price: float | None = None
    high_put_price: float | None = None
    price_offset_ticks: float = 0.0
    tick_size: float = 0.05
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    max_orders: int | None = None
    contract_multiplier: float = 1.0
    product: str = "MIS"
    exchange: str = "NFO"
    broker_instrument_master_path: str | Path | None = None
    require_broker_instrument_resolution: bool = False
    require_broker_instrument_token: bool = True
    instrument_master_research_id_column: str | None = None
    instrument_master_underlying_column: str | None = None
    instrument_master_expiry_column: str | None = None
    instrument_master_strike_column: str | None = None
    instrument_master_option_type_column: str | None = None
    instrument_master_exchange_column: str | None = None
    instrument_master_broker_symbol_column: str | None = None
    instrument_master_broker_token_column: str | None = None
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
class ParityLaunchPipelineReport:
    order_plan: ParityOrderPlanReport | None
    instrument_resolution: BrokerInstrumentResolutionReport | None
    staging: OrderStagingReport | None
    launch: LaunchBundleReport | None
    export: OrderExportReport | None
    upload: OrderUploadPackReport | None
    broker_readiness: BrokerReadinessReport | None
    components: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_parity_launch_pipeline(
    promotion_dir: str | Path,
    *,
    output_dir: str | Path,
    config: ParityLaunchPipelineConfig | None = None,
) -> ParityLaunchPipelineReport:
    config = config or ParityLaunchPipelineConfig()
    _validate_config(config)
    promotion = Path(promotion_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    components: list[dict[str, object]] = []

    order_plan_dir = out / "01_order_plan"
    order_plan = write_parity_order_plan(
        promotion,
        output_dir=order_plan_dir,
        config=ParityOrderPlanConfig(
            symbol_prefix=config.symbol_prefix,
            future_instrument_id=config.future_instrument_id,
            direction=config.direction,
            expiry=config.expiry,
            strike=config.strike,
            low_strike=config.low_strike,
            high_strike=config.high_strike,
            qty=config.qty,
            call_price=config.call_price,
            put_price=config.put_price,
            future_price=config.future_price,
            low_call_price=config.low_call_price,
            low_put_price=config.low_put_price,
            high_call_price=config.high_call_price,
            high_put_price=config.high_put_price,
            price_offset_ticks=config.price_offset_ticks,
            tick_size=config.tick_size,
            max_order_qty=config.max_order_qty,
            max_notional=config.max_notional,
            price_band_pct=config.price_band_pct,
        ),
    )
    components.append(_component("order_plan", order_plan.ready, order_plan_dir, order_plan.summary))

    instrument_resolution = None
    staging = None
    launch = None
    export = None
    upload = None
    broker_readiness = None
    staging_input = order_plan_dir / "parity_order_candidates.csv"
    instrument_resolution_dir = out / "02_instrument_resolution"
    instrument_resolution_gate_ready = True

    if _order_plan_ready(order_plan):
        if config.broker_instrument_master_path is not None:
            instrument_resolution = write_broker_instrument_resolution(
                staging_input,
                config.broker_instrument_master_path,
                output_dir=instrument_resolution_dir,
                config=BrokerInstrumentResolutionConfig(
                    adapter=config.adapter,
                    exchange=config.exchange,
                    require_broker_token=config.require_broker_instrument_token,
                    master_research_id_column=config.instrument_master_research_id_column,
                    master_underlying_column=config.instrument_master_underlying_column,
                    master_expiry_column=config.instrument_master_expiry_column,
                    master_strike_column=config.instrument_master_strike_column,
                    master_option_type_column=config.instrument_master_option_type_column,
                    master_exchange_column=config.instrument_master_exchange_column,
                    master_broker_symbol_column=config.instrument_master_broker_symbol_column,
                    master_broker_token_column=config.instrument_master_broker_token_column,
                ),
            )
            components.append(
                _component(
                    "instrument_resolution",
                    instrument_resolution.ready,
                    instrument_resolution_dir,
                    instrument_resolution.summary,
                )
            )
            instrument_resolution_gate_ready = instrument_resolution.ready
            if instrument_resolution.ready:
                staging_input = (
                    instrument_resolution_dir
                    / "resolved_order_candidates.csv"
                )
        elif config.require_broker_instrument_resolution:
            instrument_resolution_gate_ready = False
            components.append(
                _missing_component(
                    "instrument_resolution",
                    instrument_resolution_dir,
                    "broker_instrument_master_not_provided",
                )
            )
    elif (
        config.broker_instrument_master_path is not None
        or config.require_broker_instrument_resolution
    ):
        instrument_resolution_gate_ready = False
        components.append(
            _skipped_component(
                "instrument_resolution",
                instrument_resolution_dir,
                "order_plan_not_ready",
            )
        )

    if _order_plan_ready(order_plan) and instrument_resolution_gate_ready:
        staging_dir = out / "02_staged_orders"
        staging = write_staged_orders(
            staging_input,
            output_dir=staging_dir,
            source="orders",
            adapter=config.adapter,
            limits=OrderStagingLimits(
                max_order_qty=config.max_order_qty,
                max_notional=config.max_notional,
                price_band_pct=config.price_band_pct,
                max_orders=config.max_orders,
                contract_multiplier=config.contract_multiplier,
            ),
        )
        components.append(_component("staged_orders", _staging_ready(staging), staging_dir, staging.summary))
    else:
        reason = (
            "instrument_resolution_not_ready"
            if _order_plan_ready(order_plan)
            else "order_plan_not_ready"
        )
        components.append(
            _skipped_component(
                "staged_orders",
                out / "02_staged_orders",
                reason,
            )
        )

    if staging is not None and _staging_ready(staging):
        launch_dir = out / "03_launch"
        launch = write_launch_bundle(
            promotion_dir=promotion,
            staged_orders_dir=out / "02_staged_orders",
            output_dir=launch_dir,
            mode=config.mode,
            adapter=config.adapter,
            thresholds=LaunchThresholds(
                max_order_notional=config.max_notional,
            ),
        )
        components.append(_component("launch", launch.ready, launch_dir, launch.summary))
    else:
        components.append(_skipped_component("launch", out / "03_launch", "staged_orders_not_ready"))

    if launch is not None and launch.ready:
        export_dir = out / "04_export"
        export = write_order_export(
            launch_dir,
            output_dir=export_dir,
            config=OrderExportConfig(
                adapter=config.adapter,
                route_tag=config.route_tag,
                require_instrument_resolution=(
                    config.require_broker_instrument_resolution
                ),
                require_broker_instrument_token=(
                    config.require_broker_instrument_token
                ),
                max_orders=config.max_orders,
            ),
        )
        components.append(_component("export", export.ready, export_dir, export.summary))
    else:
        components.append(_skipped_component("export", out / "04_export", "launch_not_ready"))

    if export is not None and export.ready:
        upload_dir = out / "05_upload_pack"
        upload = write_order_upload_pack(
            export_dir,
            output_dir=upload_dir,
            config=OrderUploadPackConfig(
                adapter=config.adapter,
                product=config.product,
                exchange=config.exchange,
                require_reviewed_schema=config.require_reviewed_schema,
                require_instrument_resolution=(
                    config.require_broker_instrument_resolution
                ),
                require_broker_instrument_token=(
                    config.require_broker_instrument_token
                ),
            ),
        )
        components.append(_component("upload_pack", upload.ready, upload_dir, upload.summary))
    else:
        components.append(_skipped_component("upload_pack", out / "05_upload_pack", "export_not_ready"))

    if export is not None and upload is not None:
        broker_readiness_dir = out / "06_broker_readiness"
        broker_readiness = write_broker_readiness_report(
            output_dir=broker_readiness_dir,
            schema_audit_dir=config.broker_schema_audit_dir,
            order_export_dir=out / "04_export",
            instrument_resolution_dir=(
                instrument_resolution_dir
                if instrument_resolution is not None
                else None
            ),
            mapping_draft_dir=config.broker_mapping_draft_dir,
            mapped_orders_dir=config.broker_mapped_orders_dir,
            upload_pack_dir=out / "05_upload_pack",
            halt_export_dir=config.broker_halt_export_dir,
            reconciliation_dir=config.broker_reconciliation_dir,
            runtime_session_dir=config.broker_runtime_session_dir,
            vendor_market_data_batch_dir=config.broker_vendor_data_readiness_dir,
            thresholds=BrokerReadinessThresholds(
                adapter=config.adapter,
                expected_market=str(launch.summary.iloc[0].get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
                expected_vendor_data_kind="ticks",
                require_reviewed_schema=config.require_reviewed_schema,
                require_schema_audit=config.require_broker_schema_audit,
                require_order_export=True,
                require_instrument_resolution=config.require_broker_instrument_resolution,
                require_mapping_draft=config.require_broker_mapping_draft,
                require_mapped_orders=config.require_broker_mapped_orders,
                require_upload_pack=True,
                require_halt_export=config.require_broker_halt_export,
                require_reconciliation=config.require_broker_reconciliation,
                require_runtime_session=config.require_broker_runtime_session,
            ),
        )
        components.append(
            _component("broker_readiness", broker_readiness.ready, broker_readiness_dir, broker_readiness.summary)
        )
    else:
        components.append(
            _skipped_component("broker_readiness", out / "06_broker_readiness", "upload_pack_not_available")
        )

    component_frame = pd.DataFrame(components)
    summary = _summary(
        component_frame,
        config,
        order_plan=order_plan,
        instrument_resolution=instrument_resolution,
        order_export=export,
        upload_pack=upload,
        broker_readiness=broker_readiness,
    )
    component_frame.to_csv(out / "parity_launch_pipeline_components.csv", index=False)
    summary.to_csv(out / "parity_launch_pipeline_summary.csv", index=False)
    order_plan_manifest = order_plan_dir / "manifest.json"
    manifest_inputs = {
        "promotion": promotion,
        "promotion_manifest": promotion / "manifest.json",
        "order_plan_manifest": order_plan_manifest,
        "order_plan_dependencies": manifest_dependency_paths(
            order_plan_manifest
        ),
    }
    if instrument_resolution is not None:
        instrument_resolution_manifest = (
            instrument_resolution_dir / "manifest.json"
        )
        manifest_inputs.update(
            {
                "instrument_resolution_manifest": instrument_resolution_manifest,
                "instrument_resolution_dependencies": manifest_dependency_paths(
                    instrument_resolution_manifest
                ),
            }
        )
    write_experiment_manifest(
        out,
        run_type="parity_launch_pipeline",
        parameters={
            "strategy": str(summary.iloc[0].get("strategy", PARITY_BOX_STRATEGY)),
            "market": str(summary.iloc[0].get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
            "config": asdict(config),
        },
        inputs=manifest_inputs,
        extra={
            "order_plan_promotion_manifest_current": bool(
                summary.iloc[0].get(
                    "order_plan_promotion_manifest_current",
                    False,
                )
            ),
            "broker_instrument_resolution_required": bool(
                config.require_broker_instrument_resolution
            ),
            "broker_instrument_resolution_ready": bool(
                instrument_resolution is not None
                and instrument_resolution.ready
            ),
        },
    )
    return ParityLaunchPipelineReport(
        order_plan,
        instrument_resolution,
        staging,
        launch,
        export,
        upload,
        broker_readiness,
        component_frame,
        summary,
        out,
    )


def _order_plan_ready(report: ParityOrderPlanReport) -> bool:
    if not report.ready or report.orders.empty:
        return False
    return int(report.summary.iloc[0].get("orders", 0)) > 0


def _staging_ready(report: OrderStagingReport) -> bool:
    if not report.passed or report.summary.empty:
        return False
    return int(report.summary.iloc[0].get("accepted_orders", 0)) > 0


def _component(name: str, ready: bool, artifact_dir: Path, summary: pd.DataFrame) -> dict[str, object]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "component": name,
        "status": "ready" if ready else "not_ready",
        "ready": bool(ready),
        "artifact_dir": str(artifact_dir),
        "orders": _int(row.get("orders", row.get("accepted_orders", 0))),
        "failed_checks": _int(row.get("failed_checks", row.get("rejected_orders", 0))),
        "recommendation": str(row.get("recommendation", "")),
        "reason": "",
    }


def _skipped_component(name: str, artifact_dir: Path, reason: str) -> dict[str, object]:
    return {
        "component": name,
        "status": "skipped",
        "ready": False,
        "artifact_dir": str(artifact_dir),
        "orders": 0,
        "failed_checks": 1,
        "recommendation": "fix_upstream_gate",
        "reason": reason,
    }


def _missing_component(
    name: str,
    artifact_dir: Path,
    reason: str,
) -> dict[str, object]:
    return {
        "component": name,
        "status": "not_ready",
        "ready": False,
        "artifact_dir": str(artifact_dir),
        "orders": 0,
        "failed_checks": 1,
        "recommendation": "provide_broker_instrument_master",
        "reason": reason,
    }


def _summary(
    components: pd.DataFrame,
    config: ParityLaunchPipelineConfig,
    *,
    order_plan: ParityOrderPlanReport,
    instrument_resolution: BrokerInstrumentResolutionReport | None = None,
    order_export: OrderExportReport | None = None,
    upload_pack: OrderUploadPackReport | None = None,
    broker_readiness: BrokerReadinessReport | None = None,
) -> pd.DataFrame:
    ready = bool(components["ready"].astype(bool).all()) if not components.empty else False
    failed = int((~components["ready"].astype(bool)).sum()) if not components.empty else 0
    skipped = int((components["status"] == "skipped").sum()) if not components.empty else 0
    order_row = order_plan.summary.iloc[0] if not order_plan.summary.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": str(order_row.get("strategy", PARITY_BOX_STRATEGY)),
                "market": str(order_row.get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
                "direction": str(order_row.get("direction", "")),
                "leg_family": str(order_row.get("leg_family", "")),
                "adapter": config.adapter,
                "mode": config.mode,
                "components": int(len(components)),
                "ready_components": int(components["ready"].astype(bool).sum()) if not components.empty else 0,
                "failed_components": failed,
                "skipped_components": skipped,
                "order_plan_promotion_manifest_current": bool(
                    order_row.get(
                        "promotion_manifest_current",
                        False,
                    )
                ),
                "order_plan_promotion_manifest_error": str(
                    order_row.get("promotion_manifest_error", "")
                ),
                **_instrument_resolution_summary_fields(
                    instrument_resolution,
                    order_export,
                    upload_pack,
                    config,
                ),
                **_broker_readiness_summary_fields(broker_readiness),
                "recommendation": _recommendation(
                    ready,
                    instrument_resolution,
                ),
            }
        ]
    )


def _instrument_resolution_summary_fields(
    instrument_resolution: BrokerInstrumentResolutionReport | None,
    order_export: OrderExportReport | None,
    upload_pack: OrderUploadPackReport | None,
    config: ParityLaunchPipelineConfig,
) -> dict[str, object]:
    row = (
        instrument_resolution.summary.iloc[0]
        if instrument_resolution is not None
        and not instrument_resolution.summary.empty
        else pd.Series(dtype=object)
    )
    provided = instrument_resolution is not None and not row.empty
    ready = bool(
        provided
        and instrument_resolution is not None
        and instrument_resolution.ready
    )
    export_ready = _report_summary_bool(
        order_export,
        "instrument_resolution_ready",
    )
    upload_ready = _report_summary_bool(
        upload_pack,
        "instrument_resolution_ready",
    )
    lineage_ready = bool(ready and export_ready and upload_ready)
    return {
        "broker_instrument_resolution_required": bool(
            config.require_broker_instrument_resolution
        ),
        "broker_instrument_resolution_provided": provided,
        "broker_instrument_resolution_ready": ready,
        "broker_instrument_resolution_orders": _int(
            row.get("orders", 0)
        ),
        "broker_instrument_resolved_orders": _int(
            row.get("resolved_orders", 0)
        ),
        "broker_instrument_unresolved_orders": _int(
            row.get("unresolved_orders", 0)
        ),
        "broker_instrument_complete_leg_groups": _int(
            row.get("complete_leg_groups", 0)
        ),
        "broker_instrument_leg_groups": _int(
            row.get("leg_groups", 0)
        ),
        "broker_contract_export_ready": export_ready,
        "broker_contract_upload_ready": upload_ready,
        "broker_contract_lineage_ready": lineage_ready,
        "broker_contract_ready": lineage_ready,
    }


def _report_summary_bool(
    report: OrderExportReport | OrderUploadPackReport | None,
    column: str,
) -> bool:
    if report is None or report.summary.empty:
        return False
    return bool(report.summary.iloc[0].get(column, False))


def _recommendation(
    ready: bool,
    instrument_resolution: BrokerInstrumentResolutionReport | None,
) -> str:
    if not ready:
        return "keep_in_research"
    if (
        instrument_resolution is not None
        and instrument_resolution.ready
    ):
        return "broker_resolved_paper_or_shadow_handoff"
    return "paper_or_shadow_handoff_instrument_resolution_unproven"


def _broker_readiness_summary_fields(broker_readiness: BrokerReadinessReport | None) -> dict[str, object]:
    row = (
        broker_readiness.summary.iloc[0]
        if broker_readiness is not None and not broker_readiness.summary.empty
        else pd.Series(dtype=object)
    )
    return {
        "broker_readiness_provided": broker_readiness is not None and not row.empty,
        "broker_readiness_ready": bool(broker_readiness.ready) if broker_readiness is not None else False,
        "broker_readiness_route_readiness_ready": bool(row.get("route_readiness_ready", False)),
        "broker_readiness_route_readiness_strategy": str(row.get("route_readiness_strategy", "")),
        "broker_readiness_route_readiness_market": str(row.get("route_readiness_market", "")),
        "broker_readiness_route_readiness_gap_pairs": _int(row.get("route_readiness_gap_pairs", 0)),
        "broker_readiness_route_readiness_ops_launch_controls_present": bool(
            row.get("route_readiness_ops_launch_controls_present", False)
        ),
        "broker_readiness_route_readiness_ops_launch_controls_blocked_pairs": _int(
            row.get("route_readiness_ops_launch_controls_blocked_pairs", 0)
        ),
        "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": _int(
            row.get("route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0)
        ),
        "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": _int(
            row.get("route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs", 0)
        ),
        "broker_readiness_route_broker_route_readiness_provided": bool(
            row.get("route_broker_route_readiness_provided", False)
        ),
        "broker_readiness_route_broker_route_readiness_ready": bool(
            row.get("route_broker_route_readiness_ready", False)
        ),
        "broker_readiness_route_broker_route_readiness_strategy": str(
            row.get("route_broker_route_readiness_strategy", "")
        ),
        "broker_readiness_route_broker_route_readiness_market": str(
            row.get("route_broker_route_readiness_market", "")
        ),
        "broker_readiness_route_broker_route_readiness_gap_pairs": _int(
            row.get("route_broker_route_readiness_gap_pairs", 0)
        ),
        "broker_readiness_route_broker_route_readiness_ops_launch_controls_ready": bool(
            row.get("route_broker_route_readiness_ops_launch_controls_ready", False)
        ),
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _int(
            row.get("route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0)
        ),
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _int(
            row.get("route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0)
        ),
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": _int(
            row.get("route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0)
        ),
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": _int(
            row.get("route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0)
        ),
    }


def _validate_config(config: ParityLaunchPipelineConfig) -> None:
    if config.mode not in {"paper", "shadow"}:
        raise ValueError("mode must be 'paper' or 'shadow'")
    if not str(config.symbol_prefix).strip():
        raise ValueError("symbol_prefix must not be blank")
    if not str(config.future_instrument_id).strip():
        raise ValueError("future_instrument_id must not be blank")
    if config.qty is not None and config.qty <= 0:
        raise ValueError("qty must be positive")
    if config.price_offset_ticks < 0:
        raise ValueError("price_offset_ticks must be non-negative")
    if config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if config.max_order_qty is not None and config.max_order_qty <= 0:
        raise ValueError("max_order_qty must be positive")
    if config.max_notional is not None and config.max_notional <= 0:
        raise ValueError("max_notional must be positive")
    if config.price_band_pct is not None and config.price_band_pct < 0:
        raise ValueError("price_band_pct must be non-negative")
    if config.max_orders is not None and config.max_orders <= 0:
        raise ValueError("max_orders must be positive")
    if config.contract_multiplier <= 0:
        raise ValueError("contract_multiplier must be positive")
    if (
        config.broker_instrument_master_path is not None
        and not str(config.broker_instrument_master_path).strip()
    ):
        raise ValueError(
            "broker_instrument_master_path must not be blank"
        )


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0
