from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.vendor_market_data import (
    select_vendor_market_data_batch_source,
    vendor_market_data_batch_source_active,
)


@dataclass(frozen=True)
class RouteEnableThresholds:
    target_mode: str = "live_dryrun"
    require_cutover_ready: bool = True
    require_upload_ready: bool = True
    require_order_export_ready: bool = False
    require_adapter_match: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    min_orders: int = 1


@dataclass(frozen=True)
class RouteEnableReport:
    packet: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_route_enable_packet(
    *,
    cutover_summary: pd.DataFrame,
    cutover_config: dict[str, Any] | None = None,
    upload_summary: pd.DataFrame,
    order_export_summary: pd.DataFrame | None = None,
    thresholds: RouteEnableThresholds | None = None,
) -> RouteEnableReport:
    thresholds = thresholds or RouteEnableThresholds()
    _validate_thresholds(thresholds)
    cutover_summary = _require_nonempty(cutover_summary, "cutover_summary")
    upload_summary = _require_nonempty(upload_summary, "upload_summary")
    order_export_summary = _optional_frame(order_export_summary)
    cutover_config = cutover_config or {}

    state = {
        "cutover": _cutover_state(cutover_summary.iloc[0], cutover_config),
        "upload": _upload_state(upload_summary.iloc[0]),
        "order_export": _order_export_state(order_export_summary),
    }
    checks = _checks(state, thresholds)
    packet = _packet(state, thresholds, checks)
    summary = _summary(packet.iloc[0], checks)
    config = _config(packet.iloc[0], thresholds, checks)
    return RouteEnableReport(packet=packet, checks=checks, summary=summary, config=config)


def write_route_enable_packet(
    *,
    cutover_dir: str | Path,
    upload_pack_dir: str | Path,
    output_dir: str | Path,
    order_export_dir: str | Path | None = None,
    thresholds: RouteEnableThresholds | None = None,
) -> RouteEnableReport:
    cutover = Path(cutover_dir)
    upload = Path(upload_pack_dir)
    cutover_config_path = cutover / "cutover_config.json" if cutover.is_dir() else Path(cutover_dir)
    upload_summary_path = _summary_path(
        upload,
        "broker_upload_summary.csv",
        fallback_dirs=("05_upload_pack", "04_upload_pack"),
    )
    order_export_summary_path = (
        _summary_path(
            order_export_dir,
            "broker_order_summary.csv",
            fallback_dirs=("04_export", "03_export"),
        )
        if order_export_dir is not None
        else None
    )
    if not cutover_config_path.exists():
        raise FileNotFoundError(f"cutover config not found: {cutover_config_path}")
    cutover_summary_path = (
        cutover / "cutover_summary.csv" if cutover.is_dir() else cutover_config_path.with_name("cutover_summary.csv")
    )
    cutover_manifest_path = _sidecar_path(cutover_dir, "manifest.json")
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    broker_readiness_config_path = _manifest_input_path(cutover_manifest_path, "broker_readiness_config")
    if broker_readiness_config_path is not None:
        cutover_config = _with_broker_readiness_config_vendor_market_data_batch(
            cutover_config,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    report = evaluate_route_enable_packet(
        cutover_summary=_read_required(cutover_summary_path, "cutover_summary"),
        cutover_config=cutover_config,
        upload_summary=_read_required(upload_summary_path, "broker_upload_summary"),
        order_export_summary=(
            _read_optional(order_export_summary_path) if order_export_summary_path is not None else None
        ),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.packet.to_csv(out / "route_enable_packet.csv", index=False)
    report.checks.to_csv(out / "route_enable_checks.csv", index=False)
    report.summary.to_csv(out / "route_enable_summary.csv", index=False)
    (out / "route_enable_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "cutover_summary": cutover_summary_path,
        "cutover_config": cutover_config_path,
        "upload_pack": upload_summary_path,
    }
    if cutover_manifest_path is not None:
        inputs["cutover_manifest"] = cutover_manifest_path
    if order_export_summary_path is not None:
        inputs["order_export"] = (
            order_export_summary_path if order_export_summary_path.exists() else Path(order_export_dir)
        )
    write_experiment_manifest(
        out,
        run_type="route_enable_packet",
        parameters={"thresholds": asdict(thresholds or RouteEnableThresholds())},
        inputs=inputs,
    )
    return RouteEnableReport(report.packet, report.checks, report.summary, report.config, out)


def _checks(state: dict[str, dict[str, Any]], thresholds: RouteEnableThresholds) -> pd.DataFrame:
    cutover = state["cutover"]
    upload = state["upload"]
    order_export = state["order_export"]
    target_mode = _identity_key(thresholds.target_mode)
    upload_orders = int(upload["orders"])
    max_orders = int(cutover["max_orders_per_session"])
    max_notional = float(cutover["max_notional_per_session"])
    export_notional = float(order_export["total_notional"])
    route_readiness_required = _route_readiness_required(thresholds, cutover)
    route_readiness_active = bool(route_readiness_required or cutover["route_readiness_provided"])
    checks = [
        _check(
            "cutover_ready",
            cutover["ready"],
            "is",
            True,
            bool(cutover["ready"]) or not thresholds.require_cutover_ready,
            "cutover gate is not ready",
        ),
        _check(
            "target_mode_matches",
            cutover["target_mode"],
            "==",
            target_mode,
            bool(cutover["target_mode"] and cutover["target_mode"] == target_mode),
            "cutover target mode does not match route-enable target mode",
        ),
        _check(
            "cutover_dispatch_roundtrip_provided",
            cutover["dispatch_roundtrip_provided"],
            "is",
            True,
            bool(cutover["dispatch_roundtrip_provided"]) or not _dispatch_roundtrip_required(thresholds),
            "route enable requires cutover with dry-run dispatch round-trip proof",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_provided",
            cutover["route_dispatch_roundtrip_provided"],
            "is",
            True,
            bool(cutover["route_dispatch_roundtrip_provided"]) or not _route_dispatch_roundtrip_required(
                thresholds,
                cutover,
            ),
            "route enable requires cutover with dispatch route proof",
        ),
    ]
    if route_readiness_required:
        checks.append(
            _check(
                "cutover_route_readiness_provided",
                cutover["route_readiness_provided"],
                "is",
                True,
                bool(cutover["route_readiness_provided"]),
                "route enable requires cutover with route-readiness proof",
            )
        )
    if route_readiness_active:
        checks.extend(_route_readiness_checks(cutover))
    checks.extend(
        [
            _check(
                "upload_ready",
                upload["ready"],
                "is",
                True,
                bool(upload["ready"]) or not thresholds.require_upload_ready,
                "broker upload pack is not ready",
            ),
            _check(
                "upload_orders_min",
                upload_orders,
                ">=",
                thresholds.min_orders,
                upload_orders >= thresholds.min_orders,
                "broker upload pack does not contain enough orders",
            ),
            _check(
                "upload_orders_within_cutover_limit",
                upload_orders,
                "<=",
                max_orders,
                upload_orders <= max_orders,
                "broker upload order count exceeds cutover limit",
            ),
            _check(
                "upload_adapter_matches",
                upload["adapter"],
                "==",
                cutover["adapter"],
                (not thresholds.require_adapter_match) or upload["adapter"] == cutover["adapter"],
                "broker upload adapter does not match cutover adapter",
            ),
        ]
    )
    if _strategy_portfolio_active(cutover):
        checks.extend(
            [
                _check(
                    "strategy_portfolio_ready",
                    cutover["strategy_portfolio_ready"],
                    "is",
                    True,
                    bool(cutover["strategy_portfolio_ready"]),
                    "cutover strategy portfolio allocation is not ready",
                ),
                _check(
                    "strategy_portfolio_allocation_eligible",
                    cutover["strategy_portfolio_selected_eligible"],
                    "is",
                    True,
                    bool(cutover["strategy_portfolio_selected_eligible"]),
                    "cutover strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "strategy_portfolio_strategy_matches",
                    cutover["strategy_portfolio_selected_strategy"],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover["strategy_portfolio_selected_strategy"]
                        and cutover["strategy"]
                        and cutover["strategy_portfolio_selected_strategy"] == cutover["strategy"]
                    ),
                    "cutover strategy portfolio strategy does not match route strategy",
                ),
                _check(
                    "strategy_portfolio_market_matches",
                    cutover["strategy_portfolio_selected_market"],
                    "==",
                    cutover["market"],
                    bool(
                        cutover["strategy_portfolio_selected_market"]
                        and cutover["market"]
                        and cutover["strategy_portfolio_selected_market"] == cutover["market"]
                    ),
                    "cutover strategy portfolio market does not match route market",
                ),
                _check(
                    "strategy_portfolio_allocation_notional",
                    cutover["strategy_portfolio_selected_allocation_notional"],
                    ">",
                    0.0,
                    float(cutover["strategy_portfolio_selected_allocation_notional"]) > 0.0,
                    "cutover strategy portfolio allocation notional must be positive",
                ),
            ]
        )
    if _dispatch_roundtrip_required(thresholds) or cutover["dispatch_roundtrip_provided"]:
        checks.extend(_dispatch_roundtrip_checks(cutover, target_mode))
    if _route_dispatch_roundtrip_required(thresholds, cutover):
        checks.extend(_route_dispatch_roundtrip_checks(cutover, target_mode))
    if _shadow_broker_readiness_active(cutover):
        checks.extend(_shadow_broker_readiness_checks(cutover))
    if _broker_shadow_broker_readiness_active(cutover):
        checks.extend(_broker_shadow_broker_readiness_checks(cutover))
    if _broker_vendor_data_readiness_active(cutover):
        checks.extend(_broker_vendor_data_readiness_checks(cutover))
    if _broker_vendor_market_data_batch_active(cutover):
        checks.extend(_broker_vendor_market_data_batch_checks(cutover))
    if thresholds.require_order_export_ready:
        checks.append(
            _check(
                "order_export_provided",
                order_export["provided"],
                "is",
                True,
                bool(order_export["provided"]),
                "order export summary is required but missing",
            )
        )
    if order_export["provided"]:
        checks.extend(
            [
                _check(
                    "order_export_ready",
                    order_export["ready"],
                    "is",
                    True,
                    bool(order_export["ready"]) or not thresholds.require_order_export_ready,
                    "order export is not ready",
                ),
                _check(
                    "order_export_adapter_matches",
                    order_export["adapter"],
                    "==",
                    cutover["adapter"],
                    (not thresholds.require_adapter_match) or order_export["adapter"] == cutover["adapter"],
                    "order export adapter does not match cutover adapter",
                ),
                _check(
                    "order_export_orders_match_upload",
                    order_export["orders"],
                    "==",
                    upload_orders,
                    int(order_export["orders"]) == upload_orders,
                    "order export and upload pack order counts differ",
                ),
                _check(
                    "order_export_notional_within_cutover_limit",
                    export_notional,
                    "<=",
                    max_notional,
                    export_notional <= max_notional,
                    "order export notional exceeds cutover limit",
                ),
            ]
        )
        if _strategy_portfolio_active(cutover):
            checks.append(
                _check(
                    "order_export_notional_within_strategy_portfolio_allocation",
                    export_notional,
                    "<=",
                    cutover["strategy_portfolio_selected_allocation_notional"],
                    export_notional <= float(cutover["strategy_portfolio_selected_allocation_notional"]),
                    "order export notional exceeds selected strategy portfolio allocation",
                )
            )
    return pd.DataFrame(checks)


def _route_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_route_readiness_ready",
            cutover["route_readiness_ready"],
            "is",
            True,
            bool(cutover["route_readiness_ready"]),
            "cutover route-readiness proof is not ready",
        ),
        _check(
            "cutover_route_readiness_strategy_matches",
            cutover["route_readiness_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["route_readiness_strategy"]
                and cutover["strategy"]
                and cutover["route_readiness_strategy"] == cutover["strategy"]
            ),
            "cutover route-readiness strategy does not match route strategy",
        ),
        _check(
            "cutover_route_readiness_market_matches",
            cutover["route_readiness_market"],
            "==",
            cutover["market"],
            bool(
                cutover["route_readiness_market"]
                and cutover["market"]
                and cutover["route_readiness_market"] == cutover["market"]
            ),
            "cutover route-readiness market does not match route market",
        ),
    ]


def _dispatch_roundtrip_checks(cutover: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_dispatch_roundtrip_ready",
            cutover["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(cutover["dispatch_roundtrip_ready"]),
            "cutover dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            "cutover_dispatch_roundtrip_target_mode_matches",
            cutover["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(cutover["dispatch_roundtrip_target_mode"] and cutover["dispatch_roundtrip_target_mode"] == target_mode),
            "cutover dispatch round-trip target mode does not match route target",
        ),
        _check(
            "cutover_dispatch_roundtrip_strategy_matches",
            cutover["dispatch_roundtrip_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["dispatch_roundtrip_strategy"]
                and cutover["strategy"]
                and cutover["dispatch_roundtrip_strategy"] == cutover["strategy"]
            ),
            "cutover dispatch round-trip strategy does not match route strategy",
        ),
        _check(
            "cutover_dispatch_roundtrip_market_matches",
            cutover["dispatch_roundtrip_market"],
            "==",
            cutover["market"],
            bool(
                cutover["dispatch_roundtrip_market"]
                and cutover["market"]
                and cutover["dispatch_roundtrip_market"] == cutover["market"]
            ),
            "cutover dispatch round-trip market does not match route market",
        ),
        _check(
            "cutover_dispatch_roundtrip_scenario_matches",
            cutover["dispatch_roundtrip_scenario_key"],
            "==",
            cutover["scenario_key"],
            bool(
                cutover["dispatch_roundtrip_scenario_key"]
                and cutover["scenario_key"]
                and cutover["dispatch_roundtrip_scenario_key"] == cutover["scenario_key"]
            ),
            "cutover dispatch round-trip scenario does not match route scenario",
        ),
        _check(
            "cutover_dispatch_roundtrip_missing_request_acks",
            cutover["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_missing_request_acks"]) <= 0,
            "cutover dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "cutover_dispatch_roundtrip_rejected_orders",
            cutover["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_rejected_orders"]) <= 0,
            "cutover dispatch round-trip has rejected orders",
        ),
        _check(
            "cutover_dispatch_roundtrip_unmatched_acks",
            cutover["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_unmatched_acks"]) <= 0,
            "cutover dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "cutover_dispatch_roundtrip_failed_checks",
            cutover["dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_failed_checks"]) <= 0,
            "cutover dispatch round-trip has failed component checks",
        ),
        _check(
            "cutover_route_enable_dispatch_roundtrip_failed_checks",
            cutover["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(cutover["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            "cutover carries failed route-enable dispatch round-trip checks",
        ),
    ]


def _route_dispatch_roundtrip_checks(cutover: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_route_dispatch_roundtrip_ready",
            cutover["route_dispatch_roundtrip_ready"],
            "is",
            True,
            bool(cutover["route_dispatch_roundtrip_ready"]),
            "cutover dispatch route proof is not ready",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_target_mode_matches",
            cutover["route_dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(
                cutover["route_dispatch_roundtrip_target_mode"]
                and cutover["route_dispatch_roundtrip_target_mode"] == target_mode
            ),
            "cutover dispatch route proof target mode does not match route target",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_strategy_matches",
            cutover["route_dispatch_roundtrip_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["route_dispatch_roundtrip_strategy"]
                and cutover["strategy"]
                and cutover["route_dispatch_roundtrip_strategy"] == cutover["strategy"]
            ),
            "cutover dispatch route proof strategy does not match route strategy",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_market_matches",
            cutover["route_dispatch_roundtrip_market"],
            "==",
            cutover["market"],
            bool(
                cutover["route_dispatch_roundtrip_market"]
                and cutover["market"]
                and cutover["route_dispatch_roundtrip_market"] == cutover["market"]
            ),
            "cutover dispatch route proof market does not match route market",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_scenario_matches",
            cutover["route_dispatch_roundtrip_scenario_key"],
            "==",
            cutover["scenario_key"],
            bool(
                cutover["route_dispatch_roundtrip_scenario_key"]
                and cutover["scenario_key"]
                and cutover["route_dispatch_roundtrip_scenario_key"] == cutover["scenario_key"]
            ),
            "cutover dispatch route proof scenario does not match route scenario",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_batch_id_provided",
            cutover["route_dispatch_roundtrip_batch_id"],
            "is not",
            "",
            bool(cutover["route_dispatch_roundtrip_batch_id"]),
            "cutover dispatch route proof batch id is missing",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_request_count_matches",
            f"{cutover['route_dispatch_roundtrip_requests']}/{cutover['route_dispatch_roundtrip_acked_orders']}",
            "==",
            f"{cutover['dispatch_roundtrip_requests']}/{cutover['dispatch_roundtrip_acked_orders']}",
            (
                int(cutover["route_dispatch_roundtrip_requests"]) == int(cutover["dispatch_roundtrip_requests"])
                and int(cutover["route_dispatch_roundtrip_acked_orders"])
                == int(cutover["dispatch_roundtrip_acked_orders"])
            ),
            "cutover dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_missing_request_acks",
            cutover["route_dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_missing_request_acks"]) <= 0,
            "cutover dispatch route proof has missing request acknowledgements",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_rejected_orders",
            cutover["route_dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_rejected_orders"]) <= 0,
            "cutover dispatch route proof has rejected orders",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_unmatched_acks",
            cutover["route_dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_unmatched_acks"]) <= 0,
            "cutover dispatch route proof has unmatched acknowledgements",
        ),
    ]


def _broker_vendor_market_data_batch_active(cutover: dict[str, Any]) -> bool:
    vendor = cutover["broker_dispatch_roundtrip_vendor_market_data_batch"]
    return bool(_to_bool(vendor["provided"]) or int(vendor["dataset_count"]) > 0)


def _broker_vendor_data_readiness_active(cutover: dict[str, Any]) -> bool:
    readiness = cutover["broker_vendor_data_readiness"]
    return bool(
        _to_bool(readiness["provided"])
        or _to_bool(readiness["ready"])
        or int(readiness["failed_checks"]) > 0
    )


def _broker_vendor_data_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    readiness = cutover["broker_vendor_data_readiness"]
    prefix = "cutover_broker_vendor_data_readiness"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(readiness["provided"]),
            "is",
            True,
            _to_bool(readiness["provided"]),
            "cutover broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(readiness["ready"]),
            "is",
            True,
            _to_bool(readiness["ready"]),
            "cutover broker-vendor readiness wrapper proof is not ready",
        ),
        _check(
            f"{prefix}_failed_checks",
            int(readiness["failed_checks"]),
            "<=",
            0,
            int(readiness["failed_checks"]) <= 0,
            "cutover broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _broker_vendor_market_data_batch_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    vendor = cutover["broker_dispatch_roundtrip_vendor_market_data_batch"]
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(vendor["provided"]),
            "is",
            True,
            _to_bool(vendor["provided"]),
            "cutover broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(vendor["ready"]),
            "is",
            True,
            _to_bool(vendor["ready"]),
            "cutover broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            f"{prefix}_adapter_matches",
            vendor["adapter"],
            "==",
            cutover["adapter"],
            bool(vendor["adapter"] and cutover["adapter"] and vendor["adapter"] == cutover["adapter"]),
            "cutover broker-readiness vendor market-data adapter does not match route adapter",
        ),
        _check(
            f"{prefix}_market_matches",
            vendor["market"],
            "==",
            cutover["market"],
            bool(vendor["market"] and cutover["market"] and vendor["market"] == cutover["market"]),
            "cutover broker-readiness vendor market-data market does not match route market",
        ),
        _check(
            f"{prefix}_manifest_run_type",
            vendor["manifest_run_type"],
            "==",
            "vendor_market_data_batch_pipeline",
            vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline",
            "cutover broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            f"{prefix}_dataset_count",
            int(vendor["dataset_count"]),
            ">",
            0,
            int(vendor["dataset_count"]) > 0,
            "cutover broker-readiness vendor market-data batch has no datasets",
        ),
        _check(
            f"{prefix}_failed_datasets",
            int(vendor["failed_datasets"]),
            "<=",
            0,
            int(vendor["failed_datasets"]) <= 0,
            "cutover broker-readiness vendor market-data batch has failed datasets",
        ),
        _check(
            f"{prefix}_source_files",
            int(vendor["unique_source_files"]),
            ">",
            0,
            int(vendor["unique_source_files"]) > 0,
            "cutover broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            f"{prefix}_header_fingerprints",
            int(vendor["unique_header_fingerprints"]),
            ">",
            0,
            int(vendor["unique_header_fingerprints"]) > 0,
            "cutover broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            f"{prefix}_source_file_fingerprint_coverage",
            float(vendor["source_file_fingerprint_coverage"]),
            ">=",
            1.0,
            float(vendor["source_file_fingerprint_coverage"]) >= 1.0,
            "cutover broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            f"{prefix}_min_mapping_coverage",
            float(vendor["min_mapping_coverage"]),
            ">=",
            1.0,
            float(vendor["min_mapping_coverage"]) >= 1.0,
            "cutover broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            f"{prefix}_mapping_drafts",
            int(vendor["unique_mapping_drafts"]),
            ">",
            0,
            int(vendor["unique_mapping_drafts"]) > 0,
            "cutover broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            f"{prefix}_mapping_sources",
            str(vendor["mapping_sources"]).strip(),
            "!=",
            "",
            bool(str(vendor["mapping_sources"]).strip()),
            "cutover broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            f"{prefix}_comparison_accepted",
            _to_bool(vendor["comparison_accepted"]),
            "is",
            True,
            _to_bool(vendor["comparison_accepted"]),
            "cutover broker-readiness vendor market-data comparison was not accepted",
        ),
        _check(
            f"{prefix}_comparison_failed_checks",
            int(vendor["comparison_failed_checks"]),
            "<=",
            0,
            int(vendor["comparison_failed_checks"]) <= 0,
            "cutover broker-readiness vendor market-data comparison has failed checks",
        ),
    ]


def _shadow_broker_readiness_active(cutover: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(cutover, key_prefix="")


def _shadow_broker_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        cutover,
        key_prefix="",
        check_prefix="cutover_shadow_broker",
        label="cutover shadow broker",
    )


def _broker_shadow_broker_readiness_active(cutover: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(cutover, key_prefix="broker_")


def _broker_shadow_broker_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        cutover,
        key_prefix="broker_",
        check_prefix="cutover_broker_shadow_broker",
        label="cutover broker-readiness shadow broker",
        check_provided=True,
    )


def _shadow_broker_readiness_active_for(cutover: dict[str, Any], *, key_prefix: str) -> bool:
    session_fields = (
        "readiness_sessions",
        "vendor_data_readiness_sessions",
        "route_readiness_sessions",
        "dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(cutover.get(_shadow_broker_key(key_prefix, "readiness_provided"), False))
        or any(int(cutover[_shadow_broker_key(key_prefix, field)]) > 0 for field in session_fields)
    )


def _shadow_broker_readiness_checks_for(
    cutover: dict[str, Any],
    *,
    key_prefix: str,
    check_prefix: str,
    label: str,
    check_provided: bool = False,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    if check_provided:
        checks.append(
            _check(
                f"{check_prefix}_readiness_provided",
                _to_bool(cutover[_shadow_broker_key(key_prefix, "readiness_provided")]),
                "is",
                True,
                _to_bool(cutover[_shadow_broker_key(key_prefix, "readiness_provided")]),
                f"{label} proof is active but not marked provided",
            )
        )
    sessions = int(cutover[_shadow_broker_key(key_prefix, "readiness_sessions")])
    if sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_readiness_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]) == sessions,
                    f"{label} readiness evidence is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_adapter_matches",
                    cutover[_shadow_broker_key(key_prefix, "adapter")],
                    "==",
                    cutover["adapter"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "adapter")]
                        and cutover[_shadow_broker_key(key_prefix, "adapter")] == cutover["adapter"]
                    ),
                    f"{label} adapter does not match route adapter",
                ),
                _check(
                    f"{check_prefix}_adapter_consistent",
                    int(cutover[_shadow_broker_key(key_prefix, "adapter_count")]),
                    "==",
                    1,
                    int(cutover[_shadow_broker_key(key_prefix, "adapter_count")]) == 1,
                    f"{label} adapter identity is missing or mixed",
                ),
            ]
        )
    vendor_sessions = int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_sessions")])
    if vendor_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_vendor_data_readiness_present_for_broker_sessions",
                    vendor_sessions,
                    "==",
                    sessions,
                    vendor_sessions == sessions,
                    f"{label} vendor-data wrapper proof is present for only some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_provided",
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")]),
                    "==",
                    sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_failed_checks",
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]) <= 0,
                    f"{label} vendor-data wrapper proof has failed checks",
                ),
            ]
        )
    route_sessions = int(cutover[_shadow_broker_key(key_prefix, "route_readiness_sessions")])
    if route_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_readiness_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]),
                    "==",
                    route_sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")])
                    == route_sessions,
                    f"{label} route-readiness proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_readiness_strategy_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_readiness_strategy")],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_readiness_strategy")]
                        and cutover[_shadow_broker_key(key_prefix, "route_readiness_strategy")] == cutover["strategy"]
                    ),
                    f"{label} route-readiness strategy does not match route strategy",
                ),
                _check(
                    f"{check_prefix}_route_readiness_market_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_readiness_market")],
                    "==",
                    cutover["market"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_readiness_market")]
                        and cutover[_shadow_broker_key(key_prefix, "route_readiness_market")] == cutover["market"]
                    ),
                    f"{label} route-readiness market does not match route market",
                ),
                _check(
                    f"{check_prefix}_route_readiness_gap_pairs",
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]) <= 0,
                    f"{label} route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_sessions")])
    if dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_dispatch_roundtrip_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")]),
                    "==",
                    dispatch_sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")])
                    == dispatch_sessions,
                    f"{label} dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_strategy_matches",
                    cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        and cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        == cutover["strategy"]
                    ),
                    f"{label} dispatch round-trip strategy does not match route strategy",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_market_matches",
                    cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")],
                    "==",
                    cutover["market"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")]
                        and cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")] == cutover["market"]
                    ),
                    f"{label} dispatch round-trip market does not match route market",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_scenario_consistent",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_missing_request_acks",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")])
                    <= 0,
                    f"{label} dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_rejected_orders",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]) <= 0,
                    f"{label} dispatch round-trip has rejected orders",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_unmatched_acks",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]) <= 0,
                    f"{label} dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_sessions")])
    if route_dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")]),
                    "==",
                    route_dispatch_sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")])
                    == route_dispatch_sessions,
                    f"{label} route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_strategy_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        and cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        == cutover["strategy"]
                    ),
                    f"{label} route dispatch round-trip strategy does not match route strategy",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_market_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")],
                    "==",
                    cutover["market"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        and cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        == cutover["market"]
                    ),
                    f"{label} route dispatch round-trip market does not match route market",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_scenario_consistent",
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _shadow_broker_key(key_prefix: str, suffix: str) -> str:
    return f"{key_prefix}shadow_broker_{suffix}"


def _packet(
    state: dict[str, dict[str, Any]],
    thresholds: RouteEnableThresholds,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    cutover = state["cutover"]
    upload = state["upload"]
    order_export = state["order_export"]
    ready = bool(checks["passed"].astype(bool).all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "route_enabled": ready,
                "route_state": "enabled" if ready else "disabled",
                "target_mode": cutover["target_mode"],
                "strategy": cutover["strategy"],
                "market": cutover["market"],
                "scenario_key": cutover["scenario_key"],
                "adapter": cutover["adapter"],
                "max_orders_per_session": int(cutover["max_orders_per_session"]),
                "max_notional_per_session": float(cutover["max_notional_per_session"]),
                "stop_loss": cutover["stop_loss"],
                "strategy_portfolio_required": cutover["strategy_portfolio_required"],
                "strategy_portfolio_provided": cutover["strategy_portfolio_provided"],
                "strategy_portfolio_ready": cutover["strategy_portfolio_ready"],
                "strategy_portfolio_deployment_mode": cutover["strategy_portfolio_deployment_mode"],
                "strategy_portfolio_allocation_mode": cutover["strategy_portfolio_allocation_mode"],
                "strategy_portfolio_capital_currency": cutover["strategy_portfolio_capital_currency"],
                "strategy_portfolio_selected_profile": cutover["strategy_portfolio_selected_profile"],
                "strategy_portfolio_selected_strategy": cutover["strategy_portfolio_selected_strategy"],
                "strategy_portfolio_selected_market": cutover["strategy_portfolio_selected_market"],
                "strategy_portfolio_selected_eligible": cutover["strategy_portfolio_selected_eligible"],
                "strategy_portfolio_selected_allocation_weight": cutover[
                    "strategy_portfolio_selected_allocation_weight"
                ],
                "strategy_portfolio_selected_allocation_notional": cutover[
                    "strategy_portfolio_selected_allocation_notional"
                ],
                "strategy_portfolio_notional_cap_applied": cutover["strategy_portfolio_notional_cap_applied"],
                "pre_portfolio_max_notional_per_session": cutover["pre_portfolio_max_notional_per_session"],
                "upload_ready": upload["ready"],
                "upload_orders": int(upload["orders"]),
                "upload_output_file": upload["output_file"],
                "upload_recommendation": upload["recommendation"],
                "adapter_schema_status": upload["schema_status"],
                "broker_schema_status": cutover["broker_schema_status"],
                "broker_schema_reviewed": cutover["broker_schema_reviewed"],
                "broker_schema_review_mode": cutover["broker_schema_review_mode"],
                "order_export_provided": order_export["provided"],
                "order_export_ready": order_export["ready"],
                "order_export_orders": int(order_export["orders"]),
                "order_export_total_notional": float(order_export["total_notional"]),
                "order_export_max_order_notional": float(order_export["max_order_notional"]),
                "proof_refresh_ready": cutover["proof_refresh_ready"],
                "proof_refresh_strategy": cutover["proof_refresh_strategy"],
                "proof_refresh_market": cutover["proof_refresh_market"],
                "route_readiness_required": _route_readiness_required(thresholds, cutover),
                "route_readiness_provided": cutover["route_readiness_provided"],
                "route_readiness_ready": cutover["route_readiness_ready"],
                "route_readiness_strategy": cutover["route_readiness_strategy"],
                "route_readiness_market": cutover["route_readiness_market"],
                "route_readiness_route_ready_pairs": cutover["route_readiness_route_ready_pairs"],
                "route_readiness_gap_pairs": cutover["route_readiness_gap_pairs"],
                "route_readiness_recommendation": cutover["route_readiness_recommendation"],
                "shadow_broker_readiness_sessions": cutover["shadow_broker_readiness_sessions"],
                "shadow_broker_readiness_ready_sessions": cutover["shadow_broker_readiness_ready_sessions"],
                "shadow_broker_vendor_data_readiness_sessions": cutover[
                    "shadow_broker_vendor_data_readiness_sessions"
                ],
                "shadow_broker_vendor_data_readiness_provided_sessions": cutover[
                    "shadow_broker_vendor_data_readiness_provided_sessions"
                ],
                "shadow_broker_vendor_data_readiness_ready_sessions": cutover[
                    "shadow_broker_vendor_data_readiness_ready_sessions"
                ],
                "shadow_broker_vendor_data_readiness_failed_checks": cutover[
                    "shadow_broker_vendor_data_readiness_failed_checks"
                ],
                "shadow_broker_adapter": cutover["shadow_broker_adapter"],
                "shadow_broker_adapter_count": cutover["shadow_broker_adapter_count"],
                "shadow_broker_route_readiness_sessions": cutover["shadow_broker_route_readiness_sessions"],
                "shadow_broker_route_readiness_ready_sessions": cutover[
                    "shadow_broker_route_readiness_ready_sessions"
                ],
                "shadow_broker_route_readiness_strategy": cutover["shadow_broker_route_readiness_strategy"],
                "shadow_broker_route_readiness_market": cutover["shadow_broker_route_readiness_market"],
                "shadow_broker_route_readiness_gap_pairs": cutover["shadow_broker_route_readiness_gap_pairs"],
                "shadow_broker_dispatch_roundtrip_sessions": cutover["shadow_broker_dispatch_roundtrip_sessions"],
                "shadow_broker_dispatch_roundtrip_ready_sessions": cutover[
                    "shadow_broker_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_dispatch_roundtrip_strategy": cutover["shadow_broker_dispatch_roundtrip_strategy"],
                "shadow_broker_dispatch_roundtrip_market": cutover["shadow_broker_dispatch_roundtrip_market"],
                "shadow_broker_dispatch_roundtrip_scenario_count": cutover[
                    "shadow_broker_dispatch_roundtrip_scenario_count"
                ],
                "shadow_broker_dispatch_roundtrip_missing_request_acks": cutover[
                    "shadow_broker_dispatch_roundtrip_missing_request_acks"
                ],
                "shadow_broker_dispatch_roundtrip_rejected_orders": cutover[
                    "shadow_broker_dispatch_roundtrip_rejected_orders"
                ],
                "shadow_broker_dispatch_roundtrip_unmatched_acks": cutover[
                    "shadow_broker_dispatch_roundtrip_unmatched_acks"
                ],
                "shadow_broker_route_dispatch_roundtrip_sessions": cutover[
                    "shadow_broker_route_dispatch_roundtrip_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": cutover[
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_strategy": cutover[
                    "shadow_broker_route_dispatch_roundtrip_strategy"
                ],
                "shadow_broker_route_dispatch_roundtrip_market": cutover[
                    "shadow_broker_route_dispatch_roundtrip_market"
                ],
                "shadow_broker_route_dispatch_roundtrip_scenario_count": cutover[
                    "shadow_broker_route_dispatch_roundtrip_scenario_count"
                ],
                **_broker_shadow_broker_packet_fields(cutover),
                **_broker_vendor_data_readiness_packet_fields(cutover),
                **_broker_vendor_market_data_batch_packet_fields(cutover),
                **_vendor_market_data_batch_packet_fields(cutover),
                "broker_resume_gate_ready": cutover["broker_resume_gate_ready"],
                "broker_resume_proof_refresh_ready": cutover["broker_resume_proof_refresh_ready"],
                "dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "dispatch_roundtrip_provided": cutover["dispatch_roundtrip_provided"],
                "dispatch_roundtrip_ready": cutover["dispatch_roundtrip_ready"],
                "dispatch_roundtrip_target_mode": cutover["dispatch_roundtrip_target_mode"],
                "dispatch_roundtrip_strategy": cutover["dispatch_roundtrip_strategy"],
                "dispatch_roundtrip_market": cutover["dispatch_roundtrip_market"],
                "dispatch_roundtrip_scenario_key": cutover["dispatch_roundtrip_scenario_key"],
                "dispatch_roundtrip_batch_id": cutover["dispatch_roundtrip_batch_id"],
                "dispatch_roundtrip_requests": cutover["dispatch_roundtrip_requests"],
                "dispatch_roundtrip_acked_orders": cutover["dispatch_roundtrip_acked_orders"],
                "dispatch_roundtrip_missing_request_acks": cutover["dispatch_roundtrip_missing_request_acks"],
                "dispatch_roundtrip_rejected_orders": cutover["dispatch_roundtrip_rejected_orders"],
                "dispatch_roundtrip_unmatched_acks": cutover["dispatch_roundtrip_unmatched_acks"],
                "dispatch_roundtrip_failed_checks": cutover["dispatch_roundtrip_failed_checks"],
                "route_enable_dispatch_roundtrip_failed_checks": cutover[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "route_dispatch_roundtrip_required": _route_dispatch_roundtrip_required(thresholds, cutover),
                "route_dispatch_roundtrip_provided": cutover["route_dispatch_roundtrip_provided"],
                "route_dispatch_roundtrip_ready": cutover["route_dispatch_roundtrip_ready"],
                "route_dispatch_roundtrip_target_mode": cutover["route_dispatch_roundtrip_target_mode"],
                "route_dispatch_roundtrip_strategy": cutover["route_dispatch_roundtrip_strategy"],
                "route_dispatch_roundtrip_market": cutover["route_dispatch_roundtrip_market"],
                "route_dispatch_roundtrip_scenario_key": cutover["route_dispatch_roundtrip_scenario_key"],
                "route_dispatch_roundtrip_batch_id": cutover["route_dispatch_roundtrip_batch_id"],
                "route_dispatch_roundtrip_requests": cutover["route_dispatch_roundtrip_requests"],
                "route_dispatch_roundtrip_acked_orders": cutover["route_dispatch_roundtrip_acked_orders"],
                "route_dispatch_roundtrip_missing_request_acks": cutover["route_dispatch_roundtrip_missing_request_acks"],
                "route_dispatch_roundtrip_rejected_orders": cutover["route_dispatch_roundtrip_rejected_orders"],
                "route_dispatch_roundtrip_unmatched_acks": cutover["route_dispatch_roundtrip_unmatched_acks"],
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1,
                "threshold_target_mode": thresholds.target_mode,
            }
        ]
    )


def _broker_shadow_broker_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    return {
        "cutover_broker_shadow_broker_readiness_provided": cutover[
            "broker_shadow_broker_readiness_provided"
        ],
        "cutover_broker_shadow_broker_readiness_sessions": cutover[
            "broker_shadow_broker_readiness_sessions"
        ],
        "cutover_broker_shadow_broker_readiness_ready_sessions": cutover[
            "broker_shadow_broker_readiness_ready_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_sessions": cutover[
            "broker_shadow_broker_vendor_data_readiness_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions": cutover[
            "broker_shadow_broker_vendor_data_readiness_provided_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions": cutover[
            "broker_shadow_broker_vendor_data_readiness_ready_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_failed_checks": cutover[
            "broker_shadow_broker_vendor_data_readiness_failed_checks"
        ],
        "cutover_broker_shadow_broker_adapter": cutover["broker_shadow_broker_adapter"],
        "cutover_broker_shadow_broker_adapter_count": cutover["broker_shadow_broker_adapter_count"],
        "cutover_broker_shadow_broker_route_readiness_sessions": cutover[
            "broker_shadow_broker_route_readiness_sessions"
        ],
        "cutover_broker_shadow_broker_route_readiness_ready_sessions": cutover[
            "broker_shadow_broker_route_readiness_ready_sessions"
        ],
        "cutover_broker_shadow_broker_route_readiness_strategy": cutover[
            "broker_shadow_broker_route_readiness_strategy"
        ],
        "cutover_broker_shadow_broker_route_readiness_market": cutover[
            "broker_shadow_broker_route_readiness_market"
        ],
        "cutover_broker_shadow_broker_route_readiness_gap_pairs": cutover[
            "broker_shadow_broker_route_readiness_gap_pairs"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_sessions": cutover[
            "broker_shadow_broker_dispatch_roundtrip_sessions"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions": cutover[
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_strategy": cutover[
            "broker_shadow_broker_dispatch_roundtrip_strategy"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_market": cutover[
            "broker_shadow_broker_dispatch_roundtrip_market"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count": cutover[
            "broker_shadow_broker_dispatch_roundtrip_scenario_count"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": cutover[
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders": cutover[
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": cutover[
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_sessions"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_strategy"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_market": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_market"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count"
        ],
    }


def _vendor_market_data_batch_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    vendor = cutover["vendor_market_data_batch"]
    return {
        "cutover_vendor_market_data_batch_provided": vendor["provided"],
        "cutover_vendor_market_data_batch_ready": vendor["ready"],
        "cutover_vendor_market_data_batch_adapter": vendor["adapter"],
        "cutover_vendor_market_data_batch_kind": vendor["kind"],
        "cutover_vendor_market_data_batch_manifest_run_type": vendor["manifest_run_type"],
        "cutover_vendor_market_data_batch_market": vendor["market"],
        "cutover_vendor_market_data_batch_dataset_count": vendor["dataset_count"],
        "cutover_vendor_market_data_batch_ready_datasets": vendor["ready_datasets"],
        "cutover_vendor_market_data_batch_failed_datasets": vendor["failed_datasets"],
        "cutover_vendor_market_data_batch_ready_rate": vendor["ready_rate"],
        "cutover_vendor_market_data_batch_unique_source_files": vendor["unique_source_files"],
        "cutover_vendor_market_data_batch_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        "cutover_vendor_market_data_batch_source_file_fingerprint_coverage": vendor[
            "source_file_fingerprint_coverage"
        ],
        "cutover_vendor_market_data_batch_min_mapping_coverage": vendor["min_mapping_coverage"],
        "cutover_vendor_market_data_batch_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        "cutover_vendor_market_data_batch_mapping_sources": vendor["mapping_sources"],
        "cutover_vendor_market_data_batch_comparison_accepted": vendor["comparison_accepted"],
        "cutover_vendor_market_data_batch_comparison_failed_checks": vendor["comparison_failed_checks"],
        "cutover_vendor_market_data_batch_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_market_data_batch_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    vendor = cutover["broker_dispatch_roundtrip_vendor_market_data_batch"]
    field_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": vendor["provided"],
        f"{field_prefix}_ready": vendor["ready"],
        f"{field_prefix}_adapter": vendor["adapter"],
        f"{field_prefix}_kind": vendor["kind"],
        f"{field_prefix}_manifest_run_type": vendor["manifest_run_type"],
        f"{field_prefix}_market": vendor["market"],
        f"{field_prefix}_dataset_count": vendor["dataset_count"],
        f"{field_prefix}_ready_datasets": vendor["ready_datasets"],
        f"{field_prefix}_failed_datasets": vendor["failed_datasets"],
        f"{field_prefix}_ready_rate": vendor["ready_rate"],
        f"{field_prefix}_unique_source_files": vendor["unique_source_files"],
        f"{field_prefix}_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        f"{field_prefix}_source_file_fingerprint_coverage": vendor["source_file_fingerprint_coverage"],
        f"{field_prefix}_min_mapping_coverage": vendor["min_mapping_coverage"],
        f"{field_prefix}_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        f"{field_prefix}_mapping_sources": vendor["mapping_sources"],
        f"{field_prefix}_comparison_accepted": vendor["comparison_accepted"],
        f"{field_prefix}_comparison_failed_checks": vendor["comparison_failed_checks"],
        f"{field_prefix}_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_data_readiness_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    readiness = cutover["broker_vendor_data_readiness"]
    return {
        "cutover_broker_vendor_data_readiness_provided": readiness["provided"],
        "cutover_broker_vendor_data_readiness_ready": readiness["ready"],
        "cutover_broker_vendor_data_readiness_failed_checks": readiness["failed_checks"],
    }


def _summary(packet: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(packet["target_mode"]),
                "strategy": str(packet["strategy"]),
                "market": str(packet["market"]),
                "scenario_key": str(packet["scenario_key"]),
                "adapter": str(packet["adapter"]),
                "route_state": "enabled" if ready else "disabled",
                "upload_orders": int(packet["upload_orders"]),
                "max_orders_per_session": int(packet["max_orders_per_session"]),
                "max_notional_per_session": float(packet["max_notional_per_session"]),
                "order_export_total_notional": float(packet["order_export_total_notional"]),
                "strategy_portfolio_required": _to_bool(packet["strategy_portfolio_required"]),
                "strategy_portfolio_provided": _to_bool(packet["strategy_portfolio_provided"]),
                "strategy_portfolio_ready": _to_bool(packet["strategy_portfolio_ready"]),
                "strategy_portfolio_deployment_mode": str(packet["strategy_portfolio_deployment_mode"]),
                "strategy_portfolio_allocation_mode": str(packet["strategy_portfolio_allocation_mode"]),
                "strategy_portfolio_capital_currency": str(packet["strategy_portfolio_capital_currency"]),
                "strategy_portfolio_selected_profile": str(packet["strategy_portfolio_selected_profile"]),
                "strategy_portfolio_selected_strategy": str(packet["strategy_portfolio_selected_strategy"]),
                "strategy_portfolio_selected_market": str(packet["strategy_portfolio_selected_market"]),
                "strategy_portfolio_selected_eligible": _to_bool(packet["strategy_portfolio_selected_eligible"]),
                "strategy_portfolio_selected_allocation_weight": float(
                    packet["strategy_portfolio_selected_allocation_weight"]
                ),
                "strategy_portfolio_selected_allocation_notional": float(
                    packet["strategy_portfolio_selected_allocation_notional"]
                ),
                "strategy_portfolio_notional_cap_applied": _to_bool(
                    packet["strategy_portfolio_notional_cap_applied"]
                ),
                "pre_portfolio_max_notional_per_session": float(packet["pre_portfolio_max_notional_per_session"]),
                "adapter_schema_status": str(packet["adapter_schema_status"]),
                "broker_schema_status": str(packet["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(packet["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(packet["broker_schema_review_mode"]),
                "proof_refresh_ready": _to_bool(packet["proof_refresh_ready"]),
                "route_readiness_required": _to_bool(packet["route_readiness_required"]),
                "route_readiness_provided": _to_bool(packet["route_readiness_provided"]),
                "route_readiness_ready": _to_bool(packet["route_readiness_ready"]),
                "route_readiness_strategy": str(packet["route_readiness_strategy"]),
                "route_readiness_market": str(packet["route_readiness_market"]),
                "route_readiness_route_ready_pairs": int(packet["route_readiness_route_ready_pairs"]),
                "route_readiness_gap_pairs": int(packet["route_readiness_gap_pairs"]),
                "shadow_broker_readiness_sessions": int(packet["shadow_broker_readiness_sessions"]),
                "shadow_broker_readiness_ready_sessions": int(packet["shadow_broker_readiness_ready_sessions"]),
                "shadow_broker_vendor_data_readiness_sessions": int(
                    packet["shadow_broker_vendor_data_readiness_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    packet["shadow_broker_vendor_data_readiness_provided_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    packet["shadow_broker_vendor_data_readiness_ready_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    packet["shadow_broker_vendor_data_readiness_failed_checks"]
                ),
                "shadow_broker_adapter": str(packet["shadow_broker_adapter"]),
                "shadow_broker_adapter_count": int(packet["shadow_broker_adapter_count"]),
                "shadow_broker_route_readiness_sessions": int(packet["shadow_broker_route_readiness_sessions"]),
                "shadow_broker_route_readiness_ready_sessions": int(
                    packet["shadow_broker_route_readiness_ready_sessions"]
                ),
                "shadow_broker_route_readiness_strategy": str(packet["shadow_broker_route_readiness_strategy"]),
                "shadow_broker_route_readiness_market": str(packet["shadow_broker_route_readiness_market"]),
                "shadow_broker_route_readiness_gap_pairs": int(packet["shadow_broker_route_readiness_gap_pairs"]),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    packet["shadow_broker_dispatch_roundtrip_sessions"]
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    packet["shadow_broker_dispatch_roundtrip_ready_sessions"]
                ),
                "shadow_broker_dispatch_roundtrip_strategy": str(
                    packet["shadow_broker_dispatch_roundtrip_strategy"]
                ),
                "shadow_broker_dispatch_roundtrip_market": str(packet["shadow_broker_dispatch_roundtrip_market"]),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    packet["shadow_broker_dispatch_roundtrip_scenario_count"]
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    packet["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    packet["shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    packet["shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    packet["shadow_broker_route_dispatch_roundtrip_sessions"]
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    packet["shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": str(
                    packet["shadow_broker_route_dispatch_roundtrip_strategy"]
                ),
                "shadow_broker_route_dispatch_roundtrip_market": str(
                    packet["shadow_broker_route_dispatch_roundtrip_market"]
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    packet["shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
                **_broker_shadow_broker_summary_fields(packet),
                **_broker_vendor_data_readiness_summary_fields(packet),
                **_broker_vendor_market_data_batch_summary_fields(packet),
                **_vendor_market_data_batch_summary_fields(packet),
                "broker_resume_gate_ready": _to_bool(packet["broker_resume_gate_ready"]),
                "broker_resume_proof_refresh_ready": _to_bool(packet["broker_resume_proof_refresh_ready"]),
                "dispatch_roundtrip_required": _to_bool(packet["dispatch_roundtrip_required"]),
                "dispatch_roundtrip_provided": _to_bool(packet["dispatch_roundtrip_provided"]),
                "dispatch_roundtrip_ready": _to_bool(packet["dispatch_roundtrip_ready"]),
                "dispatch_roundtrip_batch_id": str(packet["dispatch_roundtrip_batch_id"]),
                "dispatch_roundtrip_requests": int(packet["dispatch_roundtrip_requests"]),
                "dispatch_roundtrip_acked_orders": int(packet["dispatch_roundtrip_acked_orders"]),
                "dispatch_roundtrip_missing_request_acks": int(packet["dispatch_roundtrip_missing_request_acks"]),
                "dispatch_roundtrip_rejected_orders": int(packet["dispatch_roundtrip_rejected_orders"]),
                "dispatch_roundtrip_unmatched_acks": int(packet["dispatch_roundtrip_unmatched_acks"]),
                "dispatch_roundtrip_failed_checks": int(packet["dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    packet["route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "route_dispatch_roundtrip_required": _to_bool(packet["route_dispatch_roundtrip_required"]),
                "route_dispatch_roundtrip_provided": _to_bool(packet["route_dispatch_roundtrip_provided"]),
                "route_dispatch_roundtrip_ready": _to_bool(packet["route_dispatch_roundtrip_ready"]),
                "route_dispatch_roundtrip_batch_id": str(packet["route_dispatch_roundtrip_batch_id"]),
                "route_dispatch_roundtrip_requests": int(packet["route_dispatch_roundtrip_requests"]),
                "route_dispatch_roundtrip_acked_orders": int(packet["route_dispatch_roundtrip_acked_orders"]),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    packet["route_dispatch_roundtrip_missing_request_acks"]
                ),
                "route_dispatch_roundtrip_rejected_orders": int(packet["route_dispatch_roundtrip_rejected_orders"]),
                "route_dispatch_roundtrip_unmatched_acks": int(packet["route_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": failed,
                "recommendation": "enable_broker_route" if ready else "keep_broker_route_disabled",
            }
        ]
    )


def _broker_shadow_broker_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_broker_shadow_broker_readiness_provided": _to_bool(
            packet["cutover_broker_shadow_broker_readiness_provided"]
        ),
        "cutover_broker_shadow_broker_readiness_sessions": int(
            packet["cutover_broker_shadow_broker_readiness_sessions"]
        ),
        "cutover_broker_shadow_broker_readiness_ready_sessions": int(
            packet["cutover_broker_shadow_broker_readiness_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_sessions": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_failed_checks"]
        ),
        "cutover_broker_shadow_broker_adapter": str(packet["cutover_broker_shadow_broker_adapter"]),
        "cutover_broker_shadow_broker_adapter_count": int(
            packet["cutover_broker_shadow_broker_adapter_count"]
        ),
        "cutover_broker_shadow_broker_route_readiness_sessions": int(
            packet["cutover_broker_shadow_broker_route_readiness_sessions"]
        ),
        "cutover_broker_shadow_broker_route_readiness_ready_sessions": int(
            packet["cutover_broker_shadow_broker_route_readiness_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_route_readiness_strategy": str(
            packet["cutover_broker_shadow_broker_route_readiness_strategy"]
        ),
        "cutover_broker_shadow_broker_route_readiness_market": str(
            packet["cutover_broker_shadow_broker_route_readiness_market"]
        ),
        "cutover_broker_shadow_broker_route_readiness_gap_pairs": int(
            packet["cutover_broker_shadow_broker_route_readiness_gap_pairs"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_sessions": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_sessions"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_strategy": str(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_strategy"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_market": str(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_market"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy": str(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_market": str(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_market"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
        ),
    }


def _vendor_market_data_batch_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_vendor_market_data_batch_provided": _to_bool(
            packet["cutover_vendor_market_data_batch_provided"]
        ),
        "cutover_vendor_market_data_batch_ready": _to_bool(packet["cutover_vendor_market_data_batch_ready"]),
        "cutover_vendor_market_data_batch_adapter": str(packet["cutover_vendor_market_data_batch_adapter"]),
        "cutover_vendor_market_data_batch_kind": str(packet["cutover_vendor_market_data_batch_kind"]),
        "cutover_vendor_market_data_batch_manifest_run_type": str(
            packet["cutover_vendor_market_data_batch_manifest_run_type"]
        ),
        "cutover_vendor_market_data_batch_market": str(packet["cutover_vendor_market_data_batch_market"]),
        "cutover_vendor_market_data_batch_dataset_count": int(
            packet["cutover_vendor_market_data_batch_dataset_count"]
        ),
        "cutover_vendor_market_data_batch_ready_datasets": int(
            packet["cutover_vendor_market_data_batch_ready_datasets"]
        ),
        "cutover_vendor_market_data_batch_failed_datasets": int(
            packet["cutover_vendor_market_data_batch_failed_datasets"]
        ),
        "cutover_vendor_market_data_batch_ready_rate": _jsonable(
            packet["cutover_vendor_market_data_batch_ready_rate"]
        ),
        "cutover_vendor_market_data_batch_unique_source_files": int(
            packet["cutover_vendor_market_data_batch_unique_source_files"]
        ),
        "cutover_vendor_market_data_batch_unique_header_fingerprints": int(
            packet["cutover_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "cutover_vendor_market_data_batch_source_file_fingerprint_coverage": _jsonable(
            packet["cutover_vendor_market_data_batch_source_file_fingerprint_coverage"]
        ),
        "cutover_vendor_market_data_batch_min_mapping_coverage": _jsonable(
            packet["cutover_vendor_market_data_batch_min_mapping_coverage"]
        ),
        "cutover_vendor_market_data_batch_unique_mapping_drafts": int(
            packet["cutover_vendor_market_data_batch_unique_mapping_drafts"]
        ),
        "cutover_vendor_market_data_batch_mapping_sources": str(
            packet["cutover_vendor_market_data_batch_mapping_sources"]
        ),
        "cutover_vendor_market_data_batch_comparison_accepted": _to_bool(
            packet["cutover_vendor_market_data_batch_comparison_accepted"]
        ),
        "cutover_vendor_market_data_batch_comparison_failed_checks": int(
            packet["cutover_vendor_market_data_batch_comparison_failed_checks"]
        ),
    }


def _broker_vendor_market_data_batch_summary_fields(packet: pd.Series) -> dict[str, Any]:
    field_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": _to_bool(packet[f"{field_prefix}_provided"]),
        f"{field_prefix}_ready": _to_bool(packet[f"{field_prefix}_ready"]),
        f"{field_prefix}_adapter": str(packet[f"{field_prefix}_adapter"]),
        f"{field_prefix}_kind": str(packet[f"{field_prefix}_kind"]),
        f"{field_prefix}_manifest_run_type": str(packet[f"{field_prefix}_manifest_run_type"]),
        f"{field_prefix}_market": str(packet[f"{field_prefix}_market"]),
        f"{field_prefix}_dataset_count": int(packet[f"{field_prefix}_dataset_count"]),
        f"{field_prefix}_ready_datasets": int(packet[f"{field_prefix}_ready_datasets"]),
        f"{field_prefix}_failed_datasets": int(packet[f"{field_prefix}_failed_datasets"]),
        f"{field_prefix}_ready_rate": _jsonable(packet[f"{field_prefix}_ready_rate"]),
        f"{field_prefix}_unique_source_files": int(packet[f"{field_prefix}_unique_source_files"]),
        f"{field_prefix}_unique_header_fingerprints": int(
            packet[f"{field_prefix}_unique_header_fingerprints"]
        ),
        f"{field_prefix}_source_file_fingerprint_coverage": _jsonable(
            packet[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        f"{field_prefix}_min_mapping_coverage": _jsonable(packet[f"{field_prefix}_min_mapping_coverage"]),
        f"{field_prefix}_unique_mapping_drafts": int(packet[f"{field_prefix}_unique_mapping_drafts"]),
        f"{field_prefix}_mapping_sources": str(packet[f"{field_prefix}_mapping_sources"]),
        f"{field_prefix}_comparison_accepted": _to_bool(packet[f"{field_prefix}_comparison_accepted"]),
        f"{field_prefix}_comparison_failed_checks": int(packet[f"{field_prefix}_comparison_failed_checks"]),
    }


def _broker_vendor_data_readiness_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_broker_vendor_data_readiness_provided": _to_bool(
            packet["cutover_broker_vendor_data_readiness_provided"]
        ),
        "cutover_broker_vendor_data_readiness_ready": _to_bool(
            packet["cutover_broker_vendor_data_readiness_ready"]
        ),
        "cutover_broker_vendor_data_readiness_failed_checks": int(
            packet["cutover_broker_vendor_data_readiness_failed_checks"]
        ),
    }


def _config(packet: pd.Series, thresholds: RouteEnableThresholds, checks: pd.DataFrame) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    return {
        "schema_version": 1,
        "route_enabled": _to_bool(packet["route_enabled"]),
        "route_state": str(packet["route_state"]),
        "failed_check_count": len(failed_check_records),
        "target_mode": str(packet["target_mode"]),
        "strategy": str(packet["strategy"]),
        "market": str(packet["market"]),
        "scenario_key": str(packet["scenario_key"]),
        "adapter": str(packet["adapter"]),
        "limits": {
            "max_orders_per_session": int(packet["max_orders_per_session"]),
            "max_notional_per_session": float(packet["max_notional_per_session"]),
            "stop_loss": _jsonable(packet["stop_loss"]),
        },
        "strategy_portfolio": {
            "required": _to_bool(packet["strategy_portfolio_required"]),
            "provided": _to_bool(packet["strategy_portfolio_provided"]),
            "ready": _to_bool(packet["strategy_portfolio_ready"]),
            "deployment_mode": str(packet["strategy_portfolio_deployment_mode"]),
            "allocation_mode": str(packet["strategy_portfolio_allocation_mode"]),
            "capital_currency": str(packet["strategy_portfolio_capital_currency"]),
            "selected_profile": str(packet["strategy_portfolio_selected_profile"]),
            "selected_strategy": str(packet["strategy_portfolio_selected_strategy"]),
            "selected_market": str(packet["strategy_portfolio_selected_market"]),
            "selected_eligible": _to_bool(packet["strategy_portfolio_selected_eligible"]),
            "selected_allocation_weight": float(packet["strategy_portfolio_selected_allocation_weight"]),
            "selected_allocation_notional": float(packet["strategy_portfolio_selected_allocation_notional"]),
            "notional_cap_applied": _to_bool(packet["strategy_portfolio_notional_cap_applied"]),
            "pre_portfolio_max_notional_per_session": float(packet["pre_portfolio_max_notional_per_session"]),
        },
        "upload": {
            "ready": _to_bool(packet["upload_ready"]),
            "orders": int(packet["upload_orders"]),
            "output_file": str(packet["upload_output_file"]),
            "adapter_schema_status": str(packet["adapter_schema_status"]),
            "recommendation": str(packet["upload_recommendation"]),
        },
        "broker_readiness": {
            "adapter_schema_status": str(packet["broker_schema_status"]),
            "schema_reviewed": _to_bool(packet["broker_schema_reviewed"]),
            "schema_review_mode": str(packet["broker_schema_review_mode"]),
        },
        "order_export": {
            "provided": _to_bool(packet["order_export_provided"]),
            "ready": _to_bool(packet["order_export_ready"]),
            "orders": int(packet["order_export_orders"]),
            "total_notional": float(packet["order_export_total_notional"]),
            "max_order_notional": float(packet["order_export_max_order_notional"]),
        },
        "proof_freshness": {
            "ready": _to_bool(packet["proof_refresh_ready"]),
            "strategy": str(packet["proof_refresh_strategy"]),
            "market": str(packet["proof_refresh_market"]),
        },
        "route_readiness": {
            "required": _to_bool(packet["route_readiness_required"]),
            "provided": _to_bool(packet["route_readiness_provided"]),
            "ready": _to_bool(packet["route_readiness_ready"]),
            "strategy": str(packet["route_readiness_strategy"]),
            "market": str(packet["route_readiness_market"]),
            "route_ready_pairs": int(packet["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(packet["route_readiness_gap_pairs"]),
            "recommendation": str(packet["route_readiness_recommendation"]),
        },
        "shadow_broker_readiness": {
            "provided": int(packet["shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(packet["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(packet["shadow_broker_readiness_ready_sessions"]),
            "adapter": str(packet["shadow_broker_adapter"]),
            "adapter_count": int(packet["shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(packet["shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(packet["shadow_broker_vendor_data_readiness_provided_sessions"]),
                "ready_sessions": int(packet["shadow_broker_vendor_data_readiness_ready_sessions"]),
                "failed_checks": int(packet["shadow_broker_vendor_data_readiness_failed_checks"]),
            },
            "route_readiness": {
                "sessions": int(packet["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(packet["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(packet["shadow_broker_route_readiness_strategy"]),
                "market": str(packet["shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(packet["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(packet["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(packet["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(packet["shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(packet["shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(packet["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    packet["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(packet["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(packet["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(packet["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(packet["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(packet["shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(packet["shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(packet["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "cutover_broker_shadow_broker_readiness": _broker_shadow_broker_config(packet),
        "cutover_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(packet),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _broker_vendor_market_data_batch_config(packet)
        ),
        "cutover_vendor_market_data_batch": _vendor_market_data_batch_config(packet),
        "broker_resume_gate": {
            "ready": _to_bool(packet["broker_resume_gate_ready"]),
            "proof_refresh_ready": _to_bool(packet["broker_resume_proof_refresh_ready"]),
        },
        "dispatch_roundtrip": {
            "required": _to_bool(packet["dispatch_roundtrip_required"]),
            "provided": _to_bool(packet["dispatch_roundtrip_provided"]),
            "ready": _to_bool(packet["dispatch_roundtrip_ready"]),
            "target_mode": str(packet["dispatch_roundtrip_target_mode"]),
            "strategy": str(packet["dispatch_roundtrip_strategy"]),
            "market": str(packet["dispatch_roundtrip_market"]),
            "scenario_key": str(packet["dispatch_roundtrip_scenario_key"]),
            "dispatch_batch_id": str(packet["dispatch_roundtrip_batch_id"]),
            "requests": int(packet["dispatch_roundtrip_requests"]),
            "acked_orders": int(packet["dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(packet["dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(packet["dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(packet["dispatch_roundtrip_unmatched_acks"]),
            "failed_checks": int(packet["dispatch_roundtrip_failed_checks"]),
            "route_enable_dispatch_roundtrip": {
                "failed_checks": int(packet["route_enable_dispatch_roundtrip_failed_checks"]),
            },
            "route_proof": {
                "required": _to_bool(packet["route_dispatch_roundtrip_required"]),
                "provided": _to_bool(packet["route_dispatch_roundtrip_provided"]),
                "ready": _to_bool(packet["route_dispatch_roundtrip_ready"]),
                "target_mode": str(packet["route_dispatch_roundtrip_target_mode"]),
                "strategy": str(packet["route_dispatch_roundtrip_strategy"]),
                "market": str(packet["route_dispatch_roundtrip_market"]),
                "scenario_key": str(packet["route_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(packet["route_dispatch_roundtrip_batch_id"]),
                "requests": int(packet["route_dispatch_roundtrip_requests"]),
                "acked_orders": int(packet["route_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(packet["route_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(packet["route_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(packet["route_dispatch_roundtrip_unmatched_acks"]),
            },
        },
        "thresholds": asdict(thresholds),
        "failed_checks": [str(record.get("check", "")) for record in failed_check_records],
        "primary_blocker": failed_check_records[0] if failed_check_records else {},
    }


def _failed_check_records(checks: pd.DataFrame) -> list[dict[str, object]]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool)]
    return [
        {str(key): _jsonable_check_value(value) for key, value in row.items()}
        for row in failed.to_dict(orient="records")
    ]


def _jsonable_check_value(value: object) -> object:
    value = _jsonable(value)
    if hasattr(value, "item"):
        try:
            return value.item()  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError):
            pass
    return value


def _broker_shadow_broker_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(packet["cutover_broker_shadow_broker_readiness_provided"]),
        "sessions": int(packet["cutover_broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(packet["cutover_broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(packet["cutover_broker_shadow_broker_adapter"]),
        "adapter_count": int(packet["cutover_broker_shadow_broker_adapter_count"]),
        "broker_vendor_data_readiness": {
            "sessions": int(packet["cutover_broker_shadow_broker_vendor_data_readiness_sessions"]),
            "provided_sessions": int(
                packet["cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
            ),
            "ready_sessions": int(packet["cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions"]),
            "failed_checks": int(packet["cutover_broker_shadow_broker_vendor_data_readiness_failed_checks"]),
        },
        "route_readiness": {
            "sessions": int(packet["cutover_broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(packet["cutover_broker_shadow_broker_route_readiness_ready_sessions"]),
            "strategy": str(packet["cutover_broker_shadow_broker_route_readiness_strategy"]),
            "market": str(packet["cutover_broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(packet["cutover_broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(packet["cutover_broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(packet["cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(packet["cutover_broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(packet["cutover_broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(packet["cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(
                packet["cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(
                packet["cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
            ),
            "max_unmatched_acks": int(
                packet["cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
            ),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(
                packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
            ),
            "strategy": str(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy"]),
            "market": str(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _vendor_market_data_batch_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(packet["cutover_vendor_market_data_batch_provided"]),
        "ready": _to_bool(packet["cutover_vendor_market_data_batch_ready"]),
        "adapter": str(packet["cutover_vendor_market_data_batch_adapter"]),
        "kind": str(packet["cutover_vendor_market_data_batch_kind"]),
        "manifest_run_type": str(packet["cutover_vendor_market_data_batch_manifest_run_type"]),
        "market": str(packet["cutover_vendor_market_data_batch_market"]),
        "dataset_count": int(packet["cutover_vendor_market_data_batch_dataset_count"]),
        "ready_datasets": int(packet["cutover_vendor_market_data_batch_ready_datasets"]),
        "failed_datasets": int(packet["cutover_vendor_market_data_batch_failed_datasets"]),
        "ready_rate": _jsonable(packet["cutover_vendor_market_data_batch_ready_rate"]),
        "unique_source_files": int(packet["cutover_vendor_market_data_batch_unique_source_files"]),
        "unique_header_fingerprints": int(
            packet["cutover_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "source_file_fingerprint_coverage": _jsonable(
            packet["cutover_vendor_market_data_batch_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(packet["cutover_vendor_market_data_batch_min_mapping_coverage"]),
        "unique_mapping_drafts": int(packet["cutover_vendor_market_data_batch_unique_mapping_drafts"]),
        "mapping_sources": str(packet["cutover_vendor_market_data_batch_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(packet["cutover_vendor_market_data_batch_comparison_accepted"]),
            "failed_checks": int(packet["cutover_vendor_market_data_batch_comparison_failed_checks"]),
        },
        "datasets": _json_list(packet["cutover_vendor_market_data_batch_datasets_json"]),
    }


def _broker_vendor_market_data_batch_config(packet: pd.Series) -> dict[str, Any]:
    field_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(packet[f"{field_prefix}_provided"]),
        "ready": _to_bool(packet[f"{field_prefix}_ready"]),
        "adapter": str(packet[f"{field_prefix}_adapter"]),
        "kind": str(packet[f"{field_prefix}_kind"]),
        "manifest_run_type": str(packet[f"{field_prefix}_manifest_run_type"]),
        "market": str(packet[f"{field_prefix}_market"]),
        "dataset_count": int(packet[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(packet[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(packet[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(packet[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(packet[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(packet[f"{field_prefix}_unique_header_fingerprints"]),
        "source_file_fingerprint_coverage": _jsonable(
            packet[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(packet[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(packet[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": str(packet[f"{field_prefix}_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(packet[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(packet[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(packet[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_data_readiness_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(packet["cutover_broker_vendor_data_readiness_provided"]),
        "ready": _to_bool(packet["cutover_broker_vendor_data_readiness_ready"]),
        "failed_checks": int(packet["cutover_broker_vendor_data_readiness_failed_checks"]),
    }


def _vendor_market_data_batch_state(
    vendor: dict[str, Any],
    *,
    row: pd.Series | None = None,
    field_prefix: str = "",
) -> dict[str, Any]:
    row = pd.Series(dtype=object) if row is None else row
    comparison = vendor.get("comparison", {}) or {}
    datasets = vendor.get("datasets")
    if datasets is None and field_prefix:
        datasets = _json_list(row.get(f"{field_prefix}_datasets_json", "[]"))
    datasets = datasets or []
    row_value = (lambda suffix, default: row.get(f"{field_prefix}_{suffix}", default)) if field_prefix else (
        lambda _suffix, default: default
    )
    return {
        "provided": _to_bool(vendor.get("provided", row_value("provided", False))),
        "ready": _to_bool(vendor.get("ready", row_value("ready", False))),
        "adapter": _identity_key(_first_text(vendor.get("adapter", ""), row_value("adapter", ""))),
        "kind": _first_text(vendor.get("kind", ""), row_value("kind", "")),
        "manifest_run_type": _identity_key(
            _first_text(vendor.get("manifest_run_type", ""), row_value("manifest_run_type", ""))
        ),
        "market": _identity_key(_first_text(vendor.get("market", ""), row_value("market", ""))),
        "dataset_count": int(_number_from(vendor, "dataset_count", _number(row, f"{field_prefix}_dataset_count", 0.0))),
        "ready_datasets": int(
            _number_from(vendor, "ready_datasets", _number(row, f"{field_prefix}_ready_datasets", 0.0))
        ),
        "failed_datasets": int(
            _number_from(vendor, "failed_datasets", _number(row, f"{field_prefix}_failed_datasets", 0.0))
        ),
        "ready_rate": _number_from(vendor, "ready_rate", _number(row, f"{field_prefix}_ready_rate", 0.0)),
        "unique_source_files": int(
            _number_from(
                vendor,
                "unique_source_files",
                _number(row, f"{field_prefix}_unique_source_files", 0.0),
            )
        ),
        "unique_header_fingerprints": int(
            _number_from(
                vendor,
                "unique_header_fingerprints",
                _number(row, f"{field_prefix}_unique_header_fingerprints", 0.0),
            )
        ),
        "source_file_fingerprint_coverage": _number_from(
            vendor,
            "source_file_fingerprint_coverage",
            _number(row, f"{field_prefix}_source_file_fingerprint_coverage", 0.0),
        ),
        "min_mapping_coverage": _number_from(
            vendor,
            "min_mapping_coverage",
            _number(row, f"{field_prefix}_min_mapping_coverage", 0.0),
        ),
        "unique_mapping_drafts": int(
            _number_from(
                vendor,
                "unique_mapping_drafts",
                _number(row, f"{field_prefix}_unique_mapping_drafts", 0.0),
            )
        ),
        "mapping_sources": _first_text(vendor.get("mapping_sources", ""), row_value("mapping_sources", "")),
        "comparison_accepted": _to_bool(comparison.get("accepted", row_value("comparison_accepted", False))),
        "comparison_failed_checks": int(
            _number_from(
                comparison,
                "failed_checks",
                _number(row, f"{field_prefix}_comparison_failed_checks", 0.0),
            )
        ),
        "datasets": [
            {
                "dataset": _first_text(item.get("dataset", "")),
                "ready": _to_bool(item.get("ready", False)),
                "source_file_sha256": _first_text(item.get("source_file_sha256", "")),
                "source_header_sha256": _first_text(item.get("source_header_sha256", "")),
                "mapping_draft_sha256": _first_text(item.get("mapping_draft_sha256", "")),
                "mapping_source": _first_text(item.get("mapping_source", "")),
            }
            for item in datasets
            if isinstance(item, dict)
        ],
    }


def _broker_vendor_data_readiness_state(
    readiness: dict[str, Any],
    *,
    row: pd.Series | None = None,
    field_prefix: str = "",
) -> dict[str, Any]:
    row = pd.Series(dtype=object) if row is None else row
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    row_value = (lambda suffix, default: row.get(f"{field_prefix}_{suffix}", default)) if field_prefix else (
        lambda _suffix, default: default
    )
    return {
        "provided": _to_bool(readiness.get("provided", row_value("provided", active_config))),
        "ready": _to_bool(readiness.get("ready", row_value("ready", False))),
        "failed_checks": _broker_vendor_data_readiness_failed_checks(
            readiness,
            fallback=_number(row, f"{field_prefix}_failed_checks", 0.0) if field_prefix else 0.0,
        ),
    }


def _broker_vendor_data_readiness_failed_checks(
    readiness: dict[str, Any],
    *,
    fallback: float = 0.0,
) -> int:
    failed_checks = readiness.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_from(readiness, "failed_checks", fallback))
    return int(_number_from(readiness, "failed_check_count", fallback))


def _cutover_state(row: pd.Series, config: dict[str, Any]) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    proof = config.get("proof_freshness", {}) or {}
    runtime_session = config.get("runtime_session", {}) or {}
    strategy_portfolio = runtime_session.get("strategy_portfolio", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    resume = broker_readiness.get("resume_gate", {}) or {}
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    broker_route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route_readiness = config.get("scaleup_route_readiness", {}) or {}
    shadow_broker = config.get("scaleup_shadow_broker_readiness", {}) or {}
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_shadow_broker = config.get("scaleup_broker_shadow_broker_readiness", {}) or {}
    (
        broker_vendor_market_data_batch,
        broker_vendor_market_data_batch_prefix,
    ) = _broker_vendor_market_data_batch_source(config)
    (
        broker_vendor_data_readiness,
        broker_vendor_data_readiness_prefix,
    ) = _broker_vendor_data_readiness_source(config)
    vendor_market_data_batch = config.get("scaleup_vendor_market_data_batch", {}) or {}
    scaleup_dispatch = config.get("scaleup_dispatch_roundtrip", {}) or {}
    scaleup_route_enable = scaleup_dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route = dispatch.get("route_proof", {}) or {}
    return {
        "ready": _to_bool(row.get("ready", config.get("ready", False))),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""))),
        "market": _identity_key(_first_text(row.get("market", ""), config.get("market", ""))),
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "strategy_portfolio_required": _to_bool(
            strategy_portfolio.get(
                "required",
                row.get("runtime_strategy_portfolio_required", row.get("strategy_portfolio_required", False)),
            )
        ),
        "strategy_portfolio_provided": _to_bool(
            strategy_portfolio.get(
                "provided",
                row.get("runtime_strategy_portfolio_provided", row.get("strategy_portfolio_provided", False)),
            )
        ),
        "strategy_portfolio_ready": _to_bool(
            strategy_portfolio.get(
                "ready",
                row.get("runtime_strategy_portfolio_ready", row.get("strategy_portfolio_ready", False)),
            )
        ),
        "strategy_portfolio_deployment_mode": _first_text(
            strategy_portfolio.get("deployment_mode", ""),
            row.get("runtime_strategy_portfolio_deployment_mode", ""),
            row.get("strategy_portfolio_deployment_mode", ""),
        ),
        "strategy_portfolio_allocation_mode": _first_text(
            strategy_portfolio.get("allocation_mode", ""),
            row.get("runtime_strategy_portfolio_allocation_mode", ""),
            row.get("strategy_portfolio_allocation_mode", ""),
        ),
        "strategy_portfolio_capital_currency": _first_text(
            strategy_portfolio.get("capital_currency", ""),
            row.get("runtime_strategy_portfolio_capital_currency", ""),
            row.get("strategy_portfolio_capital_currency", ""),
        ),
        "strategy_portfolio_selected_profile": _first_text(
            strategy_portfolio.get("selected_profile", ""),
            row.get("runtime_strategy_portfolio_selected_profile", ""),
            row.get("strategy_portfolio_selected_profile", ""),
        ),
        "strategy_portfolio_selected_strategy": _strategy_key(
            _first_text(
                strategy_portfolio.get("selected_strategy", ""),
                row.get("runtime_strategy_portfolio_selected_strategy", ""),
                row.get("strategy_portfolio_selected_strategy", ""),
            )
        ),
        "strategy_portfolio_selected_market": _identity_key(
            _first_text(
                strategy_portfolio.get("selected_market", ""),
                row.get("runtime_strategy_portfolio_selected_market", ""),
                row.get("strategy_portfolio_selected_market", ""),
            )
        ),
        "strategy_portfolio_selected_eligible": _to_bool(
            strategy_portfolio.get(
                "selected_eligible",
                row.get(
                    "runtime_strategy_portfolio_selected_eligible",
                    row.get("strategy_portfolio_selected_eligible", False),
                ),
            )
        ),
        "strategy_portfolio_selected_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "selected_allocation_weight",
                _number(
                    row,
                    "runtime_strategy_portfolio_selected_allocation_weight",
                    _number(row, "strategy_portfolio_selected_allocation_weight", 0.0),
                ),
            )
        ),
        "strategy_portfolio_selected_allocation_notional": float(
            _number_from(
                strategy_portfolio,
                "selected_allocation_notional",
                _number(
                    row,
                    "runtime_strategy_portfolio_selected_allocation_notional",
                    _number(row, "strategy_portfolio_selected_allocation_notional", 0.0),
                ),
            )
        ),
        "strategy_portfolio_notional_cap_applied": _to_bool(
            strategy_portfolio.get(
                "notional_cap_applied",
                row.get(
                    "runtime_strategy_portfolio_notional_cap_applied",
                    row.get("strategy_portfolio_notional_cap_applied", False),
                ),
            )
        ),
        "pre_portfolio_max_notional_per_session": float(
            _number_from(
                strategy_portfolio,
                "pre_portfolio_max_notional_per_session",
                _number(
                    row,
                    "runtime_pre_portfolio_max_notional_per_session",
                    _number(row, "pre_portfolio_max_notional_per_session", 0.0),
                ),
            )
        ),
        "proof_refresh_ready": _to_bool(proof.get("ready", row.get("proof_refresh_ready", False))),
        "proof_refresh_strategy": _strategy_key(
            _first_text(proof.get("strategy", ""), row.get("proof_refresh_strategy", ""))
        ),
        "proof_refresh_market": _identity_key(_first_text(proof.get("market", ""), row.get("proof_refresh_market", ""))),
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("scaleup_route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("scaleup_route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(
            route_readiness.get("ready", row.get("scaleup_route_readiness_ready", False))
        ),
        "route_readiness_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get("scaleup_route_readiness_strategy", ""))
        ),
        "route_readiness_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get("scaleup_route_readiness_market", ""))
        ),
        "route_readiness_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, "scaleup_route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "route_readiness_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, "scaleup_route_readiness_gap_pairs", 0.0))
        ),
        "route_readiness_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get("scaleup_route_readiness_recommendation", ""),
        ),
        "shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "scaleup_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("scaleup_shadow_broker_adapter", ""))
        ),
        "shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "scaleup_shadow_broker_adapter_count", 0.0),
            )
        ),
        "shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "scaleup_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("scaleup_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("scaleup_shadow_broker_route_readiness_market", ""),
            )
        ),
        "shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "scaleup_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("scaleup_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("scaleup_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "scaleup_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("scaleup_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("scaleup_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        **_broker_shadow_broker_state_fields(row, broker_shadow_broker),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_state(
            broker_vendor_market_data_batch,
            row=row,
            field_prefix=broker_vendor_market_data_batch_prefix,
        ),
        "broker_vendor_data_readiness": _broker_vendor_data_readiness_state(
            broker_vendor_data_readiness,
            row=row,
            field_prefix=broker_vendor_data_readiness_prefix,
        ),
        "vendor_market_data_batch": _vendor_market_data_batch_state(vendor_market_data_batch),
        "broker_schema_status": _first_text(
            broker_readiness.get("adapter_schema_status", ""),
            row.get("broker_schema_status", ""),
        ),
        "broker_schema_reviewed": _to_bool(
            broker_readiness.get("schema_reviewed", row.get("broker_schema_reviewed", False))
        ),
        "broker_schema_review_mode": _first_text(
            broker_readiness.get("schema_review_mode", ""),
            row.get("broker_schema_review_mode", ""),
        ),
        "broker_resume_gate_ready": _to_bool(resume.get("ready", row.get("broker_resume_gate_ready", False))),
        "broker_resume_proof_refresh_ready": _to_bool(
            resume.get("proof_refresh_ready", row.get("broker_resume_proof_refresh_ready", False))
        ),
        "dispatch_roundtrip_required": _to_bool(
            dispatch.get("required", row.get("broker_dispatch_roundtrip_required", False))
        ),
        "dispatch_roundtrip_provided": _to_bool(
            dispatch.get("provided", row.get("broker_dispatch_roundtrip_provided", False))
        ),
        "dispatch_roundtrip_ready": _to_bool(
            dispatch.get("ready", row.get("broker_dispatch_roundtrip_ready", False))
        ),
        "dispatch_roundtrip_target_mode": _identity_key(
            _first_text(dispatch.get("target_mode", ""), row.get("broker_dispatch_roundtrip_target_mode", ""))
        ),
        "dispatch_roundtrip_strategy": _strategy_key(
            _first_text(dispatch.get("strategy", ""), row.get("broker_dispatch_roundtrip_strategy", ""))
        ),
        "dispatch_roundtrip_market": _identity_key(
            _first_text(dispatch.get("market", ""), row.get("broker_dispatch_roundtrip_market", ""))
        ),
        "dispatch_roundtrip_scenario_key": _first_text(
            dispatch.get("scenario_key", ""),
            row.get("broker_dispatch_roundtrip_scenario_key", ""),
        ),
        "dispatch_roundtrip_batch_id": _first_text(
            dispatch.get("dispatch_batch_id", ""),
            row.get("broker_dispatch_roundtrip_batch_id", ""),
        ),
        "dispatch_roundtrip_requests": int(
            _number_from(
                dispatch,
                "requests",
                _number(row, "broker_dispatch_roundtrip_requests", 0.0),
            )
        ),
        "dispatch_roundtrip_acked_orders": int(
            _number_from(
                dispatch,
                "acked_orders",
                _number(row, "broker_dispatch_roundtrip_acked_orders", 0.0),
            )
        ),
        "dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                dispatch,
                "missing_request_acks",
                _number(row, "broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_rejected_orders": int(
            _number_from(
                dispatch,
                "rejected_orders",
                _number(row, "broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                dispatch,
                "unmatched_acks",
                _number(row, "broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_failed_checks": int(
            _number_from(
                dispatch,
                "failed_checks",
                _number(row, "broker_dispatch_roundtrip_failed_checks", 0.0),
            )
        ),
        "route_enable_dispatch_roundtrip_failed_checks": max(
            int(
                _number_from(
                    broker_route_enable,
                    "failed_checks",
                    _number(row, "broker_route_enable_dispatch_roundtrip_failed_checks", 0.0),
                )
            ),
            int(
                _number_from(
                    scaleup_route_enable,
                    "failed_checks",
                    _number(row, "scaleup_route_enable_dispatch_roundtrip_failed_checks", 0.0),
                )
            ),
        ),
        "route_dispatch_roundtrip_required": _to_bool(
            route.get("required", row.get("broker_route_dispatch_roundtrip_required", False))
        ),
        "route_dispatch_roundtrip_provided": _to_bool(
            route.get("provided", row.get("broker_route_dispatch_roundtrip_provided", False))
        ),
        "route_dispatch_roundtrip_ready": _to_bool(
            route.get("ready", row.get("broker_route_dispatch_roundtrip_ready", False))
        ),
        "route_dispatch_roundtrip_target_mode": _identity_key(
            _first_text(route.get("target_mode", ""), row.get("broker_route_dispatch_roundtrip_target_mode", ""))
        ),
        "route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(route.get("strategy", ""), row.get("broker_route_dispatch_roundtrip_strategy", ""))
        ),
        "route_dispatch_roundtrip_market": _identity_key(
            _first_text(route.get("market", ""), row.get("broker_route_dispatch_roundtrip_market", ""))
        ),
        "route_dispatch_roundtrip_scenario_key": _first_text(
            route.get("scenario_key", ""),
            row.get("broker_route_dispatch_roundtrip_scenario_key", ""),
        ),
        "route_dispatch_roundtrip_batch_id": _first_text(
            route.get("dispatch_batch_id", ""),
            row.get("broker_route_dispatch_roundtrip_batch_id", ""),
        ),
        "route_dispatch_roundtrip_requests": int(
            _number_from(
                route,
                "requests",
                _number(row, "broker_route_dispatch_roundtrip_requests", 0.0),
            )
        ),
        "route_dispatch_roundtrip_acked_orders": int(
            _number_from(
                route,
                "acked_orders",
                _number(row, "broker_route_dispatch_roundtrip_acked_orders", 0.0),
            )
        ),
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                route,
                "missing_request_acks",
                _number(row, "broker_route_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "route_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                route,
                "rejected_orders",
                _number(row, "broker_route_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                route,
                "unmatched_acks",
                _number(row, "broker_route_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
    }


def _broker_vendor_market_data_batch_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return select_vendor_market_data_batch_source(
        config,
        (
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="scaleup_broker_dispatch_roundtrip_vendor_market_data_batch",
    )


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
        (config.get("cutover_broker_vendor_data_readiness"), "cutover_broker_vendor_data_readiness"),
        (config.get("scaleup_broker_vendor_data_readiness"), "scaleup_broker_vendor_data_readiness"),
        (config.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness"),
    ]
    broker_readiness = config.get("broker_readiness", {}) or {}
    if isinstance(broker_readiness, dict):
        candidates.append(
            (broker_readiness.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
        broker_dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
        if isinstance(broker_dispatch, dict):
            candidates.append(
                (broker_dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
            )
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(
            (dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
    for candidate, source in candidates:
        if isinstance(candidate, dict) and _broker_vendor_data_readiness_source_active(candidate):
            return candidate, source
    return {}, "scaleup_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    cutover_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    vendor, _source = _broker_vendor_market_data_batch_source(cutover_config)
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        sidecar_vendor, _source = select_vendor_market_data_batch_source(
            dispatch,
            (
                "broker_dispatch_roundtrip_vendor_market_data_batch",
                "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
                "vendor_market_data_batch",
                "roundtrip_vendor_market_data_batch",
            ),
            default_source="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    else:
        sidecar_vendor = {}
    should_hydrate_vendor = (
        not vendor_market_data_batch_source_active(vendor)
        and vendor_market_data_batch_source_active(sidecar_vendor)
    )
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(cutover_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(broker_readiness_config)
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    if not should_hydrate_vendor and not should_hydrate_readiness:
        return cutover_config

    out = dict(cutover_config)
    if should_hydrate_vendor:
        out["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out["scaleup_broker_vendor_data_readiness"] = dict(sidecar_readiness)
    return out


def _manifest_input_path(manifest_path: Path | None, input_name: str) -> Path | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = (manifest.get("inputs", {}) or {}).get(input_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path if path.exists() else None


def _broker_shadow_broker_state_fields(row: pd.Series, shadow_broker: dict[str, Any]) -> dict[str, Any]:
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    return {
        "broker_shadow_broker_readiness_provided": _to_bool(
            shadow_broker.get("provided", row.get("scaleup_broker_shadow_broker_readiness_provided", False))
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("scaleup_broker_shadow_broker_adapter", ""))
        ),
        "broker_shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "scaleup_broker_shadow_broker_adapter_count", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("scaleup_broker_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("scaleup_broker_shadow_broker_route_readiness_market", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "scaleup_broker_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("scaleup_broker_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("scaleup_broker_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("scaleup_broker_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
    }


def _upload_state(row: pd.Series) -> dict[str, Any]:
    return {
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "schema_status": _first_text(row.get("adapter_schema_status", "")),
        "orders": int(_number(row, "orders", 0.0)),
        "output_file": _first_text(row.get("output_file", "")),
        "recommendation": _first_text(row.get("recommendation", "")),
    }


def _order_export_state(summary: pd.DataFrame) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "provided": not summary.empty,
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "orders": int(_number(row, "orders", 0.0)),
        "total_notional": float(_number(row, "total_notional", 0.0)),
        "max_order_notional": float(_number(row, "max_order_notional", 0.0)),
    }


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required route-enable input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required route-enable input is empty: {name}")
    return frame


def _read_optional(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_csv(file_path)


def _summary_path(path: str | Path | None, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path:
    if path is None:
        return Path(filename)
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / filename
    if direct.exists():
        return direct
    return next(
        (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
        direct,
    )


def _sidecar_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        file_path = candidate / filename
    else:
        file_path = candidate if candidate.name == filename else candidate.with_name(filename)
    return file_path if file_path.exists() else None


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: RouteEnableThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: RouteEnableThresholds, cutover: dict[str, Any] | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (cutover is not None and cutover["route_readiness_required"])
    )


def _strategy_portfolio_active(cutover: dict[str, Any]) -> bool:
    return bool(cutover["strategy_portfolio_required"] or cutover["strategy_portfolio_provided"])


def _route_dispatch_roundtrip_required(thresholds: RouteEnableThresholds, cutover: dict[str, Any]) -> bool:
    return bool(
        _dispatch_roundtrip_required(thresholds)
        or cutover["route_dispatch_roundtrip_required"]
        or cutover["route_dispatch_roundtrip_provided"]
    )


def _validate_thresholds(thresholds: RouteEnableThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_from(mapping: dict[str, Any], key: str, fallback: float) -> float:
    value = mapping.get(key, fallback)
    if value is None or _is_missing(value):
        return float(fallback)
    return float(value)


def _nullable_number(value: object) -> float | None:
    if value is None or _is_missing(value):
        return None
    return float(value)


def _first_text(*values: object) -> str:
    for value in values:
        text = _object_text(value)
        if text:
            return text
    return ""


def _strategy_key(value: object) -> str:
    key = _identity_key(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    return _object_text(value).lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _object_text(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed", "enabled"}
    return bool(value)


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value: object) -> object:
    if _is_missing(value):
        return None
    return value


def _json_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }
