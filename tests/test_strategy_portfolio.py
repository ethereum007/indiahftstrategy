import json

import pandas as pd
import pytest

from hft_cli import main
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.strategy_portfolio import (
    StrategyPortfolioConfig,
    evaluate_strategy_portfolio,
    write_strategy_portfolio_allocations,
)


def scorecard_row(
    rank,
    profile,
    strategy,
    *,
    ready=True,
    readiness_score=1.0,
    market="india_nse_index_derivatives",
    next_gate="plan-scaleup",
):
    return {
        "rank": rank,
        "profile": profile,
        "strategy": strategy,
        "market": market,
        "ready": ready,
        "readiness_score": readiness_score,
        "passed_required_run_types": int(round(readiness_score * 6)),
        "required_run_type_count": 6,
        "missing_required_run_types": "" if ready else "imbalance_replay_walkforward",
        "blocked_required_run_types": "",
        "next_required_run_type": "" if ready else "imbalance_replay_walkforward",
        "next_gate": next_gate,
        "next_gate_help_command": f"python -m hft_cli {next_gate} --help",
        "failed_checks": 0 if ready else 1,
        "dirty_runs": 0,
        "git_commit_count": 1,
        "latest_generated_at_utc": "2026-06-18T09:30:00Z",
        "recommendation": "ready_for_shadow_scaleup_review" if ready else "complete_profile_evidence_gaps",
    }


def mixed_scorecard():
    return pd.DataFrame(
        [
            scorecard_row(1, "leadlag", "lead_lag_taker"),
            scorecard_row(2, "parity", "parity_box"),
            scorecard_row(
                3,
                "imbalance",
                "imbalance",
                ready=False,
                readiness_score=0.4,
                next_gate="walkforward-imbalance-replay",
            ),
        ]
    )


def same_strategy_scorecard():
    return pd.DataFrame(
        [
            scorecard_row(1, "leadlag_fast", "lead_lag_taker"),
            scorecard_row(2, "leadlag_slow", "lead_lag_taker"),
        ]
    )


def write_research_family_bundle(root):
    root.mkdir(parents=True, exist_ok=True)
    source = root / "registered_source.csv"
    pd.DataFrame([{"study": "study_001", "pvalue": 0.01}]).to_csv(
        source,
        index=False,
    )
    selected_candidate = {
        "study_label": "study_001",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "candidate_scenario": "scenario=leadlag",
        "holm_adjusted_pvalue": 0.01,
        "family_passed": True,
    }
    pd.DataFrame([selected_candidate]).to_csv(
        root / "research_family_studies.csv",
        index=False,
    )
    pd.DataFrame([{"check": "family_closed", "passed": True}]).to_csv(
        root / "research_family_checks.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "ready": True,
                "passed": True,
                "family_id": "family_001",
                "registration_id": "registration_001",
                "prospective_registration_passed": True,
                "registration_closed": True,
                "family_wise_error_control_claimed": True,
                "family_candidate_count": 1,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(root / "research_family_summary.csv", index=False)
    pd.DataFrame([{"priority": 1, "queue_status": "ready"}]).to_csv(
        root / "research_family_action_queue.csv",
        index=False,
    )
    pd.DataFrame([{"study_label": "study_001", "attempt_count": 1}]).to_csv(
        root / "research_family_launch_attempt_census.csv",
        index=False,
    )
    (root / "research_family_config.json").write_text(
        json.dumps(
            {
                "passed": True,
                "parameters": {"family_id": "family_001"},
                "summary": {
                    "family_id": "family_001",
                    "registration_id": "registration_001",
                    "registration_closed": True,
                },
                "selected_candidates": [selected_candidate],
                "authorizes_submission": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "research_family_runbook.md").write_text(
        "# Research Family\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        root,
        run_type="research_family_audit",
        inputs={"registered_source": source},
        extra={
            "passed": True,
            "family_id": "family_001",
            "registration_id": "registration_001",
            "prospective_registration_passed": True,
            "registration_closed": True,
            "family_wise_error_control_claimed": True,
            "authorizes_submission": False,
        },
    )
    return file_sha256(root / "manifest.json")


def family_bound_scorecard(family_root, family_manifest_sha):
    frame = mixed_scorecard().iloc[:1].copy()
    frame["research_family_applicable"] = True
    frame["research_family_enabled"] = True
    frame["research_family_required"] = True
    frame["registered_research_detected"] = True
    frame["research_family_provided"] = True
    frame["research_family_gate_passed"] = True
    frame["research_family_reason"] = "registered research family closed"
    frame["research_family_manifest_current"] = True
    frame["research_family_valid"] = True
    frame["research_family_id"] = "family_001"
    frame["research_family_registration_id"] = "registration_001"
    frame["research_family_path"] = str(family_root)
    frame["research_family_manifest_sha256"] = family_manifest_sha
    frame["research_family_registration_closed"] = True
    frame["research_family_error_control_claimed"] = True
    frame["research_family_candidate_identity"] = "scenario=leadlag"
    frame["research_family_candidate_identity_count"] = 1
    frame["research_family_candidate_consistent"] = True
    frame["research_family_candidate_match"] = True
    frame["research_family_matched_study_label"] = "study_001"
    frame["research_family_matched_holm_adjusted_pvalue"] = 0.01
    frame["authorizes_submission"] = False
    return frame


def write_scorecard_bundle(root, frame, *, contract_mismatch=False):
    root.mkdir(parents=True, exist_ok=True)
    frame.to_csv(root / "strategy_scorecard.csv", index=False)
    pd.DataFrame(columns=["profile", "gap"]).to_csv(
        root / "strategy_scorecard_gaps.csv",
        index=False,
    )
    ready = frame["ready"].map(bool)
    family_enabled = frame.get(
        "research_family_enabled",
        pd.Series(False, index=frame.index),
    ).map(bool)
    family_passed = frame.get(
        "research_family_gate_passed",
        pd.Series(False, index=frame.index),
    ).map(bool)
    registered = frame.get(
        "registered_research_detected",
        pd.Series(False, index=frame.index),
    ).map(bool)
    family_rows = frame.loc[family_enabled | registered]
    reference = family_rows.iloc[0].to_dict() if not family_rows.empty else {}
    summary = {
        "ready": bool(ready.any()),
        "profile_count": len(frame),
        "ready_profiles": int(ready.sum()),
        "blocked_profiles": int((~ready).sum()),
        "registered_research_profiles": int(registered.sum()),
        "research_family_gate_passed_profiles": int(
            (family_enabled & family_passed).sum()
        ),
        "research_family_id": reference.get("research_family_id", ""),
        "research_family_registration_id": reference.get(
            "research_family_registration_id",
            "",
        ),
        "research_family_path": reference.get("research_family_path", ""),
        "research_family_manifest_sha256": reference.get(
            "research_family_manifest_sha256",
            "",
        ),
        "authorizes_submission": False,
    }
    pd.DataFrame([summary]).to_csv(
        root / "strategy_scorecard_summary.csv",
        index=False,
    )
    actions = []
    for _, row in frame.iterrows():
        actions.append(
            {
                "profile": row.get("profile", ""),
                "strategy": row.get("strategy", ""),
                "market": row.get("market", ""),
                "ready": bool(row.get("ready", False)),
                "readiness_score": float(row.get("readiness_score", 0.0)),
                "research_family_enabled": bool(
                    row.get("research_family_enabled", False)
                ),
                "research_family_required": bool(
                    row.get("research_family_required", False)
                ),
                "registered_research_detected": bool(
                    row.get("registered_research_detected", False)
                ),
                "research_family_provided": bool(
                    row.get("research_family_provided", False)
                ),
                "research_family_gate_passed": bool(
                    row.get("research_family_gate_passed", False)
                ),
                "research_family_manifest_current": bool(
                    row.get("research_family_manifest_current", False)
                ),
                "research_family_valid": bool(
                    row.get("research_family_valid", False)
                ),
                "research_family_id": row.get("research_family_id", ""),
                "research_family_registration_id": row.get(
                    "research_family_registration_id",
                    "",
                ),
                "research_family_manifest_sha256": row.get(
                    "research_family_manifest_sha256",
                    "",
                ),
                "research_family_candidate_identity": row.get(
                    "research_family_candidate_identity",
                    "",
                ),
                "research_family_candidate_match": bool(
                    row.get("research_family_candidate_match", False)
                ),
                "research_family_matched_study_label": row.get(
                    "research_family_matched_study_label",
                    "",
                ),
                "research_family_matched_holm_adjusted_pvalue": float(
                    row.get(
                        "research_family_matched_holm_adjusted_pvalue",
                        0.0,
                    )
                ),
                "authorizes_submission": False,
            }
        )
    config = {
        "ready": bool(ready.any()),
        "ready_action_count": int(ready.sum()),
        "blocked_action_count": int((~ready).sum()),
        "research_family_id": reference.get("research_family_id", ""),
        "research_family_registration_id": reference.get(
            "research_family_registration_id",
            "",
        ),
        "research_family_path": reference.get("research_family_path", ""),
        "research_family_manifest_sha256": reference.get(
            "research_family_manifest_sha256",
            "",
        ),
        "authorizes_submission": False,
        "next_actions": actions,
    }
    if contract_mismatch:
        config["research_family_id"] = "different_family"
    (root / "strategy_scorecard_next_actions.json").write_text(
        json.dumps(config),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "priority": index + 1,
                "queue_status": "ready" if action["ready"] else "blocked",
                "profile": action["profile"],
            }
            for index, action in enumerate(actions)
        ]
    ).to_csv(root / "strategy_scorecard_action_queue.csv", index=False)
    (root / "strategy_scorecard_runbook.md").write_text(
        "# Strategy Scorecard\n",
        encoding="utf-8",
    )
    source = root / "catalog.csv"
    pd.DataFrame([{"run_type": "robust_selection_pipeline"}]).to_csv(
        source,
        index=False,
    )
    inputs = {"catalog": source}
    family_path = reference.get("research_family_path", "")
    if family_path:
        inputs["research_family_audit"] = family_path
        inputs["research_family_manifest"] = (
            family_path / "manifest.json"
            if hasattr(family_path, "__truediv__")
            else str(family_path) + "/manifest.json"
        )
    write_experiment_manifest(
        root,
        run_type="strategy_scorecard",
        inputs=inputs,
        extra={
            "ready": bool(ready.any()),
            "research_family_provided": bool(
                frame.get(
                    "research_family_provided",
                    pd.Series(False, index=frame.index),
                ).map(bool).any()
            ),
            "research_family_id": reference.get("research_family_id", ""),
            "research_family_manifest_sha256": reference.get(
                "research_family_manifest_sha256",
                "",
            ),
            "registered_research_profiles": int(registered.sum()),
            "research_family_gate_passed_profiles": int(
                (family_enabled & family_passed).sum()
            ),
            "authorizes_submission": False,
        },
    )


def test_strategy_portfolio_allocates_ready_profiles_with_reserve():
    report = evaluate_strategy_portfolio(
        mixed_scorecard(),
        config=StrategyPortfolioConfig(total_capital=1_000_000, reserve_weight=0.10, max_profile_weight=0.60),
    )

    allocations = report.allocations.set_index("profile")
    assert report.ready
    assert bool(allocations.loc["leadlag", "eligible"])
    assert bool(allocations.loc["parity", "eligible"])
    assert not bool(allocations.loc["imbalance", "eligible"])
    assert allocations.loc["imbalance", "eligibility_reason"] == "profile_not_ready"
    assert allocations.loc["leadlag", "allocation_weight"] == 0.45
    assert allocations.loc["parity", "allocation_weight"] == 0.45
    assert allocations.loc["leadlag", "allocation_notional"] == 450_000
    assert report.summary.loc[0, "allocated_weight"] == 0.90
    assert report.summary.loc[0, "reserve_notional"] == 100_000
    assert report.summary.loc[0, "allocated_strategy_count"] == 2
    assert report.summary.loc[0, "allocated_market_count"] == 1
    assert report.summary.loc[0, "max_strategy_allocation_weight"] == 0.45
    assert report.summary.loc[0, "max_market_allocation_weight"] == 0.90
    assert int(report.summary.loc[0, "failed_check_count"]) == 0
    assert report.config["schema_version"] == 1
    assert report.config["allocation_count"] == 2
    assert report.config["ready_allocations"][0]["profile"] == "leadlag"
    assert report.config["blocked_allocations"][0]["profile"] == "imbalance"
    assert report.action_queue is not None
    assert int(report.summary.loc[0, "action_queue_count"]) == 3
    assert int(report.summary.loc[0, "ready_action_count"]) == 2
    assert int(report.summary.loc[0, "blocked_action_count"]) == 1
    assert report.summary.loc[0, "next_gate"] == "plan-scaleup"
    assert report.config["action_queue_count"] == 3
    assert report.config["ready_action_count"] == 2
    assert report.config["blocked_action_count"] == 1
    assert report.config["primary_action_status"] == "ready"
    assert report.config["primary_action"]["profile"] == "leadlag"
    assert {item["profile"] for item in report.config["ready_actions"]} == {"leadlag", "parity"}
    assert {item["profile"] for item in report.config["blocked_actions"]} == {"imbalance"}


def test_strategy_portfolio_caps_profiles_and_leaves_unallocated_budget():
    report = evaluate_strategy_portfolio(
        mixed_scorecard().iloc[:2],
        config=StrategyPortfolioConfig(total_capital=1_000, reserve_weight=0.0, max_profile_weight=0.40),
    )

    allocations = report.allocations.set_index("profile")
    assert report.ready
    assert allocations.loc["leadlag", "allocation_weight"] == 0.40
    assert allocations.loc["parity", "allocation_weight"] == 0.40
    assert report.summary.loc[0, "allocated_weight"] == 0.80
    assert round(report.summary.loc[0, "unallocated_weight"], 6) == 0.20


def test_strategy_portfolio_blocks_strategy_concentration_when_requested():
    report = evaluate_strategy_portfolio(
        same_strategy_scorecard(),
        config=StrategyPortfolioConfig(
            total_capital=1_000_000,
            reserve_weight=0.10,
            max_profile_weight=0.60,
            min_strategy_count=2,
            max_strategy_weight=0.50,
        ),
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert report.summary.loc[0, "allocated_strategy_count"] == 1
    assert report.summary.loc[0, "top_strategy_by_weight"] == "lead_lag_taker"
    assert report.summary.loc[0, "max_strategy_allocation_weight"] == 0.90
    assert not bool(checks.loc["allocated_strategy_count", "passed"])
    assert not bool(checks.loc["max_strategy_allocation_weight", "passed"])
    assert report.config["allocation_config"]["min_strategy_count"] == 2
    assert report.config["allocation_config"]["max_strategy_weight"] == 0.50
    assert "allocated_strategy_count" in set(report.action_queue["check"])
    assert "max_strategy_allocation_weight" in set(report.action_queue["check"])


def test_strategy_portfolio_blocks_market_concentration_when_requested():
    report = evaluate_strategy_portfolio(
        mixed_scorecard().iloc[:2],
        config=StrategyPortfolioConfig(
            total_capital=1_000_000,
            reserve_weight=0.10,
            max_profile_weight=0.60,
            min_market_count=2,
            max_market_weight=0.50,
        ),
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert report.summary.loc[0, "allocated_market_count"] == 1
    assert report.summary.loc[0, "top_market_by_weight"] == "india_nse_index_derivatives"
    assert report.summary.loc[0, "max_market_allocation_weight"] == 0.90
    assert not bool(checks.loc["allocated_market_count", "passed"])
    assert not bool(checks.loc["max_market_allocation_weight", "passed"])
    assert report.config["allocation_config"]["min_market_count"] == 2
    assert report.config["allocation_config"]["max_market_weight"] == 0.50
    assert "allocated_market_count" in set(report.action_queue["check"])
    assert "max_market_allocation_weight" in set(report.action_queue["check"])


def test_strategy_portfolio_fails_closed_when_no_profile_is_ready():
    report = evaluate_strategy_portfolio(
        pd.DataFrame(
            [
                scorecard_row(
                    1,
                    "imbalance",
                    "imbalance",
                    ready=False,
                    readiness_score=0.8,
                    next_gate="walkforward-imbalance-replay",
                )
            ]
        )
    )

    assert not report.ready
    assert int(report.summary.loc[0, "failed_check_count"]) == 2
    assert report.summary.loc[0, "primary_blocker_check"] == "eligible_profile_count"
    assert report.summary.loc[0, "first_failed_reason"] == (
        "at least one strategy profile must pass readiness filters before allocation"
    )
    assert report.config["failed_checks"][0] == "eligible_profile_count"
    assert report.config["primary_blocker"]["check"] == "eligible_profile_count"
    assert report.action_queue is not None
    assert set(report.action_queue["queue_status"]) == {"blocked"}
    assert "profile_eligible:imbalance" in set(report.action_queue["check"])
    assert "eligible_profile_count" in set(report.action_queue["check"])
    assert int(report.summary.loc[0, "blocked_action_count"]) == len(report.action_queue)
    assert report.config["primary_action_status"] == "blocked"
    assert report.config["next_gate"] == "walkforward-imbalance-replay"


def test_write_strategy_portfolio_outputs_files_and_manifest(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    out_dir = tmp_path / "portfolio"
    mixed_scorecard().to_csv(scorecard_path, index=False)

    report = write_strategy_portfolio_allocations(
        scorecard_path,
        output_dir=out_dir,
        config=StrategyPortfolioConfig(total_capital=500_000, reserve_weight=0.20, max_profile_weight=0.50),
    )

    assert report.output_dir == out_dir
    assert report.ready
    assert (out_dir / "strategy_portfolio_allocations.csv").exists()
    assert (out_dir / "strategy_portfolio_checks.csv").exists()
    assert (out_dir / "strategy_portfolio_summary.csv").exists()
    assert (out_dir / "strategy_portfolio_action_queue.csv").exists()
    assert (out_dir / "strategy_portfolio_config.json").exists()
    assert (out_dir / "strategy_portfolio_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "strategy_portfolio_action_queue.csv")
    config = json.loads((out_dir / "strategy_portfolio_config.json").read_text(encoding="utf-8"))
    assert config == report.config
    assert config["ready"]
    assert config["allocation_config"]["total_capital"] == 500_000
    assert len(action_queue) == config["action_queue_count"]
    assert int((action_queue["queue_status"] == "ready").sum()) == config["ready_action_count"]
    assert int((action_queue["queue_status"] == "blocked").sum()) == config["blocked_action_count"]
    runbook = (out_dir / "strategy_portfolio_runbook.md").read_text(encoding="utf-8")
    assert "# Strategy Portfolio Allocation Runbook" in runbook
    assert "## Allocations" in runbook
    assert "## Scheduler Actions" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "strategy_portfolio_allocations.csv" in artifact_paths
    assert "strategy_portfolio_action_queue.csv" in artifact_paths
    assert "strategy_portfolio_runbook.md" in artifact_paths


def test_strategy_portfolio_carries_current_family_bound_scorecard_proof(tmp_path):
    family_root = tmp_path / "family"
    family_sha = write_research_family_bundle(family_root)
    scorecard_root = tmp_path / "scorecard"
    write_scorecard_bundle(
        scorecard_root,
        family_bound_scorecard(family_root, family_sha),
    )
    out_dir = tmp_path / "portfolio"

    report = write_strategy_portfolio_allocations(
        scorecard_root,
        output_dir=out_dir,
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )

    assert report.ready
    allocation = report.allocations.iloc[0]
    assert allocation["allocation_weight"] == 0.90
    assert bool(allocation["scorecard_manifest_current"])
    assert bool(allocation["scorecard_contract_consistent"])
    assert bool(allocation["research_family_provenance_current"])
    assert allocation["research_family_id"] == "family_001"
    assert allocation["research_family_registration_id"] == "registration_001"
    assert allocation["research_family_manifest_sha256"] == family_sha
    assert allocation["research_family_matched_study_label"] == "study_001"
    assert not bool(allocation["authorizes_submission"])
    provenance = report.config["scorecard_provenance"]
    assert provenance["manifest_required"]
    assert provenance["manifest_current"]
    assert provenance["contract_consistent"]
    assert provenance["research_family_provenance_current"]
    assert not report.config["authorizes_submission"]

    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    )
    assert integrity.passed
    catalog_path = scorecard_root / "catalog.csv"
    original_catalog = catalog_path.read_text(encoding="utf-8")
    catalog_path.write_text(original_catalog + "\n", encoding="utf-8")
    nested_input_drift = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    )
    assert not nested_input_drift.passed
    assert nested_input_drift.error == "input_drift"
    catalog_path.write_text(original_catalog, encoding="utf-8")
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    ).passed
    family_source = family_root / "registered_source.csv"
    original_family_source = family_source.read_text(encoding="utf-8")
    family_source.write_text(
        original_family_source + "\n",
        encoding="utf-8",
    )
    recursive_input_drift = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    )
    assert not recursive_input_drift.passed
    assert recursive_input_drift.error == "input_drift"
    family_source.write_text(original_family_source, encoding="utf-8")
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    ).passed
    family_studies = family_root / "research_family_studies.csv"
    family_studies.write_text(
        family_studies.read_text(encoding="utf-8") + "study_002,True\n",
        encoding="utf-8",
    )
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_strategy_portfolio_blocks_family_bound_csv_without_scorecard_manifest(tmp_path):
    family_root = tmp_path / "family"
    family_sha = write_research_family_bundle(family_root)
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    family_bound_scorecard(family_root, family_sha).to_csv(
        scorecard_path,
        index=False,
    )
    in_memory = evaluate_strategy_portfolio(
        family_bound_scorecard(family_root, family_sha),
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )
    assert not in_memory.ready
    assert in_memory.allocations.loc[0, "allocation_weight"] == 0.0

    report = write_strategy_portfolio_allocations(
        scorecard_path,
        output_dir=tmp_path / "portfolio",
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert not bool(checks.loc["scorecard_manifest_provided", "passed"])
    assert report.allocations.loc[0, "allocation_weight"] == 0.0
    assert (
        report.allocations.loc[0, "eligibility_reason"]
        == "scorecard_provenance_not_current"
    )
    assert report.summary.loc[0, "primary_blocker_check"] == (
        "scorecard_manifest_provided"
    )
    assert report.action_queue.iloc[0]["next_gate"] == (
        "score-strategy-readiness"
    )


def test_strategy_portfolio_blocks_stale_family_bound_scorecard_bundle(tmp_path):
    family_root = tmp_path / "family"
    family_sha = write_research_family_bundle(family_root)
    scorecard_root = tmp_path / "scorecard"
    scorecard = family_bound_scorecard(family_root, family_sha)
    write_scorecard_bundle(scorecard_root, scorecard)
    scorecard.loc[0, "readiness_score"] = 0.99
    scorecard.to_csv(scorecard_root / "strategy_scorecard.csv", index=False)

    report = write_strategy_portfolio_allocations(
        scorecard_root,
        output_dir=tmp_path / "portfolio",
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert not bool(checks.loc["scorecard_manifest_current", "passed"])
    assert report.config["scorecard_provenance"]["manifest_error"] == (
        "artifact_drift"
    )
    assert report.allocations.loc[0, "allocation_weight"] == 0.0


def test_strategy_portfolio_blocks_fresh_but_inconsistent_scorecard_contract(tmp_path):
    family_root = tmp_path / "family"
    family_sha = write_research_family_bundle(family_root)
    scorecard_root = tmp_path / "scorecard"
    write_scorecard_bundle(
        scorecard_root,
        family_bound_scorecard(family_root, family_sha),
        contract_mismatch=True,
    )

    report = write_strategy_portfolio_allocations(
        scorecard_root,
        output_dir=tmp_path / "portfolio",
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert bool(checks.loc["scorecard_manifest_current", "passed"])
    assert not bool(checks.loc["scorecard_contract_consistent", "passed"])
    assert "config_research_family_id_mismatch" in report.config[
        "scorecard_provenance"
    ]["contract_error"]
    assert report.allocations.loc[0, "allocation_weight"] == 0.0


def test_strategy_portfolio_blocks_fresh_scorecard_relabeling_family_bundle(tmp_path):
    family_root = tmp_path / "family"
    family_sha = write_research_family_bundle(family_root)
    scorecard_root = tmp_path / "scorecard"
    scorecard = family_bound_scorecard(family_root, family_sha)
    scorecard["research_family_id"] = "relabeled_family"
    write_scorecard_bundle(scorecard_root, scorecard)

    report = write_strategy_portfolio_allocations(
        scorecard_root,
        output_dir=tmp_path / "portfolio",
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert bool(checks.loc["scorecard_manifest_current", "passed"])
    assert bool(checks.loc["scorecard_contract_consistent", "passed"])
    assert not bool(
        checks.loc["research_family_provenance_current", "passed"]
    )
    assert "research_family_id_mismatch:summary" in report.config[
        "scorecard_provenance"
    ]["research_family_provenance_error"]
    assert report.allocations.loc[0, "allocation_weight"] == 0.0


def test_cli_strategy_portfolio_can_require_manifest_for_plain_scorecard(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    mixed_scorecard().iloc[:1].to_csv(scorecard_path, index=False)
    out_dir = tmp_path / "portfolio"

    code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(out_dir),
            "--require-scorecard-manifest",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "strategy_portfolio_checks.csv").set_index(
        "check"
    )
    assert code == 2
    assert not bool(checks.loc["scorecard_manifest_provided", "passed"])
    assert not bool(
        pd.read_csv(out_dir / "strategy_portfolio_summary.csv").loc[0, "ready"]
    )


def test_strategy_portfolio_refuses_to_overwrite_scorecard_bundle(tmp_path):
    scorecard_root = tmp_path / "scorecard"
    write_scorecard_bundle(scorecard_root, mixed_scorecard().iloc[:1])

    with pytest.raises(ValueError, match="must not overwrite"):
        write_strategy_portfolio_allocations(
            scorecard_root,
            output_dir=scorecard_root,
        )


def test_strategy_portfolio_rejects_authorizing_source_but_emits_non_authorizing_rows(
    tmp_path,
):
    scorecard_root = tmp_path / "scorecard"
    scorecard = mixed_scorecard().iloc[:1].copy()
    scorecard["authorizes_submission"] = True
    write_scorecard_bundle(scorecard_root, scorecard)

    report = write_strategy_portfolio_allocations(
        scorecard_root,
        output_dir=tmp_path / "portfolio",
    )

    checks = report.checks.set_index("check")
    assert not report.ready
    assert not bool(checks.loc["scorecard_non_authorizing", "passed"])
    assert report.allocations.loc[0, "allocation_weight"] == 0.0
    assert not bool(report.allocations.loc[0, "authorizes_submission"])
    assert not report.config["authorizes_submission"]


def test_cli_strategy_portfolio_returns_breach_when_no_profile_is_ready(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    out_dir = tmp_path / "portfolio"
    blocked_dir = tmp_path / "portfolio_blocked"
    actions_dir = tmp_path / "portfolio_actions"
    pd.DataFrame(
        [
            scorecard_row(
                1,
                "imbalance",
                "imbalance",
                ready=False,
                readiness_score=0.8,
                next_gate="walkforward-imbalance-replay",
            )
        ]
    ).to_csv(scorecard_path, index=False)

    code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(out_dir),
            "--total-capital",
            "1000000",
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.5",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "strategy_portfolio_summary.csv")
    checks = pd.read_csv(out_dir / "strategy_portfolio_checks.csv")
    action_queue = pd.read_csv(out_dir / "strategy_portfolio_action_queue.csv")
    config = json.loads((out_dir / "strategy_portfolio_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "primary_blocker_check"] == "eligible_profile_count"
    assert "eligible_profile_count" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "blocked_action_count"]) == len(action_queue)
    assert config["primary_blocker"]["check"] == "eligible_profile_count"
    assert config["blocked_action_count"] == len(action_queue)
    assert config["primary_action_status"] == "blocked"

    blocked_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(blocked_dir),
            "--total-capital",
            "1000000",
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.5",
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(actions_dir),
            "--total-capital",
            "1000000",
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.5",
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


def test_cli_strategy_portfolio_action_gates_on_ready_allocation(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    blocked_dir = tmp_path / "portfolio_blocked"
    actions_dir = tmp_path / "portfolio_actions"
    mixed_scorecard().iloc[:2].to_csv(scorecard_path, index=False)

    blocked_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(blocked_dir),
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(actions_dir),
            "--fail-on-actions",
        ]
    )

    assert blocked_code == 0
    assert actions_code == 2


def test_cli_strategy_portfolio_fails_on_diversity_gate(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    out_dir = tmp_path / "portfolio"
    same_strategy_scorecard().to_csv(scorecard_path, index=False)

    code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(out_dir),
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.6",
            "--min-strategy-count",
            "2",
            "--max-strategy-weight",
            "0.5",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "strategy_portfolio_summary.csv")
    checks = pd.read_csv(out_dir / "strategy_portfolio_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "allocated_strategy_count"] == 1
    assert summary.loc[0, "top_strategy_by_weight"] == "lead_lag_taker"
    assert {"allocated_strategy_count", "max_strategy_allocation_weight"}.issubset(
        set(checks.loc[~checks["passed"].astype(bool), "check"])
    )
