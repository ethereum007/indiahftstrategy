from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class BrokerDispatchThresholds:
    target_mode: str = "live_dryrun"
    require_route_enabled: bool = True
    require_dry_run: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    min_orders: int = 1
    max_orders: int | None = None


@dataclass(frozen=True)
class BrokerDispatchReport:
    dispatch_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_dispatch_plan(
    *,
    route_enable_summary: pd.DataFrame,
    route_enable_config: dict[str, Any] | None = None,
    upload_orders: pd.DataFrame,
    upload_file_hash: str = "",
    thresholds: BrokerDispatchThresholds | None = None,
) -> BrokerDispatchReport:
    thresholds = thresholds or BrokerDispatchThresholds()
    _validate_thresholds(thresholds)
    route_enable_summary = _require_nonempty(route_enable_summary, "route_enable_summary")
    upload_orders = _require_nonempty(upload_orders, "upload_orders")
    route_enable_config = route_enable_config or {}

    route = _route_state(route_enable_summary.iloc[0], route_enable_config)
    dispatch_orders = _dispatch_orders(upload_orders, route, upload_file_hash)
    checks = _checks(route, dispatch_orders, thresholds)
    summary = _summary(route, dispatch_orders, checks, upload_file_hash, thresholds)
    config = _config(route, dispatch_orders, summary.iloc[0], thresholds, checks, upload_file_hash)
    return BrokerDispatchReport(
        dispatch_orders=dispatch_orders,
        checks=checks,
        summary=summary,
        config=config,
    )


def write_broker_dispatch_plan(
    *,
    route_enable_dir: str | Path,
    upload_pack_dir: str | Path,
    output_dir: str | Path,
    upload_orders_path: str | Path | None = None,
    thresholds: BrokerDispatchThresholds | None = None,
) -> BrokerDispatchReport:
    route_dir = Path(route_enable_dir)
    upload_dir = Path(upload_pack_dir)
    route_config_path = route_dir / "route_enable_config.json" if route_dir.is_dir() else Path(route_enable_dir)
    if not route_config_path.exists():
        raise FileNotFoundError(f"route-enable config not found: {route_config_path}")
    route_summary_path = (
        route_dir / "route_enable_summary.csv"
        if route_dir.is_dir()
        else route_config_path.with_name("route_enable_summary.csv")
    )
    route_manifest_path = _sidecar_path(route_enable_dir, "manifest.json")
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    upload_file = _upload_orders_path(upload_dir, route_config, upload_orders_path)
    upload_bytes = upload_file.read_bytes()
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=_read_required(route_summary_path, "route_enable_summary"),
        route_enable_config=route_config,
        upload_orders=pd.read_csv(upload_file),
        upload_file_hash=hashlib.sha256(upload_bytes).hexdigest(),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.dispatch_orders.to_csv(out / "broker_dispatch_orders.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_summary.csv", index=False)
    (out / "broker_dispatch_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "route_enable_summary": route_summary_path,
        "route_enable_config": route_config_path,
        "upload_orders": upload_file,
    }
    if route_manifest_path is not None:
        inputs["route_enable_manifest"] = route_manifest_path
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_plan",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchThresholds())},
        inputs=inputs,
    )
    return BrokerDispatchReport(report.dispatch_orders, report.checks, report.summary, report.config, out)


def _dispatch_orders(upload_orders: pd.DataFrame, route: dict[str, Any], upload_file_hash: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    batch_id = _batch_id(route, upload_orders, upload_file_hash)
    for idx, row in upload_orders.reset_index(drop=True).iterrows():
        source_order_id = _source_order_id(row, idx)
        payload = _jsonable_row(row.to_dict())
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        rows.append(
            {
                "dispatch_batch_id": batch_id,
                "dispatch_sequence": idx + 1,
                "dispatch_order_id": f"DSP-{idx + 1:06d}-{payload_hash[:12]}",
                "dispatch_action": "dry_run_submit",
                "dry_run_only": True,
                "target_mode": route["target_mode"],
                "strategy": route["strategy"],
                "market": route["market"],
                "scenario_key": route["scenario_key"],
                "adapter": route["adapter"],
                "source_order_id": source_order_id,
                "source_payload_hash": payload_hash,
                "upload_file_hash": upload_file_hash,
                "route_enable_hash": route["route_enable_hash"],
                "route_dispatch_roundtrip_batch_id": route["dispatch_roundtrip_batch_id"],
                "order_payload_json": json.dumps(payload, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _checks(route: dict[str, Any], dispatch_orders: pd.DataFrame, thresholds: BrokerDispatchThresholds) -> pd.DataFrame:
    orders = int(len(dispatch_orders))
    max_orders = thresholds.max_orders or int(route["max_orders_per_session"])
    target_mode = _identity_key(thresholds.target_mode)
    route_readiness_required = _route_readiness_required(thresholds, route)
    route_readiness_active = bool(route_readiness_required or route["route_readiness_provided"])
    checks = [
        _check(
            "route_enabled",
            route["route_enabled"],
            "is",
            True,
            bool(route["route_enabled"]) or not thresholds.require_route_enabled,
            "route-enable packet is not enabled",
        ),
        _check(
            "target_mode_matches",
            route["target_mode"],
            "==",
            target_mode,
            bool(route["target_mode"] and route["target_mode"] == target_mode),
            "dispatch target mode does not match route-enable target mode",
        ),
        _check(
            "route_dispatch_roundtrip_provided",
            route["dispatch_roundtrip_provided"],
            "is",
            True,
            bool(route["dispatch_roundtrip_provided"]) or not _dispatch_roundtrip_required(thresholds),
            "dispatch requires route-enable dry-run dispatch round-trip proof",
        ),
    ]
    if route_readiness_required:
        checks.append(
            _check(
                "route_readiness_provided",
                route["route_readiness_provided"],
                "is",
                True,
                bool(route["route_readiness_provided"]),
                "dispatch requires route-enable route-readiness proof",
            )
        )
    if route_readiness_active:
        checks.extend(_route_readiness_checks(route))
    checks.extend(
        [
            _check(
                "dispatch_orders_min",
                orders,
                ">=",
                thresholds.min_orders,
                orders >= thresholds.min_orders,
                "dispatch batch does not contain enough orders",
            ),
            _check(
                "dispatch_orders_within_limit",
                orders,
                "<=",
                max_orders,
                orders <= max_orders,
                "dispatch order count exceeds route limit",
            ),
            _check(
                "dispatch_orders_match_route_enable",
                orders,
                "==",
                int(route["upload_orders"]),
                orders == int(route["upload_orders"]),
                "dispatch order count does not match route-enable upload order count",
            ),
            _check(
                "unique_dispatch_order_id",
                int(dispatch_orders["dispatch_order_id"].nunique()),
                "==",
                orders,
                int(dispatch_orders["dispatch_order_id"].nunique()) == orders,
                "dispatch order ids are not unique",
            ),
            _check(
                "unique_source_order_id",
                int(dispatch_orders["source_order_id"].nunique()),
                "==",
                orders,
                int(dispatch_orders["source_order_id"].nunique()) == orders,
                "source order ids are not unique",
            ),
            _check(
                "dry_run_only",
                bool(dispatch_orders["dry_run_only"].astype(bool).all()),
                "is",
                True,
                bool(dispatch_orders["dry_run_only"].astype(bool).all()) or not thresholds.require_dry_run,
                "dispatch plan contains non-dry-run rows",
            ),
        ]
    )
    if _dispatch_roundtrip_required(thresholds) or route["dispatch_roundtrip_provided"]:
        checks.extend(_dispatch_roundtrip_checks(route, target_mode))
    if _shadow_broker_readiness_active(route):
        checks.extend(_shadow_broker_readiness_checks(route))
    if _broker_shadow_broker_readiness_active(route):
        checks.extend(_broker_shadow_broker_readiness_checks(route))
    if _broker_vendor_market_data_batch_active(route):
        checks.extend(_broker_vendor_market_data_batch_checks(route))
    return pd.DataFrame(checks)


def _route_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _check(
            "route_readiness_ready",
            route["route_readiness_ready"],
            "is",
            True,
            bool(route["route_readiness_ready"]),
            "route-enable route-readiness proof is not ready",
        ),
        _check(
            "route_readiness_strategy_matches",
            route["route_readiness_strategy"],
            "==",
            route["strategy"],
            bool(
                route["route_readiness_strategy"]
                and route["strategy"]
                and route["route_readiness_strategy"] == route["strategy"]
            ),
            "route-enable route-readiness strategy does not match dispatch strategy",
        ),
        _check(
            "route_readiness_market_matches",
            route["route_readiness_market"],
            "==",
            route["market"],
            bool(
                route["route_readiness_market"]
                and route["market"]
                and route["route_readiness_market"] == route["market"]
            ),
            "route-enable route-readiness market does not match dispatch market",
        ),
    ]


def _dispatch_roundtrip_checks(route: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            route["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(route["dispatch_roundtrip_ready"]),
            "route-enable dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            route["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(route["dispatch_roundtrip_target_mode"] and route["dispatch_roundtrip_target_mode"] == target_mode),
            "route-enable dispatch round-trip target mode does not match dispatch target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            route["dispatch_roundtrip_strategy"],
            "==",
            route["strategy"],
            bool(
                route["dispatch_roundtrip_strategy"]
                and route["strategy"]
                and route["dispatch_roundtrip_strategy"] == route["strategy"]
            ),
            "route-enable dispatch round-trip strategy does not match dispatch strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            route["dispatch_roundtrip_market"],
            "==",
            route["market"],
            bool(
                route["dispatch_roundtrip_market"]
                and route["market"]
                and route["dispatch_roundtrip_market"] == route["market"]
            ),
            "route-enable dispatch round-trip market does not match dispatch market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            route["dispatch_roundtrip_scenario_key"],
            "==",
            route["scenario_key"],
            bool(
                route["dispatch_roundtrip_scenario_key"]
                and route["scenario_key"]
                and route["dispatch_roundtrip_scenario_key"] == route["scenario_key"]
            ),
            "route-enable dispatch round-trip scenario does not match dispatch scenario",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            route["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(route["dispatch_roundtrip_missing_request_acks"]) <= 0,
            "route-enable dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            route["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(route["dispatch_roundtrip_rejected_orders"]) <= 0,
            "route-enable dispatch round-trip has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            route["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(route["dispatch_roundtrip_unmatched_acks"]) <= 0,
            "route-enable dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "route_enable_dispatch_roundtrip_failed_checks",
            route["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(route["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            "route-enable dispatch round-trip has failed component checks",
        ),
    ]


def _shadow_broker_readiness_active(route: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(route, key_prefix="")


def _shadow_broker_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        route,
        key_prefix="",
        check_prefix="route_shadow_broker",
        label="route-enable shadow broker",
    )


def _broker_shadow_broker_readiness_active(route: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(route, key_prefix="broker_")


def _broker_shadow_broker_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        route,
        key_prefix="broker_",
        check_prefix="route_broker_shadow_broker",
        label="route-enable broker-readiness shadow broker",
        check_provided=True,
    )


def _broker_vendor_market_data_batch_active(route: dict[str, Any]) -> bool:
    vendor = route["broker_dispatch_roundtrip_vendor_market_data_batch"]
    return bool(_to_bool(vendor["provided"]) or int(vendor["dataset_count"]) > 0)


def _broker_vendor_market_data_batch_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    vendor = route["broker_dispatch_roundtrip_vendor_market_data_batch"]
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(vendor["provided"]),
            "is",
            True,
            _to_bool(vendor["provided"]),
            "route-enable broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(vendor["ready"]),
            "is",
            True,
            _to_bool(vendor["ready"]),
            "route-enable broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            f"{prefix}_adapter_matches",
            vendor["adapter"],
            "==",
            route["adapter"],
            bool(vendor["adapter"] and route["adapter"] and vendor["adapter"] == route["adapter"]),
            "route-enable broker-readiness vendor market-data adapter does not match dispatch adapter",
        ),
        _check(
            f"{prefix}_market_matches",
            vendor["market"],
            "==",
            route["market"],
            bool(vendor["market"] and route["market"] and vendor["market"] == route["market"]),
            "route-enable broker-readiness vendor market-data market does not match dispatch market",
        ),
        _check(
            f"{prefix}_dataset_count",
            int(vendor["dataset_count"]),
            ">",
            0,
            int(vendor["dataset_count"]) > 0,
            "route-enable broker-readiness vendor market-data batch has no datasets",
        ),
        _check(
            f"{prefix}_failed_datasets",
            int(vendor["failed_datasets"]),
            "<=",
            0,
            int(vendor["failed_datasets"]) <= 0,
            "route-enable broker-readiness vendor market-data batch has failed datasets",
        ),
        _check(
            f"{prefix}_source_files",
            int(vendor["unique_source_files"]),
            ">",
            0,
            int(vendor["unique_source_files"]) > 0,
            "route-enable broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            f"{prefix}_header_fingerprints",
            int(vendor["unique_header_fingerprints"]),
            ">",
            0,
            int(vendor["unique_header_fingerprints"]) > 0,
            "route-enable broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            f"{prefix}_mapping_sources",
            str(vendor["mapping_sources"]).strip(),
            "!=",
            "",
            bool(str(vendor["mapping_sources"]).strip()),
            "route-enable broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            f"{prefix}_comparison_accepted",
            _to_bool(vendor["comparison_accepted"]),
            "is",
            True,
            _to_bool(vendor["comparison_accepted"]),
            "route-enable broker-readiness vendor market-data comparison was not accepted",
        ),
        _check(
            f"{prefix}_comparison_failed_checks",
            int(vendor["comparison_failed_checks"]),
            "<=",
            0,
            int(vendor["comparison_failed_checks"]) <= 0,
            "route-enable broker-readiness vendor market-data comparison has failed checks",
        ),
    ]


def _shadow_broker_readiness_active_for(route: dict[str, Any], *, key_prefix: str) -> bool:
    session_fields = (
        "readiness_sessions",
        "route_readiness_sessions",
        "dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(route.get(_shadow_broker_key(key_prefix, "readiness_provided"), False))
        or any(int(route[_shadow_broker_key(key_prefix, field)]) > 0 for field in session_fields)
    )


def _shadow_broker_readiness_checks_for(
    route: dict[str, Any],
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
                _to_bool(route[_shadow_broker_key(key_prefix, "readiness_provided")]),
                "is",
                True,
                _to_bool(route[_shadow_broker_key(key_prefix, "readiness_provided")]),
                f"{label} proof is active but not marked provided",
            )
        )
    sessions = int(route[_shadow_broker_key(key_prefix, "readiness_sessions")])
    if sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_readiness_ready",
                    int(route[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(route[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]) == sessions,
                    f"{label} readiness evidence is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_adapter_matches",
                    route[_shadow_broker_key(key_prefix, "adapter")],
                    "==",
                    route["adapter"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "adapter")]
                        and route[_shadow_broker_key(key_prefix, "adapter")] == route["adapter"]
                    ),
                    f"{label} adapter does not match dispatch adapter",
                ),
                _check(
                    f"{check_prefix}_adapter_consistent",
                    int(route[_shadow_broker_key(key_prefix, "adapter_count")]),
                    "==",
                    1,
                    int(route[_shadow_broker_key(key_prefix, "adapter_count")]) == 1,
                    f"{label} adapter identity is missing or mixed",
                ),
            ]
        )
    route_sessions = int(route[_shadow_broker_key(key_prefix, "route_readiness_sessions")])
    if route_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_readiness_ready",
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]),
                    "==",
                    route_sessions,
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]) == route_sessions,
                    f"{label} route-readiness proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_readiness_strategy_matches",
                    route[_shadow_broker_key(key_prefix, "route_readiness_strategy")],
                    "==",
                    route["strategy"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_readiness_strategy")]
                        and route[_shadow_broker_key(key_prefix, "route_readiness_strategy")] == route["strategy"]
                    ),
                    f"{label} route-readiness strategy does not match dispatch strategy",
                ),
                _check(
                    f"{check_prefix}_route_readiness_market_matches",
                    route[_shadow_broker_key(key_prefix, "route_readiness_market")],
                    "==",
                    route["market"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_readiness_market")]
                        and route[_shadow_broker_key(key_prefix, "route_readiness_market")] == route["market"]
                    ),
                    f"{label} route-readiness market does not match dispatch market",
                ),
                _check(
                    f"{check_prefix}_route_readiness_gap_pairs",
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]) <= 0,
                    f"{label} route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_sessions")])
    if dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_dispatch_roundtrip_ready",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")]),
                    "==",
                    dispatch_sessions,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")])
                    == dispatch_sessions,
                    f"{label} dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_strategy_matches",
                    route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")],
                    "==",
                    route["strategy"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        and route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")] == route["strategy"]
                    ),
                    f"{label} dispatch round-trip strategy does not match dispatch strategy",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_market_matches",
                    route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")],
                    "==",
                    route["market"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")]
                        and route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")] == route["market"]
                    ),
                    f"{label} dispatch round-trip market does not match dispatch market",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_scenario_consistent",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_missing_request_acks",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]) <= 0,
                    f"{label} dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_rejected_orders",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]) <= 0,
                    f"{label} dispatch round-trip has rejected orders",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_unmatched_acks",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]) <= 0,
                    f"{label} dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_sessions")])
    if route_dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_ready",
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")]),
                    "==",
                    route_dispatch_sessions,
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")])
                    == route_dispatch_sessions,
                    f"{label} route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_strategy_matches",
                    route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")],
                    "==",
                    route["strategy"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        and route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        == route["strategy"]
                    ),
                    f"{label} route dispatch round-trip strategy does not match dispatch strategy",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_market_matches",
                    route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")],
                    "==",
                    route["market"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        and route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        == route["market"]
                    ),
                    f"{label} route dispatch round-trip market does not match dispatch market",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_scenario_consistent",
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _shadow_broker_key(key_prefix: str, suffix: str) -> str:
    return f"{key_prefix}shadow_broker_{suffix}"


def _summary(
    route: dict[str, Any],
    dispatch_orders: pd.DataFrame,
    checks: pd.DataFrame,
    upload_file_hash: str,
    thresholds: BrokerDispatchThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "dispatch_state": "armed_dry_run" if ready else "disabled",
                "target_mode": route["target_mode"],
                "strategy": route["strategy"],
                "market": route["market"],
                "scenario_key": route["scenario_key"],
                "adapter": route["adapter"],
                "broker_schema_status": route["broker_schema_status"],
                "broker_schema_reviewed": route["broker_schema_reviewed"],
                "broker_schema_review_mode": route["broker_schema_review_mode"],
                "dispatch_orders": int(len(dispatch_orders)),
                "route_upload_orders": int(route["upload_orders"]),
                "max_orders_per_session": int(route["max_orders_per_session"]),
                "max_notional_per_session": float(route["max_notional_per_session"]),
                "upload_file_hash": upload_file_hash,
                "dispatch_batch_id": str(dispatch_orders.iloc[0]["dispatch_batch_id"]) if not dispatch_orders.empty else "",
                "route_readiness_required": _route_readiness_required(thresholds, route),
                "route_readiness_provided": route["route_readiness_provided"],
                "route_readiness_ready": route["route_readiness_ready"],
                "route_readiness_strategy": route["route_readiness_strategy"],
                "route_readiness_market": route["route_readiness_market"],
                "route_readiness_route_ready_pairs": route["route_readiness_route_ready_pairs"],
                "route_readiness_gap_pairs": route["route_readiness_gap_pairs"],
                "shadow_broker_readiness_sessions": route["shadow_broker_readiness_sessions"],
                "shadow_broker_readiness_ready_sessions": route["shadow_broker_readiness_ready_sessions"],
                "shadow_broker_adapter": route["shadow_broker_adapter"],
                "shadow_broker_adapter_count": route["shadow_broker_adapter_count"],
                "shadow_broker_route_readiness_sessions": route["shadow_broker_route_readiness_sessions"],
                "shadow_broker_route_readiness_ready_sessions": route[
                    "shadow_broker_route_readiness_ready_sessions"
                ],
                "shadow_broker_route_readiness_strategy": route["shadow_broker_route_readiness_strategy"],
                "shadow_broker_route_readiness_market": route["shadow_broker_route_readiness_market"],
                "shadow_broker_route_readiness_gap_pairs": route["shadow_broker_route_readiness_gap_pairs"],
                "shadow_broker_dispatch_roundtrip_sessions": route["shadow_broker_dispatch_roundtrip_sessions"],
                "shadow_broker_dispatch_roundtrip_ready_sessions": route[
                    "shadow_broker_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_dispatch_roundtrip_strategy": route["shadow_broker_dispatch_roundtrip_strategy"],
                "shadow_broker_dispatch_roundtrip_market": route["shadow_broker_dispatch_roundtrip_market"],
                "shadow_broker_dispatch_roundtrip_scenario_count": route[
                    "shadow_broker_dispatch_roundtrip_scenario_count"
                ],
                "shadow_broker_dispatch_roundtrip_missing_request_acks": route[
                    "shadow_broker_dispatch_roundtrip_missing_request_acks"
                ],
                "shadow_broker_dispatch_roundtrip_rejected_orders": route[
                    "shadow_broker_dispatch_roundtrip_rejected_orders"
                ],
                "shadow_broker_dispatch_roundtrip_unmatched_acks": route[
                    "shadow_broker_dispatch_roundtrip_unmatched_acks"
                ],
                "shadow_broker_route_dispatch_roundtrip_sessions": route[
                    "shadow_broker_route_dispatch_roundtrip_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": route[
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_strategy": route[
                    "shadow_broker_route_dispatch_roundtrip_strategy"
                ],
                "shadow_broker_route_dispatch_roundtrip_market": route[
                    "shadow_broker_route_dispatch_roundtrip_market"
                ],
                "shadow_broker_route_dispatch_roundtrip_scenario_count": route[
                    "shadow_broker_route_dispatch_roundtrip_scenario_count"
                ],
                **_broker_shadow_broker_summary_fields(route),
                **_broker_vendor_market_data_batch_summary_fields(route),
                **_vendor_market_data_batch_summary_fields(route),
                "route_dispatch_roundtrip_required": route["dispatch_roundtrip_required"],
                "route_dispatch_roundtrip_provided": route["dispatch_roundtrip_provided"],
                "route_dispatch_roundtrip_ready": route["dispatch_roundtrip_ready"],
                "route_dispatch_roundtrip_target_mode": route["dispatch_roundtrip_target_mode"],
                "route_dispatch_roundtrip_strategy": route["dispatch_roundtrip_strategy"],
                "route_dispatch_roundtrip_market": route["dispatch_roundtrip_market"],
                "route_dispatch_roundtrip_scenario_key": route["dispatch_roundtrip_scenario_key"],
                "route_dispatch_roundtrip_batch_id": route["dispatch_roundtrip_batch_id"],
                "route_dispatch_roundtrip_requests": route["dispatch_roundtrip_requests"],
                "route_dispatch_roundtrip_acked_orders": route["dispatch_roundtrip_acked_orders"],
                "route_dispatch_roundtrip_missing_request_acks": route["dispatch_roundtrip_missing_request_acks"],
                "route_dispatch_roundtrip_rejected_orders": route["dispatch_roundtrip_rejected_orders"],
                "route_dispatch_roundtrip_unmatched_acks": route["dispatch_roundtrip_unmatched_acks"],
                "route_enable_dispatch_roundtrip_failed_checks": route[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "dry_run_only": True,
                "failed_checks": failed,
                "recommendation": "ready_for_broker_dryrun_dispatch" if ready else "keep_dispatch_disabled",
            }
        ]
    )


def _broker_shadow_broker_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "route_broker_shadow_broker_readiness_provided": route["broker_shadow_broker_readiness_provided"],
        "route_broker_shadow_broker_readiness_sessions": route["broker_shadow_broker_readiness_sessions"],
        "route_broker_shadow_broker_readiness_ready_sessions": route[
            "broker_shadow_broker_readiness_ready_sessions"
        ],
        "route_broker_shadow_broker_adapter": route["broker_shadow_broker_adapter"],
        "route_broker_shadow_broker_adapter_count": route["broker_shadow_broker_adapter_count"],
        "route_broker_shadow_broker_route_readiness_sessions": route[
            "broker_shadow_broker_route_readiness_sessions"
        ],
        "route_broker_shadow_broker_route_readiness_ready_sessions": route[
            "broker_shadow_broker_route_readiness_ready_sessions"
        ],
        "route_broker_shadow_broker_route_readiness_strategy": route[
            "broker_shadow_broker_route_readiness_strategy"
        ],
        "route_broker_shadow_broker_route_readiness_market": route["broker_shadow_broker_route_readiness_market"],
        "route_broker_shadow_broker_route_readiness_gap_pairs": route[
            "broker_shadow_broker_route_readiness_gap_pairs"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_sessions": route[
            "broker_shadow_broker_dispatch_roundtrip_sessions"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_ready_sessions": route[
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_strategy": route[
            "broker_shadow_broker_dispatch_roundtrip_strategy"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_market": route[
            "broker_shadow_broker_dispatch_roundtrip_market"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_scenario_count": route[
            "broker_shadow_broker_dispatch_roundtrip_scenario_count"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": route[
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_rejected_orders": route[
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": route[
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_sessions": route[
            "broker_shadow_broker_route_dispatch_roundtrip_sessions"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": route[
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_strategy": route[
            "broker_shadow_broker_route_dispatch_roundtrip_strategy"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_market": route[
            "broker_shadow_broker_route_dispatch_roundtrip_market"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": route[
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count"
        ],
    }


def _vendor_market_data_batch_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    vendor = route["vendor_market_data_batch"]
    return {
        "route_vendor_market_data_batch_provided": vendor["provided"],
        "route_vendor_market_data_batch_ready": vendor["ready"],
        "route_vendor_market_data_batch_adapter": vendor["adapter"],
        "route_vendor_market_data_batch_kind": vendor["kind"],
        "route_vendor_market_data_batch_market": vendor["market"],
        "route_vendor_market_data_batch_dataset_count": vendor["dataset_count"],
        "route_vendor_market_data_batch_ready_datasets": vendor["ready_datasets"],
        "route_vendor_market_data_batch_failed_datasets": vendor["failed_datasets"],
        "route_vendor_market_data_batch_ready_rate": vendor["ready_rate"],
        "route_vendor_market_data_batch_unique_source_files": vendor["unique_source_files"],
        "route_vendor_market_data_batch_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        "route_vendor_market_data_batch_mapping_sources": vendor["mapping_sources"],
        "route_vendor_market_data_batch_comparison_accepted": vendor["comparison_accepted"],
        "route_vendor_market_data_batch_comparison_failed_checks": vendor["comparison_failed_checks"],
        "route_vendor_market_data_batch_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_market_data_batch_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    vendor = route["broker_dispatch_roundtrip_vendor_market_data_batch"]
    field_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": vendor["provided"],
        f"{field_prefix}_ready": vendor["ready"],
        f"{field_prefix}_adapter": vendor["adapter"],
        f"{field_prefix}_kind": vendor["kind"],
        f"{field_prefix}_market": vendor["market"],
        f"{field_prefix}_dataset_count": vendor["dataset_count"],
        f"{field_prefix}_ready_datasets": vendor["ready_datasets"],
        f"{field_prefix}_failed_datasets": vendor["failed_datasets"],
        f"{field_prefix}_ready_rate": vendor["ready_rate"],
        f"{field_prefix}_unique_source_files": vendor["unique_source_files"],
        f"{field_prefix}_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        f"{field_prefix}_mapping_sources": vendor["mapping_sources"],
        f"{field_prefix}_comparison_accepted": vendor["comparison_accepted"],
        f"{field_prefix}_comparison_failed_checks": vendor["comparison_failed_checks"],
        f"{field_prefix}_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_shadow_broker_config(summary: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(summary["route_broker_shadow_broker_readiness_provided"]),
        "sessions": int(summary["route_broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(summary["route_broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(summary["route_broker_shadow_broker_adapter"]),
        "adapter_count": int(summary["route_broker_shadow_broker_adapter_count"]),
        "route_readiness": {
            "sessions": int(summary["route_broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(summary["route_broker_shadow_broker_route_readiness_ready_sessions"]),
            "strategy": str(summary["route_broker_shadow_broker_route_readiness_strategy"]),
            "market": str(summary["route_broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(summary["route_broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(summary["route_broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary["route_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(summary["route_broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(summary["route_broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(summary["route_broker_shadow_broker_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(
                summary["route_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(summary["route_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]),
            "max_unmatched_acks": int(summary["route_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(summary["route_broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary["route_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(summary["route_broker_shadow_broker_route_dispatch_roundtrip_strategy"]),
            "market": str(summary["route_broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(summary["route_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _vendor_market_data_batch_config(summary: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(summary["route_vendor_market_data_batch_provided"]),
        "ready": _to_bool(summary["route_vendor_market_data_batch_ready"]),
        "adapter": str(summary["route_vendor_market_data_batch_adapter"]),
        "kind": str(summary["route_vendor_market_data_batch_kind"]),
        "market": str(summary["route_vendor_market_data_batch_market"]),
        "dataset_count": int(summary["route_vendor_market_data_batch_dataset_count"]),
        "ready_datasets": int(summary["route_vendor_market_data_batch_ready_datasets"]),
        "failed_datasets": int(summary["route_vendor_market_data_batch_failed_datasets"]),
        "ready_rate": _jsonable(summary["route_vendor_market_data_batch_ready_rate"]),
        "unique_source_files": int(summary["route_vendor_market_data_batch_unique_source_files"]),
        "unique_header_fingerprints": int(
            summary["route_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "mapping_sources": str(summary["route_vendor_market_data_batch_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(summary["route_vendor_market_data_batch_comparison_accepted"]),
            "failed_checks": int(summary["route_vendor_market_data_batch_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary["route_vendor_market_data_batch_datasets_json"]),
    }


def _broker_vendor_market_data_batch_config(summary: pd.Series) -> dict[str, Any]:
    field_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(summary[f"{field_prefix}_provided"]),
        "ready": _to_bool(summary[f"{field_prefix}_ready"]),
        "adapter": str(summary[f"{field_prefix}_adapter"]),
        "kind": str(summary[f"{field_prefix}_kind"]),
        "market": str(summary[f"{field_prefix}_market"]),
        "dataset_count": int(summary[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(summary[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(summary[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(summary[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(summary[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(summary[f"{field_prefix}_unique_header_fingerprints"]),
        "mapping_sources": str(summary[f"{field_prefix}_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(summary[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(summary[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary[f"{field_prefix}_datasets_json"]),
    }


def _config(
    route: dict[str, Any],
    dispatch_orders: pd.DataFrame,
    summary: pd.Series,
    thresholds: BrokerDispatchThresholds,
    checks: pd.DataFrame,
    upload_file_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": _to_bool(summary["ready"]),
        "dispatch_state": str(summary["dispatch_state"]),
        "dry_run_only": True,
        "dispatch_batch_id": str(summary["dispatch_batch_id"]),
        "target_mode": route["target_mode"],
        "strategy": route["strategy"],
        "market": route["market"],
        "scenario_key": route["scenario_key"],
        "adapter": route["adapter"],
        "broker_readiness": {
            "adapter_schema_status": route["broker_schema_status"],
            "schema_reviewed": _to_bool(route["broker_schema_reviewed"]),
            "schema_review_mode": route["broker_schema_review_mode"],
        },
        "limits": {
            "max_orders_per_session": int(route["max_orders_per_session"]),
            "max_notional_per_session": float(route["max_notional_per_session"]),
            "stop_loss": _jsonable(route["stop_loss"]),
        },
        "upload": {
            "orders": int(route["upload_orders"]),
            "file_hash": upload_file_hash,
            "output_file": route["upload_output_file"],
        },
        "route_readiness": {
            "required": _to_bool(summary["route_readiness_required"]),
            "provided": _to_bool(summary["route_readiness_provided"]),
            "ready": _to_bool(summary["route_readiness_ready"]),
            "strategy": str(summary["route_readiness_strategy"]),
            "market": str(summary["route_readiness_market"]),
            "route_ready_pairs": int(summary["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(summary["route_readiness_gap_pairs"]),
            "recommendation": route["route_readiness_recommendation"],
        },
        "shadow_broker_readiness": {
            "provided": int(summary["shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(summary["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(summary["shadow_broker_readiness_ready_sessions"]),
            "adapter": str(summary["shadow_broker_adapter"]),
            "adapter_count": int(summary["shadow_broker_adapter_count"]),
            "route_readiness": {
                "sessions": int(summary["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(summary["shadow_broker_route_readiness_strategy"]),
                "market": str(summary["shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(summary["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(summary["shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(summary["shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(summary["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(summary["shadow_broker_dispatch_roundtrip_missing_request_acks"]),
                "max_rejected_orders": int(summary["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(summary["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(summary["shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(summary["shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(summary["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "route_broker_shadow_broker_readiness": _broker_shadow_broker_config(summary),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _broker_vendor_market_data_batch_config(summary)
        ),
        "route_vendor_market_data_batch": _vendor_market_data_batch_config(summary),
        "dispatch": {
            "orders": int(len(dispatch_orders)),
            "first_dispatch_order_id": str(dispatch_orders.iloc[0]["dispatch_order_id"])
            if not dispatch_orders.empty
            else "",
            "last_dispatch_order_id": str(dispatch_orders.iloc[-1]["dispatch_order_id"])
            if not dispatch_orders.empty
            else "",
        },
        "route_dispatch_roundtrip": {
            "required": _to_bool(route["dispatch_roundtrip_required"]),
            "provided": _to_bool(route["dispatch_roundtrip_provided"]),
            "ready": _to_bool(route["dispatch_roundtrip_ready"]),
            "target_mode": route["dispatch_roundtrip_target_mode"],
            "strategy": route["dispatch_roundtrip_strategy"],
            "market": route["dispatch_roundtrip_market"],
            "scenario_key": route["dispatch_roundtrip_scenario_key"],
            "dispatch_batch_id": route["dispatch_roundtrip_batch_id"],
            "requests": int(route["dispatch_roundtrip_requests"]),
            "acked_orders": int(route["dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(route["dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(route["dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(route["dispatch_roundtrip_unmatched_acks"]),
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": int(route["route_enable_dispatch_roundtrip_failed_checks"]),
        },
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _route_state(row: pd.Series, config: dict[str, Any]) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    upload = config.get("upload", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    route_readiness = config.get("route_readiness", {}) or {}
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_shadow_broker = config.get("cutover_broker_shadow_broker_readiness", {}) or {}
    broker_shadow_broker_route = broker_shadow_broker.get("route_readiness", {}) or {}
    broker_shadow_broker_dispatch = broker_shadow_broker.get("dispatch_roundtrip", {}) or {}
    broker_shadow_broker_route_dispatch = broker_shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_vendor_market_data_batch = (
        config.get("cutover_broker_dispatch_roundtrip_vendor_market_data_batch", {}) or {}
    )
    vendor_market_data_batch = config.get("cutover_vendor_market_data_batch", {}) or {}
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route_proof = dispatch.get("route_proof", {}) or {}
    payload = _jsonable_row({"summary": row.to_dict(), "config": config})
    route_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "route_enabled": _to_bool(config.get("route_enabled", row.get("ready", False))),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""))),
        "market": _identity_key(_first_text(row.get("market", ""), config.get("market", ""))),
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
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
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "upload_orders": int(_number_from(upload, "orders", _number(row, "upload_orders", 0.0))),
        "upload_output_file": _first_text(upload.get("output_file", "")),
        "route_enable_hash": route_hash,
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(route_readiness.get("ready", row.get("route_readiness_ready", False))),
        "route_readiness_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get("route_readiness_strategy", ""))
        ),
        "route_readiness_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get("route_readiness_market", ""))
        ),
        "route_readiness_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, "route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "route_readiness_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, "route_readiness_gap_pairs", 0.0))
        ),
        "route_readiness_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get("route_readiness_recommendation", ""),
        ),
        "shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("shadow_broker_adapter", ""))
        ),
        "shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "shadow_broker_adapter_count", 0.0),
            )
        ),
        "shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("shadow_broker_route_readiness_market", ""),
            )
        ),
        "shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_provided": _to_bool(
            broker_shadow_broker.get("provided", row.get("cutover_broker_shadow_broker_readiness_provided", False))
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number_from(
                broker_shadow_broker,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number_from(
                broker_shadow_broker,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(
            _first_text(
                broker_shadow_broker.get("adapter", ""),
                row.get("cutover_broker_shadow_broker_adapter", ""),
            )
        ),
        "broker_shadow_broker_adapter_count": int(
            _number_from(
                broker_shadow_broker,
                "adapter_count",
                _number(row, "cutover_broker_shadow_broker_adapter_count", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number_from(
                broker_shadow_broker_route,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                broker_shadow_broker_route,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                broker_shadow_broker_route.get("strategy", ""),
                row.get("cutover_broker_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                broker_shadow_broker_route.get("market", ""),
                row.get("cutover_broker_shadow_broker_route_readiness_market", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                broker_shadow_broker_route,
                "max_gap_pairs",
                _number(row, "cutover_broker_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                broker_shadow_broker_dispatch.get("strategy", ""),
                row.get("cutover_broker_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                broker_shadow_broker_dispatch.get("market", ""),
                row.get("cutover_broker_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "scenario_count",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                broker_shadow_broker_route_dispatch,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                broker_shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                broker_shadow_broker_route_dispatch.get("strategy", ""),
                row.get("cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                broker_shadow_broker_route_dispatch.get("market", ""),
                row.get("cutover_broker_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                broker_shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_state(
            row,
            broker_vendor_market_data_batch,
            field_prefix="cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "vendor_market_data_batch": _vendor_market_data_batch_state(row, vendor_market_data_batch),
        "dispatch_roundtrip_required": _to_bool(
            route_proof.get("required", row.get("route_dispatch_roundtrip_required", False))
        ),
        "dispatch_roundtrip_provided": _to_bool(
            route_proof.get("provided", row.get("route_dispatch_roundtrip_provided", False))
        ),
        "dispatch_roundtrip_ready": _to_bool(
            route_proof.get("ready", row.get("route_dispatch_roundtrip_ready", False))
        ),
        "dispatch_roundtrip_target_mode": _identity_key(
            _first_text(route_proof.get("target_mode", ""), row.get("route_dispatch_roundtrip_target_mode", ""))
        ),
        "dispatch_roundtrip_strategy": _strategy_key(
            _first_text(route_proof.get("strategy", ""), row.get("route_dispatch_roundtrip_strategy", ""))
        ),
        "dispatch_roundtrip_market": _identity_key(
            _first_text(route_proof.get("market", ""), row.get("route_dispatch_roundtrip_market", ""))
        ),
        "dispatch_roundtrip_scenario_key": _first_text(
            route_proof.get("scenario_key", ""),
            row.get("route_dispatch_roundtrip_scenario_key", ""),
        ),
        "dispatch_roundtrip_batch_id": _first_text(
            route_proof.get("dispatch_batch_id", ""),
            row.get("route_dispatch_roundtrip_batch_id", ""),
        ),
        "dispatch_roundtrip_requests": int(
            _number_from(route_proof, "requests", _number(row, "route_dispatch_roundtrip_requests", 0.0))
        ),
        "dispatch_roundtrip_acked_orders": int(
            _number_from(route_proof, "acked_orders", _number(row, "route_dispatch_roundtrip_acked_orders", 0.0))
        ),
        "dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                route_proof,
                "missing_request_acks",
                _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_rejected_orders": int(
            _number_from(route_proof, "rejected_orders", _number(row, "route_dispatch_roundtrip_rejected_orders", 0.0))
        ),
        "dispatch_roundtrip_unmatched_acks": int(
            _number_from(route_proof, "unmatched_acks", _number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0))
        ),
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number_from(
                route_enable,
                "failed_checks",
                _number(
                    row,
                    "route_enable_dispatch_roundtrip_failed_checks",
                    _number(row, "dispatch_roundtrip_failed_checks", 0.0),
                ),
            )
        ),
    }


def _batch_id(route: dict[str, Any], upload_orders: pd.DataFrame, upload_file_hash: str) -> str:
    seed = {
        "route_enable_hash": route["route_enable_hash"],
        "upload_file_hash": upload_file_hash,
        "orders": len(upload_orders),
    }
    return f"BDP-{hashlib.sha256(json.dumps(seed, sort_keys=True).encode('utf-8')).hexdigest()[:16]}"


def _vendor_market_data_batch_state(
    row: pd.Series,
    vendor: dict[str, Any],
    *,
    field_prefix: str = "cutover_vendor_market_data_batch",
) -> dict[str, Any]:
    comparison = vendor.get("comparison", {}) or {}
    datasets = vendor.get("datasets")
    if datasets is None:
        datasets = _json_list(row.get(f"{field_prefix}_datasets_json", "[]"))
    datasets = datasets or []
    return {
        "provided": _to_bool(vendor.get("provided", row.get(f"{field_prefix}_provided", False))),
        "ready": _to_bool(vendor.get("ready", row.get(f"{field_prefix}_ready", False))),
        "adapter": _first_text(vendor.get("adapter", ""), row.get(f"{field_prefix}_adapter", "")),
        "kind": _first_text(vendor.get("kind", ""), row.get(f"{field_prefix}_kind", "")),
        "market": _identity_key(
            _first_text(vendor.get("market", ""), row.get(f"{field_prefix}_market", ""))
        ),
        "dataset_count": int(
            _number_from(
                vendor,
                "dataset_count",
                _number(row, f"{field_prefix}_dataset_count", 0.0),
            )
        ),
        "ready_datasets": int(
            _number_from(
                vendor,
                "ready_datasets",
                _number(row, f"{field_prefix}_ready_datasets", 0.0),
            )
        ),
        "failed_datasets": int(
            _number_from(
                vendor,
                "failed_datasets",
                _number(row, f"{field_prefix}_failed_datasets", 0.0),
            )
        ),
        "ready_rate": _number_from(
            vendor,
            "ready_rate",
            _number(row, f"{field_prefix}_ready_rate", 0.0),
        ),
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
        "mapping_sources": _first_text(
            vendor.get("mapping_sources", ""),
            row.get(f"{field_prefix}_mapping_sources", ""),
        ),
        "comparison_accepted": _to_bool(
            comparison.get("accepted", row.get(f"{field_prefix}_comparison_accepted", False))
        ),
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


def _source_order_id(row: pd.Series, idx: int) -> str:
    for column in ("client_order_id", "client_tag", "broker_order_id", "tag", "strategy_tag"):
        value = _object_text(row.get(column, ""))
        if value:
            return value
    return f"row-{idx + 1:06d}"


def _upload_orders_path(upload_dir: Path, route_config: dict[str, Any], override: str | Path | None) -> Path:
    if override is not None:
        candidate = Path(override)
    else:
        upload_file = str((route_config.get("upload", {}) or {}).get("output_file", "")).strip()
        filename = upload_file or "broker_upload_orders.csv"
        if upload_dir.is_dir():
            direct = upload_dir / filename
            candidate = next(
                (
                    nested
                    for folder in ("05_upload_pack", "04_upload_pack")
                    if (nested := upload_dir / folder / filename).exists()
                ),
                direct,
            )
        else:
            candidate = upload_dir
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"broker upload orders not found: {candidate}")
    return candidate


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch input is empty: {name}")
    return frame


def _sidecar_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        file_path = candidate / filename
    else:
        file_path = candidate if candidate.name == filename else candidate.with_name(filename)
    return file_path if file_path.exists() else None


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: BrokerDispatchThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: BrokerDispatchThresholds, route: dict[str, Any] | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (route is not None and route["route_readiness_required"])
    )


def _validate_thresholds(thresholds: BrokerDispatchThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")
    if thresholds.max_orders is not None and thresholds.max_orders <= 0:
        raise ValueError("max_orders must be positive")


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
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


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
