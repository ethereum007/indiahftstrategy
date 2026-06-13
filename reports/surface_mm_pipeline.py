from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.proof import ProofThresholds
from reports.promotion import PromotionReport, PromotionThresholds, write_promotion_report
from reports.quote_risk import QuoteRiskReport, QuoteRiskThresholds, write_quote_risk_report
from reports.sweeps import SweepComparison, write_sweep_comparison
from strategies.run_surface_mm_sweep import SurfaceMMSweepResult, run_surface_mm_sweep
from strategies.run_surface_quotes import SurfaceQuoteRunResult, run_surface_quote_generation


SURFACE_SWEEP_GROUP_COLS = ["quote_ttl_ns", "order_latency_us", "fill_depth_fraction", "markout_horizon_ns"]


@dataclass(frozen=True)
class SurfaceMMResearchPipelineReport:
    stages: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    quotes: SurfaceQuoteRunResult | None = None
    quote_review: QuoteRiskReport | None = None
    sweep: SurfaceMMSweepResult | None = None
    selection: SweepComparison | None = None
    promotion: PromotionReport | None = None
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def write_surface_mm_research_pipeline(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path,
    data_readiness_comparison_dir: str | Path | None = None,
    require_data_readiness_comparison: bool = False,
    market_portability_dir: str | Path | None = None,
    require_market_portability: bool = False,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    asof_latency_ns: int = 0,
    tte_years: float = 30 / 365,
    tick_size: float = 0.05,
    lot_size: int = 75,
    quote_lots: int = 1,
    edge_ticks: float = 2.0,
    inventory_skew_ticks_per_lot: float = 0.5,
    max_market_spread_ticks: float | None = None,
    max_quotes_per_snapshot: int | None = None,
    max_snapshots: int | None = None,
    quote_risk_thresholds: QuoteRiskThresholds | None = None,
    quote_ttl_ns_values: list[int],
    order_latency_us_values: list[float],
    fill_depth_fraction_values: list[float],
    markout_horizon_ns_values: list[int],
    contract_multiplier: float = 1.0,
    max_quotes: int | None = None,
    proof_thresholds: ProofThresholds | None = None,
    min_selection_pass_rate: float = 1.0,
    min_selection_sweeps: int = 1,
    min_selection_median_net_pnl: float = 0.0,
    max_selection_worst_drawdown: float | None = None,
    promotion_thresholds: PromotionThresholds | None = None,
) -> SurfaceMMResearchPipelineReport:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    quotes_dir = out / "01_quotes"
    quote_review_dir = out / "02_quote_review"
    sweep_dir = out / "03_sweep"
    selection_dir = out / "04_selection"
    promotion_dir = out / "05_promotion"

    quote_risk_thresholds = quote_risk_thresholds or QuoteRiskThresholds()
    proof_thresholds = proof_thresholds or ProofThresholds()
    promotion_thresholds = promotion_thresholds or PromotionThresholds()
    market_portability_config = _read_market_portability_config(market_portability_dir)
    portability_stage = _market_portability_stage(
        market_portability_config,
        required=require_market_portability,
        input_dir=market_portability_dir,
        expected_market=market,
    )
    parameters = _parameters(
        market=market,
        require_market_portability=require_market_portability,
        require_data_readiness_comparison=require_data_readiness_comparison,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        asof_latency_ns=asof_latency_ns,
        tte_years=tte_years,
        tick_size=tick_size,
        lot_size=lot_size,
        quote_lots=quote_lots,
        edge_ticks=edge_ticks,
        inventory_skew_ticks_per_lot=inventory_skew_ticks_per_lot,
        max_market_spread_ticks=max_market_spread_ticks,
        max_quotes_per_snapshot=max_quotes_per_snapshot,
        max_snapshots=max_snapshots,
        quote_risk_thresholds=quote_risk_thresholds,
        quote_ttl_ns_values=quote_ttl_ns_values,
        order_latency_us_values=order_latency_us_values,
        fill_depth_fraction_values=fill_depth_fraction_values,
        markout_horizon_ns_values=markout_horizon_ns_values,
        contract_multiplier=contract_multiplier,
        max_quotes=max_quotes,
        proof_thresholds=proof_thresholds,
        min_selection_pass_rate=min_selection_pass_rate,
        min_selection_sweeps=min_selection_sweeps,
        min_selection_median_net_pnl=min_selection_median_net_pnl,
        max_selection_worst_drawdown=max_selection_worst_drawdown,
        promotion_thresholds=promotion_thresholds,
    )
    if portability_stage is not None and not bool(portability_stage["status"]):
        return _write_pipeline_outputs(
            output_dir=out,
            quotes=None,
            quote_review=None,
            sweep=None,
            selection=None,
            promotion=None,
            candidate_config=_blocked_candidate_config("market_portability"),
            chain_path=Path(chain_path),
            futures_path=Path(futures_path),
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
            parameters=parameters,
            portability_stage=portability_stage,
            blocked_reason="market_portability_not_ready",
        )

    quotes = run_surface_quote_generation(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=quotes_dir,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
        asof_latency_ns=asof_latency_ns,
        tte_years=tte_years,
        tick_size=tick_size,
        lot_size=lot_size,
        quote_lots=quote_lots,
        edge_ticks=edge_ticks,
        inventory_skew_ticks_per_lot=inventory_skew_ticks_per_lot,
        max_market_spread_ticks=max_market_spread_ticks,
        max_quotes_per_snapshot=max_quotes_per_snapshot,
        max_snapshots=max_snapshots,
    )
    quote_review = write_quote_risk_report(
        quotes_dir / "surface_quotes.csv",
        output_dir=quote_review_dir,
        thresholds=quote_risk_thresholds,
        data_readiness_comparison_dir=data_readiness_comparison_dir,
        require_data_readiness_comparison=require_data_readiness_comparison,
    )
    if not quote_review.passed:
        return _write_pipeline_outputs(
            output_dir=out,
            quotes=quotes,
            quote_review=quote_review,
            sweep=None,
            selection=None,
            promotion=None,
            candidate_config=_blocked_candidate_config("quote_review"),
            chain_path=Path(chain_path),
            futures_path=Path(futures_path),
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
            parameters=parameters,
            portability_stage=portability_stage,
        )

    sweep = run_surface_mm_sweep(
        quotes_path=quotes_dir / "surface_quotes.csv",
        chain_path=chain_path,
        output_dir=sweep_dir,
        quote_ttl_ns_values=quote_ttl_ns_values,
        order_latency_us_values=order_latency_us_values,
        fill_depth_fraction_values=fill_depth_fraction_values,
        markout_horizon_ns_values=markout_horizon_ns_values,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
        lot_size=lot_size,
        option_tick=tick_size,
        contract_multiplier=contract_multiplier,
        max_quotes=max_quotes,
        proof_thresholds=proof_thresholds,
        quote_risk_review_dir=quote_review_dir,
        require_quote_risk_review=True,
    )
    if not sweep.proof.passed:
        return _write_pipeline_outputs(
            output_dir=out,
            quotes=quotes,
            quote_review=quote_review,
            sweep=sweep,
            selection=None,
            promotion=None,
            candidate_config=_blocked_candidate_config("sweep"),
            chain_path=Path(chain_path),
            futures_path=Path(futures_path),
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
            parameters=parameters,
            portability_stage=portability_stage,
        )

    selection = write_sweep_comparison(
        [sweep_dir],
        output_dir=selection_dir,
        labels=["surface_mm"],
        group_cols=SURFACE_SWEEP_GROUP_COLS,
        min_pass_rate=min_selection_pass_rate,
        min_sweeps=min_selection_sweeps,
        min_median_net_pnl=min_selection_median_net_pnl,
        max_worst_drawdown=max_selection_worst_drawdown,
    )
    if not selection.has_selection:
        return _write_pipeline_outputs(
            output_dir=out,
            quotes=quotes,
            quote_review=quote_review,
            sweep=sweep,
            selection=selection,
            promotion=None,
            candidate_config=_blocked_candidate_config("selection"),
            chain_path=Path(chain_path),
            futures_path=Path(futures_path),
            data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
            if data_readiness_comparison_dir is not None
            else None,
            market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
            parameters=parameters,
            portability_stage=portability_stage,
        )

    promotion = write_promotion_report(
        selection_dir,
        output_dir=promotion_dir,
        thresholds=promotion_thresholds,
    )
    return _write_pipeline_outputs(
        output_dir=out,
        quotes=quotes,
        quote_review=quote_review,
        sweep=sweep,
        selection=selection,
        promotion=promotion,
        candidate_config=_promotion_candidate_config(promotion_dir, promotion),
        chain_path=Path(chain_path),
        futures_path=Path(futures_path),
        data_readiness_comparison_dir=Path(data_readiness_comparison_dir)
        if data_readiness_comparison_dir is not None
        else None,
        market_portability_dir=Path(market_portability_dir) if market_portability_dir is not None else None,
        parameters=parameters,
        portability_stage=portability_stage,
    )


def _write_pipeline_outputs(
    *,
    output_dir: Path,
    quotes: SurfaceQuoteRunResult | None,
    quote_review: QuoteRiskReport | None,
    sweep: SurfaceMMSweepResult | None,
    selection: SweepComparison | None,
    promotion: PromotionReport | None,
    candidate_config: dict[str, Any],
    chain_path: Path,
    futures_path: Path,
    data_readiness_comparison_dir: Path | None,
    parameters: dict[str, Any],
    market_portability_dir: Path | None = None,
    portability_stage: dict[str, Any] | None = None,
    blocked_reason: str = "preflight_not_ready",
) -> SurfaceMMResearchPipelineReport:
    stages = _stages(
        quotes,
        quote_review,
        sweep,
        selection,
        promotion,
        portability_stage=portability_stage,
        blocked_reason=blocked_reason,
    )
    summary = _summary(stages, quotes, quote_review, sweep, selection, promotion)
    config = _candidate_config(candidate_config, summary.iloc[0], stages)
    stages.to_csv(output_dir / "surface_mm_pipeline_stages.csv", index=False)
    summary.to_csv(output_dir / "surface_mm_pipeline_summary.csv", index=False)
    (output_dir / "candidate_config.json").write_text(
        json.dumps(_jsonable(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        output_dir,
        run_type="surface_mm_research_pipeline",
        parameters=parameters,
        inputs={
            "chain": chain_path,
            "futures": futures_path,
            "quotes": output_dir / "01_quotes",
            "quote_review": output_dir / "02_quote_review",
            "sweep": output_dir / "03_sweep",
            "selection": output_dir / "04_selection",
            "promotion": output_dir / "05_promotion",
            "data_readiness_comparison": data_readiness_comparison_dir,
            "market_portability": market_portability_dir,
        },
    )
    return SurfaceMMResearchPipelineReport(
        stages=stages,
        summary=summary,
        candidate_config=config,
        quotes=quotes,
        quote_review=quote_review,
        sweep=sweep,
        selection=selection,
        promotion=promotion,
        output_dir=output_dir,
    )


def _stages(
    quotes: SurfaceQuoteRunResult | None,
    quote_review: QuoteRiskReport | None,
    sweep: SurfaceMMSweepResult | None,
    selection: SweepComparison | None,
    promotion: PromotionReport | None,
    *,
    portability_stage: dict[str, Any] | None = None,
    blocked_reason: str = "preflight_not_ready",
) -> pd.DataFrame:
    rows = []
    if portability_stage is not None:
        rows.append(portability_stage)
    rows.extend(
        [
            _quote_stage(quotes) if quotes is not None else _skipped_stage("quote_generation", blocked_reason),
            _stage_row("quote_review", quote_review.output_dir, quote_review.summary, "all_passed")
            if quote_review is not None
            else _skipped_stage("quote_review", "quote_generation_not_ready"),
            _sweep_stage(sweep) if sweep is not None else _skipped_stage("sweep", "quote_review_not_ready"),
            _selection_stage(selection) if selection is not None else _skipped_stage("selection", "sweep_not_ready"),
            _stage_row("promotion", promotion.output_dir, promotion.summary, "ready")
            if promotion is not None
            else _skipped_stage("promotion", "selection_not_ready"),
        ]
    )
    return pd.DataFrame(rows)


def _quote_stage(quotes: SurfaceQuoteRunResult) -> dict[str, Any]:
    row = quotes.summary.iloc[0] if not quotes.summary.empty else pd.Series(dtype=object)
    quote_count = _int(row, "quotes")
    return {
        "stage": "quote_generation",
        "status": quote_count > 0,
        "status_column": "quotes",
        "skipped": False,
        "output_dir": str(quotes.output_dir or ""),
        "failed_checks": 0 if quote_count > 0 else 1,
        "recommendation": "quotes_generated" if quote_count > 0 else "no_surface_quotes_generated",
    }


def _sweep_stage(sweep: SurfaceMMSweepResult) -> dict[str, Any]:
    row = sweep.summary.iloc[0] if not sweep.summary.empty else pd.Series(dtype=object)
    return {
        "stage": "sweep",
        "status": bool(sweep.proof.passed),
        "status_column": "proof.all_passed",
        "skipped": False,
        "output_dir": str(sweep.output_dir or ""),
        "failed_checks": 0 if sweep.proof.passed else 1,
        "recommendation": "proof_passed" if sweep.proof.passed else str(row.get("quote_risk_review_reason", "proof_failed")),
    }


def _selection_stage(selection: SweepComparison) -> dict[str, Any]:
    row = selection.summary.iloc[0] if not selection.summary.empty else pd.Series(dtype=object)
    status = bool(selection.has_selection)
    return {
        "stage": "selection",
        "status": status,
        "status_column": "selectable_scenarios",
        "skipped": False,
        "output_dir": str(selection.output_dir or ""),
        "failed_checks": 0 if status else 1,
        "recommendation": "scenario_selected" if status else "no_selectable_scenario",
        "selectable_scenarios": _int(row, "selectable_scenarios"),
    }


def _stage_row(stage: str, output_dir: Path | None, summary: pd.DataFrame, status_column: str) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    status = _to_bool(row.get(status_column, False))
    return {
        "stage": stage,
        "status": status,
        "status_column": status_column,
        "skipped": False,
        "output_dir": str(output_dir or ""),
        "failed_checks": _int(row, "failed_checks"),
        "recommendation": str(row.get("recommendation", "")),
    }


def _skipped_stage(stage: str, reason: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": False,
        "status_column": "",
        "skipped": True,
        "output_dir": "",
        "failed_checks": 1,
        "recommendation": reason,
    }


def _summary(
    stages: pd.DataFrame,
    quotes: SurfaceQuoteRunResult | None,
    quote_review: QuoteRiskReport | None,
    sweep: SurfaceMMSweepResult | None,
    selection: SweepComparison | None,
    promotion: PromotionReport | None,
) -> pd.DataFrame:
    ready = bool(stages["status"].map(_to_bool).all()) if not stages.empty else False
    quote_row = quotes.summary.iloc[0] if quotes is not None and not quotes.summary.empty else pd.Series(dtype=object)
    review_row = (
        quote_review.summary.iloc[0]
        if quote_review is not None and not quote_review.summary.empty
        else pd.Series(dtype=object)
    )
    sweep_row = sweep.summary.iloc[0] if sweep is not None and not sweep.summary.empty else pd.Series(dtype=object)
    selection_row = (
        selection.summary.iloc[0] if selection is not None and not selection.summary.empty else pd.Series(dtype=object)
    )
    promotion_row = (
        promotion.summary.iloc[0] if promotion is not None and not promotion.summary.empty else pd.Series(dtype=object)
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_stages": int((~stages["status"].map(_to_bool)).sum()) if not stages.empty else 0,
                "skipped_stages": int(stages["skipped"].map(_to_bool).sum()) if not stages.empty else 0,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_researching",
                "quote_generation_passed": quotes is not None and _int(quote_row, "quotes") > 0,
                "quote_review_passed": bool(quote_review.passed) if quote_review is not None else False,
                "sweep_proof_passed": bool(sweep.proof.passed) if sweep is not None else False,
                "selection_has_scenario": bool(selection.has_selection) if selection is not None else False,
                "promotion_ready": bool(promotion.ready) if promotion is not None else False,
                "candidate_scenario_key": str(promotion_row.get("candidate_scenario_key", "")),
                "quotes": _int(quote_row, "quotes"),
                "marketable_quotes": _int(review_row, "marketable_quotes"),
                "sweep_scenarios": _int(sweep_row, "scenario_count"),
                "sweep_pass_rate": _float(sweep_row, "pass_rate"),
                "selectable_scenarios": _int(selection_row, "selectable_scenarios"),
            }
        ]
    )


def _read_market_portability_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "market_portability_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"market portability config not found: {candidate}")
    return json.loads(candidate.read_text(encoding="utf-8"))


def _market_portability_stage(
    config: dict[str, Any],
    *,
    required: bool,
    input_dir: str | Path | None,
    expected_market: str,
) -> dict[str, Any] | None:
    if not config and not required:
        return None
    provided = bool(config)
    pair = _matching_portability_pair(config, expected_market) if provided else {}
    status = bool(pair)
    reason = "ready" if status else "market_portability_missing"
    if provided and not status:
        reason = _matching_portability_gap(config, expected_market).get(
            "next_gate",
            "market_portability_pair_not_ready",
        )
    return {
        "stage": "market_portability",
        "status": bool(status),
        "status_column": "ready_pairs",
        "skipped": False,
        "output_dir": str(input_dir or ""),
        "failed_checks": 0 if status else 1,
        "recommendation": reason,
    }


def _matching_portability_pair(config: dict[str, Any], expected_market: str) -> dict[str, Any]:
    expected = _identity(expected_market)
    for pair in config.get("ready_pairs") or []:
        if _identity(pair.get("strategy")) != "surface_market_making":
            continue
        if _identity(pair.get("market")) != expected:
            continue
        if str(pair.get("status", "")).strip().lower() in {"india_ready", "portable_research"}:
            return dict(pair)
    return {}


def _matching_portability_gap(config: dict[str, Any], expected_market: str) -> dict[str, Any]:
    expected = _identity(expected_market)
    for pair in config.get("gap_pairs") or []:
        if _identity(pair.get("strategy")) == "surface_market_making" and _identity(pair.get("market")) == expected:
            return dict(pair)
    return {}


def _promotion_candidate_config(path: Path, promotion: PromotionReport) -> dict[str, Any]:
    config_path = path / "candidate_config.json"
    if not config_path.exists():
        return _blocked_candidate_config("promotion")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["ready"] = bool(promotion.ready)
    return config


def _candidate_config(source: dict[str, Any], summary: pd.Series, stages: pd.DataFrame) -> dict[str, Any]:
    config = dict(source)
    config["schema_version"] = int(config.get("schema_version", 1))
    config["ready"] = _to_bool(summary.get("ready", False))
    config["strategy"] = "surface_mm"
    config["source_run_type"] = "surface_mm_research_pipeline"
    failed = list(config.get("failed_checks", []) or [])
    failed.extend(stages.loc[~stages["status"].map(_to_bool), "stage"].astype(str).tolist())
    config["failed_checks"] = list(dict.fromkeys(failed))
    config["pipeline"] = {
        "ready": _jsonable(summary.get("ready")),
        "failed_stages": _jsonable(summary.get("failed_stages")),
        "recommendation": _jsonable(summary.get("recommendation")),
        "stages": [
            {
                "stage": str(row.stage),
                "status": bool(row.status),
                "skipped": bool(row.skipped),
                "recommendation": str(row.recommendation),
            }
            for row in stages.itertuples(index=False)
        ],
    }
    return config


def _blocked_candidate_config(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": False,
        "strategy": "surface_mm",
        "failed_checks": [reason],
        "parameters": {},
        "metrics": {},
        "recommendation": "keep_researching",
    }


def _parameters(**values: Any) -> dict[str, Any]:
    return {
        key: asdict(value) if hasattr(value, "__dataclass_fields__") else value
        for key, value in values.items()
    }


def _float(row: pd.Series, column: str) -> float:
    try:
        return float(row.get(column, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _int(row: pd.Series, column: str) -> int:
    try:
        return int(float(row.get(column, 0)))
    except (TypeError, ValueError):
        return 0


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _identity(value: object) -> str:
    if value is None:
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
