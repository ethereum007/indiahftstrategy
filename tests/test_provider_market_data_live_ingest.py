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
from reports.provider_market_data_live_ingest import (
    ProviderMarketDataLiveIngestConfig,
    write_provider_market_data_live_session_ingest,
)
from reports.provider_market_data_live_preflight import (
    ProviderMarketDataLivePreflightConfig,
    write_provider_market_data_live_session_preflight,
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


def _write_expected_captures(live_packet_path):
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    for idx, window in enumerate(packet["capture_windows"]):
        _write_capture(window["capture_path"], "2026-06-23", base=100.0 + idx)


def _write_capture_bundle(tmp_path, live_packet_path):
    preflight = write_provider_market_data_live_session_preflight(
        live_packet_path,
        tmp_path / "preflight",
        config=ProviderMarketDataLivePreflightConfig(now_iso="2026-06-23T08:45:00+05:30"),
    )
    bundle = write_provider_market_data_live_capture_bundle(
        live_packet_path,
        tmp_path / "capture_bundle",
        config=ProviderMarketDataLiveCaptureBundleConfig(
            preflight_config_path=str(preflight.output_dir / "provider_market_data_live_preflight_config.json"),
            ingest_output_dir=str(tmp_path / "live_ingest"),
        ),
    )
    return bundle.output_dir / "provider_market_data_live_capture_bundle.json"


def _mutate_bundle(bundle_path, mutator):
    target = Path(bundle_path)
    bundle = json.loads(target.read_text(encoding="utf-8"))
    mutator(bundle)
    target.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def test_provider_market_data_live_ingest_runs_batch_from_session_packet(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    _write_expected_captures(live_packet)
    out_dir = tmp_path / "live_ingest"

    report = write_provider_market_data_live_session_ingest(live_packet, out_dir)

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_live_ingest_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "provider_market_data_live_ingest_action_queue.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["expected_capture_count"] == 2
    assert summary["present_capture_count"] == 2
    assert summary["nonempty_capture_count"] == 2
    assert summary["batch_ready"]
    assert summary["batch_output_dir"] == str(tmp_path / "batch")
    assert action_queue.loc[0, "queue_status"] == "ready"
    assert action_queue.loc[0, "action"] == "feed_provider_market_data_batch_to_research"
    assert config["ready"]
    assert config["batch"]["ready"]
    assert manifest["run_type"] == "provider_market_data_live_session_ingest"
    assert "captures" in manifest["inputs"]
    assert "batch_manifest" in manifest["inputs"]
    assert (tmp_path / "batch" / "provider_market_data_batch_summary.csv").exists()
    assert (out_dir / "provider_market_data_live_ingest_windows.csv").exists()


def test_provider_market_data_live_ingest_fingerprints_capture_bundle_env_template(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    bundle_path = _write_capture_bundle(tmp_path, live_packet)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    _write_expected_captures(live_packet)
    out_dir = tmp_path / "live_ingest_with_bundle"

    report = write_provider_market_data_live_session_ingest(
        live_packet,
        out_dir,
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )

    summary = report.summary.iloc[0]
    config = json.loads((out_dir / "provider_market_data_live_ingest_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert Path(summary["capture_bundle_path"]) == bundle_path
    assert summary["capture_bundle_provided"]
    assert summary["capture_bundle_ready"]
    assert Path(summary["capture_env_template_path"]) == env_template_path
    assert summary["capture_env_template_exists"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert summary["adapter_handoff_provided"]
    assert summary["adapter_handoff_exists"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert summary["source_credential_env_template_exists"]
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert summary["source_live_fetch_contract_available"]
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert config["capture_bundle"]["path"] == str(bundle_path)
    assert config["capture_bundle"]["env_template_path"] == str(env_template_path)
    assert config["capture_bundle"]["env_template_exists"] is True
    assert config["capture_bundle"]["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["capture_bundle"]["adapter_handoff_exists"] is True
    assert config["capture_bundle"]["source_credential_env_template"]["sha256"] == summary["source_credential_env_template_sha256"]
    assert config["capture_bundle"]["live_fetch_contract"]["available"] is True
    assert manifest["inputs"]["capture_bundle"]["path"] == str(bundle_path.resolve())
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True


def test_provider_market_data_live_ingest_blocks_missing_source_env_template(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    bundle_path = _mutate_bundle(
        _write_capture_bundle(tmp_path, live_packet),
        lambda bundle: (
            bundle.update({"source_credential_env_template": {"path": "", "exists": False, "sha256": ""}}),
            bundle["authentication"].pop("source_env_template", None),
        ),
    )
    _write_expected_captures(live_packet)

    report = write_provider_market_data_live_session_ingest(
        live_packet,
        tmp_path / "live_ingest",
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_source_credential_env_template_carried" in failed
    assert not bool(report.summary.iloc[0]["source_credential_env_template_exists"])
    assert report.batch is None
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_source_env_template"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_ingest_blocks_missing_live_fetch_contract(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    bundle_path = _mutate_bundle(
        _write_capture_bundle(tmp_path, live_packet),
        lambda bundle: (
            bundle.update({"live_fetch_contract": {"available": False}}),
            bundle["preflight"].pop("live_fetch_contract", None),
        ),
    )
    _write_expected_captures(live_packet)

    report = write_provider_market_data_live_session_ingest(
        live_packet,
        tmp_path / "live_ingest",
        config=ProviderMarketDataLiveIngestConfig(capture_bundle_path=str(bundle_path)),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_bundle_live_fetch_contract_carried" in failed
    assert not bool(report.summary.iloc[0]["source_live_fetch_contract_available"])
    assert report.batch is None
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_live_fetch_contract"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_ingest_blocks_missing_capture_files(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"

    report = write_provider_market_data_live_session_ingest(live_packet, tmp_path / "live_ingest")

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert report.batch is None
    assert "expected_capture_files_exist" in failed
    assert report.action_queue.loc[0, "next_gate"] == "provider_fetcher_live_run"
    assert not (tmp_path / "batch" / "provider_market_data_batch_summary.csv").exists()


def test_cli_provider_market_data_live_ingest_accepts_session_packet(tmp_path):
    plan = _write_live_plan(tmp_path)
    live_packet = plan.output_dir / "provider_market_data_live_session_packet.json"
    _write_expected_captures(live_packet)
    out_dir = tmp_path / "cli_live_ingest"

    code = main(
        [
            "ingest-provider-market-data-live-session",
            "--live-session-packet",
            str(live_packet),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_ingest_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "batch_ready"])
