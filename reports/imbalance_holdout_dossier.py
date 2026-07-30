from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from strategies.run_imbalance_replay import run_imbalance_replay


SCENARIO_COLUMNS = [
    "fold",
    "label",
    "ticks_path",
    "scenario",
    "axis",
    "axis_value",
    "total_latency_us",
    "feed_latency_us",
    "order_latency_us",
    "cost_multiplier",
    "qty_multiplier",
    "qty",
    "run_dir",
    "gross_pnl",
    "total_costs",
    "net_pnl",
    "max_drawdown",
    "orders_sent",
    "fills",
    "filled_qty",
    "turnover",
    "return_on_turnover_bps",
    "liquidity_shortfall_events",
    "liquidity_shortfall_qty",
    "liquidity_shortfall_rate",
    "terminal_residual_position_qty",
    "profitable",
]

CURVE_COLUMNS = [
    "fold_count",
    "total_gross_pnl",
    "total_costs",
    "total_net_pnl",
    "min_fold_net_pnl",
    "profitable_fold_rate",
    "total_orders_sent",
    "total_fills",
    "total_filled_qty",
    "total_turnover",
    "return_on_turnover_bps",
    "total_liquidity_shortfall_events",
    "total_liquidity_shortfall_qty",
    "liquidity_shortfall_rate",
    "max_terminal_residual_position_qty",
]


@dataclass(frozen=True)
class ImbalanceHoldoutThresholds:
    min_holdout_folds: int = 3
    min_baseline_profitable_fold_rate: float = 2.0 / 3.0
    min_baseline_total_net_pnl: float = 0.0
    min_baseline_total_fills: int = 1
    min_max_latency_total_net_pnl: float = 0.0
    min_max_cost_total_net_pnl: float = 0.0
    min_max_qty_total_net_pnl: float = 0.0
    max_max_qty_liquidity_shortfall_rate: float = 0.25


@dataclass(frozen=True)
class ImbalanceHoldoutDossier:
    scenarios: pd.DataFrame
    latency_curve: pd.DataFrame
    cost_curve: pd.DataFrame
    capacity_curve: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(
            not self.summary.empty
            and _to_bool(self.summary.iloc[0].get("passed", False))
        )


def write_imbalance_holdout_dossier(
    candidate_dir: str | Path,
    holdout_tick_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    baseline_latency_us: float = 300.0,
    latency_us_values: list[float] | None = None,
    feed_latency_fraction: float = 0.2,
    cost_multipliers: list[float] | None = None,
    qty_multipliers: list[float] | None = None,
    max_position_lots: int = 20,
    thresholds: ImbalanceHoldoutThresholds | None = None,
) -> ImbalanceHoldoutDossier:
    thresholds = thresholds or ImbalanceHoldoutThresholds()
    _validate_thresholds(thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    candidate_root = Path(candidate_dir)
    candidate_manifest = candidate_root / "manifest.json"
    candidate_config_path = candidate_root / "candidate_config.json"
    holdouts = [Path(path) for path in holdout_tick_paths]
    fold_labels = _fold_labels(holdouts, labels)
    config, config_error = _read_candidate_config(candidate_config_path)
    params, params_error = _candidate_params(config)
    integrity = verify_experiment_manifest(
        candidate_manifest,
        expected_run_type="promotion_report",
        required_artifacts=(
            "candidate_config.json",
            "promotion_candidate.csv",
            "promotion_checks.csv",
            "promotion_summary.csv",
        ),
        require_input_fingerprints=True,
    )
    dependencies = (
        manifest_dependency_paths(candidate_manifest)
        if candidate_manifest.is_file()
        else []
    )
    overlap = _selection_overlap(holdouts, dependencies)
    preflight_checks = _preflight_checks(
        integrity_passed=integrity.passed,
        integrity_error=integrity.error,
        config=config,
        config_error=config_error,
        params_error=params_error,
        holdouts=holdouts,
        overlap=overlap,
        thresholds=thresholds,
    )

    scenarios = pd.DataFrame(columns=SCENARIO_COLUMNS)
    latency_curve = _empty_latency_curve()
    cost_curve = _empty_cost_curve()
    capacity_curve = _empty_capacity_curve()
    checks = preflight_checks
    evaluated = False
    specs: list[dict[str, Any]] = []

    if bool(preflight_checks["passed"].all()):
        latency_values = _normalized_values(
            latency_us_values or [100.0, 300.0, 500.0, 1_000.0],
            baseline_latency_us,
            name="latency_us_values",
            minimum=0.0,
        )
        cost_values = _normalized_values(
            cost_multipliers or [1.0, 1.25, 1.5, 2.0],
            1.0,
            name="cost_multipliers",
            minimum=0.0,
        )
        qty_values = _normalized_values(
            qty_multipliers or [1.0, 2.0, 4.0, 8.0],
            1.0,
            name="qty_multipliers",
            minimum=np.nextafter(0.0, 1.0),
        )
        if not 0.0 <= feed_latency_fraction <= 1.0:
            raise ValueError("feed_latency_fraction must be between 0 and 1")
        if max_position_lots <= 0:
            raise ValueError("max_position_lots must be positive")
        specs = _scenario_specs(
            params=params,
            baseline_latency_us=float(baseline_latency_us),
            latency_values=latency_values,
            cost_values=cost_values,
            qty_values=qty_values,
            feed_latency_fraction=float(feed_latency_fraction),
        )
        required_position_lots = max(
            int(spec["qty"]) for spec in specs
        ) // int(params["lot_size"])
        if max_position_lots < required_position_lots:
            raise ValueError(
                "max_position_lots must cover the largest capacity scenario "
                f"({required_position_lots} lots)"
            )
        scenarios = _run_scenarios(
            holdouts,
            fold_labels,
            specs,
            output_dir=out,
            params=params,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            max_position_lots=max_position_lots,
        )
        latency_curve = _latency_curve(
            scenarios,
            baseline_latency_us=float(baseline_latency_us),
        )
        cost_curve = _cost_curve(scenarios)
        capacity_curve = _capacity_curve(
            scenarios,
            lot_size=int(params["lot_size"]),
        )
        outcome_checks = _outcome_checks(
            scenarios,
            latency_curve,
            cost_curve,
            capacity_curve,
            expected_scenarios=len(holdouts) * len(specs),
            thresholds=thresholds,
        )
        checks = pd.concat(
            [preflight_checks, outcome_checks],
            ignore_index=True,
        )
        evaluated = True

    summary = _summary(
        scenarios,
        latency_curve,
        cost_curve,
        capacity_curve,
        checks,
        config=config,
        integrity_passed=integrity.passed,
        selection_isolated=not bool(overlap),
        evaluated=evaluated,
    )
    report = ImbalanceHoldoutDossier(
        scenarios=scenarios,
        latency_curve=latency_curve,
        cost_curve=cost_curve,
        capacity_curve=capacity_curve,
        checks=checks,
        summary=summary,
        output_dir=out,
    )
    _write_outputs(
        report,
        candidate_manifest=candidate_manifest,
        candidate_config_path=candidate_config_path,
        candidate_dependencies=dependencies,
        holdouts=holdouts,
        parameters={
            "labels": fold_labels,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "baseline_latency_us": baseline_latency_us,
            "latency_us_values": sorted(
                {
                    float(spec["total_latency_us"])
                    for spec in specs
                    if spec["axis"] in {"baseline", "latency"}
                }
            ),
            "feed_latency_fraction": feed_latency_fraction,
            "cost_multipliers": sorted(
                {
                    float(spec["cost_multiplier"])
                    for spec in specs
                    if spec["axis"] in {"baseline", "cost"}
                }
            ),
            "qty_multipliers": sorted(
                {
                    float(spec["qty_multiplier"])
                    for spec in specs
                    if spec["axis"] in {"baseline", "capacity"}
                }
            ),
            "max_position_lots": max_position_lots,
            "thresholds": asdict(thresholds),
            "candidate_replay_defaults": params,
            "non_authorizing": True,
        },
    )
    return report


def _run_scenarios(
    holdouts: list[Path],
    labels: list[str],
    specs: list[dict[str, Any]],
    *,
    output_dir: Path,
    params: dict[str, Any],
    timestamp_unit: str,
    timestamp_tz: str | None,
    filter_session: bool,
    max_position_lots: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    generic = params["generic_costs"]
    for fold, (ticks_path, label) in enumerate(
        zip(holdouts, labels),
        start=1,
    ):
        fold_root = output_dir / "runs" / f"f{fold:02d}"
        for spec in specs:
            run_dir = fold_root / str(spec["scenario"])
            replay = run_imbalance_replay(
                ticks_path=ticks_path,
                output_dir=run_dir,
                timestamp_unit=timestamp_unit,
                timestamp_tz=timestamp_tz,
                filter_session=filter_session,
                market=str(params["market"]),
                instrument_id=str(params["instrument_id"]),
                instrument_kind=str(params["instrument_kind"]),
                lot_size=int(params["lot_size"]),
                tick_size=float(params["tick_size"]),
                qty=int(spec["qty"]),
                entry_imbalance=float(params["entry_imbalance"]),
                exit_imbalance=float(params["exit_imbalance"]),
                min_microprice_edge_ticks=float(
                    params["min_microprice_edge_ticks"]
                ),
                max_spread_ticks=float(params["max_spread_ticks"]),
                min_depth=int(params["min_depth"]),
                hold_ns=int(params["hold_ns"]),
                cooloff_ns=int(params["cooloff_ns"]),
                feed_latency_us=float(spec["feed_latency_us"]),
                order_latency_us=float(spec["order_latency_us"]),
                generic_buy_notional_rate=float(
                    generic["buy_notional_rate"]
                ),
                generic_sell_notional_rate=float(
                    generic["sell_notional_rate"]
                ),
                generic_per_unit_fee=float(generic["per_unit_fee"]),
                generic_per_contract_fee=float(
                    generic["per_contract_fee"]
                ),
                generic_per_order_fee=float(generic["per_order_fee"]),
                cost_multiplier=float(spec["cost_multiplier"]),
                max_position_lots=max_position_lots,
                markout_horizons_ns=list(params["markout_horizons_ns"]),
            )
            rows.append(
                _scenario_row(
                    replay,
                    fold=fold,
                    label=label,
                    ticks_path=ticks_path,
                    run_dir=run_dir,
                    spec=spec,
                )
            )
    return pd.DataFrame(rows, columns=SCENARIO_COLUMNS)


def _scenario_row(
    replay: Any,
    *,
    fold: int,
    label: str,
    ticks_path: Path,
    run_dir: Path,
    spec: dict[str, Any],
) -> dict[str, Any]:
    summary = replay.summary.iloc[0]
    fills = replay.result.fills
    filled_qty = (
        float(pd.to_numeric(fills["qty"], errors="coerce").abs().sum())
        if not fills.empty and "qty" in fills
        else 0.0
    )
    turnover = _number(summary, "turnover")
    net_pnl = _number(summary, "net_pnl")
    shortfall_qty = _number(summary, "liquidity_shortfall_qty")
    observed_qty = filled_qty + shortfall_qty
    return {
        "fold": fold,
        "label": label,
        "ticks_path": str(ticks_path.resolve()),
        "scenario": spec["scenario"],
        "axis": spec["axis"],
        "axis_value": spec["axis_value"],
        "total_latency_us": spec["total_latency_us"],
        "feed_latency_us": spec["feed_latency_us"],
        "order_latency_us": spec["order_latency_us"],
        "cost_multiplier": spec["cost_multiplier"],
        "qty_multiplier": spec["qty_multiplier"],
        "qty": spec["qty"],
        "run_dir": str(run_dir.resolve()),
        "gross_pnl": _number(summary, "gross_pnl"),
        "total_costs": _number(summary, "total_costs"),
        "net_pnl": net_pnl,
        "max_drawdown": _number(summary, "max_drawdown"),
        "orders_sent": _integer(summary, "orders_sent"),
        "fills": _integer(summary, "fills"),
        "filled_qty": filled_qty,
        "turnover": turnover,
        "return_on_turnover_bps": (
            1e4 * net_pnl / turnover if turnover > 0 else np.nan
        ),
        "liquidity_shortfall_events": _integer(
            summary,
            "liquidity_shortfall_events",
        ),
        "liquidity_shortfall_qty": shortfall_qty,
        "liquidity_shortfall_rate": (
            shortfall_qty / observed_qty if observed_qty > 0 else 0.0
        ),
        "terminal_residual_position_qty": _number(
            summary,
            "terminal_residual_position_qty",
        ),
        "profitable": net_pnl > 0,
    }


def _scenario_specs(
    *,
    params: dict[str, Any],
    baseline_latency_us: float,
    latency_values: list[float],
    cost_values: list[float],
    qty_values: list[float],
    feed_latency_fraction: float,
) -> list[dict[str, Any]]:
    if not math.isfinite(baseline_latency_us) or baseline_latency_us < 0:
        raise ValueError("baseline_latency_us must be finite and non-negative")
    lot_size = int(params["lot_size"])
    base_qty = int(params["qty"])
    if lot_size <= 0 or base_qty <= 0 or base_qty % lot_size:
        raise ValueError("candidate qty must be a positive whole number of lots")

    def make_spec(
        scenario: str,
        axis: str,
        axis_value: float,
        *,
        latency: float = baseline_latency_us,
        cost: float = 1.0,
        qty_multiplier: float = 1.0,
    ) -> dict[str, Any]:
        qty_lots = max(1, int(round(base_qty * qty_multiplier / lot_size)))
        qty = qty_lots * lot_size
        actual_qty_multiplier = qty / base_qty
        return {
            "scenario": scenario,
            "axis": axis,
            "axis_value": axis_value,
            "total_latency_us": latency,
            "feed_latency_us": latency * feed_latency_fraction,
            "order_latency_us": latency * (1.0 - feed_latency_fraction),
            "cost_multiplier": cost,
            "qty_multiplier": actual_qty_multiplier,
            "qty": qty,
        }

    specs = [
        make_spec(
            "base",
            "baseline",
            1.0,
        )
    ]
    for value in latency_values:
        if _same_number(value, baseline_latency_us):
            continue
        specs.append(
            make_spec(
                f"lat_{_token(value)}",
                "latency",
                value,
                latency=value,
            )
        )
    for value in cost_values:
        if _same_number(value, 1.0):
            continue
        specs.append(
            make_spec(
                f"cost_{_token(value)}",
                "cost",
                value,
                cost=value,
            )
        )
    seen_qty = {base_qty}
    for value in qty_values:
        spec = make_spec(
            f"qty_{_token(value)}",
            "capacity",
            value,
            qty_multiplier=value,
        )
        if int(spec["qty"]) in seen_qty:
            continue
        seen_qty.add(int(spec["qty"]))
        spec["scenario"] = f"qty_{int(spec['qty'])}"
        spec["axis_value"] = spec["qty_multiplier"]
        specs.append(spec)
    return specs


def _latency_curve(
    scenarios: pd.DataFrame,
    *,
    baseline_latency_us: float,
) -> pd.DataFrame:
    selected = _axis_rows(scenarios, "latency")
    rows = []
    for latency, group in selected.groupby(
        "total_latency_us",
        dropna=False,
        sort=True,
    ):
        row = {
            "total_latency_us": float(latency),
            "feed_latency_us": float(group["feed_latency_us"].iloc[0]),
            "order_latency_us": float(group["order_latency_us"].iloc[0]),
            **_aggregate(group),
        }
        rows.append(row)
    curve = pd.DataFrame(
        rows,
        columns=[
            "total_latency_us",
            "feed_latency_us",
            "order_latency_us",
            *CURVE_COLUMNS,
        ],
    )
    baseline = _curve_value(
        curve,
        "total_latency_us",
        baseline_latency_us,
        "total_net_pnl",
    )
    curve["pnl_retention_vs_baseline"] = curve["total_net_pnl"].map(
        lambda value: _retention(value, baseline)
    )
    return curve


def _cost_curve(scenarios: pd.DataFrame) -> pd.DataFrame:
    selected = _axis_rows(scenarios, "cost")
    rows = []
    for multiplier, group in selected.groupby(
        "cost_multiplier",
        dropna=False,
        sort=True,
    ):
        rows.append(
            {
                "cost_multiplier": float(multiplier),
                **_aggregate(group),
            }
        )
    curve = pd.DataFrame(
        rows,
        columns=["cost_multiplier", *CURVE_COLUMNS],
    )
    baseline = _curve_value(
        curve,
        "cost_multiplier",
        1.0,
        "total_net_pnl",
    )
    curve["pnl_retention_vs_baseline"] = curve["total_net_pnl"].map(
        lambda value: _retention(value, baseline)
    )
    return curve


def _capacity_curve(
    scenarios: pd.DataFrame,
    *,
    lot_size: int,
) -> pd.DataFrame:
    selected = _axis_rows(scenarios, "capacity")
    rows = []
    for (qty, multiplier), group in selected.groupby(
        ["qty", "qty_multiplier"],
        dropna=False,
        sort=True,
    ):
        aggregate = _aggregate(group)
        requested_lots = len(group) * float(qty) / lot_size
        rows.append(
            {
                "qty": int(qty),
                "qty_multiplier": float(multiplier),
                **aggregate,
                "net_pnl_per_requested_lot": (
                    aggregate["total_net_pnl"] / requested_lots
                    if requested_lots > 0
                    else np.nan
                ),
            }
        )
    curve = pd.DataFrame(
        rows,
        columns=[
            "qty",
            "qty_multiplier",
            *CURVE_COLUMNS,
            "net_pnl_per_requested_lot",
        ],
    ).sort_values("qty", ignore_index=True)
    baseline = _curve_value(
        curve,
        "qty_multiplier",
        1.0,
        "total_net_pnl",
    )
    curve["linear_scale_efficiency"] = curve.apply(
        lambda row: _scale_efficiency(
            float(row["total_net_pnl"]),
            baseline,
            float(row["qty_multiplier"]),
        ),
        axis=1,
    )
    curve["marginal_net_pnl"] = curve["total_net_pnl"].diff()
    curve["marginal_net_pnl_per_added_lot"] = (
        curve["marginal_net_pnl"]
        / (curve["qty"].diff() / lot_size)
    )
    return curve


def _axis_rows(scenarios: pd.DataFrame, axis: str) -> pd.DataFrame:
    return scenarios.loc[
        scenarios["axis"].isin(["baseline", axis])
    ].copy()


def _aggregate(group: pd.DataFrame) -> dict[str, Any]:
    total_turnover = float(group["turnover"].sum())
    total_net_pnl = float(group["net_pnl"].sum())
    filled_qty = float(group["filled_qty"].sum())
    shortfall_qty = float(group["liquidity_shortfall_qty"].sum())
    observed_qty = filled_qty + shortfall_qty
    return {
        "fold_count": int(group["fold"].nunique()),
        "total_gross_pnl": float(group["gross_pnl"].sum()),
        "total_costs": float(group["total_costs"].sum()),
        "total_net_pnl": total_net_pnl,
        "min_fold_net_pnl": float(group["net_pnl"].min()),
        "profitable_fold_rate": float(group["profitable"].mean()),
        "total_orders_sent": int(group["orders_sent"].sum()),
        "total_fills": int(group["fills"].sum()),
        "total_filled_qty": filled_qty,
        "total_turnover": total_turnover,
        "return_on_turnover_bps": (
            1e4 * total_net_pnl / total_turnover
            if total_turnover > 0
            else np.nan
        ),
        "total_liquidity_shortfall_events": int(
            group["liquidity_shortfall_events"].sum()
        ),
        "total_liquidity_shortfall_qty": shortfall_qty,
        "liquidity_shortfall_rate": (
            shortfall_qty / observed_qty if observed_qty > 0 else 0.0
        ),
        "max_terminal_residual_position_qty": float(
            group["terminal_residual_position_qty"].max()
        ),
    }


def _preflight_checks(
    *,
    integrity_passed: bool,
    integrity_error: str,
    config: dict[str, Any],
    config_error: str,
    params_error: str,
    holdouts: list[Path],
    overlap: list[Path],
    thresholds: ImbalanceHoldoutThresholds,
) -> pd.DataFrame:
    files_current = bool(holdouts) and all(path.is_file() for path in holdouts)
    resolved = [path.resolve() for path in holdouts if path.exists()]
    rows = [
        _check(
            "candidate_manifest_current",
            integrity_passed,
            "is",
            True,
            integrity_passed,
            integrity_error or "candidate promotion manifest is not current",
        ),
        _check(
            "candidate_config_readable",
            not bool(config_error),
            "is",
            True,
            not bool(config_error),
            config_error,
        ),
        _check(
            "candidate_ready",
            _to_bool(config.get("ready", False)),
            "is",
            True,
            _to_bool(config.get("ready", False)),
            "candidate promotion is not ready",
        ),
        _check(
            "candidate_strategy",
            str(config.get("strategy", "")),
            "==",
            "imbalance",
            str(config.get("strategy", "")) == "imbalance",
            "candidate strategy is not imbalance",
        ),
        _check(
            "candidate_replay_defaults_complete",
            not bool(params_error),
            "is",
            True,
            not bool(params_error),
            params_error,
        ),
        _check(
            "holdout_files_current",
            files_current,
            "is",
            True,
            files_current,
            "one or more holdout tick files are missing",
        ),
        _check(
            "holdout_files_unique",
            len(resolved),
            "==",
            len(set(resolved)),
            len(resolved) == len(set(resolved)),
            "holdout tick files must be unique",
        ),
        _check(
            "selection_isolated",
            ",".join(str(path) for path in overlap),
            "==",
            "",
            not bool(overlap),
            "holdout data overlaps candidate development lineage",
        ),
        _threshold_check(
            "holdout_fold_count",
            len(holdouts),
            ">=",
            thresholds.min_holdout_folds,
        ),
    ]
    return pd.DataFrame(rows)


def _outcome_checks(
    scenarios: pd.DataFrame,
    latency_curve: pd.DataFrame,
    cost_curve: pd.DataFrame,
    capacity_curve: pd.DataFrame,
    *,
    expected_scenarios: int,
    thresholds: ImbalanceHoldoutThresholds,
) -> pd.DataFrame:
    baseline = scenarios.loc[scenarios["axis"] == "baseline"]
    baseline_agg = _aggregate(baseline)
    max_latency = latency_curve.sort_values("total_latency_us").iloc[-1]
    max_cost = cost_curve.sort_values("cost_multiplier").iloc[-1]
    max_qty = capacity_curve.sort_values("qty").iloc[-1]
    rows = [
        _threshold_check(
            "scenario_grid_complete",
            len(scenarios),
            "==",
            expected_scenarios,
        ),
        _threshold_check(
            "baseline_profitable_fold_rate",
            baseline_agg["profitable_fold_rate"],
            ">=",
            thresholds.min_baseline_profitable_fold_rate,
        ),
        _threshold_check(
            "baseline_total_net_pnl",
            baseline_agg["total_net_pnl"],
            ">=",
            thresholds.min_baseline_total_net_pnl,
        ),
        _threshold_check(
            "baseline_total_fills",
            baseline_agg["total_fills"],
            ">=",
            thresholds.min_baseline_total_fills,
        ),
        _threshold_check(
            "max_latency_total_net_pnl",
            max_latency["total_net_pnl"],
            ">=",
            thresholds.min_max_latency_total_net_pnl,
        ),
        _threshold_check(
            "max_cost_total_net_pnl",
            max_cost["total_net_pnl"],
            ">=",
            thresholds.min_max_cost_total_net_pnl,
        ),
        _threshold_check(
            "max_qty_total_net_pnl",
            max_qty["total_net_pnl"],
            ">=",
            thresholds.min_max_qty_total_net_pnl,
        ),
        _threshold_check(
            "max_qty_liquidity_shortfall_rate",
            max_qty["liquidity_shortfall_rate"],
            "<=",
            thresholds.max_max_qty_liquidity_shortfall_rate,
        ),
    ]
    return pd.DataFrame(rows)


def _summary(
    scenarios: pd.DataFrame,
    latency_curve: pd.DataFrame,
    cost_curve: pd.DataFrame,
    capacity_curve: pd.DataFrame,
    checks: pd.DataFrame,
    *,
    config: dict[str, Any],
    integrity_passed: bool,
    selection_isolated: bool,
    evaluated: bool,
) -> pd.DataFrame:
    passed = bool(
        evaluated
        and not checks.empty
        and checks["passed"].map(_to_bool).all()
    )
    baseline = scenarios.loc[scenarios["axis"] == "baseline"]
    baseline_agg = _aggregate(baseline) if not baseline.empty else {}
    max_latency = _last_row(latency_curve, "total_latency_us")
    max_cost = _last_row(cost_curve, "cost_multiplier")
    max_qty = _last_row(capacity_curve, "qty")
    failed = checks.loc[~checks["passed"].map(_to_bool), "check"].astype(str)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "evaluated": evaluated,
                "non_authorizing": True,
                "recommendation": (
                    "shadow_review_candidate"
                    if passed
                    else "keep_in_research"
                ),
                "strategy": "imbalance",
                "market": str(
                    (config.get("replay_defaults", {}) or {}).get(
                        "market",
                        "",
                    )
                ),
                "candidate_scenario_key": str(
                    config.get("scenario_key", "")
                ),
                "candidate_manifest_current": integrity_passed,
                "selection_isolated": selection_isolated,
                "holdout_folds": int(
                    baseline["fold"].nunique()
                    if not baseline.empty
                    else 0
                ),
                "scenario_count": len(scenarios),
                "checks": len(checks),
                "failed_checks": len(failed),
                "failed_check_names": ",".join(failed),
                "baseline_total_net_pnl": baseline_agg.get(
                    "total_net_pnl",
                    np.nan,
                ),
                "baseline_profitable_fold_rate": baseline_agg.get(
                    "profitable_fold_rate",
                    np.nan,
                ),
                "baseline_total_fills": baseline_agg.get(
                    "total_fills",
                    0,
                ),
                "max_tested_latency_us": _series_number(
                    max_latency,
                    "total_latency_us",
                ),
                "max_latency_total_net_pnl": _series_number(
                    max_latency,
                    "total_net_pnl",
                ),
                "max_profitable_latency_us": _max_profitable(
                    latency_curve,
                    "total_latency_us",
                ),
                "max_tested_cost_multiplier": _series_number(
                    max_cost,
                    "cost_multiplier",
                ),
                "max_cost_total_net_pnl": _series_number(
                    max_cost,
                    "total_net_pnl",
                ),
                "max_profitable_cost_multiplier": _max_profitable(
                    cost_curve,
                    "cost_multiplier",
                ),
                "max_tested_qty": _series_number(max_qty, "qty"),
                "max_tested_qty_multiplier": _series_number(
                    max_qty,
                    "qty_multiplier",
                ),
                "max_qty_total_net_pnl": _series_number(
                    max_qty,
                    "total_net_pnl",
                ),
                "max_qty_linear_scale_efficiency": _series_number(
                    max_qty,
                    "linear_scale_efficiency",
                ),
                "max_qty_liquidity_shortfall_rate": _series_number(
                    max_qty,
                    "liquidity_shortfall_rate",
                ),
                "max_profitable_qty": _max_profitable(
                    capacity_curve,
                    "qty",
                ),
            }
        ]
    )


def _write_outputs(
    report: ImbalanceHoldoutDossier,
    *,
    candidate_manifest: Path,
    candidate_config_path: Path,
    candidate_dependencies: list[Path],
    holdouts: list[Path],
    parameters: dict[str, Any],
) -> None:
    if report.output_dir is None:
        raise ValueError("output_dir is required")
    out = report.output_dir
    report.scenarios.to_csv(out / "holdout_scenarios.csv", index=False)
    report.latency_curve.to_csv(out / "latency_curve.csv", index=False)
    report.cost_curve.to_csv(out / "cost_curve.csv", index=False)
    report.capacity_curve.to_csv(out / "capacity_curve.csv", index=False)
    report.checks.to_csv(out / "holdout_checks.csv", index=False)
    report.summary.to_csv(out / "holdout_summary.csv", index=False)
    payload = {
        "schema_version": 1,
        "summary": _records(report.summary),
        "checks": _records(report.checks),
        "latency_curve": _records(report.latency_curve),
        "cost_curve": _records(report.cost_curve),
        "capacity_curve": _records(report.capacity_curve),
        "limitations": [
            "This dossier is non-authorizing and cannot enable broker routing.",
            "Selection isolation proves path separation, not that a human never inspected holdout data.",
            "Historical or synthetic holdout performance is not evidence of live profitability.",
            "Capacity is bounded by observed top-of-book liquidity and remains a conservative research estimate.",
        ],
    }
    (out / "research_proof.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "RESEARCH_PROOF.md").write_text(
        _markdown(report),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="imbalance_holdout_dossier",
        parameters=parameters,
        inputs={
            "candidate_manifest": candidate_manifest,
            "candidate_config": candidate_config_path,
            "candidate_dependencies": candidate_dependencies,
            "holdout_ticks": holdouts,
        },
        extra={
            "passed": report.passed,
            "non_authorizing": True,
        },
    )


def _markdown(report: ImbalanceHoldoutDossier) -> str:
    summary = report.summary.iloc[0]
    failed = report.checks.loc[
        ~report.checks["passed"].map(_to_bool)
    ]
    lines = [
        "# Imbalance Holdout Research Proof",
        "",
        f"**Verdict:** {'PASS' if report.passed else 'BLOCKED'}",
        "",
        (
            "This is a selection-isolated, non-authorizing research verdict. "
            "It does not permit paper, shadow, or live broker submission."
        ),
        "",
        "## Snapshot",
        "",
        f"- Candidate: `{summary.get('candidate_scenario_key', '')}`",
        f"- Market: `{summary.get('market', '')}`",
        f"- Holdout folds: {_display(summary.get('holdout_folds'))}",
        f"- Scenario replays: {_display(summary.get('scenario_count'))}",
        (
            "- Baseline net PnL: "
            f"{_display(summary.get('baseline_total_net_pnl'))}"
        ),
        (
            "- Profitable holdout rate: "
            f"{_percent(summary.get('baseline_profitable_fold_rate'))}"
        ),
        (
            "- Maximum profitable tested latency: "
            f"{_display(summary.get('max_profitable_latency_us'))} us"
        ),
        (
            "- Maximum profitable tested cost multiplier: "
            f"{_display(summary.get('max_profitable_cost_multiplier'))}x"
        ),
        (
            "- Maximum profitable tested quantity: "
            f"{_display(summary.get('max_profitable_qty'))}"
        ),
        "",
        "## Latency Curve",
        "",
        _markdown_table(
            report.latency_curve,
            [
                "total_latency_us",
                "total_net_pnl",
                "profitable_fold_rate",
                "pnl_retention_vs_baseline",
                "return_on_turnover_bps",
            ],
        ),
        "",
        "## Cost Curve",
        "",
        _markdown_table(
            report.cost_curve,
            [
                "cost_multiplier",
                "total_costs",
                "total_net_pnl",
                "profitable_fold_rate",
                "pnl_retention_vs_baseline",
            ],
        ),
        "",
        "## Capacity Curve",
        "",
        _markdown_table(
            report.capacity_curve,
            [
                "qty",
                "qty_multiplier",
                "total_net_pnl",
                "net_pnl_per_requested_lot",
                "linear_scale_efficiency",
                "liquidity_shortfall_rate",
            ],
        ),
        "",
        "## Gate Checks",
        "",
        _markdown_table(
            report.checks,
            [
                "check",
                "value",
                "operator",
                "threshold",
                "passed",
            ],
        ),
        "",
        "## Failed Checks",
        "",
    ]
    if failed.empty:
        lines.append("- None.")
    else:
        for row in failed.itertuples(index=False):
            lines.append(f"- `{row.check}`: {row.reason}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "- Latency results estimate how quickly the edge decays as "
                "the exchange-to-decision-to-order path slows."
            ),
            "- Cost results stress the complete cash cost model without changing fills.",
            (
                "- Capacity results rerun larger venue-valid quantities "
                "against the same observed book, so saturation and "
                "shortfalls are visible."
            ),
            (
                "- Holdout path separation prevents the promoted candidate's "
                "manifested development inputs from being reused as holdouts."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_Not evaluated._"
    visible = [column for column in columns if column in frame]
    header = "| " + " | ".join(visible) + " |"
    divider = "| " + " | ".join("---" for _ in visible) + " |"
    rows = [
        "| "
        + " | ".join(_display(row[column]) for column in visible)
        + " |"
        for _, row in frame[visible].iterrows()
    ]
    return "\n".join([header, divider, *rows])


def _candidate_params(
    config: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    defaults = config.get("replay_defaults", {})
    if not isinstance(defaults, dict):
        return {}, "candidate replay_defaults must be an object"
    required = [
        "market",
        "instrument_id",
        "instrument_kind",
        "lot_size",
        "tick_size",
        "qty",
        "entry_imbalance",
        "exit_imbalance",
        "min_microprice_edge_ticks",
        "max_spread_ticks",
        "min_depth",
        "hold_ns",
        "cooloff_ns",
    ]
    missing = [
        name
        for name in required
        if name not in defaults or defaults[name] is None
    ]
    if missing:
        return {}, f"candidate replay_defaults missing: {missing}"
    generic = defaults.get("generic_costs", {}) or {}
    if not isinstance(generic, dict):
        return {}, "candidate replay_defaults.generic_costs must be an object"
    try:
        params = {
            "market": str(defaults["market"]),
            "instrument_id": str(defaults["instrument_id"]),
            "instrument_kind": str(defaults["instrument_kind"]),
            "lot_size": int(defaults["lot_size"]),
            "tick_size": float(defaults["tick_size"]),
            "qty": int(defaults["qty"]),
            "entry_imbalance": float(defaults["entry_imbalance"]),
            "exit_imbalance": float(defaults["exit_imbalance"]),
            "min_microprice_edge_ticks": float(
                defaults["min_microprice_edge_ticks"]
            ),
            "max_spread_ticks": float(defaults["max_spread_ticks"]),
            "min_depth": int(defaults["min_depth"]),
            "hold_ns": int(defaults["hold_ns"]),
            "cooloff_ns": int(defaults["cooloff_ns"]),
            "markout_horizons_ns": [
                int(value)
                for value in defaults.get(
                    "markout_horizons_ns",
                    [100_000_000, 1_000_000_000],
                )
            ],
            "generic_costs": {
                "buy_notional_rate": float(
                    generic.get("buy_notional_rate", 0.0)
                ),
                "sell_notional_rate": float(
                    generic.get("sell_notional_rate", 0.0)
                ),
                "per_unit_fee": float(generic.get("per_unit_fee", 0.0)),
                "per_contract_fee": float(
                    generic.get("per_contract_fee", 0.0)
                ),
                "per_order_fee": float(generic.get("per_order_fee", 0.0)),
            },
        }
    except (TypeError, ValueError) as exc:
        return {}, f"candidate replay defaults are invalid: {exc}"
    numeric_values = [
        params["tick_size"],
        params["entry_imbalance"],
        params["exit_imbalance"],
        params["min_microprice_edge_ticks"],
        params["max_spread_ticks"],
        *params["generic_costs"].values(),
    ]
    if not all(math.isfinite(float(value)) for value in numeric_values):
        return {}, "candidate replay defaults contain non-finite values"
    return params, ""


def _read_candidate_config(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "candidate_config.json is missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}, "candidate_config.json is unreadable"
    if not isinstance(payload, dict):
        return {}, "candidate_config.json must contain an object"
    return payload, ""


def _selection_overlap(
    holdouts: list[Path],
    dependencies: list[Path],
) -> list[Path]:
    overlaps: list[Path] = []
    resolved_dependencies = [path.resolve() for path in dependencies]
    for holdout in holdouts:
        resolved = holdout.resolve()
        for dependency in resolved_dependencies:
            if resolved == dependency or (
                dependency.is_dir() and dependency in resolved.parents
            ):
                overlaps.append(resolved)
                break
    return overlaps


def _fold_labels(paths: list[Path], labels: list[str] | None) -> list[str]:
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match holdout tick files")
    values = labels if labels is not None else [path.stem for path in paths]
    return [str(value) for value in values]


def _normalized_values(
    values: list[float],
    required: float,
    *,
    name: str,
    minimum: float,
) -> list[float]:
    normalized = [float(value) for value in values]
    normalized.append(float(required))
    if any(
        not math.isfinite(value) or value < minimum
        for value in normalized
    ):
        raise ValueError(f"{name} contains an invalid value")
    return sorted(set(normalized))


def _validate_thresholds(thresholds: ImbalanceHoldoutThresholds) -> None:
    if thresholds.min_holdout_folds <= 0:
        raise ValueError("min_holdout_folds must be positive")
    if not 0 <= thresholds.min_baseline_profitable_fold_rate <= 1:
        raise ValueError(
            "min_baseline_profitable_fold_rate must be between 0 and 1"
        )
    if thresholds.min_baseline_total_fills < 0:
        raise ValueError("min_baseline_total_fills must be non-negative")
    if not 0 <= thresholds.max_max_qty_liquidity_shortfall_rate <= 1:
        raise ValueError(
            "max_max_qty_liquidity_shortfall_rate must be between 0 and 1"
        )


def _threshold_check(
    name: str,
    value: float | int,
    operator: str,
    threshold: float | int,
) -> dict[str, Any]:
    numeric = float(value)
    target = float(threshold)
    if operator == ">=":
        passed = numeric >= target
    elif operator == "<=":
        passed = numeric <= target
    elif operator == "==":
        passed = _same_number(numeric, target)
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    return _check(
        name,
        value,
        operator,
        threshold,
        passed,
        "" if passed else f"{name} {numeric:.6g} failed {operator} {target:.6g}",
    )


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _empty_latency_curve() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "total_latency_us",
            "feed_latency_us",
            "order_latency_us",
            *CURVE_COLUMNS,
            "pnl_retention_vs_baseline",
        ]
    )


def _empty_cost_curve() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "cost_multiplier",
            *CURVE_COLUMNS,
            "pnl_retention_vs_baseline",
        ]
    )


def _empty_capacity_curve() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "qty",
            "qty_multiplier",
            *CURVE_COLUMNS,
            "net_pnl_per_requested_lot",
            "linear_scale_efficiency",
            "marginal_net_pnl",
            "marginal_net_pnl_per_added_lot",
        ]
    )


def _curve_value(
    frame: pd.DataFrame,
    key: str,
    expected: float,
    value: str,
) -> float:
    match = frame.loc[
        pd.to_numeric(frame[key], errors="coerce").map(
            lambda item: _same_number(item, expected)
        )
    ]
    return float(match.iloc[0][value]) if not match.empty else np.nan


def _last_row(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=object)
    return frame.sort_values(column).iloc[-1]


def _max_profitable(frame: pd.DataFrame, column: str) -> float:
    if frame.empty:
        return np.nan
    profitable = frame.loc[
        pd.to_numeric(frame["total_net_pnl"], errors="coerce") >= 0
    ]
    return (
        float(pd.to_numeric(profitable[column], errors="coerce").max())
        if not profitable.empty
        else np.nan
    )


def _retention(value: float, baseline: float) -> float:
    if not math.isfinite(baseline) or abs(baseline) <= 1e-12:
        return np.nan
    return float(value) / baseline


def _scale_efficiency(
    value: float,
    baseline: float,
    multiplier: float,
) -> float:
    denominator = baseline * multiplier
    if (
        not math.isfinite(denominator)
        or abs(denominator) <= 1e-12
    ):
        return np.nan
    return value / denominator


def _same_number(left: Any, right: Any) -> bool:
    try:
        return math.isclose(
            float(left),
            float(right),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    except (TypeError, ValueError):
        return False


def _token(value: float) -> str:
    text = f"{float(value):.9g}"
    return re.sub(r"[^0-9A-Za-z]+", "p", text).strip("p") or "0"


def _number(row: pd.Series, column: str) -> float:
    if column not in row or pd.isna(row[column]):
        return 0.0
    return float(row[column])


def _integer(row: pd.Series, column: str) -> int:
    return int(round(_number(row, column)))


def _series_number(row: pd.Series, column: str) -> float:
    if column not in row or pd.isna(row[column]):
        return np.nan
    return float(row[column])


def _to_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "passed",
            "ready",
        }
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _display(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.6g}"
    return str(value)


def _percent(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NA"
    if not math.isfinite(numeric):
        return "NA"
    return f"{100.0 * numeric:.1f}%"


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            str(key): _jsonable(value)
            for key, value in row.items()
        }
        for row in frame.to_dict(orient="records")
    ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value
