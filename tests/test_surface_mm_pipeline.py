import json

import pandas as pd

from engine.surface import black76_price
from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.evidence import EvidenceThresholds, evaluate_strategy_evidence, evidence_profile_run_types
from reports.market_portability import MarketPortabilityReportConfig, write_market_portability_report
from reports.proof import ProofThresholds
from reports.promotion import PromotionThresholds
from reports.surface_quality import SurfaceQualityThresholds
from reports.surface_mm_pipeline import write_surface_mm_research_pipeline


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def option_row(ts, strike, *, forward=1000.0, vol=0.2, tte=30 / 365):
    call_mid = black76_price(option_type="C", forward=forward, strike=strike, tte_years=tte, vol=vol)
    put_mid = black76_price(option_type="P", forward=forward, strike=strike, tte_years=tte, vol=vol)
    return {
        "ts": ts,
        "expiry": "2026-06-30",
        "strike": float(strike),
        "call_bid": round(max(call_mid - 0.10, 0.05), 2),
        "call_ask": round(call_mid + 0.10, 2),
        "call_bid_qty": 300,
        "call_ask_qty": 300,
        "put_bid": round(max(put_mid - 0.10, 0.05), 2),
        "put_ask": round(put_mid + 0.10, 2),
        "put_bid_qty": 300,
        "put_ask_qty": 300,
    }


def write_surface_inputs(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:01")
    chain = pd.DataFrame(
        [option_row(ts0, strike, forward=1000.0) for strike in [950.0, 1000.0, 1050.0]]
        + [option_row(ts1, strike, forward=970.0) for strike in [950.0, 1000.0, 1050.0]]
    )
    futures = pd.DataFrame(
        [
            {"ts": ts0, "bid": 999.95, "ask": 1000.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 969.95, "ask": 970.05, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)
    return chain_path, futures_path


def test_surface_mm_research_pipeline_promotes_candidate(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "surface_pipeline"

    report = write_surface_mm_research_pipeline(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        edge_ticks=0.0,
        max_market_spread_ticks=20.0,
        max_quotes_per_snapshot=4,
        quote_ttl_ns_values=[2_000_000_000],
        order_latency_us_values=[0.0],
        fill_depth_fraction_values=[1.0],
        markout_horizon_ns_values=[1_000_000_000],
        proof_thresholds=ProofThresholds(min_net_pnl=-1_000_000.0, min_fills=1, min_maker_share=0.0),
        min_selection_median_net_pnl=-1_000_000.0,
        promotion_thresholds=PromotionThresholds(min_median_net_pnl=-1_000_000.0, min_median_fills=1),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    quote_review_summary = pd.read_csv(out_dir / "02_quote_review" / "quote_risk_summary.csv")
    assert report.ready
    assert report.promotion is not None
    assert report.summary.loc[0, "strategy"] == "surface_mm"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert quote_review_summary.loc[0, "strategy"] == "surface_mm"
    assert quote_review_summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "surface_mm"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert int(report.summary.loc[0, "quotes"]) >= 1
    assert bool(report.summary.loc[0, "sweep_proof_passed"])
    assert bool(report.summary.loc[0, "promotion_ready"])
    assert config["ready"]
    assert config["strategy"] == "surface_mm"
    assert report.stages.iloc[0]["stage"] == "quote_generation"
    assert config["source_run_type"] == "surface_mm_research_pipeline"
    assert set(report.stages["stage"]) == {"quote_generation", "quote_review", "sweep", "selection", "promotion"}
    assert (out_dir / "01_quotes" / "surface_quotes.csv").exists()
    assert (out_dir / "02_quote_review" / "quote_risk_summary.csv").exists()
    assert (out_dir / "03_sweep" / "sweep_summary.csv").exists()
    assert (out_dir / "04_selection" / "selection_summary.csv").exists()
    assert (out_dir / "05_promotion" / "promotion_summary.csv").exists()
    assert (out_dir / "surface_mm_pipeline_stages.csv").exists()
    assert (out_dir / "surface_mm_pipeline_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_surface_mm_pipeline_artifacts_satisfy_surface_mm_evidence_profile(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "surface_pipeline_with_quality"

    write_surface_mm_research_pipeline(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        edge_ticks=0.0,
        max_market_spread_ticks=20.0,
        max_quotes_per_snapshot=4,
        surface_quality_horizon_ns_values=[1_000_000_000],
        require_surface_quality=True,
        surface_quality_thresholds=SurfaceQualityThresholds(min_mae_improvement=-1_000_000.0),
        quote_ttl_ns_values=[2_000_000_000],
        order_latency_us_values=[0.0],
        fill_depth_fraction_values=[1.0],
        markout_horizon_ns_values=[1_000_000_000],
        proof_thresholds=ProofThresholds(min_net_pnl=-1_000_000.0, min_fills=1, min_maker_share=0.0),
        min_selection_median_net_pnl=-1_000_000.0,
        promotion_thresholds=PromotionThresholds(min_median_net_pnl=-1_000_000.0, min_median_fills=1),
    )

    catalog = catalog_experiment_runs([out_dir]).catalog
    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("surface_mm"),
            allow_dirty_git=True,
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="surface_mm",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(evidence_profile_run_types("surface_mm"))
    assert review.summary.loc[0, "strategy"] == "surface_mm"
    assert review.summary.loc[0, "market"] == "india_nse_index_derivatives"


def test_surface_mm_pipeline_blocks_nonportable_market_pair(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    portability_dir = tmp_path / "portability"
    out_dir = tmp_path / "surface_pipeline_blocked"
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("us_options_regular",),
            strategies=("surface_market_making",),
        ),
    )

    report = write_surface_mm_research_pipeline(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        market="us_options_regular",
        filter_session=False,
        market_portability_dir=portability_dir,
        require_market_portability=True,
        quote_ttl_ns_values=[2_000_000_000],
        order_latency_us_values=[0.0],
        fill_depth_fraction_values=[1.0],
        markout_horizon_ns_values=[1_000_000_000],
    )

    stages = report.stages.set_index("stage")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert not bool(stages.loc["market_portability", "status"])
    assert bool(stages.loc["quote_generation", "skipped"])
    assert stages.loc["quote_generation", "recommendation"] == "market_portability_not_ready"
    assert "market_portability" in config["failed_checks"]


def test_surface_mm_pipeline_blocks_failed_surface_quality(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "surface_pipeline_quality_blocked"

    report = write_surface_mm_research_pipeline(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        edge_ticks=0.0,
        max_market_spread_ticks=20.0,
        max_quotes_per_snapshot=4,
        surface_quality_horizon_ns_values=[1_000_000_000],
        require_surface_quality=True,
        surface_quality_thresholds=SurfaceQualityThresholds(min_mae_improvement=1_000_000.0),
        quote_ttl_ns_values=[2_000_000_000],
        order_latency_us_values=[0.0],
        fill_depth_fraction_values=[1.0],
        markout_horizon_ns_values=[1_000_000_000],
    )

    stages = report.stages.set_index("stage")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert report.surface_quality is not None
    assert not bool(stages.loc["surface_quality", "status"])
    assert bool(stages.loc["quote_review", "skipped"])
    assert stages.loc["quote_review", "recommendation"] == "surface_quality_not_ready"
    assert "surface_quality" in config["failed_checks"]
    assert (out_dir / "02_surface_quality" / "surface_quality_summary.csv").exists()


def test_cli_surface_mm_research_pipeline_fails_closed_without_data_readiness(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "surface_pipeline_cli"

    code = main(
        [
            "pipeline-surface-mm-research",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--edge-ticks",
            "0",
            "--max-market-spread-ticks",
            "20",
            "--max-quotes-per-snapshot",
            "4",
            "--quote-ttl-ns",
            "2000000000",
            "--fill-depth-fraction",
            "1",
            "--require-data-readiness-comparison",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "surface_mm_pipeline_summary.csv")
    stages = pd.read_csv(out_dir / "surface_mm_pipeline_stages.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not bool(stages.loc[stages["stage"] == "quote_review", "status"].iloc[0])
    assert bool(stages.loc[stages["stage"] == "sweep", "skipped"].iloc[0])
    assert "quote_review" in config["failed_checks"]


def test_cli_surface_mm_research_pipeline_requires_surface_quality(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "surface_pipeline_cli_quality"

    code = main(
        [
            "pipeline-surface-mm-research",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--edge-ticks",
            "0",
            "--max-market-spread-ticks",
            "20",
            "--max-quotes-per-snapshot",
            "4",
            "--surface-quality-horizon-ns",
            "1000000000",
            "--require-surface-quality",
            "--min-surface-quality-mae-improvement",
            "1000000",
            "--quote-ttl-ns",
            "2000000000",
            "--fill-depth-fraction",
            "1",
            "--fail-on-breach",
        ]
    )

    stages = pd.read_csv(out_dir / "surface_mm_pipeline_stages.csv")
    assert code == 2
    assert not bool(stages.loc[stages["stage"] == "surface_quality", "status"].iloc[0])
    assert bool(stages.loc[stages["stage"] == "quote_review", "skipped"].iloc[0])


def test_cli_surface_mm_pipeline_requires_market_portability(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    portability_dir = tmp_path / "portability"
    out_dir = tmp_path / "surface_pipeline_cli_portability"
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("us_options_regular",),
            strategies=("surface_market_making",),
        ),
    )

    code = main(
        [
            "pipeline-surface-mm-research",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--market",
            "us_options_regular",
            "--no-filter-session",
            "--market-portability",
            str(portability_dir),
            "--require-market-portability",
            "--quote-ttl-ns",
            "2000000000",
            "--fill-depth-fraction",
            "1",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "surface_mm_pipeline_summary.csv")
    stages = pd.read_csv(out_dir / "surface_mm_pipeline_stages.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "market_portability" in set(stages.loc[~stages["status"].astype(bool), "stage"])
    assert bool(stages.loc[stages["stage"] == "quote_generation", "skipped"].iloc[0])
    assert "market_portability" in config["failed_checks"]
