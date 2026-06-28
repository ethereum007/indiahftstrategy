import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from reports.market_data_fetch import MarketDataFetchConfig, write_market_data_fetch_plan
from reports.market_data_source import MarketDataSourceConfig, write_market_data_source_plan
from reports.provider_market_data_client import write_provider_market_data_client_plan
from reports.provider_market_data_fetcher import write_provider_market_data_fetcher_plan
from reports.provider_market_data_live_bundle import (
    ProviderMarketDataLiveCaptureBundleConfig,
    write_provider_market_data_live_capture_bundle,
)
from reports.provider_market_data_live_evidence import (
    ProviderMarketDataLiveEvidenceConfig,
    write_provider_market_data_live_evidence_review,
)
from reports.provider_market_data_live_ingest import (
    ProviderMarketDataLiveIngestConfig,
    write_provider_market_data_live_session_ingest,
)
from reports.provider_market_data_live_preflight import (
    ProviderMarketDataLivePreflightConfig,
    write_provider_market_data_live_session_preflight,
)
from reports.provider_market_data_live_rehearsal import (
    ProviderMarketDataLiveRehearsalConfig,
    write_provider_market_data_live_rehearsal,
)
from reports.provider_market_data_live_session import (
    ProviderMarketDataLiveSessionConfig,
    write_provider_market_data_live_session_plan,
)
from reports.provider_market_data_research_handoff import (
    ProviderMarketDataResearchHandoffConfig,
    write_provider_market_data_research_handoff,
)


def _write_client_packet(tmp_path):
    source_report = write_market_data_source_plan(
        tmp_path / "source",
        config=MarketDataSourceConfig(
            provider="arrow_money",
            kind="ticks",
            transport="websocket",
            source_uri="wss://feed.arrow.money/market-data/nse",
            auth_env_vars=("ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"),
        ),
    )
    fetch_report = write_market_data_fetch_plan(
        source_report.output_dir / "market_data_source_config.json",
        tmp_path / "fetch",
        config=MarketDataFetchConfig(symbols=("NIFTY-I", "BANKNIFTY-I")),
    )
    fetcher_report = write_provider_market_data_fetcher_plan(
        fetch_report.output_dir / "market_data_fetch_config.json",
        tmp_path / "fetcher",
    )
    client_report = write_provider_market_data_client_plan(
        fetcher_report.output_dir / "provider_market_data_fetcher_config.json",
        tmp_path / "client",
    )
    return client_report.output_dir / "provider_market_data_client_packet.json"


def _write_live_plan(tmp_path):
    client_packet = _write_client_packet(tmp_path)
    return write_provider_market_data_live_session_plan(
        client_packet,
        tmp_path / "live_plan",
        config=ProviderMarketDataLiveSessionConfig(
            trade_date="2026-06-23",
            windows=("open=09:15-09:45", "close=14:45-15:15"),
            capture_dir=str(tmp_path / "captures"),
            batch_output_dir=str(tmp_path / "batch"),
            min_capture_rows=2,
            pipeline_min_rows=2,
            tick_size=0.05,
            max_median_spread_ticks=2,
        ),
    )


def _write_capture(path: str | Path, day: str, *, base: float):
    capture = Path(path)
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(
        "ts,bid,ask,bid_qty,ask_qty,last,last_qty\n"
        f"{day} 09:15:00,{base:.2f},{base + 0.05:.2f},75,150,{base + 0.05:.2f},75\n"
        f"{day} 09:15:01,{base + 0.05:.2f},{base + 0.10:.2f},100,125,{base + 0.05:.2f},50\n",
        encoding="utf-8",
    )


def _write_expected_captures(live_packet_path):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    for idx, window in enumerate(packet["capture_windows"]):
        _write_capture(window["capture_path"], "2026-06-23", base=100.0 + idx)


def _write_real_ingest(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    _write_expected_captures(live_packet)
    return write_provider_market_data_live_session_ingest(live_packet, tmp_path / "live_ingest")


def _write_real_evidence(tmp_path):
    ingest = _write_real_ingest(tmp_path)
    return write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )


def _write_bundle_linked_real_evidence(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    preflight = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )
    bundle = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            ingest_output_dir=str(tmp_path / "live_ingest"),
        ),
    )
    bundle_path = bundle.output_dir / "provider_market_data_live_capture_bundle.json"
    _write_expected_captures(live_packet)
    ingest = write_provider_market_data_live_session_ingest(
        live_packet,
        tmp_path / "live_ingest",
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )
    evidence = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )
    return evidence, bundle_path


def _mutate_json(path, mutator):
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    mutator(payload)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _write_rehearsal_ingest(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    preflight = write_provider_market_data_live_session_preflight(
        live_packet,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )
    bundle = write_provider_market_data_live_capture_bundle(
        live_packet,
        tmp_path / "bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            ingest_output_dir=str(tmp_path / "rehearsal_ingest"),
        ),
    )
    return write_provider_market_data_live_rehearsal(
        bundle.output_dir / "provider_market_data_live_capture_bundle.json",
        tmp_path / "rehearsal",
        config=ProviderMarketDataLiveRehearsalConfig(
            rows_per_window=3,
            ingest_output_dir=str(tmp_path / "rehearsal_ingest"),
            ingest_min_capture_rows=2,
            ingest_pipeline_min_rows=2,
        ),
    )


def _write_synthetic_smoke_evidence(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)
    return write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(
            allow_synthetic_rehearsal=True,
            min_capture_rows=2,
        ),
    )


def test_provider_market_data_research_handoff_builds_imbalance_commands_from_live_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    out_dir = tmp_path / "handoff"

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        out_dir,
        config=ProviderMarketDataResearchHandoffConfig(
            output_root=str(tmp_path / "research"),
            min_tick_folds=2,
            tick_size=0.05,
        ),
    )

    summary = report.summary.iloc[0]
    commands = pd.read_csv(out_dir / "provider_market_data_research_handoff_commands.csv")
    action_queue = pd.read_csv(out_dir / "provider_market_data_research_handoff_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(summary["research_ready"])
    assert summary["dataset_count"] == 2
    assert summary["ready_command_count"] == 2
    assert set(commands["run_type"]) == {"imbalance_edge_walkforward", "imbalance_replay_walkforward"}
    assert commands["command"].str.contains("walkforward-imbalance-edge").any()
    assert commands["command"].str.contains("candidate_config.json", regex=False).any()
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "next_gate"] == "walkforward-imbalance-edge"
    assert "walkforward-imbalance-edge" in action_queue.loc[0, "next_gate_help_command"]
    assert manifest["run_type"] == "provider_market_data_research_handoff"


def test_provider_market_data_research_handoff_carries_capture_bundle_provenance(tmp_path):
    evidence, bundle_path = _write_bundle_linked_real_evidence(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    out_dir = tmp_path / "handoff"

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        out_dir,
        config=ProviderMarketDataResearchHandoffConfig(
            output_root=str(tmp_path / "research"),
            min_tick_folds=2,
            tick_size=0.05,
        ),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_research_handoff_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "provider_market_data_research_handoff_runbook.md").read_text(encoding="utf-8")
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert bool(summary["capture_bundle_provided"])
    assert bool(summary["capture_bundle_exists"])
    assert bool(summary["capture_bundle_ready"])
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert bool(summary["capture_env_template_exists"])
    assert len(summary["capture_env_template_sha256"]) == 64
    assert summary["capture_env_template_sha256"] == bundle["capture_env_template_sha256"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert bool(summary["adapter_handoff_provided"])
    assert bool(summary["adapter_handoff_exists"])
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert summary["adapter_handoff_sha256"] == bundle["adapter_handoff_sha256"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert bool(summary["source_credential_env_template_exists"])
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert bool(summary["source_live_fetch_contract_available"])
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert bool(summary["capture_bundle_metadata_matches_session"])
    assert bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"])
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_exists"] is True
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["capture_bundle"]["source_credential_env_template_sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["exchange"] == "NFO"
    assert config["capture_bundle"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert config["capture_bundle"]["capture_bundle_metadata_matches_session"] is True
    assert config["exchange"] == "NFO"
    assert config["source_session"]["close_local"] == "15:30:00"
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["exchange"] == "NFO"
    assert manifest["extra"]["source_session"]["timezone"] == "Asia/Kolkata"
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert str(source_env_template_path) in runbook
    assert str(adapter_handoff_path) in runbook


def test_provider_market_data_research_handoff_blocks_capture_bundle_session_mismatch(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    evidence_config_path = evidence.output_dir / "provider_market_data_live_evidence_config.json"
    _mutate_json(
        evidence_config_path,
        lambda payload: payload["capture_bundle"]["capture_bundle_source_session"].update({"open_local": "09:30:00"}),
    )

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(
            output_root=str(tmp_path / "research"),
            min_tick_folds=2,
            tick_size=0.05,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "capture_bundle_source_session_matches_evidence" in failed
    assert summary["capture_bundle_source_session_open_local"] == "09:30:00"
    assert summary["source_session_open_local"] == "09:15:00"
    assert report.action_queue.loc[0, "action"] == "regenerate_live_evidence_with_session_metadata"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_research_handoff_blocks_missing_source_env_template(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    evidence_config_path = evidence.output_dir / "provider_market_data_live_evidence_config.json"
    manifest_path = evidence.output_dir / "manifest.json"
    _mutate_json(
        evidence_config_path,
        lambda payload: payload["capture_bundle"].update(
            {
                "source_credential_env_template_path": "",
                "source_credential_env_template_provided": False,
                "source_credential_env_template_exists": False,
                "source_credential_env_template_sha256": "",
            }
        ),
    )
    _mutate_json(
        manifest_path,
        lambda payload: (
            payload["inputs"].pop("source_credential_env_template", None),
            payload["extra"].update({"source_credential_env_template": {"path": "", "exists": False, "sha256": ""}}),
        ),
    )

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(
            output_root=str(tmp_path / "research"),
            min_tick_folds=2,
            tick_size=0.05,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_source_credential_env_template_carried" in failed
    assert not bool(report.summary.iloc[0]["source_credential_env_template_exists"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_source_env_template"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_research_handoff_blocks_missing_live_fetch_contract(tmp_path):
    evidence, _ = _write_bundle_linked_real_evidence(tmp_path)
    evidence_config_path = evidence.output_dir / "provider_market_data_live_evidence_config.json"
    manifest_path = evidence.output_dir / "manifest.json"
    _mutate_json(
        evidence_config_path,
        lambda payload: payload["capture_bundle"].update(
            {
                "source_live_fetch_contract_available": False,
                "source_live_fetch_contract_next_gate": "",
                "source_live_fetch_contract_command_template": "",
            }
        ),
    )
    _mutate_json(
        manifest_path,
        lambda payload: payload["extra"].update(
            {"live_fetch_contract": {"available": False, "next_gate": "", "command_template": ""}}
        ),
    )

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(
            output_root=str(tmp_path / "research"),
            min_tick_folds=2,
            tick_size=0.05,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_live_fetch_contract_carried" in failed
    assert not bool(report.summary.iloc[0]["source_live_fetch_contract_available"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_live_fetch_contract"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_research_handoff_blocks_synthetic_smoke_evidence(tmp_path):
    evidence = _write_synthetic_smoke_evidence(tmp_path)

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(output_root=str(tmp_path / "research")),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert evidence.ready
    assert not bool(evidence.summary.iloc[0]["research_ready"])
    assert not report.ready
    assert not bool(summary["research_ready"])
    assert "live_evidence_research_ready" in failed
    assert "synthetic_rehearsal_absent" in failed
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "next_gate"] == "review-provider-market-data-live-evidence"


def test_provider_market_data_research_handoff_blocks_unsupported_strategy(tmp_path):
    evidence = _write_real_evidence(tmp_path)

    report = write_provider_market_data_research_handoff(
        evidence.output_dir,
        tmp_path / "handoff",
        config=ProviderMarketDataResearchHandoffConfig(
            strategies=("leadlag",),
            output_root=str(tmp_path / "research"),
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    command = report.commands.iloc[0]
    assert not report.ready
    assert "requested_strategies_supported" in failed
    assert command["queue_status"] == "blocked"
    assert command["next_gate"] == "walkforward-leadlag-replay"
    assert "leader/laggard" in command["reason"]


def test_cli_provider_market_data_research_handoff_accepts_live_evidence(tmp_path):
    evidence = _write_real_evidence(tmp_path)
    out_dir = tmp_path / "cli_handoff"

    code = main(
        [
            "handoff-provider-market-data-research",
            "--live-evidence-dir",
            str(evidence.output_dir),
            "--out",
            str(out_dir),
            "--output-root",
            str(tmp_path / "research"),
            "--min-tick-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_research_handoff_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "ready_command_count"]) == 2
