from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class StrategyPortfolioConfig:
    total_capital: float = 1_000_000.0
    capital_currency: str = "INR"
    reserve_weight: float = 0.10
    max_profile_weight: float = 0.40
    min_readiness_score: float = 1.0
    require_ready: bool = True
    include_profiles: tuple[str, ...] = ()
    exclude_profiles: tuple[str, ...] = ()
    allocation_mode: str = "readiness_weighted"
    deployment_mode: str = "paper_shadow"


@dataclass(frozen=True)
class StrategyPortfolioReport:
    allocations: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_strategy_portfolio(
    scorecard: pd.DataFrame,
    *,
    config: StrategyPortfolioConfig | None = None,
) -> StrategyPortfolioReport:
    config = config or StrategyPortfolioConfig()
    normalized = _normalize_scorecard(scorecard)
    allocations = _allocations(normalized, config)
    checks = _checks(allocations, config)
    summary = _summary(allocations, checks, config)
    payload = _config(allocations, checks, summary, config)
    return StrategyPortfolioReport(allocations=allocations, checks=checks, summary=summary, config=payload)


def write_strategy_portfolio_allocations(
    scorecard_path: str | Path,
    *,
    output_dir: str | Path,
    config: StrategyPortfolioConfig | None = None,
) -> StrategyPortfolioReport:
    scorecard_file = _scorecard_path(scorecard_path)
    scorecard = pd.read_csv(scorecard_file)
    config = config or StrategyPortfolioConfig()
    report = evaluate_strategy_portfolio(scorecard, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.allocations.to_csv(out / "strategy_portfolio_allocations.csv", index=False)
    report.checks.to_csv(out / "strategy_portfolio_checks.csv", index=False)
    report.summary.to_csv(out / "strategy_portfolio_summary.csv", index=False)
    (out / "strategy_portfolio_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "strategy_portfolio_runbook.md").write_text(
        _runbook_markdown(report.config),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="strategy_portfolio_allocation",
        parameters={"allocation": asdict(config)},
        inputs={"strategy_scorecard": scorecard_file},
    )
    return StrategyPortfolioReport(report.allocations, report.checks, report.summary, report.config, out)


def _normalize_scorecard(scorecard: pd.DataFrame) -> pd.DataFrame:
    defaults: dict[str, Any] = {
        "rank": 0,
        "profile": "",
        "strategy": "",
        "market": "",
        "ready": False,
        "readiness_score": 0.0,
        "passed_required_run_types": 0,
        "required_run_type_count": 0,
        "next_required_run_type": "",
        "next_gate": "",
        "next_gate_help_command": "",
        "recommendation": "",
    }
    frame = scorecard.copy()
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
    if frame.empty:
        return frame.loc[:, list(defaults)].copy()
    frame = frame.loc[:, list(defaults)].copy()
    frame["rank"] = frame["rank"].map(_integer)
    missing_rank = frame["rank"] <= 0
    if bool(missing_rank.any()):
        frame.loc[missing_rank, "rank"] = np.arange(1, int(missing_rank.sum()) + 1, dtype=int)
    frame["profile"] = frame["profile"].map(_text)
    frame["strategy"] = frame["strategy"].map(_text)
    frame["market"] = frame["market"].map(_text)
    frame["ready"] = frame["ready"].map(_bool)
    frame["readiness_score"] = frame["readiness_score"].map(_numeric)
    frame["passed_required_run_types"] = frame["passed_required_run_types"].map(_integer)
    frame["required_run_type_count"] = frame["required_run_type_count"].map(_integer)
    frame["next_required_run_type"] = frame["next_required_run_type"].map(_text)
    frame["next_gate"] = frame["next_gate"].map(_text)
    frame["next_gate_help_command"] = frame["next_gate_help_command"].map(_text)
    frame["recommendation"] = frame["recommendation"].map(_text)
    return frame.sort_values(["rank", "profile"]).reset_index(drop=True)


def _allocations(scorecard: pd.DataFrame, config: StrategyPortfolioConfig) -> pd.DataFrame:
    frame = scorecard.copy()
    include_profiles = {_profile_key(profile) for profile in config.include_profiles if _text(profile)}
    exclude_profiles = {_profile_key(profile) for profile in config.exclude_profiles if _text(profile)}
    frame["eligible"] = [
        _eligible(row, config, include_profiles=include_profiles, exclude_profiles=exclude_profiles)
        for _, row in frame.iterrows()
    ]
    frame["eligibility_reason"] = [
        _eligibility_reason(row, config, include_profiles=include_profiles, exclude_profiles=exclude_profiles)
        for _, row in frame.iterrows()
    ]
    frame["allocation_score"] = [
        _allocation_score(row) if bool(row.get("eligible", False)) else 0.0 for _, row in frame.iterrows()
    ]
    weights = _capped_weights(
        frame.loc[frame["eligible"].astype(bool), "allocation_score"],
        deployable_weight=_deployable_weight(config),
        max_profile_weight=_bounded_max_weight(config),
    )
    frame["allocation_weight"] = [float(weights.get(index, 0.0)) for index in frame.index]
    frame["allocation_notional"] = frame["allocation_weight"].map(lambda weight: weight * max(_numeric(config.total_capital), 0.0))
    frame["reserve_weight"] = _bounded_reserve_weight(config)
    frame["max_profile_weight"] = _bounded_max_weight(config)
    frame["capital_currency"] = _text(config.capital_currency)
    frame["deployment_mode"] = _text(config.deployment_mode)
    frame["allocation_mode"] = _text(config.allocation_mode)
    return frame[
        [
            "rank",
            "profile",
            "strategy",
            "market",
            "ready",
            "readiness_score",
            "passed_required_run_types",
            "required_run_type_count",
            "eligible",
            "eligibility_reason",
            "allocation_score",
            "allocation_weight",
            "allocation_notional",
            "reserve_weight",
            "max_profile_weight",
            "capital_currency",
            "deployment_mode",
            "allocation_mode",
            "next_required_run_type",
            "next_gate",
            "next_gate_help_command",
            "recommendation",
        ]
    ]


def _checks(allocations: pd.DataFrame, config: StrategyPortfolioConfig) -> pd.DataFrame:
    eligible_count = int(allocations["eligible"].astype(bool).sum()) if not allocations.empty else 0
    allocated_weight = float(allocations["allocation_weight"].sum()) if not allocations.empty else 0.0
    deployable_weight = _deployable_weight(config)
    rows = [
        _check(
            "total_capital_positive",
            _numeric(config.total_capital) > 0.0,
            _numeric(config.total_capital),
            ">",
            0.0,
            "total capital must be positive before creating a paper allocation",
        ),
        _check(
            "reserve_weight_between_0_and_1",
            0.0 <= _numeric(config.reserve_weight) <= 1.0,
            _numeric(config.reserve_weight),
            "between",
            "0..1",
            "reserve weight must be between 0 and 1",
        ),
        _check(
            "max_profile_weight_between_0_and_1",
            0.0 < _numeric(config.max_profile_weight) <= 1.0,
            _numeric(config.max_profile_weight),
            "between",
            "(0..1]",
            "max profile weight must be greater than 0 and no more than 1",
        ),
        _check(
            "min_readiness_score_between_0_and_1",
            0.0 <= _numeric(config.min_readiness_score) <= 1.0,
            _numeric(config.min_readiness_score),
            "between",
            "0..1",
            "minimum readiness score must be between 0 and 1",
        ),
        _check(
            "allocation_mode_supported",
            config.allocation_mode == "readiness_weighted",
            _text(config.allocation_mode),
            "is",
            "readiness_weighted",
            "only readiness-weighted paper allocation is supported",
        ),
        _check(
            "eligible_profile_count",
            eligible_count > 0,
            eligible_count,
            ">",
            0,
            "at least one strategy profile must pass readiness filters before allocation",
        ),
        _check(
            "allocated_weight_positive",
            allocated_weight > 0.0,
            allocated_weight,
            ">",
            0.0,
            "allocated weight must be positive after reserve and profile caps",
        ),
        _check(
            "allocated_weight_lte_deployable",
            allocated_weight <= deployable_weight + 1e-9,
            allocated_weight,
            "<=",
            deployable_weight,
            "allocated weight must not exceed the deployable budget",
        ),
    ]
    return pd.DataFrame(rows)


def _summary(allocations: pd.DataFrame, checks: pd.DataFrame, config: StrategyPortfolioConfig) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    primary = failed.iloc[0].to_dict() if not failed.empty else {}
    allocated = allocations.loc[allocations["allocation_weight"] > 0.0] if not allocations.empty else pd.DataFrame()
    top = _top_allocation(allocated)
    total_capital = max(_numeric(config.total_capital), 0.0)
    allocated_weight = float(allocations["allocation_weight"].sum()) if not allocations.empty else 0.0
    reserve_weight = _bounded_reserve_weight(config)
    unallocated_weight = max(0.0, 1.0 - reserve_weight - allocated_weight)
    ready = failed.empty
    return pd.DataFrame(
        [
            {
                "ready": bool(ready),
                "deployment_mode": _text(config.deployment_mode),
                "allocation_mode": _text(config.allocation_mode),
                "capital_currency": _text(config.capital_currency),
                "total_capital": float(total_capital),
                "reserve_weight": float(reserve_weight),
                "reserve_notional": float(total_capital * reserve_weight),
                "deployable_weight": float(_deployable_weight(config)),
                "profile_count": int(len(allocations)),
                "eligible_profile_count": int(allocations["eligible"].astype(bool).sum()) if not allocations.empty else 0,
                "allocated_profile_count": int(len(allocated)),
                "allocated_weight": float(allocated_weight),
                "allocated_notional": float(total_capital * allocated_weight),
                "unallocated_weight": float(unallocated_weight),
                "unallocated_notional": float(total_capital * unallocated_weight),
                "max_profile_weight": float(_bounded_max_weight(config)),
                "top_profile": _text(top.get("profile", "")),
                "top_strategy": _text(top.get("strategy", "")),
                "top_market": _text(top.get("market", "")),
                "top_allocation_weight": float(_numeric(top.get("allocation_weight", 0.0))),
                "top_allocation_notional": float(_numeric(top.get("allocation_notional", 0.0))),
                "failed_check_count": int(len(failed)),
                "failed_check_names": ";".join(failed["check"].astype(str).tolist()) if not failed.empty else "",
                "first_failed_reason": _text(primary.get("reason", "")),
                "primary_blocker_check": _text(primary.get("check", "")),
                "primary_blocker_value": primary.get("value", ""),
                "primary_blocker_operator": _text(primary.get("operator", "")),
                "primary_blocker_threshold": primary.get("threshold", ""),
                "primary_blocker_reason": _text(primary.get("reason", "")),
                "recommendation": _recommendation(primary),
            }
        ]
    )


def _config(
    allocations: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    config: StrategyPortfolioConfig,
) -> dict[str, Any]:
    summary_row = _jsonable_row(summary.iloc[0].to_dict()) if not summary.empty else {}
    failed_checks = [row for row in _records(checks) if not bool(row.get("passed", False))]
    allocation_records = _records(allocations)
    ready_allocations = [row for row in allocation_records if _numeric(row.get("allocation_weight", 0.0)) > 0.0]
    blocked_allocations = [row for row in allocation_records if not bool(row.get("eligible", False))]
    primary = failed_checks[0] if failed_checks else {}
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "deployment_mode": _text(config.deployment_mode),
        "allocation_mode": _text(config.allocation_mode),
        "allocation_config": _jsonable(asdict(config)),
        "summary": summary_row,
        "allocation_count": len(ready_allocations),
        "blocked_profile_count": len(blocked_allocations),
        "failed_check_count": len(failed_checks),
        "failed_checks": [str(row.get("check", "")) for row in failed_checks],
        "first_failed_reason": _text(primary.get("reason", "")),
        "primary_blocker": _primary_blocker(primary),
        "allocations": allocation_records,
        "ready_allocations": ready_allocations,
        "blocked_allocations": blocked_allocations,
        "checks": _records(checks),
    }


def _eligible(
    row: pd.Series,
    config: StrategyPortfolioConfig,
    *,
    include_profiles: set[str],
    exclude_profiles: set[str],
) -> bool:
    return _eligibility_reason(
        row,
        config,
        include_profiles=include_profiles,
        exclude_profiles=exclude_profiles,
    ) == "eligible_for_paper_shadow_allocation"


def _eligibility_reason(
    row: pd.Series,
    config: StrategyPortfolioConfig,
    *,
    include_profiles: set[str],
    exclude_profiles: set[str],
) -> str:
    profile = _profile_key(row.get("profile", ""))
    if include_profiles and profile not in include_profiles:
        return "profile_not_in_include_filter"
    if profile in exclude_profiles:
        return "profile_excluded"
    if config.require_ready and not _bool(row.get("ready", False)):
        return "profile_not_ready"
    if _numeric(row.get("readiness_score", 0.0)) < _numeric(config.min_readiness_score):
        return "readiness_score_below_threshold"
    return "eligible_for_paper_shadow_allocation"


def _allocation_score(row: pd.Series) -> float:
    score = max(_numeric(row.get("readiness_score", 0.0)), 0.0)
    if score > 0.0:
        return score
    return max(float(_integer(row.get("passed_required_run_types", 0))), 1.0)


def _capped_weights(scores: pd.Series, *, deployable_weight: float, max_profile_weight: float) -> dict[int, float]:
    if scores.empty or deployable_weight <= 0.0 or max_profile_weight <= 0.0:
        return {}
    weights = {int(index): 0.0 for index in scores.index}
    active = [int(index) for index in scores.index]
    remaining = float(deployable_weight)
    clean_scores = scores.map(_numeric)
    while active and remaining > 1e-12:
        active_scores = clean_scores.loc[active]
        score_sum = float(active_scores.sum())
        if score_sum <= 0.0:
            active_scores = pd.Series(1.0, index=active)
            score_sum = float(len(active))
        capped: list[tuple[int, float]] = []
        proposed: dict[int, float] = {}
        for index in active:
            share = remaining * float(active_scores.loc[index]) / score_sum
            cap_left = max(0.0, max_profile_weight - weights[index])
            if share >= cap_left - 1e-12:
                capped.append((index, cap_left))
            else:
                proposed[index] = share
        if not capped:
            for index, share in proposed.items():
                weights[index] += share
            remaining = 0.0
            break
        for index, share in capped:
            weights[index] += share
            remaining -= share
            active.remove(index)
    return weights


def _check(check: str, passed: bool, value: Any, operator: str, threshold: Any, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "passed": bool(passed),
        "value": _jsonable(value),
        "operator": operator,
        "threshold": _jsonable(threshold),
        "reason": "" if passed else reason,
    }


def _top_allocation(allocated: pd.DataFrame) -> dict[str, Any]:
    if allocated.empty:
        return {}
    ordered = allocated.sort_values(["allocation_weight", "readiness_score", "rank"], ascending=[False, False, True])
    return ordered.iloc[0].to_dict()


def _recommendation(primary: dict[str, Any]) -> str:
    if not primary:
        return "paper_shadow_allocation_ready"
    check = _text(primary.get("check", ""))
    if check in {
        "total_capital_positive",
        "reserve_weight_between_0_and_1",
        "max_profile_weight_between_0_and_1",
        "min_readiness_score_between_0_and_1",
        "allocation_mode_supported",
    }:
        return "fix_strategy_portfolio_allocation_inputs"
    if check == "eligible_profile_count":
        return "complete_strategy_scorecard_evidence_before_allocating"
    if check == "allocated_weight_positive":
        return "increase_deployable_budget_or_profile_cap"
    return "review_strategy_portfolio_allocation_checks"


def _primary_blocker(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "check": _text(row.get("check", "")),
        "passed": False,
        "value": row.get("value", ""),
        "operator": _text(row.get("operator", "")),
        "threshold": row.get("threshold", ""),
        "reason": _text(row.get("reason", "")),
    }


def _runbook_markdown(config: dict[str, Any]) -> str:
    ready_label = "yes" if bool(config.get("ready", False)) else "no"
    summary = config.get("summary", {}) if isinstance(config.get("summary"), dict) else {}
    lines = [
        "# Strategy Portfolio Allocation Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Deployment mode: {_code(config.get('deployment_mode'))}",
        f"- Allocation mode: {_code(config.get('allocation_mode'))}",
        f"- Total capital: {_format_money(summary.get('total_capital'), summary.get('capital_currency'))}",
        f"- Allocated: {_format_weight(summary.get('allocated_weight'))} / {_format_money(summary.get('allocated_notional'), summary.get('capital_currency'))}",
        f"- Reserve: {_format_weight(summary.get('reserve_weight'))} / {_format_money(summary.get('reserve_notional'), summary.get('capital_currency'))}",
        f"- Recommendation: {_text(summary.get('recommendation'))}",
        "",
        "## Allocations",
        "",
        _allocations_table(config.get("ready_allocations", [])),
        "",
        "## Blocked Profiles",
        "",
        _blocked_table(config.get("blocked_allocations", [])),
        "",
        "## Failed Checks",
        "",
        _checks_table([row for row in config.get("checks", []) if isinstance(row, dict) and not bool(row.get("passed", False))]),
        "",
    ]
    return "\n".join(lines)


def _allocations_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Profile", "Strategy", "Market", "Weight", "Notional", "Score", "Next gate"],
        [
            [
                _text(row.get("profile")),
                _text(row.get("strategy")),
                _text(row.get("market")),
                _format_weight(row.get("allocation_weight")),
                _format_money(row.get("allocation_notional"), row.get("capital_currency")),
                f"{_numeric(row.get('readiness_score')):.3f}",
                _code(row.get("next_gate")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _blocked_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Profile", "Ready", "Score", "Reason", "Next gate"],
        [
            [
                _text(row.get("profile")),
                "yes" if bool(row.get("ready", False)) else "no",
                f"{_numeric(row.get('readiness_score')):.3f}",
                _text(row.get("eligibility_reason")),
                _code(row.get("next_gate")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _checks_table(rows: Any) -> str:
    records = rows if isinstance(rows, list) else []
    if not records:
        return "_None_"
    return _markdown_table(
        ["Check", "Value", "Operator", "Threshold", "Reason"],
        [
            [
                _text(row.get("check")),
                _text(row.get("value")),
                _text(row.get("operator")),
                _text(row.get("threshold")),
                _text(row.get("reason")),
            ]
            for row in records
            if isinstance(row, dict)
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _scorecard_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "strategy_scorecard.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"strategy scorecard not found: {candidate}")
    return candidate


def _deployable_weight(config: StrategyPortfolioConfig) -> float:
    return max(0.0, 1.0 - _bounded_reserve_weight(config))


def _bounded_reserve_weight(config: StrategyPortfolioConfig) -> float:
    return min(max(_numeric(config.reserve_weight), 0.0), 1.0)


def _bounded_max_weight(config: StrategyPortfolioConfig) -> float:
    return min(max(_numeric(config.max_profile_weight), 0.0), 1.0)


def _profile_key(value: Any) -> str:
    return _text(value).strip().lower()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_row(row) for row in frame.to_dict(orient="records")]


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


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
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _integer(value: Any) -> int:
    return int(round(_numeric(value)))


def _numeric(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return bool(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _format_weight(value: Any) -> str:
    return f"{_numeric(value):.3f}"


def _format_money(value: Any, currency: Any) -> str:
    return f"{_text(currency) or 'INR'} {_numeric(value):,.2f}"


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
