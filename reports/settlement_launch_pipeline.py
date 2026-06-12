from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from adapters.order_export import OrderExportConfig, OrderExportReport, write_order_export
from adapters.order_upload_pack import (
    OrderUploadPackConfig,
    OrderUploadPackReport,
    write_order_upload_pack,
)
from adapters.orders import OrderStagingLimits, OrderStagingReport, write_staged_orders
from reports.launch import LaunchBundleReport, LaunchThresholds, write_launch_bundle
from reports.manifest import write_experiment_manifest
from reports.settlement_order_plan import (
    SettlementOrderPlanConfig,
    SettlementOrderPlanReport,
    write_settlement_order_plan,
)


@dataclass(frozen=True)
class SettlementLaunchPipelineConfig:
    adapter: str = "arrow_money"
    mode: str = "shadow"
    route_tag: str | None = None
    symbol_prefix: str = "NIFTY"
    qty: int | None = None
    price_offset_ticks: float = 0.0
    tick_size: float = 0.05
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    max_orders: int | None = None
    contract_multiplier: float = 1.0
    product: str = "MIS"
    exchange: str = "NFO"
    require_reviewed_schema: bool = True


@dataclass(frozen=True)
class SettlementLaunchPipelineReport:
    order_plan: SettlementOrderPlanReport | None
    staging: OrderStagingReport | None
    launch: LaunchBundleReport | None
    export: OrderExportReport | None
    upload: OrderUploadPackReport | None
    components: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_settlement_launch_pipeline(
    promotion_dir: str | Path,
    *,
    output_dir: str | Path,
    config: SettlementLaunchPipelineConfig | None = None,
) -> SettlementLaunchPipelineReport:
    config = config or SettlementLaunchPipelineConfig()
    _validate_config(config)
    promotion = Path(promotion_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    components: list[dict[str, object]] = []

    order_plan_dir = out / "01_order_plan"
    order_plan = write_settlement_order_plan(
        promotion,
        output_dir=order_plan_dir,
        config=SettlementOrderPlanConfig(
            symbol_prefix=config.symbol_prefix,
            qty=config.qty,
            price_offset_ticks=config.price_offset_ticks,
            tick_size=config.tick_size,
        ),
    )
    components.append(_component("order_plan", order_plan.ready, order_plan_dir, order_plan.summary))

    staging = None
    launch = None
    export = None
    upload = None

    if _order_plan_ready(order_plan):
        staging_dir = out / "02_staged_orders"
        staging = write_staged_orders(
            order_plan_dir / "settlement_order_candidates.csv",
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
        components.append(_skipped_component("staged_orders", out / "02_staged_orders", "order_plan_not_ready"))

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
            ),
        )
        components.append(_component("upload_pack", upload.ready, upload_dir, upload.summary))
    else:
        components.append(_skipped_component("upload_pack", out / "05_upload_pack", "export_not_ready"))

    component_frame = pd.DataFrame(components)
    summary = _summary(component_frame, config)
    component_frame.to_csv(out / "settlement_launch_pipeline_components.csv", index=False)
    summary.to_csv(out / "settlement_launch_pipeline_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="settlement_launch_pipeline",
        parameters={"config": asdict(config)},
        inputs={"promotion": promotion},
    )
    return SettlementLaunchPipelineReport(order_plan, staging, launch, export, upload, component_frame, summary, out)


def _order_plan_ready(report: SettlementOrderPlanReport) -> bool:
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


def _summary(components: pd.DataFrame, config: SettlementLaunchPipelineConfig) -> pd.DataFrame:
    ready = bool(components["ready"].astype(bool).all()) if not components.empty else False
    failed = int((~components["ready"].astype(bool)).sum()) if not components.empty else 0
    skipped = int((components["status"] == "skipped").sum()) if not components.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "mode": config.mode,
                "components": int(len(components)),
                "ready_components": int(components["ready"].astype(bool).sum()) if not components.empty else 0,
                "failed_components": failed,
                "skipped_components": skipped,
                "recommendation": "paper_or_shadow_handoff" if ready else "keep_in_research",
            }
        ]
    )


def _validate_config(config: SettlementLaunchPipelineConfig) -> None:
    if config.mode not in {"paper", "shadow"}:
        raise ValueError("mode must be 'paper' or 'shadow'")
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


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0
