from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


ROUTE_READY_STATUS = "ready_for_live_dryrun_route_review"
PORTABLE_STATUSES = {"india_ready", "portable_research"}
_EVIDENCE_BOOL_COLUMNS = {
    "ready",
    "require_file_inputs",
    "require_no_blocked_placeholder_schema",
    "require_broker_roundtrip_portfolio_safe",
    "fail_on_broker_roundtrip_portfolio_breach",
    "require_broker_roundtrip_portfolio_concentration_ok",
    "fail_on_broker_roundtrip_portfolio_concentration_breach",
    "require_broker_roundtrip_resume_route_ready",
    "fail_on_broker_roundtrip_resume_route_breach",
    "require_provider_broker_roundtrip_synthetic_sidecar_ready",
    "fail_on_provider_broker_roundtrip_synthetic_sidecar_breach",
    "require_provider_lineage_selection",
}
_EVIDENCE_COUNT_COLUMNS = {
    "placeholder_schema_blocked_runs",
    "broker_roundtrip_portfolio_safe_runs",
    "broker_roundtrip_portfolio_breach_runs",
    "broker_roundtrip_portfolio_concentration_ok_runs",
    "broker_roundtrip_portfolio_concentration_breach_runs",
    "broker_roundtrip_resume_route_ready_runs",
    "broker_roundtrip_resume_route_breach_runs",
    "broker_roundtrip_resume_route_gap_breach_runs",
    "broker_roundtrip_resume_route_launch_control_breach_runs",
    "broker_roundtrip_resume_route_portfolio_breach_runs",
    "broker_roundtrip_resume_route_concentration_breach_runs",
    "provider_broker_roundtrip_runs",
    "provider_broker_roundtrip_passed_runs",
    "provider_broker_roundtrip_synthetic_dataset_count",
    "provider_broker_roundtrip_synthetic_sidecar_count",
    "provider_broker_roundtrip_synthetic_sidecar_readable_count",
    "provider_broker_roundtrip_synthetic_sidecar_proof_runs",
    "provider_broker_roundtrip_synthetic_sidecar_ready_runs",
    "provider_broker_roundtrip_synthetic_sidecar_breach_runs",
    "provider_lineage_required_run_type_count",
    "provider_lineage_covered_run_type_count",
    "provider_lineage_selectable_runs",
    "provider_lineage_selection_blocked_runs",
    "provider_lineage_selected_run_count",
    "provider_lineage_selected_pair_count",
    "input_directory_count",
    "input_other_count",
    "input_unfingerprinted_count",
}


@dataclass(frozen=True)
class RouteReadinessReview:
    pairs: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame | None = None
    output_dir: Path | None = None
    config: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def build_route_readiness_review(
    market_portability_config: dict[str, Any],
    *,
    strategy_evidence_summaries: pd.DataFrame | None = None,
    ops_evidence_summaries: pd.DataFrame | None = None,
    require_ops_file_inputs: bool = True,
) -> RouteReadinessReview:
    strategy_evidence = _normalize_evidence_frame(strategy_evidence_summaries)
    ops_evidence = _normalize_evidence_frame(ops_evidence_summaries)
    pair_rows = [
        _pair_row(
            pair,
            strategy_evidence,
            ops_evidence,
            require_ops_file_inputs=require_ops_file_inputs,
        )
        for pair in _portability_pairs(market_portability_config)
    ]
    pairs = pd.DataFrame(pair_rows)
    gaps = pairs.loc[~pairs["route_ready"].astype(bool)].reset_index(drop=True) if not pairs.empty else pairs
    summary = _summary(pairs, gaps, require_ops_file_inputs=require_ops_file_inputs)
    action_queue = _action_queue(pairs)
    config = _config(pairs, gaps, summary, action_queue, market_portability_config, require_ops_file_inputs)
    return RouteReadinessReview(
        pairs=pairs,
        gaps=gaps,
        summary=summary,
        action_queue=action_queue,
        config=config,
    )


def write_route_readiness_review(
    output_dir: str | Path,
    *,
    market_portability: str | Path,
    strategy_evidence: tuple[str | Path, ...] = (),
    ops_evidence: tuple[str | Path, ...] = (),
    require_ops_file_inputs: bool = True,
) -> RouteReadinessReview:
    portability_path = _market_portability_config_path(market_portability)
    market_portability_config = json.loads(portability_path.read_text(encoding="utf-8"))
    strategy_paths, strategy_summaries = _read_evidence_summaries(strategy_evidence)
    ops_paths, ops_summaries = _read_evidence_summaries(ops_evidence)
    review = build_route_readiness_review(
        market_portability_config,
        strategy_evidence_summaries=strategy_summaries,
        ops_evidence_summaries=ops_summaries,
        require_ops_file_inputs=require_ops_file_inputs,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    review.pairs.to_csv(out / "route_readiness_pairs.csv", index=False)
    review.gaps.to_csv(out / "route_readiness_gaps.csv", index=False)
    review.summary.to_csv(out / "route_readiness_summary.csv", index=False)
    action_queue = review.action_queue if review.action_queue is not None else _action_queue(review.pairs)
    action_queue.to_csv(out / "route_readiness_action_queue.csv", index=False)
    (out / "route_readiness_runbook.md").write_text(
        _runbook_markdown(review.summary.iloc[0], review.pairs, review.gaps, action_queue),
        encoding="utf-8",
    )
    (out / "route_readiness_config.json").write_text(
        json.dumps(review.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="route_readiness_review",
        parameters={"require_ops_file_inputs": bool(require_ops_file_inputs)},
        inputs={
            "market_portability_config": portability_path,
            "strategy_evidence_summaries": strategy_paths,
            "ops_evidence_summaries": ops_paths,
        },
    )
    return RouteReadinessReview(
        pairs=review.pairs,
        gaps=review.gaps,
        summary=review.summary,
        action_queue=action_queue,
        output_dir=out,
        config=review.config,
    )


def _portability_pairs(config: dict[str, Any]) -> list[dict[str, Any]]:
    ready = config.get("ready_pairs", []) or []
    gaps = config.get("gap_pairs", []) or []
    if not isinstance(ready, list) or not isinstance(gaps, list):
        raise ValueError("market portability config must contain list ready_pairs and gap_pairs")
    pairs = []
    for item in [*ready, *gaps]:
        if isinstance(item, dict):
            pairs.append(item)
    return pairs


def _pair_row(
    pair: dict[str, Any],
    strategy_evidence: pd.DataFrame,
    ops_evidence: pd.DataFrame,
    *,
    require_ops_file_inputs: bool,
) -> dict[str, Any]:
    strategy = _text(pair.get("strategy"))
    market = _text(pair.get("market"))
    portability_status = _text(pair.get("status"))
    strategy_profile = _text(pair.get("strategy_evidence_profile"))
    ops_profile = _text(pair.get("ops_evidence_profile")) or "ops_launch"
    portability_ready = portability_status in PORTABLE_STATUSES
    strategy_match = _match_evidence(
        strategy_evidence,
        expected_profile=strategy_profile,
        expected_strategy=strategy,
        expected_market=market,
        label="strategy",
    )
    ops_match = _match_evidence(
        ops_evidence,
        expected_profile=ops_profile,
        expected_strategy=strategy,
        expected_market=market,
        label="ops",
    )
    ops_non_file_inputs = (
        _number(ops_match.row.get("input_directory_count", 0))
        + _number(ops_match.row.get("input_other_count", 0))
        + _number(ops_match.row.get("input_unfingerprinted_count", 0))
        if ops_match.row
        else 0
    )
    ops_file_inputs_required = _to_bool(ops_match.row.get("require_file_inputs", False)) if ops_match.row else False
    ops_file_inputs_clean = bool(ops_file_inputs_required and ops_non_file_inputs == 0)
    ops_control_failures = _ops_launch_control_failures(ops_match.row) if ops_match.row else []
    ops_launch_controls_ready = bool(not ops_control_failures)
    status = _route_status(
        portability_ready=portability_ready,
        strategy_match=strategy_match,
        ops_match=ops_match,
        require_ops_file_inputs=require_ops_file_inputs,
        ops_file_inputs_clean=ops_file_inputs_clean,
        ops_launch_controls_ready=ops_launch_controls_ready,
    )
    route_ready = status == ROUTE_READY_STATUS
    return {
        "strategy": strategy,
        "market": market,
        "portability_status": portability_status,
        "portability_ready": bool(portability_ready),
        "strategy_evidence_profile": strategy_profile,
        "strategy_evidence_ready": bool(strategy_match.ready),
        "strategy_evidence_status": strategy_match.status,
        "strategy_evidence_source": strategy_match.source,
        "strategy_evidence_recommendation": strategy_match.recommendation,
        "ops_evidence_profile": ops_profile,
        "ops_evidence_ready": bool(ops_match.ready),
        "ops_evidence_status": ops_match.status,
        "ops_evidence_source": ops_match.source,
        "ops_evidence_recommendation": ops_match.recommendation,
        "ops_file_inputs_required": bool(ops_file_inputs_required),
        "ops_non_file_input_count": int(ops_non_file_inputs),
        "ops_launch_controls_ready": bool(ops_launch_controls_ready),
        "ops_launch_control_failures": ";".join(ops_control_failures),
        "ops_placeholder_schema_blocked_runs": int(_number(ops_match.row.get("placeholder_schema_blocked_runs", 0)))
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(ops_match.row.get("broker_roundtrip_portfolio_safe_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_portfolio_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(ops_match.row.get("broker_roundtrip_portfolio_concentration_ok_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_portfolio_concentration_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_resume_route_ready_runs": int(
            _number(ops_match.row.get("broker_roundtrip_resume_route_ready_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_resume_route_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_resume_route_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_resume_route_gap_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_resume_route_gap_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_resume_route_launch_control_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_resume_route_launch_control_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_resume_route_portfolio_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_resume_route_portfolio_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_broker_roundtrip_resume_route_concentration_breach_runs": int(
            _number(ops_match.row.get("broker_roundtrip_resume_route_concentration_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_runs": int(
            _number(ops_match.row.get("provider_broker_roundtrip_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_passed_runs": int(
            _number(ops_match.row.get("provider_broker_roundtrip_passed_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_synthetic_dataset_count": int(
            _number(ops_match.row.get("provider_broker_roundtrip_synthetic_dataset_count", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_synthetic_sidecar_count": int(
            _number(ops_match.row.get("provider_broker_roundtrip_synthetic_sidecar_count", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_synthetic_sidecar_readable_count": int(
            _number(ops_match.row.get("provider_broker_roundtrip_synthetic_sidecar_readable_count", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_synthetic_sidecar_proof_runs": int(
            _number(ops_match.row.get("provider_broker_roundtrip_synthetic_sidecar_proof_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_synthetic_sidecar_ready_runs": int(
            _number(ops_match.row.get("provider_broker_roundtrip_synthetic_sidecar_ready_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs": int(
            _number(ops_match.row.get("provider_broker_roundtrip_synthetic_sidecar_breach_runs", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_lineage_selected_run_count": int(
            _number(ops_match.row.get("provider_lineage_selected_run_count", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_lineage_selected_pair_count": int(
            _number(ops_match.row.get("provider_lineage_selected_pair_count", 0))
        )
        if ops_match.row
        else 0,
        "ops_provider_lineage_selected_pair_ids": _text(
            ops_match.row.get("provider_lineage_selected_pair_ids", "")
        )
        if ops_match.row
        else "",
        "ops_provider_lineage_selected_run_dirs": _text(
            ops_match.row.get("provider_lineage_selected_run_dirs", "")
        )
        if ops_match.row
        else "",
        "ops_provider_lineage_selection_contract_version": _text(
            ops_match.row.get("provider_lineage_selection_contract_version", "")
        )
        if ops_match.row
        else "",
        "ops_provider_lineage_selection_contract_sha256": _text(
            ops_match.row.get("provider_lineage_selection_contract_sha256", "")
        ).lower()
        if ops_match.row
        else "",
        "ops_provider_lineage_selection_artifact": _text(
            ops_match.row.get("provider_lineage_selection_artifact", "")
        )
        if ops_match.row
        else "",
        "route_ready": bool(route_ready),
        "status": status,
        "blocker": "" if route_ready else _blocker(pair, status),
        "next_gate": "live_dryrun_route_review" if route_ready else _next_gate(pair, status),
        "next_gate_help_command": _next_gate_help_command(
            "live_dryrun_route_review" if route_ready else _next_gate(pair, status)
        ),
    }


@dataclass(frozen=True)
class EvidenceMatch:
    found: bool
    ready: bool
    status: str
    source: str
    recommendation: str
    row: dict[str, Any]


def _match_evidence(
    frame: pd.DataFrame,
    *,
    expected_profile: str,
    expected_strategy: str,
    expected_market: str,
    label: str,
) -> EvidenceMatch:
    empty = EvidenceMatch(
        found=False,
        ready=False,
        status=f"{label}_evidence_missing",
        source="",
        recommendation="",
        row={},
    )
    if frame.empty:
        return empty
    profile = _normalize_identity(expected_profile)
    candidates = frame.loc[frame["evidence_profile"].map(_normalize_identity) == profile].copy()
    if candidates.empty:
        return empty
    strategy_key = _normalize_strategy(expected_strategy)
    market_key = _normalize_identity(expected_market)
    identity = candidates.loc[
        (candidates["strategy"].map(_normalize_strategy) == strategy_key)
        & (candidates["market"].map(_normalize_identity) == market_key)
    ].copy()
    if identity.empty:
        return EvidenceMatch(
            found=False,
            ready=False,
            status=f"{label}_evidence_identity_mismatch",
            source="",
            recommendation="",
            row={},
        )
    sort_columns = ["_ready_sort"]
    identity["_ready_sort"] = identity["ready"].map(_to_bool)
    if label == "ops":
        identity["_ops_control_failure_sort"] = identity.apply(
            lambda row: -len(_ops_launch_control_failures(row.to_dict())),
            axis=1,
        )
        sort_columns.append("_ops_control_failure_sort")
    row = (
        identity.sort_values(sort_columns, kind="mergesort")
        .iloc[-1]
        .drop(labels=["_ready_sort", "_ops_control_failure_sort"], errors="ignore")
        .to_dict()
    )
    ready = _to_bool(row.get("ready", False))
    return EvidenceMatch(
        found=True,
        ready=ready,
        status=f"{label}_evidence_ready" if ready else f"{label}_evidence_incomplete",
        source=_text(row.get("source_path")),
        recommendation=_text(row.get("recommendation")),
        row=row,
    )


def _route_status(
    *,
    portability_ready: bool,
    strategy_match: EvidenceMatch,
    ops_match: EvidenceMatch,
    require_ops_file_inputs: bool,
    ops_file_inputs_clean: bool,
    ops_launch_controls_ready: bool,
) -> str:
    if not portability_ready:
        return "blocked_by_portability"
    if not strategy_match.found:
        return strategy_match.status
    if not strategy_match.ready:
        return "strategy_evidence_incomplete"
    if not ops_match.found:
        return ops_match.status
    if not ops_match.ready:
        return "ops_evidence_incomplete"
    if require_ops_file_inputs and not ops_file_inputs_clean:
        return "ops_file_provenance_not_gated"
    if not ops_launch_controls_ready:
        return "ops_launch_controls_not_gated"
    return ROUTE_READY_STATUS


def _ops_launch_control_failures(row: dict[str, Any]) -> list[str]:
    checks = [
        (
            "require_no_blocked_placeholder_schema",
            _to_bool(row.get("require_no_blocked_placeholder_schema", False)),
        ),
        ("placeholder_schema_blocked_runs", int(_number(row.get("placeholder_schema_blocked_runs", 0))) == 0),
        (
            "require_broker_roundtrip_portfolio_safe",
            _to_bool(row.get("require_broker_roundtrip_portfolio_safe", False)),
        ),
        (
            "fail_on_broker_roundtrip_portfolio_breach",
            _to_bool(row.get("fail_on_broker_roundtrip_portfolio_breach", False)),
        ),
        (
            "broker_roundtrip_portfolio_safe_runs",
            int(_number(row.get("broker_roundtrip_portfolio_safe_runs", 0))) >= 1,
        ),
        (
            "broker_roundtrip_portfolio_breach_runs",
            int(_number(row.get("broker_roundtrip_portfolio_breach_runs", 0))) == 0,
        ),
        (
            "require_broker_roundtrip_portfolio_concentration_ok",
            _to_bool(row.get("require_broker_roundtrip_portfolio_concentration_ok", False)),
        ),
        (
            "fail_on_broker_roundtrip_portfolio_concentration_breach",
            _to_bool(row.get("fail_on_broker_roundtrip_portfolio_concentration_breach", False)),
        ),
        (
            "broker_roundtrip_portfolio_concentration_ok_runs",
            int(_number(row.get("broker_roundtrip_portfolio_concentration_ok_runs", 0))) >= 1,
        ),
        (
            "broker_roundtrip_portfolio_concentration_breach_runs",
            int(_number(row.get("broker_roundtrip_portfolio_concentration_breach_runs", 0))) == 0,
        ),
        (
            "require_broker_roundtrip_resume_route_ready",
            _to_bool(row.get("require_broker_roundtrip_resume_route_ready", False)),
        ),
        (
            "fail_on_broker_roundtrip_resume_route_breach",
            _to_bool(row.get("fail_on_broker_roundtrip_resume_route_breach", False)),
        ),
        (
            "broker_roundtrip_resume_route_ready_runs",
            int(_number(row.get("broker_roundtrip_resume_route_ready_runs", 0))) >= 1,
        ),
        (
            "broker_roundtrip_resume_route_breach_runs",
            int(_number(row.get("broker_roundtrip_resume_route_breach_runs", 0))) == 0,
        ),
        (
            "broker_roundtrip_resume_route_gap_breach_runs",
            int(_number(row.get("broker_roundtrip_resume_route_gap_breach_runs", 0))) == 0,
        ),
        (
            "broker_roundtrip_resume_route_launch_control_breach_runs",
            int(_number(row.get("broker_roundtrip_resume_route_launch_control_breach_runs", 0))) == 0,
        ),
        (
            "broker_roundtrip_resume_route_portfolio_breach_runs",
            int(_number(row.get("broker_roundtrip_resume_route_portfolio_breach_runs", 0))) == 0,
        ),
        (
            "broker_roundtrip_resume_route_concentration_breach_runs",
            int(_number(row.get("broker_roundtrip_resume_route_concentration_breach_runs", 0))) == 0,
        ),
    ]
    if _provider_sidecar_controls_active(row):
        checks.extend(
            [
                (
                    "require_provider_broker_roundtrip_synthetic_sidecar_ready",
                    _to_bool(row.get("require_provider_broker_roundtrip_synthetic_sidecar_ready", False)),
                ),
                (
                    "fail_on_provider_broker_roundtrip_synthetic_sidecar_breach",
                    _to_bool(row.get("fail_on_provider_broker_roundtrip_synthetic_sidecar_breach", False)),
                ),
                (
                    "provider_broker_roundtrip_synthetic_sidecar_proof_runs",
                    int(_number(row.get("provider_broker_roundtrip_synthetic_sidecar_proof_runs", 0))) >= 1,
                ),
                (
                    "provider_broker_roundtrip_synthetic_sidecar_ready_runs",
                    int(_number(row.get("provider_broker_roundtrip_synthetic_sidecar_ready_runs", 0))) >= 1,
                ),
                (
                    "provider_broker_roundtrip_synthetic_sidecar_breach_runs",
                    int(_number(row.get("provider_broker_roundtrip_synthetic_sidecar_breach_runs", 0))) == 0,
                ),
            ]
        )
    if _provider_lineage_controls_active(row):
        required_types = int(
            _number(row.get("provider_lineage_required_run_type_count", 0))
        )
        covered_types = int(
            _number(row.get("provider_lineage_covered_run_type_count", 0))
        )
        selected_run_count = int(
            _number(row.get("provider_lineage_selected_run_count", 0))
        )
        selected_pair_count = int(
            _number(row.get("provider_lineage_selected_pair_count", 0))
        )
        selected_pair_ids = _semicolon_values(
            row.get("provider_lineage_selected_pair_ids", "")
        )
        selection_contract = _text(
            row.get("provider_lineage_selection_contract_sha256", "")
        )
        checks.extend(
            [
                (
                    "require_provider_lineage_selection",
                    _to_bool(row.get("require_provider_lineage_selection", False)),
                ),
                (
                    "provider_lineage_selection_policy",
                    _normalize_identity(
                        row.get("provider_lineage_selection_policy", "")
                    )
                    == "required",
                ),
                (
                    "provider_lineage_required_run_type_count",
                    required_types > 0,
                ),
                (
                    "provider_lineage_covered_run_type_count",
                    required_types > 0 and covered_types >= required_types,
                ),
                (
                    "provider_lineage_selectable_runs",
                    required_types > 0
                    and int(
                        _number(row.get("provider_lineage_selectable_runs", 0))
                    )
                    >= required_types,
                ),
                (
                    "provider_lineage_selected_run_count",
                    required_types > 0 and selected_run_count >= required_types,
                ),
                (
                    "provider_lineage_selected_pair_count",
                    required_types > 0 and selected_pair_count == required_types,
                ),
                (
                    "provider_lineage_selected_pair_ids",
                    required_types > 0
                    and len(selected_pair_ids) == required_types
                    and len(set(selected_pair_ids)) == required_types
                    and all(_valid_sha256(value) for value in selected_pair_ids),
                ),
                (
                    "provider_lineage_selection_contract_sha256",
                    _valid_sha256(selection_contract),
                ),
            ]
        )
    return [name for name, passed in checks if not passed]


def _provider_sidecar_controls_active(row: dict[str, Any]) -> bool:
    return (
        _normalize_identity(row.get("evidence_profile", "")) == "provider_imbalance_ops_launch"
        or _to_bool(row.get("require_provider_broker_roundtrip_synthetic_sidecar_ready", False))
        or _to_bool(row.get("fail_on_provider_broker_roundtrip_synthetic_sidecar_breach", False))
        or int(_number(row.get("provider_broker_roundtrip_synthetic_sidecar_proof_runs", 0))) > 0
    )


def _provider_lineage_controls_active(row: dict[str, Any]) -> bool:
    return (
        _normalize_identity(row.get("evidence_profile", ""))
        == "provider_imbalance_ops_launch"
        or _to_bool(row.get("require_provider_lineage_selection", False))
        or int(_number(row.get("provider_lineage_required_run_type_count", 0)))
        > 0
    )


def _next_gate(pair: dict[str, Any], status: str) -> str:
    if status == "blocked_by_portability":
        return _text(pair.get("next_gate"))
    if status.startswith("strategy_evidence"):
        return _text(pair.get("strategy_evidence_gate"))
    if status.startswith("ops") or status == "ops_file_provenance_not_gated":
        return _text(pair.get("ops_evidence_gate"))
    return ""


def _next_gate_help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    if not gate or gate in {"live_dryrun_route_review", "run_walkforward_and_paper_shadow_gates"}:
        return ""
    if gate == "run_market_profile_report_with_fee_assumptions":
        return "python -m hft_cli market-portability-report --help"
    command = gate.split()[0]
    cli_commands = {
        "market-portability-report",
        "review-route-readiness",
        "review-strategy-evidence",
    }
    if command in cli_commands:
        return f"python -m hft_cli {gate} --help"
    return ""


def _blocker(pair: dict[str, Any], status: str) -> str:
    if status == "blocked_by_portability":
        return _text(pair.get("blocker")) or status
    return status


def _summary(
    pairs: pd.DataFrame,
    gaps: pd.DataFrame,
    *,
    require_ops_file_inputs: bool,
) -> pd.DataFrame:
    if pairs.empty:
        return pd.DataFrame(
            [
                {
                    "ready": False,
                    "strategy": "",
                    "market": "",
                    "strategy_count": 0,
                    "market_count": 0,
                    "pair_count": 0,
                    "route_ready_pairs": 0,
                    "gap_pairs": 0,
                    "strategy_evidence_ready_pairs": 0,
                    "ops_evidence_ready_pairs": 0,
                    "portability_blocked_pairs": 0,
                    "ops_file_provenance_blocked_pairs": 0,
                    "ops_launch_controls_blocked_pairs": 0,
                    "ops_broker_roundtrip_portfolio_breach_pairs": 0,
                    "ops_broker_roundtrip_portfolio_concentration_breach_pairs": 0,
                    "ops_broker_roundtrip_resume_route_breach_pairs": 0,
                    "ops_broker_roundtrip_resume_route_gap_breach_pairs": 0,
                    "ops_broker_roundtrip_resume_route_launch_control_breach_pairs": 0,
                    "ops_broker_roundtrip_resume_route_portfolio_breach_pairs": 0,
                    "ops_broker_roundtrip_resume_route_concentration_breach_pairs": 0,
                    "ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": 0,
                    "ops_provider_lineage_selected_run_count": 0,
                    "ops_provider_lineage_selected_pair_count": 0,
                    "ops_provider_lineage_selected_pair_ids": "",
                    "ops_provider_lineage_selected_run_dirs": "",
                    "ops_provider_lineage_selection_contract_version": "",
                    "ops_provider_lineage_selection_contract_sha256": "",
                    "ops_provider_lineage_selection_artifact": "",
                    "require_ops_file_inputs": bool(require_ops_file_inputs),
                    "ready_action_count": 0,
                    "blocked_action_count": 0,
                    "next_gate": "",
                    "next_gate_help_command": "",
                    "recommendation": "route_readiness_inputs_missing",
                }
            ]
        )
    route_ready = int(pairs["route_ready"].astype(bool).sum())
    gap_count = int(len(gaps))
    ready = bool(route_ready > 0 and gap_count == 0)
    route_pairs = pairs.loc[pairs["route_ready"].astype(bool)]
    identity_pairs = route_pairs if not route_pairs.empty else pairs
    strategies = sorted(set(identity_pairs["strategy"].astype(str))) if "strategy" in identity_pairs else []
    markets = sorted(set(identity_pairs["market"].astype(str))) if "market" in identity_pairs else []
    next_gate = _primary_next_gate(pairs, gaps, ready=ready)
    lineage_row = identity_pairs.iloc[0] if not identity_pairs.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": strategies[0] if len(strategies) == 1 else "",
                "market": markets[0] if len(markets) == 1 else "",
                "strategy_count": int(len(strategies)),
                "market_count": int(len(markets)),
                "pair_count": int(len(pairs)),
                "route_ready_pairs": route_ready,
                "gap_pairs": gap_count,
                "strategy_evidence_ready_pairs": int(pairs["strategy_evidence_ready"].astype(bool).sum()),
                "ops_evidence_ready_pairs": int(pairs["ops_evidence_ready"].astype(bool).sum()),
                "portability_blocked_pairs": int((pairs["status"].astype(str) == "blocked_by_portability").sum()),
                "ops_file_provenance_blocked_pairs": int(
                    (pairs["status"].astype(str) == "ops_file_provenance_not_gated").sum()
                ),
                "ops_launch_controls_blocked_pairs": int(
                    (pairs["status"].astype(str) == "ops_launch_controls_not_gated").sum()
                ),
                "ops_broker_roundtrip_portfolio_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_portfolio_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_portfolio_breach_runs" in pairs
                else 0,
                "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_portfolio_concentration_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_portfolio_concentration_breach_runs" in pairs
                else 0,
                "ops_broker_roundtrip_resume_route_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_resume_route_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_resume_route_breach_runs" in pairs
                else 0,
                "ops_broker_roundtrip_resume_route_gap_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_resume_route_gap_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_resume_route_gap_breach_runs" in pairs
                else 0,
                "ops_broker_roundtrip_resume_route_launch_control_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_resume_route_launch_control_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_resume_route_launch_control_breach_runs" in pairs
                else 0,
                "ops_broker_roundtrip_resume_route_portfolio_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_resume_route_portfolio_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_resume_route_portfolio_breach_runs" in pairs
                else 0,
                "ops_broker_roundtrip_resume_route_concentration_breach_pairs": int(
                    (pairs["ops_broker_roundtrip_resume_route_concentration_breach_runs"].astype(int) > 0).sum()
                )
                if "ops_broker_roundtrip_resume_route_concentration_breach_runs" in pairs
                else 0,
                "ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    (
                        pairs[
                            "ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs"
                        ].astype(int)
                        > 0
                    ).sum()
                )
                if "ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs" in pairs
                else 0,
                "ops_provider_lineage_selected_run_count": int(
                    _number(lineage_row.get("ops_provider_lineage_selected_run_count", 0))
                ),
                "ops_provider_lineage_selected_pair_count": int(
                    _number(lineage_row.get("ops_provider_lineage_selected_pair_count", 0))
                ),
                "ops_provider_lineage_selected_pair_ids": _text(
                    lineage_row.get("ops_provider_lineage_selected_pair_ids", "")
                ),
                "ops_provider_lineage_selected_run_dirs": _text(
                    lineage_row.get("ops_provider_lineage_selected_run_dirs", "")
                ),
                "ops_provider_lineage_selection_contract_version": _text(
                    lineage_row.get("ops_provider_lineage_selection_contract_version", "")
                ),
                "ops_provider_lineage_selection_contract_sha256": _text(
                    lineage_row.get("ops_provider_lineage_selection_contract_sha256", "")
                ),
                "ops_provider_lineage_selection_artifact": _text(
                    lineage_row.get("ops_provider_lineage_selection_artifact", "")
                ),
                "require_ops_file_inputs": bool(require_ops_file_inputs),
                "ready_action_count": route_ready,
                "blocked_action_count": int((~pairs["route_ready"].astype(bool)).sum()),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
                "recommendation": "eligible_for_live_dryrun_route_review"
                if ready
                else "complete_route_readiness_gaps",
            }
        ]
    )


def _primary_next_gate(pairs: pd.DataFrame, gaps: pd.DataFrame, *, ready: bool) -> str:
    if ready:
        ready_pairs = pairs.loc[pairs["route_ready"].astype(bool)] if not pairs.empty else pairs
        if not ready_pairs.empty:
            return _text(ready_pairs.iloc[0].get("next_gate"))
        return "live_dryrun_route_review"
    if not gaps.empty:
        return _text(gaps.iloc[0].get("next_gate"))
    return ""


def _config(
    pairs: pd.DataFrame,
    gaps: pd.DataFrame,
    summary: pd.DataFrame,
    action_queue: pd.DataFrame,
    market_portability_config: dict[str, Any],
    require_ops_file_inputs: bool,
) -> dict[str, Any]:
    summary_row = summary.iloc[0].to_dict() if not summary.empty else {}
    ready_pairs = pairs.loc[pairs["route_ready"].astype(bool)].copy() if not pairs.empty else pairs
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "summary": _jsonable_row(summary_row),
        "require_ops_file_inputs": bool(require_ops_file_inputs),
        "market_portability_ready": bool(market_portability_config.get("ready", False)),
        "route_ready_pairs": _records(ready_pairs),
        "gap_pairs": _records(gaps),
        "next_gates": sorted(set(gaps["next_gate"].astype(str))) if not gaps.empty else [],
        "ready_action_count": int(pairs["route_ready"].astype(bool).sum()) if not pairs.empty else 0,
        "blocked_action_count": int((~pairs["route_ready"].astype(bool)).sum()) if not pairs.empty else 0,
        "next_gate": _text(summary_row.get("next_gate")),
        "next_gate_help_command": _text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(ready_actions),
        "blocked_actions": _action_records(blocked_actions),
    }


def _first_action_record(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return _jsonable_row(frame.iloc[0].to_dict())


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _action_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_row(row) for row in frame.to_dict(orient="records")]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    columns = [
        "strategy",
        "market",
        "portability_status",
        "strategy_evidence_profile",
        "strategy_evidence_status",
        "strategy_evidence_source",
        "strategy_evidence_recommendation",
        "strategy_evidence_ready",
        "ops_evidence_profile",
        "ops_evidence_status",
        "ops_evidence_source",
        "ops_evidence_recommendation",
        "ops_evidence_ready",
        "ops_file_inputs_required",
        "ops_non_file_input_count",
        "ops_launch_controls_ready",
        "ops_launch_control_failures",
        "ops_placeholder_schema_blocked_runs",
        "ops_broker_roundtrip_portfolio_safe_runs",
        "ops_broker_roundtrip_portfolio_breach_runs",
        "ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "ops_broker_roundtrip_portfolio_concentration_breach_runs",
        "ops_broker_roundtrip_resume_route_ready_runs",
        "ops_broker_roundtrip_resume_route_breach_runs",
        "ops_broker_roundtrip_resume_route_gap_breach_runs",
        "ops_broker_roundtrip_resume_route_launch_control_breach_runs",
        "ops_broker_roundtrip_resume_route_portfolio_breach_runs",
        "ops_broker_roundtrip_resume_route_concentration_breach_runs",
        "ops_provider_broker_roundtrip_runs",
        "ops_provider_broker_roundtrip_passed_runs",
        "ops_provider_broker_roundtrip_synthetic_dataset_count",
        "ops_provider_broker_roundtrip_synthetic_sidecar_count",
        "ops_provider_broker_roundtrip_synthetic_sidecar_readable_count",
        "ops_provider_broker_roundtrip_synthetic_sidecar_proof_runs",
        "ops_provider_broker_roundtrip_synthetic_sidecar_ready_runs",
        "ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs",
        "ops_provider_lineage_selected_run_count",
        "ops_provider_lineage_selected_pair_count",
        "ops_provider_lineage_selected_pair_ids",
        "ops_provider_lineage_selected_run_dirs",
        "ops_provider_lineage_selection_contract_version",
        "ops_provider_lineage_selection_contract_sha256",
        "ops_provider_lineage_selection_artifact",
        "route_ready",
        "status",
        "blocker",
        "next_gate",
        "next_gate_help_command",
    ]
    available = [column for column in columns if column in frame.columns]
    return [_jsonable_row(row) for row in frame[available].to_dict(orient="records")]


def _action_queue(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not pairs.empty:
        ordered = pairs.sort_values(["route_ready", "strategy", "market"], ascending=[False, True, True])
        for priority, row in enumerate(ordered.to_dict(orient="records"), start=1):
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "ready" if bool(row.get("route_ready", False)) else "blocked",
                    "strategy": _text(row.get("strategy")),
                    "market": _text(row.get("market")),
                    "status": _text(row.get("status")),
                    "blocker": _text(row.get("blocker")),
                    "next_gate": _text(row.get("next_gate")),
                    "next_gate_help_command": _text(row.get("next_gate_help_command")),
                    "strategy_evidence_profile": _text(row.get("strategy_evidence_profile")),
                    "strategy_evidence_status": _text(row.get("strategy_evidence_status")),
                    "ops_evidence_profile": _text(row.get("ops_evidence_profile")),
                    "ops_evidence_status": _text(row.get("ops_evidence_status")),
                    "ops_file_inputs_required": bool(row.get("ops_file_inputs_required", False)),
                    "ops_non_file_input_count": int(_number(row.get("ops_non_file_input_count", 0))),
                    "ops_launch_controls_ready": bool(row.get("ops_launch_controls_ready", False)),
                    "ops_launch_control_failures": _text(row.get("ops_launch_control_failures")),
                    "ops_broker_roundtrip_portfolio_safe_runs": int(
                        _number(row.get("ops_broker_roundtrip_portfolio_safe_runs", 0))
                    ),
                    "ops_broker_roundtrip_portfolio_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_portfolio_breach_runs", 0))
                    ),
                    "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                        _number(row.get("ops_broker_roundtrip_portfolio_concentration_ok_runs", 0))
                    ),
                    "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_portfolio_concentration_breach_runs", 0))
                    ),
                    "ops_broker_roundtrip_resume_route_ready_runs": int(
                        _number(row.get("ops_broker_roundtrip_resume_route_ready_runs", 0))
                    ),
                    "ops_broker_roundtrip_resume_route_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_resume_route_breach_runs", 0))
                    ),
                    "ops_broker_roundtrip_resume_route_gap_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_resume_route_gap_breach_runs", 0))
                    ),
                    "ops_broker_roundtrip_resume_route_launch_control_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_resume_route_launch_control_breach_runs", 0))
                    ),
                    "ops_broker_roundtrip_resume_route_portfolio_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_resume_route_portfolio_breach_runs", 0))
                    ),
                    "ops_broker_roundtrip_resume_route_concentration_breach_runs": int(
                        _number(row.get("ops_broker_roundtrip_resume_route_concentration_breach_runs", 0))
                    ),
                    "ops_provider_broker_roundtrip_runs": int(
                        _number(row.get("ops_provider_broker_roundtrip_runs", 0))
                    ),
                    "ops_provider_broker_roundtrip_passed_runs": int(
                        _number(row.get("ops_provider_broker_roundtrip_passed_runs", 0))
                    ),
                    "ops_provider_broker_roundtrip_synthetic_dataset_count": int(
                        _number(row.get("ops_provider_broker_roundtrip_synthetic_dataset_count", 0))
                    ),
                    "ops_provider_broker_roundtrip_synthetic_sidecar_count": int(
                        _number(row.get("ops_provider_broker_roundtrip_synthetic_sidecar_count", 0))
                    ),
                    "ops_provider_broker_roundtrip_synthetic_sidecar_readable_count": int(
                        _number(row.get("ops_provider_broker_roundtrip_synthetic_sidecar_readable_count", 0))
                    ),
                    "ops_provider_broker_roundtrip_synthetic_sidecar_proof_runs": int(
                        _number(row.get("ops_provider_broker_roundtrip_synthetic_sidecar_proof_runs", 0))
                    ),
                    "ops_provider_broker_roundtrip_synthetic_sidecar_ready_runs": int(
                        _number(row.get("ops_provider_broker_roundtrip_synthetic_sidecar_ready_runs", 0))
                    ),
                    "ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs": int(
                        _number(row.get("ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs", 0))
                    ),
                    "ops_provider_lineage_selected_run_count": int(
                        _number(row.get("ops_provider_lineage_selected_run_count", 0))
                    ),
                    "ops_provider_lineage_selected_pair_count": int(
                        _number(row.get("ops_provider_lineage_selected_pair_count", 0))
                    ),
                    "ops_provider_lineage_selected_pair_ids": _text(
                        row.get("ops_provider_lineage_selected_pair_ids", "")
                    ),
                    "ops_provider_lineage_selected_run_dirs": _text(
                        row.get("ops_provider_lineage_selected_run_dirs", "")
                    ),
                    "ops_provider_lineage_selection_contract_version": _text(
                        row.get("ops_provider_lineage_selection_contract_version", "")
                    ),
                    "ops_provider_lineage_selection_contract_sha256": _text(
                        row.get("ops_provider_lineage_selection_contract_sha256", "")
                    ),
                    "ops_provider_lineage_selection_artifact": _text(
                        row.get("ops_provider_lineage_selection_artifact", "")
                    ),
                    "recommendation": _route_action_recommendation(row),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "strategy",
            "market",
            "status",
            "blocker",
            "next_gate",
            "next_gate_help_command",
            "strategy_evidence_profile",
            "strategy_evidence_status",
            "ops_evidence_profile",
            "ops_evidence_status",
            "ops_file_inputs_required",
            "ops_non_file_input_count",
            "ops_launch_controls_ready",
            "ops_launch_control_failures",
            "ops_broker_roundtrip_portfolio_safe_runs",
            "ops_broker_roundtrip_portfolio_breach_runs",
            "ops_broker_roundtrip_portfolio_concentration_ok_runs",
            "ops_broker_roundtrip_portfolio_concentration_breach_runs",
            "ops_broker_roundtrip_resume_route_ready_runs",
            "ops_broker_roundtrip_resume_route_breach_runs",
            "ops_broker_roundtrip_resume_route_gap_breach_runs",
            "ops_broker_roundtrip_resume_route_launch_control_breach_runs",
            "ops_broker_roundtrip_resume_route_portfolio_breach_runs",
            "ops_broker_roundtrip_resume_route_concentration_breach_runs",
            "ops_provider_broker_roundtrip_runs",
            "ops_provider_broker_roundtrip_passed_runs",
            "ops_provider_broker_roundtrip_synthetic_dataset_count",
            "ops_provider_broker_roundtrip_synthetic_sidecar_count",
            "ops_provider_broker_roundtrip_synthetic_sidecar_readable_count",
            "ops_provider_broker_roundtrip_synthetic_sidecar_proof_runs",
            "ops_provider_broker_roundtrip_synthetic_sidecar_ready_runs",
            "ops_provider_broker_roundtrip_synthetic_sidecar_breach_runs",
            "ops_provider_lineage_selected_run_count",
            "ops_provider_lineage_selected_pair_count",
            "ops_provider_lineage_selected_pair_ids",
            "ops_provider_lineage_selected_run_dirs",
            "ops_provider_lineage_selection_contract_version",
            "ops_provider_lineage_selection_contract_sha256",
            "ops_provider_lineage_selection_artifact",
            "recommendation",
        ],
    )


def _route_action_recommendation(row: dict[str, Any]) -> str:
    if bool(row.get("route_ready", False)):
        return "ready_for_live_dryrun_route_review"
    status = _text(row.get("status"))
    if status == "ops_evidence_incomplete":
        return _text(row.get("ops_evidence_recommendation")) or "complete_ops_launch_evidence"
    if status.startswith("ops"):
        return "complete_ops_launch_evidence"
    if status == "strategy_evidence_incomplete":
        return _text(row.get("strategy_evidence_recommendation")) or "complete_strategy_evidence"
    if status.startswith("strategy"):
        return "complete_strategy_evidence"
    if status == "blocked_by_portability":
        return "resolve_market_portability_gap"
    return "complete_route_readiness_gaps"


def _runbook_markdown(
    summary_row: pd.Series,
    pairs: pd.DataFrame,
    gaps: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Route Readiness Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Recommendation: {_text(summary_row.get('recommendation'))}",
        f"- Route-ready pairs: {int(_number(summary_row.get('route_ready_pairs', 0)))}",
        f"- Gap pairs: {int(_number(summary_row.get('gap_pairs', 0)))}",
        f"- Require ops file inputs: {str(_to_bool(summary_row.get('require_ops_file_inputs', False))).lower()}",
        "",
        "## Action Queue",
        "",
        _action_queue_table(action_queue),
        "",
        "## Route Pairs",
        "",
        _pairs_table(pairs),
        "",
        "## Gaps",
        "",
        _pairs_table(gaps),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Status", "Strategy", "Market", "Next gate", "Help", "Ops controls", "Recommendation"],
        [
            [
                str(int(_number(row.get("priority", 0)))),
                _text(row.get("queue_status")),
                _text(row.get("strategy")),
                _text(row.get("market")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _text(row.get("ops_launch_control_failures")),
                _text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _pairs_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_None_"
    return _markdown_table(
        ["Strategy", "Market", "Status", "Blocker", "Ops controls", "Next gate"],
        [
            [
                _text(row.get("strategy")),
                _text(row.get("market")),
                _text(row.get("status")),
                _text(row.get("blocker")),
                _text(row.get("ops_launch_control_failures")),
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
    return _text(value).replace("|", "\\|")


def _read_evidence_summaries(paths: tuple[str | Path, ...]) -> tuple[list[Path], pd.DataFrame]:
    summary_paths = [_evidence_summary_path(path) for path in paths]
    rows: list[dict[str, Any]] = []
    for path in summary_paths:
        frame = pd.read_csv(path)
        for _, row in frame.iterrows():
            item = row.to_dict()
            item["source_path"] = str(path)
            rows.append(item)
    return summary_paths, pd.DataFrame(rows)


def _normalize_evidence_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(
            columns=[
                "ready",
                "evidence_profile",
                "strategy",
                "market",
                "recommendation",
                "require_file_inputs",
                "input_directory_count",
                "input_other_count",
                "input_unfingerprinted_count",
                "source_path",
            ]
        )
    normalized = frame.copy()
    for column in [
        "ready",
        "evidence_profile",
        "strategy",
        "market",
        "recommendation",
        "require_file_inputs",
        "require_no_blocked_placeholder_schema",
        "placeholder_schema_blocked_runs",
        "require_broker_roundtrip_portfolio_safe",
        "fail_on_broker_roundtrip_portfolio_breach",
        "broker_roundtrip_portfolio_safe_runs",
        "broker_roundtrip_portfolio_breach_runs",
        "require_broker_roundtrip_portfolio_concentration_ok",
        "fail_on_broker_roundtrip_portfolio_concentration_breach",
        "broker_roundtrip_portfolio_concentration_ok_runs",
        "broker_roundtrip_portfolio_concentration_breach_runs",
        "require_broker_roundtrip_resume_route_ready",
        "fail_on_broker_roundtrip_resume_route_breach",
        "broker_roundtrip_resume_route_ready_runs",
        "broker_roundtrip_resume_route_breach_runs",
        "broker_roundtrip_resume_route_gap_breach_runs",
        "broker_roundtrip_resume_route_launch_control_breach_runs",
        "broker_roundtrip_resume_route_portfolio_breach_runs",
        "broker_roundtrip_resume_route_concentration_breach_runs",
        "require_provider_broker_roundtrip_synthetic_sidecar_ready",
        "fail_on_provider_broker_roundtrip_synthetic_sidecar_breach",
        "provider_broker_roundtrip_runs",
        "provider_broker_roundtrip_passed_runs",
        "provider_broker_roundtrip_synthetic_dataset_count",
        "provider_broker_roundtrip_synthetic_sidecar_count",
        "provider_broker_roundtrip_synthetic_sidecar_readable_count",
        "provider_broker_roundtrip_synthetic_sidecar_proof_runs",
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs",
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs",
        "require_provider_lineage_selection",
        "provider_lineage_selection_policy",
        "provider_lineage_required_run_type_count",
        "provider_lineage_covered_run_type_count",
        "provider_lineage_selectable_runs",
        "provider_lineage_selection_blocked_runs",
        "provider_lineage_selected_run_count",
        "provider_lineage_selected_pair_count",
        "provider_lineage_selected_pair_ids",
        "provider_lineage_selected_run_dirs",
        "provider_lineage_selection_contract_version",
        "provider_lineage_selection_contract_sha256",
        "provider_lineage_selection_artifact",
        "input_directory_count",
        "input_other_count",
        "input_unfingerprinted_count",
        "source_path",
    ]:
        if column not in normalized.columns:
            normalized[column] = False if column in _EVIDENCE_BOOL_COLUMNS else 0 if column in _EVIDENCE_COUNT_COLUMNS else ""
    return normalized


def _market_portability_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "market_portability_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"market portability config not found: {candidate}")
    return candidate


def _evidence_summary_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "strategy_evidence_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"strategy evidence summary not found: {candidate}")
    return candidate


def _normalize_strategy(value: Any) -> str:
    normalized = _normalize_identity(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(normalized, normalized)


def _normalize_identity(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _semicolon_values(value: Any) -> list[str]:
    return [
        item.strip().lower()
        for item in _text(value).split(";")
        if item.strip()
    ]


def _valid_sha256(value: Any) -> bool:
    candidate = _text(value).strip().lower()
    return len(candidate) == 64 and all(
        character in "0123456789abcdef" for character in candidate
    )


def _number(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if pd.isna(number):
        return 0
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


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
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
