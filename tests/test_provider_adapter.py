import json
from pathlib import Path

import pandas as pd
import pytest

from provider_adapter import ProviderAdapterError, execute_provider_capture, main


START = "2026-06-23T09:15:00+05:30"
END = "2026-06-23T09:45:00+05:30"
SCHEMA = ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
ENVIRONMENT = {
    "ARROW_MONEY_API_KEY": "present-runtime-value-1",
    "ARROW_MONEY_API_SECRET": "present-runtime-value-2",
}


def _write_contract(tmp_path: Path) -> tuple[Path, Path, Path]:
    output = (tmp_path / "captures" / "open.csv").resolve()
    env_template = tmp_path / "provider_market_data_live_capture_env_template.env"
    env_template.write_text(
        "ARROW_MONEY_API_KEY=\nARROW_MONEY_API_SECRET=\n",
        encoding="utf-8",
    )
    handoff = tmp_path / "provider_market_data_adapter_handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "provider": "arrow_money",
                "transport": "websocket",
                "endpoint": "wss://feed.arrow.money/market-data/nse",
                "market": "india_nse_index_derivatives",
                "exchange": "NFO",
                "kind": "ticks",
                "capture_env_template": env_template.name,
                "authentication": {
                    "env_vars": ["ARROW_MONEY_API_KEY", "ARROW_MONEY_API_SECRET"],
                    "values_stored": False,
                },
                "output": {"format": "csv", "schema_columns": SCHEMA},
                "capture_windows": [
                    {
                        "provider": "arrow_money",
                        "transport": "websocket",
                        "endpoint": "wss://feed.arrow.money/market-data/nse",
                        "market": "india_nse_index_derivatives",
                        "exchange": "NFO",
                        "kind": "ticks",
                        "start_local": START,
                        "end_local": END,
                        "capture_path": str(output),
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return handoff, env_template, output


def _arguments(handoff: Path, env_template: Path, output: Path) -> dict[str, object]:
    return {
        "handoff_path": handoff,
        "env_template_path": env_template,
        "provider": "arrow_money",
        "transport": "websocket",
        "endpoint": "wss://feed.arrow.money/market-data/nse",
        "market": "india_nse_index_derivatives",
        "exchange": "NFO",
        "kind": "ticks",
        "start_local": START,
        "end_local": END,
        "output_path": output,
        "backend_entrypoint": "trusted_arrow_backend:capture",
        "environ": ENVIRONMENT,
    }


def _write_valid_capture(request) -> None:
    frame = pd.DataFrame(
        [
            {
                "ts": request.start_ns,
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": 75,
                "ask_qty": 150,
                "last": 100.05,
                "last_qty": 75,
            },
            {
                "ts": request.start_ns + 1_000_000,
                "bid": 100.05,
                "ask": 100.10,
                "bid_qty": 150,
                "ask_qty": 75,
                "last": 100.05,
                "last_qty": 75,
            },
        ],
        columns=request.schema_columns,
    )
    frame.to_csv(request.output_path, index=False)


def test_provider_adapter_executes_trusted_backend_and_writes_safe_receipt(tmp_path):
    handoff, env_template, output = _write_contract(tmp_path)

    result = execute_provider_capture(
        **_arguments(handoff, env_template, output),
        backend=_write_valid_capture,
    )

    assert result.receipt["ready"] is True
    assert result.receipt["evidence_class"] == "provider_live_capture"
    assert result.receipt["credential_values_stored"] is False
    assert result.receipt["credential_env_presence"] == {
        "ARROW_MONEY_API_KEY": True,
        "ARROW_MONEY_API_SECRET": True,
    }
    assert result.receipt["output"]["row_count"] == 2
    assert result.receipt["output"]["columns"] == SCHEMA
    assert len(result.receipt["output"]["sha256"]) == 64
    receipt_text = result.receipt_path.read_text(encoding="utf-8")
    assert "present-runtime-value-1" not in receipt_text
    assert "present-runtime-value-2" not in receipt_text


def test_provider_adapter_cli_loads_backend_from_provider_environment(tmp_path, monkeypatch, capsys):
    handoff, env_template, output = _write_contract(tmp_path)
    backend_module = tmp_path / "trusted_test_backend.py"
    backend_module.write_text(
        "import pandas as pd\n"
        "def capture(request):\n"
        "    rows = [[request.start_ns, 100.0, 100.05, 75, 75, 100.0, 75]]\n"
        "    pd.DataFrame(rows, columns=request.schema_columns).to_csv(request.output_path, index=False)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("ARROW_MONEY_PROVIDER_ADAPTER_BACKEND", "trusted_test_backend:capture")
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    code = main(_cli_arguments(handoff, env_template, output))

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backend_entrypoint"] == "trusted_test_backend:capture"
    assert payload["output"]["row_count"] == 1


def test_provider_adapter_cli_fails_closed_without_backend(tmp_path, monkeypatch, capsys):
    handoff, env_template, output = _write_contract(tmp_path)
    monkeypatch.delenv("ARROW_MONEY_PROVIDER_ADAPTER_BACKEND", raising=False)
    monkeypatch.delenv("PROVIDER_ADAPTER_BACKEND", raising=False)

    code = main(_cli_arguments(handoff, env_template, output))

    assert code == 2
    assert "no provider backend configured" in capsys.readouterr().err
    assert not output.exists()


def test_provider_adapter_blocks_handoff_identity_mismatch(tmp_path):
    handoff, env_template, output = _write_contract(tmp_path)
    arguments = _arguments(handoff, env_template, output)
    arguments["provider"] = "irage"

    with pytest.raises(ProviderAdapterError, match="provider does not match"):
        execute_provider_capture(**arguments, backend=_write_valid_capture)


def test_provider_adapter_blocks_persisted_credential_template_value(tmp_path):
    handoff, env_template, output = _write_contract(tmp_path)
    env_template.write_text(
        "ARROW_MONEY_API_KEY=must-have-been-blank\nARROW_MONEY_API_SECRET=\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderAdapterError, match="must not persist a value"):
        execute_provider_capture(
            **_arguments(handoff, env_template, output),
            backend=_write_valid_capture,
        )


def test_provider_adapter_blocks_missing_runtime_credentials(tmp_path):
    handoff, env_template, output = _write_contract(tmp_path)
    arguments = _arguments(handoff, env_template, output)
    arguments["environ"] = {"ARROW_MONEY_API_KEY": "present"}

    with pytest.raises(ProviderAdapterError, match="ARROW_MONEY_API_SECRET"):
        execute_provider_capture(**arguments, backend=_write_valid_capture)


def test_provider_adapter_blocks_backend_output_schema_drift(tmp_path):
    handoff, env_template, output = _write_contract(tmp_path)

    def write_bad_schema(request) -> None:
        pd.DataFrame(
            [[request.start_ns, 100.0, 100.05, 75, 75]],
            columns=["ts", "bid", "ask", "bid_qty", "ask_qty"],
        ).to_csv(request.output_path, index=False)

    with pytest.raises(ProviderAdapterError, match="must exactly match"):
        execute_provider_capture(
            **_arguments(handoff, env_template, output),
            backend=write_bad_schema,
        )


def test_provider_adapter_blocks_rows_outside_capture_window(tmp_path):
    handoff, env_template, output = _write_contract(tmp_path)

    def write_late_tick(request) -> None:
        pd.DataFrame(
            [[request.end_ns + 1, 100.0, 100.05, 75, 75, 100.0, 75]],
            columns=request.schema_columns,
        ).to_csv(request.output_path, index=False)

    with pytest.raises(ProviderAdapterError, match="outside the requested session window"):
        execute_provider_capture(
            **_arguments(handoff, env_template, output),
            backend=write_late_tick,
        )


def _cli_arguments(handoff: Path, env_template: Path, output: Path) -> list[str]:
    return [
        "capture",
        "--handoff",
        str(handoff),
        "--env-template",
        str(env_template),
        "--provider",
        "arrow_money",
        "--transport",
        "websocket",
        "--endpoint",
        "wss://feed.arrow.money/market-data/nse",
        "--market",
        "india_nse_index_derivatives",
        "--exchange",
        "NFO",
        "--kind",
        "ticks",
        "--start",
        START,
        "--end",
        END,
        "--output",
        str(output),
    ]
