import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from provider_adapter import ProviderCaptureRequest, execute_provider_capture


def write_bundle_captures(
    live_packet_path: str | Path,
    capture_bundle_path: str | Path,
    frame_factory: Callable[[ProviderCaptureRequest, int], Any],
) -> None:
    packet = json.loads(Path(live_packet_path).read_text(encoding="utf-8"))
    bundle_dir = Path(capture_bundle_path).parent
    credential_env_vars = [
        str(name) for name in packet.get("authentication", {}).get("env_vars", [])
    ]
    environ = {
        name: f"present-test-value-{index}"
        for index, name in enumerate(credential_env_vars, start=1)
    }
    for index, window in enumerate(packet["capture_windows"]):
        def backend(request: ProviderCaptureRequest, *, capture_index: int = index) -> None:
            frame_factory(request, capture_index).to_csv(request.output_path, index=False)

        execute_provider_capture(
            handoff_path=bundle_dir / "provider_market_data_adapter_handoff.json",
            env_template_path=(
                bundle_dir / "provider_market_data_live_capture_env_template.env"
            ),
            provider=packet["provider"],
            transport=packet["transport"],
            endpoint=packet["endpoint"],
            market=packet["market"],
            exchange=packet["exchange"],
            kind=packet["kind"],
            start_local=window["start_local"],
            end_local=window["end_local"],
            output_path=window["capture_path"],
            backend=backend,
            backend_entrypoint="approved_test_backend:capture",
            environ=environ,
        )
