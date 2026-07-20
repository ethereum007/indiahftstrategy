from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.leadlag_candidate_contract import (
    edge_audit,
    edge_audit_bound,
    edge_latency_budget_ns,
    replay_latency_ns,
)
from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from strategies.run_leadlag_replay import LEAD_LAG_STRATEGY, LeadLagReplayResult, run_leadlag_replay


@dataclass(frozen=True)
class LeadLagReplayWalkForwardThresholds:
    min_folds: int = 1
    min_proof_pass_rate: float = 1.0
    min_total_fills: int = 1
    min_total_net_pnl: float = 0.0
    max_worst_drawdown: float | None = None
    min_median_markout_mean: float | None = None


@dataclass(frozen=True)
class LeadLagReplayWalkForwardReport:
    folds: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    candidate_config: dict[str, Any]
    replays: list[LeadLagReplayResult]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def write_leadlag_replay_walkforward(
    leader_paths: list[str | Path],
    laggard_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    candidate_config: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str | None = None,
    lot_size: int = 75,
    leader_tick: float | None = None,
    laggard_tick: float | None = None,
    delta: float | None = None,
    trigger_ticks: float | None = None,
    qty: int | None = None,
    flat_after_ns: int | None = None,
    cooloff_ns: int | None = None,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    generic_buy_notional_rate: float | None = None,
    generic_sell_notional_rate: float | None = None,
    generic_per_unit_fee: float | None = None,
    generic_per_contract_fee: float | None = None,
    generic_per_order_fee: float | None = None,
    max_position_lots: int = 20,
    markout_horizons_ns: list[int] | None = None,
    proof_thresholds: ProofThresholds | None = None,
    thresholds: LeadLagReplayWalkForwardThresholds | None = None,
) -> LeadLagReplayWalkForwardReport:
    leaders = [Path(path) for path in leader_paths]
    laggards = [Path(path) for path in laggard_paths]
    fold_labels = _fold_labels(leaders, laggards, labels)
    thresholds = thresholds or LeadLagReplayWalkForwardThresholds(min_folds=len(leaders))
    _validate_thresholds(thresholds)
    proof_thresholds = proof_thresholds or ProofThresholds()
    candidate_path, candidate = _load_candidate(candidate_config)
    replay_defaults = candidate.get("replay_defaults", {}) if candidate else {}
    if not isinstance(replay_defaults, dict):
        raise ValueError("candidate config replay_defaults must be an object")
    generic_defaults = replay_defaults.get("generic_costs", {})
    if generic_defaults is None:
        generic_defaults = {}
    if not isinstance(generic_defaults, dict):
        raise ValueError("candidate config replay_defaults.generic_costs must be an object")

    replay_params = {
        "market": str(_coalesce(market, replay_defaults.get("market"), INDIA_NSE_INDEX_DERIVATIVES.name)),
        "leader_tick": float(_coalesce(leader_tick, replay_defaults.get("leader_tick"), 0.05)),
        "laggard_tick": float(_coalesce(laggard_tick, replay_defaults.get("laggard_tick"), 0.05)),
        "delta": float(_coalesce(delta, replay_defaults.get("delta"), 1.0)),
        "trigger_ticks": float(_coalesce(trigger_ticks, replay_defaults.get("trigger_ticks"), 3.0)),
        "qty": int(_coalesce(qty, replay_defaults.get("qty"), 75)),
        "flat_after_ns": int(_coalesce(flat_after_ns, replay_defaults.get("flat_after_ns"), 500_000_000)),
        "cooloff_ns": int(_coalesce(cooloff_ns, replay_defaults.get("cooloff_ns"), 0)),
        "feed_latency_us": float(feed_latency_us),
        "order_latency_us": float(order_latency_us),
        "markout_horizons_ns": _coalesce_list(
            markout_horizons_ns,
            replay_defaults.get("markout_horizons_ns"),
            [100_000_000, 1_000_000_000],
        ),
        "generic_costs": {
            "buy_notional_rate": float(_coalesce(generic_buy_notional_rate, generic_defaults.get("buy_notional_rate"), 0.0)),
            "sell_notional_rate": float(_coalesce(generic_sell_notional_rate, generic_defaults.get("sell_notional_rate"), 0.0)),
            "per_unit_fee": float(_coalesce(generic_per_unit_fee, generic_defaults.get("per_unit_fee"), 0.0)),
            "per_contract_fee": float(_coalesce(generic_per_contract_fee, generic_defaults.get("per_contract_fee"), 0.0)),
            "per_order_fee": float(_coalesce(generic_per_order_fee, generic_defaults.get("per_order_fee"), 0.0)),
        },
    }

    out = Path(output_dir)
    runs_root = out / "runs"
    out.mkdir(parents=True, exist_ok=True)

    run_dirs: list[Path] = []
    replays: list[LeadLagReplayResult] = []
    fold_rows: list[dict[str, Any]] = []
    for idx, (leader_path, laggard_path, label) in enumerate(zip(leaders, laggards, fold_labels), start=1):
        run_dir = runs_root / f"{idx:02d}_{_safe_label(label)}"
        replay = run_leadlag_replay(
            leader_path=leader_path,
            laggard_path=laggard_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            market=replay_params["market"],
            lot_size=lot_size,
            leader_tick=replay_params["leader_tick"],
            laggard_tick=replay_params["laggard_tick"],
            delta=replay_params["delta"],
            trigger_ticks=replay_params["trigger_ticks"],
            qty=replay_params["qty"],
            flat_after_ns=replay_params["flat_after_ns"],
            cooloff_ns=replay_params["cooloff_ns"],
            feed_latency_us=replay_params["feed_latency_us"],
            order_latency_us=replay_params["order_latency_us"],
            generic_buy_notional_rate=replay_params["generic_costs"]["buy_notional_rate"],
            generic_sell_notional_rate=replay_params["generic_costs"]["sell_notional_rate"],
            generic_per_unit_fee=replay_params["generic_costs"]["per_unit_fee"],
            generic_per_contract_fee=replay_params["generic_costs"]["per_contract_fee"],
            generic_per_order_fee=replay_params["generic_costs"]["per_order_fee"],
            max_position_lots=max_position_lots,
            markout_horizons_ns=replay_params["markout_horizons_ns"],
        )
        run_dirs.append(run_dir)
        replays.append(replay)
        fold_rows.append(_fold_row(idx, label, leader_path, laggard_path, run_dir, replay))

    proof = write_proof_report(
        run_dirs,
        output_dir=out / "proof",
        thresholds=proof_thresholds,
        run_names=fold_labels,
    )
    folds = _merge_proof_metrics(pd.DataFrame(fold_rows), proof)
    checks = _checks(
        folds,
        thresholds,
        candidate=candidate,
        replay_params=replay_params,
    )
    summary = _summary(
        folds,
        checks,
        candidate=candidate,
        replay_params=replay_params,
    )
    summary["strategy"] = LEAD_LAG_STRATEGY
    summary["market"] = replay_params["market"]
    config = _candidate_config(
        candidate,
        candidate_path,
        checks,
        summary.iloc[0],
        replay_params=replay_params,
    )

    folds.to_csv(out / "leadlag_replay_walkforward_folds.csv", index=False)
    checks.to_csv(out / "leadlag_replay_walkforward_checks.csv", index=False)
    summary.to_csv(out / "leadlag_replay_walkforward_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="leadlag_replay_walkforward",
        parameters={
            "labels": fold_labels,
            "candidate_config": str(candidate_path) if candidate_path is not None else None,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "strategy": LEAD_LAG_STRATEGY,
            "market": replay_params["market"],
            "lot_size": lot_size,
            "leader_tick": replay_params["leader_tick"],
            "laggard_tick": replay_params["laggard_tick"],
            "delta": replay_params["delta"],
            "trigger_ticks": replay_params["trigger_ticks"],
            "qty": replay_params["qty"],
            "flat_after_ns": replay_params["flat_after_ns"],
            "cooloff_ns": replay_params["cooloff_ns"],
            "feed_latency_us": replay_params["feed_latency_us"],
            "order_latency_us": replay_params["order_latency_us"],
            "generic_costs": replay_params["generic_costs"],
            "max_position_lots": max_position_lots,
            "markout_horizons_ns": replay_params["markout_horizons_ns"],
            "proof_thresholds": asdict(proof_thresholds),
            "thresholds": asdict(thresholds),
        },
        inputs={"leaders": leaders, "laggards": laggards, "candidate_config": candidate_path, "run_dirs": run_dirs},
    )
    return LeadLagReplayWalkForwardReport(
        folds=folds,
        checks=checks,
        summary=summary,
        proof=proof,
        candidate_config=config,
        replays=replays,
        output_dir=out,
    )


def _fold_labels(leaders: list[Path], laggards: list[Path], labels: list[str] | None) -> list[str]:
    if not leaders:
        raise ValueError("at least one leader file is required")
    if len(leaders) != len(laggards):
        raise ValueError("leader_paths and laggard_paths must have the same length")
    if labels is not None and len(labels) != len(leaders):
        raise ValueError("labels must match leader_paths length")
    return [str(label) for label in labels] if labels is not None else [f"{leader.stem}__{laggard.stem}" for leader, laggard in zip(leaders, laggards)]


def _load_candidate(path: str | Path | None) -> tuple[Path | None, dict[str, Any]]:
    if path is None:
        return None, {}
    candidate_path = Path(path)
    if candidate_path.is_dir():
        candidate_path = candidate_path / "candidate_config.json"
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if _normalize_strategy(candidate.get("strategy")) != LEAD_LAG_STRATEGY:
        raise ValueError(f"candidate config is not for lead-lag strategy: {candidate_path}")
    if not _to_bool(candidate.get("ready", False)):
        failed = candidate.get("failed_checks", []) or []
        raise ValueError(f"lead-lag candidate config is not ready: {failed}")
    return candidate_path, candidate


def _fold_row(
    index: int,
    label: str,
    leader_path: Path,
    laggard_path: Path,
    run_dir: Path,
    replay: LeadLagReplayResult,
) -> dict[str, Any]:
    row = replay.summary.iloc[0] if not replay.summary.empty else pd.Series(dtype=object)
    return {
        "fold_index": int(index),
        "fold": label,
        "leader_path": str(leader_path),
        "laggard_path": str(laggard_path),
        "run_dir": str(run_dir),
        "net_pnl": _float(row, "net_pnl"),
        "fills": _int(row, "fills"),
        "orders_sent": _int(row, "orders_sent"),
        "total_costs": _float(row, "total_costs"),
        "turnover": _float(row, "turnover"),
        "order_to_trade_ratio": _float(row, "order_to_trade_ratio"),
        "otr_breached": _to_bool(row.get("otr_breached", False)),
        "maker_share": _float(row, "maker_share"),
        "portfolio_delta": _float(row, "portfolio_delta"),
        "portfolio_vega": _float(row, "portfolio_vega"),
    }


def _merge_proof_metrics(folds: pd.DataFrame, proof: ProofReport) -> pd.DataFrame:
    proof_passed = (
        proof.checks.groupby("run", dropna=False)["passed"].all().rename("proof_passed").reset_index()
    )
    proof_columns = ["run"] + [column for column in proof.metrics.columns if column not in folds.columns and column != "run"]
    proof_metrics = proof.metrics[proof_columns] if not proof.metrics.empty else pd.DataFrame(columns=proof_columns)
    merged = folds.merge(proof_metrics, left_on="fold", right_on="run", how="left")
    if "run" in merged.columns:
        merged = merged.drop(columns=["run"])
    merged = merged.merge(proof_passed, left_on="fold", right_on="run", how="left")
    if "run" in merged.columns:
        merged = merged.drop(columns=["run"])
    merged["proof_passed"] = merged["proof_passed"].fillna(False).map(_to_bool)
    merged["robust_score"] = (
        pd.to_numeric(merged["net_pnl"], errors="coerce").fillna(0.0)
        - pd.to_numeric(merged.get("max_drawdown", 0.0), errors="coerce").fillna(0.0)
        - pd.to_numeric(merged["total_costs"], errors="coerce").fillna(0.0)
    )
    return merged


def _checks(
    folds: pd.DataFrame,
    thresholds: LeadLagReplayWalkForwardThresholds,
    *,
    candidate: dict[str, Any],
    replay_params: dict[str, Any],
) -> pd.DataFrame:
    proof_pass_rate = float(folds["proof_passed"].map(_to_bool).mean()) if not folds.empty else 0.0
    total_fills = int(pd.to_numeric(folds.get("fills", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    total_net_pnl = float(pd.to_numeric(folds.get("net_pnl", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    rows = [
        _threshold_check("fold_count", len(folds), ">=", thresholds.min_folds),
        _threshold_check("proof_pass_rate", proof_pass_rate, ">=", thresholds.min_proof_pass_rate),
        _threshold_check("total_fills", total_fills, ">=", thresholds.min_total_fills),
        _threshold_check("total_net_pnl", total_net_pnl, ">=", thresholds.min_total_net_pnl),
    ]
    if thresholds.max_worst_drawdown is not None:
        rows.append(
            _threshold_check("worst_drawdown", _numeric_reduce(folds, "max_drawdown", "max"), "<=", thresholds.max_worst_drawdown)
        )
    if thresholds.min_median_markout_mean is not None:
        rows.append(
            _threshold_check(
                "median_markout_mean",
                _numeric_reduce(folds, "markout_mean", "median"),
                ">=",
                thresholds.min_median_markout_mean,
            )
        )
    candidate_edge_audit = edge_audit(candidate)
    if candidate_edge_audit:
        edge_current = edge_audit_bound(candidate)
        rows.append(
            {
                "check": "edge_audit_current",
                "value": float(edge_current),
                "operator": "is",
                "threshold": 1.0,
                "passed": bool(edge_current),
                "reason": (
                    ""
                    if edge_current
                    else "candidate edge audit is not passed, current, and measurement-bound"
                ),
            }
        )
        rows.append(
            _threshold_check(
                "total_replay_latency_ns",
                replay_latency_ns(replay_params),
                "<=",
                edge_latency_budget_ns(candidate),
            )
        )
    return pd.DataFrame(rows)


def _summary(
    folds: pd.DataFrame,
    checks: pd.DataFrame,
    *,
    candidate: dict[str, Any],
    replay_params: dict[str, Any],
) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    net_pnl = pd.to_numeric(folds.get("net_pnl", pd.Series(dtype=float)), errors="coerce")
    fills = pd.to_numeric(folds.get("fills", pd.Series(dtype=float)), errors="coerce")
    proof_pass_rate = float(folds["proof_passed"].map(_to_bool).mean()) if not folds.empty else 0.0
    latency_budget_ns = edge_latency_budget_ns(candidate)
    total_replay_latency_ns = replay_latency_ns(replay_params)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "paper_or_shadow_candidate" if passed else "keep_researching",
                "fold_count": int(len(folds)),
                "proof_passed_folds": int(folds["proof_passed"].map(_to_bool).sum()) if not folds.empty else 0,
                "proof_pass_rate": proof_pass_rate,
                "total_net_pnl": float(net_pnl.fillna(0.0).sum()),
                "median_net_pnl": float(net_pnl.median(skipna=True)),
                "min_net_pnl": float(net_pnl.min(skipna=True)),
                "total_fills": int(fills.fillna(0).sum()),
                "median_fills": float(fills.median(skipna=True)),
                "worst_drawdown": _numeric_reduce(folds, "max_drawdown", "max"),
                "median_markout_mean": _numeric_reduce(folds, "markout_mean", "median"),
                "median_robust_score": _numeric_reduce(folds, "robust_score", "median"),
                "edge_audit_bound": edge_audit_bound(candidate),
                "edge_latency_budget_ns": latency_budget_ns,
                "total_replay_latency_ns": total_replay_latency_ns,
                "edge_latency_headroom_ns": (
                    latency_budget_ns - total_replay_latency_ns
                    if not np.isnan(latency_budget_ns)
                    else np.nan
                ),
            }
        ]
    )


def _candidate_config(
    source: dict[str, Any],
    source_path: Path | None,
    checks: pd.DataFrame,
    summary: pd.Series,
    *,
    replay_params: dict[str, Any],
) -> dict[str, Any]:
    config = copy.deepcopy(source) if source else {"schema_version": 1, "strategy": LEAD_LAG_STRATEGY}
    config["ready"] = bool(summary.get("passed", False))
    config["source_run_type"] = "leadlag_replay_walkforward"
    if source_path is not None:
        config["source_candidate_config"] = str(source_path)
    failed_checks = list(config.get("failed_checks", []) or [])
    failed_checks.extend(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist())
    config["failed_checks"] = list(dict.fromkeys(failed_checks))
    config["replay_defaults"] = {
        **(config.get("replay_defaults", {}) if isinstance(config.get("replay_defaults", {}), dict) else {}),
        "market": _jsonable(replay_params["market"]),
        "leader_tick": _jsonable(replay_params["leader_tick"]),
        "laggard_tick": _jsonable(replay_params["laggard_tick"]),
        "delta": _jsonable(replay_params["delta"]),
        "trigger_ticks": _jsonable(replay_params["trigger_ticks"]),
        "qty": _jsonable(replay_params["qty"]),
        "flat_after_ns": _jsonable(replay_params["flat_after_ns"]),
        "cooloff_ns": _jsonable(replay_params["cooloff_ns"]),
        "feed_latency_us": _jsonable(replay_params["feed_latency_us"]),
        "order_latency_us": _jsonable(replay_params["order_latency_us"]),
        "markout_horizons_ns": _jsonable(replay_params["markout_horizons_ns"]),
        "generic_costs": _jsonable(replay_params["generic_costs"]),
    }
    config["replay_walkforward"] = {
        "fold_count": _jsonable(summary.get("fold_count")),
        "proof_passed_folds": _jsonable(summary.get("proof_passed_folds")),
        "proof_pass_rate": _jsonable(summary.get("proof_pass_rate")),
        "total_net_pnl": _jsonable(summary.get("total_net_pnl")),
        "total_fills": _jsonable(summary.get("total_fills")),
        "worst_drawdown": _jsonable(summary.get("worst_drawdown")),
        "median_markout_mean": _jsonable(summary.get("median_markout_mean")),
        "edge_audit_bound": _jsonable(summary.get("edge_audit_bound")),
        "edge_latency_budget_ns": _jsonable(
            summary.get("edge_latency_budget_ns")
        ),
        "total_replay_latency_ns": _jsonable(
            summary.get("total_replay_latency_ns")
        ),
        "edge_latency_headroom_ns": _jsonable(
            summary.get("edge_latency_headroom_ns")
        ),
    }
    return config


def _threshold_check(name: str, value: Any, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_thresholds(thresholds: LeadLagReplayWalkForwardThresholds) -> None:
    if thresholds.min_folds <= 0:
        raise ValueError("min_folds must be positive")
    if not 0 <= thresholds.min_proof_pass_rate <= 1:
        raise ValueError("min_proof_pass_rate must be between 0 and 1")
    if thresholds.min_total_fills < 0:
        raise ValueError("min_total_fills must be non-negative")


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    raise ValueError("at least one value is required")


def _coalesce_list(*values: Any) -> list[int]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list) and value:
            return [int(item) for item in value]
        if isinstance(value, tuple) and value:
            return [int(item) for item in value]
        if not isinstance(value, (list, tuple)):
            return [int(value)]
    raise ValueError("at least one list value is required")


def _safe_label(label: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", label.strip())
    return text.strip("._-") or "fold"


def _numeric_reduce(frame: pd.DataFrame, column: str, reducer: str) -> float:
    if frame.empty or column not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce")
    if reducer == "max":
        return float(values.max(skipna=True))
    if reducer == "median":
        return float(values.median(skipna=True))
    raise ValueError(f"unsupported reducer {reducer!r}")


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _int(row: pd.Series, column: str) -> int:
    value = _float(row, column)
    return int(value) if not pd.isna(value) else 0


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _normalize_strategy(value: object) -> str:
    normalized = _identity_key(value)
    aliases = {
        "leadlag": LEAD_LAG_STRATEGY,
        "lead_lag": LEAD_LAG_STRATEGY,
        "leadlag_taker": LEAD_LAG_STRATEGY,
    }
    return aliases.get(normalized, normalized)


def _identity_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
