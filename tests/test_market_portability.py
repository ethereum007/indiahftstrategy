import json

import pandas as pd

from hft_cli import main
from reports.market_portability import (
    MarketPortabilityReportConfig,
    build_market_portability_report,
    write_market_portability_report,
)


def test_market_portability_report_gates_us_research_on_explicit_fees():
    report = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives", "us_equities_regular", "us_options_regular"),
            strategies=("microprice_imbalance", "settlement_convergence"),
        )
    )

    rows = report.matrix.set_index(["strategy", "market"])
    assert rows.loc[("microprice_imbalance", "india_nse_index_derivatives"), "status"] == "india_ready"
    assert "plan-imbalance-orders" in rows.loc[
        ("microprice_imbalance", "india_nse_index_derivatives"), "workflow_commands"
    ]
    assert "pipeline-imbalance-launch" in rows.loc[
        ("microprice_imbalance", "india_nse_index_derivatives"), "workflow_commands"
    ]
    assert rows.loc[("microprice_imbalance", "us_equities_regular"), "status"] == "needs_fee_model"
    assert rows.loc[("settlement_convergence", "us_options_regular"), "status"] == "blocked"
    assert (
        rows.loc[("settlement_convergence", "us_options_regular"), "blocker"]
        == "market_microstructure_model_missing"
    )
    assert int(report.summary.loc[0, "gaps"]) == 4


def test_market_portability_config_records_ready_gap_and_next_gate_pairs():
    report = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("india_nse_index_derivatives", "us_equities_regular"),
            strategies=("microprice_imbalance",),
        )
    )

    assert report.config["ready"]
    assert {"market", "strategy", "status", "blocker", "next_gate"} <= set(report.config["gap_pairs"][0])
    assert report.config["ready_pairs"] == [
        {
            "market": "india_nse_index_derivatives",
            "strategy": "microprice_imbalance",
            "status": "india_ready",
            "blocker": "",
            "next_gate": "run_walkforward_and_paper_shadow_gates",
        }
    ]
    assert "run_market_profile_report_with_fee_assumptions" in report.config["next_gates"]


def test_market_portability_report_marks_us_options_portable_with_fee_model():
    report = build_market_portability_report(
        MarketPortabilityReportConfig(
            markets=("us_options_regular",),
            strategies=("parity_box", "surface_market_making"),
            explicit_fee_model=True,
        )
    )

    assert set(report.matrix["status"]) == {"portable_research"}
    assert report.gaps.empty
    assert report.ready
    assert set(report.matrix["next_gate"]) == {"run_walkforward_and_paper_shadow_gates"}
    parity_commands = report.matrix.set_index("strategy").loc["parity_box", "workflow_commands"]
    assert "plan-parity-orders" in parity_commands
    assert "pipeline-parity-launch" in parity_commands


def test_write_market_portability_report_outputs_files_and_manifest(tmp_path):
    out_dir = tmp_path / "portability"

    report = write_market_portability_report(
        out_dir,
        config=MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("lead_lag_taker",),
            explicit_fee_model=True,
        ),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "market_portability_matrix.csv").exists()
    assert (out_dir / "market_portability_gaps.csv").exists()
    assert (out_dir / "market_portability_summary.csv").exists()
    config = json.loads((out_dir / "market_portability_config.json").read_text(encoding="utf-8"))
    assert config["ready"]
    assert config["requested_markets"] == ["us_equities_regular"]
    assert config["ready_pairs"] == [
        {
            "market": "us_equities_regular",
            "strategy": "lead_lag_taker",
            "status": "portable_research",
            "blocker": "",
            "next_gate": "run_walkforward_and_paper_shadow_gates",
        }
    ]
    assert "plan-leadlag-orders" in report.matrix.loc[0, "workflow_commands"]
    assert "pipeline-leadlag-launch" in report.matrix.loc[0, "workflow_commands"]
    assert (out_dir / "manifest.json").exists()


def test_cli_market_portability_report_writes_selected_strategy(tmp_path):
    out_dir = tmp_path / "cli_portability"

    code = main(
        [
            "market-portability-report",
            "--market",
            "us_options_regular",
            "--strategy",
            "surface_market_making",
            "--explicit-fee-model",
            "--out",
            str(out_dir),
        ]
    )

    matrix = pd.read_csv(out_dir / "market_portability_matrix.csv")
    summary = pd.read_csv(out_dir / "market_portability_summary.csv")
    assert code == 0
    assert matrix.loc[0, "strategy"] == "surface_market_making"
    assert matrix.loc[0, "status"] == "portable_research"
    assert bool(summary.loc[0, "ready"])
    assert (out_dir / "market_portability_config.json").exists()
