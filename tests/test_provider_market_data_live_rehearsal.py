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


def _write_bundle(tmp_path):
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
    return bundle.output_dir / "provider_market_data_live_capture_bundle.json"


def _first_capture_path(bundle_path):
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    return Path(bundle["commands"][0]["capture_path"])


def _mutate_bundle(bundle_path, mutator):
    target = Path(bundle_path)
    bundle = json.loads(target.read_text(encoding="utf-8"))
    mutator(bundle)
    target.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def test_provider_market_data_live_rehearsal_writes_synthetic_captures_and_runs_ingest(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    env_template_path = bundle_path.parent / "provider_market_data_live_capture_env_template.env"
    adapter_handoff_path = bundle_path.parent / "provider_market_data_adapter_handoff.json"
    source_env_template_path = Path(bundle["source_credential_env_template"]["path"])
    out_dir = tmp_path / "rehearsal"

    report = write_provider_market_data_live_rehearsal(
        bundle_path,
        out_dir,
        config=ProviderMarketDataLiveRehearsalConfig(
            rows_per_window=3,
            ingest_output_dir=str(tmp_path / "rehearsal_ingest"),
            ingest_min_capture_rows=2,
            ingest_pipeline_min_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    captures = pd.read_csv(out_dir / "provider_market_data_live_rehearsal_captures.csv")
    config = json.loads((out_dir / "provider_market_data_live_rehearsal_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert summary["synthetic_only"]
    assert summary["capture_count"] == 2
    assert summary["synthetic_rows_written"] == 6
    assert summary["ingest_ready"]
    assert Path(summary["env_template_path"]) == env_template_path
    assert summary["env_template_provided"]
    assert summary["env_template_exists"]
    assert Path(summary["adapter_handoff_path"]) == adapter_handoff_path
    assert summary["adapter_handoff_provided"]
    assert summary["adapter_handoff_exists"]
    assert Path(summary["source_credential_env_template_path"]) == source_env_template_path
    assert summary["source_credential_env_template_exists"]
    assert len(summary["source_credential_env_template_sha256"]) == 64
    assert summary["source_live_fetch_contract_available"]
    assert summary["source_live_fetch_contract_next_gate"] == "provider_fetcher"
    assert summary["adapter_contract_provider"] == "arrow_money"
    assert summary["adapter_contract_transport"] == "websocket"
    assert summary["adapter_contract_command_count"] == 2
    assert not bool(summary["adapter_contract_values_stored"])
    assert captures["synthetic_rows_written"].tolist() == [3, 3]
    assert all(Path(path).exists() for path in captures["capture_path"])
    assert all(Path(path).exists() for path in captures["sidecar_path"])
    assert captures["adapter_command_sha256"].str.len().tolist() == [64, 64]
    assert captures["sidecar_sha256"].str.len().tolist() == [64, 64]
    sidecar = json.loads(Path(captures.loc[0, "sidecar_path"]).read_text(encoding="utf-8"))
    assert sidecar["synthetic_only"]
    assert sidecar["provider"] == "arrow_money"
    assert sidecar["transport"] == "websocket"
    assert sidecar["adapter_command"] == captures.loc[0, "adapter_command"]
    assert sidecar["adapter_command_sha256"] == captures.loc[0, "adapter_command_sha256"]
    assert sidecar["capture_env_template"]["path"] == str(env_template_path)
    assert sidecar["capture_env_template"]["sha256"] == bundle["capture_env_template_sha256"]
    assert sidecar["adapter_handoff"]["path"] == str(adapter_handoff_path)
    assert sidecar["adapter_handoff"]["sha256"] == bundle["adapter_handoff_sha256"]
    assert sidecar["source_credential_env_template"]["sha256"] == summary["source_credential_env_template_sha256"]
    assert sidecar["live_fetch_contract"]["next_gate"] == "provider_fetcher"
    assert sidecar["adapter_execution_contract"]["provider"] == "arrow_money"
    assert sidecar["adapter_execution_contract"]["values_stored"] is False
    assert sidecar["invariants"]["synthetic_capture_not_market_evidence"] is True
    assert config["synthetic_only"] is True
    assert config["env_template_path"] == str(env_template_path)
    assert config["env_template_exists"] is True
    assert config["adapter_handoff_path"] == str(adapter_handoff_path)
    assert config["adapter_handoff_exists"] is True
    assert config["source_credential_env_template"]["sha256"] == summary["source_credential_env_template_sha256"]
    assert config["live_fetch_contract"]["available"] is True
    assert config["adapter_execution_contract"]["provider"] == "arrow_money"
    assert config["adapter_execution_contract"]["capture_bundle_ready"] is True
    assert config["adapter_execution_contract"]["values_stored"] is False
    assert config["ingest"]["ready"] is True
    assert manifest["run_type"] == "provider_market_data_live_rehearsal"
    assert manifest["inputs"]["capture_env_template"]["path"] == str(env_template_path.resolve())
    assert manifest["inputs"]["adapter_handoff"]["path"] == str(adapter_handoff_path.resolve())
    assert manifest["inputs"]["source_credential_env_template"]["path"] == str(source_env_template_path.resolve())
    assert manifest["extra"]["source_credential_env_template"]["exists"] is True
    assert manifest["extra"]["live_fetch_contract"]["available"] is True
    assert manifest["extra"]["adapter_execution_contract"]["provider"] == "arrow_money"
    assert manifest["extra"]["adapter_execution_contract"]["values_stored"] is False
    assert "synthetic_captures" in manifest["inputs"]
    assert "synthetic_capture_sidecars" in manifest["inputs"]


def test_provider_market_data_live_rehearsal_blocks_existing_capture_without_overwrite(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    capture = _first_capture_path(bundle_path)
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text("ts,bid,ask,bid_qty,ask_qty,last,last_qty\n", encoding="utf-8")

    report = write_provider_market_data_live_rehearsal(
        bundle_path,
        tmp_path / "rehearsal",
        config=ProviderMarketDataLiveRehearsalConfig(rows_per_window=3),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "capture_files_do_not_already_exist" in failed
    assert report.ingest is None
    assert report.action_queue.loc[0, "next_gate"] == "rehearse-provider-market-data-live-capture"


def test_provider_market_data_live_rehearsal_blocks_missing_source_env_template(tmp_path):
    bundle_path = _mutate_bundle(
        _write_bundle(tmp_path),
        lambda bundle: (
            bundle.update({"source_credential_env_template": {"path": "", "exists": False, "sha256": ""}}),
            bundle["authentication"].pop("source_env_template", None),
        ),
    )

    report = write_provider_market_data_live_rehearsal(
        bundle_path,
        tmp_path / "rehearsal",
        config=ProviderMarketDataLiveRehearsalConfig(rows_per_window=3),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "bundle_source_credential_env_template_carried" in failed
    assert not bool(report.summary.iloc[0]["source_credential_env_template_exists"])
    assert report.ingest is None
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_source_env_template"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_provider_market_data_live_rehearsal_blocks_missing_live_fetch_contract(tmp_path):
    bundle_path = _mutate_bundle(
        _write_bundle(tmp_path),
        lambda bundle: (
            bundle.update({"live_fetch_contract": {"available": False}}),
            bundle["preflight"].pop("live_fetch_contract", None),
        ),
    )

    report = write_provider_market_data_live_rehearsal(
        bundle_path,
        tmp_path / "rehearsal",
        config=ProviderMarketDataLiveRehearsalConfig(rows_per_window=3),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "bundle_live_fetch_contract_carried" in failed
    assert not bool(report.summary.iloc[0]["source_live_fetch_contract_available"])
    assert report.ingest is None
    assert report.action_queue.loc[0, "action"] == "regenerate_capture_bundle_with_live_fetch_contract"
    assert report.action_queue.loc[0, "next_gate"] == "bundle-provider-market-data-live-capture"


def test_cli_provider_market_data_live_rehearsal_can_skip_ingest(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    out_dir = tmp_path / "cli_rehearsal"

    code = main(
        [
            "rehearse-provider-market-data-live-capture",
            "--capture-bundle",
            str(bundle_path),
            "--out",
            str(out_dir),
            "--rows-per-window",
            "2",
            "--no-run-ingest",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "provider_market_data_live_rehearsal_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "synthetic_only"])
    assert not bool(summary.loc[0, "ingest_ready"])
