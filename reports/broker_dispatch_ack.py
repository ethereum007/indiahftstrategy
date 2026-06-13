from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


ACCEPTED_ACK_STATUSES = {
    "accepted",
    "ack",
    "acked",
    "acknowledged",
    "queued",
    "submitted",
    "dry_run_accepted",
    "success",
    "ok",
}
REJECTED_ACK_STATUSES = {"reject", "rejected", "error", "failed", "denied", "blocked"}


@dataclass(frozen=True)
class BrokerDispatchAckThresholds:
    require_dispatch_ready: bool = True
    require_all_acked: bool = True
    require_dispatch_roundtrip: bool = False
    allow_rejections: bool = False
    max_duplicate_ack_orders: int = 0
    max_unmatched_acks: int = 0


@dataclass(frozen=True)
class BrokerDispatchAckReport:
    acknowledgements: pd.DataFrame
    unmatched_acks: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_broker_dispatch_acknowledgements(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    broker_acks: pd.DataFrame,
    thresholds: BrokerDispatchAckThresholds | None = None,
) -> BrokerDispatchAckReport:
    thresholds = thresholds or BrokerDispatchAckThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")
    broker_acks = _normalize_acks(broker_acks)
    acknowledgements = _acknowledgements(dispatch_orders, broker_acks)
    unmatched = _unmatched_acks(dispatch_orders, broker_acks)
    checks = _checks(dispatch_summary.iloc[0], acknowledgements, unmatched, thresholds)
    summary = _summary(dispatch_summary.iloc[0], acknowledgements, unmatched, checks)
    config = _config(summary.iloc[0], thresholds, checks)
    return BrokerDispatchAckReport(
        acknowledgements=acknowledgements,
        unmatched_acks=unmatched,
        checks=checks,
        summary=summary,
        config=config,
    )


def write_broker_dispatch_acknowledgements(
    *,
    dispatch_dir: str | Path,
    acks_path: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchAckThresholds | None = None,
) -> BrokerDispatchAckReport:
    dispatch = Path(dispatch_dir)
    acks = Path(acks_path)
    if not acks.exists():
        raise FileNotFoundError(f"broker acknowledgement file not found: {acks}")
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=_read_required(dispatch / "broker_dispatch_summary.csv", "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch / "broker_dispatch_orders.csv", "broker_dispatch_orders"),
        broker_acks=pd.read_csv(acks),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.acknowledgements.to_csv(out / "broker_dispatch_acknowledgements.csv", index=False)
    report.unmatched_acks.to_csv(out / "broker_dispatch_unmatched_acks.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_ack_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_ack_summary.csv", index=False)
    (out / "broker_dispatch_ack_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_ack_reconciliation",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchAckThresholds())},
        inputs={"dispatch": dispatch, "acks": acks},
    )
    return BrokerDispatchAckReport(
        report.acknowledgements,
        report.unmatched_acks,
        report.checks,
        report.summary,
        report.config,
        out,
    )


def _acknowledgements(dispatch_orders: pd.DataFrame, acks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, order in dispatch_orders.reset_index(drop=True).iterrows():
        matches, match_key = _matching_acks(order, acks)
        status = _latest_text(matches, "ack_status")
        broker_order_id = _latest_text(matches, "broker_order_id")
        ack_ts_ns = _latest_number(matches, "ack_ts_ns")
        dispatch_route_batch_id = _text(order, "route_dispatch_roundtrip_batch_id")
        ack_route_batch_ids = _unique_text_values(matches, "route_dispatch_roundtrip_batch_id")
        ack_count = int(len(matches))
        rows.append(
            {
                "dispatch_batch_id": _text(order, "dispatch_batch_id"),
                "dispatch_order_id": _text(order, "dispatch_order_id"),
                "route_dispatch_roundtrip_batch_id": (
                    ack_route_batch_ids[0] if len(ack_route_batch_ids) == 1 else dispatch_route_batch_id
                ),
                "dispatch_order_route_roundtrip_batch_id": dispatch_route_batch_id,
                "ack_route_dispatch_roundtrip_batch_ids": "|".join(ack_route_batch_ids),
                "source_order_id": _text(order, "source_order_id"),
                "target_mode": _text(order, "target_mode"),
                "strategy": _text(order, "strategy"),
                "market": _text(order, "market"),
                "adapter": _text(order, "adapter"),
                "ack_count": ack_count,
                "ack_status": status,
                "broker_order_id": broker_order_id,
                "ack_ts_ns": ack_ts_ns,
                "match_key": match_key,
                "acked": status in ACCEPTED_ACK_STATUSES,
                "rejected": status in REJECTED_ACK_STATUSES,
                "duplicate_ack": ack_count > 1,
                "missing_ack": ack_count == 0,
            }
        )
    return pd.DataFrame(rows)


def _unmatched_acks(dispatch_orders: pd.DataFrame, acks: pd.DataFrame) -> pd.DataFrame:
    if acks.empty:
        return acks
    dispatch_ids = set(dispatch_orders.get("dispatch_order_id", pd.Series(dtype=object)).dropna().astype(str))
    source_ids = set(dispatch_orders.get("source_order_id", pd.Series(dtype=object)).dropna().astype(str))
    matched = pd.Series(False, index=acks.index)
    if "dispatch_order_id" in acks.columns:
        matched = matched | acks["dispatch_order_id"].astype(str).isin(dispatch_ids)
    if "source_order_id" in acks.columns:
        matched = matched | acks["source_order_id"].astype(str).isin(source_ids)
    return acks.loc[~matched].reset_index(drop=True)


def _checks(
    dispatch_summary: pd.Series,
    acknowledgements: pd.DataFrame,
    unmatched_acks: pd.DataFrame,
    thresholds: BrokerDispatchAckThresholds,
) -> pd.DataFrame:
    dispatch_ready = _to_bool(dispatch_summary.get("ready", False))
    orders = int(len(acknowledgements))
    acked = int(acknowledgements["acked"].astype(bool).sum()) if orders else 0
    rejected = int(acknowledgements["rejected"].astype(bool).sum()) if orders else 0
    missing = int(acknowledgements["missing_ack"].astype(bool).sum()) if orders else 0
    duplicates = int(acknowledgements["duplicate_ack"].astype(bool).sum()) if orders else 0
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                dispatch_ready,
                "is",
                True,
                dispatch_ready or not thresholds.require_dispatch_ready,
                "broker dispatch plan is not ready",
            ),
            _check(
                "all_dispatch_orders_acked",
                acked,
                "==",
                orders,
                (acked == orders and missing == 0) or not thresholds.require_all_acked,
                "not every dispatch order has an accepted acknowledgement",
            ),
            _check(
                "rejected_orders",
                rejected,
                "==",
                0,
                rejected == 0 or thresholds.allow_rejections,
                "broker acknowledgements include rejected orders",
            ),
            _check(
                "duplicate_ack_orders",
                duplicates,
                "<=",
                thresholds.max_duplicate_ack_orders,
                duplicates <= thresholds.max_duplicate_ack_orders,
                "duplicate acknowledgements exceeded threshold",
            ),
            _check(
                "unmatched_acks",
                int(len(unmatched_acks)),
                "<=",
                thresholds.max_unmatched_acks,
                int(len(unmatched_acks)) <= thresholds.max_unmatched_acks,
                "broker acknowledgement file contains unmatched rows",
            ),
        ]
    )
    if _dispatch_roundtrip_required(dispatch_summary, thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    ):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_dispatch_roundtrip_checks(dispatch_summary)),
                pd.DataFrame(_route_batch_continuity_checks(dispatch_summary, acknowledgements)),
            ],
            ignore_index=True,
        )
    return checks


def _dispatch_roundtrip_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    target_mode = _identity_key(dispatch_summary.get("target_mode", ""))
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    scenario = _text(dispatch_summary, "scenario_key")
    return [
        _check(
            "route_dispatch_roundtrip_provided",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
            "ack reconciliation requires dispatch plan with route round-trip proof",
        ),
        _check(
            "route_dispatch_roundtrip_ready",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "dispatch route round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_batch_id_provided",
            _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "nonempty",
            True,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_batch_id")),
            "dispatch route round-trip proof batch id is missing",
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
            "dispatch route round-trip target mode does not match acknowledgement target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")),
            "==",
            strategy,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")) == strategy
            ),
            "dispatch route round-trip strategy does not match acknowledgement strategy",
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
            "dispatch route round-trip market does not match acknowledgement market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key"),
            "==",
            scenario,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") and scenario)
            and _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") == scenario,
            "dispatch route round-trip scenario does not match acknowledgement scenario",
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


def _route_batch_continuity_checks(
    dispatch_summary: pd.Series,
    acknowledgements: pd.DataFrame,
) -> list[dict[str, object]]:
    route_batch_id = _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
    dispatch_order_batches = _unique_text_values(acknowledgements, "dispatch_order_route_roundtrip_batch_id")
    ack_route_batches = _unique_pipe_text_values(acknowledgements, "ack_route_dispatch_roundtrip_batch_ids")
    matched = acknowledgements.loc[acknowledgements["ack_count"].astype(int) > 0] if not acknowledgements.empty else acknowledgements
    missing_ack_route_batches = (
        int((matched["ack_route_dispatch_roundtrip_batch_ids"].astype(str).str.strip() == "").sum())
        if not matched.empty and "ack_route_dispatch_roundtrip_batch_ids" in matched.columns
        else 0
    )
    return [
        _check(
            "dispatch_order_route_roundtrip_batch_matches",
            "|".join(dispatch_order_batches),
            "==",
            route_batch_id,
            bool(route_batch_id and len(dispatch_order_batches) == 1 and dispatch_order_batches[0] == route_batch_id),
            "dispatch order route proof batch ids do not match dispatch summary",
        ),
        _check(
            "ack_route_roundtrip_batch_matches",
            f"{'|'.join(ack_route_batches)}; missing={missing_ack_route_batches}",
            "==",
            route_batch_id,
            bool(
                route_batch_id
                and missing_ack_route_batches == 0
                and len(ack_route_batches) == 1
                and ack_route_batches[0] == route_batch_id
            ),
            "broker acknowledgement route proof batch ids do not match dispatch summary",
        ),
    ]


def _summary(
    dispatch_summary: pd.Series,
    acknowledgements: pd.DataFrame,
    unmatched_acks: pd.DataFrame,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    orders = int(len(acknowledgements))
    acked = int(acknowledgements["acked"].astype(bool).sum()) if orders else 0
    rejected = int(acknowledgements["rejected"].astype(bool).sum()) if orders else 0
    missing = int(acknowledgements["missing_ack"].astype(bool).sum()) if orders else 0
    duplicates = int(acknowledgements["duplicate_ack"].astype(bool).sum()) if orders else 0
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "target_mode": _text(dispatch_summary, "target_mode"),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                "dispatch_orders": orders,
                "acked_orders": acked,
                "missing_acks": missing,
                "rejected_orders": rejected,
                "duplicate_ack_orders": duplicates,
                "unmatched_acks": int(len(unmatched_acks)),
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
                "ack_rate": acked / orders if orders else 0.0,
                "failed_checks": failed,
                "recommendation": "broker_dispatch_acknowledged" if passed else "investigate_broker_dispatch_acks",
            }
        ]
    )


def _config(summary: pd.Series, thresholds: BrokerDispatchAckThresholds, checks: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": _to_bool(summary["passed"]),
        "target_mode": _text(summary, "target_mode"),
        "strategy": _text(summary, "strategy"),
        "market": _text(summary, "market"),
        "scenario_key": _text(summary, "scenario_key"),
        "adapter": _text(summary, "adapter"),
        "dispatch_orders": int(summary["dispatch_orders"]),
        "acked_orders": int(summary["acked_orders"]),
        "missing_acks": int(summary["missing_acks"]),
        "rejected_orders": int(summary["rejected_orders"]),
        "duplicate_ack_orders": int(summary["duplicate_ack_orders"]),
        "unmatched_acks": int(summary["unmatched_acks"]),
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


def _matching_acks(order: pd.Series, acks: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if acks.empty:
        return acks, ""
    dispatch_order_id = _text(order, "dispatch_order_id")
    if dispatch_order_id and "dispatch_order_id" in acks.columns:
        matches = acks.loc[acks["dispatch_order_id"].astype(str).str.strip() == dispatch_order_id]
        if not matches.empty:
            return matches, "dispatch_order_id"
    source_order_id = _text(order, "source_order_id")
    if source_order_id and "source_order_id" in acks.columns:
        matches = acks.loc[acks["source_order_id"].astype(str).str.strip() == source_order_id]
        if not matches.empty:
            return matches, "source_order_id"
    return acks.iloc[:0], ""


def _normalize_acks(acks: pd.DataFrame) -> pd.DataFrame:
    frame = acks.copy().reset_index(drop=True)
    if frame.empty:
        return frame
    status_column = _first_column(frame, ("ack_status", "status", "order_status", "broker_status"))
    if status_column:
        frame["ack_status"] = frame[status_column].map(_status_key)
    else:
        frame["ack_status"] = ""
    if "broker_order_id" not in frame.columns:
        frame["broker_order_id"] = ""
    if "ack_ts_ns" not in frame.columns:
        frame["ack_ts_ns"] = pd.NA
    return frame


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    for column in candidates:
        if column in frame.columns:
            return column
    return ""


def _latest_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return str(values.iloc[-1]) if not values.empty else ""


def _latest_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return float("nan")
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else float("nan")


def _unique_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).str.strip()
    return sorted(set(values.loc[values != ""]))


def _unique_pipe_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    values: set[str] = set()
    if frame.empty or column not in frame.columns:
        return []
    for raw in frame[column].dropna().astype(str):
        for value in raw.split("|"):
            cleaned = value.strip()
            if cleaned:
                values.add(cleaned)
    return sorted(values)


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch acknowledgement input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch acknowledgement input is empty: {name}")
    return frame


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(dispatch_summary: pd.Series, thresholds: BrokerDispatchAckThresholds) -> bool:
    return bool(
        thresholds.require_dispatch_roundtrip
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
    )


def _validate_thresholds(thresholds: BrokerDispatchAckThresholds) -> None:
    if thresholds.max_duplicate_ack_orders < 0:
        raise ValueError("max_duplicate_ack_orders must be non-negative")
    if thresholds.max_unmatched_acks < 0:
        raise ValueError("max_unmatched_acks must be non-negative")


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


def _status_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


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
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready", "accepted"}
    return bool(value)


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
