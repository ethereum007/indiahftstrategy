from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import get_adapter
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class BrokerDispatchSendThresholds:
    target_mode: str = "live_dryrun"
    require_dispatch_ready: bool = True
    require_armed_dispatch: bool = True
    require_dry_run: bool = True
    require_dispatch_roundtrip: bool = False
    max_requests: int | None = None


@dataclass(frozen=True)
class BrokerDispatchSendReport:
    requests: pd.DataFrame
    expected_acks: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_dispatch_send_packet(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds | None = None,
) -> BrokerDispatchSendReport:
    thresholds = thresholds or BrokerDispatchSendThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")

    summary_row = dispatch_summary.iloc[0]
    requests = _request_rows(summary_row, dispatch_orders)
    expected_acks = _expected_ack_template(requests)
    checks = _checks(summary_row, dispatch_orders, requests, thresholds)
    summary = _summary(summary_row, requests, checks)
    config = _config(summary.iloc[0], requests, thresholds, checks)
    return BrokerDispatchSendReport(
        requests=requests,
        expected_acks=expected_acks,
        checks=checks,
        summary=summary,
        config=config,
    )


def write_broker_dispatch_send_packet(
    *,
    dispatch_dir: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchSendThresholds | None = None,
) -> BrokerDispatchSendReport:
    dispatch = Path(dispatch_dir)
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=_read_required(dispatch / "broker_dispatch_summary.csv", "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch / "broker_dispatch_orders.csv", "broker_dispatch_orders"),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.requests.to_csv(out / "broker_dispatch_send_requests.csv", index=False)
    report.expected_acks.to_csv(out / "broker_dispatch_expected_acks.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_send_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_send_summary.csv", index=False)
    (out / "broker_dispatch_send_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_send_packet",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchSendThresholds())},
        inputs={"dispatch": dispatch},
    )
    return BrokerDispatchSendReport(
        report.requests,
        report.expected_acks,
        report.checks,
        report.summary,
        report.config,
        out,
    )


def _request_rows(dispatch_summary: pd.Series, dispatch_orders: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    adapter = _text(dispatch_summary, "adapter") or _first_order_text(dispatch_orders, "adapter")
    target_mode = _identity_key(_text(dispatch_summary, "target_mode") or _first_order_text(dispatch_orders, "target_mode"))
    for index, order in dispatch_orders.reset_index(drop=True).iterrows():
        payload, payload_error = _order_payload(order)
        envelope = {
            "adapter": adapter,
            "target_mode": target_mode,
            "dry_run_only": True,
            "submission_enabled": False,
            "dispatch_batch_id": _text(order, "dispatch_batch_id"),
            "dispatch_order_id": _text(order, "dispatch_order_id"),
            "route_dispatch_roundtrip_batch_id": _text(order, "route_dispatch_roundtrip_batch_id")
            or _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "source_order_id": _text(order, "source_order_id"),
            "source_payload_hash": _text(order, "source_payload_hash"),
            "order": payload,
        }
        request_hash = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode("utf-8")).hexdigest()
        rows.append(
            {
                "request_id": f"BDR-{index + 1:06d}-{request_hash[:12]}",
                "dispatch_batch_id": _text(order, "dispatch_batch_id"),
                "dispatch_order_id": _text(order, "dispatch_order_id"),
                "route_dispatch_roundtrip_batch_id": _text(order, "route_dispatch_roundtrip_batch_id")
                or _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
                "source_order_id": _text(order, "source_order_id"),
                "target_mode": target_mode,
                "strategy": _text(order, "strategy") or _text(dispatch_summary, "strategy"),
                "market": _text(order, "market") or _text(dispatch_summary, "market"),
                "scenario_key": _text(order, "scenario_key") or _text(dispatch_summary, "scenario_key"),
                "adapter": adapter,
                "request_action": _text(order, "dispatch_action") or "dry_run_submit",
                "transport": "file_packet",
                "endpoint": f"{adapter}.orders.dry_run_submit",
                "http_method": "POST",
                "submission_enabled": False,
                "dry_run_only": _to_bool(order.get("dry_run_only", False)),
                "idempotency_key": f"IDEMP-{request_hash[:24]}",
                "source_payload_hash": _text(order, "source_payload_hash"),
                "request_payload_hash": request_hash,
                "payload_valid": payload_error == "",
                "payload_error": payload_error,
                "request_payload_json": json.dumps(envelope, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _expected_ack_template(requests: pd.DataFrame) -> pd.DataFrame:
    if requests.empty:
        return pd.DataFrame(
            columns=[
                "dispatch_order_id",
                "source_order_id",
                "request_id",
                "idempotency_key",
                "route_dispatch_roundtrip_batch_id",
                "adapter",
                "target_mode",
                "broker_order_id",
                "ack_status",
                "ack_ts_ns",
                "notes",
            ]
        )
    return pd.DataFrame(
        [
            {
                "dispatch_order_id": row.dispatch_order_id,
                "source_order_id": row.source_order_id,
                "request_id": row.request_id,
                "idempotency_key": row.idempotency_key,
                "route_dispatch_roundtrip_batch_id": row.route_dispatch_roundtrip_batch_id,
                "adapter": row.adapter,
                "target_mode": row.target_mode,
                "broker_order_id": "",
                "ack_status": "",
                "ack_ts_ns": "",
                "notes": "fill from Arrow.money/iRage dry-run acknowledgement log",
            }
            for row in requests.itertuples(index=False)
        ]
    )


def _checks(
    dispatch_summary: pd.Series,
    dispatch_orders: pd.DataFrame,
    requests: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
) -> pd.DataFrame:
    orders = int(len(dispatch_orders))
    request_count = int(len(requests))
    max_requests = thresholds.max_requests if thresholds.max_requests is not None else orders
    summary_ready = _to_bool(dispatch_summary.get("ready", False))
    dispatch_state = _identity_key(dispatch_summary.get("dispatch_state", ""))
    target_mode = _identity_key(dispatch_summary.get("target_mode", ""))
    adapter = _text(dispatch_summary, "adapter") or _first_order_text(dispatch_orders, "adapter")
    adapter_known = _adapter_known(adapter)
    dry_run_only = bool(requests["dry_run_only"].astype(bool).all()) if not requests.empty else False
    submission_disabled = bool((~requests["submission_enabled"].astype(bool)).all()) if not requests.empty else False
    unique_idempotency = int(requests["idempotency_key"].nunique()) if not requests.empty else 0
    payloads_valid = bool(requests["payload_valid"].astype(bool).all()) if not requests.empty else False
    route_roundtrip_active = _dispatch_roundtrip_required(thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    )
    route_batch_id = _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
    order_route_batches = _unique_text_values(dispatch_orders, "route_dispatch_roundtrip_batch_id")
    request_route_batches = _unique_text_values(requests, "route_dispatch_roundtrip_batch_id")
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                summary_ready,
                "is",
                True,
                summary_ready or not thresholds.require_dispatch_ready,
                "broker dispatch plan is not ready",
            ),
            _check(
                "dispatch_armed_dry_run",
                dispatch_state,
                "==",
                "armed_dry_run",
                dispatch_state == "armed_dry_run" or not thresholds.require_armed_dispatch,
                "dispatch state is not armed for dry-run sending",
            ),
            _check(
                "target_mode_matches",
                target_mode,
                "==",
                thresholds.target_mode,
                target_mode == thresholds.target_mode,
                "sender packet target mode does not match dispatch target",
            ),
            _check(
                "route_dispatch_roundtrip_provided",
                _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False))
                or not _dispatch_roundtrip_required(thresholds),
                "sender packet requires dispatch plan with route round-trip proof",
            ),
            _check("adapter_known", adapter, "in", "known adapters", adapter_known, "dispatch adapter is unknown"),
            _check(
                "request_count_matches_dispatch",
                request_count,
                "==",
                orders,
                request_count == orders,
                "sender packet request count does not match dispatch order count",
            ),
            _check(
                "request_count_within_limit",
                request_count,
                "<=",
                max_requests,
                request_count <= max_requests,
                "sender packet request count exceeds limit",
            ),
            _check(
                "dry_run_only",
                dry_run_only,
                "is",
                True,
                dry_run_only or not thresholds.require_dry_run,
                "sender packet contains non-dry-run requests",
            ),
            _check(
                "submission_disabled",
                submission_disabled,
                "is",
                True,
                submission_disabled,
                "sender packet would enable live submission",
            ),
            _check(
                "unique_idempotency_key",
                unique_idempotency,
                "==",
                request_count,
                unique_idempotency == request_count,
                "sender packet idempotency keys are not unique",
            ),
            _check("payloads_valid", payloads_valid, "is", True, payloads_valid, "dispatch payload JSON is invalid"),
        ]
    )
    if _dispatch_roundtrip_required(thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    ):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_dispatch_roundtrip_checks(dispatch_summary, target_mode)),
                pd.DataFrame(
                    [
                        _check(
                            "dispatch_order_route_roundtrip_batch_matches",
                            "|".join(order_route_batches),
                            "==",
                            route_batch_id,
                            bool(
                                route_batch_id
                                and len(order_route_batches) == 1
                                and order_route_batches[0] == route_batch_id
                            ),
                            "dispatch order route proof batch ids do not match dispatch summary",
                        ),
                        _check(
                            "request_route_roundtrip_batch_matches",
                            "|".join(request_route_batches),
                            "==",
                            route_batch_id,
                            bool(
                                route_batch_id
                                and len(request_route_batches) == 1
                                and request_route_batches[0] == route_batch_id
                            ),
                            "sender request route proof batch ids do not match dispatch summary",
                        ),
                    ]
                )
                if route_roundtrip_active
                else pd.DataFrame(),
            ],
            ignore_index=True,
        )
    return checks


def _dispatch_roundtrip_checks(dispatch_summary: pd.Series, target_mode: str) -> list[dict[str, object]]:
    strategy = _text(dispatch_summary, "strategy")
    market = _identity_key(dispatch_summary.get("market", ""))
    scenario = _text(dispatch_summary, "scenario_key")
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "dispatch route round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")),
            "==",
            target_mode,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")) == target_mode
            ),
            "dispatch route round-trip target mode does not match sender target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")),
            "==",
            _identity_key(strategy),
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")) == _identity_key(strategy)
            ),
            "dispatch route round-trip strategy does not match sender strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", "")) == market
            ),
            "dispatch route round-trip market does not match sender market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key"),
            "==",
            scenario,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") and scenario)
            and _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") == scenario,
            "dispatch route round-trip scenario does not match sender scenario",
        ),
        _check(
            "route_dispatch_roundtrip_batch_id_provided",
            _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "is not",
            "",
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_batch_id")),
            "dispatch route round-trip proof batch id is missing",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)) <= 0,
            "dispatch route round-trip has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)) <= 0,
            "dispatch route round-trip has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)) <= 0,
            "dispatch route round-trip has unmatched acknowledgements",
        ),
    ]


def _summary(dispatch_summary: pd.Series, requests: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "request_state": "dry_run_send_packet_ready" if ready else "disabled",
                "target_mode": _identity_key(dispatch_summary.get("target_mode", "")),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                "dispatch_batch_id": _text(dispatch_summary, "dispatch_batch_id"),
                "dispatch_orders": int(_number(dispatch_summary, "dispatch_orders", len(requests))),
                "requests": int(len(requests)),
                "route_dispatch_roundtrip_required": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_required", False)
                ),
                "route_dispatch_roundtrip_provided": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_provided", False)
                ),
                "route_dispatch_roundtrip_ready": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_ready", False)
                ),
                "route_dispatch_roundtrip_target_mode": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")
                ),
                "route_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_strategy", "")
                ),
                "route_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_market", "")
                ),
                "route_dispatch_roundtrip_scenario_key": _text(
                    dispatch_summary, "route_dispatch_roundtrip_scenario_key"
                ),
                "route_dispatch_roundtrip_batch_id": _text(
                    dispatch_summary, "route_dispatch_roundtrip_batch_id"
                ),
                "route_dispatch_roundtrip_requests": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_requests", 0.0)
                ),
                "route_dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_acked_orders", 0.0)
                ),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "route_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "route_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "dry_run_only": bool(requests["dry_run_only"].astype(bool).all()) if not requests.empty else False,
                "submission_enabled": False,
                "failed_checks": failed,
                "recommendation": "ready_for_non_submitting_broker_sender_review"
                if ready
                else "keep_broker_sender_disabled",
            }
        ]
    )


def _config(
    summary: pd.Series,
    requests: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": _to_bool(summary["ready"]),
        "request_state": _text(summary, "request_state"),
        "submission_enabled": False,
        "transport": "file_packet",
        "target_mode": _text(summary, "target_mode"),
        "strategy": _text(summary, "strategy"),
        "market": _text(summary, "market"),
        "scenario_key": _text(summary, "scenario_key"),
        "adapter": _text(summary, "adapter"),
        "dispatch_batch_id": _text(summary, "dispatch_batch_id"),
        "requests": int(summary["requests"]),
        "first_request_id": str(requests.iloc[0]["request_id"]) if not requests.empty else "",
        "last_request_id": str(requests.iloc[-1]["request_id"]) if not requests.empty else "",
        "route_dispatch_roundtrip": {
            "required": _to_bool(summary["route_dispatch_roundtrip_required"]),
            "provided": _to_bool(summary["route_dispatch_roundtrip_provided"]),
            "ready": _to_bool(summary["route_dispatch_roundtrip_ready"]),
            "target_mode": _text(summary, "route_dispatch_roundtrip_target_mode"),
            "strategy": _text(summary, "route_dispatch_roundtrip_strategy"),
            "market": _text(summary, "route_dispatch_roundtrip_market"),
            "scenario_key": _text(summary, "route_dispatch_roundtrip_scenario_key"),
            "dispatch_batch_id": _text(summary, "route_dispatch_roundtrip_batch_id"),
            "requests": int(summary["route_dispatch_roundtrip_requests"]),
            "acked_orders": int(summary["route_dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(summary["route_dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(summary["route_dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(summary["route_dispatch_roundtrip_unmatched_acks"]),
        },
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _order_payload(order: pd.Series) -> tuple[dict[str, Any], str]:
    raw = _text(order, "order_payload_json")
    if not raw:
        return {}, "missing order_payload_json"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"invalid order_payload_json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "order_payload_json is not an object"
    return _jsonable_row(payload), ""


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch send input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch send input is empty: {name}")
    return frame


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: BrokerDispatchSendThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _validate_thresholds(thresholds: BrokerDispatchSendThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_requests is not None and thresholds.max_requests <= 0:
        raise ValueError("max_requests must be positive")


def _adapter_known(adapter: str) -> bool:
    try:
        get_adapter(adapter)
    except ValueError:
        return False
    return True


def _first_order_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return str(values.iloc[0]) if not values.empty else ""


def _unique_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).str.strip()
    return sorted(set(values.loc[values != ""]))


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


def _identity_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed", "armed", "accepted"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
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
