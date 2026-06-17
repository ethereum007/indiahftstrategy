import json

import pandas as pd

from hft_cli import main
from reports.market_portability import MarketPortabilityReportConfig, build_market_portability_report, write_market_portability_report
from reports.route_readiness import build_route_readiness_review, write_route_readiness_review


def evidence_summary(
    *,
    profile: str,
    strategy: str = "imbalance",
    market: str = "india_nse_index_derivatives",
    ready: bool = True,
    require_file_inputs: bool = False,
    input_directory_count: int = 0,
    input_other_count: int = 0,
    input_unfingerprinted_count: int = 0,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_checks": 0 if ready else 1,
                "recommendation": (
                    "eligible_for_live_dryrun_route_review"
                    if profile == "ops_launch" and ready
                    else "ops_launch_evidence_incomplete"
                    if profile == "ops_launch"
                    else "eligible_for_shadow_scaleup_review"
                    if ready
                    else "strategy_evidence_incomplete"
                ),
                "evidence_profile": profile,
                "strategy": strategy,
                "market": market,
                "require_file_inputs": require_file_inputs,
                "input_file_count": 3,
                "input_directory_count": input_directory_count,
                "input_other_count": input_other_count,
                "input_unfingerprinted_count": input_unfingerprinted_count,
                "source_path": f"runs/evidence/{profile}/strategy_evidence_summary.csv",
            }
        ]
    )


def test_route_readiness_passes_when_portability_strategy_and_ops_evidence_match():
    portability = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives",),
            strategies=("microprice_imbalance",),
        )
    )

    review = build_route_readiness_review(
        portability.config,
        strategy_evidence_summaries=evidence_summary(profile="imbalance"),
        ops_evidence_summaries=evidence_summary(profile="ops_launch", require_file_inputs=True),
    )

    assert review.ready
    row = review.pairs.iloc[0]
    assert row["route_ready"]
    assert row["status"] == "ready_for_live_dryrun_route_review"
    assert row["next_gate"] == "live_dryrun_route_review"
    assert row["next_gate_help_command"] == ""
    assert review.summary.iloc[0]["strategy"] == "microprice_imbalance"
    assert review.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert review.summary.iloc[0]["next_gate"] == "live_dryrun_route_review"
    assert review.summary.iloc[0]["next_gate_help_command"] == ""
    assert int(review.summary.iloc[0]["ready_action_count"]) == 1
    assert int(review.summary.iloc[0]["blocked_action_count"]) == 0
    assert review.config["route_ready_pairs"][0]["strategy"] == "microprice_imbalance"
    assert review.config["ready_action_count"] == 1
    assert review.config["blocked_action_count"] == 0


def test_route_readiness_blocks_ops_evidence_without_file_input_gate():
    portability = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives",),
            strategies=("microprice_imbalance",),
        )
    )

    review = build_route_readiness_review(
        portability.config,
        strategy_evidence_summaries=evidence_summary(profile="imbalance"),
        ops_evidence_summaries=evidence_summary(profile="ops_launch", require_file_inputs=False),
    )

    assert not review.ready
    row = review.pairs.iloc[0]
    assert not row["route_ready"]
    assert row["status"] == "ops_file_provenance_not_gated"
    assert row["next_gate"] == "review-strategy-evidence --profile ops_launch --require-file-inputs"
    assert row["next_gate_help_command"] == (
        "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
    )
    summary = review.summary.iloc[0]
    assert summary["next_gate"] == "review-strategy-evidence --profile ops_launch --require-file-inputs"
    assert summary["next_gate_help_command"] == (
        "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
    )
    assert int(summary["ready_action_count"]) == 0
    assert int(summary["blocked_action_count"]) == 1
    assert review.config["next_gates"] == ["review-strategy-evidence --profile ops_launch --require-file-inputs"]


def test_route_readiness_blocks_incomplete_ops_evidence_with_action_hint(tmp_path):
    portability_dir = tmp_path / "portability"
    strategy_dir = tmp_path / "strategy_evidence"
    ops_dir = tmp_path / "ops_evidence"
    out_dir = tmp_path / "route_readiness"
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives",),
            strategies=("microprice_imbalance",),
        ),
    )
    strategy_dir.mkdir()
    ops_dir.mkdir()
    evidence_summary(profile="imbalance").to_csv(strategy_dir / "strategy_evidence_summary.csv", index=False)
    evidence_summary(profile="ops_launch", ready=False, require_file_inputs=True).to_csv(
        ops_dir / "strategy_evidence_summary.csv",
        index=False,
    )

    review = write_route_readiness_review(
        out_dir,
        market_portability=portability_dir,
        strategy_evidence=(strategy_dir,),
        ops_evidence=(ops_dir,),
    )

    queue = pd.read_csv(out_dir / "route_readiness_action_queue.csv")
    runbook = (out_dir / "route_readiness_runbook.md").read_text(encoding="utf-8")
    assert not review.ready
    assert queue.loc[0, "queue_status"] == "blocked"
    assert queue.loc[0, "status"] == "ops_evidence_incomplete"
    assert queue.loc[0, "next_gate"] == "review-strategy-evidence --profile ops_launch --require-file-inputs"
    assert queue.loc[0, "next_gate_help_command"] == (
        "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
    )
    assert queue.loc[0, "recommendation"] == "ops_launch_evidence_incomplete"
    assert "- Ready: no" in runbook
    assert "`review-strategy-evidence --profile ops_launch --require-file-inputs`" in runbook


def test_route_readiness_carries_portability_gaps_forward():
    portability = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("microprice_imbalance",),
        )
    )

    review = build_route_readiness_review(
        portability.config,
        strategy_evidence_summaries=evidence_summary(profile="imbalance", market="us_equities_regular"),
        ops_evidence_summaries=evidence_summary(
            profile="ops_launch",
            market="us_equities_regular",
            require_file_inputs=True,
        ),
    )

    assert not review.ready
    row = review.gaps.iloc[0]
    assert row["status"] == "blocked_by_portability"
    assert row["blocker"] == "explicit_fee_model_required"
    assert row["next_gate"] == "run_market_profile_report_with_fee_assumptions"


def test_write_route_readiness_outputs_files_and_manifest(tmp_path):
    portability_dir = tmp_path / "portability"
    strategy_dir = tmp_path / "strategy_evidence"
    ops_dir = tmp_path / "ops_evidence"
    out_dir = tmp_path / "route_readiness"
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives",),
            strategies=("microprice_imbalance",),
        ),
    )
    strategy_dir.mkdir()
    ops_dir.mkdir()
    evidence_summary(profile="imbalance").to_csv(strategy_dir / "strategy_evidence_summary.csv", index=False)
    evidence_summary(profile="ops_launch", require_file_inputs=True).to_csv(
        ops_dir / "strategy_evidence_summary.csv",
        index=False,
    )

    review = write_route_readiness_review(
        out_dir,
        market_portability=portability_dir,
        strategy_evidence=(strategy_dir,),
        ops_evidence=(ops_dir,),
    )

    assert review.output_dir == out_dir
    assert (out_dir / "route_readiness_pairs.csv").exists()
    assert (out_dir / "route_readiness_gaps.csv").exists()
    assert (out_dir / "route_readiness_summary.csv").exists()
    assert (out_dir / "route_readiness_action_queue.csv").exists()
    assert (out_dir / "route_readiness_config.json").exists()
    assert (out_dir / "route_readiness_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    queue = pd.read_csv(out_dir / "route_readiness_action_queue.csv")
    config = json.loads((out_dir / "route_readiness_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "route_readiness_runbook.md").read_text(encoding="utf-8")
    assert config["ready"]
    assert config["route_ready_pairs"][0]["route_ready"]
    assert config["ready_action_count"] == 1
    assert config["blocked_action_count"] == 0
    assert config["summary"]["next_gate"] == "live_dryrun_route_review"
    assert config["summary"]["ready_action_count"] == 1
    assert config["summary"]["blocked_action_count"] == 0
    assert queue.loc[0, "queue_status"] == "ready"
    assert queue.loc[0, "next_gate"] == "live_dryrun_route_review"
    assert "# Route Readiness Runbook" in runbook
    assert "- Ready: yes" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "route_readiness_action_queue.csv" in artifact_paths
    assert "route_readiness_runbook.md" in artifact_paths


def test_cli_route_readiness_fails_on_missing_ops_evidence_when_requested(tmp_path):
    portability_dir = tmp_path / "portability"
    strategy_dir = tmp_path / "strategy_evidence"
    out_dir = tmp_path / "route_readiness_cli"
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives",),
            strategies=("microprice_imbalance",),
        ),
    )
    strategy_dir.mkdir()
    evidence_summary(profile="imbalance").to_csv(strategy_dir / "strategy_evidence_summary.csv", index=False)

    code = main(
        [
            "review-route-readiness",
            "--portability",
            str(portability_dir),
            "--strategy-evidence",
            str(strategy_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    assert code == 2
    pairs = pd.read_csv(out_dir / "route_readiness_pairs.csv")
    assert pairs.loc[0, "status"] == "ops_evidence_missing"
