from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from markets.profiles import MARKET_PROFILES, MarketProfile, get_market_profile
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class StrategyPortabilitySpec:
    strategy: str
    family: str
    data_requirements: tuple[str, ...]
    workflow_commands: tuple[str, ...]
    portable_market_types: tuple[str, ...]
    india_only: bool = False
    requires_explicit_fee_model_outside_india: bool = True
    notes: str = ""


@dataclass(frozen=True)
class MarketPortabilityReportConfig:
    markets: tuple[str, ...] = tuple(MARKET_PROFILES)
    strategies: tuple[str, ...] = ()
    explicit_fee_model: bool = False


@dataclass(frozen=True)
class MarketPortabilityReport:
    matrix: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    config: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


STRATEGY_SPECS: dict[str, StrategyPortabilitySpec] = {
    "microprice_imbalance": StrategyPortabilitySpec(
        strategy="microprice_imbalance",
        family="single_instrument_tob",
        data_requirements=("top_of_book_ticks", "forward_mid_labels", "explicit_fees"),
        workflow_commands=(
            "walkforward-imbalance-edge",
            "walkforward-imbalance-replay",
            "promote-imbalance-candidate",
            "pipeline-imbalance",
        ),
        portable_market_types=("equity", "options", "derivatives"),
        notes="portable when session profile, tick size, lot size, and fee model are explicit",
    ),
    "lead_lag_taker": StrategyPortabilitySpec(
        strategy="lead_lag_taker",
        family="cross_instrument_latency",
        data_requirements=("paired_top_of_book_ticks", "lead_lag_measurement", "explicit_fees"),
        workflow_commands=("measure-leadlag", "audit-leadlag-edge", "replay-leadlag", "sweep-leadlag"),
        portable_market_types=("equity", "options", "derivatives"),
        notes="portable to US pairs once paired feeds share a normalized clock",
    ),
    "parity_box": StrategyPortabilitySpec(
        strategy="parity_box",
        family="options_relative_value",
        data_requirements=("option_chain_snapshots", "futures_or_forward", "explicit_fees"),
        workflow_commands=("scan-parity-box", "audit-parity-edge", "replay-parity", "sweep-parity"),
        portable_market_types=("options", "derivatives"),
        notes="portable to option markets with executable chain plus hedge/forward inputs",
    ),
    "surface_market_making": StrategyPortabilitySpec(
        strategy="surface_market_making",
        family="options_liquidity_provision",
        data_requirements=("option_chain_snapshots", "futures_or_forward", "vol_surface", "explicit_fees"),
        workflow_commands=("quote-surface", "review-quotes", "replay-surface-mm", "sweep-surface-mm"),
        portable_market_types=("options", "derivatives"),
        notes="portable to US listed options after fee and contract assumptions are explicit",
    ),
    "settlement_convergence": StrategyPortabilitySpec(
        strategy="settlement_convergence",
        family="expiry_settlement_microstructure",
        data_requirements=("index_ticks", "expiring_option_chain", "india_settlement_window"),
        workflow_commands=(
            "audit-settlement-convergence",
            "walkforward-settlement-convergence",
            "promote-settlement-candidate",
            "pipeline-settlement-launch",
        ),
        portable_market_types=("derivatives",),
        india_only=True,
        requires_explicit_fee_model_outside_india=False,
        notes="India-specific running-average settlement workflow; US requires a separate settlement model",
    ),
}


def build_market_portability_report(
    config: MarketPortabilityReportConfig | None = None,
) -> MarketPortabilityReport:
    config = config or MarketPortabilityReportConfig()
    _validate_config(config)
    selected = _selected_specs(config.strategies)
    rows = []
    for market_name in config.markets:
        profile = get_market_profile(market_name)
        for spec in selected:
            rows.append(_matrix_row(spec, profile, config))
    matrix = pd.DataFrame(rows)
    gaps = _gaps(matrix)
    summary = _summary(matrix, gaps)
    report_config = _config(matrix, gaps, summary, config)
    return MarketPortabilityReport(matrix=matrix, gaps=gaps, summary=summary, config=report_config)


def write_market_portability_report(
    output_dir: str | Path,
    *,
    config: MarketPortabilityReportConfig | None = None,
) -> MarketPortabilityReport:
    config = config or MarketPortabilityReportConfig()
    report = build_market_portability_report(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.matrix.to_csv(out / "market_portability_matrix.csv", index=False)
    report.gaps.to_csv(out / "market_portability_gaps.csv", index=False)
    report.summary.to_csv(out / "market_portability_summary.csv", index=False)
    (out / "market_portability_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="market_portability_report",
        parameters={"config": asdict(config)},
        inputs={},
    )
    return MarketPortabilityReport(report.matrix, report.gaps, report.summary, out, report.config)


def _matrix_row(
    spec: StrategyPortabilitySpec,
    profile: MarketProfile,
    config: MarketPortabilityReportConfig,
) -> dict[str, object]:
    market_type = _market_type(profile)
    supported_type = market_type in spec.portable_market_types
    india = profile.country == "IN"
    fee_ready = india or (not spec.requires_explicit_fee_model_outside_india) or config.explicit_fee_model
    if spec.india_only and not india:
        status = "blocked"
        blocker = "market_microstructure_model_missing"
        next_gate = "implement_market_specific_settlement_model"
    elif not supported_type:
        status = "blocked"
        blocker = "unsupported_market_type"
        next_gate = (
            "select_options_or_derivatives_market"
            if spec.family.startswith("options")
            else "review_strategy_market_fit"
        )
    elif not fee_ready:
        status = "needs_fee_model"
        blocker = "explicit_fee_model_required"
        next_gate = "run_market_profile_report_with_fee_assumptions"
    else:
        status = "portable_research" if not india else "india_ready"
        blocker = ""
        next_gate = "run_walkforward_and_paper_shadow_gates"

    return {
        "strategy": spec.strategy,
        "family": spec.family,
        "market": profile.name,
        "country": profile.country,
        "currency": profile.currency,
        "market_type": market_type,
        "status": status,
        "supported_market_type": supported_type,
        "explicit_fee_model_ready": fee_ready,
        "default_tick": float(profile.default_tick),
        "default_lot_size": int(profile.default_lot_size),
        "data_requirements": "|".join(spec.data_requirements),
        "workflow_commands": "|".join(spec.workflow_commands),
        "blocker": blocker,
        "next_gate": next_gate,
        "notes": spec.notes,
    }


def _gaps(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame(columns=["market", "strategy", "status", "blocker", "next_gate"])
    gaps = matrix.loc[matrix["status"].isin(["blocked", "needs_fee_model"])].copy()
    return gaps[["market", "strategy", "status", "blocker", "next_gate"]].reset_index(drop=True)


def _summary(matrix: pd.DataFrame, gaps: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame(
            [
                {
                    "ready": False,
                    "markets": 0,
                    "strategies": 0,
                    "matrix_rows": 0,
                    "india_ready": 0,
                    "portable_research": 0,
                    "needs_fee_model": 0,
                    "blocked": 0,
                    "gaps": 0,
                }
            ]
        )
    status_counts = matrix["status"].value_counts()
    ready_rows = int(status_counts.get("india_ready", 0) + status_counts.get("portable_research", 0))
    return pd.DataFrame(
        [
            {
                "ready": bool(ready_rows > 0 and len(gaps) < len(matrix)),
                "markets": int(matrix["market"].nunique()),
                "strategies": int(matrix["strategy"].nunique()),
                "matrix_rows": int(len(matrix)),
                "india_ready": int(status_counts.get("india_ready", 0)),
                "portable_research": int(status_counts.get("portable_research", 0)),
                "needs_fee_model": int(status_counts.get("needs_fee_model", 0)),
                "blocked": int(status_counts.get("blocked", 0)),
                "gaps": int(len(gaps)),
            }
        ]
    )


def _config(
    matrix: pd.DataFrame,
    gaps: pd.DataFrame,
    summary: pd.DataFrame,
    report_config: MarketPortabilityReportConfig,
) -> dict[str, Any]:
    summary_row = summary.iloc[0].to_dict() if not summary.empty else {}
    ready_rows = (
        matrix.loc[matrix["status"].isin(["india_ready", "portable_research"])]
        if not matrix.empty
        else matrix
    )
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "requested_markets": list(report_config.markets),
        "requested_strategies": list(report_config.strategies) or sorted(STRATEGY_SPECS),
        "explicit_fee_model": bool(report_config.explicit_fee_model),
        "summary": _jsonable_row(summary_row),
        "ready_pairs": _pair_records(ready_rows),
        "gap_pairs": _pair_records(gaps),
        "next_gates": sorted(set(gaps["next_gate"].astype(str))) if not gaps.empty else [],
    }


def _pair_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    columns = [
        column
        for column in ("market", "strategy", "status", "blocker", "next_gate")
        if column in frame.columns
    ]
    return [_jsonable_row(row) for row in frame[columns].to_dict(orient="records")]


def _market_type(profile: MarketProfile) -> str:
    name = profile.name.lower()
    if "options" in name:
        return "options"
    if "derivatives" in name:
        return "derivatives"
    return "equity"


def _selected_specs(names: tuple[str, ...]) -> list[StrategyPortabilitySpec]:
    if not names:
        return list(STRATEGY_SPECS.values())
    return [STRATEGY_SPECS[name] for name in names]


def _validate_config(config: MarketPortabilityReportConfig) -> None:
    if not config.markets:
        raise ValueError("markets must not be empty")
    for market in config.markets:
        get_market_profile(market)
    unknown = [name for name in config.strategies if name not in STRATEGY_SPECS]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}; known strategies: {sorted(STRATEGY_SPECS)}")


def _jsonable_row(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: object) -> object:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
