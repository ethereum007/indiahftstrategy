from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from adapters.broker_readiness import (
    BrokerReadinessReport,
    BrokerReadinessThresholds,
    write_broker_readiness_report,
)
from adapters.order_export import OrderExportConfig, OrderExportReport, write_order_export
from adapters.order_upload_pack import OrderUploadPackConfig, OrderUploadPackReport, write_order_upload_pack
from adapters.orders import OrderStagingLimits, OrderStagingReport, write_staged_orders
from reports.launch import LaunchBundleReport, LaunchThresholds, write_launch_bundle
from reports.manifest import write_experiment_manifest
from reports.quote_lifecycle import QuoteLifecycleReport, QuoteLifecycleThresholds, write_quote_lifecycle_plan


@dataclass(frozen=True)
class SurfaceMMLaunchPipelineConfig:
    adapter: str = "arrow_money"
    mode: str = "shadow"
    route_tag: str | None = None
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    max_orders: int | None = None
    contract_multiplier: float = 1.0
    product: str = "MIS"
    exchange: str = "NFO"
    quote_ttl_ns: int | None = None
    max_quote_order_messages: int | None = None
    max_active_quotes: int | None = None
    max_quote_replaces: int | None = None
    max_quote_cancels: int | None = None
    max_quote_messages_per_snapshot: int | None = None
    expected_quote_fills: int | None = None
    max_quote_otr: float | None = None
    require_reviewed_schema: bool = True
    broker_schema_audit_dir: str | Path | None = None
    broker_mapping_draft_dir: str | Path | None = None
    broker_mapped_orders_dir: str | Path | None = None
    broker_halt_export_dir: str | Path | None = None
    broker_reconciliation_dir: str | Path | None = None
    require_broker_schema_audit: bool = False
    require_broker_mapping_draft: bool = False
    require_broker_mapped_orders: bool = False
    require_broker_halt_export: bool = False
    require_broker_reconciliation: bool = False


@dataclass(frozen=True)
class SurfaceMMLaunchPipelineReport:
    quote_lifecycle: QuoteLifecycleReport | None
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
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def write_surface_mm_launch_pipeline(
    surface_pipeline_dir: str | Path,
    *,
    output_dir: str | Path,
    config: SurfaceMMLaunchPipelineConfig | None = None,
) -> SurfaceMMLaunchPipelineReport:
    config = config or SurfaceMMLaunchPipelineConfig()
    _validate_config(config)
    surface_pipeline = Path(surface_pipeline_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    quotes_path = surface_pipeline / "01_quotes" / "surface_quotes.csv"
    quote_review_dir = surface_pipeline / "02_quote_review"
    promotion_dir = surface_pipeline / "05_promotion"
    if not quotes_path.exists():
        raise FileNotFoundError(f"surface quotes not found: {quotes_path}")
    if not (quote_review_dir / "quote_risk_summary.csv").exists():
        raise FileNotFoundError(f"quote risk summary not found: {quote_review_dir / 'quote_risk_summary.csv'}")
    if not (promotion_dir / "promotion_summary.csv").exists():
        raise FileNotFoundError(f"surface promotion summary not found: {promotion_dir / 'promotion_summary.csv'}")

    components: list[dict[str, object]] = []
    quote_lifecycle = None
    staging = None
    launch = None
    export = None
    upload = None
    broker_readiness = None

    quote_lifecycle_dir = out / "00_quote_lifecycle"
    quote_lifecycle = write_quote_lifecycle_plan(
        quotes_path,
        output_dir=quote_lifecycle_dir,
        thresholds=QuoteLifecycleThresholds(
            quote_ttl_ns=config.quote_ttl_ns,
            max_order_messages=config.max_quote_order_messages,
            max_active_quotes=config.max_active_quotes,
            max_replaces=config.max_quote_replaces,
            max_cancels=config.max_quote_cancels,
            max_messages_per_snapshot=config.max_quote_messages_per_snapshot,
            expected_fills=config.expected_quote_fills,
            max_order_to_trade_ratio=config.max_quote_otr,
        ),
        quote_risk_review_dir=quote_review_dir,
        require_quote_risk_review=True,
    )
    components.append(_component("quote_lifecycle", quote_lifecycle.ready, quote_lifecycle_dir, quote_lifecycle.summary))

    staging_dir = out / "01_staged_orders"
    if quote_lifecycle.ready:
        staging = write_staged_orders(
            quote_lifecycle_dir / "quote_lifecycle_route_orders.csv",
            output_dir=staging_dir,
            source="surface_quotes",
            adapter=config.adapter,
            limits=OrderStagingLimits(
                max_order_qty=config.max_order_qty,
                max_notional=config.max_notional,
                price_band_pct=config.price_band_pct,
                max_orders=config.max_orders,
                contract_multiplier=config.contract_multiplier,
            ),
            quote_risk_review_dir=quote_review_dir,
            require_quote_risk_review=True,
        )
        components.append(_component("staged_orders", _staging_ready(staging), staging_dir, staging.summary))
    else:
        components.append(_skipped_component("staged_orders", staging_dir, "quote_lifecycle_not_ready"))

    if staging is not None and _staging_ready(staging):
        launch_dir = out / "02_launch"
        launch = write_launch_bundle(
            promotion_dir=promotion_dir,
            staged_orders_dir=staging_dir,
            output_dir=launch_dir,
            mode=config.mode,
            adapter=config.adapter,
            thresholds=LaunchThresholds(
                max_order_notional=config.max_notional,
                require_quote_risk_review=True,
            ),
        )
        components.append(_component("launch", launch.ready, launch_dir, launch.summary))
    else:
        components.append(_skipped_component("launch", out / "02_launch", "staged_orders_not_ready"))

    if launch is not None and launch.ready:
        export_dir = out / "03_export"
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
        components.append(_skipped_component("export", out / "03_export", "launch_not_ready"))

    if export is not None and export.ready:
        upload_dir = out / "04_upload_pack"
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
        components.append(_skipped_component("upload_pack", out / "04_upload_pack", "export_not_ready"))

    if export is not None and upload is not None:
        broker_readiness_dir = out / "05_broker_readiness"
        broker_readiness = write_broker_readiness_report(
            output_dir=broker_readiness_dir,
            schema_audit_dir=config.broker_schema_audit_dir,
            order_export_dir=out / "03_export",
            mapping_draft_dir=config.broker_mapping_draft_dir,
            mapped_orders_dir=config.broker_mapped_orders_dir,
            upload_pack_dir=out / "04_upload_pack",
            halt_export_dir=config.broker_halt_export_dir,
            reconciliation_dir=config.broker_reconciliation_dir,
            thresholds=BrokerReadinessThresholds(
                adapter=config.adapter,
                require_reviewed_schema=config.require_reviewed_schema,
                require_schema_audit=config.require_broker_schema_audit,
                require_order_export=True,
                require_mapping_draft=config.require_broker_mapping_draft,
                require_mapped_orders=config.require_broker_mapped_orders,
                require_upload_pack=True,
                require_halt_export=config.require_broker_halt_export,
                require_reconciliation=config.require_broker_reconciliation,
            ),
        )
        components.append(
            _component("broker_readiness", broker_readiness.ready, broker_readiness_dir, broker_readiness.summary)
        )
    else:
        components.append(_skipped_component("broker_readiness", out / "05_broker_readiness", "upload_pack_not_available"))

    component_frame = pd.DataFrame(components)
    summary = _summary(component_frame, config)
    component_frame.to_csv(out / "surface_mm_launch_pipeline_components.csv", index=False)
    summary.to_csv(out / "surface_mm_launch_pipeline_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="surface_mm_launch_pipeline",
        parameters={"config": asdict(config)},
        inputs={"surface_pipeline": surface_pipeline},
    )
    return SurfaceMMLaunchPipelineReport(quote_lifecycle, staging, launch, export, upload, broker_readiness, component_frame, summary, out)


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
        "orders": _int(row.get("orders", row.get("accepted_orders", row.get("order_messages", 0)))),
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


def _summary(components: pd.DataFrame, config: SurfaceMMLaunchPipelineConfig) -> pd.DataFrame:
    ready = bool(components["ready"].astype(bool).all()) if not components.empty else False
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "mode": config.mode,
                "components": int(len(components)),
                "ready_components": int(components["ready"].astype(bool).sum()) if not components.empty else 0,
                "failed_components": int((~components["ready"].astype(bool)).sum()) if not components.empty else 0,
                "skipped_components": int((components["status"] == "skipped").sum()) if not components.empty else 0,
                "recommendation": "paper_or_shadow_handoff" if ready else "keep_in_research",
            }
        ]
    )


def _validate_config(config: SurfaceMMLaunchPipelineConfig) -> None:
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
    for attr in (
        "quote_ttl_ns",
        "max_quote_order_messages",
        "max_active_quotes",
        "max_quote_replaces",
        "max_quote_cancels",
        "max_quote_messages_per_snapshot",
        "expected_quote_fills",
    ):
        value = getattr(config, attr)
        if value is not None and value < 0:
            raise ValueError(f"{attr} must be non-negative")
    if config.max_quote_otr is not None and config.max_quote_otr <= 0:
        raise ValueError("max_quote_otr must be positive")


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0
