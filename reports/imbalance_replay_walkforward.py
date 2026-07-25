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
from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from strategies.run_imbalance_replay import ImbalanceReplayResult, run_imbalance_replay


@dataclass(frozen=True)
class ImbalanceReplayWalkForwardThresholds:
    min_folds: int = 1
    min_proof_pass_rate: float = 1.0
    min_total_fills: int = 1
    min_total_net_pnl: float = 0.0
    max_worst_drawdown: float | None = None
    min_median_markout_mean: float | None = None


@dataclass(frozen=True)
class ImbalanceReplayWalkForwardReport:
    folds: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    candidate_config: dict[str, Any]
    replays: list[ImbalanceReplayResult]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def write_imbalance_replay_walkforward(
    tick_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    candidate_config: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str | None = None,
    instrument_id: str = "BOOK",
    instrument_kind: str = "OPT",
    lot_size: int = 75,
    tick_size: float | None = None,
    qty: int = 75,
    entry_imbalance: float | None = None,
    exit_imbalance: float = 0.15,
    min_microprice_edge_ticks: float | None = None,
    max_spread_ticks: float = 2.0,
    min_depth: int = 1,
    hold_ns: int | None = None,
    cooloff_ns: int = 0,
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
    thresholds: ImbalanceReplayWalkForwardThresholds | None = None,
) -> ImbalanceReplayWalkForwardReport:
    paths = [Path(path) for path in tick_paths]
    fold_labels = _fold_labels(paths, labels)
    thresholds = thresholds or ImbalanceReplayWalkForwardThresholds(min_folds=len(paths))
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
        "instrument_id": str(_coalesce(replay_defaults.get("instrument_id"), instrument_id)),
        "instrument_kind": str(_coalesce(replay_defaults.get("instrument_kind"), instrument_kind)),
        "lot_size": int(_coalesce(replay_defaults.get("lot_size"), lot_size)),
        "tick_size": float(tick_size if tick_size is not None else _coalesce(replay_defaults.get("tick_size"), 0.05)),
        "qty": int(_coalesce(replay_defaults.get("qty"), qty)),
        "entry_imbalance": float(_coalesce(entry_imbalance, replay_defaults.get("entry_imbalance"), 0.6)),
        "exit_imbalance": float(_coalesce(replay_defaults.get("exit_imbalance"), exit_imbalance)),
        "min_microprice_edge_ticks": float(
            _coalesce(min_microprice_edge_ticks, replay_defaults.get("min_microprice_edge_ticks"), 0.25)
        ),
        "max_spread_ticks": float(_coalesce(replay_defaults.get("max_spread_ticks"), max_spread_ticks)),
        "min_depth": int(_coalesce(replay_defaults.get("min_depth"), min_depth)),
        "hold_ns": int(_coalesce(hold_ns, replay_defaults.get("hold_ns"), 500_000_000)),
        "cooloff_ns": int(_coalesce(replay_defaults.get("cooloff_ns"), cooloff_ns)),
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
    replays: list[ImbalanceReplayResult] = []
    fold_rows: list[dict[str, Any]] = []
    for idx, (ticks_path, label) in enumerate(zip(paths, fold_labels), start=1):
        run_dir = runs_root / f"{idx:02d}_{_safe_label(label)}"
        replay = run_imbalance_replay(
            ticks_path=ticks_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            market=replay_params["market"],
            instrument_id=replay_params["instrument_id"],
            instrument_kind=replay_params["instrument_kind"],
            lot_size=replay_params["lot_size"],
            tick_size=replay_params["tick_size"],
            qty=replay_params["qty"],
            entry_imbalance=replay_params["entry_imbalance"],
            exit_imbalance=replay_params["exit_imbalance"],
            min_microprice_edge_ticks=replay_params["min_microprice_edge_ticks"],
            max_spread_ticks=replay_params["max_spread_ticks"],
            min_depth=replay_params["min_depth"],
            hold_ns=replay_params["hold_ns"],
            cooloff_ns=replay_params["cooloff_ns"],
            feed_latency_us=feed_latency_us,
            order_latency_us=order_latency_us,
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
        fold_rows.append(_fold_row(idx, label, ticks_path, run_dir, replay))

    proof = write_proof_report(
        run_dirs,
        output_dir=out / "proof",
        thresholds=proof_thresholds,
        run_names=fold_labels,
    )
    folds = _merge_proof_metrics(pd.DataFrame(fold_rows), proof)
    checks = _checks(folds, thresholds)
    summary = _summary(folds, checks)
    summary["strategy"] = "imbalance"
    summary["market"] = replay_params["market"]
    config = _candidate_config(
        candidate,
        candidate_path,
        checks,
        summary.iloc[0],
        replay_params=replay_params,
    )

    folds.to_csv(out / "imbalance_replay_walkforward_folds.csv", index=False)
    checks.to_csv(out / "imbalance_replay_walkforward_checks.csv", index=False)
    summary.to_csv(out / "imbalance_replay_walkforward_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="imbalance_replay_walkforward",
        parameters={
            "labels": fold_labels,
            "candidate_config": str(candidate_path) if candidate_path is not None else None,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "strategy": "imbalance",
            "market": replay_params["market"],
            "instrument_id": replay_params["instrument_id"],
            "instrument_kind": replay_params["instrument_kind"],
            "lot_size": replay_params["lot_size"],
            "tick_size": replay_params["tick_size"],
            "qty": replay_params["qty"],
            "entry_imbalance": replay_params["entry_imbalance"],
            "exit_imbalance": replay_params["exit_imbalance"],
            "min_microprice_edge_ticks": replay_params["min_microprice_edge_ticks"],
            "max_spread_ticks": replay_params["max_spread_ticks"],
            "min_depth": replay_params["min_depth"],
            "hold_ns": replay_params["hold_ns"],
            "cooloff_ns": replay_params["cooloff_ns"],
            "feed_latency_us": feed_latency_us,
            "order_latency_us": order_latency_us,
            "generic_costs": replay_params["generic_costs"],
            "max_position_lots": max_position_lots,
            "markout_horizons_ns": replay_params["markout_horizons_ns"],
            "proof_thresholds": asdict(proof_thresholds),
            "thresholds": asdict(thresholds),
        },
        inputs={"ticks": paths, "candidate_config": candidate_path, "run_dirs": run_dirs},
    )
    return ImbalanceReplayWalkForwardReport(
        folds=folds,
        checks=checks,
        summary=summary,
        proof=proof,
        candidate_config=config,
        replays=replays,
        output_dir=out,
    )


def _fold_labels(paths: list[Path], labels: list[str] | None) -> list[str]:
    if not paths:
        raise ValueError("at least one tick file is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match tick_paths length")
    return [str(label) for label in labels] if labels is not None else [path.stem for path in paths]


def _load_candidate(path: str | Path | None) -> tuple[Path | None, dict[str, Any]]:
    if path is None:
        return None, {}
    candidate_path = Path(path)
    if candidate_path.is_dir():
        candidate_path = candidate_path / "candidate_config.json"
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if str(candidate.get("strategy", "")).strip().lower() != "imbalance":
        raise ValueError(f"candidate config is not for imbalance strategy: {candidate_path}")
    if not _to_bool(candidate.get("ready", False)):
        failed = candidate.get("failed_checks", []) or []
        raise ValueError(f"imbalance candidate config is not ready: {failed}")
    return candidate_path, candidate


def _fold_row(
    index: int,
    label: str,
    ticks_path: Path,
    run_dir: Path,
    replay: ImbalanceReplayResult,
) -> dict[str, Any]:
    row = replay.summary.iloc[0] if not replay.summary.empty else pd.Series(dtype=object)
    return {
        "fold_index": int(index),
        "fold": label,
        "ticks_path": str(ticks_path),
        "run_dir": str(run_dir),
        "signal_count": int(len(replay.signals)),
        "net_pnl": _float(row, "net_pnl"),
        "fills": _int(row, "fills"),
        "orders_sent": _int(row, "orders_sent"),
        "total_costs": _float(row, "total_costs"),
        "turnover": _float(row, "turnover"),
        "order_to_trade_ratio": _float(row, "order_to_trade_ratio"),
        "otr_breached": _to_bool(row.get("otr_breached", False)),
        "maker_share": _float(row, "maker_share"),
        "pending_order_risk_reservation_enabled": _to_bool(
            row.get("pending_order_risk_reservation_enabled", False)
        ),
        "aggressive_self_cross_prevention_enabled": _to_bool(
            row.get("aggressive_self_cross_prevention_enabled", False)
        ),
        "venue_order_validation_enabled": _to_bool(
            row.get("venue_order_validation_enabled", False)
        ),
        "shared_event_liquidity_enabled": _to_bool(
            row.get("shared_event_liquidity_enabled", False)
        ),
        "persistent_displayed_liquidity_enabled": _to_bool(
            row.get("persistent_displayed_liquidity_enabled", False)
        ),
        "lot_conserving_fills_enabled": _to_bool(
            row.get("lot_conserving_fills_enabled", False)
        ),
        "causal_event_ordering_enabled": _to_bool(
            row.get("causal_event_ordering_enabled", False)
        ),
        "cancel_lifecycle_tracking_enabled": _to_bool(
            row.get("cancel_lifecycle_tracking_enabled", False)
        ),
        "cancel_requests": _int(row, "cancel_requests"),
        "cancel_effective_events": _int(
            row,
            "cancel_effective_events",
        ),
        "cancel_effective_after_partial_fill_events": _int(
            row,
            "cancel_effective_after_partial_fill_events",
        ),
        "cancel_filled_before_effective_events": _int(
            row,
            "cancel_filled_before_effective_events",
        ),
        "cancel_closed_before_effective_events": _int(
            row,
            "cancel_closed_before_effective_events",
        ),
        "cancel_pending_at_replay_end_events": _int(
            row,
            "cancel_pending_at_replay_end_events",
        ),
        "cancel_inflight_filled_qty": _int(
            row,
            "cancel_inflight_filled_qty",
        ),
        "arrival_queue_initialization_enabled": _to_bool(
            row.get("arrival_queue_initialization_enabled", False)
        ),
        "limit_orders_sent": _int(row, "limit_orders_sent"),
        "queue_initialization_events": _int(
            row,
            "queue_initialization_events",
        ),
        "deferred_queue_initialization_events": _int(
            row,
            "deferred_queue_initialization_events",
        ),
        "uninitialized_limit_orders": _int(
            row,
            "uninitialized_limit_orders",
        ),
        "max_queue_initialization_lag_ns": _int(
            row,
            "max_queue_initialization_lag_ns",
        ),
        "residual_resting_transition_events": _int(
            row,
            "residual_resting_transition_events",
        ),
        "residual_resting_transition_qty": _int(
            row,
            "residual_resting_transition_qty",
        ),
        "deferred_residual_queue_events": _int(
            row,
            "deferred_residual_queue_events",
        ),
        "unresolved_residual_queue_events": _int(
            row,
            "unresolved_residual_queue_events",
        ),
        "max_residual_queue_initialization_lag_ns": _int(
            row,
            "max_residual_queue_initialization_lag_ns",
        ),
        "passive_price_through_depth_constrained_enabled": _to_bool(
            row.get(
                "passive_price_through_depth_constrained_enabled",
                False,
            )
        ),
        "passive_price_through_events": _int(
            row,
            "passive_price_through_events",
        ),
        "passive_price_through_requested_qty": _int(
            row,
            "passive_price_through_requested_qty",
        ),
        "passive_price_through_filled_qty": _int(
            row,
            "passive_price_through_filled_qty",
        ),
        "passive_price_through_shortfall_qty": _int(
            row,
            "passive_price_through_shortfall_qty",
        ),
        "passive_price_through_incomplete_events": _int(
            row,
            "passive_price_through_incomplete_events",
        ),
        "terminal_liquidation_depth_constrained_enabled": _to_bool(
            row.get(
                "terminal_liquidation_depth_constrained_enabled",
                False,
            )
        ),
        "terminal_liquidation_events": _int(
            row,
            "terminal_liquidation_events",
        ),
        "terminal_liquidation_requested_qty": _int(
            row,
            "terminal_liquidation_requested_qty",
        ),
        "terminal_liquidation_filled_qty": _int(
            row,
            "terminal_liquidation_filled_qty",
        ),
        "terminal_liquidation_shortfall_qty": _int(
            row,
            "terminal_liquidation_shortfall_qty",
        ),
        "terminal_liquidation_incomplete_events": _int(
            row,
            "terminal_liquidation_incomplete_events",
        ),
        "terminal_residual_position_qty": _int(
            row,
            "terminal_residual_position_qty",
        ),
        "terminal_residual_instruments": _int(
            row,
            "terminal_residual_instruments",
        ),
        "terminal_liquidation_complete": _to_bool(
            row.get("terminal_liquidation_complete", False)
        ),
        "liquidity_shortfall_events": _int(
            row,
            "liquidity_shortfall_events",
        ),
        "liquidity_shortfall_qty": _int(row, "liquidity_shortfall_qty"),
        "carried_depletion_shortfall_events": _int(
            row,
            "carried_depletion_shortfall_events",
        ),
        "carried_depletion_shortfall_qty": _int(
            row,
            "carried_depletion_shortfall_qty",
        ),
        "pretrade_rejections": _int(row, "pretrade_rejections"),
        "venue_rule_rejections": _int(row, "venue_rule_rejections"),
        "position_risk_rejections": _int(row, "position_risk_rejections"),
        "self_cross_rejections": _int(row, "self_cross_rejections"),
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


def _checks(folds: pd.DataFrame, thresholds: ImbalanceReplayWalkForwardThresholds) -> pd.DataFrame:
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
    return pd.DataFrame(rows)


def _summary(folds: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    net_pnl = pd.to_numeric(folds.get("net_pnl", pd.Series(dtype=float)), errors="coerce")
    fills = pd.to_numeric(folds.get("fills", pd.Series(dtype=float)), errors="coerce")
    pending_risk_enabled = folds.get(
        "pending_order_risk_reservation_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    self_cross_prevention_enabled = folds.get(
        "aggressive_self_cross_prevention_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    venue_order_validation_enabled = folds.get(
        "venue_order_validation_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    shared_liquidity_enabled = folds.get(
        "shared_event_liquidity_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    persistent_liquidity_enabled = folds.get(
        "persistent_displayed_liquidity_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    lot_conserving_fills_enabled = folds.get(
        "lot_conserving_fills_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    causal_event_ordering_enabled = folds.get(
        "causal_event_ordering_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    cancel_lifecycle_tracking_enabled = folds.get(
        "cancel_lifecycle_tracking_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    arrival_queue_enabled = folds.get(
        "arrival_queue_initialization_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    price_through_depth_constrained = folds.get(
        "passive_price_through_depth_constrained_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    terminal_depth_constrained = folds.get(
        "terminal_liquidation_depth_constrained_enabled",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    terminal_complete = folds.get(
        "terminal_liquidation_complete",
        pd.Series(False, index=folds.index),
    ).map(_to_bool)
    proof_pass_rate = float(folds["proof_passed"].map(_to_bool).mean()) if not folds.empty else 0.0
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
                "pending_order_risk_reservation_enabled_folds": int(
                    pending_risk_enabled.sum()
                ),
                "aggressive_self_cross_prevention_enabled_folds": int(
                    self_cross_prevention_enabled.sum()
                ),
                "venue_order_validation_enabled_folds": int(
                    venue_order_validation_enabled.sum()
                ),
                "shared_event_liquidity_enabled_folds": int(
                    shared_liquidity_enabled.sum()
                ),
                "persistent_displayed_liquidity_enabled_folds": int(
                    persistent_liquidity_enabled.sum()
                ),
                "lot_conserving_fills_enabled_folds": int(
                    lot_conserving_fills_enabled.sum()
                ),
                "causal_event_ordering_enabled_folds": int(
                    causal_event_ordering_enabled.sum()
                ),
                "cancel_lifecycle_tracking_enabled_folds": int(
                    cancel_lifecycle_tracking_enabled.sum()
                ),
                "total_cancel_requests": _numeric_reduce(
                    folds,
                    "cancel_requests",
                    "sum",
                ),
                "total_cancel_effective_events": _numeric_reduce(
                    folds,
                    "cancel_effective_events",
                    "sum",
                ),
                "total_cancel_effective_after_partial_fill_events": (
                    _numeric_reduce(
                        folds,
                        "cancel_effective_after_partial_fill_events",
                        "sum",
                    )
                ),
                "total_cancel_filled_before_effective_events": (
                    _numeric_reduce(
                        folds,
                        "cancel_filled_before_effective_events",
                        "sum",
                    )
                ),
                "total_cancel_closed_before_effective_events": (
                    _numeric_reduce(
                        folds,
                        "cancel_closed_before_effective_events",
                        "sum",
                    )
                ),
                "total_cancel_pending_at_replay_end_events": (
                    _numeric_reduce(
                        folds,
                        "cancel_pending_at_replay_end_events",
                        "sum",
                    )
                ),
                "total_cancel_inflight_filled_qty": _numeric_reduce(
                    folds,
                    "cancel_inflight_filled_qty",
                    "sum",
                ),
                "arrival_queue_initialization_enabled_folds": int(
                    arrival_queue_enabled.sum()
                ),
                "passive_price_through_depth_constrained_folds": int(
                    price_through_depth_constrained.sum()
                ),
                "terminal_liquidation_depth_constrained_folds": int(
                    terminal_depth_constrained.sum()
                ),
                "terminal_liquidation_complete_folds": int(
                    terminal_complete.sum()
                ),
                "total_limit_orders_sent": _numeric_reduce(
                    folds,
                    "limit_orders_sent",
                    "sum",
                ),
                "total_queue_initialization_events": _numeric_reduce(
                    folds,
                    "queue_initialization_events",
                    "sum",
                ),
                "total_deferred_queue_initialization_events": _numeric_reduce(
                    folds,
                    "deferred_queue_initialization_events",
                    "sum",
                ),
                "total_uninitialized_limit_orders": _numeric_reduce(
                    folds,
                    "uninitialized_limit_orders",
                    "sum",
                ),
                "max_queue_initialization_lag_ns": _numeric_reduce(
                    folds,
                    "max_queue_initialization_lag_ns",
                    "max",
                ),
                "total_residual_resting_transition_events": _numeric_reduce(
                    folds,
                    "residual_resting_transition_events",
                    "sum",
                ),
                "total_residual_resting_transition_qty": _numeric_reduce(
                    folds,
                    "residual_resting_transition_qty",
                    "sum",
                ),
                "total_deferred_residual_queue_events": _numeric_reduce(
                    folds,
                    "deferred_residual_queue_events",
                    "sum",
                ),
                "total_unresolved_residual_queue_events": _numeric_reduce(
                    folds,
                    "unresolved_residual_queue_events",
                    "sum",
                ),
                "max_residual_queue_initialization_lag_ns": _numeric_reduce(
                    folds,
                    "max_residual_queue_initialization_lag_ns",
                    "max",
                ),
                "total_passive_price_through_events": _numeric_reduce(
                    folds,
                    "passive_price_through_events",
                    "sum",
                ),
                "total_passive_price_through_requested_qty": _numeric_reduce(
                    folds,
                    "passive_price_through_requested_qty",
                    "sum",
                ),
                "total_passive_price_through_filled_qty": _numeric_reduce(
                    folds,
                    "passive_price_through_filled_qty",
                    "sum",
                ),
                "total_passive_price_through_shortfall_qty": _numeric_reduce(
                    folds,
                    "passive_price_through_shortfall_qty",
                    "sum",
                ),
                "total_passive_price_through_incomplete_events": _numeric_reduce(
                    folds,
                    "passive_price_through_incomplete_events",
                    "sum",
                ),
                "total_terminal_liquidation_events": _numeric_reduce(
                    folds,
                    "terminal_liquidation_events",
                    "sum",
                ),
                "total_terminal_liquidation_requested_qty": _numeric_reduce(
                    folds,
                    "terminal_liquidation_requested_qty",
                    "sum",
                ),
                "total_terminal_liquidation_filled_qty": _numeric_reduce(
                    folds,
                    "terminal_liquidation_filled_qty",
                    "sum",
                ),
                "total_terminal_liquidation_shortfall_qty": _numeric_reduce(
                    folds,
                    "terminal_liquidation_shortfall_qty",
                    "sum",
                ),
                "total_terminal_liquidation_incomplete_events": _numeric_reduce(
                    folds,
                    "terminal_liquidation_incomplete_events",
                    "sum",
                ),
                "total_terminal_residual_position_qty": _numeric_reduce(
                    folds,
                    "terminal_residual_position_qty",
                    "sum",
                ),
                "total_terminal_residual_instruments": _numeric_reduce(
                    folds,
                    "terminal_residual_instruments",
                    "sum",
                ),
                "total_liquidity_shortfall_events": _numeric_reduce(
                    folds,
                    "liquidity_shortfall_events",
                    "sum",
                ),
                "total_liquidity_shortfall_qty": _numeric_reduce(
                    folds,
                    "liquidity_shortfall_qty",
                    "sum",
                ),
                "total_carried_depletion_shortfall_events": _numeric_reduce(
                    folds,
                    "carried_depletion_shortfall_events",
                    "sum",
                ),
                "total_carried_depletion_shortfall_qty": _numeric_reduce(
                    folds,
                    "carried_depletion_shortfall_qty",
                    "sum",
                ),
                "total_pretrade_rejections": _numeric_reduce(
                    folds,
                    "pretrade_rejections",
                    "sum",
                ),
                "total_venue_rule_rejections": _numeric_reduce(
                    folds,
                    "venue_rule_rejections",
                    "sum",
                ),
                "total_position_risk_rejections": _numeric_reduce(
                    folds,
                    "position_risk_rejections",
                    "sum",
                ),
                "total_self_cross_rejections": _numeric_reduce(
                    folds,
                    "self_cross_rejections",
                    "sum",
                ),
                "worst_drawdown": _numeric_reduce(folds, "max_drawdown", "max"),
                "median_markout_mean": _numeric_reduce(folds, "markout_mean", "median"),
                "median_robust_score": _numeric_reduce(folds, "robust_score", "median"),
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
    config = copy.deepcopy(source) if source else {"schema_version": 1, "strategy": "imbalance"}
    config["ready"] = bool(summary.get("passed", False))
    config["source_run_type"] = "imbalance_replay_walkforward"
    if source_path is not None:
        config["source_candidate_config"] = str(source_path)
    failed_checks = list(config.get("failed_checks", []) or [])
    failed_checks.extend(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist())
    config["failed_checks"] = list(dict.fromkeys(failed_checks))
    config["replay_defaults"] = {
        **(config.get("replay_defaults", {}) if isinstance(config.get("replay_defaults", {}), dict) else {}),
        "tick_size": _jsonable(replay_params["tick_size"]),
        "market": _jsonable(replay_params["market"]),
        "instrument_id": _jsonable(replay_params["instrument_id"]),
        "instrument_kind": _jsonable(replay_params["instrument_kind"]),
        "lot_size": _jsonable(replay_params["lot_size"]),
        "qty": _jsonable(replay_params["qty"]),
        "entry_imbalance": _jsonable(replay_params["entry_imbalance"]),
        "exit_imbalance": _jsonable(replay_params["exit_imbalance"]),
        "min_microprice_edge_ticks": _jsonable(replay_params["min_microprice_edge_ticks"]),
        "max_spread_ticks": _jsonable(replay_params["max_spread_ticks"]),
        "min_depth": _jsonable(replay_params["min_depth"]),
        "hold_ns": _jsonable(replay_params["hold_ns"]),
        "cooloff_ns": _jsonable(replay_params["cooloff_ns"]),
        "markout_horizons_ns": _jsonable(replay_params["markout_horizons_ns"]),
        "generic_costs": _jsonable(replay_params["generic_costs"]),
    }
    config["replay_walkforward"] = {
        "fold_count": _jsonable(summary.get("fold_count")),
        "proof_passed_folds": _jsonable(summary.get("proof_passed_folds")),
        "proof_pass_rate": _jsonable(summary.get("proof_pass_rate")),
        "total_net_pnl": _jsonable(summary.get("total_net_pnl")),
        "total_fills": _jsonable(summary.get("total_fills")),
        "pending_order_risk_reservation_enabled_folds": _jsonable(
            summary.get("pending_order_risk_reservation_enabled_folds")
        ),
        "aggressive_self_cross_prevention_enabled_folds": _jsonable(
            summary.get("aggressive_self_cross_prevention_enabled_folds")
        ),
        "venue_order_validation_enabled_folds": _jsonable(
            summary.get("venue_order_validation_enabled_folds")
        ),
        "shared_event_liquidity_enabled_folds": _jsonable(
            summary.get("shared_event_liquidity_enabled_folds")
        ),
        "persistent_displayed_liquidity_enabled_folds": _jsonable(
            summary.get("persistent_displayed_liquidity_enabled_folds")
        ),
        "lot_conserving_fills_enabled_folds": _jsonable(
            summary.get("lot_conserving_fills_enabled_folds")
        ),
        "causal_event_ordering_enabled_folds": _jsonable(
            summary.get("causal_event_ordering_enabled_folds")
        ),
        "cancel_lifecycle_tracking_enabled_folds": _jsonable(
            summary.get("cancel_lifecycle_tracking_enabled_folds")
        ),
        "total_cancel_requests": _jsonable(
            summary.get("total_cancel_requests")
        ),
        "total_cancel_effective_events": _jsonable(
            summary.get("total_cancel_effective_events")
        ),
        "total_cancel_effective_after_partial_fill_events": _jsonable(
            summary.get(
                "total_cancel_effective_after_partial_fill_events"
            )
        ),
        "total_cancel_filled_before_effective_events": _jsonable(
            summary.get("total_cancel_filled_before_effective_events")
        ),
        "total_cancel_closed_before_effective_events": _jsonable(
            summary.get("total_cancel_closed_before_effective_events")
        ),
        "total_cancel_pending_at_replay_end_events": _jsonable(
            summary.get("total_cancel_pending_at_replay_end_events")
        ),
        "total_cancel_inflight_filled_qty": _jsonable(
            summary.get("total_cancel_inflight_filled_qty")
        ),
        "arrival_queue_initialization_enabled_folds": _jsonable(
            summary.get("arrival_queue_initialization_enabled_folds")
        ),
        "passive_price_through_depth_constrained_folds": _jsonable(
            summary.get("passive_price_through_depth_constrained_folds")
        ),
        "total_limit_orders_sent": _jsonable(
            summary.get("total_limit_orders_sent")
        ),
        "total_queue_initialization_events": _jsonable(
            summary.get("total_queue_initialization_events")
        ),
        "total_deferred_queue_initialization_events": _jsonable(
            summary.get("total_deferred_queue_initialization_events")
        ),
        "total_uninitialized_limit_orders": _jsonable(
            summary.get("total_uninitialized_limit_orders")
        ),
        "max_queue_initialization_lag_ns": _jsonable(
            summary.get("max_queue_initialization_lag_ns")
        ),
        "total_residual_resting_transition_events": _jsonable(
            summary.get("total_residual_resting_transition_events")
        ),
        "total_residual_resting_transition_qty": _jsonable(
            summary.get("total_residual_resting_transition_qty")
        ),
        "total_deferred_residual_queue_events": _jsonable(
            summary.get("total_deferred_residual_queue_events")
        ),
        "total_unresolved_residual_queue_events": _jsonable(
            summary.get("total_unresolved_residual_queue_events")
        ),
        "max_residual_queue_initialization_lag_ns": _jsonable(
            summary.get("max_residual_queue_initialization_lag_ns")
        ),
        "total_passive_price_through_events": _jsonable(
            summary.get("total_passive_price_through_events")
        ),
        "total_passive_price_through_requested_qty": _jsonable(
            summary.get("total_passive_price_through_requested_qty")
        ),
        "total_passive_price_through_filled_qty": _jsonable(
            summary.get("total_passive_price_through_filled_qty")
        ),
        "total_passive_price_through_shortfall_qty": _jsonable(
            summary.get("total_passive_price_through_shortfall_qty")
        ),
        "total_passive_price_through_incomplete_events": _jsonable(
            summary.get("total_passive_price_through_incomplete_events")
        ),
        "terminal_liquidation_depth_constrained_folds": _jsonable(
            summary.get("terminal_liquidation_depth_constrained_folds")
        ),
        "terminal_liquidation_complete_folds": _jsonable(
            summary.get("terminal_liquidation_complete_folds")
        ),
        "total_terminal_liquidation_events": _jsonable(
            summary.get("total_terminal_liquidation_events")
        ),
        "total_terminal_liquidation_requested_qty": _jsonable(
            summary.get("total_terminal_liquidation_requested_qty")
        ),
        "total_terminal_liquidation_filled_qty": _jsonable(
            summary.get("total_terminal_liquidation_filled_qty")
        ),
        "total_terminal_liquidation_shortfall_qty": _jsonable(
            summary.get("total_terminal_liquidation_shortfall_qty")
        ),
        "total_terminal_liquidation_incomplete_events": _jsonable(
            summary.get("total_terminal_liquidation_incomplete_events")
        ),
        "total_terminal_residual_position_qty": _jsonable(
            summary.get("total_terminal_residual_position_qty")
        ),
        "total_terminal_residual_instruments": _jsonable(
            summary.get("total_terminal_residual_instruments")
        ),
        "total_liquidity_shortfall_events": _jsonable(
            summary.get("total_liquidity_shortfall_events")
        ),
        "total_liquidity_shortfall_qty": _jsonable(
            summary.get("total_liquidity_shortfall_qty")
        ),
        "total_carried_depletion_shortfall_events": _jsonable(
            summary.get("total_carried_depletion_shortfall_events")
        ),
        "total_carried_depletion_shortfall_qty": _jsonable(
            summary.get("total_carried_depletion_shortfall_qty")
        ),
        "total_pretrade_rejections": _jsonable(
            summary.get("total_pretrade_rejections")
        ),
        "total_venue_rule_rejections": _jsonable(
            summary.get("total_venue_rule_rejections")
        ),
        "total_position_risk_rejections": _jsonable(
            summary.get("total_position_risk_rejections")
        ),
        "total_self_cross_rejections": _jsonable(
            summary.get("total_self_cross_rejections")
        ),
        "worst_drawdown": _jsonable(summary.get("worst_drawdown")),
        "median_markout_mean": _jsonable(summary.get("median_markout_mean")),
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


def _validate_thresholds(thresholds: ImbalanceReplayWalkForwardThresholds) -> None:
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
    if reducer == "sum":
        return float(values.fillna(0.0).sum())
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
