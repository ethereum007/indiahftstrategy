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
    evidence_profile: str
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
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


STRATEGY_SPECS: dict[str, StrategyPortabilitySpec] = {
    "microprice_imbalance": StrategyPortabilitySpec(
        strategy="microprice_imbalance",
        family="single_instrument_tob",
        evidence_profile="imbalance",
        data_requirements=("top_of_book_ticks", "forward_mid_labels", "explicit_fees"),
        workflow_commands=(
            "walkforward-imbalance-edge",
            "walkforward-imbalance-replay",
            "promote-imbalance-candidate",
            "pipeline-imbalance-research",
            "plan-imbalance-orders",
            "pipeline-imbalance-launch",
        ),
        portable_market_types=("equity", "options", "derivatives"),
        notes="portable when session profile, tick size, lot size, and fee model are explicit",
    ),
    "lead_lag_taker": StrategyPortabilitySpec(
        strategy="lead_lag_taker",
        family="cross_instrument_latency",
        evidence_profile="leadlag",
        data_requirements=("paired_top_of_book_ticks", "lead_lag_measurement", "explicit_fees"),
        workflow_commands=(
            "measure-leadlag",
            "audit-leadlag-edge",
            "walkforward-leadlag-replay",
            "promote-leadlag-candidate",
            "plan-leadlag-orders",
            "pipeline-leadlag-launch",
        ),
        portable_market_types=("equity", "options", "derivatives"),
        notes="portable to US pairs once paired feeds share a normalized clock",
    ),
    "parity_box": StrategyPortabilitySpec(
        strategy="parity_box",
        family="options_relative_value",
        evidence_profile="parity",
        data_requirements=("option_chain_snapshots", "futures_or_forward", "explicit_fees"),
        workflow_commands=(
            "scan-parity-box",
            "audit-parity-edge",
            "replay-parity",
            "sweep-parity",
            "promote-parity-candidate",
            "plan-parity-orders",
            "pipeline-parity-launch",
        ),
        portable_market_types=("options", "derivatives"),
        notes="portable to option markets with executable chain plus hedge/forward inputs",
    ),
    "surface_market_making": StrategyPortabilitySpec(
        strategy="surface_market_making",
        family="options_liquidity_provision",
        evidence_profile="surface_mm",
        data_requirements=("option_chain_snapshots", "futures_or_forward", "vol_surface", "explicit_fees"),
        workflow_commands=(
            "quote-surface",
            "review-quotes",
            "replay-surface-mm",
            "sweep-surface-mm",
            "pipeline-surface-mm-research",
            "pipeline-surface-mm-launch",
        ),
        portable_market_types=("options", "derivatives"),
        notes="portable to US listed options after fee and contract assumptions are explicit",
    ),
    "settlement_convergence": StrategyPortabilitySpec(
        strategy="settlement_convergence",
        family="expiry_settlement_microstructure",
        evidence_profile="settlement",
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

_PAIR_COLUMNS = (
    "market",
    "strategy",
    "status",
    "blocker",
    "next_gate",
    "strategy_evidence_profile",
    "strategy_evidence_gate",
    "ops_evidence_profile",
    "ops_evidence_gate",
    "next_gate_help_command",
)


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
    action_queue = _action_queue(matrix)
    summary = _summary(matrix, gaps, action_queue)
    report_config = _config(matrix, gaps, summary, action_queue, config)
    return MarketPortabilityReport(
        matrix=matrix,
        gaps=gaps,
        summary=summary,
        config=report_config,
        action_queue=action_queue,
    )


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
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.matrix)
    action_queue.to_csv(out / "market_portability_action_queue.csv", index=False)
    (out / "market_portability_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.matrix, report.gaps, action_queue),
        encoding="utf-8",
    )
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
    return MarketPortabilityReport(report.matrix, report.gaps, report.summary, out, report.config, action_queue)


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
        "strategy_evidence_profile": spec.evidence_profile,
        "strategy_evidence_gate": f"review-strategy-evidence --profile {spec.evidence_profile}",
        "ops_evidence_profile": "ops_launch",
        "ops_evidence_gate": "review-strategy-evidence --profile ops_launch --require-file-inputs",
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
        "next_gate_help_command": _next_gate_help_command(next_gate),
        "notes": spec.notes,
    }


def _gaps(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame(columns=_PAIR_COLUMNS)
    gaps = matrix.loc[matrix["status"].isin(["blocked", "needs_fee_model"])].copy()
    return gaps[[column for column in _PAIR_COLUMNS if column in gaps.columns]].reset_index(drop=True)


def _summary(matrix: pd.DataFrame, gaps: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
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
                    "ready_action_count": 0,
                    "blocked_action_count": 0,
                    "next_gate": "",
                    "next_gate_help_command": "",
                    "recommendation": "market_portability_inputs_missing",
                }
            ]
        )
    status_counts = matrix["status"].value_counts()
    ready_rows = int(status_counts.get("india_ready", 0) + status_counts.get("portable_research", 0))
    next_gate = _primary_next_gate(matrix, gaps)
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
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum())
                if not action_queue.empty
                else 0,
                "blocked_action_count": int((action_queue["queue_status"].astype(str) == "blocked").sum())
                if not action_queue.empty
                else 0,
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
                "recommendation": _summary_recommendation(ready_rows, len(gaps)),
            }
        ]
    )


def _config(
    matrix: pd.DataFrame,
    gaps: pd.DataFrame,
    summary: pd.DataFrame,
    action_queue: pd.DataFrame,
    report_config: MarketPortabilityReportConfig,
) -> dict[str, Any]:
    summary_row = summary.iloc[0].to_dict() if not summary.empty else {}
    ready_rows = (
        matrix.loc[matrix["status"].isin(["india_ready", "portable_research"])]
        if not matrix.empty
        else matrix
    )
    primary_action = _first_action_record(action_queue)
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
        "ready_action_count": int(summary_row.get("ready_action_count", 0) or 0),
        "blocked_action_count": int(summary_row.get("blocked_action_count", 0) or 0),
        "next_gate": _text(summary_row.get("next_gate")),
        "next_gate_help_command": _text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(
            action_queue.loc[action_queue["queue_status"].astype(str) == "ready"]
            if not action_queue.empty
            else action_queue
        ),
        "blocked_actions": _action_records(
            action_queue.loc[action_queue["queue_status"].astype(str) == "blocked"]
            if not action_queue.empty
            else action_queue
        ),
    }


def _first_action_record(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return _jsonable_row(frame.iloc[0].to_dict())


def _pair_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    columns = [column for column in _PAIR_COLUMNS if column in frame.columns]
    return [_jsonable_row(row) for row in frame[columns].to_dict(orient="records")]


def _action_queue(matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not matrix.empty:
        ordered = matrix.copy()
        ordered["_queue_rank"] = (
            ordered["status"]
            .map({"india_ready": 0, "portable_research": 0, "needs_fee_model": 1, "blocked": 2})
            .fillna(3)
        )
        ordered = ordered.sort_values(["_queue_rank", "strategy", "market"]).drop(columns=["_queue_rank"])
        for priority, row in enumerate(ordered.to_dict(orient="records"), start=1):
            status = _text(row.get("status"))
            ready = status in {"india_ready", "portable_research"}
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "ready" if ready else "blocked",
                    "strategy": _text(row.get("strategy")),
                    "family": _text(row.get("family")),
                    "market": _text(row.get("market")),
                    "market_type": _text(row.get("market_type")),
                    "status": status,
                    "blocker": _text(row.get("blocker")),
                    "next_gate": _text(row.get("next_gate")),
                    "next_gate_help_command": _text(row.get("next_gate_help_command")),
                    "strategy_evidence_profile": _text(row.get("strategy_evidence_profile")),
                    "strategy_evidence_gate": _text(row.get("strategy_evidence_gate")),
                    "ops_evidence_gate": _text(row.get("ops_evidence_gate")),
                    "data_requirements": _text(row.get("data_requirements")),
                    "workflow_commands": _text(row.get("workflow_commands")),
                    "recommendation": _action_recommendation(row),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "strategy",
            "family",
            "market",
            "market_type",
            "status",
            "blocker",
            "next_gate",
            "next_gate_help_command",
            "strategy_evidence_profile",
            "strategy_evidence_gate",
            "ops_evidence_gate",
            "data_requirements",
            "workflow_commands",
            "recommendation",
        ],
    )


def _action_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [_jsonable_row(row) for row in frame.to_dict(orient="records")]


def _primary_next_gate(matrix: pd.DataFrame, gaps: pd.DataFrame) -> str:
    if not gaps.empty:
        return _text(gaps.iloc[0].get("next_gate"))
    ready = matrix.loc[matrix["status"].isin(["india_ready", "portable_research"])] if not matrix.empty else matrix
    if not ready.empty:
        return _text(ready.iloc[0].get("next_gate"))
    return ""


def _summary_recommendation(ready_rows: int, gap_count: int) -> str:
    if ready_rows > 0 and gap_count == 0:
        return "advance_ready_pairs_to_strategy_and_route_evidence"
    if ready_rows > 0 and gap_count > 0:
        return "advance_ready_pairs_and_resolve_portability_gaps"
    if gap_count > 0:
        return "resolve_portability_gaps"
    return "market_portability_inputs_missing"


def _action_recommendation(row: dict[str, object]) -> str:
    status = _text(row.get("status"))
    blocker = _text(row.get("blocker"))
    if status in {"india_ready", "portable_research"}:
        return "run_strategy_walkforward_and_route_readiness_gates"
    if status == "needs_fee_model":
        return "rerun_market_portability_with_explicit_fee_model"
    if blocker == "market_microstructure_model_missing":
        return "implement_market_specific_settlement_model"
    if blocker == "unsupported_market_type":
        return "select_supported_market_or_strategy"
    return "resolve_market_portability_gap"


def _next_gate_help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    if not gate or gate in {"run_walkforward_and_paper_shadow_gates", "implement_market_specific_settlement_model"}:
        return ""
    if gate in {
        "run_market_profile_report_with_fee_assumptions",
        "select_options_or_derivatives_market",
        "review_strategy_market_fit",
    }:
        return "python -m hft_cli market-portability-report --help"
    return ""


def _runbook_markdown(
    summary_row: pd.Series,
    matrix: pd.DataFrame,
    gaps: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Market Portability Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Recommendation: {_text(summary_row.get('recommendation'))}",
        f"- Ready actions: {int(_number(summary_row.get('ready_action_count', 0)))}",
        f"- Blocked actions: {int(_number(summary_row.get('blocked_action_count', 0)))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Action Queue",
        "",
        _action_queue_table(action_queue),
        "",
        "## Matrix",
        "",
        _matrix_table(matrix),
        "",
        "## Gaps",
        "",
        _matrix_table(gaps),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Status", "Strategy", "Market", "Next gate", "Help", "Recommendation"],
        [
            [
                str(int(_number(row.get("priority", 0)))),
                _text(row.get("queue_status")),
                _text(row.get("strategy")),
                _text(row.get("market")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _matrix_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_None_"
    return _markdown_table(
        ["Strategy", "Market", "Status", "Blocker", "Next gate"],
        [
            [
                _text(row.get("strategy")),
                _text(row.get("market")),
                _text(row.get("status")),
                _text(row.get("blocker")),
                _code(row.get("next_gate")),
            ]
            for row in frame.to_dict(orient="records")
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _number(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    try:
        if pd.isna(number):
            return 0
    except (TypeError, ValueError):
        pass
    return int(number)


def _to_bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


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
