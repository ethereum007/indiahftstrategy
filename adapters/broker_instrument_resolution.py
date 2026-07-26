from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.instruments import parse_option_instrument_id
from reports.manifest import write_experiment_manifest


MASTER_COLUMN_ALIASES = {
    "research_id": (
        "research_instrument_id",
        "source_instrument_id",
        "internal_instrument_id",
    ),
    "underlying": (
        "underlying",
        "underlying_symbol",
        "root",
        "name",
    ),
    "expiry": (
        "expiry",
        "expiry_date",
        "expiration",
        "expiration_date",
    ),
    "strike": (
        "strike",
        "strike_price",
        "strikeprice",
    ),
    "option_type": (
        "option_type",
        "optiontype",
        "option_right",
        "right",
        "instrument_type",
    ),
    "exchange": (
        "exchange",
        "exchange_segment",
        "segment",
        "exch_seg",
    ),
    "broker_symbol": (
        "tradingsymbol",
        "trading_symbol",
        "broker_symbol",
        "contract_symbol",
        "symbol",
    ),
    "broker_token": (
        "instrument_token",
        "exchange_token",
        "security_id",
        "securityid",
        "token",
    ),
}


@dataclass(frozen=True)
class BrokerInstrumentResolutionConfig:
    adapter: str = "arrow_money"
    exchange: str = "NFO"
    require_broker_token: bool = True
    master_research_id_column: str | None = None
    master_underlying_column: str | None = None
    master_expiry_column: str | None = None
    master_strike_column: str | None = None
    master_option_type_column: str | None = None
    master_exchange_column: str | None = None
    master_broker_symbol_column: str | None = None
    master_broker_token_column: str | None = None
    output_filename: str = "resolved_order_candidates.csv"


@dataclass(frozen=True)
class BrokerInstrumentResolutionReport:
    orders: pd.DataFrame
    resolution: pd.DataFrame
    checks: pd.DataFrame
    groups: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def resolve_broker_instruments(
    orders: pd.DataFrame,
    instrument_master: pd.DataFrame,
    *,
    config: BrokerInstrumentResolutionConfig | None = None,
) -> BrokerInstrumentResolutionReport:
    config = config or BrokerInstrumentResolutionConfig()
    _validate_config(config)
    _require_order_columns(orders)
    columns = _resolve_master_columns(instrument_master, config)
    schema_checks = _schema_checks(columns, config)
    resolution = _resolve_orders(orders, instrument_master, columns, config)
    resolution = _reject_reused_symbols(resolution)
    groups = _group_coverage(orders, resolution)
    checks = pd.DataFrame(
        [
            *schema_checks,
            *_order_checks(resolution),
            *_group_checks(groups),
        ]
    )
    resolved_orders = _resolved_orders(orders, resolution)
    summary = _summary(
        resolved_orders,
        resolution,
        checks,
        groups,
        instrument_master,
        columns,
        config,
    )
    action_queue = _action_queue(checks)
    return BrokerInstrumentResolutionReport(
        orders=resolved_orders,
        resolution=resolution,
        checks=checks,
        groups=groups,
        summary=summary,
        action_queue=action_queue,
    )


def write_broker_instrument_resolution(
    orders_path: str | Path,
    instrument_master_path: str | Path,
    *,
    output_dir: str | Path,
    config: BrokerInstrumentResolutionConfig | None = None,
) -> BrokerInstrumentResolutionReport:
    config = config or BrokerInstrumentResolutionConfig()
    _validate_config(config)
    orders_file = Path(orders_path)
    master_file = Path(instrument_master_path)
    if not orders_file.is_file():
        raise FileNotFoundError(f"order candidates not found: {orders_file}")
    if not master_file.is_file():
        raise FileNotFoundError(f"broker instrument master not found: {master_file}")

    report = resolve_broker_instruments(
        pd.read_csv(orders_file),
        pd.read_csv(master_file, dtype=str, keep_default_na=False),
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.resolution.to_csv(out / "instrument_resolution.csv", index=False)
    report.checks.to_csv(out / "instrument_resolution_checks.csv", index=False)
    report.groups.to_csv(out / "instrument_resolution_groups.csv", index=False)
    report.summary.to_csv(out / "instrument_resolution_summary.csv", index=False)
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.checks)
    )
    action_queue.to_csv(out / "instrument_resolution_action_queue.csv", index=False)
    (out / "instrument_resolution_config.json").write_text(
        json.dumps(
            _config_payload(report.summary.iloc[0], action_queue, config),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "instrument_resolution_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_instrument_resolution",
        parameters={"config": asdict(config)},
        inputs={
            "orders": orders_file,
            "instrument_master": master_file,
        },
    )
    return BrokerInstrumentResolutionReport(
        report.orders,
        report.resolution,
        report.checks,
        report.groups,
        report.summary,
        out,
        action_queue,
    )


def _resolve_master_columns(
    instrument_master: pd.DataFrame,
    config: BrokerInstrumentResolutionConfig,
) -> dict[str, str]:
    requested = {
        "research_id": config.master_research_id_column,
        "underlying": config.master_underlying_column,
        "expiry": config.master_expiry_column,
        "strike": config.master_strike_column,
        "option_type": config.master_option_type_column,
        "exchange": config.master_exchange_column,
        "broker_symbol": config.master_broker_symbol_column,
        "broker_token": config.master_broker_token_column,
    }
    lookup = {_column_key(column): str(column) for column in instrument_master.columns}
    resolved: dict[str, str] = {}
    for field, explicit in requested.items():
        if explicit is not None:
            resolved[field] = str(explicit) if str(explicit) in instrument_master.columns else ""
            continue
        resolved[field] = next(
            (
                lookup[_column_key(alias)]
                for alias in MASTER_COLUMN_ALIASES[field]
                if _column_key(alias) in lookup
            ),
            "",
        )
    return resolved


def _schema_checks(
    columns: dict[str, str],
    config: BrokerInstrumentResolutionConfig,
) -> list[dict[str, Any]]:
    semantic = all(
        columns[field]
        for field in ("underlying", "expiry", "strike", "option_type")
    )
    identity_available = bool(columns["research_id"] or semantic)
    specs = [
        (
            "master_broker_symbol_column",
            columns["broker_symbol"],
            True,
            "instrument master has no broker trading-symbol column",
        ),
        (
            "master_exchange_column",
            columns["exchange"],
            bool(config.exchange),
            "instrument master has no exchange/segment column",
        ),
        (
            "master_identity_columns",
            "direct" if columns["research_id"] else "semantic" if semantic else "",
            True,
            "instrument master needs a research-ID column or underlying/expiry/strike/option-type columns",
        ),
        (
            "master_broker_token_column",
            columns["broker_token"],
            config.require_broker_token,
            "instrument master has no broker token/security-ID column",
        ),
    ]
    rows = []
    for check, value, required, reason in specs:
        passed = bool(value) or not required
        if check == "master_identity_columns":
            passed = identity_available
        rows.append(
            _check(
                check,
                value,
                "not_empty" if required else "optional",
                True if required else False,
                passed,
                reason,
                scope="schema",
            )
        )
    return rows


def _resolve_orders(
    orders: pd.DataFrame,
    master: pd.DataFrame,
    columns: dict[str, str],
    config: BrokerInstrumentResolutionConfig,
) -> pd.DataFrame:
    normalized = _normalized_master(master, columns)
    rows = []
    for position, (_, order) in enumerate(orders.iterrows()):
        research_id = _text(order.get("instrument_id"))
        identity = _order_identity(order, research_id)
        candidates = normalized.iloc[0:0]
        method = ""

        if columns["research_id"]:
            direct = normalized.loc[
                normalized["_research_id"] == _identity_key(research_id)
            ]
            if not direct.empty:
                candidates = direct
                method = "direct_research_id"

        if candidates.empty and identity["semantic_available"]:
            candidates = normalized.loc[
                (normalized["_underlying"] == identity["underlying"])
                & (normalized["_expiry"] == identity["expiry"])
                & np.isclose(
                    normalized["_strike"].astype(float),
                    float(identity["strike"]),
                    rtol=0.0,
                    atol=1e-9,
                    equal_nan=False,
                )
                & (normalized["_option_type"] == identity["option_type"])
            ]
            method = "semantic_option_identity"

        if config.exchange:
            candidates = candidates.loc[
                candidates["_exchange"] == _exchange_key(config.exchange)
            ]

        candidate_count = int(len(candidates))
        selected = candidates.iloc[0] if candidate_count == 1 else pd.Series(dtype=object)
        broker_symbol = _text(selected.get("_broker_symbol"))
        broker_token = _text(selected.get("_broker_token"))
        reason = _resolution_reason(
            candidate_count,
            broker_symbol,
            broker_token,
            identity_available=bool(
                columns["research_id"] or identity["semantic_available"]
            ),
            exchange_available=bool(columns["exchange"] or not config.exchange),
            require_token=config.require_broker_token,
        )
        rows.append(
            {
                "order_position": position,
                "client_order_id": _text(order.get("client_order_id")),
                "leg_group_id": _text(order.get("leg_group_id")) or "__all__",
                "leg_role": _text(order.get("leg_role")),
                "research_instrument_id": research_id,
                "underlying": identity["underlying"],
                "expiry": identity["expiry"],
                "strike": identity["strike"],
                "option_type": identity["option_type"],
                "exchange": _exchange_key(config.exchange),
                "match_method": method,
                "candidate_count": candidate_count,
                "master_row": (
                    int(selected.get("_master_row"))
                    if not selected.empty
                    else pd.NA
                ),
                "broker_symbol": broker_symbol,
                "broker_token": broker_token,
                "matched": not bool(reason),
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _normalized_master(
    master: pd.DataFrame,
    columns: dict[str, str],
) -> pd.DataFrame:
    out = master.copy().reset_index(drop=True)
    out["_master_row"] = out.index.astype(int)
    out["_research_id"] = _series_text(out, columns["research_id"]).map(
        _identity_key
    )
    out["_underlying"] = _series_text(out, columns["underlying"]).map(
        _identity_key
    )
    out["_expiry"] = _series_text(out, columns["expiry"]).map(
        _expiry_key
    )
    out["_strike"] = pd.to_numeric(
        _series_text(out, columns["strike"]),
        errors="coerce",
    )
    out["_option_type"] = _series_text(out, columns["option_type"]).map(
        _option_type_key
    )
    out["_exchange"] = _series_text(out, columns["exchange"]).map(
        _exchange_key
    )
    out["_broker_symbol"] = _series_text(out, columns["broker_symbol"])
    out["_broker_token"] = _series_text(out, columns["broker_token"])
    return out


def _order_identity(order: pd.Series, research_id: str) -> dict[str, Any]:
    parsed = parse_option_instrument_id(research_id)
    underlying = _identity_key(
        _text(order.get("underlying"))
        or (parsed.underlying if parsed is not None else "")
    )
    expiry = _expiry_key(
        _text(order.get("expiry"))
        or (parsed.expiry if parsed is not None else "")
    )
    strike = _number(
        order.get("strike"),
        parsed.strike if parsed is not None else np.nan,
    )
    option_type = _option_type_key(
        _text(order.get("option_type"))
        or (parsed.option_type if parsed is not None else "")
    )
    semantic_available = bool(
        underlying
        and expiry
        and not np.isnan(strike)
        and option_type
    )
    return {
        "underlying": underlying,
        "expiry": expiry,
        "strike": strike,
        "option_type": option_type,
        "semantic_available": semantic_available,
    }


def _resolution_reason(
    candidate_count: int,
    broker_symbol: str,
    broker_token: str,
    *,
    identity_available: bool,
    exchange_available: bool,
    require_token: bool,
) -> str:
    if not exchange_available:
        return "master_exchange_column_missing"
    if not identity_available:
        return "order_identity_unavailable"
    if candidate_count == 0:
        return "instrument_not_found"
    if candidate_count > 1:
        return "ambiguous_instrument_match"
    if not broker_symbol:
        return "broker_symbol_blank"
    if require_token and not broker_token:
        return "broker_token_blank"
    return ""


def _reject_reused_symbols(resolution: pd.DataFrame) -> pd.DataFrame:
    if resolution.empty:
        return resolution
    out = resolution.copy()
    eligible = out["matched"].astype(bool) & out["broker_symbol"].astype(str).str.strip().ne("")
    duplicated = out.loc[eligible].duplicated(
        subset=["leg_group_id", "broker_symbol"],
        keep=False,
    )
    duplicate_index = out.loc[eligible].index[duplicated]
    if len(duplicate_index):
        out.loc[duplicate_index, "matched"] = False
        out.loc[duplicate_index, "reason"] = "broker_symbol_reused_within_leg_group"
    return out


def _resolved_orders(
    orders: pd.DataFrame,
    resolution: pd.DataFrame,
) -> pd.DataFrame:
    out = orders.copy().reset_index(drop=True)
    out["research_instrument_id"] = out["instrument_id"].astype(str)
    out["broker_instrument_token"] = ""
    out["instrument_resolution_method"] = ""
    out["instrument_resolution_status"] = "unresolved"
    for _, row in resolution.iterrows():
        position = int(row["order_position"])
        out.at[position, "broker_instrument_token"] = _text(
            row.get("broker_token")
        )
        out.at[position, "instrument_resolution_method"] = _text(
            row.get("match_method")
        )
        if bool(row["matched"]):
            out.at[position, "instrument_id"] = _text(
                row.get("broker_symbol")
            )
            out.at[position, "instrument_resolution_status"] = "resolved"
    return out


def _group_coverage(
    orders: pd.DataFrame,
    resolution: pd.DataFrame,
) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(
            columns=[
                "leg_group_id",
                "expected_legs",
                "order_legs",
                "resolved_legs",
                "unique_broker_symbols",
                "complete",
                "reason",
            ]
        )
    rows = []
    group_ids = (
        orders.get("leg_group_id", pd.Series(["__all__"] * len(orders)))
        .fillna("")
        .astype(str)
        .replace("", "__all__")
    )
    for group_id in group_ids.drop_duplicates().tolist():
        mask = group_ids == group_id
        group_orders = orders.loc[mask]
        positions = list(np.flatnonzero(mask.to_numpy()))
        group_resolution = resolution.loc[
            resolution["order_position"].isin(positions)
        ]
        expected_values = pd.to_numeric(
            group_orders.get(
                "leg_count",
                pd.Series([len(group_orders)] * len(group_orders)),
            ),
            errors="coerce",
        ).dropna()
        unique_expected = sorted(set(int(value) for value in expected_values))
        expected = unique_expected[0] if len(unique_expected) == 1 else 0
        resolved = int(group_resolution["matched"].astype(bool).sum())
        unique_symbols = int(
            group_resolution.loc[
                group_resolution["matched"].astype(bool),
                "broker_symbol",
            ]
            .astype(str)
            .nunique()
        )
        order_legs = int(len(group_orders))
        complete = bool(
            expected > 0
            and order_legs == expected
            and resolved == expected
            and unique_symbols == expected
        )
        reason = ""
        if len(unique_expected) != 1:
            reason = "leg_count_inconsistent"
        elif order_legs != expected:
            reason = "leg_group_order_count_mismatch"
        elif resolved != expected:
            reason = "leg_group_not_fully_resolved"
        elif unique_symbols != expected:
            reason = "leg_group_broker_symbols_not_unique"
        rows.append(
            {
                "leg_group_id": group_id,
                "expected_legs": expected,
                "order_legs": order_legs,
                "resolved_legs": resolved,
                "unique_broker_symbols": unique_symbols,
                "complete": complete,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _order_checks(resolution: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _, row in resolution.iterrows():
        label = _text(row.get("client_order_id")) or str(
            int(row["order_position"])
        )
        rows.append(
            _check(
                f"order_instrument_resolved:{label}",
                int(row["candidate_count"]),
                "exact_unique_match",
                1,
                bool(row["matched"]),
                _text(row.get("reason")),
                scope="order",
                instrument_id=_text(row.get("research_instrument_id")),
                leg_group_id=_text(row.get("leg_group_id")),
            )
        )
    return rows


def _group_checks(groups: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        _check(
            f"leg_group_fully_resolved:{_text(row.get('leg_group_id'))}",
            int(row["resolved_legs"]),
            "==",
            int(row["expected_legs"]),
            bool(row["complete"]),
            _text(row.get("reason")),
            scope="leg_group",
            leg_group_id=_text(row.get("leg_group_id")),
        )
        for _, row in groups.iterrows()
    ]


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
    *,
    scope: str,
    instrument_id: str = "",
    leg_group_id: str = "",
) -> dict[str, Any]:
    return {
        "check": name,
        "scope": scope,
        "instrument_id": instrument_id,
        "leg_group_id": leg_group_id,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _summary(
    orders: pd.DataFrame,
    resolution: pd.DataFrame,
    checks: pd.DataFrame,
    groups: pd.DataFrame,
    master: pd.DataFrame,
    columns: dict[str, str],
    config: BrokerInstrumentResolutionConfig,
) -> pd.DataFrame:
    failed = (
        int((~checks["passed"].astype(bool)).sum())
        if not checks.empty
        else 1
    )
    total = int(len(resolution))
    matched = (
        int(resolution["matched"].astype(bool).sum())
        if total
        else 0
    )
    unresolved = total - matched
    ambiguous = (
        int(
            resolution["reason"]
            .astype(str)
            .eq("ambiguous_instrument_match")
            .sum()
        )
        if total
        else 0
    )
    complete_groups = (
        int(groups["complete"].astype(bool).sum())
        if not groups.empty
        else 0
    )
    ready = bool(total > 0 and failed == 0)
    first_failed = (
        checks.loc[~checks["passed"].astype(bool)].iloc[0]
        if failed and not checks.empty
        else pd.Series(dtype=object)
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "exchange": config.exchange,
                "orders": total,
                "resolved_orders": matched,
                "unresolved_orders": unresolved,
                "ambiguous_orders": ambiguous,
                "resolution_coverage": matched / total if total else 0.0,
                "leg_groups": int(len(groups)),
                "complete_leg_groups": complete_groups,
                "instrument_master_rows": int(len(master)),
                "require_broker_token": config.require_broker_token,
                "broker_symbol_column": columns["broker_symbol"],
                "broker_token_column": columns["broker_token"],
                "failed_checks": failed,
                "primary_blocker_check": _text(first_failed.get("check")),
                "primary_blocker_reason": _text(first_failed.get("reason")),
                "output_file": config.output_filename,
                "recommendation": (
                    "stage_resolved_multi_leg_orders"
                    if ready
                    else "fix_instrument_master_coverage"
                ),
            }
        ]
    )


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "priority",
        "queue_status",
        "check",
        "scope",
        "instrument_id",
        "leg_group_id",
        "actual",
        "operator",
        "expected",
        "next_gate",
        "reason",
        "recommendation",
    ]
    if checks.empty:
        return pd.DataFrame(columns=columns)
    failed = checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)
    rows = []
    for priority, row in enumerate(failed.to_dict(orient="records"), start=1):
        rows.append(
            {
                "priority": priority,
                "queue_status": "blocked",
                "check": _text(row.get("check")),
                "scope": _text(row.get("scope")),
                "instrument_id": _text(row.get("instrument_id")),
                "leg_group_id": _text(row.get("leg_group_id")),
                "actual": row.get("value", ""),
                "operator": _text(row.get("operator")),
                "expected": row.get("threshold", ""),
                "next_gate": "resolve-broker-instruments",
                "reason": _text(row.get("reason")),
                "recommendation": "refresh_or_correct_broker_instrument_master",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _config_payload(
    summary: pd.Series,
    action_queue: pd.DataFrame,
    config: BrokerInstrumentResolutionConfig,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": bool(summary.get("ready", False)),
        "adapter": _text(summary.get("adapter")),
        "exchange": _text(summary.get("exchange")),
        "resolution": {
            "orders": int(summary.get("orders", 0)),
            "resolved_orders": int(summary.get("resolved_orders", 0)),
            "unresolved_orders": int(summary.get("unresolved_orders", 0)),
            "ambiguous_orders": int(summary.get("ambiguous_orders", 0)),
            "coverage": float(summary.get("resolution_coverage", 0.0)),
            "leg_groups": int(summary.get("leg_groups", 0)),
            "complete_leg_groups": int(
                summary.get("complete_leg_groups", 0)
            ),
            "require_broker_token": bool(config.require_broker_token),
            "broker_symbol_column": _text(
                summary.get("broker_symbol_column")
            ),
            "broker_token_column": _text(
                summary.get("broker_token_column")
            ),
        },
        "failed_checks": int(summary.get("failed_checks", 0)),
        "primary_blocker": {
            "check": _text(summary.get("primary_blocker_check")),
            "reason": _text(summary.get("primary_blocker_reason")),
        },
        "next_actions": _jsonable_records(action_queue),
    }


def _runbook_markdown(
    summary: pd.Series,
    action_queue: pd.DataFrame,
) -> str:
    lines = [
        "# Broker Instrument Resolution Runbook",
        "",
        f"- Ready: {'yes' if bool(summary.get('ready', False)) else 'no'}",
        f"- Adapter: {_text(summary.get('adapter'))}",
        f"- Exchange: {_text(summary.get('exchange'))}",
        f"- Orders: {int(summary.get('orders', 0))}",
        f"- Resolved orders: {int(summary.get('resolved_orders', 0))}",
        f"- Resolution coverage: {float(summary.get('resolution_coverage', 0.0)):.6f}",
        f"- Complete leg groups: {int(summary.get('complete_leg_groups', 0))}/{int(summary.get('leg_groups', 0))}",
        f"- Failed checks: {int(summary.get('failed_checks', 0))}",
        "",
        "## Blocked Actions",
        "",
    ]
    if action_queue.empty:
        lines.append("_None_")
    else:
        lines.extend(
            [
                "| priority | check | instrument | leg group | reason |",
                "| --- | --- | --- | --- | --- |",
                *[
                    "| {priority} | {check} | {instrument} | {group} | {reason} |".format(
                        priority=int(row["priority"]),
                        check=_markdown_text(row["check"]),
                        instrument=_markdown_text(row["instrument_id"]),
                        group=_markdown_text(row["leg_group_id"]),
                        reason=_markdown_text(row["reason"]),
                    )
                    for _, row in action_queue.iterrows()
                ],
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _require_order_columns(orders: pd.DataFrame) -> None:
    required = ["instrument_id"]
    missing = [column for column in required if column not in orders.columns]
    if missing:
        raise ValueError(
            f"order candidates missing required columns: {missing}"
        )


def _validate_config(config: BrokerInstrumentResolutionConfig) -> None:
    if not str(config.adapter).strip():
        raise ValueError("adapter must not be blank")
    if not str(config.exchange).strip():
        raise ValueError("exchange must not be blank")
    if not str(config.output_filename).strip():
        raise ValueError("output_filename must not be blank")
    if Path(config.output_filename).name != config.output_filename:
        raise ValueError("output_filename must be a file name")


def _series_text(frame: pd.DataFrame, column: str) -> pd.Series:
    if not column or column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    return frame[column].map(_text)


def _column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def _identity_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def _exchange_key(value: object) -> str:
    key = _identity_key(value)
    if key.startswith("NFO") or key in {"NSEFO", "NSEFNO", "NSEOPT"}:
        return "NFO"
    return key


def _option_type_key(value: object) -> str:
    key = _identity_key(value)
    if key in {"C", "CE", "CALL"}:
        return "C"
    if key in {"P", "PE", "PUT"}:
        return "P"
    return ""


def _expiry_key(value: object) -> str:
    text = _text(value)
    if not text:
        return ""
    if re.fullmatch(r"[0-9]{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return pd.Timestamp(text).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _number(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return float(default) if np.isnan(number) else number


def _text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _jsonable_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for row in frame.to_dict(orient="records"):
        record = {}
        for key, value in row.items():
            try:
                if pd.isna(value):
                    record[str(key)] = None
                    continue
            except (TypeError, ValueError):
                pass
            record[str(key)] = value
        records.append(record)
    return records


def _markdown_text(value: object) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")
