import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from tests.provider_adapter_capture_support import write_bundle_captures
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


def _write_expected_captures(live_packet_path, capture_bundle_path=None):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    if capture_bundle_path is not None:
        def frame_factory(request, index):
            start = pd.Timestamp(request.start_local)
            base = 100.0 + index
            return pd.DataFrame(
                [
                    [start.strftime("%Y-%m-%d %H:%M:%S"), base, base + 0.05, 75, 150, base + 0.05, 75],
                    [(start + pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"), base + 0.05, base + 0.10, 100, 125, base + 0.05, 50],
                ],
                columns=request.schema_columns,
            )

        write_bundle_captures(live_packet_path, capture_bundle_path, frame_factory)
        return
    for idx, window in enumerate(packet["capture_windows"]):
        _write_capture(window["capture_path"], "2026-06-23", base=100.0 + idx)


def _write_real_ingest(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    _write_expected_captures(live_packet)
    return write_provider_market_data_live_session_ingest(live_packet, tmp_path / "live_ingest")


def _write_bundle_linked_real_ingest(tmp_path):
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
    _write_expected_captures(live_packet, bundle_path)
    ingest = write_provider_market_data_live_session_ingest(
        live_packet,
        tmp_path / "live_ingest",
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )
    return ingest, bundle_path


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


def test_provider_market_data_live_evidence_accepts_real_provider_ingest(tmp_path):
    ingest = _write_real_ingest(tmp_path)
    out_dir = tmp_path / "evidence"

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        out_dir,
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    summary = report.summary.iloc[0]
    action_queue = pd.read_csv(out_dir / "provider_market_data_live_evidence_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["research_ready"]
    assert summary["synthetic_capture_count"] == 0
    assert summary["recommendation"] == "feed_walkforward_research"
    assert action_queue.loc[0, "next_gate"] == "review-data-readiness"
    assert manifest["run_type"] == "provider_market_data_live_evidence_review"


def test_provider_market_data_live_evidence_carries_capture_bundle_provenance(tmp_path):
    ingest, bundle_path = _write_bundle_linked_real_ingest(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    out_dir = tmp_path / "evidence_with_bundle"

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        out_dir,
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_live_evidence_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["research_ready"]
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert summary["capture_bundle_provided"]
    assert summary["capture_bundle_ready"]
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert summary["capture_env_template_exists"]
    assert len(summary["capture_env_template_sha256"]) == 64
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert summary["adapter_handoff_provided"]
    assert summary["adapter_handoff_exists"]
    assert len(summary["adapter_handoff_sha256"]) == 64
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert summary["source_credential_env_template_exists"]
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert summary["source_live_fetch_contract_available"]
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_exchange"] == "NFO"
    assert summary["adapter_contract_metadata_matches_session"]
    assert not bool(summary["adapter_contract_values_stored"])
    assert len(summary["provider_profile_sha256"]) == 64
    assert summary["provider_profile_adapter"] == "arrow_money"
    assert summary["provider_profile_transports"] == "file;rest;websocket"
    assert "live_ticks" in summary["provider_profile_capabilities"]
    assert summary["ingest_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert summary["capture_bundle_provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert summary["provider_profile_matches_ingest"]
    assert summary["provider_profile_matches_bundle"]
    assert summary["provider_capture_command_count"] == 2
    assert summary["provider_capture_command_providers"] == "arrow_money"
    assert summary["provider_capture_command_transports"] == "websocket"
    assert summary["capture_bundle_provider_capture_command_count"] == 2
    assert summary["capture_bundle_provider_capture_command_missing_count"] == 0
    assert summary["capture_bundle_provider_capture_commands_match_session"]
    assert summary["exchange"] == "NFO"
    assert summary["source_session_timezone"] == "Asia/Kolkata"
    assert summary["source_session_open_local"] == "09:15:00"
    assert summary["source_session_close_local"] == "15:30:00"
    assert summary["capture_bundle_exchange"] == "NFO"
    assert summary["capture_bundle_source_session_open_local"] == "09:15:00"
    assert summary["capture_bundle_market_session_open_local"] == "09:15"
    assert summary["capture_bundle_metadata_matches_session"]
    assert summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
    assert config["capture_bundle"]["capture_bundle_path"] == str(bundle_path)
    assert config["capture_bundle"]["capture_env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["capture_env_template_sha256"] == summary["capture_env_template_sha256"]
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_exists"] is True
    assert config["capture_bundle"]["adapter_handoff_sha256"] == summary["adapter_handoff_sha256"]
    assert config["capture_bundle"]["source_credential_env_template_sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["source_live_fetch_contract_available"] is True
    assert config["capture_bundle"]["capture_bundle_provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["capture_bundle"]["adapter_execution_contract"]["capture_bundle_ready"] is True
    assert config["capture_bundle"]["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["adapter_execution_contract"]["values_stored"] is False
    assert config["capture_bundle"]["provider_capture_command_count"] == 2
    assert config["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_command_count"] == 2
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert config["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert config["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["provider_profile_sha256"] == summary["provider_profile_sha256"]
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["live_session_packet"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert config["capture_bundle"]["capture_bundle_exchange"] == "NFO"
    assert config["capture_bundle"]["capture_bundle_source_session"]["timezone"] == "Asia/Kolkata"
    assert config["capture_bundle"]["capture_bundle_market_session"]["open_local"] == "09:15"
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
    assert manifest["extra"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_bundle_metadata_matches_session"] is True
    assert manifest["extra"]["capture_bundle"]["market_session"]["open_local"] == "09:15"
    assert manifest["extra"]["capture_bundle"]["provider_profile"]["sha256"] == summary["provider_profile_sha256"]
    assert manifest["extra"]["capture_env_template"]["sha256"] == summary["capture_env_template_sha256"]
    assert manifest["extra"]["adapter_handoff"]["sha256"] == summary["adapter_handoff_sha256"]
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert manifest["extra"]["live_fetch_contract"]["exchange"] == "NFO"
    assert manifest["extra"]["live_fetch_contract"]["session"]["close_local"] == "15:30:00"
    assert manifest["extra"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["provider_capture_command_providers"] == "arrow_money"
    assert manifest["extra"]["provider_capture_command_transports"] == "websocket"
    assert manifest["extra"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle_provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle_provider_capture_command_missing_count"] == 0
    assert manifest["extra"]["capture_bundle_provider_capture_commands_match_session"] is True
    assert manifest["extra"]["capture_bundle_provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_command_count"] == 2
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands"][0]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["capture_bundle"]["provider_capture_commands_match_session"] is True


def test_provider_market_data_live_evidence_blocks_capture_bundle_session_mismatch(tmp_path):
    ingest, _ = _write_bundle_linked_real_ingest(tmp_path)
    ingest_config_path = ingest.output_dir / "provider_market_data_live_ingest_config.json"
    _mutate_json(
        ingest_config_path,
        lambda payload: payload["capture_bundle"]["source_session"].update({"open_local": "09:30:00"}),
    )

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert "capture_bundle_metadata_matches_session" in failed
    assert summary["capture_bundle_source_session_open_local"] == "09:30:00"
    assert summary["source_session_open_local"] == "09:15:00"
    assert not bool(summary["capture_bundle_metadata_matches_session"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_session_metadata"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_evidence_blocks_missing_source_env_template(tmp_path):
    ingest, _ = _write_bundle_linked_real_ingest(tmp_path)
    ingest_config_path = ingest.output_dir / "provider_market_data_live_ingest_config.json"
    manifest_path = ingest.output_dir / "manifest.json"
    _mutate_json(
        ingest_config_path,
        lambda payload: payload["capture_bundle"].update(
            {"source_credential_env_template": {"path": "", "exists": False, "sha256": ""}}
        ),
    )
    _mutate_json(
        manifest_path,
        lambda payload: (
            payload["inputs"].pop("source_credential_env_template", None),
            payload["extra"].update({"source_credential_env_template": {"path": "", "exists": False, "sha256": ""}}),
        ),
    )

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_source_credential_env_template_carried" in failed
    assert not bool(report.summary.iloc[0]["source_credential_env_template_exists"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_source_env_template"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_evidence_blocks_missing_live_fetch_contract(tmp_path):
    ingest, _ = _write_bundle_linked_real_ingest(tmp_path)
    ingest_config_path = ingest.output_dir / "provider_market_data_live_ingest_config.json"
    manifest_path = ingest.output_dir / "manifest.json"
    _mutate_json(
        ingest_config_path,
        lambda payload: payload["capture_bundle"].update({"live_fetch_contract": {"available": False}}),
    )
    _mutate_json(
        manifest_path,
        lambda payload: payload["extra"].update({"live_fetch_contract": {"available": False}}),
    )

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_live_fetch_contract_carried" in failed
    assert not bool(report.summary.iloc[0]["source_live_fetch_contract_available"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_live_fetch_contract"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_evidence_blocks_missing_bundle_provider_profile(tmp_path):
    ingest, _ = _write_bundle_linked_real_ingest(tmp_path)
    ingest_config_path = ingest.output_dir / "provider_market_data_live_ingest_config.json"
    manifest_path = ingest.output_dir / "manifest.json"
    _mutate_json(
        ingest_config_path,
        lambda payload: payload["capture_bundle"].pop("provider_profile", None),
    )
    _mutate_json(
        manifest_path,
        lambda payload: payload["extra"]["capture_bundle"].pop("provider_profile", None),
    )

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_provider_profile_carried" in failed
    assert report.summary.iloc[0]["capture_bundle_provider_profile_sha256"] == ""
    assert not bool(report.summary.iloc[0]["provider_profile_matches_bundle"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_provider_profile"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_evidence_blocks_bundle_provider_capture_command_mismatch(tmp_path):
    ingest, _ = _write_bundle_linked_real_ingest(tmp_path)
    ingest_config_path = ingest.output_dir / "provider_market_data_live_ingest_config.json"
    _mutate_json(
        ingest_config_path,
        lambda payload: payload["capture_bundle"]["provider_capture_commands"][0].update(
            {"command_template": "provider-adapter capture --wrong"}
        ),
    )

    report = write_provider_market_data_live_evidence_review(
        ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_provider_capture_commands_match_session" in failed
    assert not bool(report.summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"])
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_session_provider_capture_commands"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_evidence_blocks_synthetic_rehearsal_by_default(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)

    report = write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(min_capture_rows=2),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert not summary["research_ready"]
    assert summary["synthetic_capture_count"] == 2
    assert summary["synthetic_sidecar_proof_ready"]
    assert summary["synthetic_sidecar_count"] == 2
    assert summary["synthetic_sidecar_adapter_command_hash_count"] == 2
    assert summary["synthetic_sidecar_capture_env_template_match_count"] == 2
    assert summary["synthetic_sidecar_adapter_handoff_match_count"] == 2
    assert "synthetic_rehearsal_absent" in failed
    assert report.action_queue.loc[0, "next_gate"] == "provider_fetcher_live_run"


def test_provider_market_data_live_evidence_allows_rehearsal_as_smoke_only(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)
    out_dir = tmp_path / "evidence"

    report = write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        out_dir,
        config=ProviderMarketDataLiveEvidenceConfig(
            allow_synthetic_rehearsal=True,
            min_capture_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    captures = pd.read_csv(out_dir / "provider_market_data_live_evidence_captures.csv")
    config = json.loads((out_dir / "provider_market_data_live_evidence_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert not summary["research_ready"]
    assert summary["synthetic_sidecar_proof_ready"]
    assert summary["synthetic_sidecar_count"] == 2
    assert summary["synthetic_sidecar_readable_count"] == 2
    assert summary["synthetic_sidecar_source_count"] == 2
    assert summary["synthetic_sidecar_adapter_command_hash_count"] == 2
    assert summary["synthetic_sidecar_capture_env_template_match_count"] == 2
    assert summary["synthetic_sidecar_adapter_handoff_match_count"] == 2
    assert summary["synthetic_sidecar_source_env_template_match_count"] == 2
    assert summary["synthetic_sidecar_live_fetch_contract_count"] == 2
    assert summary["synthetic_sidecar_adapter_execution_contract_safe_count"] == 2
    assert summary["synthetic_sidecar_invariant_count"] == 2
    assert captures["sidecar_adapter_command_sha256"].str.len().tolist() == [64, 64]
    assert captures["sidecar_capture_env_template_sha256"].str.len().tolist() == [64, 64]
    assert captures["sidecar_adapter_handoff_sha256"].str.len().tolist() == [64, 64]
    assert captures["sidecar_source_credential_env_template_sha256"].str.len().tolist() == [64, 64]
    assert captures["sidecar_live_fetch_contract_next_gate"].tolist() == ["provider_fetcher", "provider_fetcher"]
    assert captures["sidecar_adapter_contract_provider"].tolist() == ["arrow_money", "arrow_money"]
    assert captures["sidecar_adapter_contract_values_stored"].tolist() == [False, False]
    assert config["synthetic_sidecar_proof"]["ready"] is True
    assert config["synthetic_sidecar_proof"]["adapter_handoff_match_count"] == 2
    assert manifest["extra"]["synthetic_sidecar_proof"]["ready"] is True
    assert "synthetic_capture_sidecars" in manifest["inputs"]
    assert summary["recommendation"] == "rehearsal_backend_smoke_only"
    assert report.action_queue.loc[0, "action"] == "replace_synthetic_captures_with_provider_live_captures"
    assert report.action_queue.loc[0, "next_gate"] == "provider_fetcher_live_run"


def test_provider_market_data_live_evidence_blocks_stale_rehearsal_sidecar_proof(tmp_path):
    rehearsal = _write_rehearsal_ingest(tmp_path)
    sidecar_path = Path(rehearsal.captures.loc[0, "sidecar_path"])
    _mutate_json(
        sidecar_path,
        lambda payload: payload["adapter_handoff"].update({"sha256": "0" * 64}),
    )

    report = write_provider_market_data_live_evidence_review(
        rehearsal.ingest.output_dir,
        tmp_path / "evidence",
        config=ProviderMarketDataLiveEvidenceConfig(
            allow_synthetic_rehearsal=True,
            min_capture_rows=2,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert not bool(summary["synthetic_sidecar_proof_ready"])
    assert summary["synthetic_sidecar_count"] == 2
    assert summary["synthetic_sidecar_adapter_handoff_match_count"] == 1
    assert "synthetic_sidecar_adapter_handoff_matches_ingest" in failed
    assert "synthetic_rehearsal_absent" not in failed
    assert report.action_queue.loc[0, "action"] == "regenerate_synthetic_rehearsal_sidecars"
    assert report.action_queue.loc[0, "next_gate"] == "rehearse-provider-market-data-live-capture"


def test_cli_provider_market_data_live_evidence_accepts_real_provider_ingest(tmp_path):
    ingest = _write_real_ingest(tmp_path)
    out_dir = tmp_path / "cli_evidence"

    code = main(
        [
            "review-provider-market-data-live-evidence",
            "--live-ingest-dir",
            str(ingest.output_dir),
            "--out",
            str(out_dir),
            "--min-capture-rows",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_evidence_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "research_ready"])
