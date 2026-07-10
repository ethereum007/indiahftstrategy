from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd


Backend = Callable[["ProviderCaptureRequest"], None]


class ProviderAdapterError(RuntimeError):
    """Raised when a provider capture cannot satisfy its handoff contract."""


@dataclass(frozen=True)
class ProviderCaptureRequest:
    handoff_path: Path
    env_template_path: Path
    provider: str
    transport: str
    endpoint: str
    market: str
    exchange: str
    kind: str
    start_local: str
    end_local: str
    start_ns: int
    end_ns: int
    output_path: Path
    schema_columns: tuple[str, ...]
    credential_env_vars: tuple[str, ...]
    credential_env_presence: Mapping[str, bool]
    backend_entrypoint: str


@dataclass(frozen=True)
class ProviderCaptureResult:
    request: ProviderCaptureRequest
    receipt: dict[str, object]
    receipt_path: Path


@dataclass(frozen=True)
class ProviderCaptureReceiptValidation:
    receipt_path: Path
    exists: bool
    readable: bool
    receipt_sha256: str
    ready: bool
    evidence_class: str
    backend_entrypoint: str
    capture_match: bool
    contract_match: bool
    handoff_match: bool
    env_template_match: bool
    credential_contract_safe: bool
    window_match: bool
    schema_match: bool
    row_count: int
    error: str

    @property
    def passed(self) -> bool:
        return bool(
            self.exists
            and self.readable
            and self.ready
            and self.evidence_class == "provider_live_capture"
            and self.backend_entrypoint
            and self.capture_match
            and self.contract_match
            and self.handoff_match
            and self.env_template_match
            and self.credential_contract_safe
            and self.window_match
            and self.schema_match
            and self.row_count >= 1
            and not self.error
        )


def execute_provider_capture(
    *,
    handoff_path: str | Path,
    env_template_path: str | Path,
    provider: str,
    transport: str,
    endpoint: str,
    market: str,
    exchange: str,
    kind: str,
    start_local: str,
    end_local: str,
    output_path: str | Path,
    backend: Backend,
    backend_entrypoint: str,
    overwrite: bool = False,
    environ: Mapping[str, str] | None = None,
) -> ProviderCaptureResult:
    environment = dict(os.environ if environ is None else environ)
    handoff_file = Path(handoff_path).resolve()
    handoff = _read_handoff(handoff_file)
    request = _capture_request(
        handoff=handoff,
        handoff_path=handoff_file,
        env_template_path=env_template_path,
        provider=provider,
        transport=transport,
        endpoint=endpoint,
        market=market,
        exchange=exchange,
        kind=kind,
        start_local=start_local,
        end_local=end_local,
        output_path=output_path,
        backend_entrypoint=backend_entrypoint,
        environ=environment,
    )
    receipt_path = Path(f"{request.output_path}.adapter.json")
    collisions = [path for path in (request.output_path, receipt_path) if path.exists()]
    if collisions and not overwrite:
        raise ProviderAdapterError(
            "capture output already exists; pass --overwrite only after reviewing the prior artifact: "
            + ", ".join(str(path) for path in collisions)
        )

    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        backend(request)
    except Exception as exc:  # pragma: no cover - backend behavior is external
        raise ProviderAdapterError(
            f"provider backend raised {type(exc).__name__}; inspect backend logs for details"
        ) from exc

    output_state = _validate_capture_output(request)
    receipt = {
        "schema_version": 1,
        "ready": True,
        "evidence_class": "provider_live_capture",
        "provider": request.provider,
        "transport": request.transport,
        "endpoint": request.endpoint,
        "market": request.market,
        "exchange": request.exchange,
        "kind": request.kind,
        "backend_entrypoint": request.backend_entrypoint,
        "handoff": {
            "path": str(request.handoff_path),
            "sha256": _file_sha256(request.handoff_path),
        },
        "credential_env_template": {
            "path": str(request.env_template_path),
            "sha256": _file_sha256(request.env_template_path),
        },
        "credential_env_vars": list(request.credential_env_vars),
        "credential_env_presence": dict(request.credential_env_presence),
        "credential_values_stored": False,
        "window": {
            "start_local": request.start_local,
            "end_local": request.end_local,
            "start_ns": request.start_ns,
            "end_ns": request.end_ns,
        },
        "output": output_state,
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return ProviderCaptureResult(request=request, receipt=receipt, receipt_path=receipt_path)


def validate_provider_capture_receipt(
    *,
    receipt_path: str | Path,
    capture_path: str | Path,
    handoff_path: str | Path,
    env_template_path: str | Path,
    provider: str,
    transport: str,
    endpoint: str,
    market: str,
    exchange: str,
    kind: str,
    start_local: str,
    end_local: str,
    schema_columns: Sequence[str],
    credential_env_vars: Sequence[str],
) -> ProviderCaptureReceiptValidation:
    receipt_file = Path(receipt_path).resolve()
    defaults = {
        "receipt_path": receipt_file,
        "exists": receipt_file.exists() and receipt_file.is_file(),
        "readable": False,
        "receipt_sha256": "",
        "ready": False,
        "evidence_class": "",
        "backend_entrypoint": "",
        "capture_match": False,
        "contract_match": False,
        "handoff_match": False,
        "env_template_match": False,
        "credential_contract_safe": False,
        "window_match": False,
        "schema_match": False,
        "row_count": 0,
        "error": "adapter receipt does not exist",
    }
    if not defaults["exists"]:
        return ProviderCaptureReceiptValidation(**defaults)
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        defaults["error"] = f"adapter receipt is not readable JSON ({type(exc).__name__})"
        return ProviderCaptureReceiptValidation(**defaults)
    if not isinstance(receipt, dict):
        defaults["error"] = "adapter receipt JSON must be an object"
        return ProviderCaptureReceiptValidation(**defaults)

    capture_file = Path(capture_path).resolve()
    handoff_file = Path(handoff_path).resolve()
    env_template_file = Path(env_template_path).resolve()
    output = receipt.get("output") if isinstance(receipt.get("output"), dict) else {}
    receipt_handoff = receipt.get("handoff") if isinstance(receipt.get("handoff"), dict) else {}
    receipt_template = (
        receipt.get("credential_env_template")
        if isinstance(receipt.get("credential_env_template"), dict)
        else {}
    )
    window = receipt.get("window") if isinstance(receipt.get("window"), dict) else {}
    env_presence = (
        receipt.get("credential_env_presence")
        if isinstance(receipt.get("credential_env_presence"), dict)
        else {}
    )
    expected_env_vars = [str(name) for name in credential_env_vars]
    receipt_env_vars = receipt.get("credential_env_vars")
    receipt_env_vars = (
        [str(name) for name in receipt_env_vars]
        if isinstance(receipt_env_vars, list)
        else []
    )
    row_count = _safe_int(output.get("row_count"))
    capture_match = bool(
        _receipt_path_matches(output.get("path"), capture_file)
        and capture_file.exists()
        and _text(output.get("sha256")) == _file_sha256(capture_file)
        and row_count >= 1
    )
    handoff_match = bool(
        _receipt_path_matches(receipt_handoff.get("path"), handoff_file)
        and handoff_file.exists()
        and _text(receipt_handoff.get("sha256")) == _file_sha256(handoff_file)
    )
    env_template_match = bool(
        _receipt_path_matches(receipt_template.get("path"), env_template_file)
        and env_template_file.exists()
        and _text(receipt_template.get("sha256")) == _file_sha256(env_template_file)
    )
    contract_match = all(
        _text(receipt.get(field)) == expected
        for field, expected in {
            "provider": provider,
            "transport": transport,
            "endpoint": endpoint,
            "market": market,
            "exchange": exchange,
            "kind": kind,
        }.items()
    )
    credential_contract_safe = bool(
        receipt.get("credential_values_stored") is False
        and receipt_env_vars == expected_env_vars
        and set(env_presence) == set(expected_env_vars)
        and all(value is True for value in env_presence.values())
    )
    window_match = bool(
        _text(window.get("start_local")) == start_local
        and _text(window.get("end_local")) == end_local
        and _safe_int(window.get("start_ns")) == _iso_ns(start_local, "start")
        and _safe_int(window.get("end_ns")) == _iso_ns(end_local, "end")
    )
    schema_match = output.get("columns") == [str(column) for column in schema_columns]
    ready = receipt.get("ready") is True
    evidence_class = _text(receipt.get("evidence_class"))
    backend_entrypoint = _text(receipt.get("backend_entrypoint"))
    failures = [
        name
        for name, passed in {
            "receipt_ready": ready,
            "evidence_class": evidence_class == "provider_live_capture",
            "backend_entrypoint": bool(backend_entrypoint),
            "capture_match": capture_match,
            "contract_match": contract_match,
            "handoff_match": handoff_match,
            "env_template_match": env_template_match,
            "credential_contract_safe": credential_contract_safe,
            "window_match": window_match,
            "schema_match": schema_match,
            "row_count": row_count >= 1,
        }.items()
        if not passed
    ]
    return ProviderCaptureReceiptValidation(
        receipt_path=receipt_file,
        exists=True,
        readable=True,
        receipt_sha256=_file_sha256(receipt_file),
        ready=ready,
        evidence_class=evidence_class,
        backend_entrypoint=backend_entrypoint,
        capture_match=capture_match,
        contract_match=contract_match,
        handoff_match=handoff_match,
        env_template_match=env_template_match,
        credential_contract_safe=credential_contract_safe,
        window_match=window_match,
        schema_match=bool(schema_match),
        row_count=row_count,
        error=";".join(failures),
    )


def backend_env_var(provider: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
    if not key:
        raise ProviderAdapterError("provider must contain an alphanumeric character")
    return f"{key}_PROVIDER_ADAPTER_BACKEND"


def _capture_request(
    *,
    handoff: dict[str, object],
    handoff_path: Path,
    env_template_path: str | Path,
    provider: str,
    transport: str,
    endpoint: str,
    market: str,
    exchange: str,
    kind: str,
    start_local: str,
    end_local: str,
    output_path: str | Path,
    backend_entrypoint: str,
    environ: Mapping[str, str],
) -> ProviderCaptureRequest:
    if not _as_bool(handoff.get("ready")):
        raise ProviderAdapterError("adapter handoff is not ready")
    if int(handoff.get("schema_version") or 0) != 1:
        raise ProviderAdapterError("adapter handoff schema_version must be 1")

    supplied = {
        "provider": provider,
        "transport": transport,
        "endpoint": endpoint,
        "market": market,
        "exchange": exchange,
        "kind": kind,
    }
    for field, actual in supplied.items():
        expected = _text(handoff.get(field))
        if actual != expected:
            raise ProviderAdapterError(
                f"{field} does not match adapter handoff: expected {expected!r}, got {actual!r}"
            )

    output = _mapping(handoff.get("output"), "output")
    schema_columns = tuple(_string_list(output.get("schema_columns"), "output.schema_columns"))
    if not schema_columns:
        raise ProviderAdapterError("adapter handoff output schema is empty")

    auth = _mapping(handoff.get("authentication"), "authentication")
    if _as_bool(auth.get("values_stored")):
        raise ProviderAdapterError("adapter handoff must not store credential values")
    credential_env_vars = tuple(_string_list(auth.get("env_vars"), "authentication.env_vars"))

    expected_template_name = _text(handoff.get("capture_env_template"))
    template_path = _resolve_relative_path(env_template_path, handoff_path.parent)
    if not template_path.exists() or not template_path.is_file():
        raise ProviderAdapterError(f"credential env template does not exist: {template_path}")
    if expected_template_name:
        expected_template = _resolve_relative_path(expected_template_name, handoff_path.parent)
        if template_path != expected_template:
            raise ProviderAdapterError(
                f"credential env template does not match handoff: expected {expected_template}, got {template_path}"
            )
    template_vars = _blank_env_template_vars(template_path)
    if set(template_vars) != set(credential_env_vars):
        raise ProviderAdapterError(
            "credential env template variables do not match the handoff authentication contract"
        )
    credential_presence = {
        name: bool(str(environ.get(name, "")).strip()) for name in credential_env_vars
    }
    missing = [name for name, present in credential_presence.items() if not present]
    if missing:
        raise ProviderAdapterError(
            "required credential environment variables are missing: " + ", ".join(missing)
        )

    resolved_output = Path(output_path).resolve()
    window = _matching_window(
        handoff,
        output_path=resolved_output,
        start_local=start_local,
        end_local=end_local,
    )
    for field, actual in supplied.items():
        expected = _text(window.get(field))
        if expected and actual != expected:
            raise ProviderAdapterError(
                f"capture window {field} does not match request: expected {expected!r}, got {actual!r}"
            )

    start_ns = _iso_ns(start_local, "start")
    end_ns = _iso_ns(end_local, "end")
    if end_ns <= start_ns:
        raise ProviderAdapterError("capture window end must be after start")
    if not backend_entrypoint.strip():
        raise ProviderAdapterError("provider backend entrypoint is required")

    return ProviderCaptureRequest(
        handoff_path=handoff_path,
        env_template_path=template_path,
        provider=provider,
        transport=transport,
        endpoint=endpoint,
        market=market,
        exchange=exchange,
        kind=kind,
        start_local=start_local,
        end_local=end_local,
        start_ns=start_ns,
        end_ns=end_ns,
        output_path=resolved_output,
        schema_columns=schema_columns,
        credential_env_vars=credential_env_vars,
        credential_env_presence=credential_presence,
        backend_entrypoint=backend_entrypoint,
    )


def _matching_window(
    handoff: Mapping[str, object],
    *,
    output_path: Path,
    start_local: str,
    end_local: str,
) -> dict[str, object]:
    windows = handoff.get("capture_windows")
    if not isinstance(windows, list) or not windows:
        raise ProviderAdapterError("adapter handoff has no capture windows")
    for item in windows:
        if not isinstance(item, dict):
            continue
        capture_path = _text(item.get("capture_path") or item.get("output"))
        if not capture_path:
            continue
        if Path(capture_path).resolve() != output_path:
            continue
        if _text(item.get("start_local")) != start_local:
            continue
        if _text(item.get("end_local")) != end_local:
            continue
        return item
    raise ProviderAdapterError(
        "capture request does not match an exact output/start/end window in the adapter handoff"
    )


def _validate_capture_output(request: ProviderCaptureRequest) -> dict[str, object]:
    path = request.output_path
    if not path.exists() or not path.is_file():
        raise ProviderAdapterError(f"provider backend did not create the capture output: {path}")
    if path.stat().st_size <= 0:
        raise ProviderAdapterError(f"provider backend created an empty capture output: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise ProviderAdapterError(
            f"provider capture is not a readable CSV ({type(exc).__name__})"
        ) from exc
    if list(frame.columns) != list(request.schema_columns):
        raise ProviderAdapterError(
            "provider capture columns must exactly match the handoff schema: "
            f"expected {list(request.schema_columns)}, got {list(frame.columns)}"
        )
    if frame.empty:
        raise ProviderAdapterError("provider capture must contain at least one row")
    if "ts" not in frame.columns:
        raise ProviderAdapterError("provider capture schema must include ts")

    ts = _capture_timestamp_ns(frame["ts"], request)
    if not ts.is_monotonic_increasing:
        raise ProviderAdapterError("provider capture timestamps must be monotonic")
    if bool((ts < request.start_ns).any()) or bool((ts > request.end_ns).any()):
        raise ProviderAdapterError("provider capture contains rows outside the requested session window")

    required_prices = [col for col in ("bid", "ask") if col in frame.columns]
    required_qty = [col for col in ("bid_qty", "ask_qty") if col in frame.columns]
    for prefix in ("call", "put"):
        required_prices.extend(
            col for col in (f"{prefix}_bid", f"{prefix}_ask") if col in frame.columns
        )
        required_qty.extend(
            col for col in (f"{prefix}_bid_qty", f"{prefix}_ask_qty") if col in frame.columns
        )
    for column in required_prices + required_qty:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            raise ProviderAdapterError(f"provider capture {column} values must be numeric and non-null")
        if bool((values < 0).any()):
            raise ProviderAdapterError(f"provider capture {column} values must be non-negative")
    for bid_col, ask_col in (("bid", "ask"), ("call_bid", "call_ask"), ("put_bid", "put_ask")):
        if bid_col in frame.columns and ask_col in frame.columns:
            bid = pd.to_numeric(frame[bid_col], errors="coerce")
            ask = pd.to_numeric(frame[ask_col], errors="coerce")
            if bool((bid > ask).any()):
                raise ProviderAdapterError(
                    f"provider capture contains crossed {bid_col}/{ask_col} quotes"
                )

    return {
        "path": str(path),
        "sha256": _file_sha256(path),
        "row_count": int(len(frame)),
        "columns": list(frame.columns),
        "min_ts_ns": int(ts.min()),
        "max_ts_ns": int(ts.max()),
    }


def _capture_timestamp_ns(
    values: pd.Series,
    request: ProviderCaptureRequest,
) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all():
        if bool(((numeric % 1) != 0).any()):
            raise ProviderAdapterError(
                "numeric provider capture ts values must be integer nanoseconds"
            )
        return numeric.astype("int64")
    try:
        parsed = pd.to_datetime(values, errors="coerce")
    except (TypeError, ValueError) as exc:
        raise ProviderAdapterError(
            "provider capture ts values must be UTC nanoseconds or datetimes"
        ) from exc
    if parsed.isna().any():
        raise ProviderAdapterError(
            "provider capture ts values must be UTC nanoseconds or datetimes"
        )
    try:
        if parsed.dt.tz is None:
            contract_timezone = pd.Timestamp(request.start_local).tzinfo
            parsed = parsed.dt.tz_localize(contract_timezone)
        parsed = parsed.dt.tz_convert("UTC")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProviderAdapterError(
            "provider capture datetime timestamps must share one timezone contract"
        ) from exc
    return parsed.map(lambda value: pd.Timestamp(value).value).astype("int64")


def _read_handoff(path: Path) -> dict[str, object]:
    if not path.exists() or not path.is_file():
        raise ProviderAdapterError(f"adapter handoff does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProviderAdapterError(f"adapter handoff JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProviderAdapterError("adapter handoff JSON must be an object")
    return payload


def _blank_env_template_vars(path: Path) -> list[str]:
    names: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ProviderAdapterError(
                f"credential env template line {line_number} must use NAME="
            )
        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ProviderAdapterError(
                f"credential env template line {line_number} has an invalid variable name"
            )
        if value.strip():
            raise ProviderAdapterError(
                f"credential env template must not persist a value for {name}"
            )
        if name in names:
            raise ProviderAdapterError(f"credential env template repeats {name}")
        names.append(name)
    return names


def _load_backend(entrypoint: str) -> Backend:
    module_name, separator, attribute = entrypoint.partition(":")
    if not separator or not module_name or not attribute:
        raise ProviderAdapterError(
            "provider backend must use the trusted Python entrypoint form module:function"
        )
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ProviderAdapterError(
            f"provider backend module {module_name!r} could not be imported ({type(exc).__name__})"
        ) from exc
    backend = getattr(module, attribute, None)
    if not callable(backend):
        raise ProviderAdapterError(f"provider backend {entrypoint!r} is not callable")
    return backend


def _backend_entrypoint(provider: str, explicit: str, environ: Mapping[str, str]) -> str:
    if explicit.strip():
        return explicit.strip()
    provider_key = backend_env_var(provider)
    return str(environ.get(provider_key) or environ.get("PROVIDER_ADAPTER_BACKEND") or "").strip()


def _iso_ns(value: str, label: str) -> int:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ProviderAdapterError(f"capture window {label} is not a valid ISO timestamp") from exc
    if stamp.tzinfo is None:
        raise ProviderAdapterError(f"capture window {label} must include a timezone offset")
    return int(stamp.tz_convert("UTC").value)


def _resolve_relative_path(value: str | Path, base: Path) -> Path:
    path = Path(value)
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _receipt_path_matches(value: object, expected: Path) -> bool:
    raw = _text(value)
    if not raw:
        return False
    try:
        return Path(raw).resolve() == expected.resolve()
    except OSError:
        return str(Path(raw)) == str(expected)


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProviderAdapterError(f"adapter handoff {label} must be an object")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProviderAdapterError(f"adapter handoff {label} must be a list of strings")
    return [item for item in value if item]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="provider-adapter",
        description="Execute a trusted provider capture backend against a credential-safe handoff.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="Capture one exact handoff window and validate its CSV output.")
    capture.add_argument("--handoff", required=True)
    capture.add_argument("--env-template", required=True)
    capture.add_argument("--provider", required=True)
    capture.add_argument("--transport", required=True)
    capture.add_argument("--endpoint", required=True)
    capture.add_argument("--market", required=True)
    capture.add_argument("--exchange", required=True)
    capture.add_argument("--kind", required=True)
    capture.add_argument("--start", required=True)
    capture.add_argument("--end", required=True)
    capture.add_argument("--output", required=True)
    capture.add_argument(
        "--backend",
        default="",
        help=(
            "Trusted Python module:function backend. Defaults to "
            "<PROVIDER>_PROVIDER_ADAPTER_BACKEND, then PROVIDER_ADAPTER_BACKEND."
        ),
    )
    capture.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment = dict(os.environ)
    try:
        entrypoint = _backend_entrypoint(args.provider, args.backend, environment)
        if not entrypoint:
            raise ProviderAdapterError(
                "no provider backend configured; set "
                f"{backend_env_var(args.provider)}=module:function or pass --backend"
            )
        backend = _load_backend(entrypoint)
        result = execute_provider_capture(
            handoff_path=args.handoff,
            env_template_path=args.env_template,
            provider=args.provider,
            transport=args.transport,
            endpoint=args.endpoint,
            market=args.market,
            exchange=args.exchange,
            kind=args.kind,
            start_local=args.start,
            end_local=args.end,
            output_path=args.output,
            backend=backend,
            backend_entrypoint=entrypoint,
            overwrite=args.overwrite,
            environ=environment,
        )
    except ProviderAdapterError as exc:
        print(f"provider-adapter: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
