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
    summary = _summary(route, dispatch_orders, checks, upload_file_hash)
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
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_plan",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchThresholds())},
        inputs={"route_enable": route_config_path, "upload_orders": upload_file},
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
                "order_payload_json": json.dumps(payload, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _checks(route: dict[str, Any], dispatch_orders: pd.DataFrame, thresholds: BrokerDispatchThresholds) -> pd.DataFrame:
    orders = int(len(dispatch_orders))
    max_orders = thresholds.max_orders or int(route["max_orders_per_session"])
    target_mode = _identity_key(thresholds.target_mode)
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
    return pd.DataFrame(checks)


def _summary(
    route: dict[str, Any],
    dispatch_orders: pd.DataFrame,
    checks: pd.DataFrame,
    upload_file_hash: str,
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
                "dispatch_orders": int(len(dispatch_orders)),
                "route_upload_orders": int(route["upload_orders"]),
                "max_orders_per_session": int(route["max_orders_per_session"]),
                "max_notional_per_session": float(route["max_notional_per_session"]),
                "upload_file_hash": upload_file_hash,
                "dispatch_batch_id": str(dispatch_orders.iloc[0]["dispatch_batch_id"]) if not dispatch_orders.empty else "",
                "dry_run_only": True,
                "failed_checks": failed,
                "recommendation": "ready_for_broker_dryrun_dispatch" if ready else "keep_dispatch_disabled",
            }
        ]
    )


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
        "dispatch": {
            "orders": int(len(dispatch_orders)),
            "first_dispatch_order_id": str(dispatch_orders.iloc[0]["dispatch_order_id"])
            if not dispatch_orders.empty
            else "",
            "last_dispatch_order_id": str(dispatch_orders.iloc[-1]["dispatch_order_id"])
            if not dispatch_orders.empty
            else "",
        },
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _route_state(row: pd.Series, config: dict[str, Any]) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    upload = config.get("upload", {}) or {}
    payload = _jsonable_row({"summary": row.to_dict(), "config": config})
    route_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "route_enabled": _to_bool(config.get("route_enabled", row.get("ready", False))),
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
        "upload_orders": int(_number_from(upload, "orders", _number(row, "upload_orders", 0.0))),
        "upload_output_file": _first_text(upload.get("output_file", "")),
        "route_enable_hash": route_hash,
    }


def _batch_id(route: dict[str, Any], upload_orders: pd.DataFrame, upload_file_hash: str) -> str:
    seed = {
        "route_enable_hash": route["route_enable_hash"],
        "upload_file_hash": upload_file_hash,
        "orders": len(upload_orders),
    }
    return f"BDP-{hashlib.sha256(json.dumps(seed, sort_keys=True).encode('utf-8')).hexdigest()[:16]}"


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
        candidate = upload_dir / (upload_file or "broker_upload_orders.csv")
    if not candidate.exists():
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


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


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
